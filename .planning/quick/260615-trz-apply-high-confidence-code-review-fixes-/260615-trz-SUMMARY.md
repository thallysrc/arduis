---
quick_id: 260615-trz
description: Apply 3 high-confidence code-review fixes (git_service, layout, theme)
date: 2026-06-15
status: complete
source: .planning/CODE-REVIEW-2026-06-15.md (findings #1, #2, #3)
commits:
  - 98877a4 fix(260615-trz): guard git_service spawn/finish against GLib.Error
  - b03bd50 fix(260615-trz): close_leaf clears focus/MRU on last-pane close
  - 6c15306 fix(260615-trz): _apply_theme recolors terminals across ALL projects
tests: 440 passed (437 baseline + 3 new regression tests)
---

# Quick Task 260615-trz — Summary

Applied the three clearly-correct, well-contained fixes from the 2026-06-15 autonomous code
review. Each shipped atomically with a regression test. Full suite green (440 passed).

## Fix 1 — git_service spawn/finish exception guard (Finding #1, High)
`run_git_async` (`src/arduis/git_service.py`) could crash uncaught when `Gio.Subprocess.new` /
`launcher.spawnv` raised `GLib.Error` (missing exe, or `cwd` deleted by a concurrent conclude),
and likewise in `communicate_utf8_finish`. The exception escaped into the GLib loop and `on_done`
was never called → UI stuck waiting forever. Now both the spawn block and the finish callback are
wrapped in `try/except GLib.Error` → `on_done(-1, "", str(exc))`. Success path is byte-identical.
**Test:** drives `run_git_async` with a non-existent `cwd` and asserts `on_done` fires once with
rc != 0 instead of raising.

## Fix 2 — layout.close_leaf stale state on last-pane close (Finding #2, Medium)
`close_leaf` (`src/arduis/layout.py`) early-returned on the single-leaf-root path, skipping the
`_mru.remove` / `focused_id` reset. After closing the last pane, `focused_id` and `_mru` still
referenced the dead session. Removed the early return so control falls through to the shared
cleanup. **Test:** `test_close_last_leaf_clears_focus_and_mru` — asserts `root is None`,
`focused_id is None`, and no stale MRU id after closing the last leaf.

## Fix 3 — _apply_theme recolors ALL projects' terminals (Finding #3, Medium)
`_apply_theme` (`src/arduis/window.py`) iterated only the active project's `_term_by_sid`, so a
background project's live (unparented) terminals kept the old palette after a theme switch —
contradicting its own docstring. Now iterates every registered project via `self._bundle_for(proj)`
and recolors each bundle's terminals. **Test:** a genuine headless test using the existing GTK-free
`ArduisWindow.__new__` + `_display=None` seam (already used by `test_window_projects.py`) — drives
the real `_apply_theme` across two projects with stub terminals and asserts the background project's
terminal is recolored (fails against the old active-only loop). The on-screen visual flip remains a
manual/broadway-smoke UAT item (display-bound).

## Not touched
Deferred findings #4 (multi-project attention surfacing — needs UX decision), #5 (orphan-on-close
SIGKILL timing — UX tradeoff), #6 (state-file namespace, low impact), #7 (appconfig root-scalar) —
left for PO decision per `.planning/CODE-REVIEW-2026-06-15.md`.

## Verification
- `/tmp/arduis-venv/bin/python -m pytest` → **440 passed**, 4 pre-existing warnings (GTK
  CssProvider deprecation + os.fork() notice — not introduced here).
- Worktree-isolated execution; branch fast-forward-merged to master.
