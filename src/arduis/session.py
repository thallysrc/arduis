"""GTK-free serializable session model for the worktree core loop.

The single source of truth for which worktrees exist, their dirs/branch,
pid/pgid, and lifecycle state. The UI (tabs in Plan 02, the Phase-3 sidebar
later) is a *view* of this store. Imports NO ``gi``.

Decisions:
- D-08 / Pitfall 1: the agent is launched by feeding ``AGENT_FEED`` into the
  PTY. It is the bytes literal ``b"claude\\n"`` because ``Vte.Terminal.feed_child``
  rejects ``str`` at the 0.76 floor (``TypeError: Must be number, not str``).
- D-11: hibernate kills the worktree process group and clears pid/pgid but KEEPS
  the directory on disk (the actual ``os.killpg`` teardown lives in Plan 02's
  ``window.py``; this module only models the field transition).
- D-13: the store is GTK-free and serializable via ``dataclasses.asdict``, with
  the ``rss_kb`` RAM field present from day one (populated in Phase 3), but it is
  in-memory only in Phase 2 — serializable does not mean persisted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum

AGENT_FEED: bytes = b"claude\n"  # D-08 — bytes, not str (0.76 feed_child TypeError on str)


class SessionState(str, Enum):
    """str-Enum so it serializes to its plain value via ``asdict``/``json``."""

    ACTIVE = "active"
    HIBERNATED = "hibernated"


@dataclass
class WorktreeSession:
    """One worktree's lifecycle state. Serializable, GTK-free."""

    session_id: str                       # stable key (e.g. the branch name)
    branch: str
    worktree_dir: str                     # absolute sibling path ../<repo>-<branch>
    repo_root: str
    state: SessionState = SessionState.ACTIVE
    pid: int | None = None                # shell pid from the spawn callback
    pgid: int | None = None               # process-group id for teardown (RAM-01)
    # --- RAM fields, present day-one (D-13); populated in Phase 3 (RAM-02/03) ---
    rss_kb: int | None = None             # resident set size; None until a monitor lands

    def to_dict(self) -> dict:
        """Serialize to a plain dict (proves D-13 serializability, no persistence)."""
        return asdict(self)


class SessionStore:
    """In-memory registry of ``WorktreeSession`` keyed by ``session_id``."""

    def __init__(self) -> None:
        self._sessions: dict[str, WorktreeSession] = {}

    def add(self, s: WorktreeSession) -> None:
        self._sessions[s.session_id] = s

    def get(self, sid: str) -> WorktreeSession | None:
        return self._sessions.get(sid)

    def by_branch(self, branch: str) -> WorktreeSession | None:
        return next((s for s in self._sessions.values() if s.branch == branch), None)

    def all(self) -> list[WorktreeSession]:
        return list(self._sessions.values())

    def to_list(self) -> list[dict]:
        """JSON-serializable snapshot (str-Enum dumps as its value)."""
        return [s.to_dict() for s in self._sessions.values()]


def hibernate_fields(session: WorktreeSession) -> None:
    """Apply the hibernate model transition (D-11).

    Flip state to HIBERNATED and clear pid/pgid (the agent's group is killed by
    the caller). Leave ``worktree_dir``/``repo_root`` (directory kept on disk) and
    ``rss_kb`` untouched.
    """
    session.state = SessionState.HIBERNATED
    session.pid = None
    session.pgid = None
    # worktree_dir kept on disk (D-11); rss_kb left as-is
