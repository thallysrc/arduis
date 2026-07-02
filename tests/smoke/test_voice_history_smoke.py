"""Voice-agent step-4 smoke (headless broadway). Runnable harness.

Proves, without a display and WITHOUT touching the real ~/.config/arduis:
  - ``_run_voice_prompt`` splits a NEW agent pane in the active workspace and feeds
    exactly ``prompt_feed_bytes(cmd, <normalized prompt>)`` into its shell;
  - the spoken prompt lands at the top of ``voice_history.json`` (persisted);
  - a default split (no ``feed=``) still feeds the plain agent command —
    byte-identical legacy behavior;
  - an empty/whitespace prompt is a strict no-op (no pane, no history entry);
  - the header has the mic toggle + history menu button.

Run: gtk4-broadwayd :97 & GDK_BACKEND=broadway BROADWAY_DISPLAY=:97 \
       python tests/smoke/test_voice_history_smoke.py
SKIPS (exit 0) if gtk4-broadwayd is absent. Broadwayd killed in finally.
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
    if os.environ.get("GDK_BACKEND") == "broadway" and os.environ.get("BROADWAY_DISPLAY"):
        return None
    if shutil.which("gtk4-broadwayd") is None:
        print("SMOKE_SKIP gtk4-broadwayd not found")
        sys.exit(0)
    proc = subprocess.Popen(["gtk4-broadwayd", ":97"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    os.environ["GDK_BACKEND"] = "broadway"
    os.environ["BROADWAY_DISPLAY"] = ":97"
    return proc.pid


def main():
    bpid = _start_broadway()
    sandbox = tempfile.mkdtemp(prefix="arduis-voice-smoke-")
    home = os.path.join(sandbox, "home")
    os.makedirs(os.path.join(home, ".config", "arduis"))
    proj = os.path.join(sandbox, "proj")
    os.makedirs(proj)
    genv = {**os.environ, "HOME": home, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "init", "-q"], cwd=proj, env=genv, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "i"], cwd=proj, env=genv,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    os.environ["HOME"] = home  # do NOT override XDG_RUNTIME_DIR (broadway socket)
    os.chdir(proj)
    sys.path.insert(0, os.path.join(REPO, "src"))

    import gi
    gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); gi.require_version("Vte", "3.91")
    from gi.repository import Adw, GLib
    from arduis import agentconfig, voice_store
    from arduis.session import Workspace, RepoCheckout, SessionState, default_workspace_terminals
    from arduis.window import ArduisWindow

    app = Adw.Application(application_id="dev.smoke.arduisvoice")

    def on_activate(a):
        win = ArduisWindow(application=a)

        check("history_path_sandboxed", win._voice_history_path.startswith(home))
        check("mic_button_exists", getattr(win, "_voice_btn", None) is not None)
        check("history_button_exists", getattr(win, "_voice_history_btn", None) is not None)

        workspace_dir = os.path.join(sandbox, "proj-workspaces", "feat")
        wt = os.path.join(workspace_dir, "proj")
        os.makedirs(wt)
        workspace = Workspace(workspace_id="feat", branch="feat", workspace_dir=workspace_dir,
                    repos=[RepoCheckout(repo_name="proj", worktree_dir=wt, branch="feat")],
                    state=SessionState.ACTIVE, terminals=default_workspace_terminals("feat"))
        win._store.add(workspace)
        win._rebuild_sidebar()
        win._build_workspace_terminals(workspace, ["proj"])
        win._swap_workspace("feat")

        # capture every feed on terminals created from here on
        fed = {}
        orig_make = win._make_terminal

        def make_wrapped():
            t = orig_make()
            t.feed_child = (lambda term: lambda b: fed.__setitem__(
                id(term), fed.get(id(term), b"") + bytes(b)))(t)
            return t
        win._make_terminal = make_wrapped

        def wait_for(pred, timeout_s=15.0):
            ctx = GLib.MainContext.default()
            deadline = time.time() + timeout_s
            while time.time() < deadline:
                ctx.iteration(False)
                if pred():
                    return True
                time.sleep(0.01)
            return False

        # --- spoken prompt → new pane fed with claude '<prompt>' -------------
        before = set(win._term_by_sid)
        win._run_voice_prompt("  fix the\nlogin bug ")
        new_tids = set(win._term_by_sid) - before
        check("voice_prompt_creates_pane", len(new_tids) == 1)
        got_feed = wait_for(lambda: any(fed.values()))
        expected = agentconfig.prompt_feed_bytes("claude", "fix the login bug")
        feeds = [b for b in fed.values() if b]
        check("voice_prompt_fed_bytes",
              got_feed and len(feeds) == 1 and feeds[0] == expected)

        # --- history persisted, normalized, newest first ----------------------
        hist = voice_store.load_history(win._voice_history_path)
        check("history_has_normalized_prompt",
              len(hist) == 1 and hist[0]["text"] == "fix the login bug")

        # --- default split (no feed) keeps legacy bytes ------------------------
        fed.clear()
        model = win._active_layout()
        win._split_active_pane(model.focused_id, "h")
        got_default = wait_for(lambda: any(fed.values()))
        legacy = agentconfig.agent_feed_bytes("claude")
        dfeeds = [b for b in fed.values() if b]
        check("default_split_unchanged",
              got_default and len(dfeeds) == 1 and dfeeds[0] == legacy)

        # --- empty prompt is a strict no-op ------------------------------------
        fed.clear()
        before = set(win._term_by_sid)
        win._run_voice_prompt("   \n ")
        check("empty_prompt_noop",
              set(win._term_by_sid) == before
              and len(voice_store.load_history(win._voice_history_path)) == 1)

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
