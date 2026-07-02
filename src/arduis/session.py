"""GTK-free serializable session model for the project/workspace core loop.

The single source of truth for which workspaces exist, their dirs/branch, per-repo
worktrees, pid/pgid, and lifecycle state. The UI (tabs in Plan 02, the sidebar
later) is a *view* of this store. Imports NO ``gi``.

The unit of work is a WORKSPACE (03.2 pivot): one branch name across N member repos.
A ``Workspace`` owns N ``RepoCheckout``s (worktree metadata: repo_name, dir, branch).

UX pivot (2026-06-11, supersedes D-01/D-02): a workspace's DEFAULT workspace is TWO
WORKSPACE-LEVEL terminals — one ``agent`` running ``claude`` (``t0``) over one plain
``shell`` (``t1``) — held in ``Workspace.terminals`` (NOT per-repo), regardless of how
many repos the workspace spans. Both open at ``workspace.workspace_dir`` so one agent works
across every repo. Testing a real 6-repo project showed the old one-column-per-repo
default produced an unusable 2×6 grid of tiny panes; the user now grows the
workspace via the split machinery. ``RepoCheckout.terminals`` is kept for any
per-repo split a user attaches but is empty by default. A 1-repo project is the
identical shape — no special-case. This REPLACES the old single-worktree session
model (OQ3 — no two parallel models; the prior ``Worktree``-``Session`` type is gone).

Decisions:
- OQ1: terminal ids are structured ``{workspace_id}:{repo_name}:tN`` and each
  ``TerminalRecord`` carries a ``repo_name`` field, so per-repo RAM grouping and
  "close a repository" (D-10) are field lookups, not string parsing.
- OQ2: partial creation is best-effort (D-10 "arduis never deletes"). The model
  lets a ``Workspace`` hold the repos that succeeded while one aborts; no auto-rollback
  (the abort handling lands in Plan 02 ``window.py``; the model simply must not
  assume all repos are present).
- D-08 / Pitfall 1: the agent is launched by feeding ``AGENT_FEED`` into the PTY.
  It is the bytes literal ``b"claude\\n"`` because ``Vte.Terminal.feed_child``
  rejects ``str`` at the 0.76 floor (``TypeError: Must be number, not str``).
- D-08 / D-11 / Pitfall 3: hibernate clears EVERY terminal's pid/pgid across
  EVERY repo of the workspace (no group forgotten → RAM can't leak) but KEEPS every
  dir on disk (the actual ``os.killpg`` teardown lives in ``window.py``; this
  module only models the field transition).
- D-13 / A2: the store is GTK-free and serializable via ``dataclasses.asdict``
  (recursing into repos → terminals), with each terminal's ``rss_kb`` RAM field
  present from day one (summed by the caller; populated in Phase 3). In-memory
  only — serializable does not mean persisted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum

AGENT_FEED: bytes = b"claude\n"  # D-08 — bytes, not str (0.76 feed_child TypeError on str)

# D-12 (Plan 04, RAM-04) — the resume feed for an AUTO-SUSPENDED workspace: `claude
# --continue` resumes the most recent conversation in the cwd so an idle auto-suspend
# costs the user nothing (verified flag in claude 2.1.175). bytes for the same reason
# as AGENT_FEED (feed_child rejects str at the 0.76 floor). MANUAL create/resume keeps
# AGENT_FEED so Phase-2 semantics are unchanged (the window selects which to feed by
# Workspace.auto_suspended).
AGENT_RESUME_FEED: bytes = b"claude --continue\n"


class SessionState(str, Enum):
    """str-Enum so it serializes to its plain value via ``asdict``/``json``."""

    ACTIVE = "active"
    HIBERNATED = "hibernated"


@dataclass
class TerminalRecord:
    """One terminal inside a repo's workspace (D-01).

    ``kind`` is ``"agent"`` (the PTY fed ``AGENT_FEED`` → ``claude``) or
    ``"shell"`` (a plain ``zsh``). ``pid``/``pgid`` come from the spawn callback
    and are the per-terminal teardown handle (cleared on hibernate, Pitfall 3).
    ``rss_kb`` is summed across a workspace's terminals by the caller (RAM-03).
    ``repo_name`` (OQ1) groups terminals by member repo for per-repo RAM/teardown
    and "close a repository" (D-10) — a field lookup, not string parsing.

    ``status``/``status_ts`` (Phase 4 STATUS-02) carry the latest attention state
    (``running``/``waiting``/``ready``/``idle``/``ended``, or None = no opinion yet)
    and its epoch timestamp, written by ``window.py`` from the state-file watcher
    and consumed by ``attention.aggregate_workspace``. They are appended LAST (after
    ``repo_name``) per the house rule so existing positional construction keeps
    working — they default to None (a fresh terminal has no opinion).
    """

    term_id: str                          # stable key, e.g. "feat:backend:t0"
    kind: str                             # "agent" (claude-fed) | "shell" (plain zsh)
    pid: int | None = None                # shell pid from the spawn callback
    pgid: int | None = None               # process-group id for teardown (RAM-01)
    rss_kb: int | None = None             # resident set size; None until a monitor lands
    repo_name: str | None = None          # OQ1 — which member repo this terminal belongs to
    status: str | None = None             # Phase 4 STATUS-02 — latest attention state; None=no opinion
    status_ts: float | None = None        # epoch of the last status write (staleness/idle sweep)


def default_repo_terminals(workspace_id: str, repo_name: str) -> list[TerminalRecord]:
    """The default 2-terminal set for ONE repo of a workspace: agent + shell (D-01).

    OQ1 structured id ``{workspace}:{repo}:tN`` plus the ``repo_name`` field so RAM
    accounting and teardown can group by repo via a field lookup.
    """
    return [
        TerminalRecord(f"{workspace_id}:{repo_name}:t0", "agent", repo_name=repo_name),
        TerminalRecord(f"{workspace_id}:{repo_name}:t1", "shell", repo_name=repo_name),
    ]


def default_workspace_terminals(workspace_id: str) -> list[TerminalRecord]:
    """The default 2-terminal set for a WORKSPACE: agent + shell (UX pivot 2026-06-11).

    SUPERSEDES the one-column-per-repo default (D-01/D-02): testing a real 6-repo
    project produced an unusable 2×6 grid of tiny panes. The new default opens
    EVERY workspace with exactly TWO workspace-level terminals — agent (claude,
    ``t0``) over shell (zsh, ``t1``) — regardless of repo count, BOTH rooted at the
    workspace folder (``workspace.workspace_dir``, which mirrors the project root) so one agent
    works across all the workspace's repos. The user grows the workspace via the split
    machinery; no per-repo columns are auto-created.

    Ids are ``{workspace_id}:tN`` (NO repo segment — workspace-scoped, not bound to a repo),
    matching the pinned-main workspace shape; ``repo_name`` stays ``None``.
    """
    return [
        TerminalRecord(f"{workspace_id}:t0", "agent"),
        TerminalRecord(f"{workspace_id}:t1", "shell"),
    ]


@dataclass
class RepoCheckout:
    """One member repo's worktree inside a workspace (D-08). GTK-free, serializable."""

    repo_name: str
    worktree_dir: str                     # <workspace_dir>/<repo_name>
    branch: str
    terminals: list[TerminalRecord] = field(default_factory=list)


@dataclass
class Workspace:
    """The unit of work: one branch across N member repos (D-08).

    A 1-repo project is a Workspace with one ``RepoCheckout`` (success criterion 5 —
    no special-case). ``repos`` may hold fewer than the project's members while a
    creation is in flight (best-effort partial creation, OQ2).
    """

    workspace_id: str                     # stable key (the branch name / sanitized)
    branch: str
    workspace_dir: str                    # ../<root_base>-tasks/<sanitized-branch>/
    repos: list[RepoCheckout] = field(default_factory=list)
    # UX pivot (2026-06-11): the workspace's DEFAULT workspace is TWO workspace-level
    # terminals (agent + shell) rooted at workspace_dir, regardless of repo count
    # (supersedes the per-repo columns of D-01/D-02). ``repos`` keeps worktree
    # metadata only; these are where the agent/shell actually run + any user
    # splits. ``terminals`` is the LAST field so positional construction keeps
    # working.
    state: SessionState = SessionState.ACTIVE
    terminals: list[TerminalRecord] = field(default_factory=list)
    # Phase 4 / D-12 (RAM-04): True iff this workspace was auto-suspended by the idle
    # auto-suspend tick (vs a user-driven hibernate). The WINDOW sets it True right
    # before firing the shared hibernate path and clears it on resume after selecting
    # the resume feed; ``hibernate_fields`` (the manual path) must never touch it so a
    # manual hibernate stays False. Appended LAST per the house rule so positional
    # construction keeps working; defaults False (a fresh workspace was never auto-suspended).
    auto_suspended: bool = False

    def to_dict(self) -> dict:
        """Serialize to a plain dict (asdict recurses repos → terminals — D-13/A2)."""
        return asdict(self)


class SessionStore:
    """In-memory registry of ``Workspace`` keyed by ``workspace_id``.

    Method names are kept (``add``/``get``/``by_branch``/``all``/``to_list``) so
    Plan 02's ``window.py`` migration is a minimal call-site change.
    """

    def __init__(self) -> None:
        self._workspaces: dict[str, Workspace] = {}

    def add(self, w: Workspace) -> None:
        self._workspaces[w.workspace_id] = w

    def get(self, workspace_id: str) -> Workspace | None:
        return self._workspaces.get(workspace_id)

    def remove(self, workspace_id: str) -> None:
        """Drop a workspace from the registry (e.g. a create where every repo aborted).

        Removes the in-memory record only — arduis NEVER deletes anything from
        disk (D-10); the symlink-only workspace folder may remain and the startup scan
        already rejects it (no ``.git`` worktree-pointer child).
        """
        self._workspaces.pop(workspace_id, None)

    def by_branch(self, branch: str) -> Workspace | None:
        return next((w for w in self._workspaces.values() if w.branch == branch), None)

    def all(self) -> list[Workspace]:
        return list(self._workspaces.values())

    def to_list(self) -> list[dict]:
        """JSON-serializable snapshot (str-Enum dumps as its value)."""
        return [w.to_dict() for w in self._workspaces.values()]


def hibernate_fields(workspace: Workspace) -> None:
    """Apply the hibernate model transition over a whole workspace (D-08/D-11, Pitfall 3).

    Flip state to HIBERNATED and clear EVERY terminal's pid/pgid across EVERY repo
    (each group is killed by the caller — no group forgotten, so RAM can't leak).
    Keep every repo's ``worktree_dir`` and the ``workspace_dir`` (dirs kept on disk)
    and each terminal's ``rss_kb`` untouched (frozen until re-spawn).
    """
    workspace.state = SessionState.HIBERNATED
    # Clear the WORKSPACE-level terminals (the default agent+shell pair + any user
    # splits live here under the UX pivot) AND any leftover per-repo terminals
    # (none by default, but a per-repo split could attach one) — no group forgotten.
    for t in workspace.terminals:
        t.pid = None
        t.pgid = None
    for repo in workspace.repos:
        for t in repo.terminals:
            t.pid = None
            t.pgid = None
    # every repo's worktree_dir + workspace.workspace_dir kept on disk; rss_kb untouched
