"""GTK-free attention/status policy brain for Phase 4 (STATUS-01/02/03, RAM-04).

Every decision rule that ``window.py`` (Plans 03/04) wires into the GTK loop lives
here as a PURE, unit-tested function — consistent with the ``layout.py`` / ``caps.py``
pattern. Imports NO ``gi`` and does NO I/O beyond the explicit file helpers
(``read_state`` / ``clear_status_dir`` / ``hook_script_source`` / ``load_config``).

Anchors (04-CONTEXT decisions):
- D-03: 5 states ``running / waiting / ready / idle / ended``. IDLE is COMPUTED by
  arduis (ready + threshold), NEVER written by a hook and NEVER derived from
  ``running`` (a long tool call emits no events — Pitfall 6). ``waiting`` is the
  cardinal orange: it is NEVER silently auto-degraded (Pitfall 2).
- D-04: per-terminal state files under ``$XDG_RUNTIME_DIR/arduis/status/`` with the
  ``~/.cache/arduis/status/`` fallback; arduis composes the FULL path itself and
  hands it to the hook via env, so branch-name sanitization lives in tested Python.
- D-06: a task's status aggregates over its AGENT terminals only (waiting >
  running > ready > idle > ended); a terminal with no opinion (no state file ever)
  contributes nothing (Pitfall 8).
- Pitfall 5/7: a ``running`` file whose hook pid is dead → ``ended``; a ``running``
  older than a generous ceiling degrades to ``ready`` on the sweep (never from
  ``waiting``).

This module performs NO GTK and NO blocking work: ``effective_status`` /
``aggregate_task`` take ``now`` and ``pid_alive`` from the caller and never touch
the clock or the process table themselves.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from enum import Enum

# --- Sanitization (mirror worktree.sanitize_branch_for_dir hardening) ----------
# term_id is task-scoped ("feat:t0") or repo-split ("feat:backend:t2"); ":" is a
# legal Linux filename char so it is KEPT, only the unsafe set collapses to "-".
_UNSAFE_TERM_CHARS = re.compile(r"[^A-Za-z0-9._:-]")
_DOTDOT = re.compile(r"\.\.+")  # any run of >=2 dots -> "-" (path-traversal guard)

# Generous ceiling: a "running" older than this with no fresh event degrades to
# "ready" on the sweep. Generous because a long tool/Bash call emits no events
# (Pitfall 6) and a wrongly-degraded running could chain into auto-suspend.
RUNNING_STALE_CEILING_S = 2 * 3600  # 2h (UAT-revisitable)


class AgentStatus(str, Enum):
    """The 5-state model (D-03). str-Enum so ``.value`` is the plain string and it
    serializes/round-trips through the state-file JSON ``"state"`` field."""

    RUNNING = "running"
    WAITING = "waiting"
    READY = "ready"
    IDLE = "idle"
    ENDED = "ended"


# Aggregation precedence (D-06): waiting > running > ready > idle > ended. Lower
# index == higher urgency.
_PRECEDENCE = (
    AgentStatus.WAITING,
    AgentStatus.RUNNING,
    AgentStatus.READY,
    AgentStatus.IDLE,
    AgentStatus.ENDED,
)


@dataclass
class StateDoc:
    """Parsed shape of a hook-written state file (Plan 01 contract).

    Only the fields arduis consumes are modeled; unknown keys in the JSON are
    ignored. ``message`` feeds the notification body; ``pid`` feeds the staleness
    sweep (Pitfall 5: verify the hook pid is alive before trusting ``running``).
    """

    state: str
    ts: float
    event: str
    message: str
    pid: int | None


# --- State-file paths (D-04) ---------------------------------------------------
def status_dir(env: dict | None = None) -> str:
    """Directory holding the per-terminal state files (D-04).

    ``$XDG_RUNTIME_DIR/arduis/status`` when set (tmpfs, 0700, auto-cleared at
    logout); otherwise the ``$HOME/.cache/arduis/status`` fallback. Pure: reads the
    supplied mapping (defaults to ``os.environ``), composes a path, no I/O.
    """
    if env is None:
        env = dict(os.environ)
    runtime = env.get("XDG_RUNTIME_DIR")
    if runtime:
        return os.path.join(runtime, "arduis", "status")
    home = env.get("HOME", "")
    return os.path.join(home, ".cache", "arduis", "status")


def sanitize_term_id(term_id: str) -> str:
    """Reduce any term_id (may embed a user branch name) to a SAFE flat leaf.

    Allowlist ``[A-Za-z0-9._:-]`` (":" kept — legal on Linux and used by the
    structured ids), every other char → "-", then collapse any ".." run to "-" so
    no parent-traversal segment can survive (T-04-06). The result can never be
    ``""``, ``.``, ``..`` or contain a path separator.
    """
    safe = _UNSAFE_TERM_CHARS.sub("-", term_id)
    safe = _DOTDOT.sub("-", safe)
    safe = safe.strip(".")
    if safe in ("", ".", ".."):
        return "term"
    return safe


def state_file_path(dir: str, term_id: str) -> str:
    """Absolute leaf ``<dir>/<sanitize(term_id)>.json`` (T-04-06: flat, in-dir).

    The sanitized leaf can contain no ``os.sep`` and no surviving ``..``, so the
    result's ``dirname`` is always exactly ``dir`` — a hostile term_id cannot
    escape the status directory.
    """
    return os.path.join(dir, sanitize_term_id(term_id) + ".json")


def clear_status_dir(dir: str) -> None:
    """Wipe stale state files at arduis startup (Pitfall 5), creating ``dir``.

    Unlinks ONLY regular, non-symlink files DIRECTLY inside ``dir`` (the ``x.json``
    state files plus any ``.arduis-*`` mkstemp leftovers). Subdirectories and
    symlinks are IGNORED — no recursion and no symlink-follow (T-04-11: a hostile
    symlink can't trick the wipe into deleting outside the dir). Missing dir is a
    no-op beyond creating it.
    """
    os.makedirs(dir, exist_ok=True)
    with os.scandir(dir) as it:
        for entry in it:
            try:
                # is_symlink first (no follow); only plain regular files unlink.
                if entry.is_symlink():
                    continue
                if entry.is_file(follow_symlinks=False):
                    os.unlink(entry.path)
            except OSError:
                # never let a single odd entry crash startup cleanup
                continue


# --- Tolerant read (T-04-07) ---------------------------------------------------
def read_state(path: str) -> StateDoc | None:
    """Parse a state file into a ``StateDoc``; return None on ANY failure.

    Tolerates a missing file, an empty file, garbage bytes, and a JSON object that
    lacks the required ``state`` key — readers (on the GTK main loop) NEVER crash on
    a half-written file (T-04-07). ``ts`` defaults to 0.0, ``pid`` stays None when
    absent/non-int.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    state = data.get("state")
    if not isinstance(state, str) or not state:
        return None
    try:
        ts = float(data.get("ts", 0.0))
    except (TypeError, ValueError):
        ts = 0.0
    pid = data.get("pid")
    if not isinstance(pid, int) or isinstance(pid, bool):
        pid = None
    return StateDoc(
        state=state,
        ts=ts,
        event=str(data.get("event", "") or ""),
        message=str(data.get("message", "") or ""),
        pid=pid,
    )


# --- Time-based effective status (D-03, Pitfalls 5/6/7) ------------------------
def effective_status(
    doc: StateDoc,
    now: float,
    pid_alive: bool,
    idle_after_s: float,
    stale_running_s: float = RUNNING_STALE_CEILING_S,
) -> AgentStatus:
    """Compute the CURRENT status from a parsed doc + time + pid liveness.

    Pure (no clock, no process table — the caller supplies ``now`` and
    ``pid_alive``). Rules:
    - ``ready``  : IDLE once ``now - ts >= idle_after_s`` (D-03 idle is computed),
                   else READY.
    - ``waiting``: stays WAITING regardless of age while the pid is alive (NEVER
                   auto-degrade the orange — Pitfall 2); a dead pid → ENDED.
    - ``running``: dead pid → ENDED (Pitfall 5: SIGKILL'd claude never fired
                   SessionEnd); alive but older than ``stale_running_s`` → READY
                   (Pitfall 7 phantom-running guard, generous ceiling); else
                   RUNNING.
    - ``ended``  : stays ENDED.
    Unknown ``state`` strings fall through to ENDED (conservative — they never
    look active and so can never block auto-suspend or paint a false orange).
    """
    age = now - doc.ts
    state = doc.state
    if state == AgentStatus.READY.value:
        return AgentStatus.IDLE if age >= idle_after_s else AgentStatus.READY
    if state == AgentStatus.WAITING.value:
        # cardinal rule: a real waiting is never auto-cleared by time; only a dead
        # process retires it.
        return AgentStatus.WAITING if pid_alive else AgentStatus.ENDED
    if state == AgentStatus.RUNNING.value:
        if not pid_alive:
            return AgentStatus.ENDED
        if age > stale_running_s:
            return AgentStatus.READY
        return AgentStatus.RUNNING
    if state == AgentStatus.IDLE.value:
        return AgentStatus.IDLE
    # ended or anything unrecognized
    return AgentStatus.ENDED


# --- Task aggregation (D-06, Pitfall 8) ----------------------------------------
def aggregate_task(records) -> AgentStatus | None:
    """Aggregate a task's AGENT terminals into one status (D-06), or None.

    Precedence waiting > running > ready > idle > ended. Only ``kind == "agent"``
    records with a non-None ``status`` contribute (Pitfall 8: shell terminals and
    agents that never produced a file have NO opinion — a task whose agent never
    wrote a file must not look idle and so must not auto-suspend). Empty/all-None
    input → None.

    Statuses are read from each record's ``status`` string field (the
    ``effective_status`` result the watcher stored on the record).
    """
    seen: set[str] = set()
    for rec in records:
        if getattr(rec, "kind", None) != "agent":
            continue
        status = getattr(rec, "status", None)
        if status is None:
            continue
        seen.add(status)
    if not seen:
        return None
    for status in _PRECEDENCE:
        if status.value in seen:
            return status
    # a record carried an unrecognized status string only -> no recognized opinion
    return None
