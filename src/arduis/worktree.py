"""Pure git-argv builders + parsers for the worktree core loop (GTK-free).

This is the domain layer that turns an (untrusted) branch name into safe git
argv and a safe sibling directory. It imports NO ``gi`` and touches no I/O:
``git_service.py`` (Plan 02) executes the argv these functions return via
``Gio.Subprocess``, and ``window.py`` owns the GTK wiring.

Decisions:
- D-04: default branch is auto-detected (``origin/HEAD`` -> local ``HEAD``),
  never the hardcoded literal ``main``.
- D-05: the worktree dir is a sibling ``../<repo>-<sanitized-branch>``.
- D-06: new-vs-existing is inferred from the local branch list.
- D-07: the force flag is never emitted; already-checked-out branches are detected
  via a ``worktree list --porcelain`` pre-check and handled by the caller.

Threats:
- T-02-01 (tampering/EoP): every argv is a Python list literal with the branch
  as a discrete element; nothing is joined into a shell string and there is no
  ``shell=True`` path. The caller routes argv through ``HostRunner``.
- T-02-02 (path traversal): ``sanitize_branch_for_dir`` reduces a branch to a
  safe ``[A-Za-z0-9._-]`` leaf with ``..``/separators stripped, and
  ``worktree_dir_for`` derives the dir from ``repo_root``'s parent, never from
  raw input.
"""
from __future__ import annotations

import os
import re

_ORIGIN_HEAD_PREFIX = "refs/remotes/origin/"
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_DASH_RUNS = re.compile(r"-{2,}")


# --- default-branch detection (D-04) ----------------------------------------

def argv_default_branch_via_origin(repo: str) -> list[str]:
    """argv that prints ``refs/remotes/origin/HEAD`` (fails 128 with no origin)."""
    return ["git", "-C", repo, "symbolic-ref", "refs/remotes/origin/HEAD"]


def argv_default_branch_local(repo: str) -> list[str]:
    """Fallback argv that prints the short current branch (e.g. ``master``)."""
    return ["git", "-C", repo, "symbolic-ref", "--short", "HEAD"]


def parse_default_branch(stdout: str) -> str:
    """Strip the ``refs/remotes/origin/`` prefix (if present) and whitespace."""
    name = stdout.strip()
    if name.startswith(_ORIGIN_HEAD_PREFIX):
        name = name[len(_ORIGIN_HEAD_PREFIX):]
    return name


# --- born-HEAD guard (UAT: empty repo can't host a worktree) ----------------

def argv_repo_has_commit(repo: str) -> list[str]:
    """argv whose exit status is 0 iff ``repo`` has at least one commit.

    ``git worktree add`` needs an object to check out; a freshly ``git init``'d
    repo has an unborn HEAD and the add fails with the cryptic
    ``fatal: invalid reference: HEAD``. ``rev-parse --verify -q HEAD`` exits
    non-zero (printing nothing with ``-q``) when HEAD is unborn, so the caller
    can show a friendly message instead.
    """
    return ["git", "-C", repo, "rev-parse", "--verify", "-q", "HEAD"]


# --- worktree add argv (D-07: never the force flag) -------------------------

def argv_worktree_add_new(repo: str, branch: str, worktree_dir: str, base: str) -> list[str]:
    """``git worktree add -b <branch> <dir> <base>`` — create a NEW branch."""
    return ["git", "-C", repo, "worktree", "add", "-b", branch, worktree_dir, base]


def argv_worktree_add_existing(repo: str, worktree_dir: str, branch: str) -> list[str]:
    """``git worktree add <dir> <branch>`` — check out an EXISTING branch."""
    return ["git", "-C", repo, "worktree", "add", worktree_dir, branch]


# --- branch -> safe sibling dir (D-05 / T-02-02) ----------------------------

def sanitize_branch_for_dir(branch: str) -> str:
    """Reduce a branch name to a safe flat dir component.

    Replaces ``/`` and any char outside ``[A-Za-z0-9._-]`` with ``-``, collapses
    dash runs, and strips leading/trailing ``.``/``-`` so the result can NEVER be
    ``""``, ``.``, ``..`` or contain a path separator (path-traversal guard).
    """
    safe = _UNSAFE_CHARS.sub("-", branch)
    safe = _DASH_RUNS.sub("-", safe)
    safe = safe.strip(".-")
    # collapse any residual dot-only / empty result to a stable fallback
    if safe in ("", ".", ".."):
        return "branch"
    return safe


def worktree_dir_for(repo_root: str, branch: str) -> str:
    """Sibling dir ``<parent-of-repo>/<repo-basename>-<sanitized-branch>``."""
    root = repo_root.rstrip("/")
    parent = os.path.dirname(root)
    base = os.path.basename(root)
    return os.path.join(parent, base + "-" + sanitize_branch_for_dir(branch))


# --- local branch list + new-vs-existing (WT-01 / D-06) ---------------------

def argv_list_local_branches(repo: str) -> list[str]:
    """argv printing one local branch short-name per line."""
    return ["git", "-C", repo, "for-each-ref", "--format=%(refname:short)", "refs/heads"]


def parse_local_branches(stdout: str) -> list[str]:
    """One branch per line; tolerate a leading ``* `` current-branch marker."""
    branches = []
    for line in stdout.splitlines():
        name = line.replace("*", "", 1).strip()
        if name:
            branches.append(name)
    return branches


def infer_new_vs_existing(branch: str, existing: list[str]) -> str:
    """``"existing"`` if the branch is already a local branch, else ``"new"``."""
    return "existing" if branch in existing else "new"


# --- porcelain pre-check (D-07) ---------------------------------------------

def argv_worktree_list_porcelain(repo: str) -> list[str]:
    """argv for ``git worktree list --porcelain``."""
    return ["git", "-C", repo, "worktree", "list", "--porcelain"]


def parse_worktrees(porcelain: str) -> list[dict]:
    """Parse ``worktree list --porcelain`` into records.

    Records are blank-line separated. Each record yields ``path`` and ``branch``
    (the short name, or ``None`` when detached); ``locked`` is added when present.
    """
    out: list[dict] = []
    cur: dict = {}
    for line in porcelain.splitlines():
        if not line:
            if cur:
                out.append(cur)
                cur = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree":
            cur["path"] = val
        elif key == "branch":
            cur["branch"] = val.removeprefix("refs/heads/")
        elif key == "detached":
            cur["branch"] = None
        elif key == "locked":
            cur["locked"] = True
    if cur:
        out.append(cur)
    return out


def branch_checked_out_path(branch: str, parsed: list[dict]) -> str | None:
    """Return the path where ``branch`` is checked out, or ``None`` if nowhere."""
    for rec in parsed:
        if rec.get("branch") == branch:
            return rec.get("path")
    return None
