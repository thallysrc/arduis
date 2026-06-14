---
phase: 07-opt-in-isolated-containers
plan: 04
subsystem: ui
tags: [docker-compose, gtk, toast, badges, teardown, async, window]

# Dependency graph
requires:
  - phase: 07-01
    provides: "compose.py — sanitize_project_name, parse_published_ports, assign_ports, override_bytes, config/up/down/ls argv builders, PortAssignmentError"
  - phase: 07-02
    provides: "containerstate.py — ContainerState, load/write_container_state, read_port_offset"
  - phase: 07-03
    provides: "docker_service.run_compose_async(argv, on_done, runner=) — single async compose boundary"
  - phase: 03.3-topbar-chips
    provides: "header pack_start chip bar (left free at pack_end / title region for Phase-7 UI)"
provides:
  - "Per-task default-OFF 'Isolar/Desligar containers' toggle in the sidebar row context menu (win.toggle_isolation), present only when a root compose + docker exist (CONT-01, D-11)"
  - "Full async opt-in flow: config -> parse -> assign_ports -> ALWAYS write override -> up -d -> persist ContainerState + render <service>:<host> port badges (CONT-02/03/04)"
  - "Partial-failure self-clean: non-zero up fires down, leaves toggle OFF, persists enabled=False; PortAssignmentError + malformed config JSON surfaced via toast (Pitfall 5, T-07-11)"
  - "Disable: down --remove-orphans --volumes, enabled=False but KEEPS the port map (stable re-enable)"
  - "Container teardown as a SEPARATE channel from killpg (Pitfall 7): _container_down on hibernate (async) + app-exit (sync, capped) (CONT-05, D-12)"
  - "Conservative startup orphan reconcile: docker compose ls --filter name=arduis surfaces orphaned arduis-* stacks via toast, no auto down -v (D-13)"
affects: [07-05-smoke, 09-packaging]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Glue-only window wiring: a GTK file orchestrating three GTK-free/async modules (compose/containerstate/docker_service) via nested on_done closures on the GLib loop"
    - "Adw.ToastOverlay wrapping the ToolbarView as the window's single content child; self._toast(msg) the entry point (D-10)"
    - "Two-channel teardown: killpg (process-group, agent terminals) and docker compose down (daemon-owned containers) NEVER conflated (Pitfall 7)"
    - "App-exit is the one place a brief synchronous subprocess.run(down, timeout) is acceptable to guarantee no orphan; hibernate stays async"

key-files:
  created: []
  modified:
    - src/arduis/window.py

key-decisions:
  - "Row builder is _make_row (not _build_sidebar_row as the plan named it); badges + spinner appended into the existing vertical text box under the sub-line"
  - "Busy state shows an insensitive informational 'Containers… (em andamento)' menu line rather than omitting the entry, so the user sees WHY the toggle is unavailable"
  - "App-exit teardown uses synchronous subprocess.run(timeout=10) (separate loop from killpg) because async on_done may never fire as the window closes immediately (D-12, T-07-14)"

patterns-established:
  - "Pattern: per-task container isolation toggle backed by a stateful win.toggle_isolation(task_id) action + an in-memory ContainerState map keyed by task_id, loaded at startup + create-finalize"

requirements-completed: [CONT-01, CONT-02, CONT-03, CONT-04, CONT-05]

# Metrics
duration: 18 min
completed: 2026-06-14
---

# Phase 7 Plan 04: Window Container Wiring Summary

**Per-task opt-in docker-compose isolation wired into `window.py` — a default-OFF row-menu toggle that runs the full async chain (config -> offset-probe ports -> `!override` override -> `up -d`), persists `ContainerState`, renders `<service>:<host>` port badges with a toast+spinner, tears containers down on hibernate/app-exit as a channel separate from killpg, and conservatively reconciles orphaned `arduis-*` stacks at startup.**

## Performance

- **Duration:** ~18 min
- **Started:** 2026-06-14T13:40:00Z
- **Completed:** 2026-06-14T13:58:23Z
- **Tasks:** 4 (Task 4 verification-only, no commit)
- **Files modified:** 1 (`src/arduis/window.py`)

## Accomplishments

- **Auto-detect + toggle (CONT-01, D-11):** `_resolve_project` computes `self._docker_available = shutil.which("docker") is not None` and `self._compose_path` (root `docker-compose.yml` then `compose.yaml`). The row-menu "Isolar containers"/"Desligar containers" entry (`_append_isolation_menu_item`) appears ONLY when both are present (`_isolation_available()`), default OFF, backed by the new stateful `win.toggle_isolation(task_id)` action.
- **Full async enable flow (CONT-02/03):** `_enable_isolation` → `run_compose_async(config_argv)` → `json.loads` → `parse_published_ports` → `assign_ports(offset)` → ALWAYS write `override_bytes(port_map)` (tmp+`os.replace`) → `run_compose_async(up_argv)` → persist `ContainerState(enabled=True, ports)` + toast + badges.
- **Partial-failure cleanup (Pitfall 5, T-07-11):** non-zero `up` fires a best-effort `down`, leaves the toggle OFF, persists enabled=False; `PortAssignmentError` and malformed config JSON route to `_finish_isolation_error` (toast) — never an unhandled exception on the GLib loop.
- **Disable (CONT-04):** `_disable_isolation` runs `down --remove-orphans --volumes`, sets enabled=False but KEEPS `state.ports` for stable re-enable; badges clear.
- **Teardown channel (CONT-05, D-12, Pitfall 7):** `_container_down` is a separate method from `_teardown_session_terminals` (killpg). Called ALONGSIDE killpg in `_hibernate_task` (async, then flips state OFF keeping ports) and in `_on_close_request` (a separate loop using brief synchronous `subprocess.run(timeout=10)`).
- **Startup reconcile (D-13):** `_reconcile_orphans` at the end of `_scan_tasks` runs `ls_argv()` and toasts orphaned `arduis-*` projects not matching a live task (conservative — no auto down -v).
- **State loaded at startup (CONT-04):** `_scan_tasks` and `_finalize_task_creation` populate `self._container_state[task_id]` via `load_container_state` so badges render before any `up`.
- **Toast infra (D-10):** the `Adw.ToolbarView` is wrapped in an `Adw.ToastOverlay` (the window's single content child); `self._toast(msg)` is the entry point.
- Full suite **336 passed** (baseline 336), zero regressions; `import arduis.window` clean under broadway/headless.

## New methods + call sites

| Method | Role |
|--------|------|
| `_isolation_available()` | gate: root compose + docker on PATH (CONT-01) |
| `_append_isolation_menu_item(menu, sid)` | appends the toggle/busy entry to a row menu |
| `_on_toggle_isolation_action(action, param)` | `win.toggle_isolation(s)` → `_on_toggle_isolation` |
| `_on_toggle_isolation(task_id)` | dispatch enable vs disable from persisted state |
| `_enable_isolation(task)` | async config→assign→override→up→persist |
| `_disable_isolation(task)` | async down, KEEP ports |
| `_finish_isolation_error(task, summary, detail)` | failure tail (clear busy, persist OFF, toast) |
| `_write_override(path, bytes)` | tmp+os.replace override write |
| `_ports_summary(port_map)` | `<service>:<host>` toast text |
| `_container_down(task)` | async teardown channel (Pitfall 7) |
| `_reconcile_orphans()` | startup `ls` orphan surface (D-13) |
| `_toast(msg)` | Adw.Toast entry point (D-10) |

**Call sites wired:** `_resolve_project` (auto-detect), `_make_row` (badges + spinner), `_make_row_menu_cb` (toggle entry), `_install_row_actions` (`win.toggle_isolation`), `_scan_tasks` (state load + reconcile), `_finalize_task_creation` (state load), `_hibernate_task` (`_container_down` + state flip), `_on_close_request` (sync app-exit teardown).

**Menu label strings:** `"Isolar containers"` (OFF) / `"Desligar containers"` (ON) / `"Containers… (em andamento)"` (busy, informational).
**Badge format:** `<service>:<host>` (e.g. `web:9080 db:6432`), `arduis-badge` CSS class.

## Files Created/Modified

- `src/arduis/window.py` — imports `compose`/`containerstate`/`docker_service`; 4 new `__init__` attrs (`_compose_path`, `_docker_available`, `_container_state`, `_compose_busy`) + `_compose_pending`; ToastOverlay wrap; auto-detect; the 12 new methods above; badges/spinner in `_make_row`; teardown + reconcile wiring.

## Decisions Made

- **Row builder name:** the plan referenced `_build_sidebar_row`; the actual method is `_make_row`. Badges/spinner were appended into its existing `text` vertical box (under the sub-line). No signature change.
- **Busy menu entry:** rather than omit the toggle while a compose op is in flight, an insensitive `"Containers… (em andamento)"` line is shown so the user sees the reason.
- **App-exit synchronous teardown:** `_on_close_request` uses `subprocess.run(down, timeout=10)` because the window closes immediately and async `on_done` may never fire — a brief block is acceptable per CLAUDE.md to guarantee no orphan. Hibernate stays async.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Plan referenced `_build_sidebar_row`; the real method is `_make_row`**
- **Found during:** Task 1
- **Issue:** The plan's `<interfaces>` named the row builder `_build_sidebar_row` (~1218). The actual window.py method is `_make_row` (the `_build_sidebar_row` name does not exist).
- **Fix:** Added the badge/spinner rendering into `_make_row`'s existing vertical `text` box under the sub-line, exactly where the plan intended (RAM sub-line host).
- **Files modified:** src/arduis/window.py
- **Verification:** parse-ok + import-ok; 336 passed.
- **Committed in:** de87253 (Task 1 commit)

**2. [Rule 2 - Missing Critical] `_compose_pending` map for the config→up handoff**
- **Found during:** Task 2
- **Issue:** The plan said to "stash project + port_map on a pending dict keyed by task_id" but did not declare the attribute. Without it the `_on_up` closure could not recover the assigned port_map on a clean run.
- **Fix:** Added `self._compose_pending: dict[str, dict] = {}` in `__init__` (Task 1) and used it across the config→up step; cleared in `_on_up` and `_finish_isolation_error`. (The port_map is also captured in the closure, so this is belt-and-suspenders for the persist step.)
- **Files modified:** src/arduis/window.py
- **Verification:** parse-ok + import-ok; 336 passed.
- **Committed in:** de87253 / f77c2ea

---

**Total deviations:** 2 auto-fixed (1 blocking — method-name mismatch, 1 missing-critical — pending map).
**Impact on plan:** None on behavior — every planned method, decision, and threat mitigation is implemented. The method-name fix is the only structural correction; the pending map is a one-attribute addition the plan's text implied.

## Issues Encountered

None — every verification was green on first run. The Wave-1/2/3 contracts matched their SUMMARYs exactly (port_map list-per-service shape, `run_compose_async(argv, on_done, runner=)` signature, `override_bytes({})` empty-services override).

## Notes for the Plan-05 headless smoke

- The enable flow's success path mutates the store + writes `arduis.container.toml` + `docker-compose.override.yml` in the task dir — the smoke must stage fixtures under `$HOME` (D-09) and assert argv/bytes/state, NOT spin a real stack.
- `run_compose_async` is the single seam; the smoke can inject a fake runner + stub `Gio.Subprocess.new` (per 07-03's test pattern) to fire `on_done` synchronously and assert the exact argv chain: `config_argv` → `up_argv` (success) or `up_argv` → `down_argv` (failure cleanup).
- `_on_close_request`'s app-exit teardown is the one SYNCHRONOUS `subprocess.run` path — the smoke should mock `subprocess.run` to assert the `down_argv` argv without spawning docker.
- Toast/badges/spinner have no collected unit test (window.py render is untested by prior-phase convention); they are live-UAT (07-05 smoke + manual).

## Next Phase Readiness

- The opt-in isolated-containers feature is fully wired in window.py; ready for the Wave-4 headless smoke (07-05) + host-only live UAT.
- Open item carried from 07-03: `COMPOSE_PROJECT_NAME` env is not set per-call (the `-p <project>` argv from `compose_argv` is the primary isolation key, as 07-03 noted). If live UAT shows per-call env isolation is needed, extend `docker_service` to a `Gio.SubprocessLauncher.setenv`.
- No blockers.

## Self-Check: PASSED

- FOUND: src/arduis/window.py (modified)
- FOUND: commit de87253 (Task 1)
- FOUND: commit f77c2ea (Task 2)
- FOUND: commit 15c54a1 (Task 3)

---
*Phase: 07-opt-in-isolated-containers*
*Completed: 2026-06-14*
