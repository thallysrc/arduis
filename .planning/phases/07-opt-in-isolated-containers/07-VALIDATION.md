# Phase 07: Opt-in Isolated Containers — Validation Architecture

---
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-13
validated: 2026-06-15
---

**Derived from:** 07-RESEARCH.md §"Validation Architecture" (nyquist_validation: ENABLED — no
`.planning/config.json` key disables it).
**Created:** 2026-06-13
**Validated:** 2026-06-15 (post-execution reconcile)

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (venv at `/tmp/arduis-venv`, `--system-site-packages`) |
| Baseline | 274 tests passing as of Phase 6 |
| Phase 7 tests | 57 new tests (25 + 8 + 22 + 2) |
| Full suite at gate | 344 passed |
| Quick run | `/tmp/arduis-venv/bin/python -m pytest tests/test_compose.py tests/test_containerstate.py -x -q` |
| Full suite | `/tmp/arduis-venv/bin/python -m pytest tests/ -q` |
| Headless GTK | `gtk4-broadwayd :9N` (do NOT override XDG_RUNTIME_DIR) — NOT used this phase (generation pipeline is GTK-free; window wiring is live-UAT) |
| Docker | host has 29.3.1 / compose v5.1.1 (snap on this Ubuntu host) — real `up` is a LIVE UAT item, never a unit/smoke |

## CRITICAL constraint (D-09 / Pitfall 2)

snap docker on Ubuntu **cannot read compose files outside `$HOME`**. Any test or smoke that stages a
compose file MUST stage it under `$HOME` (`tempfile.mkdtemp(dir=os.path.expanduser("~"))`), never
`/tmp`. The pytest venv living in `/tmp` is fine — only the COMPOSE FILE PATHS must be under `$HOME`.
The headless smoke (Plan 05) invokes no docker but stages under `$HOME` anyway to model the path.

## Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Plan | File Exists? | Status |
|--------|----------|-----------|-------------------|------|-------------|--------|
| CONT-01 | auto-detect root compose; toggle hidden when absent/no-docker; default OFF | manual UAT | live UAT criterion 1 (toggle visibility is GTK) | 04/05 | manual | ✅ manual-only (GTK) |
| CONT-02 | `sanitize_project_name` + stable persisted project name | unit (5 tests) | `pytest tests/test_compose.py -k sanitize` | 01 | ✅ exists | ✅ green |
| CONT-02/03 | parse `config --format json` published ports (verified shape) | unit (4 tests) | `pytest tests/test_compose.py -k parse` | 01 | ✅ exists | ✅ green |
| CONT-02/03 | override emits `ports: !override` (REPLACE, not append) | unit (6 tests) | `pytest tests/test_compose.py -k override` | 01 | ✅ exists | ✅ green |
| CONT-03 | offset map + socket-probe + whole-task collision bump + cap | unit (4 tests) | `pytest tests/test_compose.py -k assign or probe` | 01 | ✅ exists | ✅ green |
| CONT-05 | config/up/down/ls argv builders (list-form, -p, base+override -f, --remove-orphans --volumes, name=arduis) | unit (6 tests) | `pytest tests/test_compose.py -k argv` | 01 | ✅ exists | ✅ green |
| CONT-05 | `run_compose_async` routes argv through HostRunner.wrap_argv, off the GTK loop | unit/fake runner (2 tests) | `pytest tests/test_docker_service.py` | 03 | ✅ exists | ✅ green |
| CONT-03/04 | persisted port map round-trips (atomic write, multi-port, host_ip) | unit (22 tests) | `pytest tests/test_containerstate.py` | 02 | ✅ exists | ✅ green |
| CONT-03 | `[containers].port_offset` config read, default 1000 | unit (included above) | `pytest tests/test_containerstate.py -k offset` | 02 | ✅ exists | ✅ green |
| CONT-02/03 | END-TO-END generation on real disk: override CONTAINS `ports: !override` + offset port, NOT base port | smoke/headless/$HOME (8 tests) | `pytest tests/test_compose_smoke.py` | 05 | ✅ exists | ✅ green |
| CONT-01..05 | real `up` → single offset port → badges → `down` → crash-reconcile on REAL docker | LIVE UAT (host-only) | manual checklist (Plan 05 Task 2) | 05 | manual | manual-only (live docker) |

## Wave 0 Status — ALL COMPLETE

- [x] `tests/test_compose.py` — CONT-01/02/03/05 (the GTK-free `compose.py`) — 25 tests passing — **Plan 01**
- [x] `tests/fixtures/compose_config.json` — the captured `config --format json` shape (web 8080:80 + 9000 host_ip-pinned, db 5432:5432) — **Plan 01**
- [x] `tests/test_containerstate.py` — CONT-04 persistence round-trip + tolerant read + offset config — 22 tests passing — **Plan 02**
- [x] `tests/test_docker_service.py` — CONT-05 argv-routing via a fake runner (no real subprocess) — 2 tests passing — **Plan 03**
- [x] `tests/test_compose_smoke.py` — end-to-end generation + argv + mocked-probe + state, staged under `$HOME` — 8 tests passing — **Plan 05**

## Sampling Rate

- **Per task commit:** `pytest tests/test_compose.py tests/test_containerstate.py -x -q`
- **Per wave merge:** `pytest tests/ -q` (full suite, no regression off the 274 baseline)
- **Phase gate:** full suite green (344 passed) AND live UAT 5-criteria checklist accepted by PO — COMPLETE

## Honesty: what a smoke CAN and CANNOT prove

- **CAN (headless, no docker):** every generation/parse/probe/persist unit — the `ports: !override`
  tag in the emitted YAML bytes (on real disk), `sanitize_project_name`, the offset map + mocked-socket
  probe bump + cap, the captured-JSON parse, the ContainerState atomic round-trip, every compose argv
  shape, and `run_compose_async`'s HostRunner routing. This is the BULK of the real logic and is fully
  testable headless under a sandbox `$HOME`.
- **CAN (host + real docker, LIVE UAT only):** a real `up` showing the single remapped (not doubled)
  port via `docker compose config`, badges rendering, `down` leaving `docker compose ls` empty, and a
  hard-kill leaving an orphan the startup reconcile surfaces. Needs a real image pull + free port range
  → host-only, NOT CI-portable, MUST run under `$HOME` on snap docker.
- **CANNOT (headless broadway GTK):** the GTK smoke pattern from Phases 4–6 proves UI wiring but cannot
  bring up real containers in a hermetic harness. Real-container behavior is therefore a LIVE UAT
  checklist (Plan 05 Task 2) — matching the project's headless-smoke + human-verify pattern.

## Validation Sign-Off

- [x] All headless-automatable requirements have passing tests
- [x] No automated requirement left with `❌` / TBD / placeholder test ID
- [x] Manual-only items (GTK rendering, live docker, snap path constraints) correctly classified as manual — NOT blocking nyquist_compliant
- [x] Full suite (344 tests) green with no regression off the 274-test Phase 6 baseline
- [x] VERIFICATION.md independently confirmed all artifacts and behavioral spot-checks on 2026-06-14

**Approval:** validated 2026-06-15 (post-execution reconcile)

## Phase-9 packaging note

PyYAML is a NEW hard dependency (D-04, for emitting the `!override` tag). Add `python3-yaml` (Ubuntu
.deb) / `python-yaml` (Arch AUR) to the Phase-9 packaging deps. docker itself is NOT a package
dependency (the user supplies it; snap on Ubuntu, native on Arch) — arduis only shells out to it.

---

## Validation Audit 2026-06-15

### Metrics

| Metric | Count |
|--------|-------|
| Automated requirements audited | 10 |
| Gaps found (missing coverage) | 0 |
| Gaps resolved (tests exist and pass) | 10 |
| Escalated to manual-only | 2 (CONT-01 toggle visibility, live docker UAT) |

### Audit Note

This document was a stale plan-time draft (`status: draft, nyquist_compliant: false`) written on
2026-06-13 before any code existed. All Wave 0 test file targets (marked `❌`) have since been
implemented and confirmed green as of the VERIFICATION.md produced on 2026-06-14.

**Genuinely automated (57 tests, 0.08 s, no docker daemon required):**

- `tests/test_compose.py` (25 tests): `sanitize_project_name` correctness and edge cases; `parse_published_ports` against a fixture JSON capturing the real `docker compose config --format json` shape; `override_bytes` emitting the literal `ports: !override` YAML tag (REPLACE semantics, not concatenate); `assign_ports` offset + mocked-socket free-probe + whole-task collision bump + retry cap; all five argv builders (`compose_argv`, `up_argv`, `down_argv`, `config_argv`, `ls_argv`) verifying list form, `-p`, `-f` base+override, `--remove-orphans --volumes`, and `name=arduis` filter.
- `tests/test_containerstate.py` (22 tests): `ContainerState` round-trip (atomic write via `tmp+os.replace`, multi-port, `host_ip`, tolerant read returning default on missing/garbage TOML); `read_port_offset` default 1000, config value, wrong-type fallback; GTK-free discipline verified.
- `tests/test_docker_service.py` (2 tests): `run_compose_async` routes argv through a fake `HostRunner.wrap_argv` seam and calls `communicate_utf8_async` on `Gio.Subprocess` — no blocking `subprocess.run`, no threads, no asyncio.
- `tests/test_compose_smoke.py` (8 tests): end-to-end generation on real disk under a sandbox `$HOME`; asserts the override file contains the literal `ports: !override` tag and the offset port (`9080:80`), and that the base port (`8080:80`) is absent; full argv shapes; project name sanitization; probe collision bump and cap; ContainerState disk round-trip and missing-state no-op.

**Correctly manual-only (does NOT block nyquist_compliant):**

- GTK menu and badge rendering: `Adw.ToolbarView` item visibility and per-task toggle cannot be asserted headless without a real display and real GTK event loop.
- Live docker daemon execution: `docker compose up/down/ls` with a real image, real ports, and snap-docker `$HOME` path constraints requires the host's docker engine — not CI-portable and explicitly designated as LIVE UAT in the plan.

The `nyquist_compliant: true` assertion reflects that every headless-automatable requirement has a
passing test and that the two manual-only items are correctly classified as irreducibly live — not
as gaps.
