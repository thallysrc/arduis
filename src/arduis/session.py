"""GTK-free serializable session model for the project/task core loop.

The single source of truth for which tasks exist, their dirs/branch, per-repo
worktrees, pid/pgid, and lifecycle state. The UI (tabs in Plan 02, the sidebar
later) is a *view* of this store. Imports NO ``gi``.

The unit of work is a TASK (03.2 pivot): one branch name across N member repos.
A ``Task`` owns N ``RepoCheckout``s (worktree metadata: repo_name, dir, branch).

UX pivot (2026-06-11, supersedes D-01/D-02): a task's DEFAULT workspace is TWO
TASK-LEVEL terminals — one ``agent`` running ``claude`` (``t0``) over one plain
``shell`` (``t1``) — held in ``Task.terminals`` (NOT per-repo), regardless of how
many repos the task spans. Both open at ``task.task_dir`` so one agent works
across every repo. Testing a real 6-repo project showed the old one-column-per-repo
default produced an unusable 2×6 grid of tiny panes; the user now grows the
workspace via the split machinery. ``RepoCheckout.terminals`` is kept for any
per-repo split a user attaches but is empty by default. A 1-repo project is the
identical shape — no special-case. This REPLACES the old single-worktree session
model (OQ3 — no two parallel models; the prior ``Worktree``-``Session`` type is gone).

Decisions:
- OQ1: terminal ids are structured ``{task_id}:{repo_name}:tN`` and each
  ``TerminalRecord`` carries a ``repo_name`` field, so per-repo RAM grouping and
  "close a repository" (D-10) are field lookups, not string parsing.
- OQ2: partial creation is best-effort (D-10 "arduis never deletes"). The model
  lets a ``Task`` hold the repos that succeeded while one aborts; no auto-rollback
  (the abort handling lands in Plan 02 ``window.py``; the model simply must not
  assume all repos are present).
- D-08 / Pitfall 1: the agent is launched by feeding ``AGENT_FEED`` into the PTY.
  It is the bytes literal ``b"claude\\n"`` because ``Vte.Terminal.feed_child``
  rejects ``str`` at the 0.76 floor (``TypeError: Must be number, not str``).
- D-08 / D-11 / Pitfall 3: hibernate clears EVERY terminal's pid/pgid across
  EVERY repo of the task (no group forgotten → RAM can't leak) but KEEPS every
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

# D-12 (Plan 04, RAM-04) — the resume feed for an AUTO-SUSPENDED task: `claude
# --continue` resumes the most recent conversation in the cwd so an idle auto-suspend
# costs the user nothing (verified flag in claude 2.1.175). bytes for the same reason
# as AGENT_FEED (feed_child rejects str at the 0.76 floor). MANUAL create/resume keeps
# AGENT_FEED so Phase-2 semantics are unchanged (the window selects which to feed by
# Task.auto_suspended).
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
    ``rss_kb`` is summed across a task's terminals by the caller (RAM-03).
    ``repo_name`` (OQ1) groups terminals by member repo for per-repo RAM/teardown
    and "close a repository" (D-10) — a field lookup, not string parsing.

    ``status``/``status_ts`` (Phase 4 STATUS-02) carry the latest attention state
    (``running``/``waiting``/``ready``/``idle``/``ended``, or None = no opinion yet)
    and its epoch timestamp, written by ``window.py`` from the state-file watcher
    and consumed by ``attention.aggregate_task``. They are appended LAST (after
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


def default_repo_terminals(task_id: str, repo_name: str) -> list[TerminalRecord]:
    """The default 2-terminal set for ONE repo of a task: agent + shell (D-01).

    OQ1 structured id ``{task}:{repo}:tN`` plus the ``repo_name`` field so RAM
    accounting and teardown can group by repo via a field lookup.
    """
    return [
        TerminalRecord(f"{task_id}:{repo_name}:t0", "agent", repo_name=repo_name),
        TerminalRecord(f"{task_id}:{repo_name}:t1", "shell", repo_name=repo_name),
    ]


def default_task_terminals(task_id: str) -> list[TerminalRecord]:
    """The default 2-terminal set for a TASK: agent + shell (UX pivot 2026-06-11).

    SUPERSEDES the one-column-per-repo default (D-01/D-02): testing a real 6-repo
    project produced an unusable 2×6 grid of tiny panes. The new default opens
    EVERY task workspace with exactly TWO task-level terminals — agent (claude,
    ``t0``) over shell (zsh, ``t1``) — regardless of repo count, BOTH rooted at the
    task folder (``task.task_dir``, which mirrors the project root) so one agent
    works across all the task's repos. The user grows the workspace via the split
    machinery; no per-repo columns are auto-created.

    Ids are ``{task_id}:tN`` (NO repo segment — task-scoped, not bound to a repo),
    matching the pinned-main workspace shape; ``repo_name`` stays ``None``.
    """
    return [
        TerminalRecord(f"{task_id}:t0", "agent"),
        TerminalRecord(f"{task_id}:t1", "shell"),
    ]


@dataclass
class RepoCheckout:
    """One member repo's worktree inside a task (D-08). GTK-free, serializable."""

    repo_name: str
    worktree_dir: str                     # <task_dir>/<repo_name>
    branch: str
    terminals: list[TerminalRecord] = field(default_factory=list)


@dataclass
class Task:
    """The unit of work: one branch across N member repos (D-08).

    A 1-repo project is a Task with one ``RepoCheckout`` (success criterion 5 —
    no special-case). ``repos`` may hold fewer than the project's members while a
    creation is in flight (best-effort partial creation, OQ2).
    """

    task_id: str                          # stable key (the branch name / sanitized)
    branch: str
    task_dir: str                         # ../<root_base>-tasks/<sanitized-branch>/
    repos: list[RepoCheckout] = field(default_factory=list)
    # UX pivot (2026-06-11): the task's DEFAULT workspace is TWO task-level
    # terminals (agent + shell) rooted at task_dir, regardless of repo count
    # (supersedes the per-repo columns of D-01/D-02). ``repos`` keeps worktree
    # metadata only; these are where the agent/shell actually run + any user
    # splits. ``terminals`` is the LAST field so positional construction keeps
    # working.
    state: SessionState = SessionState.ACTIVE
    terminals: list[TerminalRecord] = field(default_factory=list)
    # Phase 4 / D-12 (RAM-04): True iff this task was auto-suspended by the idle
    # auto-suspend tick (vs a user-driven hibernate). The WINDOW sets it True right
    # before firing the shared hibernate path and clears it on resume after selecting
    # the resume feed; ``hibernate_fields`` (the manual path) must never touch it so a
    # manual hibernate stays False. Appended LAST per the house rule so positional
    # construction keeps working; defaults False (a fresh task was never auto-suspended).
    auto_suspended: bool = False

    def to_dict(self) -> dict:
        """Serialize to a plain dict (asdict recurses repos → terminals — D-13/A2)."""
        return asdict(self)


class SessionStore:
    """In-memory registry of ``Task`` keyed by ``task_id``.

    Method names are kept (``add``/``get``/``by_branch``/``all``/``to_list``) so
    Plan 02's ``window.py`` migration is a minimal call-site change.
    """

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}

    def add(self, t: Task) -> None:
        self._tasks[t.task_id] = t

    def get(self, task_id: str) -> Task | None:
        return self._tasks.get(task_id)

    def remove(self, task_id: str) -> None:
        """Drop a task from the registry (e.g. a create where every repo aborted).

        Removes the in-memory record only — arduis NEVER deletes anything from
        disk (D-10); the symlink-only task folder may remain and the startup scan
        already rejects it (no ``.git`` worktree-pointer child).
        """
        self._tasks.pop(task_id, None)

    def by_branch(self, branch: str) -> Task | None:
        return next((t for t in self._tasks.values() if t.branch == branch), None)

    def all(self) -> list[Task]:
        return list(self._tasks.values())

    def to_list(self) -> list[dict]:
        """JSON-serializable snapshot (str-Enum dumps as its value)."""
        return [t.to_dict() for t in self._tasks.values()]


def hibernate_fields(task: Task) -> None:
    """Apply the hibernate model transition over a whole task (D-08/D-11, Pitfall 3).

    Flip state to HIBERNATED and clear EVERY terminal's pid/pgid across EVERY repo
    (each group is killed by the caller — no group forgotten, so RAM can't leak).
    Keep every repo's ``worktree_dir`` and the ``task_dir`` (dirs kept on disk)
    and each terminal's ``rss_kb`` untouched (frozen until re-spawn).
    """
    task.state = SessionState.HIBERNATED
    # Clear the TASK-level terminals (the default agent+shell pair + any user
    # splits live here under the UX pivot) AND any leftover per-repo terminals
    # (none by default, but a per-repo split could attach one) — no group forgotten.
    for t in task.terminals:
        t.pid = None
        t.pgid = None
    for repo in task.repos:
        for t in repo.terminals:
            t.pid = None
            t.pgid = None
    # every repo's worktree_dir + task.task_dir kept on disk; rss_kb untouched
