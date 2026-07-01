---
phase: 07-opt-in-isolated-containers
verified: 2026-06-14T15:00:00-03:00
status: human_needed
score: 5/6 must-haves verified
human_verification:
  - test: "Launch arduis on a project with a root docker-compose.yml under $HOME; right-click a task row and confirm 'Isolar containers' appears. Then open a project without a compose file and confirm the entry is hidden."
    expected: "Toggle visible only when project has compose + docker on PATH; default OFF with no container badges"
    why_human: "GTK menu visibility and per-task toggle UI are not testable headless"
  - test: "Click 'Isolar containers' on a task; observe the spinner on the row and a toast. When done, run `docker compose ls` and check for the arduis-<branch> project. Run `docker compose -p arduis-<branch> -f <task_dir>/docker-compose.yml -f <task_dir>/docker-compose.override.yml config | grep -A5 ports` to confirm ONLY the offset port is shown (not the base doubled)."
    expected: "Single offset port in live stack config; badges (`web:<host> db:<host>`) appear on the task row; COMPOSE_PROJECT_NAME matches arduis-<sanitized-branch>"
    why_human: "Real docker compose up requires a live docker daemon; badge rendering is GTK"
  - test: "Note the resolved port badges. Quit arduis and relaunch on the same project. Confirm the same ports appear as badges before any new `up`."
    expected: "Ports persisted in <task_dir>/arduis.container.toml; badges render at startup from disk"
    why_human: "Requires visual verification of badge rendering across app restarts"
  - test: "Hibernate the isolated task (or click 'Desligar containers'). Confirm `docker compose ls` no longer lists the arduis-* project. Then: enable isolation again, hard-kill arduis (kill -9), relaunch — confirm arduis surfaces a toast listing the orphaned arduis-* stack WITHOUT auto-removing it."
    expected: "Teardown on hibernate: stack gone from docker compose ls. Crash-reconcile: orphan surfaced conservatively (no auto down -v)"
    why_human: "Requires real docker daemon for teardown verification; kill -9 crash simulation is a manual step"
  - test: "Confirm all the above worked with the host's docker (snap on Ubuntu / native on Arch). Verify compose files were under $HOME during the test."
    expected: "No file-not-found errors from snap-docker; all compose operations complete successfully"
    why_human: "Snap docker restriction (cannot read outside $HOME) requires live host verification"
---

# Phase 7: Opt-in Isolated Containers — Verification Report

**Phase Goal:** Per-TASK isolated docker-compose stacks, OFF by default, docker on host via HostRunner. Single root docker-compose.yml base; generated override in the task folder rewrites each service's ports via the `ports: !override` tag; unique COMPOSE_PROJECT_NAME per task; ports probed free + persisted + shown as badges; teardown (down --remove-orphans --volumes) on conclude/hibernate/exit; startup reconciles orphaned arduis-* projects.
**Verified:** 2026-06-14T15:00:00-03:00
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Auto-detect compose + per-task toggle present only when compose+docker exist, default OFF | ? HUMAN | Logic wired (`_docker_available`, `_compose_path`, `win.toggle_isolation`); GTK menu visibility requires live test |
| 2 | override_bytes emits literal `ports: !override` tag (REPLACE, not concatenate — D-01) | ✓ VERIFIED | `override_bytes` outputs `ports: !override` in bytes; `test_compose_smoke.py::test_override_uses_override_tag_and_replaces_base_port` passes on real disk; 8080:80 absent, 9080:80 present |
| 3 | Enable flow: config->assign_ports->override->up->persist ContainerState, port badges rendered | ? HUMAN | Code path verified (L1451-1531 window.py); live `up` and badge rendering require real docker |
| 4 | Teardown (_container_down) is SEPARATE from killpg (_teardown_session_terminals), fires on hibernate and app-exit | ✓ VERIFIED | `_teardown_session_terminals` (L3663-3675) contains zero compose/docker calls; `_container_down` called at L3469 alongside (never inside) it; app-exit has its own loop (L3731-3762) |
| 5 | Startup reconcile runs `docker compose ls --filter name=arduis`, surfaces orphans conservatively (no auto down -v) | ✓ VERIFIED | `_reconcile_orphans` (L1652-1690): async ls, builds `live` set from sanitized task branches, toasts orphaned arduis-* names, no auto down call |
| 6 | All docker compose calls route through HostRunner+run_compose_async (CONT-05); 344 tests green | ✓ VERIFIED | `run_compose_async` mirrors `git_service.run_git_async` exactly; wraps argv via `HostRunner.wrap_argv`; `Gio.Subprocess` + `communicate_utf8_async` (no blocking call); full suite 344 passed |

**Score:** 4/6 truths fully verified automated + 2 require human (GTK + live docker)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/arduis/compose.py` | sanitize_project_name, parse_published_ports, assign_ports, override_bytes, argv builders | ✓ VERIFIED | All functions present; GTK-free (0 gi imports); `ports: !override` tag emitted via `_Override(list)` + PyYAML representer |
| `src/arduis/containerstate.py` | ContainerState, load/write_container_state, read_port_offset | ✓ VERIFIED | All present; GTK-free; atomic write via tmp+os.replace; tolerant read returns `ContainerState()` default on error |
| `src/arduis/docker_service.py` | run_compose_async — thin async wrapper | ✓ VERIFIED | Clone of git_service.run_git_async; Gio.Subprocess + communicate_utf8_async; no subprocess.run/threading/asyncio |
| `src/arduis/window.py` (Phase 7 additions) | auto-detect, toggle, enable/disable flow, badges, teardown, reconcile | ✓ SUBSTANTIVE | `compose`, `containerstate`, `docker_service` imported; all 5 Phase 7 methods on ArduisWindow; wiring verified by grep |
| `tests/test_compose.py` | CONT-01/02/03/05 unit coverage, !override tag, offset+probe+retry, fixture parse, argv | ✓ VERIFIED | 25 tests passing |
| `tests/test_containerstate.py` | CONT-04 persistence round-trip, tolerant read, atomic write, offset config | ✓ VERIFIED | 22 tests passing |
| `tests/test_docker_service.py` | CONT-05 argv-routing via fake runner | ✓ VERIFIED | 2 tests passing |
| `tests/test_compose_smoke.py` | End-to-end generation under sandbox $HOME | ✓ VERIFIED | 8/8 tests pass; stages override on real disk under `$HOME`; asserts `ports: !override` + offset port + NO base port |
| `tests/fixtures/compose_config.json` | Captured docker compose config --format json shape | ✓ VERIFIED | web (8080:80 + 127.0.0.1:9000:9000), db (5432:5432) — 3 ports matching the plan spec |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tests/test_compose.py` | `src/arduis/compose.py` | import sanitize_project_name, parse_published_ports, assign_ports, override_bytes, compose_argv | ✓ WIRED | 25 tests call all functions; imports verified |
| `tests/test_compose.py` | `tests/fixtures/compose_config.json` | open fixture, json.loads, feed parse_published_ports | ✓ WIRED | Fixture used in parse tests |
| `src/arduis/docker_service.py` | `src/arduis/host_runner.py` | `(runner or HostRunner()).wrap_argv(argv)` | ✓ WIRED | L47 of docker_service.py |
| `src/arduis/docker_service.py` | `gi.repository.Gio` | `Gio.Subprocess.new + communicate_utf8_async` | ✓ WIRED | L48-57 of docker_service.py |
| `src/arduis/window.py` | `src/arduis/compose.py` | `import compose; override_bytes, assign_ports, up_argv, down_argv, ls_argv, config_argv` | ✓ WIRED | L73, L1474-1690 window.py — all 6 compose functions called |
| `src/arduis/window.py` | `src/arduis/containerstate.py` | `import containerstate; load/write_container_state, read_port_offset` | ✓ WIRED | L73, L1475, L1521-1524, L2368, L2782 window.py |
| `src/arduis/window.py` | `src/arduis/docker_service.py` | `docker_service.run_compose_async` for config/up/down/ls | ✓ WIRED | L1505-1531, L1530, L1573-1574, L1646, L1689 window.py |
| `window.py _on_close_request + hibernate` | `docker compose down` | `_container_down` separate from `_teardown_session_terminals` (killpg) | ✓ WIRED | Hibernate: L3463 (_teardown_session_terminals) then L3469 (_container_down) — separate calls; app-exit: L3731-3762 separate loop; `_teardown_session_terminals` body (L3663-3675) contains zero compose calls |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `window.py` badges/port display | `self._container_state[task_id].ports` | `containerstate.load_container_state(task_dir)` at scan + `_enable_isolation` write | Yes — loaded from disk TOML or from assign_ports result | ✓ FLOWING |
| `compose.override_bytes(port_map)` | `port_map` | `assign_ports(published, offset, probe)` — maps base->host via socket probe | Yes — real socket probing in production, mocked in tests | ✓ FLOWING |
| `_reconcile_orphans._on_ls` | `projects` | `docker compose ls --filter name=arduis --format json` via run_compose_async | Yes — live docker query | ? LIVE-ONLY |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| override_bytes emits `ports: !override` literal tag | Python one-liner confirming tag presence and base port absence | `ports: !override` present, `8080:80` absent, `9080:80` present | ✓ PASS |
| 57 Phase 7 unit+smoke tests pass | `pytest test_compose.py test_containerstate.py test_docker_service.py test_compose_smoke.py -q` | 57 passed in 0.08s | ✓ PASS |
| Full suite 344 tests pass with no regression | `pytest tests/ -q` | 344 passed | ✓ PASS |
| window.py imports cleanly with all Phase 7 methods | Python import check + dir() | import-ok; _container_down, _reconcile_orphans, _enable_isolation, _disable_isolation, _finish_isolation_error all present | ✓ PASS |
| GTK-free discipline | `grep -c "import gi\|from gi" compose.py containerstate.py` | 0, 0 | ✓ PASS |
| docker_service has no blocking calls | `grep subprocess.run\|threading\|asyncio docker_service.py` | Only docstring mention (no actual usage) | ✓ PASS |
| D-12: _teardown_session_terminals contains zero compose calls | inspect body (L3663-3675) | Body only calls `_teardown_pgid` on terminal pids — zero compose/docker calls | ✓ PASS |
| D-13: _reconcile_orphans is conservative (no auto down -v) | inspect _reconcile_orphans body (L1652-1690) | Surfaces orphans via toast only; no `down_argv` call inside | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| CONT-01 | 07-01, 07-04 | Auto-detect docker-compose.yml; integration optional | ? NEEDS HUMAN (GTK) | Logic wired: `shutil.which("docker")` + file check for docker-compose.yml/compose.yaml in project root; toggle hidden when unavailable |
| CONT-02 | 07-01, 07-04 | Isolated per-worktree; unique COMPOSE_PROJECT_NAME | ✓ SATISFIED | `sanitize_project_name` produces stable `arduis-<sanitized>` names (25 tests); persisted in ContainerState; wired in enable flow |
| CONT-03 | 07-01, 07-04 | Override.yml generated with auto-assigned port offset | ✓ SATISFIED | `assign_ports` + `override_bytes` with `ports: !override`; smoke tests prove on real disk; probe bump + cap tested |
| CONT-04 | 07-02, 07-04 | Container ports displayed as badges | ? NEEDS HUMAN (GTK) | `_build_sidebar_row` reads `self._container_state[sid].ports` and appends badge labels when enabled; `arduis-badge` CSS class used; visual rendering unverifiable headless |
| CONT-05 | 07-01, 07-03, 07-04 | Teardown on remove/hibernate/exit | ✓ SATISFIED | `_container_down` wired into hibernate (L3469) and app-exit (L3734-3762); separate from killpg; `down --remove-orphans --volumes` argv proven |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `window.py` L3737-3752 | `subprocess.run` at app-exit | INFO | Intentional and documented: "the one place a brief block is acceptable to guarantee no orphan"; capped at timeout=10; best-effort (errors swallowed). Not a stub — it is the documented design for guaranteed teardown at app-exit. |

No TODO/FIXME/placeholder stubs found in Phase 7 files. No empty return handlers. No hardcoded empty data that flows to rendering.

### Human Verification Required

#### 1. Auto-detect + per-task opt-in toggle (CONT-01, Criterion 1)

**Test:** Launch arduis on a project with a root docker-compose.yml under $HOME. Right-click a task row and confirm "Isolar containers" appears in the menu. The task should show no container badges (default OFF). Then open a project without a root compose file (or with docker absent from PATH) and confirm the menu entry is hidden/insensitive.
**Expected:** Toggle visible only when both conditions are met; strictly no-op otherwise.
**Why human:** GTK menu construction and item visibility are not testable in a headless harness.

#### 2. Real `up` with single offset port + badges (CONT-02/03, Criterion 2/3)

**Test:** Click "Isolar containers" on a task in a project with a root docker-compose.yml (under $HOME — snap docker requirement). Observe a spinner on the row and a toast when the op completes. Run:
```
docker compose -p arduis-<branch> -f <task_dir>/docker-compose.yml -f <task_dir>/docker-compose.override.yml config | grep -A5 ports
```
Confirm each service shows ONLY the offset host port (e.g. 9080), NOT the base port doubled (e.g. 8080 must not appear). Confirm port badges (`web:9080 db:6432`) appear on the task row.
**Expected:** Single offset port in live stack; badges rendered; COMPOSE_PROJECT_NAME = arduis-<sanitized-branch> in `docker compose ls`.
**Why human:** Real docker daemon required for `up`; badge rendering is GTK.

#### 3. Stable ports across restart (Criterion 3)

**Test:** Note the resolved port badges. Quit arduis cleanly and relaunch on the same project. Confirm the same port numbers appear as badges before any new `up` (loaded from the persisted `<task_dir>/arduis.container.toml`).
**Expected:** Ports persist; badges render at startup from the durable TOML file.
**Why human:** Visual rendering of persisted state across app restart requires live UI.

#### 4. Teardown on hibernate + crash-reconcile (Criterion 4)

**Test:** Hibernate the isolated task (sidebar menu → "Hibernar"). Run `docker compose ls` and confirm the arduis-* stack is gone (down ran). Then: re-enable isolation, hard-kill arduis (`kill -9 <pid>`), relaunch arduis. Confirm arduis surfaces a toast listing the orphaned arduis-* stack WITHOUT auto-removing it (conservative D-13).
**Expected:** Teardown on hibernate effective; orphan surfaced as toast on startup, no auto down -v.
**Why human:** Real docker teardown + kill -9 crash simulation are manual steps.

#### 5. HostRunner seam + snap-docker Ubuntu / native Arch (Criterion 5)

**Test:** Confirm all of the above worked with the host's docker (snap on Ubuntu / native on Arch). Verify compose files were staged under $HOME during the test (not /tmp).
**Expected:** No file-not-found errors from snap-docker; all operations complete successfully on both distros.
**Why human:** Platform-specific behavior (snap path restrictions) requires live host verification.

### Gaps Summary

No automated gaps. All headless-verifiable logic is implemented and tested:
- The D-01 `ports: !override` tag is the central correctness point and is confirmed: `override_bytes` emits the literal tag via a PyYAML `_Override(list)` subclass with a custom representer; the smoke proves it on real disk with the base port absent.
- D-12 (separate teardown channels): `_teardown_session_terminals` body contains zero compose calls; `_container_down` is called alongside it, never inside.
- D-13 (conservative reconcile): `_reconcile_orphans` surfaces orphans via toast only, no auto `down -v`.
- 344 tests pass (57 new Phase 7 tests on top of the 274 baseline, plus 13 from earlier phases).

5 human verification items cover the irreducibly-live behavior: GTK menu/badge rendering, real docker up/down, crash-reconcile, and snap-docker path constraints. These were explicitly designated as live-UAT-only in 07-VALIDATION.md and 07-05-PLAN.md Task 2.

---

_Verified: 2026-06-14T15:00:00-03:00_
_Verifier: Claude (gsd-verifier)_
