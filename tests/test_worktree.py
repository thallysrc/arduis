"""Tests for the pure git-argv builders + parsers (WT-01/WT-02/D-07).

GTK-free domain contract: list-form argv (never shell strings, T-02-01),
default-branch origin->local fallback (D-04), sibling-dir sanitization that
blocks path traversal (D-05/T-02-02), porcelain already-checked-out detection
(D-07), and new-vs-existing inference (WT-01). Never emits ``--force``.
"""
import os

from arduis import worktree


def test_default_branch_fallback():
    # origin argv + parse strips the refs/remotes/origin/ prefix
    assert worktree.argv_default_branch_via_origin("/r") == [
        "git", "-C", "/r", "symbolic-ref", "refs/remotes/origin/HEAD"
    ]
    assert worktree.argv_default_branch_local("/r") == [
        "git", "-C", "/r", "symbolic-ref", "--short", "HEAD"
    ]
    assert worktree.parse_default_branch("refs/remotes/origin/main\n") == "main"
    # local fallback output is already a bare branch name
    assert worktree.parse_default_branch("master\n") == "master"


def test_remote_base_and_fetch():
    # 2026-07-04: new branches are born from the REMOTE tip — the base is the
    # remote-tracking ref, refreshed by a best-effort fetch beforehand.
    assert worktree.parse_remote_base("refs/remotes/origin/main\n") == "origin/main"
    assert worktree.parse_remote_base("refs/remotes/origin/master\n") == "origin/master"
    assert worktree.argv_fetch_origin("/r") == ["git", "-C", "/r", "fetch", "origin"]


def test_repo_has_commit_argv():
    # born-HEAD guard: quiet rev-parse --verify so an empty repo is caught
    # before `worktree add` fails with the cryptic "invalid reference: HEAD".
    assert worktree.argv_repo_has_commit("/r") == [
        "git", "-C", "/r", "rev-parse", "--verify", "-q", "HEAD"
    ]
    # no shell string, branch/refs stay discrete argv elements (T-02-01)
    assert "--force" not in worktree.argv_repo_has_commit("/r")


def test_add_argv():
    # NEW branch off the detected base; --no-track so a remote-tracking base
    # (origin/<default>) never becomes the new branch's upstream
    assert worktree.argv_worktree_add_new("/r", "feat", "/d", "origin/main") == [
        "git", "-C", "/r", "worktree", "add", "--no-track", "-b", "feat",
        "/d", "origin/main",
    ]
    # EXISTING branch (checks it out)
    assert worktree.argv_worktree_add_existing("/r", "/d", "feat") == [
        "git", "-C", "/r", "worktree", "add", "/d", "feat"
    ]
    # D-07 / T-02-03: --force is NEVER emitted
    assert "--force" not in worktree.argv_worktree_add_new("/r", "feat", "/d", "main")
    assert "--force" not in worktree.argv_worktree_add_existing("/r", "/d", "feat")


def test_sanitize_dir():
    # slash -> single dash; result is a safe flat dir component
    assert worktree.sanitize_branch_for_dir("feature/foo") == "feature-foo"
    # path traversal pieces can never survive
    s = worktree.sanitize_branch_for_dir("../../etc/passwd")
    assert ".." not in s
    assert os.sep not in s
    assert s not in ("", ".", "..")
    # the sibling dir is computed from repo_root's parent + sanitized leaf
    d = worktree.worktree_dir_for("/home/u/repo", "feature/foo")
    assert d == os.path.join("/home/u", "repo-feature-foo")
    # a traversal branch never escapes the parent dir
    d2 = worktree.worktree_dir_for("/home/u/repo", "../../etc")
    assert os.path.dirname(d2) == "/home/u"
    assert ".." not in os.path.basename(d2)


def test_infer_new_vs_existing():
    assert worktree.argv_list_local_branches("/r") == [
        "git", "-C", "/r", "for-each-ref", "--format=%(refname:short)", "refs/heads"
    ]
    assert worktree.parse_local_branches("master\nfeat\n") == ["master", "feat"]
    # tolerate the `* current` marker form too
    assert worktree.parse_local_branches("  master\n* feat\n") == ["master", "feat"]
    assert worktree.infer_new_vs_existing("feat", ["master", "feat"]) == "existing"
    assert worktree.infer_new_vs_existing("new", ["master", "feat"]) == "new"


def test_detect_checked_out():
    assert worktree.argv_worktree_list_porcelain("/r") == [
        "git", "-C", "/r", "worktree", "list", "--porcelain"
    ]
    porcelain = (
        "worktree /home/u/repo\n"
        "branch refs/heads/master\n"
        "\n"
        "worktree /home/u/repo-feat\n"
        "branch refs/heads/feat\n"
        "\n"
        "worktree /home/u/repo-detached\n"
        "detached\n"
    )
    parsed = worktree.parse_worktrees(porcelain)
    assert parsed[0] == {"path": "/home/u/repo", "branch": "master"}
    assert parsed[1] == {"path": "/home/u/repo-feat", "branch": "feat"}
    assert parsed[2]["branch"] is None  # detached
    # branch_checked_out_path returns the matching record's path, else None
    assert worktree.branch_checked_out_path("feat", parsed) == "/home/u/repo-feat"
    assert worktree.branch_checked_out_path("absent", parsed) is None
