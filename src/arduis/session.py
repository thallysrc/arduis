"""GTK-free serializable session model for the worktree core loop.

The single source of truth for which worktrees exist, their dirs/branch,
pid/pgid, and lifecycle state. The UI (tabs in Plan 02, the Phase-3 sidebar
later) is a *view* of this store. Imports NO ``gi``.

Decisions:
- D-02 / D-03: a worktree is a *workspace of N terminals* (default 2 — one
  ``agent`` running ``claude`` and one plain ``shell``), not a single pid. Each
  terminal is a ``TerminalRecord``; ``default_terminals(sid)`` yields the agent +
  shell default. The canvas (Plan 02/03) shows ONE worktree's terminals.
- D-08 / Pitfall 1: the agent is launched by feeding ``AGENT_FEED`` into the
  PTY. It is the bytes literal ``b"claude\\n"`` because ``Vte.Terminal.feed_child``
  rejects ``str`` at the 0.76 floor (``TypeError: Must be number, not str``).
- D-08 / D-11 / Pitfall 3: hibernate clears EVERY terminal's pid/pgid (no group
  forgotten by the caller's teardown loop, so RAM can't leak) but KEEPS the
  directory on disk (the actual ``os.killpg`` teardown lives in ``window.py``;
  this module only models the field transition).
- D-10 / D-13: the store is GTK-free and serializable via ``dataclasses.asdict``
  (recursing into the terminals list — A2), with each terminal's ``rss_kb`` RAM
  field present from day one (summed across terminals by the caller; populated in
  Phase 3). In-memory only — serializable does not mean persisted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum

AGENT_FEED: bytes = b"claude\n"  # D-08 — bytes, not str (0.76 feed_child TypeError on str)


class SessionState(str, Enum):
    """str-Enum so it serializes to its plain value via ``asdict``/``json``."""

    ACTIVE = "active"
    HIBERNATED = "hibernated"


@dataclass
class TerminalRecord:
    """One terminal inside a worktree workspace (D-02/D-03).

    ``kind`` is ``"agent"`` (the PTY fed ``AGENT_FEED`` → ``claude``) or
    ``"shell"`` (a plain ``zsh``). ``pid``/``pgid`` come from the spawn callback
    and are the per-terminal teardown handle (cleared on hibernate, Pitfall 3).
    ``rss_kb`` is summed across a worktree's terminals by the caller (RAM-03).
    """

    term_id: str                          # stable leaf key, e.g. "feat:t0"
    kind: str                             # "agent" (claude-fed) | "shell" (plain zsh)
    pid: int | None = None                # shell pid from the spawn callback
    pgid: int | None = None               # process-group id for teardown (RAM-01)
    rss_kb: int | None = None             # resident set size; None until a monitor lands


def default_terminals(session_id: str) -> list[TerminalRecord]:
    """The default 2-terminal workspace for a worktree: one agent + one shell (D-02/D-03)."""
    return [
        TerminalRecord(f"{session_id}:t0", "agent"),
        TerminalRecord(f"{session_id}:t1", "shell"),
    ]


@dataclass
class WorktreeSession:
    """One worktree's lifecycle state — a workspace of N terminals. GTK-free, serializable."""

    session_id: str                       # stable key (e.g. the branch name)
    branch: str
    worktree_dir: str                     # absolute sibling path ../<repo>-<branch>
    repo_root: str
    state: SessionState = SessionState.ACTIVE
    # N terminals per worktree (default 2 via default_terminals — D-02/D-03). The
    # legacy single-terminal pid/pgid/rss_kb now live in terminals[0].
    terminals: list[TerminalRecord] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to a plain dict (asdict recurses into terminals — D-10/A2)."""
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
    """Apply the hibernate model transition (D-08/D-11, Pitfall 3).

    Flip state to HIBERNATED and clear EVERY terminal's pid/pgid (each group is
    killed by the caller — no group forgotten, so RAM can't leak). Leave
    ``worktree_dir``/``repo_root`` (directory kept on disk) and each terminal's
    ``rss_kb`` untouched (frozen until re-spawn).
    """
    session.state = SessionState.HIBERNATED
    for t in session.terminals:
        t.pid = None
        t.pgid = None
    # worktree_dir kept on disk (D-08/D-11); rss_kb left as-is on each terminal
