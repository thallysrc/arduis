---
phase: 03-parallel-worktrees-sidebar-ram-groundwork
plan: 03
subsystem: ram-groundwork
tags: [ram, resource-monitor, caps, proc, gtk-free, green]
requires:
  - "tests/test_resource_monitor.py + tests/test_caps.py (Plan 03-01 RED contract)"
  - "arduis.session.SessionState (str-Enum .value == 'active') for caps.active_count"
provides:
  - "arduis.resource_monitor.group_rss_kb — summed process-group RSS via /proc (D-12)"
  - "arduis.resource_monitor.format_ram_kb — pt-BR RAM formatter (MB/GB, decimal comma, em-dash)"
  - "arduis.resource_monitor._pids_in_group / _rss_kb_for_pid — live pgrp walk + smaps->statm fallback"
  - "arduis.caps.ACTIVE_CAP_DEFAULT / active_count / at_cap — the cap policy (single Phase-6 source point)"
affects:
  - "Plan 03-05 (window.py): off-loop ~2s poll calls group_rss_kb; +New flow routes through at_cap"
  - "Phase 6: ACTIVE_CAP_DEFAULT is the one constant .arduis.toml will override"
tech-stack:
  added: []
  patterns:
    - "GTK-free /proc accounting with stdlib os only, no third-party process library (D-13)"
    - "per-pid reads swallow FileNotFoundError/ProcessLookupError/PermissionError -> 0 (Pitfall 3)"
    - "smaps_rollup Rss: kB -> statm resident-pages fallback (Pitfall 5)"
    - "stat comm parsed by splitting on the LAST ')' so a comm with spaces/parens still yields pgrp"
    - "pure boolean cap policy over the in-memory session store (no untrusted input in Phase 3)"
key-files:
  created:
    - src/arduis/resource_monitor.py
    - src/arduis/caps.py
  modified: []
decisions:
  - "format_ram_kb: MB = kB/1000 (decimal MB) so 312000 kB -> '312 MB'; GB = MB/1024 so 1258291 kB -> '1,2 GB' — matched to the RED contract / UI-SPEC copy."
  - "Verified via the repo .venv pytest with PYTHONPATH=src (worktree isolation: this agent's src is not the shared checkout's); contract unchanged."
metrics:
  duration: "~6 min"
  completed: "2026-06-09"
  tasks: 2
  files: 2
---

# Phase 03 Plan 03: GTK-free RAM Modules Summary

Two zero-dependency, `import gi`-free modules make the "lightweight with
first-class RAM management" promise real and testable: `resource_monitor.py`
(per-worktree RSS summed across the whole `/proc` process group, plus the pt-BR
RAM formatter) and `caps.py` (the pure active-agent cap policy and the single
interim `ACTIVE_CAP_DEFAULT` constant Phase 6 will source from `.arduis.toml`).
Both Wave-0 RED test files (`test_resource_monitor.py`, `test_caps.py`, 12 tests)
are now GREEN.

## What Was Built

- **src/arduis/resource_monitor.py** (RAM-03 / D-12/D-13/D-14):
  - `group_rss_kb(pgid)` — `sum(_rss_kb_for_pid(p) for p in _pids_in_group(pgid))`,
    the whole-group cost (D-12); calls the two helpers by module name so tests
    monkeypatch them.
  - `_rss_kb_for_pid(pid)` — `/proc/<pid>/smaps_rollup` `Rss:` line (already kB);
    on FileNotFoundError/ProcessLookupError/PermissionError falls back to
    `/proc/<pid>/statm` field 2 (resident pages) x `SC_PAGE_SIZE` // 1024; both
    fail -> 0, no traceback (Pitfalls 3/5).
  - `_pids_in_group(pgid)` — live scan of `/proc` numeric entries, parsing each
    `stat` by splitting on the LAST `)` (comm may contain spaces/parens) and
    reading pgrp at tail index 2; per-entry errors swallowed (T-03-05/T-03-06).
  - `format_ram_kb(rss_kb)` — `None` -> `"—"`; MB = kB/1000, integer MB under
    1024 MB (`"312 MB"`); else GB = MB/1024 one decimal with pt-BR comma
    (`"1,2 GB"`) (D-14 / UI-SPEC / Pitfall 7).
  - No `import gi`, no third-party process library (D-13), stdlib `os` only.
- **src/arduis/caps.py** (RAM-02 / D-15/D-16):
  - `ACTIVE_CAP_DEFAULT = 6` — the single Phase-6-sourceable constant (D-15).
  - `active_count(sessions)` — counts only `s.state.value == "active"`.
  - `at_cap(sessions, cap=ACTIVE_CAP_DEFAULT)` — `active_count >= cap`; True means
    window.py (03-05) must BLOCK the launch and prompt-to-hibernate (D-16), never
    silent-allow / create-hibernated.
  - No `import gi`; pure functions over the in-memory store.

## Verification

- `pytest tests/test_resource_monitor.py tests/test_caps.py -q` -> **12 passed**
  (GREEN), via the repo `.venv` with `PYTHONPATH=src`.
- Suite minus the two 03-02-owned RED files (`test_keymap.py`, `test_layout.py`)
  -> **37 passed**, exit 0 — nothing this plan touched regressed.
- No new dependency: `grep -rq psutil src/ pyproject.toml` exits 1.
- Both modules GTK-free: `grep -L "import gi"` lists both.
- All Task 1 + Task 2 acceptance greps pass (functions, constant, both `/proc`
  paths present, no `gi`, no rejected dep token).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] RAM conversion factors matched to the RED contract**
- **Found during:** Task 1 verification.
- **Issue:** A literal `kB/1024` MB conversion (as the action text's "Convert
  kB->MB" implies) yields `"304 MB"` for the contract input `312000 kB`, but
  `test_ram_format` asserts `"312 MB"`. The pinned contract uses decimal MB
  (`kB/1000`) for the MB display and binary GB (`MB/1024`) for the GB display
  (`1258291 kB -> "1,2 GB"`).
- **Fix:** `mb = rss_kb / 1000`; under 1024 MB show `int(mb)` MB; else
  `gb = mb / 1024` with one decimal and `.replace(".", ",")`. All `test_ram_format`
  assertions pass.
- **Files modified:** src/arduis/resource_monitor.py
- **Commit:** d6a33f2

### Tooling note (not a code deviation)

- The plan's verify commands use bare `python3 -m pytest`, but the system
  `python3` has no pytest and this agent runs in an isolated worktree whose `src`
  is not the shared checkout's. Verification ran via
  `/home/thallysrc/Projects/arduis/.venv/bin/python -m pytest` with
  `PYTHONPATH=src` so the worktree copies are the modules under test. The
  behavioral contract is unchanged (mirrors Plan 03-01's same note).

## Out-of-Scope (not failures)

- `tests/test_keymap.py` and `tests/test_layout.py` still error at collection
  (ImportError: `keymap` / `layout` absent). Those modules are Plan 03-02's
  deliverables — a parallel Wave-1 agent in a separate worktree. Their RED state
  is correct here and outside this plan's scope; the orchestrator merges the wave
  before the full suite is expected green.

## Known Stubs

None. Both modules are complete production logic; `at_cap` is the real policy and
`group_rss_kb` is the real accounting. The only deferred wiring (the off-loop
poll that calls `group_rss_kb`, and routing +New through `at_cap`) is explicitly
Plan 03-05's window.py work, as the plan's own docstrings state.

## Threat Flags

None. The two modules introduce no new trust boundary beyond the planned
kernel-`/proc` read surface already in `<threat_model>` (T-03-05/06/07/08); the
`/proc` walk only sums RSS for matching pgrp pids, reads no cmdline/env/file
contents, and swallows other-user `PermissionError`.

## Commits

- `d6a33f2`: feat(03-03): /proc process-group RSS + pt-BR RAM formatter
- `2413472`: feat(03-03): active-agent cap policy

## Self-Check: PASSED

- FOUND: src/arduis/resource_monitor.py
- FOUND: src/arduis/caps.py
- FOUND commit: d6a33f2
- FOUND commit: 2413472
