# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## workspace-sidebar-highlight-wrong-item — WORKSPACES sidebar highlights the wrong item instead of the actually-active workspace
- **Date:** 2026-07-02
- **Error patterns:** sidebar, highlight, selected, active workspace, ListBox, novo-teste, wrong item, boot, select_row
- **Root cause:** The WORKSPACES highlight is the ListBox SINGLE-selection (`.arduis-sidebar row:selected`), but the boot path (`_open_shell_leaf` -> `_reflect_layout`) set `_active_workspace_sid` without ever calling `select_row`, and the only prior `_rebuild_sidebar` ran while `_active_workspace_sid` was still `None`. The pinned main row was therefore never selected at boot, leaving a stale row (e.g. "novo-teste") as the visually "active" one.
- **Fix:** Added `_sync_sidebar_selection()` as the single source of truth for the ListBox highlight (selects the row for `_active_workspace_sid`, unselects when `None`). Called it from `_open_shell_leaf` (boot) and reused it in `_rebuild_sidebar`.
- **Files changed:** src/arduis/window.py, tests/test_window_sidebar_selection.py
---

