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

import copy
import json
import os
import re
import tomllib
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


# --- Instant-waiting accelerator: terminal-text prompt detection ---------------
# Claude Code fires the permission Notification only ~6s AFTER the prompt renders
# (measured 2026-07-01; no bell, no config to shorten it). The visible terminal
# text is the only instant signal. This is the sanctioned SECONDARY channel
# (RESEARCH Pattern 5): escalate-only — hook events stay authoritative and
# overwrite whatever this detects. A marker alone is not enough (claude may echo
# the phrase in prose); the real dialog always renders a numbered option list.
_PROMPT_MARKERS = (
    "Do you want to proceed?",
    "Do you trust the files in this folder?",
)
_PROMPT_OPTION_SIGNATURE = "1. Yes"


def looks_like_permission_prompt(text: str) -> bool:
    """True iff ``text`` (a terminal tail snapshot) shows a live approval dialog."""
    if not text:
        return False
    if _PROMPT_OPTION_SIGNATURE not in text:
        return False
    return any(marker in text for marker in _PROMPT_MARKERS)


# --- Hook install: settings merge builder (Pattern 3, Pitfall 9, T-04-08) ------
# The 7 events arduis subscribes to (Pattern 1 event->state map). Matcher events
# carry a "matcher": "*" group; the other 5 omit the matcher key (Pitfall 9 /
# settings shape).
HOOK_EVENTS = (
    "SessionStart",
    "UserPromptSubmit",
    "Notification",
    "PostToolUse",
    "PostToolUseFailure",
    "Stop",
    "SessionEnd",
)
MATCHER_EVENTS = ("PostToolUse", "PostToolUseFailure")

# Stable install location for the env-guarded hook script (Pattern 2). The packaged
# source lives in the arduis.hooks package; arduis writes a refreshed copy here and
# registers it by ABSOLUTE path.
_INSTALL_REL = (".local", "share", "arduis", "hooks", "arduis_status_hook.py")
_DECLINED_REL = (".local", "share", "arduis", "hooks_declined")

HOOK_TIMEOUT_S = 5  # pinned (T-04-01): a misbehaving hook must not stall claude


def hook_command(script_path: str) -> str:
    """The exec-form ``command`` string for a settings hook entry (Pitfall 9).

    Returns ``/usr/bin/env python3 <abs-script>`` with a fully expanded ABSOLUTE
    path: a ``~`` is expanded, and the result must contain no ``~`` and no ``$`` —
    settings hook commands do NOT reliably expand tilde/vars across shells, so the
    path is resolved at merge time.
    """
    expanded = os.path.expanduser(os.path.expandvars(script_path))
    if not os.path.isabs(expanded) or "~" in expanded or "$" in expanded:
        raise ValueError(f"hook script path must be absolute and expansion-free: {script_path!r}")
    return f"/usr/bin/env python3 {expanded}"


def install_target_path(home: str) -> str:
    """Absolute install path of the hook script under the user's home (Pattern 2)."""
    return os.path.join(home, *_INSTALL_REL)


def declined_marker_path(home: str) -> str:
    """Path of the declined-consent marker file (D-02).

    Presence suppresses the consent dialog; arduis ``touch``es it on decline.
    tomllib is read-only so a marker file avoids growing a TOML-writer dependency.
    """
    return os.path.join(home, *_DECLINED_REL)


def hook_script_source() -> str:
    """Return the packaged hook-script content for the installer.

    Reads ``src/arduis/hooks/arduis_hook.py`` (Plan 01) via ``importlib.resources``
    so it works from an installed package too. Lazy import keeps this module
    dependency-light and lets the rest of the surface load even before Plan 01's
    ``arduis.hooks`` package exists in a parallel worktree.
    """
    from importlib.resources import files

    return files("arduis.hooks").joinpath("arduis_hook.py").read_text(encoding="utf-8")


def is_installed(settings: dict, script_path: str) -> bool:
    """True iff EVERY ``HOOK_EVENTS`` event already has an arduis hook for the path.

    A partial install (e.g. 5 of 7 events present) returns False so the next merge
    completes it. Matches by ``script_path in hook["command"]`` across each event's
    existing groups.
    """
    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False
    for event in HOOK_EVENTS:
        if not _event_has_script(hooks.get(event), script_path):
            return False
    return True


def _event_has_script(groups, script_path: str) -> bool:
    """True iff any hook in any group for this event references ``script_path``."""
    if not isinstance(groups, list):
        return False
    for group in groups:
        if not isinstance(group, dict):
            continue
        for hook in group.get("hooks", []) or []:
            if isinstance(hook, dict) and script_path in str(hook.get("command", "")):
                return True
    return False


def merged_settings(settings: dict, script_path: str) -> tuple[dict, bool]:
    """Build an ADDITIVE, idempotent, dedupe-by-path merge of arduis hooks (T-04-08).

    Returns ``(new_settings, changed)``. NEVER mutates the input (deepcopy). Every
    existing entry and unrelated top-level key (``permissions``/``model``/
    ``statusLine``/...) is preserved byte-identical; arduis APPENDS one group per
    missing event. Re-running on the result yields ``changed == False``. The
    appended ``PostToolUse``/``PostToolUseFailure`` groups carry ``"matcher": "*"``;
    the other 5 omit the matcher key. Each appended hook is exactly
    ``{"type": "command", "command": hook_command(path), "timeout": HOOK_TIMEOUT_S}``.
    """
    out = copy.deepcopy(settings)
    hooks = out.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        # a corrupt/non-dict "hooks" key: never destroy it silently — refuse to
        # touch and report unchanged (Plan 03's WRITE backs up first regardless).
        return out, False
    changed = False
    command = hook_command(script_path)
    for event in HOOK_EVENTS:
        groups = hooks.get(event)
        if not isinstance(groups, list):
            groups = []
            hooks[event] = groups
        if _event_has_script(groups, script_path):
            continue
        entry = {"type": "command", "command": command, "timeout": HOOK_TIMEOUT_S}
        if event in MATCHER_EVENTS:
            group: dict = {"matcher": "*", "hooks": [entry]}
        else:
            group = {"hooks": [entry]}
        groups.append(group)
        changed = True
    return out, changed


# --- Notify + auto-suspend policies (D-08, D-12, Pitfall 6) --------------------
# The "calm" aggregates eligible for auto-suspend — NEVER running/waiting (a long
# tool call must not be killed: Pitfall 6 / T-04-09).
_CALM_FOR_SUSPEND = (AgentStatus.READY, AgentStatus.IDLE, AgentStatus.ENDED)


def should_notify(
    old: str | None,
    new: str | None,
    window_active: bool,
    notify_ready: bool = False,
) -> bool:
    """Should arduis fire a desktop notification for this transition? (D-08)

    Fires ONLY on a transition INTO ``waiting`` while the window is UNFOCUSED — a
    re-write of ``waiting`` over ``waiting`` does not re-fire, and a focused window
    never notifies (the user is already looking). ``ready`` notifications fire only
    when ``notify_ready`` is True (the flag is default-OFF in v1 — D-08).
    """
    if window_active:
        return False
    if new == AgentStatus.WAITING.value:
        return old != AgentStatus.WAITING.value
    if new == AgentStatus.READY.value and notify_ready:
        return old != AgentStatus.READY.value
    return False


def should_autosuspend(
    aggregate: AgentStatus | None,
    calm_since: float | None,
    now: float,
    minutes: int,
) -> bool:
    """Should an idle task be auto-suspended right now? (RAM-04, D-12, Pitfall 6)

    True ONLY when the task aggregate is calm (READY/IDLE/ENDED) and has been calm
    for at least ``minutes`` minutes. ``minutes <= 0`` is OFF (the default — D-11).
    RUNNING/WAITING are NEVER suspended at any age (a 30-min tool call must survive
    — T-04-09). A None aggregate (no opinion — a fileless task) or a None
    ``calm_since`` never suspends (Pitfall 8 chain).
    """
    if minutes <= 0:
        return False
    if aggregate not in _CALM_FOR_SUSPEND:
        return False
    if calm_since is None:
        return False
    return (now - calm_since) >= minutes * 60


# --- arduis.toml config (D-11) -------------------------------------------------
@dataclass
class AttentionConfig:
    """Typed ``[attention]`` config (D-11). Safe defaults: every powerful feature OFF.

    ``auto_suspend_minutes`` 0 = OFF (the default — a process-killing feature is
    never on by accident); ``notify_ready`` / ``sound`` default OFF (D-08/D-10).
    """

    auto_suspend_minutes: int = 0
    idle_minutes: int = 10
    notify_ready: bool = False
    sound: bool = False


def _coerce_nonneg_int(value, default: int) -> int:
    """A non-negative int from a TOML value, else ``default`` (negatives → 0/off)."""
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return value if value >= 0 else 0


def _coerce_bool(value, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def load_config(path: str) -> AttentionConfig:
    """Read ``~/.config/arduis/arduis.toml`` ``[attention]`` (D-11), stdlib tomllib.

    A missing file, invalid TOML, or a wrong-typed key yields the safe default for
    that key (T-04-10: hostile/garbage values can never enable a process-killing
    feature). Read-only, mode "rb" per tomllib.
    """
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return AttentionConfig()
    section = data.get("attention")
    if not isinstance(section, dict):
        return AttentionConfig()
    defaults = AttentionConfig()
    return AttentionConfig(
        auto_suspend_minutes=_coerce_nonneg_int(
            section.get("auto_suspend_minutes"), defaults.auto_suspend_minutes
        ),
        idle_minutes=_coerce_nonneg_int(section.get("idle_minutes"), defaults.idle_minutes),
        notify_ready=_coerce_bool(section.get("notify_ready"), defaults.notify_ready),
        sound=_coerce_bool(section.get("sound"), defaults.sound),
    )
