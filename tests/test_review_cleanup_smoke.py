"""Phase-08 acceptance smoke — REAL git behavior of the conclude primitives + D-10 + gh degrade.

Pure pytest (no GTK/broadway): runs arduis.review's actual argv builders against a REAL git repo
+ worktree under a sandbox $HOME, proving the safety facts the conclude depends on:
  - a CLEAN worktree is removed by `git worktree remove` (NO --force); source repo + branch survive;
  - a DIRTY worktree REFUSES removal without --force (git's own guard — the safety holds even if the
    app gate were bypassed); the source is never touched;
  - parse_porcelain_clean classifies real `git status --porcelain` output;
  - D-10: an islink-guarded unlink removes a symlink but NEVER its target;
  - gh degrade: with gh absent from PATH, gh_available() is False and degrade_message is graceful.
Real `gh pr create` is NEVER invoked (host-only live UAT).
"""
import os
import subprocess

import pytest

from arduis import review, gh


def _run(argv, cwd=None, env=None):
    return subprocess.run(argv, cwd=cwd, env=env, capture_output=True, text=True)


@pytest.fixture
def repo_and_worktree(tmp_path, monkeypatch):
    home = tmp_path / "home"; home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    genv = {**os.environ, "HOME": str(home), "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@e",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@e"}
    src = tmp_path / "proj" / "backend"; src.mkdir(parents=True)
    _run(["git", "init", "-q", "-b", "main"], cwd=str(src), env=genv)
    (src / "f.txt").write_text("base\n")
    _run(["git", "add", "."], cwd=str(src), env=genv)
    _run(["git", "commit", "-q", "-m", "init"], cwd=str(src), env=genv)
    wt = tmp_path / "proj-workspaces" / "feat" / "backend"
    wt.parent.mkdir(parents=True)
    _run(["git", "worktree", "add", "-q", "-b", "feat", str(wt)], cwd=str(src), env=genv)
    return str(src), str(wt), genv


def test_clean_worktree_removed_source_and_branch_survive(repo_and_worktree):
    src, wt, genv = repo_and_worktree
    # clean tree → porcelain empty → parser says clean
    st = _run(review.argv_status_porcelain(wt), cwd=wt, env=genv)
    assert review.parse_porcelain_clean(st.stdout) is True
    # remove without --force succeeds
    rm = _run(review.argv_worktree_remove(src, wt), env=genv)
    assert rm.returncode == 0
    assert not os.path.exists(wt)
    # D-10: source repo + the 'feat' branch survive
    assert os.path.exists(os.path.join(src, ".git"))
    br = _run(["git", "-C", src, "branch", "--list", "feat"], env=genv)
    assert "feat" in br.stdout
    # prune is clean
    assert _run(review.argv_worktree_prune(src), env=genv).returncode == 0


def test_dirty_worktree_refuses_remove_without_force(repo_and_worktree):
    src, wt, genv = repo_and_worktree
    (os.path.join(wt, "f.txt"))  # make it dirty
    with open(os.path.join(wt, "f.txt"), "w") as fh:
        fh.write("uncommitted change\n")
    st = _run(review.argv_status_porcelain(wt), cwd=wt, env=genv)
    assert review.parse_porcelain_clean(st.stdout) is False  # gate would REFUSE
    # even if the gate were bypassed, git itself refuses to remove a dirty worktree w/o --force
    rm = _run(review.argv_worktree_remove(src, wt), env=genv)
    assert rm.returncode != 0
    assert os.path.exists(wt)  # uncommitted work preserved
    assert "--force" not in review.argv_worktree_remove(src, wt)  # never forces


def test_d10_islink_unlink_keeps_target(tmp_path):
    target = tmp_path / "docker-compose.yml"; target.write_text("services: {}\n")
    link = tmp_path / "workspace" / "docker-compose.yml"; link.parent.mkdir()
    os.symlink(os.path.relpath(target, link.parent), link)
    # the conclude folder-clean pattern: unlink only if islink
    assert os.path.islink(link)
    os.unlink(link)
    assert not os.path.exists(link)
    assert target.exists() and target.read_text() == "services: {}\n"  # target survives (D-10)


def test_gh_absent_degrades_gracefully(tmp_path, monkeypatch):
    # empty PATH → gh not found → caller shows GH_ABSENT_MSG, never calls gh
    monkeypatch.setenv("PATH", str(tmp_path / "nope"))
    assert gh.gh_available() is False
    assert gh.GH_ABSENT_MSG and isinstance(gh.GH_ABSENT_MSG, str)
    # exit-4 = needs auth → static unauth degrade; other rc → None (caller's own fallback)
    assert gh.degrade_message(gh.GH_EXIT_NEEDS_AUTH) == gh.GH_UNAUTH_MSG
    assert gh.degrade_message(1) is None
