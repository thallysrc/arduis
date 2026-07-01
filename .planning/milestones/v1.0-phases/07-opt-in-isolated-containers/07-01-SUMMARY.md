---
phase: 07-opt-in-isolated-containers
plan: 01
subsystem: infra
tags: [docker-compose, pyyaml, ports, override, sanitize, gtk-free, tdd]

# Dependency graph
requires:
  - phase: 03.2-multi-repo-tasks
    provides: symlink_plan mirrors the root docker-compose.yml into the task folder (A1 CONFIRMED)
provides:
  - "compose.sanitize_project_name(branch) -> 'arduis-<sanitized>' isolation key (CONT-02)"
  - "compose.parse_published_ports(model) -> ordered list[PublishedPort] from `docker compose config --format json` (CONT-02/03)"
  - "compose.assign_ports(published, offset, probe) -> clustered offset port map with collision retry (CONT-03)"
  - "compose.override_bytes(port_map) -> docker-compose.override.yml bytes with the load-bearing `ports: !override` tag (CONT-02/03, D-01)"
  - "compose.compose_argv/up_argv/down_argv/config_argv/ls_argv list-form argv builders (CONT-05)"
  - "compose.port_free(host_port) strict socket probe (D-06)"
affects: [07-02-containerstate, 07-03-docker-service, 07-04-window-wiring, 07-05-smoke, 09-packaging]

# Tech tracking
tech-stack:
  added: [PyYAML 6.0.1 (python3-yaml / python-yaml — add to Phase-9 dep list per D-04)]
  patterns:
    - "GTK-free translation layer: pure os/re/socket/yaml, no gi — unit-testable headless (D-08)"
    - "list-form argv contract through HostRunner, never a shell string (mirrors git_service/worktree, T-07-01)"
    - "PyYAML custom local-tag emission via _Override(list) subclass + add_representer('!override', ...)"
    - "injected probe(host_port:int)->bool for socket-free unit tests"

key-files:
  created:
    - src/arduis/compose.py
    - tests/test_compose.py
    - tests/fixtures/compose_config.json
  modified: []

key-decisions:
  - "port_map shape is {service: [{base,host,target,host_ip}]} — a per-service LIST so multi-port services (e.g. web with two ports) rebuild their whole ports list in override_bytes"
  - "PyYAML 6.0.1 confirmed available in the venv; no hand-rolled fallback needed"
  - "Tasks 1 and 2 collapsed into one feat commit (whole cohesive module + test file written together); Task 3 is verification-only with no file change"

patterns-established:
  - "Pattern: emit Compose `!override` via an _Override(list) subclass + yaml.add_representer returning represent_sequence('!override', ...)"
  - "Pattern: clustered whole-task offset bump (offset*(attempt+1)) capped at 10 -> PortAssignmentError"

requirements-completed: [CONT-01, CONT-02, CONT-03, CONT-05]

# Metrics
duration: 3min
completed: 2026-06-14
---

# Phase 7 Plan 01: GTK-free compose translation layer Summary

**GTK-free `compose.py` — branch->project-name sanitizer, the authoritative `docker compose config --format json` port reader, deterministic offset+probe port assignment with clustered collision-retry, and the load-bearing `ports: !override` override-byte generator (REPLACE not append), all pinned by 25 docker-free unit tests.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-14T12:55:42Z
- **Completed:** 2026-06-14T12:58:15Z
- **Tasks:** 3
- **Files modified:** 3 created

## Public Contract (for Wave 2/3)

The exact signatures Wave 2 (`containerstate.py`, `docker_service.py`) and Wave 3 (`window.py`) call:

| Function | Signature | Notes |
|----------|-----------|-------|
| `sanitize_project_name` | `(branch: str) -> str` | Returns `arduis-<sanitized>` (lowercase a-z0-9_-, dash-runs collapsed, leading/trailing `-_` stripped); empty -> `arduis-task`. Matches `^arduis-[a-z0-9][a-z0-9_-]*$`. |
| `parse_published_ports` | `(config_model: dict) -> list[PublishedPort]` | Pure (caller does IO + `json.loads`). Ordered (services dict order, ports list order). Skips expose-only ports (no `published`). Tolerant — never raises on missing keys. |
| `assign_ports` | `(published, offset, probe=port_free) -> dict` | Returns `{service: [{"base","host","target","host_ip"}, ...]}`. Clustered whole-task offset bump on any collision, capped at 10 -> `PortAssignmentError`. `[] -> {}`. |
| `override_bytes` | `(port_map: dict) -> bytes` | Emits `docker-compose.override.yml` with literal `ports: !override`. `{} -> services: {}` minimal override. |
| `port_free` | `(host_port: int, host: str = "127.0.0.1") -> bool` | STRICT (`SO_REUSEADDR` off). Default injected probe. |
| `compose_argv` | `(project, task_dir, *cmd) -> list[str]` | `["docker","compose","-p",project,"-f",<task_dir>/docker-compose.yml,"-f",<task_dir>/docker-compose.override.yml,*cmd]` |
| `up_argv` | `(project, task_dir) -> list[str]` | adds `up -d` |
| `down_argv` | `(project, task_dir) -> list[str]` | adds `down --remove-orphans --volumes` |
| `config_argv` | `(task_dir) -> list[str]` | `docker compose -f <task_dir>/docker-compose.yml config --format json` — base ONLY, no `-p`/override |
| `ls_argv` | `() -> list[str]` | `docker compose ls --all --filter name=arduis --format json` |

**Injected-probe contract (pinned):** `probe(host_port: int) -> bool` — ONE positional int arg, returns True when free. Host is fixed to `127.0.0.1` inside the default `port_free`. The 07-05 smoke's mock (False@1000 / True@2000) and this signature MUST agree.

**Data types:**
- `@dataclass PublishedPort: service: str; target: int; published: int; host_ip: str | None = None`
- `class PortAssignmentError(Exception)` — raised after 10 clustered offset attempts all collide (T-07-03 cap).

**port_map shape (chosen — containerstate + window MUST agree):** `{service: [{"base": int, "host": int, "target": int, "host_ip": str | None}, ...]}`. A per-service LIST so a multi-port service (e.g. `web` with `80` and `9000`) rebuilds its whole ports list. `web -> [{base:8080,host:9080,target:80,host_ip:None}, {base:9000,host:10000,target:9000,host_ip:"127.0.0.1"}]`.

## PyYAML availability

`/tmp/arduis-venv-ab12/bin/python -c "import yaml; print(yaml.__version__)"` -> **6.0.1**. Available as the planner verified; the documented hand-rolled fallback was NOT needed. PyYAML must be added to the Phase-9 packaging dep list (`python3-yaml` Ubuntu / `python-yaml` Arch) per D-04.

## `!override`-tag emission detail

```python
class _Override(list): ...
def _repr_override(dumper, data):
    return dumper.represent_sequence("!override", list(data))
yaml.add_representer(_Override, _repr_override)
```

`override_bytes` wraps each service's port-string list in `_Override(...)`, so `yaml.dump(...)` emits the literal local tag. Verified emission:

```yaml
services:
  web:
    ports: !override
    - 9080:80
    - 127.0.0.1:10000:9000
  db:
    ports: !override
    - 6432:5432
```

The base ports (`8080`, `5432:5432`) never appear (Pitfall-1 trap closed). Round-trip is proven in `test_override_bytes_round_trips_through_yaml_with_override_tag` by registering a `!override` constructor on `yaml.SafeLoader` and asserting the parsed ports equal the offset list — proving the tag is a real YAML local tag, not inline text.

## Accomplishments
- GTK-free `compose.py` (imports `os`/`re`/`socket`/`yaml` only — grep `import gi|from gi` == 0).
- The load-bearing `ports: !override` REPLACE generator with an explicit no-base-port assertion.
- Deterministic clustered offset + injected-probe assignment with 10-attempt cap.
- Authoritative `config --format json` reader against a captured host-shape fixture (no docker invoked).
- Every `docker compose` argv builder (config/up/down/ls) as list-form argv.
- 25 new unit tests; full suite 299 passed (274 baseline + 25), zero regressions.

## Task Commits

1. **Task 1 + Task 2: full module + tests** - `6147084` (feat)
2. **Task 3: full-suite verification** - no file change (verification-only step; 299 passed)

_Note: the planned per-task TDD split collapsed into one commit — see Deviations._

## Files Created/Modified
- `src/arduis/compose.py` - GTK-free translation layer (sanitize, parse, assign, override, argv, probe)
- `tests/test_compose.py` - 25 tests: sanitize/parse/argv (Task 1), assign_ports + override !override/round-trip/no-base-port (Task 2), GTK-free guard
- `tests/fixtures/compose_config.json` - captured `docker compose config --format json` shape (web with host_ip-pinned 9000, db 5432)

## Decisions Made
- **port_map per-service-list shape** so multi-port services round-trip cleanly through `override_bytes`. Pinned in the contract above for Wave 2/3 agreement.
- PyYAML used directly (6.0.1 present); no fallback emitter written.

## Deviations from Plan

### Process deviations

**1. [Rule 3 - Blocking/process] Tasks 1 and 2 committed as a single `feat` commit**
- **Found during:** Task 2
- **Issue:** The plan's TDD framing intended separate RED/GREEN commits per task. The whole module (`compose.py`) is one cohesive ~300-line file and the test file covers both tasks; the Task-1 implementation already wrote `assign_ports`/`override_bytes` to keep the module importable and internally consistent. Splitting after the fact would have required an artificial empty re-commit.
- **Fix:** Implemented and tested both tasks in commit `6147084`. Task 1's verification (`-k "sanitize or parse or argv"`) passed before, and the full `test_compose.py` (Task 2) passed after, with no working-tree changes remaining for a second commit.
- **Files modified:** src/arduis/compose.py, tests/test_compose.py, tests/fixtures/compose_config.json
- **Verification:** Task-1 filter 14 passed; full test_compose.py 25 passed; full suite 299 passed.
- **Committed in:** 6147084

---

**Total deviations:** 1 (process — commit granularity).
**Impact on plan:** None on correctness or contract — every planned behavior is implemented, tested, and committed. Only the commit count differs from the TDD ideal (1 feat commit instead of ~4 test/feat commits).

## Issues Encountered
None - the implementation matched the plan/CONTEXT defaults; PyYAML present as expected; all verifications green on first run.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Wave 2 (`07-02 containerstate.py`, `07-03 docker_service.py`) can consume the contract above. The port_map shape and the `probe(host_port:int)->bool` signature are pinned — containerstate persistence and the 07-05 smoke mock must match exactly.
- Wave 3 (`07-04 window.py`) wiring is pure glue over these functions.
- Phase-9 packaging: add PyYAML (`python3-yaml` / `python-yaml`) to the dep list (D-04).
- No blockers.

## Self-Check: PASSED

- FOUND: src/arduis/compose.py
- FOUND: tests/test_compose.py
- FOUND: tests/fixtures/compose_config.json
- FOUND: .planning/phases/07-opt-in-isolated-containers/07-01-SUMMARY.md
- FOUND: commit 6147084

---
*Phase: 07-opt-in-isolated-containers*
*Completed: 2026-06-14*
