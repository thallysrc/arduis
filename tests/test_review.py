"""Unit coverage for the GTK-free git read-introspection layer (Phase 8).

Pins REVIEW-01 (diff argv), REVIEW-03 (the dirty-tree gate + the NEVER-force
worktree remove/prune — the load-bearing safety of "Concluir", criterion 4 /
D-04), and GIT-01 (branch + ahead/behind reads). Pure import of ``arduis.review``:
no ``gi``, no I/O, no git invocation. The window layer (Waves 2/3) calls these
argv via ``run_git_async`` and reacts to the parsed result.
"""
from __future__ import annotations

from pathlib import Path

from arduis import review


# --- REVIEW-01: read-only diff argv ------------------------------------------

def test_argv_diff_is_verified_listform():
    assert review.argv_diff("/wt") == ["git", "-C", "/wt", "--no-pager", "diff"]


def test_argv_diff_stat_is_verified_listform():
    assert review.argv_diff_stat("/wt") == [
        "git", "-C", "/wt", "--no-pager", "diff", "--stat",
    ]


def test_argv_diff_repo_is_a_discrete_element():
    # the repo path is a discrete argv element, never joined into a string
    # (T-08-01: no shell, no flag injection surface)
    argv = review.argv_diff("/tasks/feat/-weird dir")
    assert "/tasks/feat/-weird dir" in argv
    assert argv[2] == "/tasks/feat/-weird dir"


# --- REVIEW-03: porcelain status argv + the dirty-tree clean gate ------------

def test_argv_status_porcelain_is_verified_listform():
    assert review.argv_status_porcelain("/wt") == [
        "git", "-C", "/wt", "status", "--porcelain",
    ]


def test_parse_porcelain_clean_empty_is_clean():
    assert review.parse_porcelain_clean("") is True


def test_parse_porcelain_clean_whitespace_only_is_clean():
    assert review.parse_porcelain_clean("\n") is True
    assert review.parse_porcelain_clean("   \n  \n") is True


def test_parse_porcelain_clean_untracked_is_dirty():
    assert review.parse_porcelain_clean("?? new.txt\n") is False


def test_parse_porcelain_clean_modified_is_dirty():
    assert review.parse_porcelain_clean(" M edited\n") is False


def test_parse_porcelain_clean_staged_is_dirty():
    assert review.parse_porcelain_clean("A  staged\n") is False


# --- REVIEW-03: worktree remove/prune — the NEVER-force safety ---------------

def test_argv_worktree_remove_is_verified_listform():
    assert review.argv_worktree_remove(
        "/src/backend", "/tasks/feat/backend"
    ) == ["git", "-C", "/src/backend", "worktree", "remove", "/tasks/feat/backend"]


def test_argv_worktree_remove_never_emits_force():
    # THE CARDINAL-SIN GUARD (T-08-02 / criterion 4 / D-04 step c-d):
    # force-deleting uncommitted work is the one thing this phase must prevent.
    # The non-force refusal IS the feature — assert no --force/-f for any input,
    # including a worktree dir whose leaf starts with a dash.
    cases = [
        ("/src/backend", "/tasks/feat/backend"),
        ("/repo", "/repo-tasks/x/repo"),
        ("/a", "-rf"),
        ("/b", "/tasks/--force/b"),
        ("/c", "/tasks/-f/c"),
    ]
    for source, wt in cases:
        argv = review.argv_worktree_remove(source, wt)
        assert "--force" not in argv, f"--force leaked for {(source, wt)}"
        assert "-f" not in argv, f"-f leaked for {(source, wt)}"
        # the worktree dir is still a discrete element (no flag injection)
        assert argv[-1] == wt


def test_argv_worktree_prune_is_verified_listform():
    assert review.argv_worktree_prune("/src/backend") == [
        "git", "-C", "/src/backend", "worktree", "prune",
    ]


# --- GIT-01: branch + ahead/behind reads -------------------------------------

def test_argv_current_branch_is_verified_listform():
    assert review.argv_current_branch("/wt") == [
        "git", "-C", "/wt", "rev-parse", "--abbrev-ref", "HEAD",
    ]


def test_argv_ahead_behind_is_verified_listform():
    assert review.argv_ahead_behind("/wt", "feat/x") == [
        "git", "-C", "/wt", "rev-list", "--left-right", "--count",
        "feat/x...feat/x@{u}",
    ]


def test_parse_ahead_behind_two_counts():
    assert review.parse_ahead_behind("3\t2") == (3, 2)


def test_parse_ahead_behind_zeros():
    assert review.parse_ahead_behind("0\t0") == (0, 0)


def test_parse_ahead_behind_empty_is_zero_zero():
    assert review.parse_ahead_behind("") == (0, 0)


def test_parse_ahead_behind_garbage_is_zero_zero():
    assert review.parse_ahead_behind("garbage") == (0, 0)


def test_parse_ahead_behind_single_token_is_zero_zero():
    assert review.parse_ahead_behind("5") == (0, 0)


def test_parse_ahead_behind_never_raises_on_junk():
    # a repo with no upstream makes `rev-list ...@{u}` fail with empty/garbage
    # stdout; the parser must degrade to (0,0), never throw.
    for junk in ("\n", "  ", "a\tb", "1\t2\t3", "-1\t2", "1.5\t2"):
        assert review.parse_ahead_behind(junk) == (0, 0)


# --- the GTK-free domain discipline ------------------------------------------

def test_review_module_is_gtk_free():
    source = Path(review.__file__).read_text(encoding="utf-8")
    assert "import gi" not in source
    assert "from gi" not in source
