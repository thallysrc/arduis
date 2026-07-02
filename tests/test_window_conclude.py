"""Regression lock for the DESTRUCTIVE 'Concluir workspace' teardown (Phase 8, D-04).

window.py needs no display to IMPORT (gi import is module-level; widget construction
is what needs a display). So we build a bare window via ``__new__`` (skip __init__/GTK),
stub the GTK-touching + channel helpers to RECORD their call order, and monkeypatch
``run_git_async`` to invoke its callback synchronously with canned git output. That lets
us assert, without a display:

  - the FIXED order: kill agents → clear state → container down → porcelain gate →
    remove → prune → clean folder → finalize;
  - a DIRTY repo REFUSES the whole conclude — ZERO worktree-remove argv issued;
  - NO ``git worktree remove`` argv ever contains ``--force``/``-f`` (the cardinal-sin
    guard, D-04) — on the clean path.
"""
import arduis.window as W
from arduis.session import Workspace, RepoCheckout, SessionState


def _bare_window(monkeypatch, repos, porcelain_out):
    """A window stub whose conclude chain records calls; run_git_async is synchronous."""
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    calls = []
    git_argvs = []

    win._runner = object()
    win._store = type("S", (), {"removed": [], "remove": lambda self, sid: self.removed.append(sid)})()

    # record-only stubs for the GTK / channel helpers the chain calls
    for name in ("_teardown_session_terminals", "_clear_workspace_state_files",
                 "_container_down", "_conclude_refuse_dialog",
                 "_conclude_clean_workspace_folder", "_conclude_finalize", "_toast"):
        monkeypatch.setattr(win, name,
                            (lambda n: (lambda *a, **k: calls.append(n)))(name))
    monkeypatch.setattr(win, "_member_repo_path", lambda repo_name: f"/src/{repo_name}")

    # synchronous run_git_async: record argv, classify status vs remove/prune, invoke cb
    def fake_run(argv, on_done, runner=None, cwd=None):
        git_argvs.append(argv)
        if "status" in argv:
            on_done(0, porcelain_out, "")
        else:  # worktree remove / prune
            calls.append("git:" + (argv[argv.index("worktree") + 1] if "worktree" in argv else "?"))
            on_done(0, "", "")
    monkeypatch.setattr(W, "run_git_async", fake_run)

    workspace = Workspace(workspace_id="feat", branch="feat", workspace_dir="/workspaces/feat",
                repos=repos, state=SessionState.ACTIVE)
    return win, workspace, calls, git_argvs


def test_clean_conclude_follows_fixed_order_and_never_forces(monkeypatch):
    repos = [RepoCheckout(repo_name="backend", worktree_dir="/workspaces/feat/backend", branch="feat"),
             RepoCheckout(repo_name="frontend", worktree_dir="/workspaces/feat/frontend", branch="feat")]
    win, workspace, calls, git_argvs = _bare_window(monkeypatch, repos, porcelain_out="")  # clean

    win._conclude_workspace(workspace)

    # order: agents killed + state cleared + container down BEFORE any git
    assert calls[0] == "_teardown_session_terminals"
    assert calls[1] == "_clear_workspace_state_files"
    assert calls[2] == "_container_down"
    # both repos removed then pruned, then folder cleaned + finalized
    assert "git:remove" in calls and "git:prune" in calls
    assert calls.index("git:remove") < calls.index("git:prune")
    assert "_conclude_clean_workspace_folder" in calls and "_conclude_finalize" in calls
    assert calls.index("git:prune") < calls.index("_conclude_finalize")
    # the cardinal-sin guard: NO worktree-remove argv carries a force flag
    for argv in git_argvs:
        if "remove" in argv:
            assert "--force" not in argv and "-f" not in argv
    # refusal NOT triggered on a clean tree
    assert "_conclude_refuse_dialog" not in calls


def test_dirty_repo_refuses_whole_conclude_no_remove(monkeypatch):
    repos = [RepoCheckout(repo_name="backend", worktree_dir="/workspaces/feat/backend", branch="feat"),
             RepoCheckout(repo_name="frontend", worktree_dir="/workspaces/feat/frontend", branch="feat")]
    win, workspace, calls, git_argvs = _bare_window(monkeypatch, repos, porcelain_out=" M app.py")  # dirty

    win._conclude_workspace(workspace)

    # agents/container channels still ran (a)(b), but the gate REFUSED before any remove
    assert "_conclude_refuse_dialog" in calls
    assert "git:remove" not in calls  # ZERO worktree-remove issued (all-or-nothing)
    assert not any("remove" in argv for argv in git_argvs)
    assert win._store.removed == []  # workspace NOT dropped — nothing destroyed


def test_no_repos_skips_straight_to_finalize(monkeypatch):
    win, workspace, calls, git_argvs = _bare_window(monkeypatch, repos=[], porcelain_out="")
    win._conclude_workspace(workspace)
    assert "_conclude_finalize" in calls
    assert not any("remove" in argv for argv in git_argvs)
