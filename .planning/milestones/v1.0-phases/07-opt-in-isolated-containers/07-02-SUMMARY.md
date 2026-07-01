---
phase: 07-opt-in-isolated-containers
plan: 02
subsystem: infra
tags: [docker-compose, containers, toml, persistence, atomic-write, gtk-free]

# Dependency graph
requires:
  - phase: 03.2-projects-and-cross-repo-tasks
    provides: "task folder model (disk = source of truth, no app-state file); symlinked root docker-compose.yml in the task dir"
provides:
  - "ContainerState dataclass + GTK-free load/write of <task_dir>/arduis.container.toml (COMPOSE_PROJECT_NAME + on/off + resolved port map)"
  - "read_port_offset: [containers].port_offset user-config read (default 1000)"
  - "the durable record criterion 3 (stable ports/badges across restart) and criterion 4 (crash reconcile) depend on"
affects: [07-03, 07-04, 07-05, docker_service, window-wiring, port-badges, startup-reconciliation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Tolerant TOML read -> no-op default (corrupt/absent file == 'not isolated', never raises)"
    - "Atomic same-dir tmp + os.replace write (mirrors appconfig.write_theme), best-effort OSError-swallowing"
    - "Flat [[container.ports]] array-of-tables with explicit service key as the on-disk port-map layout"

key-files:
  created:
    - src/arduis/containerstate.py
    - tests/test_containerstate.py
  modified: []

key-decisions:
  - "On-disk layout: [container] table (project_name/enabled) + flat [[container.ports]] array-of-tables rows keyed by explicit `service`; host_ip omitted when None"
  - "ports value shape is {service: [{base:int, host:int, target:int, host_ip:str|None}]} (list-per-service, matches compose.assign_ports per the plan)"
  - "Local _fmt_scalar + hand-rolled _serialize (NOT appconfig._serialize, which imposes the user-config _SECTION_ORDER)"
  - "bool rejected for int port fields and for port_offset (bool is an int subclass but not a valid value)"

patterns-established:
  - "Per-task state file persistence: tolerant read + atomic write, disk = source of truth (extends 03.2)"

requirements-completed: [CONT-02, CONT-03, CONT-04]

# Metrics
duration: 12 min
completed: 2026-06-14
---

# Phase 07 Plan 02: Container State Persistence Summary

**GTK-free `containerstate.py` — tolerant read + atomic write of per-task `arduis.container.toml` (COMPOSE_PROJECT_NAME + on/off + resolved port map) plus the `[containers].port_offset` config read, the durable record that keeps ports/badges stable across restarts.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-06-14T12:45:00Z
- **Completed:** 2026-06-14T12:57:54Z
- **Tasks:** 2
- **Files modified:** 2 (created)

## Public Contract (what Wave 3 will call)

```python
from arduis.containerstate import (
    ContainerState, state_path,
    load_container_state, write_container_state, read_port_offset,
)

@dataclass
class ContainerState:
    project_name: str = ""          # COMPOSE_PROJECT_NAME ("arduis-<sanitized-branch>")
    enabled: bool = False           # opt-in flag (default OFF == no-op)
    ports: dict[str, list[dict]] = field(default_factory=dict)

state_path(task_dir: str) -> str                       # <task_dir>/arduis.container.toml
load_container_state(task_dir: str) -> ContainerState  # tolerant; missing/garbage -> ContainerState()
write_container_state(task_dir: str, state: ContainerState) -> None  # atomic, best-effort
read_port_offset(config_path: str) -> int              # [containers].port_offset, default 1000
```

**`ports` shape** (matches `compose.assign_ports`'s output per the plan — `{service: [{...}]}`, a
LIST of port-dicts per service so a service with multiple published ports is representable):

```python
{"web": [{"base": 8080, "host": 9080, "target": 80, "host_ip": None},
         {"base": 9000, "host": 10000, "target": 9000, "host_ip": "127.0.0.1"}],
 "db":  [{"base": 5432, "host": 6432, "target": 5432, "host_ip": None}]}
```

> Note: the orchestrator's environment note described the shape as `{service: {base,host,target,host_ip}}`
> (single dict per service). The PLAN body — `<plan_decisions>`, `<interfaces>`, and the round-trip
> `<behavior>` example (a multi-port `web` with TWO entries) — is unambiguous that it is a LIST per
> service. I implemented the list shape (the plan is authoritative). 07-01's `compose.assign_ports`
> ran in parallel and its SUMMARY was not yet on disk; Wave 3 must confirm the two agree (the plan
> instructs "if 07-01 chose a different shape, MATCH it"). If 07-01 emits a single-dict-per-service
> map, the persistence layer needs a one-line adapter — flagged here, not a blocker for this plan.

## Exact On-Disk TOML Layout

```toml
[container]
project_name = "arduis-feat-x"
enabled = true

[[container.ports]]
service = "web"
base = 8080
host = 9080
target = 80
# host_ip line omitted when None

[[container.ports]]
service = "web"
base = 9000
host = 10000
target = 9000
host_ip = "127.0.0.1"

[[container.ports]]
service = "db"
base = 5432
host = 6432
target = 5432
```

A FLAT `[[container.ports]]` array-of-tables with an explicit `service` key (multiple rows per
service allowed). `load_container_state` groups rows by `service` to rebuild the `{service: [...]}`
dict. This round-trips verbatim through `tomllib` (pinned by `test_full_state_round_trips_verbatim`).

## Accomplishments

- `ContainerState` dataclass with the no-op default (`project_name="", enabled=False, ports={}`).
- Tolerant `load_container_state`: missing file / garbage TOML / no `[container]` table / wrong-typed
  keys all yield the no-op default; malformed port rows dropped defensively, never raises (T-07-05).
- Atomic `write_container_state`: same-dir `tempfile.mkstemp` + `os.replace`, parent `makedirs`,
  best-effort OSError-swallowing — a torn write can never corrupt the record (T-07-06).
- Full-fidelity round-trip: a multi-port, `host_ip`-pinned state survives write+load equal (criterion 3).
- `read_port_offset`: `[containers].port_offset` from the user config, default 1000 on missing/garbage/
  wrong-type incl. bool (CONT-03, T-07-07).
- GTK-free (stdlib only); 22 contract tests; full suite 296 passed (274 baseline + 22 new).

## Task Commits

1. **Task 1: containerstate.py (ContainerState, load/write round-trip, read_port_offset) + tests** - `345a703` (feat)
2. **Task 2: full suite green — no regression** - (no new commit; verification only, Task 1 already contained the tests)

_Note: the plan's Task 1 was a combined TDD RED+GREEN; implementation and its tests landed in a single commit._

## Files Created/Modified

- `src/arduis/containerstate.py` - GTK-free per-task container state: `ContainerState`, `state_path`,
  `load_container_state`, `write_container_state`, `read_port_offset` + local `_fmt_scalar`/`_serialize`/`_clean_port_entry`.
- `tests/test_containerstate.py` - 22 tests: tolerant read (no-op defaults, garbage, wrong types),
  round-trip fidelity (multi-port + host_ip), atomic/best-effort write, malformed-row dropping, offset config, GTK-free.

## Decisions Made

- Wrote a LOCAL `_serialize`/`_fmt_scalar` rather than importing `appconfig._serialize` — the latter
  imposes the user-config `_SECTION_ORDER` and a different table model. `_fmt_scalar` is a faithful
  copy of appconfig's (bool-before-int ordering, `\\`/`"` escaping).
- `host_ip` line is OMITTED when None (rather than emitting `host_ip = "None"` or a null) — TOML has
  no null; absence rebuilds as `None` in `_clean_port_entry`.
- Rejected bool for the int port fields AND for `port_offset` — bool is an int subclass in Python, so
  a forged `port_offset = true` or `host = true` would otherwise pass an `isinstance(.., int)` check.

## Deviations from Plan

None - plan executed exactly as written.

The single point worth flagging is NOT a deviation but a cross-plan coordination note: the
orchestrator environment note and the PLAN body described the `ports` shape with slightly different
wording (single-dict-per-service vs list-per-service). I followed the PLAN body (list-per-service),
which is internally consistent and the authoritative spec. See "Public Contract" above.

## Issues Encountered

The worktree's merge-base did not match the expected base (`5e578ba` vs `b1a61df`); per the
`<worktree_branch_check>` instruction I ran `git reset --hard b1a61df...`. This also meant the
worktree's `.planning` lacked `07-02-PLAN.md` (and `07-01-SUMMARY.md`) — those live in the repo root
`.planning`. I read the plan from the root path. No impact on the implementation.

## Next Phase Readiness

- The durable per-task state layer is ready for Wave 3 window wiring (toggle, badges, startup scan).
- **Wave 3 must confirm** `containerstate.ports` and `compose.assign_ports` (07-01) agree on shape;
  if 07-01 emits a single-dict-per-service map, a thin adapter is needed (flagged above).
- No blockers.

## Self-Check: PASSED

- FOUND: src/arduis/containerstate.py
- FOUND: tests/test_containerstate.py
- FOUND: .planning/phases/07-opt-in-isolated-containers/07-02-SUMMARY.md
- FOUND: commit 345a703

---
*Phase: 07-opt-in-isolated-containers*
*Completed: 2026-06-14*
