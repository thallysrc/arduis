"""GTK-free topbar chip-state (D-02/D-03/D-06). Imports NO gi.

Holds a project's member-repo set + the user's toggled-ON DEFAULT subset (which
seeds a new task's repo selection, D-02) and, separately, the repos of the
CURRENTLY-ACTIVE task to reflect/highlight (D-03) without disturbing the default.
window.py renders one chip per ``.members`` entry, styling it by ``is_selected``
(toggled-on) and ``is_active`` (belongs to the visible task), and seeds the
New-task dialog checkboxes from ``default_selection()``.

This is pure data + logic: it does NOT scan the disk (that stays in
``project.detect_member_repos`` — window.py passes its output, or the degenerate
1-element list, into the constructor). Keeping chip LOGIC out of GTK (D-06) makes
Plan 02 a thin render+wire and keeps both concerns separately testable.
"""
from __future__ import annotations


class ChipState:
    def __init__(self, members: list[str]) -> None:
        self.members: list[str] = list(members)
        # D-02: all member repos toggled ON by default (the dialog inherits this).
        self.selected: set[str] = set(self.members)
        # D-03: the active task's repos, reflected without touching `selected`.
        self.active_repos: set[str] | None = None

    def toggle(self, repo: str) -> None:
        """Flip one member chip on/off (no-op for non-members). `members` is never mutated."""
        if repo not in self.members:
            return
        if repo in self.selected:
            self.selected.discard(repo)
        else:
            self.selected.add(repo)

    def default_selection(self) -> list[str]:
        """Toggled-ON members in `members` order — seeds the New-task dialog (D-02)."""
        return [m for m in self.members if m in self.selected]

    def reflect_active(self, repo_names: set[str] | None) -> None:
        """Reflect the visible task's repos (D-03) WITHOUT changing the default set.

        None clears the reflection (pinned main / no task -> plain default highlight).
        """
        self.active_repos = set(repo_names) if repo_names is not None else None

    def is_selected(self, repo: str) -> bool:
        return repo in self.selected

    def is_active(self, repo: str) -> bool:
        return self.active_repos is not None and repo in self.active_repos
