"""Phase-03.3 acceptance smoke (headless broadway). Runnable harness.

Proves, without a display:
  (a) clean multi-repo root → one chip per `.git`-DIR repo, all selected by default;
      toggle updates default_selection; reflect_active highlights/clears (D-01/D-02/D-03);
  (b) Livon-Saude shape (2 real repos + 20 `.git`-FILE worktrees) → exactly 2 chips, not 22,
      no overflow menu (D-04 acceptance — the user's actual complaint);
  (c) degenerate 1-repo root → 1 chip, no crash (criterion 5).
Sandbox HOME + /tmp git fixtures; broadwayd on :97 killed in finally.

Run: gtk4-broadwayd :97 & GDK_BACKEND=broadway BROADWAY_DISPLAY=:97 \
       python tests/smoke/test_topbar_chips_smoke.py
SKIPS (exit 0) if gtk4-broadwayd is absent.
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


def _mk_repo(path, genv):
    os.makedirs(path, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, env=genv, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "i"], cwd=path, env=genv,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    bpid = _start_broadway()
    sandbox = tempfile.mkdtemp(prefix="arduis-033-smoke-")
    home = os.path.join(sandbox, "home")
    os.makedirs(os.path.join(home, ".config", "arduis"))
    os.environ["HOME"] = home  # do NOT override XDG_RUNTIME_DIR
    genv = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1"}
    orig_cwd = os.getcwd()
    sys.path.insert(0, os.path.join(REPO, "src"))

    import gi
    gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); gi.require_version("Vte", "3.91")
    from gi.repository import Adw
    from arduis.project import detect_member_repos
    from arduis.window import ArduisWindow

    def build_window(app):
        return ArduisWindow(application=app)

    # --- fixture (a) clean multi-repo: 3 .git-DIR repos --------------------------
    proj_a = os.path.join(sandbox, "proj_a")
    for r in ("backend", "frontend", "keycloak"):
        _mk_repo(os.path.join(proj_a, r), genv)

    # --- fixture (b) Livon-Saude shape: 2 real repos + 20 .git-FILE worktrees ----
    proj_b = os.path.join(sandbox, "proj_b")
    for r in ("backend", "frontend"):
        _mk_repo(os.path.join(proj_b, r), genv)
    # add 20 linked worktrees off backend (each gets a .git FILE pointer, not dir)
    for i in range(20):
        wt = os.path.join(proj_b, f"backend-wt{i:02d}")
        subprocess.run(["git", "-C", os.path.join(proj_b, "backend"), "worktree", "add", "-q",
                        "--detach", wt], env=genv,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # --- fixture (c) degenerate single repo --------------------------------------
    proj_c = os.path.join(sandbox, "proj_c")
    _mk_repo(proj_c, genv)

    app = Adw.Application(application_id="dev.smoke.arduis033")

    def on_activate(a):
        # (a) clean multi-repo
        os.chdir(proj_a)
        win = build_window(a)
        cs = win._chip_state
        members_ok = cs is not None and cs.members == ["backend", "frontend", "keycloak"]
        chips_ok = len(win._chip_btn_by_repo) == 3
        default_all = cs is not None and cs.default_selection() == cs.members
        check("a_members_3_sorted", members_ok)
        check("a_chip_bar_renders_3", chips_ok)
        check("a_all_selected_by_default", default_all)
        cs.toggle("frontend"); win._restyle_chips()
        toggle_ok = "frontend" not in cs.default_selection() and "backend" in cs.default_selection()
        check("a_toggle_off_updates_default", toggle_ok)
        cs.reflect_active({"backend"})
        reflect_ok = cs.is_active("backend") and not cs.is_active("frontend")
        cs.reflect_active(None)
        clear_ok = not cs.is_active("backend")
        check("a_reflect_active_then_clear", reflect_ok and clear_ok)

        # (b) Livon-Saude shape — THE user's complaint: 2 chips not 22
        os.chdir(proj_b)
        win_b = build_window(a)
        csb = win_b._chip_state
        b_members = csb is not None and csb.members == ["backend", "frontend"]
        b_chips = len(win_b._chip_btn_by_repo) == 2
        b_detect = detect_member_repos(proj_b) == ["backend", "frontend"]
        check("b_two_repos_not_twentytwo", b_members and b_detect)
        check("b_chip_bar_renders_2_no_overflow", b_chips)

        # (c) degenerate single repo
        os.chdir(proj_c)
        win_c = build_window(a)
        csc = win_c._chip_state
        c_one = csc is not None and len(csc.members) == 1 and len(win_c._chip_btn_by_repo) == 1
        check("c_degenerate_one_chip", c_one)

        a.quit()

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
