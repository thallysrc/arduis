---
quick_id: 260615-trz
description: Apply 3 high-confidence code-review fixes (git_service, layout, theme)
date: 2026-06-15
source: .planning/CODE-REVIEW-2026-06-15.md (findings #1, #2, #3)
tasks: 3
---

# Quick Task 260615-trz — Plan

Apply the three clearly-correct, well-contained fixes from the 2026-06-15 code review. Each
ships with a regression test. Run `/tmp/arduis-venv/bin/python -m pytest` (system-site-packages
venv) — the system `python3` has no pytest. Full suite must stay green (437 passing before).

## Task 1 — git_service spawn/finish exception guard (Finding #1, High)

**File:** `src/arduis/git_service.py`, `tests/test_git_service_cwd.py`

`run_git_async` can crash uncaught: `Gio.Subprocess.new` / `launcher.spawnv` raise
`GLib.Error` when the executable is missing or `cwd` was deleted (worktree concluded mid-flight),
and `communicate_utf8_finish` can also raise. The exception escapes into the GLib main loop and
`on_done` is never called → the UI stays stuck waiting forever.

- Import `GLib` (alongside `Gio`).
- Wrap the spawn block (the `if cwd is None / else` that builds `proc`) in `try/except GLib.Error as exc:` → call `on_done(-1, "", str(exc))` and `return`.
- Wrap `communicate_utf8_finish` in `_cb` in `try/except GLib.Error as exc:` → `on_done(-1, "", str(exc))` and `return`.
- Keep the `out or ""` / `err or ""` guards.
- Preserve the exact behavior on the success path (byte-identical for existing callers).

**Test:** add to `tests/test_git_service_cwd.py` a test that calls `run_git_async` with a
non-existent `cwd` (e.g. `/nonexistent/arduis-xyz`) and a fake/real `git rev-parse` argv, drives
the GLib main loop briefly (`GLib.MainContext.default().iteration(False)` in a short loop, or a
`GLib.MainLoop` with a timeout), and asserts `on_done` was invoked with a non-zero status rather
than the call raising. If driving the loop is awkward in the existing test style, mirror the
existing test harness in that file. Verify: `on_done` is called exactly once with rc != 0.

## Task 2 — layout.close_leaf stale state on last-pane close (Finding #2, Medium)

**File:** `src/arduis/layout.py`, `tests/test_layout.py`

In `close_leaf`, when `self.root` is a `LeafNode` matching `session_id`, the method sets
`self.root = None` and **early-returns**, skipping the `_mru.remove(...)` and `focused_id`
reset that the non-root path runs. Result: after closing the last pane, `focused_id` and `_mru`
still reference the dead session.

- Remove the early `return` from the single-leaf-root branch so control falls through to the
  shared cleanup (remove `session_id` from `_mru`; if `focused_id == session_id`, set it to the
  first remaining `visible_ids()` or `None`). Match the existing cleanup logic exactly; do not
  change the non-root path's behavior.

**Test:** add `test_close_last_leaf_clears_focus_and_mru` to `tests/test_layout.py`: build a
single-leaf model, `close_leaf` it, assert `root is None`, `focused_id is None`, and the session
id is absent from MRU (e.g. a subsequent `preset`/`visible_ids` shows no stale id). Keep the
existing `test_close_every_terminal_empties_the_tree` passing.

## Task 3 — _apply_theme re-colors ALL projects' terminals (Finding #3, Medium)

**File:** `src/arduis/window.py` (+ test if a GTK-free seam allows; otherwise note manual)

`_apply_theme` (around line 767) iterates `self._term_by_sid` (active project bundle only), so a
background project's live (unparented) terminals keep the old palette after a theme switch —
contradicting the docstring "re-color EVERY live terminal".

- Replace the `for term in self._term_by_sid.values():` loop with iteration over EVERY registered
  project's bundle: for each `proj in self._registry.all()`, get its bundle via `self._bundle_for(proj)`
  and re-color every terminal in `bundle["term_by_sid"].values()` (same `set_colors` + `set_color_cursor`).
- Keep `self._current_theme = theme` and the provider replace/add logic unchanged.
- Use `self._bundle_for(proj)` (the existing accessor at window.py:633) — do NOT use a bare
  `getattr` so the bundle is created consistently.

**Test:** window.py is GTK-heavy; a full unit test may need GTK. If `tests/test_themes.py` or an
existing window test seam can assert the iteration covers all projects without a display, add it.
Otherwise, document in the SUMMARY that the fix is covered by code inspection + the existing theme
tests, and that the live multi-project recolor remains a manual UAT item (it is display-bound).
Do NOT fabricate a passing test that doesn't actually exercise the change.

## Verification
- `/tmp/arduis-venv/bin/python -m pytest` → all green (≥ 437 + new tests).
- No implementation behavior changed on success paths.
