---
status: resolved
trigger: "workspace-sidebar-highlight-wrong-item: WORKSPACES list highlights the wrong item (novo-teste) instead of the actually-active workspace (arduis)"
created: 2026-07-02T17:39:18Z
updated: 2026-07-02T17:47:00Z
---

## Current Focus

hypothesis: The pinned main ("arduis") row is never visually selected at boot, so the sidebar highlight does not track the active workspace.
test: Trace boot ordering of `_active_workspace_sid` writes vs. the `select_row` calls that drive the ListBox `:selected` highlight.
expecting: A boot path that sets `_active_workspace_sid = _MAIN_SID` WITHOUT syncing ListBox selection, after the only `_rebuild_sidebar` ran with `_active_workspace_sid == None`.
next_action: Add a `_sync_sidebar_selection()` helper; call it at the end of `_open_shell_leaf` and reuse it in `_rebuild_sidebar`.

## Symptoms

expected: The WORKSPACES row for the active/focused workspace ("arduis" = pinned main row) should carry the selected/highlighted background.
actual: "novo-teste" appears highlighted while the user is actively working in the "arduis" workspace (right panel shows "arduis (master)").
errors: None — pure visual/state bug.
reproduction: Open app with 2+ workspaces; activate/focus the "arduis" (main) workspace; sidebar highlight does not match the active workspace.
started: Always broken since the multi-workspace sidebar existed (not a recent regression).

## Eliminated

- hypothesis: A persisted `active_workspace_sid` is loaded stale at boot.
  evidence: `_bundle_for` sets `bundle["active_workspace_sid"] = None` and it is never read from disk — always None at startup (window.py:782).
  timestamp: 2026-07-02T17:39:18Z

## Evidence

- timestamp: 2026-07-02T17:39:18Z
  checked: The three places the ListBox highlight is driven (`select_row`).
  found: Highlight is synced only in `_rebuild_sidebar` (2217-2220, restores selection to `_active_workspace_sid`), `_swap_workspace` (2705-2707), and `_show_hibernated_placeholder` (2765-2767). CSS `.arduis-sidebar row:selected` (179-181) is what paints the highlight.
  implication: The highlight follows the ListBox SINGLE-selection, which is only set through those paths.

- timestamp: 2026-07-02T17:39:18Z
  checked: Boot sequence in `__init__` (646-667) and `_open_shell_leaf` (1953-2004).
  found: Boot order is `_init_projects()` (calls `_rediscover` -> `_rebuild_sidebar` at 3682) THEN `_open_shell_leaf()` (662). `_open_shell_leaf` sets `_active_workspace_sid = _MAIN_SID` (1987) or via `_restore_layout` (2062), then calls `_reflect_layout()` — never `select_row` and never `_rebuild_sidebar`.
  implication: When `_rebuild_sidebar` ran (inside `_init_projects`), `_active_workspace_sid` was still None (default), so the selection-restore block did nothing. After `_open_shell_leaf` sets it to `_MAIN_SID`, nothing re-syncs the ListBox selection. The pinned "arduis" row boots UNhighlighted.

- timestamp: 2026-07-02T17:39:18Z
  checked: What visually stands out when main is unselected.
  found: With no selection on the active row, a previously-active/last-rendered row (e.g. "novo-teste", which WAS selected when it was active/resumed, or carries an attention background) remains the only visually prominent row.
  implication: The reported "novo-teste highlighted, arduis focused" is the direct consequence of the active (main) row never being selected at boot.

## Resolution

root_cause: The sidebar highlight is the ListBox SINGLE-selection, but the boot main-shell path (`_open_shell_leaf`) sets `_active_workspace_sid = _MAIN_SID` via `_reflect_layout` WITHOUT syncing the ListBox selection. The only `_rebuild_sidebar` that runs before it (inside `_init_projects`) executes while `_active_workspace_sid` is still None, so no row is selected. Net effect: the active workspace's row is never highlighted at boot, leaving a stale/other row (novo-teste) as the visually prominent one.
fix: Added `_sync_sidebar_selection()` — selects the row for `_active_workspace_sid` (unselects when None). Called it at the end of `_open_shell_leaf` (boot) and refactored `_rebuild_sidebar` to use it, centralizing the highlight source of truth on `_active_workspace_sid`.
verification: 4 new unit tests (tests/test_window_sidebar_selection.py) lock the highlight-sync logic incl. the stale-selection-correction case; full window/sidebar/attention/projects suite (137 tests) passes. User confirmed fixed in the running app.
files_changed: [src/arduis/window.py, tests/test_window_sidebar_selection.py]
