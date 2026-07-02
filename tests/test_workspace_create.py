"""Tests for the pure per-repo worktree-add resolution (D-13 / OQ2 / criterion 5).

``workspace_layout.resolve_repo_add`` is the GTK-free decision Plan 02's window.py
chain calls once per member repo, after running the porcelain pre-check + local
branch list async. It returns:
  ("new", argv)      — branch absent → create a new branch off base
  ("existing", argv) — branch present, not checked out elsewhere → check it out
  ("abort", reason)  — branch checked out elsewhere → NEVER --force (D-13)

Per-repo independence (OQ2 best-effort): the function is called once per repo and
yields independent results — no all-or-nothing coupling. The degenerate 1-repo
project resolves through the IDENTICAL path (criterion 5). T-03.2-03: no produced
argv ever contains ``--force``.
"""
import os
import shutil
import subprocess

import pytest

from arduis.workspace_layout import resolve_repo_add


def test_resolve_new():
    # branch absent from existing → ("new", worktree add -b ...).
    kind, argv = resolve_repo_add(
        "/r/backend", "feat", existing_branches=["master"],
        parsed_worktrees=[{"path": "/r/backend", "branch": "master"}],
        base="master", worktree_dir="/r-workspaces/feat/backend",
    )
    assert kind == "new"
    assert argv == [
        "git", "-C", "/r/backend", "worktree", "add", "-b", "feat",
        "/r-workspaces/feat/backend", "master",
    ]
    assert "--force" not in argv  # D-13 / T-03.2-03


def test_resolve_existing_reusable():
    # branch in existing, NOT in parsed worktrees → ("existing", worktree add ...).
    kind, argv = resolve_repo_add(
        "/r/backend", "feat", existing_branches=["master", "feat"],
        parsed_worktrees=[{"path": "/r/backend", "branch": "master"}],
        base="master", worktree_dir="/r-workspaces/feat/backend",
    )
    assert kind == "existing"
    assert argv == [
        "git", "-C", "/r/backend", "worktree", "add", "/r-workspaces/feat/backend", "feat",
    ]
    assert "--force" not in argv  # D-13 / T-03.2-03


def test_resolve_abort_on_ref_namespace_prefix_conflict_new_under_existing():
    # GAP 1: creating NEW branch `feat/MLK-1200-teste` while existing branch `feat`
    # exists is a git D/F ref-namespace conflict (refs/heads/feat is a file, so
    # refs/heads/feat/... cannot be created). Detect it in the pure function and
    # abort with a CLEAR pt-BR reason instead of leaking the raw git fatal.
    kind, reason = resolve_repo_add(
        "/r/backend", "feat/MLK-1200-teste", existing_branches=["master", "feat"],
        parsed_worktrees=[{"path": "/r/backend", "branch": "master"}],
        base="master", worktree_dir="/r-workspaces/feat-MLK-1200-teste/backend",
    )
    assert kind == "abort"
    assert "feat" in reason
    assert "feat/MLK-1200-teste" in reason
    assert "namespace" in reason.lower()
    assert isinstance(reason, str)
    assert "--force" not in reason


def test_resolve_abort_on_ref_namespace_prefix_conflict_existing_under_new():
    # The reverse D/F conflict: creating NEW branch `feat` while existing branch
    # `feat/pao` exists (refs/heads/feat/pao is a dir, so refs/heads/feat the file
    # cannot be created). Same clean abort.
    kind, reason = resolve_repo_add(
        "/r/backend", "feat", existing_branches=["master", "feat/pao"],
        parsed_worktrees=[{"path": "/r/backend", "branch": "master"}],
        base="master", worktree_dir="/r-workspaces/feat/backend",
    )
    assert kind == "abort"
    assert "feat/pao" in reason
    assert "feat" in reason
    assert "namespace" in reason.lower()


def test_resolve_no_false_namespace_conflict_on_shared_prefix_string():
    # `feature` and `feat` share a string prefix but NOT a ref-namespace prefix
    # (no `/` boundary) — must NOT be treated as a conflict.
    kind, argv = resolve_repo_add(
        "/r/backend", "feature", existing_branches=["master", "feat"],
        parsed_worktrees=[{"path": "/r/backend", "branch": "master"}],
        base="master", worktree_dir="/r-workspaces/feature/backend",
    )
    assert kind == "new"
    assert "--force" not in argv


def test_resolve_slash_branch_still_works_without_conflict():
    # The slash itself is FINE — a Jira-style `feat/MLK-1234` branch creates cleanly
    # when no conflicting `feat` (or `feat/...`) branch exists.
    kind, argv = resolve_repo_add(
        "/r/backend", "feat/MLK-1234-tarefa", existing_branches=["master"],
        parsed_worktrees=[{"path": "/r/backend", "branch": "master"}],
        base="master", worktree_dir="/r-workspaces/feat-MLK-1234-tarefa/backend",
    )
    assert kind == "new"
    assert argv[:6] == ["git", "-C", "/r/backend", "worktree", "add", "-b"]
    assert "feat/MLK-1234-tarefa" in argv
    assert "--force" not in argv


def test_resolve_abort_when_checked_out_elsewhere():
    # branch checked out at some path → ("abort", reason mentioning path); no argv.
    kind, reason = resolve_repo_add(
        "/r/backend", "feat", existing_branches=["master", "feat"],
        parsed_worktrees=[
            {"path": "/r/backend", "branch": "master"},
            {"path": "/r/backend-feat", "branch": "feat"},
        ],
        base="master", worktree_dir="/r-workspaces/feat/backend",
    )
    assert kind == "abort"
    assert "/r/backend-feat" in reason  # reason mentions the conflicting path
    # never produced a --force argv (it's a string reason, not an argv).
    assert isinstance(reason, str)
    assert "--force" not in reason


def test_per_repo_independence_best_effort():
    # OQ2: two repos, SAME branch. Repo A absent → new; repo B checked-out-elsewhere
    # → abort. Called once per repo, independent results (no coupling).
    kind_a, argv_a = resolve_repo_add(
        "/r/backend", "feat", existing_branches=["master"],
        parsed_worktrees=[{"path": "/r/backend", "branch": "master"}],
        base="master", worktree_dir="/r-workspaces/feat/backend",
    )
    kind_b, _b = resolve_repo_add(
        "/r/frontend", "feat", existing_branches=["master", "feat"],
        parsed_worktrees=[
            {"path": "/r/frontend", "branch": "master"},
            {"path": "/r/frontend-feat", "branch": "feat"},
        ],
        base="master", worktree_dir="/r-workspaces/feat/frontend",
    )
    assert kind_a == "new"
    assert kind_b == "abort"
    assert "--force" not in argv_a


def test_degenerate_single_repo_same_path():
    # Criterion 5: a 1-repo project resolves through the IDENTICAL resolve_repo_add
    # call — there is no len(repos) == 1 special branch.
    kind, argv = resolve_repo_add(
        "/solo", "feat", existing_branches=["master"],
        parsed_worktrees=[{"path": "/solo", "branch": "master"}],
        base="master", worktree_dir="/solo-workspaces/feat/solo",
    )
    assert kind == "new"
    assert argv[:6] == ["git", "-C", "/solo", "worktree", "add", "-b"]
    assert "--force" not in argv


def test_no_force_across_all_branches():
    # Belt-and-braces: every code path's argv (new/existing) is --force-free.
    for existing in (["master"], ["master", "feat"]):
        kind, argv = resolve_repo_add(
            "/r", "feat", existing_branches=existing,
            parsed_worktrees=[{"path": "/r", "branch": "master"}],
            base="master", worktree_dir="/r-workspaces/feat/r",
        )
        assert kind in ("new", "existing")
        assert "--force" not in argv


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_integration_real_worktree_add_refusal(tmp_path):
    # OPTIONAL integration: git really refuses to check out a branch already
    # checked out elsewhere — confirming resolve_repo_add's "abort" matches reality
    # WITHOUT us ever passing --force (git 2.43 on this host).
    from arduis import worktree

    repo = tmp_path / "repo"
    repo.mkdir()
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}

    def git(*args):
        return subprocess.run(["git", "-C", str(repo), *args], env=env,
                              capture_output=True, text=True)

    subprocess.run(["git", "init", "-b", "master", str(repo)], capture_output=True)
    (repo / "f").write_text("x")
    git("add", "f")
    git("commit", "-m", "init")
    git("branch", "feat")

    # check out feat at one worktree
    wt1 = tmp_path / "wt1"
    git("worktree", "add", str(wt1), "feat")

    # resolve_repo_add must say "abort" (feat is checked out at wt1).
    porcelain = git("worktree", "list", "--porcelain").stdout
    parsed = worktree.parse_worktrees(porcelain)
    kind, reason = resolve_repo_add(
        str(repo), "feat", existing_branches=["master", "feat"],
        parsed_worktrees=parsed, base="master",
        worktree_dir=str(tmp_path / "wt2"),
    )
    assert kind == "abort"
    assert str(wt1) in reason

    # and a real (force-free) add of an already-checked-out branch really fails.
    argv = worktree.argv_worktree_add_existing(str(repo), str(tmp_path / "wt2"), "feat")
    assert "--force" not in argv
    res = subprocess.run(argv, capture_output=True, text=True)
    assert res.returncode != 0  # git refuses without --force
