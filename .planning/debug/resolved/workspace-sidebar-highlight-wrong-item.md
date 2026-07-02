---
status: resolved
trigger: "workspace-sidebar-highlight-wrong-item: WORKSPACES list highlights the wrong item (novo-teste) instead of the actually-active workspace (arduis)"
created: 2026-07-02T17:39:18Z
updated: 2026-07-02T18:35:00Z
---

## Current Focus

**Round 2 findings (2026-07-02T18:20:00Z)** — user sent a screenshot pinpointing the real remaining gap: viewing "novo-teste"'s panes (top "novo-teste claude", bottom "novo-teste zsh") while the sidebar highlight stayed on "arduis" (the pinned main row, boot-selected by round 1's fix). Root cause found: `_build_workspace_terminals` (shared by workspace CREATE-finalize and RESUME) and `_restore_layout` (shared by boot main-restore and worktree-resume) both write `_active_workspace_sid` directly and call `_reflect_layout()` WITHOUT calling `_sync_sidebar_selection()` — they relied on the CALLER to later call `_rebuild_sidebar()`, which is fragile/indirect. Fixed by making both self-sufficient, centralizing `_swap_workspace`/`_show_hibernated_placeholder`'s inline sync blocks onto the same helper, and adding an AST-based structural test that fails if ANY future function assigns `_active_workspace_sid` without calling `_sync_sidebar_selection()`.

hypothesis: CONFIRMED — `_build_workspace_terminals` and `_restore_layout` are write sites that bypass `_sync_sidebar_selection`, exactly the class of gap the coordinator asked to grep for.
test: `grep -n "self\._active_workspace_sid = " src/arduis/window.py` then trace each site's enclosing function for a `_sync_sidebar_selection()`/`_swap_workspace` call.
expecting: at least one site with no adjacent sync call.
next_action: awaiting fresh human verification of round 2 fix (create workspace / resume workspace / switch between arduis, novo-teste, caramelo and confirm highlight always matches the visible canvas).

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

- hypothesis: The user is running a stale/installed copy of window.py (meson install / .deb / cached venv) that predates the round-1 fix, so it never took effect.
  evidence: The dev launcher `run.sh` -> `python3 src/main.py` does `sys.path.insert(0, .../src)` then `import arduis` — it always imports THIS checkout's `src/arduis/window.py` live, no install/build step involved. No `arduis` package is installed system-wide or in any venv (`importlib.util.find_spec('arduis')` -> None; no `/usr/bin/arduis`, no `dist-packages/arduis`). The only OTHER `window.py` copies on disk live in sibling git worktrees (`arduis-tasks/novo-teste/arduis`, `arduis-tasks/caramelo/arduis`) which are separate checkouts of the SAME project dogfooding itself (arduis manages its own dev workspaces) — those are DATA (worktrees shown as sidebar rows), not the code the running GUI process imports.
  timestamp: 2026-07-02T18:15:00Z

- hypothesis: A separate/duplicate GtkListBox or top-level window instance is involved (multiple windows each with their own selection state).
  evidence: `main.py`'s `do_activate` reuses `self.props.active_window or ArduisWindow(application=self)` — exactly one `ArduisWindow`/one `self._listbox` per app run. `_row_by_sid`/`_sid_by_row` are window-global dicts (not per-project-bundle) and are fully cleared+rebuilt by every `_rebuild_sidebar()` call, so there is never more than one row per sid at a time.
  timestamp: 2026-07-02T18:15:00Z

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

- timestamp: 2026-07-02T18:15:00Z
  checked: EVERY assignment site of `self._active_workspace_sid =` after round 1's fix (`grep -n "self\._active_workspace_sid = "`).
  found: 5 sites total. `_open_shell_leaf` (2032, covered by an unconditional trailing `_sync_sidebar_selection()` added in round 1), `_swap_workspace` (2770) and `_show_hibernated_placeholder` (2812) each had their OWN inline sync block (pre-existing, correct). But `_restore_layout` (2114) and `_build_workspace_terminals` (4002, "shared by `_create_workspace` and `_resume_workspace`" per its own docstring) set the sid and call `_reflect_layout()` directly, with NO sync call anywhere in their own body — they silently relied on whichever caller happens to invoke `_rebuild_sidebar()` afterward.
  implication: Creating a new workspace or resuming a hibernated one swaps the canvas to the new/resumed workspace's panes immediately (via `_reflect_layout()`), but the sidebar highlight only updates later IF and WHEN the caller's OWN `_rebuild_sidebar()` call runs — an indirect, easy-to-miss coupling. This matches the screenshot exactly: canvas already showing "novo-teste" panes, sidebar still showing "arduis" (the boot-selected row) highlighted.

## Resolution

root_cause: TWO layered bugs. (1) Boot: `_open_shell_leaf` set `_active_workspace_sid = _MAIN_SID` via `_reflect_layout` without syncing the ListBox selection, and the only prior `_rebuild_sidebar` ran while `_active_workspace_sid` was still None — so the active row was never selected at boot (round 1, fixed by commit 6858fca). (2) Workspace switch via create/resume: `_build_workspace_terminals` (shared by workspace creation-finalize and resume) and `_restore_layout` (shared by boot main-restore and worktree-resume) both set `_active_workspace_sid` and swap the canvas via `_reflect_layout()` directly, WITHOUT calling `_sync_sidebar_selection()` themselves — they relied on the caller's later, separate `_rebuild_sidebar()` call, an indirect coupling that left the highlight on whatever row was selected before (e.g. the boot-selected "arduis" row) while the canvas had already moved to the new/resumed workspace (round 2).
fix: Round 1 — added `_sync_sidebar_selection()` (selects the row for `_active_workspace_sid`, unselects when None) and called it from `_open_shell_leaf` + `_rebuild_sidebar`. Round 2 — made `_build_workspace_terminals` and `_restore_layout` self-sufficient by calling `_sync_sidebar_selection()` directly after their `_reflect_layout()` call (no longer depending on the caller), and refactored `_swap_workspace`/`_show_hibernated_placeholder`'s pre-existing inline sync blocks to call the same shared helper for consistency. Added an AST-based structural test (`test_every_active_workspace_sid_write_site_syncs_the_highlight`) that scans `window.py` and fails if ANY function assigns `_active_workspace_sid` without also calling `_sync_sidebar_selection()` in its own body — a standing guard against this exact bug class recurring at a new call site.
verification: 7 tests in `tests/test_window_sidebar_selection.py` (4 from round 1 + 3 new: `_build_workspace_terminals` self-sync, `_restore_layout` self-sync, AST structural guard) all pass. Full test suite: 455 tests pass, no regressions (only pre-existing unrelated deprecation warnings). User confirmed fixed end-to-end (boot + create/resume/switch) in the running app.
files_changed: [src/arduis/window.py, tests/test_window_sidebar_selection.py]
