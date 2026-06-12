---
phase: 04-attention-detection-who-s-waiting
plan: 01
subsystem: attention
tags: [claude-code-hooks, state-files, atomic-write, env-injection, vte-spawn, stdlib]

# Dependency graph
requires:
  - phase: 01-terminal
    provides: "HostRunner wrap_argv/wrap_env seam; spawn.py SHELL_ARGV/TERM_ENV list-literal posture"
provides:
  - "src/arduis/hooks/arduis_hook.py — the STATUS-01 attention sensor (stdlib-only, env-guarded, atomic, never-blocking)"
  - "Frozen event→state map: SessionStart→ready, UserPromptSubmit/PostToolUse/PostToolUseFailure→running, Notification(permission_prompt|elicitation_dialog)→waiting, Notification(idle_prompt)→ready ONLY-from-running, Stop→ready, SessionEnd→ended"
  - "State-file JSON payload contract: {state, ts(float), event, session_id, cwd, message, pid=getppid()}"
  - "spawn.build_worktree_spawn(runner, extra_env=None) — additive per-terminal env seam"
  - "Env-var contract for Plans 02/03: ARDUIS_STATE_FILE (where to write) + ARDUIS_SESSION_META (term id)"
affects: [04-02 settings-merge, 04-03 window-wiring, 05-agent-swap]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Env-guarded no-op hook: exits 0 / writes nothing unless ARDUIS_STATE_FILE is set (guaranteed invisible outside arduis)"
    - "Never-block-claude: whole body in try/except → sys.exit(0); every subprocess test asserts returncode == 0"
    - "Atomic state write: tempfile.mkstemp(prefix='.arduis-') + os.replace; failed writes unlink the temp, no droppings"
    - "Additive env seam through HostRunner (list literals, no shell-string join — T-01-01 posture preserved)"

key-files:
  created:
    - "src/arduis/hooks/__init__.py (package marker for Plan 03 installer)"
    - "src/arduis/hooks/arduis_hook.py (the injection payload)"
    - "tests/test_hook_script.py (21 subprocess round-trip tests)"
  modified:
    - "src/arduis/spawn.py (build_worktree_spawn grows extra_env)"
    - "tests/test_spawn_argv.py (4 new extra_env cases)"

key-decisions:
  - "SessionStart→ready (resolves the D-03 CONTEXT wording conflict in favour of the 04-RESEARCH verified map). Flagged for UAT in Plan 05 — a freshly spawned claude with no prompt is awaiting input; mapping to running would paint a false green until the 60s idle_prompt self-heal."
  - "State payload includes pid=os.getppid() (the claude process) as the D-04 staleness handle, in addition to the terminal pgid."
  - "Env metadata var named ARDUIS_SESSION_META per D-01 (research draft's ARDUIS_TERM_ID = same content); Plan 03 wires this name."

patterns-established:
  - "Hook = env-guarded stdlib script: no arduis import, no gi, only json/os/sys/tempfile/time — runnable under /usr/bin/env python3 anywhere"
  - "extra_env is additive and order-preserving (TERM first); TERM_ENV is never mutated (new list per call); argv is invariant under extra_env"

requirements-completed: [STATUS-01]

# Metrics
duration: 6 min
completed: 2026-06-12
---

# Phase 4 Plan 01: Hook Sensor + Env Injection Seam Summary

**The GTK-free STATUS-01 injection channel: an env-guarded stdlib-only Claude Code hook script that maps 7 hook events to the 5-state model and atomically writes per-terminal state files, plus the spawn.py `extra_env` seam through which `window.py` will inject `ARDUIS_STATE_FILE` per terminal.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-12 (worktree reset to base 59d437e)
- **Completed:** 2026-06-12
- **Tasks:** 2
- **Files modified:** 5 (3 created, 2 modified)

## Accomplishments
- Hook script (`arduis_hook.py`) is a guaranteed no-op outside arduis (no `ARDUIS_STATE_FILE` → exits 0, writes nothing) and a correct, atomic, never-blocking attention sensor inside it.
- All 7 subscribed events + the `idle_prompt` guard are pinned by 21 subprocess round-trip tests that run the script exactly as claude does (stdin JSON + inherited env).
- The cardinal-sin guard (Pitfall 2): `idle_prompt` upgrades ONLY `running → ready` and never downgrades a real `waiting`.
- `spawn.build_worktree_spawn` now accepts `extra_env` — additive, order-preserving, argv-invariant, `TERM_ENV`-immutable — the seam Plan 03 uses for per-terminal env injection.
- Full GTK-free suite green: 113 passed (baseline 88 + 21 + 4).

## Task Commits

1. **Task 1: env-guarded stdlib hook script + subprocess round-trip tests** - `0136c7e` (feat — RED+GREEN combined per plan)
2. **Task 2: spawn.py extra_env seam for per-terminal env injection** - `e37d603` (feat — RED+GREEN combined per plan)

_Note: each TDD task in this plan was specified as a single RED+GREEN unit, so each produced one feat commit (script/impl + its tests together)._

## Files Created/Modified
- `src/arduis/hooks/__init__.py` - Empty package marker so Plan 03's installer can locate the script via the package.
- `src/arduis/hooks/arduis_hook.py` - stdlib-only env-guarded hook; 7-event→5-state map; atomic `os.replace` write; `try/except → sys.exit(0)` never-block guarantee; `pid=os.getppid()`.
- `tests/test_hook_script.py` - 21 subprocess tests: env guard (D-01), full event map (D-03), payload shape (D-04), robustness (garbage/empty stdin, unwritable dir, missing parents), atomicity (no droppings, stdlib-only assertion).
- `src/arduis/spawn.py` - `build_worktree_spawn(runner, extra_env=None)`; `envv = TERM_ENV + (extra_env or [])`.
- `tests/test_spawn_argv.py` - 4 new cases: append order, argv-unchanged, `TERM_ENV` immutability, `None`==`[]`==no-arg, `ARDUIS_SESSION_META` fixture.

## Frozen Contracts for Plans 02/03

**Event → state map** (the source of truth downstream watcher/dots/notifications trust):

| Hook event | Discriminator | → state |
|---|---|---|
| `SessionStart` | — | `ready` (D-03 wording-conflict resolution; UAT-flagged) |
| `UserPromptSubmit` | — | `running` |
| `PostToolUse` | — | `running` (clears `waiting` after approval — Pitfall 3) |
| `PostToolUseFailure` | — | `running` |
| `Notification` | `permission_prompt` / `elicitation_dialog` | `waiting` |
| `Notification` | `idle_prompt` | `ready` ONLY if current file state is `running`; never touches `waiting`; no-op if no file (Pitfall 2/7) |
| `Stop` | — | `ready` |
| `SessionEnd` | — | `ended` |
| anything else | — | no-op (exit 0, no file) |

**State-file payload shape** (atomic `os.replace`, JSON):
```json
{"state": "...", "ts": <float epoch>, "event": "...",
 "session_id": "...", "cwd": "...", "message": "...", "pid": <int getppid()>}
```

**Env contract** (per agent terminal, via `extra_env`):
- `ARDUIS_STATE_FILE=<absolute path arduis composes>` — tells the hook WHERE to write (sole `waiting`-trigger trust input).
- `ARDUIS_SESSION_META=<term_id>` — terminal identity for arduis's in-memory `{path → (task_id, term_id)}` map.

## Decisions Made
- **SessionStart→ready** rather than the CONTEXT line's "SessionStart→running": adopts the 04-RESEARCH verified map. Rationale: a freshly spawned claude that received no prompt is awaiting input; mapping to running would paint a false green until the 60s idle_prompt self-heal. **Flagged for UAT (Plan 05 checklist)** so a live run can overrule.
- **pid = os.getppid()** in the payload: the hook is a child of claude, so getppid() is the claude pid — a liveness handle for the staleness sweep alongside the terminal pgid.
- **ARDUIS_SESSION_META** chosen over the research draft's `ARDUIS_TERM_ID` (same content) per locked D-01.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None. The worktree base was an ancestor of the expected base (missing the phase-04 planning commits); reset --hard to the expected base `59d437e` before starting, then executed cleanly.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The injection payload and the env seam are frozen and test-pinned. Plan 02 (settings-merge builder) can register the script's absolute path; Plan 03 (window wiring) can inject `ARDUIS_STATE_FILE`/`ARDUIS_SESSION_META` through `build_worktree_spawn(..., extra_env=...)` against the exact tested contract.
- **UAT flag carried forward:** verify SessionStart→ready (vs running) live; verify Esc-interrupt / idle_prompt self-heal timing (A2/Pitfall 7).

## Self-Check: PASSED

- All 3 created files exist on disk (`hooks/__init__.py`, `hooks/arduis_hook.py`, `tests/test_hook_script.py`).
- Both modified files present (`spawn.py`, `tests/test_spawn_argv.py`).
- Both task commits exist in git history (`0136c7e`, `e37d603`).
- Full suite green: 113 passed (baseline 88 + 21 + 4).

---
*Phase: 04-attention-detection-who-s-waiting*
*Completed: 2026-06-12*
