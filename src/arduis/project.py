"""GTK-free project/member-repo discovery (D-05/D-07; D-04 03.3). Imports NO gi.

A *project* is a root folder; its direct subdirs whose ``.git`` is a **directory**
(a true repo) are its member repos. A subdir whose ``.git`` is a FILE is a linked
worktree / submodule and is NOT a member (D-04 / 03.3). The root's OWN ``.git`` is
never a member (D-05) and there is no walk-up-the-tree (D-07). A project with no
member subdirs is the degenerate 1-repo case: the caller treats ``[]`` as "this
root is itself the single repo" and builds a one-``RepoCheckout`` Task (criterion 5).

Threats (see 03.2 threat register):
- T-03.2-04: scanned dir names are returned verbatim and only ever land as
  discrete ``-C <path>`` git-argv elements (list form, never a shell string), so a
  newline/space in a dir name cannot be interpolated into a command.
"""
from __future__ import annotations

import os


def detect_member_repos(root: str) -> list[str]:
    """Direct subdirs of ``root`` whose ``.git`` is a **directory** (a true repo).

    The root's own ``.git`` is NOT a member (D-05): ``scandir`` only yields
    direct children, so the root's ``.git`` is never in the subdir scan. D-04
    (03.3): the membership test is ``os.path.isdir(.../.git)`` — a ``.git`` FILE
    (linked worktree / submodule) is NOT a member, REVERSING the 03.2 "Pitfall 1"
    behavior that counted it via ``os.path.exists``. The PO's real ``Livon-Saude``
    root has ~20 ``backend-*``/``frontend-*`` worktrees (``.git`` is a FILE) that
    would otherwise flood the topbar chip bar. Symlinked subdirs are not followed
    (``follow_symlinks=False`` — T-03.3-03 still guarded). Returns sorted names;
    ``[]`` on error or when none (caller treats ``[]`` as the degenerate 1-repo
    project).
    """
    members: list[str] = []
    try:
        with os.scandir(root) as it:
            for e in it:
                if e.is_dir(follow_symlinks=False) and os.path.isdir(
                    os.path.join(e.path, ".git")
                ):
                    members.append(e.name)
    except OSError:
        return []
    return sorted(members)
