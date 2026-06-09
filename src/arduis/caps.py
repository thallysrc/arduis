"""GTK-free active-agent cap policy (RAM-02).

Pure functions over the in-memory ``WorktreeSession`` store that decide whether a
new worktree launch must be blocked. Imports NO ``gi``.

Decisions:
- D-15: ``ACTIVE_CAP_DEFAULT`` is the default active-agent cap (~6). This is the
  SINGLE place Phase 6 will source the value from — Phase 6 lets a trusted-repo
  ``.arduis.toml`` override it; Phase 3 uses this interim default. Keep it the one
  authoritative constant so there is exactly one knob to rewire.
- D-16: ``at_cap`` triggers with ``>=`` (active_count >= cap). When True,
  ``window.py`` (Plan 03-05) must BLOCK the new-worktree launch and present the
  prompt-to-hibernate chooser — never silent-allow, never create-hibernated.
"""
from __future__ import annotations

ACTIVE_CAP_DEFAULT = 6  # D-15 — default active-agent cap; Phase-6 .arduis.toml override point


def active_count(sessions) -> int:
    """Number of sessions whose state is ACTIVE (hibernated ones don't count)."""
    return sum(1 for s in sessions if s.state.value == "active")


def at_cap(sessions, cap: int = ACTIVE_CAP_DEFAULT) -> bool:
    """True iff the active-agent count has reached the cap (D-16, ``>=`` trigger).

    True means ``window.py`` must BLOCK the new-worktree launch and present the
    prompt-to-hibernate chooser — never silent-allow, never create-hibernated.
    """
    return active_count(sessions) >= cap
