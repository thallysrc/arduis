"""GTK-free project/member-repo discovery (D-05/D-07). Imports NO gi.

A *project* is a root folder; its direct subdirs that contain a ``.git`` entry
(dir OR file) are its member repos. The root's OWN ``.git`` is never a member
(D-05) and there is no walk-up-the-tree (D-07). A project with no member subdirs
is the degenerate 1-repo case: the caller treats ``[]`` as "this root is itself
the single repo" and builds a one-``RepoCheckout`` Task (success criterion 5).

Threats (see 03.2 threat register):
- T-03.2-04: scanned dir names are returned verbatim and only ever land as
  discrete ``-C <path>`` git-argv elements (list form, never a shell string), so a
  newline/space in a dir name cannot be interpolated into a command.
"""
from __future__ import annotations

import os


def detect_member_repos(root: str) -> list[str]:
    """Direct subdirs of ``root`` that contain a ``.git`` entry (dir OR file).

    The root's own ``.git`` is NOT a member (D-05): ``scandir`` only yields
    direct children, so the root's ``.git`` is never in the subdir scan. A
    ``.git`` *file* (linked worktree / submodule) counts via ``os.path.exists``
    (Pitfall 1), not only ``isdir``. Symlinked subdirs are not followed
    (``follow_symlinks=False``). Returns sorted names; ``[]`` on error or when
    none (caller treats ``[]`` as the degenerate 1-repo project).
    """
    members: list[str] = []
    try:
        with os.scandir(root) as it:
            for e in it:
                if e.is_dir(follow_symlinks=False) and os.path.exists(
                    os.path.join(e.path, ".git")
                ):
                    members.append(e.name)
    except OSError:
        return []
    return sorted(members)
