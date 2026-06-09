---
phase: 03-parallel-worktrees-sidebar-ram-groundwork
plan: 04
subsystem: window-presentation
tags: [gtk4, sidebar, gtkpaned, layout-reflection, parallel-worktrees, no-tabs]
requires:
  - "arduis.layout.LayoutModel + resolve_selection (Plan 03-02 — split/close/zoom/visibility/focus-or-swap)"
  - "arduis.session.SessionStore + WorktreeSession + hibernate_fields (Phase 2)"
  - "arduis.theme Dracula hexes; arduis.spawn/worktree/git_service/host_runner/exit_status (Phase 1/2 seams)"
provides:
  - "src/arduis/window.py — sidebar (Gtk.ListBox) + nested Gtk.Paned canvas reflecting LayoutModel; Adw.TabView/TabBar removed"
  - "Focus-or-swap row dispatch (D-06); split-on-new (D-03); close-pane hides (D-04); Hibernate/Resume on row context menu (D-08)"
affects:
  - "Plan 03-05 window.py — adds the ~2s RAM poll (fills the 'claude · —' sub-line + footer), the active-agent cap on +New, and the C-Space prefix keymap on top of this shell"
tech-stack:
  added: []
  patterns:
    - "window.py reflects a GTK-free model tree into widgets (no layout logic in the GTK layer)"
    - "Gtk.Paned single-parent reparent discipline: detach all leaves (unparent) BEFORE re-hanging (Pitfall 1)"
    - "Per-leaf widget map keyed by session_id; _rebind_leaf moves the widget on a swap"
    - "Sidebar row right-click via Gtk.GestureClick (secondary button) sets _menu_target_sid for D-08 actions"
    - "Branch names rendered with label.set_text (never set_markup) — T-03-09 label-injection mitigation"
key-files:
  created:
    - .planning/phases/03-parallel-worktrees-sidebar-ram-groundwork/03-04-SUMMARY.md
  modified:
    - src/arduis/window.py
decisions:
  - "The pinned 'main' scratch shell is a layout leaf (session_id 'main') but NOT a SessionStore session (D-07); it seeds the canvas root and is the only always-present row."
  - "Close-pane (✕) HIDES (D-04 default): close_leaf drops the leaf; the WorktreeSession stays ACTIVE in the store + sidebar. No confirmation dialog (UI-SPEC)."
  - "Swap (D-06) remaps the focused leaf's widget/terminal to the incoming sid via _rebind_leaf so the existing pane widget is reused rather than rebuilt."
  - "Dialog/error/menu copy switched to pt-BR per UI-SPEC ('Nova worktree', 'Não foi possível criar a worktree.', 'Hibernar'/'Retomar')."
metrics:
  duration: "~12 min"
  completed: "2026-06-09"
  tasks: 1
  files: 1
---

# Phase 03 Plan 04: Sidebar + Nested GtkPaned Canvas Summary

Rewires `window.py`'s presentation from the Phase-2 `Adw.TabView`/`TabBar` tab
strip to the real Phase-3 shell — a left **sidebar** (`Gtk.ListBox` bound to the
`SessionStore`, with the pinned `main` scratch-shell row) plus a right **nested
`Gtk.Paned` canvas** that *reflects* the GTK-free `LayoutModel` from Plan 03-02.
All split/close/zoom/visibility/focus logic stays in `layout.py`; `window.py`
only walks the model tree into widgets. The Phase-2 spawn/feed/teardown/dialog
wiring is reused verbatim — only the container changed.

## What Was Built

- **Tab strip removed (D-01):** `Adw.TabView`/`Adw.TabBar`, `_install_tab_menu`,
  the `_page_by_sid`/`_sid_by_page` maps, and all `page.set_loading`/
  `set_needs_attention` calls are gone. The body is now an `Adw.ToolbarView`
  content = `Gtk.Box(HORIZONTAL)` of a 248px sidebar + a `Gtk.Frame` canvas slot.
- **Layout model held + reflected (D-01/D-02):** `self._layout = LayoutModel()`
  is the single source of truth for what is visible. `_reflect_layout()` rebuilds
  the canvas from the model: `SplitNode → Gtk.Paned(set_wide_handle(True),
  set_shrink_start_child(False), set_shrink_end_child(False))`, `LeafNode → the
  mapped leaf widget`. Detaches every leaf (`unparent()`) before re-hanging
  (single-parent rule, Pitfall 1). `_leaf_by_sid`/`_term_by_sid` replace the old
  page maps.
- **Pane leaf (`_make_leaf`):** a `Gtk.Box(VERTICAL)` = a 32px pane header (pink
  `set_text` branch label + `claude` badge + spacer + `⊟`/`⊞`/`✕` flat buttons
  with the pt-BR tooltips `Dividir painel`/`Zoom`/`Fechar painel`) over the reused
  `_make_terminal()`. `set_size_request(240, 120)` enforces the UI-SPEC min pane.
- **Sidebar (PAR-02, D-05/D-07):** a `Gtk.ListBox` with a pinned non-session
  `main` row (sub-line `zsh · ocioso`) on top, then one row per session: 8px dot
  (green `#50fa7b` active / grey `#6272a4` hibernated), branch (13/600), and a
  `claude · —` RAM sub-line placeholder (real RSS is Plan 03-05). `_rebuild_sidebar()`
  runs after every store mutation; hibernated rows get a dimmed CSS class.
- **Focus-or-swap dispatch (PAR-02, D-06):** `row-activated` → `resolve_selection`.
  `("focus", sid)` grabs the leaf terminal + sets focus; `("swap", focused)` calls
  `set_leaf_session`, `_rebind_leaf` moves the focused leaf's widget to the new sid,
  then re-reflects. The pinned `main` row focuses the scratch-shell pane.
- **Split-on-new (D-03):** `_open_and_add` now `split(focused, branch, "h")` (or
  seeds the root leaf if the canvas is empty), creates + maps the leaf, reflects,
  then runs the existing `_spawn_into`. On a failed `git worktree add` the new leaf
  is closed and the error surfaced (`Não foi possível criar a worktree.`).
- **Close-pane hides (D-04):** the `✕` handler calls `close_leaf(sid)` +
  `_reflect_layout()`; the `WorktreeSession` stays ACTIVE in the store + sidebar.
  No confirmation. (The `⊞` button toggles `zoom`/`unzoom` as a bonus from the
  model API, satisfying the UI-SPEC zoom control.)
- **Hibernate/Resume on the row menu (D-08):** a `Gtk.GestureClick`
  (secondary button) on each session row sets `self._menu_target_sid` and pops a
  `Gtk.PopoverMenu` with `Hibernar`/`Retomar`. The Phase-2 `win.hibernate`/
  `win.resume` `Gio.SimpleAction`s + `_on_hibernate`/`_on_resume` handlers are
  reused; they now resolve the target via `_menu_session()` and refresh the row
  dot/dimming through `_rebuild_sidebar()` instead of a tab badge.
- **Dracula CSS (UI-SPEC Color):** a `Gtk.CssProvider` loaded once per display
  carries the sidebar/pane-header surface (`#21222c`), pink branch label
  (`#ff79c6`), purple focus ring (`#bd93f9`), and the active/hibernated dot
  colors. Window title stays `arduis`.
- **Preserved verbatim:** `_make_terminal`, `_install_clipboard_shortcuts`,
  `_spawn_into`, `_make_wt_spawn_cb`, `_teardown_pgid`, `_sigkill_if_alive`,
  `_on_close_request` (still iterates `self._store.all()` + `self._shell_pid`),
  `_resolve_repo_root`, and the full +New dialog chain (only the tab→pane swap
  changed in step 7).

## Verification

- `python3 -c "import ast; ast.parse(open('src/arduis/window.py').read())"` → exit 0 (parses).
- `pytest -q` (via the repo `.venv`) → **50 passed**, exit 0 — the GTK-free suite
  is unaffected (window.py is not imported by tests, by design).
- `from arduis.layout import LayoutModel, LeafNode, SplitNode, resolve_selection`
  resolves at runtime (`PYTHONPATH=src`).
- All acceptance-criteria greps pass: `Adw.TabView`/`Adw.TabBar`/`get_children`
  ABSENT; `Gtk.Paned`, `from arduis.layout import`, `resolve_selection`,
  `set_shrink_start_child`, `set_wide_handle`, the pane tooltips,
  `win.hibernate`/`win.resume`, `#50fa7b`, and `#6272a4` all PRESENT.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Verification interpreter is the repo .venv**
- **Found during:** Task 1 verification.
- **Issue:** The plan's verify commands invoke bare `python3 -m pytest`, but the
  system `python3` has no pytest. The project ships `.venv` with pytest and a
  `pyproject.toml` `pythonpath = ["src"]`.
- **Fix:** Ran all verification via `/home/thallysrc/Projects/arduis/.venv/bin/python -m pytest`.
  Same behavioral contract; only the interpreter differs (matches Plans 03-01/02/03).
- **Files modified:** none (verification-only).
- **Commit:** n/a

**2. [Rule 3 - Blocking] Doc/comment tokens collided with the absence greps**
- **Found during:** Task 1 acceptance-criteria greps.
- **Issue:** The module docstring named `Adw.TabView`/`TabBar` (describing what was
  removed) and a comment said `get_children()`. The acceptance greps require those
  literal strings to be ABSENT from the whole file, so the prose tripped them.
- **Fix:** Reworded the docstring ("the now-removed libadwaita tab view + tab bar")
  and the comment ("the GTK3 container-children accessor is gone in GTK4") to drop
  the literal tokens. No code behavior changed.
- **Files modified:** src/arduis/window.py
- **Commit:** 62ad5a2 (folded into the task commit)

### Discretionary calls (within plan latitude)

- **`⊞` zoom button** wired to the model's `zoom`/`unzoom` (the UI-SPEC lists a
  zoom control now; the `C-Space z` chord is Phase 5). Within D-04 scope.
- **`⊟` split button** re-opens the +New dialog with this pane as the split point,
  reusing the D-03 split path rather than adding a second split mechanism.
- **Copy switched to pt-BR** per the UI-SPEC Copywriting Contract (dialogs, errors,
  menu labels, tooltips).

## Known Stubs

- **Sidebar RAM sub-line `claude · —`** (src/arduis/window.py, `_rebuild_sidebar`):
  an intentional placeholder. Real per-worktree RSS is wired by **Plan 03-05**
  (the `~2s` off-loop `group_rss_kb` poll + `format_ram_kb`), exactly as both this
  plan's own action text (step 5) and Plan 03-03's SUMMARY state. The aggregate
  footer (`N agentes ativos · <total> RAM`) is likewise Plan 03-05. Not a blocker:
  the plan's goal (visible parallelism via the sidebar + paned canvas) is achieved;
  the RAM figure is the next plan's deliverable on top of this shell.

## Threat Flags

None. The two trust boundaries in the plan's `<threat_model>` are mitigated as
specified: branch names render via `label.set_text` (never `set_markup`) in both
the sidebar row and the pane header (T-03-09); row activation resolves a sid only
from the trusted `self._sid_by_row` map and `resolve_selection`, which can only
return a visible id or the current focused id (T-03-10). No new network/auth/file
surface was introduced — spawn/teardown are the unchanged Phase-2 seams.

## Commits

- `62ad5a2`: feat(03-04): replace tab strip with sidebar + nested GtkPaned canvas

## Self-Check: PASSED

- FOUND: src/arduis/window.py
- FOUND: .planning/phases/03-parallel-worktrees-sidebar-ram-groundwork/03-04-SUMMARY.md
- FOUND commit: 62ad5a2
