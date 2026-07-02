# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## workspace-sidebar-highlight-wrong-item — WORKSPACES sidebar highlights the wrong item instead of the actually-active workspace
- **Date:** 2026-07-02
- **Error patterns:** sidebar, highlight, selected, active workspace, ListBox, novo-teste, wrong item, boot, select_row, create workspace, resume workspace, restore layout, _active_workspace_sid
- **Root cause:** The WORKSPACES highlight is the ListBox SINGLE-selection (`.arduis-sidebar row:selected`), driven entirely by `_active_workspace_sid`. TWO layered gaps: (1) boot — `_open_shell_leaf` set `_active_workspace_sid` via `_reflect_layout` without ever calling `select_row`, and the only prior `_rebuild_sidebar` ran while `_active_workspace_sid` was still `None`, so the pinned main row was never selected at boot. (2) create/resume — `_build_workspace_terminals` (shared by workspace create-finalize and resume) and `_restore_layout` (shared by boot main-restore and worktree-resume) both swap the canvas via `_reflect_layout()` directly, bypassing `_swap_workspace`, and relied on the CALLER to later call `_rebuild_sidebar()` to pick up the highlight — an indirect coupling that left the highlight on a stale row (e.g. the boot-selected main row) while the canvas had already moved to the newly created/resumed workspace.
- **Fix:** Added `_sync_sidebar_selection()` as the single source of truth for the ListBox highlight (selects the row for `_active_workspace_sid`, unselects when `None`). Round 1: called it from `_open_shell_leaf` (boot) and reused it in `_rebuild_sidebar`. Round 2: made `_build_workspace_terminals` and `_restore_layout` call it directly (self-sufficient, no longer dependent on the caller's `_rebuild_sidebar()`), and centralized `_swap_workspace`/`_show_hibernated_placeholder`'s pre-existing inline sync blocks onto the same helper. Added an AST-based structural test that fails if ANY function assigns `_active_workspace_sid` without also calling `_sync_sidebar_selection()` in its own body — a standing guard against this bug class recurring at a new call site.
- **Files changed:** src/arduis/window.py, tests/test_window_sidebar_selection.py
---

## split-black-pane-hole — intermittent black region (no pane) after creating terminal splits, self-heals on window resize
- **Date:** 2026-07-02
- **Error patterns:** split, paned, black hole, region, no render, pane, black, layout, resize, self-heal, max-position, ratio, Gtk.Paned, nested split
- **Root cause:** `_init_paned_position` applied each `Gtk.Paned` split position PURELY reactively from `notify::max-position`. Creating a split calls `_reflect_layout`, which rebuilds the ENTIRE nested Paned tree; GTK4 coalesces max-position notifications, so a freshly rebuilt paned could settle at its real extent WITHOUT a final re-notify — `_apply` then ran only on a tiny transient extent (or never), leaving one child at ≈0 extent = a black hole. Any later allocation (resize) re-fired notify::max-position → `_apply` ran with the intact 0.5 ratio → hole self-healed. Secondary hazard: `_learn`'s synchronous `applying` flag missed GTK4-deferred `notify::position`, so an echo/transient collapse could poison `node.ratio` into layouts.json (a resize-RESISTANT hole).
- **Fix:** Added a self-removing `add_tick_callback` that re-runs `_apply` every frame until `max-position > 1` then stops (600-frame safety budget), guaranteeing the first proportional split regardless of notification coalescing (reactive path kept for resizes). Extracted a pure `_learned_ratio(position, max_position, last_set, settled)` guard rejecting unallocated/pre-settle/echo(exact last_set match)/degenerate(≤0.02,≥0.98) positions so a bad ratio is never persisted.
- **Files changed:** src/arduis/window.py, tests/test_paned_ratio_guard.py
---

