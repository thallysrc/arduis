---
phase: 04-attention-detection-who-s-waiting
plan: 02
subsystem: attention
tags: [hooks, state-machine, claude-code, tomllib, libnotify-policy, ram-autosuspend]

# Dependency graph
requires:
  - phase: 03.2-projects-and-cross-repo-tasks
    provides: TerminalRecord/Task session model (kind field, repo_name last-field house rule)
provides:
  - "attention.py — GTK-free Phase-4 policy brain: 5-state AgentStatus, state-file path/read/wipe helpers, effective_status (time/pid), aggregate_task (per-task), settings-merge builder, hook install path/source helpers, should_notify, should_autosuspend, AttentionConfig/load_config"
  - "TerminalRecord.status / .status_ts trailing fields (STATUS-02 store)"
affects: [04-03, 04-04, window.py status wiring, hook install consent UX, RAM-04 auto-suspend tick]

# Tech tracking
tech-stack:
  added: [tomllib (stdlib, read-only arduis.toml), importlib.resources (packaged hook-script read)]
  patterns:
    - "All Phase-4 decision rules are pure GTK-free functions (mirrors layout.py/caps.py) — provable without a display; effective_status/aggregate_task take now+pid_alive from the caller (no clock, no /proc)"
    - "Path-traversal hardening: allowlist + '..'-collapse sanitize (mirrors worktree.sanitize_branch_for_dir); state_file_path leaf's dirname == status dir always"
    - "Settings merge is deepcopy + append-only + idempotent + dedupe-by-script-path (the user's load-bearing ~/.claude/settings.json is never mutated destructively)"

key-files:
  created:
    - src/arduis/attention.py
    - tests/test_attention.py
  modified:
    - src/arduis/session.py
    - tests/test_session.py

key-decisions:
  - "idle_minutes default 10 (claude's own idle_prompt fires ~60s; 10 min is a visibly-distinct 'you forgot me' tier) — UAT-revisitable"
  - "RUNNING_STALE_CEILING_S = 2h: a running older than this (no events) degrades to ready on the sweep; generous so a long tool call is never wrongly degraded (Pitfall 6/7)"
  - "auto_suspend_minutes default 0 = OFF; negative values coerced to 0 (a process-killing feature is never on by accident — T-04-10)"
  - "declined-consent marker file ~/.local/share/arduis/hooks_declined (touch on decline; tomllib is read-only so a marker avoids a TOML-writer dep — D-02)"
  - "hook_script_source uses importlib.resources('arduis.hooks') lazily; its content test is skipif-guarded because src/arduis/hooks/arduis_hook.py is owned by the parallel wave-1 plan 04-01"

patterns-established:
  - "Pure-policy GTK-free module per phase, fully unit-tested before any window.py wiring"
  - "New dataclass fields appended LAST with a docstring note (positional-construction invariant)"

requirements-completed: [STATUS-01, STATUS-02, STATUS-03, RAM-04]

# Metrics
duration: 12 min
completed: 2026-06-12
---

# Phase 4 Plan 02: Attention Policy Brain Summary

**GTK-free `attention.py` — 5-state model, traversal-safe state-file plumbing, time/pid-based effective status, per-task aggregation, an additive/idempotent `~/.claude/settings.json` merge builder, notify + auto-suspend policies, and a `tomllib` config reader — every Phase-4 decision rule as a pure unit-tested function.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 3 (all TDD, RED+GREEN combined per task)
- **Files modified:** 4 (2 created, 2 extended)
- **Tests:** suite 88 → 141 passing (+53 new), 1 skipped (hook-source content test, awaiting 04-01 merge)

## Accomplishments

- **State model + plumbing (Task 1):** `AgentStatus` 5-state Enum; `status_dir` (XDG_RUNTIME_DIR + `~/.cache` fallback); `sanitize_term_id`/`state_file_path` (traversal-safe flat leaf, T-04-06); `clear_status_dir` (unlink plain files only, no recursion/symlink-follow, T-04-11); `read_state` (None on any parse failure, T-04-07); `effective_status` (idle computed, waiting never auto-degraded, dead-pid→ended, stale-running→ready); `aggregate_task` (agent-only precedence, fileless = no opinion).
- **Settings merge (Task 2):** `HOOK_EVENTS`/`MATCHER_EVENTS`, `hook_command` (absolute tilde/var-free exec form), `install_target_path`, `declined_marker_path`, `hook_script_source`, `is_installed`, `merged_settings` (deepcopy, additive, idempotent, dedupe-by-path, matcher `*` only on tool events, pinned timeout 5 — T-04-08).
- **Policies + config + store (Task 3):** `should_notify` (→waiting while unfocused; ready behind default-off flag), `should_autosuspend` (calm-only past threshold; never running/waiting; None never suspends — T-04-09), `AttentionConfig`/`load_config` (stdlib `tomllib`, per-key type fallback — T-04-10), `TerminalRecord.status`/`.status_ts` appended LAST.

## Public Surface (the contract Plans 03/04 wire against)

```python
class AgentStatus(str, Enum): RUNNING WAITING READY IDLE ENDED  # .value = "running" etc.

@dataclass class StateDoc: state:str; ts:float; event:str; message:str; pid:int|None

RUNNING_STALE_CEILING_S = 7200          # 2h generous ceiling (UAT-revisitable)
HOOK_EVENTS = (SessionStart, UserPromptSubmit, Notification, PostToolUse,
               PostToolUseFailure, Stop, SessionEnd)
MATCHER_EVENTS = (PostToolUse, PostToolUseFailure)
HOOK_TIMEOUT_S = 5

status_dir(env: dict|None=None) -> str
sanitize_term_id(term_id: str) -> str
state_file_path(dir: str, term_id: str) -> str
clear_status_dir(dir: str) -> None
read_state(path: str) -> StateDoc | None
effective_status(doc, now, pid_alive, idle_after_s, stale_running_s=7200) -> AgentStatus
aggregate_task(records) -> AgentStatus | None   # agent-only; precedence waiting>running>ready>idle>ended

hook_command(script_path: str) -> str           # "/usr/bin/env python3 <abs>"
install_target_path(home: str) -> str            # ~/.local/share/arduis/hooks/arduis_status_hook.py
declined_marker_path(home: str) -> str           # ~/.local/share/arduis/hooks_declined
hook_script_source() -> str                      # reads packaged arduis.hooks/arduis_hook.py (04-01)
is_installed(settings: dict, script_path: str) -> bool
merged_settings(settings: dict, script_path: str) -> tuple[dict, bool]  # (new, changed)

should_notify(old, new, window_active, notify_ready=False) -> bool
should_autosuspend(aggregate, calm_since, now, minutes) -> bool

@dataclass class AttentionConfig:
    auto_suspend_minutes:int=0; idle_minutes:int=10; notify_ready:bool=False; sound:bool=False
load_config(path: str) -> AttentionConfig
```

### Config keys / defaults (`~/.config/arduis/arduis.toml`, `[attention]`)
| Key | Default | Meaning |
|-----|---------|---------|
| `auto_suspend_minutes` | `0` (OFF) | minutes of calm before auto-suspend; 0/absent/negative = off |
| `idle_minutes` | `10` | ready→idle threshold (the grey "you forgot me" tier) |
| `notify_ready` | `false` | also notify on `ready` (default off — D-08) |
| `sound` | `false` | optional sound on notify (default off — D-10) |

### Chosen thresholds (UAT-revisitable)
- **idle_minutes = 10** — visibly distinct from claude's own ~60s idle_prompt.
- **RUNNING_STALE_CEILING_S = 2h** — a running with no events past this degrades to ready; generous so a long tool call is never wrongly killed.
- **declined-marker path** = `~/.local/share/arduis/hooks_declined` (presence suppresses the consent dialog).

## Task Commits

1. **Task 1: state model, paths/read/wipe, effective status, aggregation** - `197ee33` (feat)
2. **Task 2: additive settings merge builder + hook install helpers** - `52d3941` (feat)
3. **Task 3: notify/auto-suspend policies, arduis.toml config, TerminalRecord fields** - `10ebae2` (feat)

_TDD RED+GREEN were committed together per task (the tests and the minimal implementation that passes them landed atomically); no separate failing-test commit since the module is new and the suite must stay green for the parallel wave-merge gate._

## Files Created/Modified
- `src/arduis/attention.py` — the full GTK-free policy surface (created).
- `tests/test_attention.py` — 38 cases covering state map, paths, reads, effective/aggregate status, merge (rich fixture), notify, suspend, config (created).
- `src/arduis/session.py` — `TerminalRecord.status`/`.status_ts` appended last (modified).
- `tests/test_session.py` — positional-construction + serialization cases for the new fields (modified).

## Decisions Made
See `key-decisions` frontmatter. All adopt 04-CONTEXT/RESEARCH defaults (user AFK); no architectural deviations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Corrected an over-strict sanitizer test expectation**
- **Found during:** Task 1
- **Issue:** The drafted `test_sanitize_never_empty` asserted `sanitize_term_id("..") == "term"`, but the implementation collapses `..`→`-` (a safe flat leaf) *before* the empty-fallback check, returning `-`. The literal expectation was wrong; the security invariant (never `.`/`..`/empty/separator) holds either way.
- **Fix:** Rewrote the test to assert the actual invariant across several hostile inputs (`..`, ``, `///`, `../..`, `.`) plus the empty→`"term"` fallback, rather than a brittle exact-string match.
- **Files modified:** tests/test_attention.py
- **Verification:** `pytest tests/test_attention.py -q` green; `state_file_path`'s hostile-id test confirms `dirname == dir`.
- **Committed in:** `197ee33` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug, in a test assertion). **Impact:** none on the production surface — the sanitizer behavior was already correct and threat-safe; only the test's literal expectation was tightened to the real invariant. No scope creep.

## Issues Encountered
None. `src/arduis/hooks/arduis_hook.py` does not exist in this worktree (owned by parallel wave-1 plan 04-01); the single `hook_script_source` content test is `pytest.mark.skipif`-guarded as the plan specifies and will run unskipped after the wave merge.

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- The complete tested policy contract is ready for Plans 03/04 to wire into `window.py`: state-dir init + wipe, `Gio.FileMonitor`, dot/badge refresh, libnotify on `should_notify`, and the auto-suspend tick on `should_autosuspend`.
- After the wave merge, the `hook_script_source` content test should be re-run unskipped (04-01 lands `arduis.hooks/arduis_hook.py`); the orchestrator's full-suite gate covers this.
- Cardinal-sin rules pinned by tests: waiting never silently downgraded; running/waiting never auto-suspended; user `~/.claude/settings.json` never mutated destructively.

---
*Phase: 04-attention-detection-who-s-waiting*
*Completed: 2026-06-12*

## Self-Check: PASSED

- All created/modified files present on disk: `src/arduis/attention.py`, `tests/test_attention.py`, `src/arduis/session.py`, `tests/test_session.py`, `04-02-SUMMARY.md`.
- All task commits reachable: `197ee33`, `52d3941`, `10ebae2`.
- Full suite: 141 passed, 1 skipped (baseline was 88) — `grep -L "import gi"` lists both modules; `AGENT_FEED: bytes` count == 1 (untouched).
