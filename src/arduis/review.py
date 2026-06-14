"""Pure git read-introspection argv builders + parsers for Phase 8 (GTK-free).

This is the domain layer for the Review + Cleanup loop: the read-only diff
(REVIEW-01), the dirty-tree clean gate + the worktree remove/prune teardown
(REVIEW-03, criterion 4 / D-04), and the branch + ahead/behind reads (GIT-01).
It mirrors ``worktree.py`` exactly: every function returns list-form argv with
the repo/dir/branch as a DISCRETE element, the parsers are tolerant and never
raise, and the module imports NO ``gi`` and touches no I/O. ``git_service.py``
(``run_git_async``) executes the argv these functions return; the window layer
(Waves 2/3) is pure glue that reacts to the parsed result.

LOAD-BEARING SAFETY (the cardinal sin this phase prevents):
- ``argv_worktree_remove`` NEVER emits ``--force``/``-f``. The dirty/locked
  refusal IS the feature (criterion 4 / D-04 step c-d / T-08-02): git's own
  refusal to remove a dirty worktree is what protects uncommitted work. A test
  pins the absence of the force flag for every input.
- ``parse_porcelain_clean`` is the gate the conclude orchestrator (Wave 3)
  consults per repo BEFORE any removal is attempted (REVIEW-03 criterion 4):
  empty porcelain => clean => safe to remove; any line => dirty => refuse.

Threats (STRIDE register, 08-PLAN):
- T-08-01 (tampering/EoP): every argv is a Python list with the repo/dir/branch
  a discrete element; nothing is joined into a shell string and there is no
  ``shell=True`` path. The Wave-2 caller routes argv through ``HostRunner``.
- T-08-02 (tampering / data loss): ``argv_worktree_remove`` structurally omits
  the force flag; the never-force guard test pins it.
"""
from __future__ import annotations


# --- REVIEW-01: read-only diff argv ------------------------------------------

def argv_diff(repo: str) -> list[str]:
    """``git -C <repo> --no-pager diff`` — the read-only full diff leaf."""
    return ["git", "-C", repo, "--no-pager", "diff"]


def argv_diff_stat(repo: str) -> list[str]:
    """``git -C <repo> --no-pager diff --stat`` — the diffstat summary."""
    return ["git", "-C", repo, "--no-pager", "diff", "--stat"]


# --- REVIEW-03: porcelain status argv + the dirty-tree clean gate ------------

def argv_status_porcelain(repo: str) -> list[str]:
    """``git -C <repo> status --porcelain`` — the dirty/clean probe."""
    return ["git", "-C", repo, "status", "--porcelain"]


def parse_porcelain_clean(stdout: str) -> bool:
    """``True`` iff the porcelain output is empty (clean => safe to remove).

    The load-bearing dirty-tree gate (REVIEW-03 criterion 4): empty/whitespace-
    only porcelain means a clean tree; ANY porcelain line (``?? new.txt``,
    `` M edited``, ``A  staged``) means dirty => the conclude orchestrator
    REFUSES to remove. [VERIFIED on host, git 2.43]
    """
    return stdout.strip() == ""


# --- REVIEW-03: worktree remove/prune — the NEVER-force safety ---------------

def argv_worktree_remove(source_repo: str, worktree_dir: str) -> list[str]:
    """``git -C <source_repo> worktree remove <worktree_dir>`` — NEVER ``--force``.

    The absence of the force flag is the safety: git refuses to remove a worktree
    with uncommitted changes, which is exactly the protection we want
    (criterion 4 / D-04 / T-08-02). ``worktree_dir`` is a discrete argv element,
    so even a dir whose leaf starts with a dash cannot inject a flag.
    """
    return ["git", "-C", source_repo, "worktree", "remove", worktree_dir]


def argv_worktree_prune(source_repo: str) -> list[str]:
    """``git -C <source_repo> worktree prune`` — clean stale admin entries."""
    return ["git", "-C", source_repo, "worktree", "prune"]


# --- GIT-01: branch + ahead/behind reads -------------------------------------

def argv_current_branch(repo: str) -> list[str]:
    """``git -C <repo> rev-parse --abbrev-ref HEAD`` — the short branch name."""
    return ["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"]


def argv_ahead_behind(repo: str, branch: str) -> list[str]:
    """``git -C <repo> rev-list --left-right --count <branch>...<branch>@{u}``.

    Counts commits ahead/behind the branch's upstream. With no upstream the
    invocation fails (rc!=0) printing empty/garbage stdout; ``parse_ahead_behind``
    degrades that to ``(0, 0)`` so the window simply suppresses the arrows.
    """
    return [
        "git", "-C", repo, "rev-list", "--left-right", "--count",
        f"{branch}...{branch}@{{u}}",
    ]


def parse_ahead_behind(stdout: str) -> tuple[int, int]:
    """Parse ``"A\\tB"`` into ``(ahead, behind)``; degrade junk to ``(0, 0)``.

    Tolerant by design (GIT-01): a repo with no tracking branch makes
    ``rev-list ...@{u}`` fail with empty/garbage stdout — the caller treats
    ``(0, 0)`` as "no tracking info" and hides the arrows. NEVER raises.
    """
    parts = stdout.split()
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]), int(parts[1])
    return (0, 0)
