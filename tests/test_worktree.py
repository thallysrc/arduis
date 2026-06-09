"""Wave-0 RED contract for the GTK-free git-worktree domain layer.

Pins the pure (stdlib-only) API of `src/arduis/worktree.py`, which Plan 01
implements. Until then this file is RED (ModuleNotFoundError at import).

Decision IDs covered:
- D-04: default-branch fallback chain (never hardcode "main")
- D-05: sibling worktree dir + branch-name sanitization (path-traversal guard)
- D-06: parse local branches + infer new-vs-existing
- D-07: never --force; porcelain pre-check for already-checked-out branches

Threats T-02-01 (argv built as lists, no --force) and T-02-02 (sanitized dir
cannot escape the parent) are encoded here and mitigated in Plan 01.
Verified argv/porcelain literals come from 02-RESEARCH.md § Code Examples.
"""
from arduis.worktree import (
    argv_default_branch_via_origin,
    argv_default_branch_local,
    parse_default_branch,
    argv_worktree_add_new,
    argv_worktree_add_existing,
    sanitize_branch_for_dir,
    worktree_dir_for,
    parse_local_branches,
    infer_new_vs_existing,
    argv_worktree_list_porcelain,
    parse_worktrees,
    branch_checked_out_path,
    argv_list_local_branches,
)


def test_default_branch_fallback():
    # D-04: origin chain, then local fallback; never hardcode "main".
    assert parse_default_branch("refs/remotes/origin/main\n") == "main"
    assert argv_default_branch_via_origin("/r") == [
        "git", "-C", "/r", "symbolic-ref", "refs/remotes/origin/HEAD",
    ]
    assert argv_default_branch_local("/r") == [
        "git", "-C", "/r", "symbolic-ref", "--short", "HEAD",
    ]


def test_add_argv():
    # D-07: worktree add argv, new vs existing; NEVER --force.
    new = argv_worktree_add_new("/r", "feat", "/p/r-feat", "master")
    assert new == ["git", "-C", "/r", "worktree", "add", "-b", "feat", "/p/r-feat", "master"]

    existing = argv_worktree_add_existing("/r", "/p/r-feat", "feat")
    assert existing == ["git", "-C", "/r", "worktree", "add", "/p/r-feat", "feat"]

    assert "--force" not in new
    assert "--force" not in existing


def test_sanitize_dir():
    # D-05: sanitize branch to a flat, safe sibling-dir leaf (path-traversal guard).
    assert sanitize_branch_for_dir("feature/foo") == "feature-foo"
    assert " " not in sanitize_branch_for_dir("a b")

    # Sibling dir: ../<repo>-<sanitized-branch>
    assert worktree_dir_for("/home/u/arduis", "feature/x") == "/home/u/arduis-feature-x"

    # T-02-02: a "../escape" or "/abs" branch must not produce a basename that
    # escapes the repo's parent dir.
    assert ".." not in sanitize_branch_for_dir("../escape")
    assert ".." not in sanitize_branch_for_dir("/abs")
    import os.path
    assert ".." not in os.path.basename(worktree_dir_for("/home/u/arduis", "../escape"))
    assert ".." not in os.path.basename(worktree_dir_for("/home/u/arduis", "/abs"))


def test_detect_checked_out():
    # D-07: parse `git worktree list --porcelain`; detect already-checked-out branch.
    porcelain = (
        "worktree /home/u/arduis\n"
        "branch refs/heads/master\n"
        "\n"
        "worktree /home/u/arduis-feat\n"
        "branch refs/heads/feat\n"
        "locked\n"
    )
    parsed = parse_worktrees(porcelain)
    assert parsed[0]["path"] == "/home/u/arduis"
    assert parsed[0]["branch"] == "master"
    assert parsed[1]["path"] == "/home/u/arduis-feat"
    assert parsed[1]["branch"] == "feat"
    assert parsed[1]["locked"] is True

    # A detached record yields branch None.
    detached = parse_worktrees("worktree /home/u/d\ndetached\n")
    assert detached[0]["branch"] is None

    assert branch_checked_out_path("feat", parsed) == "/home/u/arduis-feat"
    assert branch_checked_out_path("absent", parsed) is None

    # Builder is a pure argv list (no shell string).
    assert argv_worktree_list_porcelain("/r") == [
        "git", "-C", "/r", "worktree", "list", "--porcelain",
    ]


def test_infer_new_vs_existing():
    # D-06: infer new vs existing from the parsed local-branch list.
    assert infer_new_vs_existing("feat", ["master", "feat"]) == "existing"
    assert infer_new_vs_existing("brand-new", ["master"]) == "new"

    branches = parse_local_branches("  master\n* feat\n")
    assert "master" in branches
    assert "feat" in branches
    assert "* feat" not in branches  # leading "* "/spaces stripped

    assert isinstance(argv_list_local_branches("/r"), list)
