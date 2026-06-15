"""Phase-03.4 Plan-03 acceptance smoke (headless broadway). Runnable harness.

Proves, WITHOUT manual interaction:
  (a) constructing the window with two remembered project roots renders exactly two
      project tabs + a "+ Abrir projeto" button (D-03);
  (b) after `win._switch_project(rootB)`, project A's `leaf_by_sid`/`term_by_sid`
      entries still exist and reference the SAME widget objects (NOT recreated/
      destroyed) — proving "both alive" (D-08);
  (c) exactly one project tab carries `arduis-chip-active` at a time.

Sandbox HOME + XDG_CONFIG_HOME; /tmp multi-repo git fixtures for TWO project roots;
broadwayd on a free display. The broadwayd-absent path prints `SMOKE_SKIP` and
`sys.exit(0)` BEFORE constructing any window (mirrors Plan 05 Task 1 / the 03.3 harness);
the caller treats a 0 exit (PASS or SKIP) as OK.

Run: gtk4-broadwayd :96 & GDK_BACKEND=broadway BROADWAY_DISPLAY=:96 \
       python tests/smoke/test_project_switch_smoke.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
results = []


def check(name, ok):
    results.append((name, ok))
    print(f"SMOKE {name} {'PASS' if ok else 'FAIL'}")


def _start_broadway():
    # SKIP-exit-0 BEFORE any window is built (mirrors Plan 05 Task 1).
    if os.environ.get("GDK_BACKEND") == "broadway" and os.environ.get("BROADWAY_DISPLAY"):
        return None
    if shutil.which("gtk4-broadwayd") is None:
        print("SMOKE_SKIP gtk4-broadwayd not found")
        sys.exit(0)
    proc = subprocess.Popen(["gtk4-broadwayd", ":96"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    os.environ["GDK_BACKEND"] = "broadway"
    os.environ["BROADWAY_DISPLAY"] = ":96"
    return proc.pid


def _mk_repo(path, genv):
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, env=genv, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "i"], cwd=path, env=genv,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _tab_buttons(chip_bar):
    """The chip-bar's children split into (toggle tabs, other buttons)."""
    import gi  # noqa
    from gi.repository import Gtk
    tabs, others = [], []
    child = chip_bar.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.ToggleButton):
            tabs.append(child)
        else:
            others.append(child)
        child = child.get_next_sibling()
    return tabs, others


def main():
    bpid = _start_broadway()
    sandbox = tempfile.mkdtemp(prefix="arduis-034-switch-smoke-")
    home = os.path.join(sandbox, "home")
    os.makedirs(os.path.join(home, ".config", "arduis"))
    os.environ["HOME"] = home
    os.environ["XDG_CONFIG_HOME"] = os.path.join(home, ".config")
    genv = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1"}
    orig_cwd = os.getcwd()
    sys.path.insert(0, os.path.join(REPO, "src"))

    import gi
    gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); gi.require_version("Vte", "3.91")
    from gi.repository import Adw, GLib
    from arduis import projects_store
    from arduis.window import ArduisWindow

    # --- two multi-repo project roots -------------------------------------------
    root_a = os.path.join(sandbox, "Livon-Saude")
    for r in ("backend", "frontend"):
        _mk_repo(os.path.join(root_a, r), genv)
    root_b = os.path.join(sandbox, "KarveLabs")
    for r in ("api", "web"):
        _mk_repo(os.path.join(root_b, r), genv)

    # remember BOTH projects; last_active = rootA. The window's _projects_json points
    # at XDG_CONFIG_HOME/arduis/projects.json (sandboxed).
    projects_json = os.path.join(home, ".config", "arduis", "projects.json")
    projects_store.save_projects(projects_json, [root_a, root_b], root_a)

    app = Adw.Application(application_id="dev.smoke.arduis034switch")

    def on_activate(a):
        os.chdir(root_a)  # launch inside rootA
        win = ArduisWindow(application=a)

        # (a) two tabs + a "+ Abrir projeto" button.
        tabs, others = _tab_buttons(win._chip_bar)
        labels = sorted(t.get_child().get_text() for t in tabs)
        two_tabs = labels == ["KarveLabs", "Livon-Saude"]
        has_open = any(
            getattr(o, "get_label", lambda: None)() == "+ Abrir projeto" for o in others
        )
        check("a_two_project_tabs", two_tabs)
        check("a_open_project_button_present", has_open)

        # capture project A's live terminal/leaf maps (identity check for D-08).
        proj_a = win._registry.get(root_a)
        a_maps = win._bundle_for(proj_a)
        a_leaves_before = dict(a_maps["leaf_by_sid"])
        a_terms_before = dict(a_maps["term_by_sid"])

        # (c-before) exactly one tab active == rootA.
        active_before = [t for t in tabs if t.has_css_class("arduis-chip-active")]
        active_is_a = (
            len(active_before) == 1
            and active_before[0].get_child().get_text() == "Livon-Saude"
        )
        check("c_single_active_before_switch", active_is_a)

        # (b) switch to rootB — A's maps must SURVIVE (same objects, not destroyed).
        win._switch_project(root_b)
        a_leaves_after = win._bundle_for(proj_a)["leaf_by_sid"]
        a_terms_after = win._bundle_for(proj_a)["term_by_sid"]
        leaves_alive = all(
            sid in a_leaves_after and a_leaves_after[sid] is widget
            for sid, widget in a_leaves_before.items()
        )
        terms_alive = all(
            tid in a_terms_after and a_terms_after[tid] is term
            for tid, term in a_terms_before.items()
        )
        # there WAS at least one leaf/term to keep alive (main scratch leaf).
        had_state = len(a_leaves_before) >= 1
        check("b_projectA_terminals_alive_after_switch",
              had_state and leaves_alive and terms_alive)

        # (c-after) exactly one tab active == rootB.
        tabs2, _ = _tab_buttons(win._chip_bar)
        active_after = [t for t in tabs2 if t.has_css_class("arduis-chip-active")]
        active_is_b = (
            len(active_after) == 1
            and active_after[0].get_child().get_text() == "KarveLabs"
        )
        check("c_single_active_after_switch", active_is_b)

        GLib.idle_add(a.quit)

    app.connect("activate", on_activate)
    try:
        app.run(None)
    finally:
        os.chdir(orig_cwd)
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
