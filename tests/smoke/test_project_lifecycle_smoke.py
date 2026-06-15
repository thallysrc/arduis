"""Phase-03.4 Plan-05 acceptance smoke (headless broadway). Runnable harness.

Proves the PERSISTENCE + LIFECYCLE wiring WITHOUT manual interaction (the live
process-tree no-orphans checks stay in the human UAT — broadway can't host real
agents/docker reliably):

  (a) PERSIST across "restart" (SC-2 / D-05): construct the window with cwd = root A
      → A auto-registers (D-07); `_open_project(rootB)` → projects.json lists A + B.
      Destroy the window; construct a FRESH window (same sandbox HOME/XDG) →
      `_init_projects` loads A + B from disk and renders TWO project tabs.
  (b) MISSING-ROOT SKIP (D-06): a projects.json listing a non-existent root + a real
      one → a new window loads ONLY the real one (no crash, the missing one dropped).
  (c) REMOVE-NO-LIVE SILENT (D-10): with two registered projects and no live tasks,
      `_remove_project(rootB)` drops B from the registry and rewrites projects.json to
      A only — no dialog constructed.

Sandbox HOME + XDG_CONFIG_HOME (projects.json lands in the sandbox, never the user's
real ~/.config/arduis — T-03.4-16); /tmp multi-repo git fixtures. The broadwayd-absent
path prints SMOKE_SKIP + sys.exit(0) BEFORE any window is built; the caller treats a 0
exit (PASS or SKIP) as OK.

Run: gtk4-broadwayd :95 & GDK_BACKEND=broadway BROADWAY_DISPLAY=:95 \
       python tests/smoke/test_project_lifecycle_smoke.py
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
    # SKIP-exit-0 BEFORE any window is built (mirrors the Plan-03 harness).
    if os.environ.get("GDK_BACKEND") == "broadway" and os.environ.get("BROADWAY_DISPLAY"):
        return None
    if shutil.which("gtk4-broadwayd") is None:
        print("SMOKE_SKIP gtk4-broadwayd not found")
        sys.exit(0)
    proc = subprocess.Popen(["gtk4-broadwayd", ":95"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    os.environ["GDK_BACKEND"] = "broadway"
    os.environ["BROADWAY_DISPLAY"] = ":95"
    return proc.pid


def _mk_repo(path, genv):
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, env=genv, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "i"], cwd=path, env=genv,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _tab_labels(chip_bar):
    """Sorted text of every Gtk.ToggleButton (project tab) in the chip bar."""
    from gi.repository import Gtk
    labels = []
    child = chip_bar.get_first_child()
    while child is not None:
        if isinstance(child, Gtk.ToggleButton):
            labels.append(child.get_child().get_text())
        child = child.get_next_sibling()
    return sorted(labels)


def main():
    bpid = _start_broadway()
    sandbox = tempfile.mkdtemp(prefix="arduis-034-lifecycle-smoke-")
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

    projects_json = os.path.join(home, ".config", "arduis", "projects.json")

    # --- two multi-repo project roots --------------------------------------------
    root_a = os.path.join(sandbox, "Livon-Saude")
    for r in ("backend", "frontend"):
        _mk_repo(os.path.join(root_a, r), genv)
    root_b = os.path.join(sandbox, "KarveLabs")
    for r in ("api", "web"):
        _mk_repo(os.path.join(root_b, r), genv)

    app = Adw.Application(application_id="dev.smoke.arduis034lifecycle")

    def on_activate(a):
        # ============================================================
        # (a) PERSIST across restart (SC-2 / D-05 / D-07)
        # ============================================================
        # Launch INSIDE root A (no projects.json yet) → A auto-registers (D-07).
        os.chdir(root_a)
        win1 = ArduisWindow(application=a)
        a_autoregistered = win1._registry.get(root_a) is not None
        check("a_cwd_autoregisters_on_launch", a_autoregistered)

        # Open root B → projects.json now lists A + B (persisted on add).
        win1._open_project(root_b)
        roots_after_open, last_after_open = projects_store.load_projects(projects_json)
        json_has_both = sorted(roots_after_open) == sorted([root_a, root_b])
        check("a_open_project_persists_both_to_json", json_has_both)

        # Destroy win1 and build a FRESH window in the SAME sandbox → restore from disk.
        win1.destroy()
        # Relaunch from a NEUTRAL dir (the sandbox itself, not a project) so the
        # restore comes purely from projects.json, not cwd auto-register.
        os.chdir(sandbox)
        win2 = ArduisWindow(application=a)
        restored = win2._registry.get(root_a) is not None and (
            win2._registry.get(root_b) is not None
        )
        check("a_both_projects_restored_after_restart", restored)
        tabs_after_restart = _tab_labels(win2._chip_bar)
        check("a_two_tabs_rendered_after_restart",
              tabs_after_restart == ["KarveLabs", "Livon-Saude"])
        win2.destroy()

        # ============================================================
        # (b) MISSING-ROOT SKIP (D-06)
        # ============================================================
        ghost = os.path.join(sandbox, "deleted-project")  # never created on disk
        projects_store.save_projects(projects_json, [root_a, ghost], root_a)
        os.chdir(sandbox)  # neutral cwd → registry comes from JSON only
        win3 = ArduisWindow(application=a)
        only_real = (
            win3._registry.get(root_a) is not None
            and win3._registry.get(ghost) is None
        )
        check("b_missing_root_skipped_real_loaded", only_real)
        tabs_b = _tab_labels(win3._chip_bar)
        check("b_one_tab_only", tabs_b == ["Livon-Saude"])
        win3.destroy()

        # ============================================================
        # (c) REMOVE-NO-LIVE SILENT (D-10)
        # ============================================================
        # Two registered projects, no live (ACTIVE) tasks → _remove_project drops
        # B silently (no Adw.AlertDialog) and rewrites projects.json to A only.
        projects_store.save_projects(projects_json, [root_a, root_b], root_a)
        os.chdir(sandbox)
        win4 = ArduisWindow(application=a)
        both_registered_before = (
            win4._registry.get(root_a) is not None
            and win4._registry.get(root_b) is not None
        )
        win4._remove_project(root_b)
        b_dropped = (
            win4._registry.get(root_b) is None
            and win4._registry.get(root_a) is not None
        )
        check("c_silent_remove_drops_b_from_registry",
              both_registered_before and b_dropped)
        roots_after_remove, _ = projects_store.load_projects(projects_json)
        check("c_silent_remove_rewrites_json_to_a_only",
              roots_after_remove == [root_a])
        tabs_c = _tab_labels(win4._chip_bar)
        check("c_one_tab_after_remove", tabs_c == ["Livon-Saude"])
        win4.destroy()

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
