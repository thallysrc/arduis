---
phase: 05-agent-swap-tmux-keybindings-themes
plan: 03
subsystem: ui
tags: [gtk4, vte, themes, css-provider, keymap, agent-feed, libadwaita, window-wiring]

# Dependency graph
requires:
  - phase: 05-agent-swap-tmux-keybindings-themes
    provides: "Plan 01 themes.py (Theme/THEMES/get_theme); Plan 02 agentconfig/keyconfig/appconfig + extended keymap"
  - phase: 04-attention-detection
    provides: "the ~/.config/arduis/arduis.toml config path + _att_config load pattern reused here"
provides:
  - "window.py wires the configurable agent feed (create/split/resume/refeed) from agentconfig"
  - "window.py drives the capture-phase prefix machine from [keys] (configurable prefix + bindings)"
  - "window.py _run_action handles split/zoom/refeed verbs; _zoom_pane shared by ⊞ + C-Space z"
  - "Runtime theme switch: header Tema menu + win.set_theme + _apply_theme (provider replaced, every VTE re-colored, persisted)"
affects: [05-04 (live UAT checklist), verifier, criterion-3 Wayland gate]

# Tech tracking
tech-stack:
  added: []  # zero new dependencies — stdlib (tomllib) + already-present GNOME stack
  patterns:
    - "Per-theme CSS builder (_build_css(theme)) replaces a module f-string; classes/selectors unchanged, only color values per-theme"
    - "Replaceable display CssProvider (handle kept; remove-before-add on switch — Pitfall 1)"
    - "self._current_theme is the single authoritative palette source for _make_terminal/_build_css/_apply_theme (Pitfall 2)"
    - "Configurable prefix machine: self._prefix[0] + self._keymap.get(name) over the closed action set; digit->jump kept as a non-configurable fallback"
    - "Shared _zoom_pane helper backs both the ⊞ button and the C-Space z action (no duplicated logic)"

key-files:
  created: []
  modified:
    - src/arduis/window.py

key-decisions:
  - "Adw.ColorScheme.FORCE_DARK was NEWLY set in window.__init__ (not previously present in main.py or window.py) so Adw widgets render dark under all 4 dark palettes (A3)"
  - "Dead DRACULA_* imports + the keymap module import were dropped (resolution now via self._current_theme / self._keymap); the 8 _DOT_/_BG2 module constants kept only as documented dead fallbacks"
  - "win.set_theme persists the CANONICAL theme.name (get_theme re-whitelist) so an unknown slug that fell back persists 'dracula', never the raw target (T-05-03)"

patterns-established:
  - "Phase-5 config region in __init__ loads agent/keys/theme BEFORE _install_css so first paint is in the persisted theme"
  - "_read_keys_section: tolerant tomllib [keys] reader living in window.py (keyconfig takes raw values, not the file)"

requirements-completed: [AGENT-01, UI-01, UI-02]

# Metrics
duration: 5 min
completed: 2026-06-13
---

# Phase 5 Plan 03: window.py Wiring Summary

**Wired the three tested Phase-5 domains into window.py: the agent feed now comes from `[agent] command` (create/split/resume/refeed), the C-Space prefix machine reads `[keys]` (configurable prefix + bindings) and `_run_action` handles split/zoom/refeed, and a header "Tema" menu + `win.set_theme` switches the theme at runtime — replacing (not stacking) the CssProvider, re-coloring every live VTE, and persisting the choice.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-06-13T15:10:54Z
- **Completed:** 2026-06-13T15:15:25Z
- **Tasks:** 3 (all `type="auto"`)
- **Files modified:** 1 (`src/arduis/window.py`)

## Accomplishments
- **Configurable agent feed (AGENT-01):** `_make_wt_spawn_cb` builds the feed from `self._agent_config.command` via `agentconfig.resume_feed_bytes` (auto-suspend, `--continue` only for claude-family) / `agent_feed_bytes` (create/split/manual resume). Ctrl+C job control untouched.
- **Configurable prefix + bindings (UI-01):** `_on_key` arms on `self._prefix[0]` + CONTROL_MASK and dispatches via `self._keymap.get(name)` with the digit→jump fallback; the capture-phase controller registration is unchanged. `_run_action` now handles `split`/`zoom`/`refeed` on top of focus/worktree/jump.
- **split/zoom/refeed verbs:** `split` threads the orientation through `_split_active_pane(focused_id, orientation)` (default `"h"` keeps the ⊟ button working); `zoom` calls the new shared `_zoom_pane(sid)` (also used by the ⊞ button); `refeed` calls `_refeed_focused_agent()` which `feed_child`s the configured agent into the focused live PTY — no kill, no respawn (Pitfall 5).
- **Runtime theme switch (UI-02):** header `pack_end` MenuButton (`open-menu-symbolic`) with a "Tema" submenu of one `win.set_theme(slug)` per `THEMES` entry; `_apply_theme` removes the stored provider before adding a fresh one (Pitfall 1), re-colors every `_term_by_sid` VTE, and sets `self._current_theme`; `_on_set_theme` persists the canonical `theme.name` via `appconfig.write_theme`.
- **Theme-aware paint:** `_build_css(theme)` replaces the module `_CSS` f-string (classes identical, colors per-theme); `_install_css` keeps the `self._css_provider` handle; `_make_terminal` colors from `self._current_theme`; startup loads the persisted theme (Dracula fallback).

## Task Commits

Each task was committed atomically:

1. **Task 1: theme-aware window (per-theme CSS, replaceable provider, startup theme load)** — `1bb5532` (feat)
2. **Task 2: configurable agent feed + prefix/bindings + split/zoom/refeed verbs** — `3c6f282` (feat)
3. **Task 3: header Tema menu + win.set_theme action + runtime _apply_theme** — `c9acb1e` (feat)

## Files Created/Modified
- `src/arduis/window.py` — methods changed:
  - **Agent feed:** `_make_wt_spawn_cb` (selection now `agentconfig.resume_feed_bytes` / `agent_feed_bytes` of the configured command).
  - **Prefix machine:** `_on_key` (uses `self._prefix[0]` + `self._keymap` with digit→jump fallback); `_run_action` (+split/zoom/refeed branches).
  - **New helpers:** `_zoom_pane(sid)`, `_refeed_focused_agent()`, `_apply_theme(theme)`, `_on_set_theme(action, param)`; module-level `_build_css(theme)` and `_read_keys_section(path)`.
  - **Theme paint:** `_install_css` (keeps `self._css_provider`/`self._display`), `_make_terminal` (colors from `self._current_theme`), `_split_active_pane` (+`orientation="h"` param).
  - **`__init__`:** Phase-5 config region (`_config_path`, `_agent_config`, `_prefix`, `_keymap`, `_current_theme`, `_css_provider`, `_display`); `Adw.ColorScheme.FORCE_DARK`; header "Tema" MenuButton; `_install_row_actions` registers `win.set_theme`.
  - **Imports:** added `agentconfig`/`appconfig`/`keyconfig` + `THEMES`/`Theme`/`get_theme` + stdlib `tomllib`; dropped dead `DRACULA_*` and `keymap` module imports and the `AGENT_FEED`/`AGENT_RESUME_FEED` session imports.

## Decisions Made
- **`Adw.ColorScheme.FORCE_DARK` was NEWLY set** in `window.__init__` — it was not present in `main.py` or `window.py` before this plan (verified by grep). Set once after the config region, before `_install_css`.
- **Dead imports removed** to keep the module clean: `DRACULA_FG/BG/CURSOR/PALETTE` (no longer the color source — `_make_terminal` reads `self._current_theme`), the `keymap` module (dispatch is now `self._keymap`), and `AGENT_FEED`/`AGENT_RESUME_FEED` (feed is now built from `agentconfig`). The 8 `_DOT_*`/`_BG2` module constants stay as documented dead fallbacks per the plan.
- **`tomllib` imported into window.py** for the new `_read_keys_section` tolerant `[keys]` reader (keyconfig takes raw values, not the file, so the read lives next to the existing config reads).

## Deviations from Plan

None - plan executed exactly as written. The locked `<plan_decisions>` snippets were used verbatim (config region, `_build_css`, `_apply_theme`, the `_on_key` digit fallback, the `_make_wt_spawn_cb` feed selection, the header menu, the action registration). The only judgment calls were dropping now-dead imports (anticipated by the plan: "drop them to avoid a dead import (ruff)") and confirming `FORCE_DARK` was absent before setting it (the plan's "check main.py first" instruction).

**Total deviations:** 0.
**Impact on plan:** None — pure wiring on pinned contracts.

## Issues Encountered
None. `LayoutModel.split` already accepted an `orientation="h"` default, so threading the orientation through `_split_active_pane` needed no layout-model change.

## Known Stubs
None — no hardcoded empty data flows, placeholders, or unwired components introduced. All wiring connects live tested contracts.

## User Setup Required
None - no external service configuration required. The agent command, prefix/bindings, and theme are all read from the existing `~/.config/arduis/arduis.toml` with safe defaults; no file is required to exist.

## Next Phase Readiness
- All four Phase-5 roadmap criteria are now functionally complete in code. **Plan 04** runs the live UAT checklist: the visual theme switch (dracula→nord→dracula re-color + no provider stacking), the `C-Space` prefix arming under a native Wayland session (criterion 3 gate, `$XDG_SESSION_TYPE == wayland`), split/zoom/refeed chords, and the configured-agent feed on create/split/resume.
- Full suite green (240 passed, no regression). `window.py` parses and imports cleanly headless; all new methods present.

## Self-Check: PASSED

- `src/arduis/window.py` — FOUND on disk; imports cleanly headless; `_build_css`, `_read_keys_section`, `_apply_theme`, `_on_set_theme`, `_zoom_pane`, `_refeed_focused_agent` all present.
- Commit `1bb5532` (Task 1) — FOUND in git log.
- Commit `3c6f282` (Task 2) — FOUND in git log.
- Commit `c9acb1e` (Task 3) — FOUND in git log.
- Verification greps: `win.set_theme`=4 (≥2), `remove_provider_for_display`=1 (≥1), `agent_feed_bytes|resume_feed_bytes`=5 (≥2), `self._current_theme`=7 (≥3), `self._keymap|self._prefix`=8 (≥2).
- Full suite: 240 passed, exit 0.

---
*Phase: 05-agent-swap-tmux-keybindings-themes*
*Completed: 2026-06-13*
</content>
</invoke>
