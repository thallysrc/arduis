"""Regression lock for the DESTRUCTIVE 'Concluir workspace' teardown (Phase 8, D-04).

window.py needs no display to IMPORT (gi import is module-level; widget construction
is what needs a display). So we build a bare window via ``__new__`` (skip __init__/GTK),
stub the GTK-touching + channel helpers to RECORD their call order, and monkeypatch
``run_git_async`` to invoke its callback synchronously with canned git output. That lets
us assert, without a display:

  - the FIXED order: porcelain gate FIRST (read-only) → unmerged-commits gate (still
    read-only) → kill agents → clear state → container down → remove → prune → clean
    folder → finalize;
  - a DIRTY repo REFUSES the whole conclude BEFORE anything is touched — agents alive,
    containers up, ZERO worktree-remove argv issued (the frozen-terminal regression:
    killing agents before the gate left refused workspaces with dead PTYs);
  - commits on the workspace branch MISSING from the default branch surface the
    warning dialog BEFORE any destructive channel — cancelling leaves the workspace
    fully alive; only the explicit confirmation (``_conclude_proceed``) tears down;
  - a remove failure AFTER the gate (tree dirtied in the race window) hibernates the
    workspace instead of leaving it zombie with dead terminals;
  - NO ``git worktree remove`` argv ever contains ``--force``/``-f`` (the cardinal-sin
    guard, D-04) — on the clean path.
"""
import arduis.window as W
from arduis.session import Workspace, RepoCheckout, SessionState


def _bare_window(monkeypatch, repos, porcelain_out, remove_rc=0, log_out=""):
    """A window stub whose conclude chain records calls; run_git_async is synchronous."""
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    calls = []
    git_argvs = []

    win._runner = object()
    win._store = type("S", (), {"removed": [], "remove": lambda self, sid: self.removed.append(sid)})()

    # record-only stubs for the GTK / channel helpers the chain calls
    for name in ("_teardown_session_terminals", "_clear_workspace_state_files",
                 "_container_down", "_conclude_refuse_dialog",
                 "_conclude_clean_workspace_folder", "_conclude_finalize",
                 "_hibernate_workspace", "_toast"):
        monkeypatch.setattr(win, name,
                            (lambda n: (lambda *a, **k: calls.append(n)))(name))
    monkeypatch.setattr(win, "_member_repo_path", lambda repo_name: f"/src/{repo_name}")
    # the unmerged-commits warning dialog: record the call AND capture findings
    win._unmerged_findings = []
    monkeypatch.setattr(
        win, "_conclude_unmerged_dialog",
        lambda ws, findings: (calls.append("_conclude_unmerged_dialog"),
                              win._unmerged_findings.append(findings)))

    # synchronous run_git_async: record argv, classify by command, invoke cb
    def fake_run(argv, on_done, runner=None, cwd=None):
        git_argvs.append(argv)
        if "status" in argv:
            calls.append("git:status")
            on_done(0, porcelain_out, "")
        elif "fetch" in argv:  # best-effort refresh of origin/<default> (2026-07-04)
            calls.append("git:fetch")
            on_done(0, "", "")
        elif "symbolic-ref" in argv:  # default-branch detection (origin path answers)
            calls.append("git:base")
            on_done(0, "refs/remotes/origin/master\n", "")
        elif "log" in argv:  # unmerged-commits probe (master..HEAD)
            calls.append("git:log")
            on_done(0, log_out, "")
        elif "worktree" in argv and "remove" in argv:
            calls.append("git:remove")
            on_done(remove_rc, "", "boom" if remove_rc else "")
        else:  # worktree prune
            calls.append("git:" + (argv[argv.index("worktree") + 1] if "worktree" in argv else "?"))
            on_done(0, "", "")
    monkeypatch.setattr(W, "run_git_async", fake_run)

    workspace = Workspace(workspace_id="feat", branch="feat", workspace_dir="/workspaces/feat",
                repos=repos, state=SessionState.ACTIVE)
    return win, workspace, calls, git_argvs


def _two_repos():
    return [RepoCheckout(repo_name="backend", worktree_dir="/workspaces/feat/backend", branch="feat"),
            RepoCheckout(repo_name="frontend", worktree_dir="/workspaces/feat/frontend", branch="feat")]


def test_clean_conclude_gate_first_then_fixed_order_never_forces(monkeypatch):
    win, workspace, calls, git_argvs = _bare_window(monkeypatch, _two_repos(), porcelain_out="")  # clean

    win._conclude_workspace(workspace)

    # gates FIRST: only READ-ONLY calls (porcelain + fetch + base detection +
    # unmerged log) happen BEFORE any destructive channel
    assert calls[0] == "git:status" and calls[1] == "git:status"
    gate_end = calls.index("_teardown_session_terminals")
    assert set(calls[:gate_end]) == {"git:status", "git:fetch", "git:base", "git:log"}
    # then: agents killed + state cleared + container down BEFORE any remove
    assert calls.index("_teardown_session_terminals") < calls.index("git:remove")
    assert calls.index("_clear_workspace_state_files") < calls.index("git:remove")
    assert calls.index("_container_down") < calls.index("git:remove")
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


def test_dirty_repo_refuses_before_touching_anything(monkeypatch):
    """The frozen-terminal regression: a refused conclude must leave the workspace
    fully alive — agents NOT killed, containers NOT downed, nothing removed."""
    win, workspace, calls, git_argvs = _bare_window(monkeypatch, _two_repos(), porcelain_out=" M app.py")  # dirty

    win._conclude_workspace(workspace)

    assert "_conclude_refuse_dialog" in calls
    # NOTHING destructive ran: terminals alive, containers up, state files intact
    assert "_teardown_session_terminals" not in calls
    assert "_container_down" not in calls
    assert "_clear_workspace_state_files" not in calls
    assert "git:remove" not in calls  # ZERO worktree-remove issued (all-or-nothing)
    assert not any("remove" in argv for argv in git_argvs)
    assert win._store.removed == []  # workspace NOT dropped — nothing destroyed
    assert "git:log" not in calls  # dirty refusal short-circuits the unmerged gate too


def test_unmerged_commits_warn_and_block_until_confirmation(monkeypatch):
    """Commits on the workspace branch missing from master must surface the
    warning dialog BEFORE any destructive channel — the user decides; while the
    dialog waits, the workspace is fully alive."""
    win, workspace, calls, git_argvs = _bare_window(
        monkeypatch, _two_repos(), porcelain_out="",  # clean tree, gate passes
        log_out="abc1234 feat: nova coisa\ndef5678 fix: ajuste\n")

    win._conclude_workspace(workspace)

    assert "_conclude_unmerged_dialog" in calls
    # NOTHING destructive ran while waiting for the user's answer
    assert "_teardown_session_terminals" not in calls
    assert "_container_down" not in calls
    assert "_clear_workspace_state_files" not in calls
    assert "git:remove" not in calls
    assert not any("remove" in argv for argv in git_argvs)
    assert win._store.removed == []
    # the dialog receives the commits per repo (both repos, sorted, verbatim lines)
    (findings,) = win._unmerged_findings
    assert [name for name, _ in findings] == ["backend", "frontend"]
    assert findings[0][1] == ["abc1234 feat: nova coisa", "def5678 fix: ajuste"]


def test_unmerged_confirmation_proceeds_teardown_then_remove(monkeypatch):
    """The dialog's 'Concluir mesmo assim' lands on _conclude_proceed, which must
    run the SAME fixed order as the clean path: teardown → remove → prune → finalize."""
    win, workspace, calls, git_argvs = _bare_window(
        monkeypatch, _two_repos(), porcelain_out="", log_out="abc1234 feat: x\n")
    win._conclude_workspace(workspace)
    assert "_conclude_unmerged_dialog" in calls
    calls.clear()

    win._conclude_proceed(workspace)  # what the "ok" response invokes

    assert calls.index("_teardown_session_terminals") < calls.index("git:remove")
    assert calls.index("_container_down") < calls.index("git:remove")
    assert calls.index("git:remove") < calls.index("git:prune")
    assert "_conclude_finalize" in calls
    for argv in git_argvs:
        if "remove" in argv:
            assert "--force" not in argv and "-f" not in argv


def test_merged_branch_concludes_without_extra_dialog(monkeypatch):
    """A branch fully merged into master (empty log) must NOT show the warning —
    conclude proceeds straight through (no extra click on the happy path)."""
    win, workspace, calls, _ = _bare_window(
        monkeypatch, _two_repos(), porcelain_out="", log_out="")

    win._conclude_workspace(workspace)

    assert "_conclude_unmerged_dialog" not in calls
    assert "_conclude_finalize" in calls


def test_remove_failure_hibernates_instead_of_zombie(monkeypatch):
    """If git refuses the remove AFTER the gate passed (race window), the terminals
    are already dead — the workspace must become HIBERNATED (resumable), never a
    zombie row with dead PTYs."""
    win, workspace, calls, git_argvs = _bare_window(
        monkeypatch, _two_repos(), porcelain_out="", remove_rc=1)

    win._conclude_workspace(workspace)

    assert "_toast" in calls  # failure surfaced
    assert "_hibernate_workspace" in calls  # coherent resumable state
    assert "_conclude_finalize" not in calls  # NOT finalized as if it succeeded
    assert win._store.removed == []


def test_no_repos_still_tears_down_then_finalizes(monkeypatch):
    win, workspace, calls, git_argvs = _bare_window(monkeypatch, repos=[], porcelain_out="")
    win._conclude_workspace(workspace)
    # even with no worktrees the workspace's terminals/containers must be torn down
    assert "_teardown_session_terminals" in calls
    assert "_container_down" in calls
    assert "_conclude_finalize" in calls
    assert calls.index("_teardown_session_terminals") < calls.index("_conclude_finalize")
    assert not any("remove" in argv for argv in git_argvs)
