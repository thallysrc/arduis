"""GTK-free task-folder layout builders (D-08/D-09). Imports NO gi.

A *task* is one branch name across N member repos. Its worktrees live grouped
under a sibling folder ``<parent-of-root>/<root_base>-tasks/<sanitized-branch>/``
(D-08), each member repo getting a subdir that KEEPS the repo's dir name so
relative compose build-contexts/bind-mounts resolve verbatim. Non-repo top-level
root entries (CLAUDE.md, docker-compose.yml, scripts, ...) are mirrored into the
task folder as symlinks so the layout mirrors the root (D-09).

Threats (see 03.2 threat register):
- T-03.2-01 (path traversal): the task-dir leaf is ``sanitize_branch_for_dir(branch)``
  (reused tested T-02-02 guard); ``task_dir_for`` derives the dir from
  ``dirname(root)``, never from raw branch input.
- T-03.2-02 (symlink escape, V12): ``symlink_plan`` only enumerates top-level
  entries of ``root`` and positions them INSIDE ``task_dir``; it never resolves
  user input into a symlink target. The caller materializes with a RELATIVE
  target (``os.path.relpath``) so the task folder stays relocatable.
- T-03.2-03 (force clobber): ``resolve_repo_add`` returns argv LISTS with the
  branch a discrete element and NEVER emits ``--force`` (D-13).
"""
from __future__ import annotations

import os

from arduis.worktree import (
    argv_worktree_add_existing,
    argv_worktree_add_new,
    branch_checked_out_path,
    infer_new_vs_existing,
    sanitize_branch_for_dir,
)


def task_dir_for(root: str, branch: str) -> str:
    """Grouped sibling: ``<parent-of-root>/<root_base>-tasks/<sanitized-branch>`` (D-08).

    The leaf is ``sanitize_branch_for_dir(branch)`` so a malicious branch
    (``../../etc``) can never escape into a parent dir (T-03.2-01).
    """
    root = root.rstrip("/")
    parent, base = os.path.dirname(root), os.path.basename(root)
    return os.path.join(parent, f"{base}-tasks", sanitize_branch_for_dir(branch))


def repo_worktree_dir(task_dir: str, repo_name: str) -> str:
    """A chosen repo's worktree dir inside the task folder (D-08 — repo dir names kept)."""
    return os.path.join(task_dir, repo_name)


def symlink_plan(root: str, task_dir: str, chosen_repos: set[str]) -> list[tuple[str, str]]:
    """``(src_abs_in_root, dst_in_task_dir)`` for every top-level root entry EXCEPT
    the chosen repos (real worktrees, materialized separately — D-09) and the
    meta-repo ``.git`` (NOT mirrored — D-05).

    Pure: lists root entries, returns ``(src, dst)`` pairs. The caller does the
    ``os.symlink(os.path.relpath(src, task_dir), dst)`` with a RELATIVE target so
    the task folder stays relocatable (Pattern 3, A1) — keeping this function
    I/O-free and testable.
    """
    plan: list[tuple[str, str]] = []
    for name in sorted(os.listdir(root)):
        if name in chosen_repos:
            continue  # real worktree, materialized separately (D-09)
        if name == ".git":
            continue  # meta-repo .git is NOT mirrored (D-05)
        plan.append((os.path.join(root, name), os.path.join(task_dir, name)))
    return plan


def resolve_repo_add(repo_path, branch, existing_branches, parsed_worktrees, base, worktree_dir):
    """Per-repo D-13 resolution. Returns one of:

      ``("new", argv)``      — create a new branch off ``base``
      ``("existing", argv)`` — check out the existing branch
      ``("abort", reason)``  — branch checked out elsewhere; NEVER ``--force``

    Pure: no I/O, no git execution. The caller (``window.py``, Plan 02) runs the
    porcelain pre-check + branch list async, then calls this per repo
    (best-effort, OQ2 — each repo resolves independently, no all-or-nothing
    coupling). The degenerate 1-repo project resolves through this IDENTICAL path
    (success criterion 5 — there is no ``len(repos) == 1`` branch).
    """
    where = branch_checked_out_path(branch, parsed_worktrees)
    if where is not None:
        return ("abort", f"A branch '{branch}' já está em uso em {where}. Escolha outra branch.")
    kind = infer_new_vs_existing(branch, existing_branches)
    if kind == "new":
        return ("new", argv_worktree_add_new(repo_path, branch, worktree_dir, base))
    return ("existing", argv_worktree_add_existing(repo_path, worktree_dir, branch))
