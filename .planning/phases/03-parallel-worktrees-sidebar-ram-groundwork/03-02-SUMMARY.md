---
phase: 03-parallel-worktrees-sidebar-ram-groundwork
plan: 02
subsystem: layout-keyboard
tags: [layout, keymap, gtk-free, binary-tree, prefix-keymap, green]
requires:
  - "tests/test_layout.py + tests/test_keymap.py (Plan 03-01 RED contracts)"
  - "arduis.session (session_id string keys; dataclass idiom mirrored)"
provides:
  - "src/arduis/layout.py — GTK-free binary split/leaf tree: split/close-collapse/zoom/preset/MRU/visibility + resolve_selection (D-01/D-02/D-03/D-04/D-06)"
  - "src/arduis/keymap.py — GTK-free C-Space prefix constants + dispatch() (D-09/D-10)"
affects:
  - "Plan 03-04/05 window.py — consumes LayoutModel + resolve_selection + dispatch as the thin GTK reflection"
tech-stack:
  added: []
  patterns:
    - "GTK-free domain module mirroring session.py (from __future__ import annotations + stdlib dataclasses, no gi)"
    - "Binary layout tree with degenerate-parent collapse on close (Pitfall 2)"
    - "Pure decision function (resolve_selection) returns action tuples, no side effects"
    - "Closed-set dispatcher: untrusted key -> fixed action tuple or None (T-03-03)"
key-files:
  created:
    - src/arduis/layout.py
    - src/arduis/keymap.py
  modified: []
decisions:
  - "Verified via repo .venv (pytest) — system python3 lacks pytest; behavioral contract unchanged (deviation Rule 3, inherited from Plan 03-01)."
  - "preset() merges MRU order with any call-order ids not yet touched, so a fresh model with untouched ids still builds a deterministic tree."
metrics:
  duration: "~6 min"
  completed: "2026-06-09"
  tasks: 2
  files: 2
---

# Phase 03 Plan 02: GTK-free Layout Tree + Prefix Keymap Summary

Two `import gi`-free domain modules carry all the layout and keyboard *logic* —
`layout.py` (the binary split/leaf tree that mirrors the eventual `GtkPaned` tree
but holds no widgets) and `keymap.py` (the hardcoded C-Space prefix keymap + pure
dispatcher) — turning the Plan 03-01 RED suite GREEN so window.py stays a thin
reflection of the model.

## What Was Built

- **src/arduis/layout.py** (LAYOUT-01, PAR-01, PAR-02):
  - `LeafNode(session_id)` / `SplitNode(orientation, start, end)` dataclasses; `orientation` is `"h"` (side-by-side) / `"v"` (stacked).
  - `LayoutModel` with `root`, `focused_id`, a private MRU list, and a `_pre_zoom` snapshot slot.
  - `split()` replaces the matching leaf (or root) with a two-leaf `SplitNode`, focuses + touches the new id (D-03).
  - `close_leaf()` removes the leaf and collapses the now-degenerate parent to the surviving sibling subtree, handling the root case (D-04, Pitfall 2); also prunes MRU + re-points focus.
  - `visible_ids()` / `is_visible()` walk the tree only — visibility decoupled from store existence (D-02).
  - `set_leaf_session()` swaps a leaf's id (target or focused) — the D-06 swap-into-focused op.
  - `zoom()` / `unzoom()` / `is_zoomed()` snapshot-and-restore the whole tree.
  - `preset("grid2x2"|"columns", ids)` builds a fresh balanced tree from the MRU-ordered subset (grid2x2 = `v(h(a,b), h(c,d))`; columns = right-leaning `h` chain), clearing zoom (D-04).
  - `touch()` / `mru_order()` maintain most-recent-first focus order.
  - Module-level `resolve_selection(model, id)` — pure `("focus", id)` vs `("swap", focused_id)` decision (D-06).
- **src/arduis/keymap.py** (PAR-03, D-09/D-10):
  - `PREFIX_KEYVAL = "space"`, `PREFIX_MODS = "ctrl"` (Ctrl+Space prefix).
  - `KEYMAP` = h/j/k/l focus directions + n/p worktree cycle.
  - `dispatch(key)` returns `("jump", int)` for digits 1-9, the KEYMAP tuple otherwise, `None` for unknown — split/zoom chords intentionally absent (Phase 5).

## Verification

- `pytest tests/test_layout.py tests/test_keymap.py -q` -> **13 passed**, exit 0 (GREEN).
- Full suite minus the Plan-03-03-owned modules (`--ignore test_resource_monitor.py --ignore test_caps.py`) -> **38 passed**, exit 0.
- Both modules GTK-free: `grep "import gi"` returns nothing in either file.
- All acceptance-criteria greps for both tasks pass (`class LayoutModel`, `def resolve_selection`, `def (split|close_leaf|zoom|preset|visible_ids)`, `PREFIX_KEYVAL = "space"`, `def dispatch`; no `"z"|"-"|"="` chords).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Verification interpreter is the repo .venv**
- **Found during:** Task 1 verification
- **Issue:** The plan's verify commands invoke bare `python3 -m pytest`, but the
  system `python3` has no pytest. The project ships `.venv` with pytest and a
  `pyproject.toml` setting `pythonpath = ["src"]`.
- **Fix:** Ran all verification via `/home/thallysrc/Projects/arduis/.venv/bin/python -m pytest`.
  Same behavioral contract; only the interpreter differs (matches Plan 03-01's documented deviation).
- **Files modified:** none (verification-only).
- **Commit:** n/a

## Out-of-Scope Observations

- The full `pytest -q` run reports `ImportError` for `arduis.resource_monitor` and
  `arduis.caps` (tests/test_resource_monitor.py, tests/test_caps.py). These modules
  are owned by the parallel Wave-1 Plan **03-03** and are intentionally not built
  here. Not a deviation — a known parallel-wave dependency. No action taken.

## Known Stubs

None — both modules are complete production logic. `preset` may emit an empty
`LeafNode(None)` to pad a grid2x2 with fewer than 4 ids; this is intentional
empty-cell modeling (skipped by `visible_ids`), not a stub.

## Commits

- `3c3fa99` feat(03-02): GTK-free binary split/leaf layout tree
- `b5da4fb` feat(03-02): GTK-free C-Space prefix keymap + dispatch

## Self-Check: PASSED

Both modules and the SUMMARY exist on disk; both task commits (`3c3fa99`,
`b5da4fb`) are reachable in git history.
