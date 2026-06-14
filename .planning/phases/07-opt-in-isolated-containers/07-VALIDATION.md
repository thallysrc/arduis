# Phase 07: Opt-in Isolated Containers — Validation Architecture

**Derived from:** 07-RESEARCH.md §"Validation Architecture" (nyquist_validation: ENABLED — no
`.planning/config.json` key disables it).
**Created:** 2026-06-13

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (dev MEMORY: `/tmp/arduis-venv-ab12` venv, `--system-site-packages`) |
| Baseline | 274 tests passing as of Phase 6 |
| Quick run | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_compose.py tests/test_containerstate.py -x -q` |
| Full suite | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/ -q` |
| Headless GTK | `gtk4-broadwayd :9N` (do NOT override XDG_RUNTIME_DIR) — NOT used this phase (the generation pipeline is GTK-free; window wiring is live-UAT) |
| Docker | host has 29.3.1 / compose v5.1.1 (snap on this Ubuntu host) — real `up` is a LIVE UAT item, never a unit/smoke |

## CRITICAL constraint (D-09 / Pitfall 2)

snap docker on Ubuntu **cannot read compose files outside `$HOME`**. Any test or smoke that stages a
compose file MUST stage it under `$HOME` (`tempfile.mkdtemp(dir=os.path.expanduser("~"))`), never
`/tmp`. The pytest venv living in `/tmp` is fine — only the COMPOSE FILE PATHS must be under `$HOME`.
The headless smoke (Plan 05) invokes no docker but stages under `$HOME` anyway to model the path.

## Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | Plan | File Exists? |
|--------|----------|-----------|-------------------|------|-------------|
| CONT-01 | auto-detect root compose; toggle hidden when absent/no-docker; default OFF | unit (window) | live UAT criterion 1 (toggle visibility is GTK) | 04/05 | ❌ Wave 0 (window) |
| CONT-02 | `sanitize_project_name` + stable persisted project name | unit | `pytest tests/test_compose.py -x -k sanitize` | 01 | ❌ Wave 0 |
| CONT-02/03 | parse `config --format json` published ports (verified shape) | unit (fixture JSON) | `pytest tests/test_compose.py -x -k parse` | 01 | ❌ Wave 0 |
| CONT-02/03 | override emits `ports: !override` (REPLACE, not append) | unit | `pytest tests/test_compose.py -x -k override` | 01 | ❌ Wave 0 |
| CONT-03 | offset map + socket-probe + whole-task collision bump + cap | unit (mocked socket) | `pytest tests/test_compose.py -x -k assign or probe` | 01 | ❌ Wave 0 |
| CONT-05 | config/up/down/ls argv builders (list-form, -p, base+override -f, --remove-orphans --volumes, name=arduis) | unit | `pytest tests/test_compose.py -x -k argv` | 01 | ❌ Wave 0 |
| CONT-05 | `run_compose_async` routes argv through HostRunner.wrap_argv, off the GTK loop | unit (fake runner) | `pytest tests/test_docker_service.py -x` | 03 | ❌ Wave 0 |
| CONT-03/04 | persisted port map round-trips (atomic write, multi-port, host_ip) | unit | `pytest tests/test_containerstate.py -x` | 02 | ❌ Wave 0 |
| CONT-03 | `[containers].port_offset` config read, default 1000 | unit | `pytest tests/test_containerstate.py -x -k offset` | 02 | ❌ Wave 0 |
| CONT-02/03 | END-TO-END generation on real disk: override file CONTAINS `ports: !override` + offset port, NOT base port | smoke (headless, $HOME) | `pytest tests/test_compose_smoke.py -x` | 05 | ❌ Wave 0 |
| CONT-01..05 | real `up` → single offset port → badges → `down` → crash-reconcile on REAL docker | LIVE UAT (host-only) | manual checklist (Plan 05 Task 2) | 05 | manual |

## Wave 0 Gaps (test files to create)

- [ ] `tests/test_compose.py` — CONT-01/02/03/05 (the GTK-free `compose.py`) — **Plan 01**
- [ ] `tests/fixtures/compose_config.json` — the captured `config --format json` shape (verified host
      shape: web 8080:80 + 9000 host_ip-pinned, db 5432:5432) so the parser is tested without docker — **Plan 01**
- [ ] `tests/test_containerstate.py` — CONT-04 persistence round-trip + tolerant read + offset config — **Plan 02**
- [ ] `tests/test_docker_service.py` — CONT-05 argv-routing via a fake runner (no real subprocess) — **Plan 03**
- [ ] `tests/test_compose_smoke.py` — end-to-end generation + argv + mocked-probe + state, staged under `$HOME` — **Plan 05**

## Sampling Rate

- **Per task commit:** `pytest tests/test_compose.py tests/test_containerstate.py -x -q`
- **Per wave merge:** `pytest tests/ -q` (full suite, no regression off the 274 baseline)
- **Phase gate:** full suite green AND the live UAT 5-criteria checklist passed before `/gsd-verify-work`

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

## Phase-9 packaging note

PyYAML is a NEW hard dependency (D-04, for emitting the `!override` tag). Add `python3-yaml` (Ubuntu
.deb) / `python-yaml` (Arch AUR) to the Phase-9 packaging deps. docker itself is NOT a package
dependency (the user supplies it; snap on Ubuntu, native on Arch) — arduis only shells out to it.
