---
phase: 07-opt-in-isolated-containers
plan: 03
subsystem: infra
tags: [docker-compose, gio-subprocess, async, hostrunner, gtk]

# Dependency graph
requires:
  - phase: 07-01
    provides: compose.py list-form argv builders (up_argv/down_argv/config_argv/ls_argv/compose_argv)
  - phase: 01-terminal
    provides: HostRunner seam (wrap_argv no-op native) + git_service.run_git_async (the module cloned)
provides:
  - "docker_service.run_compose_async(argv, on_done, runner=None) -> None — the single async boundary for every docker compose call (CONT-05, D-08)"
affects: [07-04-window-wiring, 07-05-smoke]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Thin async gi service mirroring git_service.run_git_async: Gio.Subprocess + communicate_utf8_async on the GLib loop, argv via HostRunner, on_done(exit_status, stdout, stderr) on the main loop"
    - "Test gi-importing async service without a real spawn: fake runner records wrap_argv argv + monkeypatch Gio.Subprocess.new to a fake proc that fires the callback synchronously"

key-files:
  created:
    - src/arduis/docker_service.py
    - tests/test_docker_service.py
  modified: []

key-decisions:
  - "Verbatim clone of git_service.run_git_async — only the function name changes (run_git_async -> run_compose_async); no streaming, no timeout, no JSON parsing (window's on_done owns json.loads)"
  - "Full test strategy used (not the minimum fallback): fake runner pins seam routing AND a Gio.Subprocess.new stub pins the on_done (exit_status, stdout, stderr) shape — no real process spawned"

patterns-established:
  - "Pattern: a fake proc with synchronous communicate_utf8_async(cb) + communicate_utf8_finish returning canned (True, out, err) lets a gi async service be unit-tested deterministically"

requirements-completed: [CONT-02, CONT-05]

# Metrics
duration: 2min
completed: 2026-06-14
---

# Phase 7 Plan 03: docker_service async compose wrapper Summary

**`docker_service.run_compose_async` — a verbatim clone of `git_service.run_git_async` that routes compose argv through the HostRunner seam and runs `docker compose` off the GTK loop via `Gio.Subprocess` + `communicate_utf8_async`, the single non-blocking async boundary every Wave-3 compose call uses, pinned by 2 spawn-free routing tests.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-06-14T13:00:23Z
- **Completed:** 2026-06-14T13:01:51Z
- **Tasks:** 2 (Task 2 verification-only, no commit)
- **Files modified:** 2 created

## Public Contract (for Wave 3 — window.py)

The exact signature Wave 3 calls — identical shape to `git_service.run_git_async`:

| Function | Signature | Notes |
|----------|-----------|-------|
| `run_compose_async` | `(argv: list[str], on_done, runner: HostRunner \| None = None) -> None` | `argv` is a list-form compose argv from `compose.py` (`up_argv`/`down_argv`/`config_argv`/`ls_argv`/`compose_argv`). Routes through `(runner or HostRunner()).wrap_argv(argv)` (no-op native → identity, new list). Runs via `Gio.Subprocess.new(wrapped, STDOUT_PIPE\|STDERR_PIPE)` + `communicate_utf8_async`. |

**Callback contract (pinned):** `on_done(exit_status: int, stdout: str, stderr: str)` — fires on the **GLib main loop**, so it is safe to mutate widgets / `SessionStore` and `json.loads` the output directly from it (the window's `on_done` does `json.loads` for `config`/`ls`; `stdout`/`stderr` are never `None` — coerced to `""`).

**Env for `COMPOSE_PROJECT_NAME` (D-03):** `run_compose_async` mirrors `git_service` exactly and takes **no env parameter** — `Gio.Subprocess.new` inherits the parent environment. Wave 3 must set `COMPOSE_PROJECT_NAME` per task before the call (e.g. via the parent process environment / a launcher), OR a follow-up may extend the wrapper to a `Gio.SubprocessLauncher` with `setenv` if per-call env isolation is required. The current clone keeps the git_service surface; passing `-p <project>` on the argv (already done by `compose_argv`) is the primary isolation mechanism, with `COMPOSE_PROJECT_NAME` as the env reinforcement.

**Runner:** `HostRunner` is the single host-execution funnel — no-op on native (returns `list(argv)`); the v2 Flatpak path (DIST-01) prepends `flatpak-spawn --host` in `wrap_argv` only. Inject a fake runner in tests.

## Accomplishments
- `docker_service.py` — the single new gi-importing service for Phase 7, a faithful clone of `git_service.run_git_async` (same imports, same `gi.require_version("Gtk","4.0")`, same `Gio.Subprocess.new(... STDOUT_PIPE|STDERR_PIPE)` + `communicate_utf8_async` + `_cb` firing `on_done(exit_status, stdout, stderr)`).
- Non-blocking by construction (T-07-09 / Pitfall 3): no `subprocess.run`, no `threading`, no `asyncio` in code — `docker compose up -d` image pulls never freeze the GTK loop.
- argv crosses the HostRunner seam (T-07-08): always a Python list, never a shell string.
- 2 spawn-free unit tests: a fake runner pins seam routing with the exact argv; a `Gio.Subprocess.new` stub + fake proc pin the wrapped argv + `STDOUT_PIPE|STDERR_PIPE` flags and the decoded `(0, "out", "")` on_done shape. A second test proves the default real `HostRunner` no-op identity wrap.
- Full suite **323 passed** (321 baseline + 2 new), zero regressions; `docker_service` imports cleanly with `run_compose_async` present.

## Task Commits

1. **Task 1: clone git_service into docker_service.run_compose_async + argv-routing test** - `ee3b8f1` (feat)
2. **Task 2: full suite green + import sanity** - no file change (verification-only; 323 passed, import-ok)

## Files Created/Modified
- `src/arduis/docker_service.py` - thin async compose wrapper (`run_compose_async`), the single new gi-importing service this phase
- `tests/test_docker_service.py` - 2 tests: seam routing + on_done shape via fake runner & Gio.Subprocess.new stub (no real spawn), and default-HostRunner identity wrap

## Decisions Made
- **Verbatim clone, not invention:** `run_compose_async` is `run_git_async` with the function renamed. No streaming, no timeout, no JSON parsing added — `compose.py` owns argv, `window.py` owns `json.loads`.
- **Full test strategy used:** the planned Gio monkeypatch was NOT awkward in this venv, so the full strategy (seam routing + on_done shape via `Gio.Subprocess.new` stub) was used — the minimum-fallback (wrap_argv-only) was not needed.

## Deviations from Plan

None - plan executed exactly as written.

The plan's "minimum acceptable test" fallback (assert only `wrap_argv`) was available but unnecessary: monkeypatching `docker_service.Gio.Subprocess.new` worked cleanly, so the full strategy (routing + on_done shape, no real spawn) was implemented as the primary path.

## Issues Encountered
None - the clone matched git_service exactly; PyGObject/Gtk available in the venv (system-site-packages); all verifications green on first run.

## Threat Coverage
- **T-07-08 (Tampering/EoP):** argv stays a Python list end-to-end (compose.py → run_compose_async → Gio.Subprocess.new); no shell, no `shell=True`, nothing joined. Pinned by the routing test asserting the exact list crosses the seam.
- **T-07-09 (DoS self):** no blocking call in code — `Gio.Subprocess` + `communicate_utf8_async` only. Verified by grep (the only `subprocess.run/threading/asyncio` tokens are in the docstring documenting their deliberate absence).

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Wave 3 (`07-04 window.py`) can wire `run_compose_async` for config/up/down/ls with the signature pinned above; the `on_done(rc, out, err)` callback runs on the GLib loop so it may `json.loads` and mutate widgets directly.
- Open item for Wave 3: decide whether `COMPOSE_PROJECT_NAME` is set via the parent environment or whether the wrapper needs a `Gio.SubprocessLauncher.setenv` extension for per-call env isolation (the `-p <project>` argv from `compose_argv` is already the primary isolation key).
- No blockers.

## Self-Check: PASSED

- FOUND: src/arduis/docker_service.py
- FOUND: tests/test_docker_service.py
- FOUND: commit ee3b8f1

---
*Phase: 07-opt-in-isolated-containers*
*Completed: 2026-06-14*
