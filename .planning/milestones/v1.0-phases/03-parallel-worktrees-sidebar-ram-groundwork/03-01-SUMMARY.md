---
phase: 03-parallel-worktrees-sidebar-ram-groundwork
plan: 01
subsystem: testing
tags: [tdd, red, layout, keymap, resource-monitor, caps, gtk-free]
requires:
  - "arduis.session.WorktreeSession / SessionState (Phase 2 domain layer)"
provides:
  - "tests/test_layout.py — layout-tree contract (split/close-collapse/zoom/preset-MRU/visibility-decoupling/focus-or-swap)"
  - "tests/test_keymap.py — prefix-dispatch contract (h/j/k/l, next/prev, digit jump, unknown->None)"
  - "tests/test_resource_monitor.py — /proc RSS contract (group sum, paren-comm parse, smaps->statm fallback, missing-pid->0, pt-BR format)"
  - "tests/test_caps.py — cap-policy contract (ACTIVE_CAP_DEFAULT=6, active_count, at_cap >= boundary)"
affects:
  - "Plan 03-02 (GREEN: layout.py + keymap.py)"
  - "Plan 03-03 (GREEN: resource_monitor.py + caps.py)"
tech-stack:
  added: []
  patterns:
    - "RED-first TDD: failing tests pin the module contract before any implementation"
    - "GTK-free domain modules asserted via *_is_gtk_free source check (mirrors test_session.py)"
    - "monkeypatched /proc — internal helpers + path-dispatching builtins.open fake; never the real /proc"
    - "host-independent statm expectation computed from os.sysconf('SC_PAGE_SIZE')"
key-files:
  created:
    - tests/test_layout.py
    - tests/test_keymap.py
    - tests/test_resource_monitor.py
    - tests/test_caps.py
  modified: []
decisions:
  - "Verified tests via the repo .venv (pytest 9.0.3) instead of bare python3 — the system python3 has no pytest; the contract under test is unchanged (deviation Rule 3)."
metrics:
  duration: "~5 min"
  completed: "2026-06-09"
  tasks: 2
  files: 4
---

# Phase 03 Plan 01: RED Test Scaffolds Summary

Four failing pytest files pin the exact behavioral contracts for the phase's
four GTK-free modules (`layout.py`, `keymap.py`, `resource_monitor.py`,
`caps.py`) before any implementation exists, forming the Nyquist sampling
surface the GREEN plans (03-02, 03-03) must satisfy.

## What Was Built

- **tests/test_layout.py** (LAYOUT-01, PAR-01/D-02, PAR-02/D-06): `test_split_focused`,
  `test_close_collapses` (degenerate-parent collapse, Pitfall 2), `test_zoom_roundtrip`,
  `test_preset_subset` (grid2x2 picks 4 from MRU; columns honors count),
  `test_visibility_decoupled` (D-02: active without a visible pane),
  `test_focus_or_swap` (D-06 pure decision), `test_layout_is_gtk_free`.
- **tests/test_keymap.py** (PAR-03/D-09/D-10): prefix constants (`Ctrl`+`space`),
  h/j/k/l direction dispatch, n/p worktree cycle, digit jump (`"3"->("jump",3)`),
  unknown key -> `None` (split/zoom chords deferred to Phase 5), `test_keymap_is_gtk_free`.
- **tests/test_resource_monitor.py** (RAM-03/D-12/D-14): `test_group_rss_sum`
  (group RSS via monkeypatched `_pids_in_group`/`_rss_kb_for_pid`),
  `test_stat_paren_comm` (split on the LAST `)` so a comm with spaces/parens still
  yields pgrp), `test_rss_fallback` (smaps_rollup raises -> statm field 2 ×
  `SC_PAGE_SIZE` // 1024), `test_rss_missing_pid` (vanished pid -> 0, Pitfall 3),
  `test_ram_format` (`"312 MB"` / `"1,2 GB"` pt-BR comma / `None`->`"—"`),
  `test_resource_monitor_is_gtk_free`.
- **tests/test_caps.py** (RAM-02/D-15/D-16): `ACTIVE_CAP_DEFAULT == 6`,
  `active_count` (counts only ACTIVE), `at_cap` below/at/custom (`>=` triggers),
  `test_caps_is_gtk_free`. Builds real `WorktreeSession` instances from the Phase-2
  `arduis.session` model.

## Verification

- `python -m pytest tests/test_{layout,keymap,resource_monitor,caps}.py -q` is **RED**:
  all four interrupt collection with `ImportError: cannot import name '<module>'`
  (exit code 2) because the modules do not exist yet — exactly the intended RED state.
- Existing suite stays **GREEN**: `test_session / test_spawn_argv / test_theme /
  test_host_runner / test_exit_decode / test_worktree` -> 25 passed, exit 0.
- No test reads the real `/proc` (T-03-01): every `/proc` access is monkeypatched.
- All acceptance-criteria greps pass for both tasks.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Verification interpreter switched to the repo .venv**
- **Found during:** Task 1 verification
- **Issue:** The plan's verify/acceptance commands invoke bare `python3 -m pytest`,
  but the system `python3` (`/usr/bin/python3`) has no `pytest` installed
  (`No module named pytest`). The project ships a `.venv` with `pytest 9.0.3` and a
  `pyproject.toml` configuring `pythonpath = ["src"]`.
- **Fix:** Ran all verification via `/home/thallysrc/Projects/arduis/.venv/bin/python -m pytest`.
  The behavioral contract being verified is identical; only the interpreter changed.
- **Files modified:** none (verification-only).
- **Commit:** n/a

## Known Stubs

None — these are RED test scaffolds by design (the modules under test are
intentionally absent; that absence IS the RED contract). No production code, no
placeholder data, no hardcoded UI values.

## Commits

- `89d3e58` test(03-01): add failing tests for layout and keymap contracts
- `765d34d` test(03-01): add failing tests for resource_monitor and caps contracts

## Self-Check: PASSED

All four test files and the SUMMARY exist on disk; both task commits (`89d3e58`,
`765d34d`) are reachable in git history.
