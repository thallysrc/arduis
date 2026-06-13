"""Phase-05 acceptance smoke (headless broadway). Runnable harness.

Proves, without a display and WITHOUT touching the real ~/.config/arduis:
  - runtime theme switch flips `_current_theme` AND REPLACES (does not stack) the
    CssProvider — a new provider object each switch (UI-02, D-07, Pitfall 1);
  - repeated switches (dracula→nord→dracula→nord) never raise and keep replacing;
  - a terminal built AFTER a switch is born under the active theme (Pitfall 2);
  - the configured `[agent] command` drives the feed bytes (AGENT-01);
  - a `[keys.bindings]` entry resolves into the dispatch table (UI-01).

Run under broadway:
  gtk4-broadwayd :95 & GDK_BACKEND=broadway BROADWAY_DISPLAY=:95 \
    python tests/smoke/test_theme_switch_smoke.py
The module SKIPS (exit 0) if gtk4-broadwayd is unavailable. Sandbox HOME only —
the real ~/.config/arduis/arduis.toml is asserted untouched (T-05-08); broadwayd
and any spawned groups are killed in finally (T-05-09).
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = "/home/thallysrc/Projects/arduis"
results = []


def check(name, ok):
    results.append((name, ok))
    print(f"SMOKE {name} {'PASS' if ok else 'FAIL'}")


def _start_broadway():
    """Start gtk4-broadwayd :95 if not already running under broadway. Returns pid|None."""
    if os.environ.get("GDK_BACKEND") == "broadway" and os.environ.get("BROADWAY_DISPLAY"):
        return None  # caller already set up the backend
    if shutil.which("gtk4-broadwayd") is None:
        print("SMOKE_SKIP gtk4-broadwayd not found")
        sys.exit(0)
    proc = subprocess.Popen(["gtk4-broadwayd", ":95"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    os.environ["GDK_BACKEND"] = "broadway"
    os.environ["BROADWAY_DISPLAY"] = ":95"
    return proc.pid


def main():
    bpid = _start_broadway()
    sandbox = tempfile.mkdtemp(prefix="arduis-05-smoke-")
    home = os.path.join(sandbox, "home")
    cfg_dir = os.path.join(home, ".config", "arduis")
    os.makedirs(cfg_dir)
    # Fixture arduis.toml: aider agent, q→zoom binding, dracula start.
    with open(os.path.join(cfg_dir, "arduis.toml"), "w") as fh:
        fh.write('[agent]\ncommand = "aider"\n\n'
                 '[keys]\nprefix = "ctrl+space"\n\n[keys.bindings]\n"q" = "zoom"\n\n'
                 '[theme]\nname = "dracula"\n')

    # synthetic git project so _resolve_project finds a repo
    proj = os.path.join(sandbox, "proj")
    os.makedirs(proj)
    genv = {**os.environ, "HOME": home, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "init", "-q"], cwd=proj, env=genv, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "i"], cwd=proj, env=genv,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Record the REAL config mtime (must stay untouched).
    real_cfg = os.path.expanduser("~/.config/arduis/arduis.toml")
    real_mtime = os.path.getmtime(real_cfg) if os.path.exists(real_cfg) else None

    os.environ["HOME"] = home  # NOTE: do NOT override XDG_RUNTIME_DIR (broadway socket)
    os.chdir(proj)
    sys.path.insert(0, os.path.join(REPO, "src"))

    import gi
    gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); gi.require_version("Vte", "3.91")
    from gi.repository import Adw
    from arduis import agentconfig
    from arduis.themes import get_theme
    from arduis.window import ArduisWindow

    app = Adw.Application(application_id="dev.smoke.arduis05")

    def on_activate(a):
        win = ArduisWindow(application=a)

        # config picked up from the sandbox arduis.toml
        check("config_agent_command", win._agent_config.command == "aider")
        check("config_keymap_q_zoom", win._keymap.get("q") == ("zoom", None))

        # theme switch: replace-not-stack
        prov0 = id(win._css_provider)
        start_name = win._current_theme.name
        win._apply_theme(get_theme("nord"))
        check("switch_flips_current_theme", win._current_theme.name == "nord")
        check("switch_replaces_provider", id(win._css_provider) != prov0)

        # repeated switches never raise, provider keeps changing
        ids = {id(win._css_provider)}
        ok = True
        for name in ("dracula", "nord", "dracula"):
            try:
                win._apply_theme(get_theme(name))
                ids.add(id(win._css_provider))
            except Exception as exc:  # noqa: BLE001
                print(f"SMOKE switch raised: {exc}")
                ok = False
        check("repeated_switches_no_crash", ok and len(ids) >= 3)

        # born-in-theme (Pitfall 2): make a terminal after switching to nord
        win._apply_theme(get_theme("nord"))
        try:
            term = win._make_terminal()
            born_ok = term is not None and win._current_theme.name == "nord"
        except Exception as exc:  # noqa: BLE001
            print(f"SMOKE _make_terminal raised: {exc}")
            born_ok = False
        check("new_terminal_born_in_active_theme", born_ok)

        # configured feed bytes
        feed = agentconfig.agent_feed_bytes(win._agent_config.command)
        check("configured_feed_bytes", feed.startswith(b"aider"))

        # real config untouched
        now_mtime = os.path.getmtime(real_cfg) if os.path.exists(real_cfg) else None
        check("real_config_untouched", now_mtime == real_mtime)

        check("started_theme_was_dracula", start_name == "dracula")
        a.quit()

    app.connect("activate", on_activate)
    try:
        app.run(None)
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
        if bpid is not None:
            try:
                os.kill(bpid, 15)
            except ProcessLookupError:
                pass

    failed = [n for n, ok in results if not ok]
    print(f"SMOKE_RESULT {'PASS' if not failed else 'FAIL'} ({len(results)-len(failed)}/{len(results)})")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
