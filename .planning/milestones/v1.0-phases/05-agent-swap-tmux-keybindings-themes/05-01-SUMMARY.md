---
phase: 05-agent-swap-tmux-keybindings-themes
plan: 01
subsystem: ui
tags: [themes, vte, palette, dataclass, gtk-free, dracula, nord, solarized, gruvbox]

# Dependency graph
requires:
  - phase: 04-attention-detection
    provides: "the GTK-free domain-module + tomllib config pattern this registry mirrors"
provides:
  - "src/arduis/themes.py — a frozen Theme dataclass + THEMES registry (4 dark themes) + get_theme whitelist"
  - "The exact color contract window.py (Plan 03) reads at apply time: bg/fg/cursor/palette + surface/accent/branch + 5 status dots"
  - "16-color + valid-hex invariants protecting Vte.Terminal.set_colors, pinned by tests"
affects: [05-03 (window.py reads Theme fields), 05-02 (appconfig persists [theme] name), UI-02]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "GTK-free frozen dataclass registry keyed by slug (mirrors theme.py / keymap.KEYMAP)"
    - "Closed dict-whitelist lookup degrading to a safe default (get_theme -> DRACULA), never a path"
    - "Default palette imported verbatim from theme.py (single source of truth, no re-typing)"

key-files:
  created:
    - src/arduis/themes.py
    - tests/test_themes.py
  modified: []

key-decisions:
  - "No separate focus_ring field — accent IS the focus ring (window._CSS used the same value for both); window.py maps accent onto ring + badge"
  - "palette is a tuple[str, ...] (frozen dataclass) of exactly 16 entries; DRACULA builds palette=tuple(DRACULA_PALETTE) from theme.py so the default look can't desync"
  - "get_theme is THEMES.get((name or 'dracula').lower(), DRACULA) — case-insensitive whitelist, name never used as a filesystem path (T-05-03)"

patterns-established:
  - "Theme dataclass field contract: name, display_name, bg, fg, cursor, palette(16), surface, accent, branch, dot_active, dot_waiting, dot_ready, dot_idle, dot_hibernated"
  - "Slugs are the closed set: dracula, nord, solarized-dark, gruvbox-dark"

requirements-completed: [UI-02]

# Metrics
duration: 4 min
completed: 2026-06-13
---

# Phase 5 Plan 01: GTK-free Theme Registry Summary

**A frozen `Theme` dataclass + `THEMES` registry of 4 dark themes (Dracula default + Nord + Solarized Dark + Gruvbox Dark) with a `get_theme(name)` closed whitelist that always degrades to Dracula, carrying both the 16-color VTE palette and every UI color `window._CSS` hardcodes — GTK-free, with the 16-color/valid-hex `set_colors` invariants pinned by tests.**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-06-13
- **Completed:** 2026-06-13
- **Tasks:** 1 (TDD: RED + GREEN)
- **Files modified:** 2 (both created)

## Accomplishments
- `src/arduis/themes.py` — GTK-free `Theme` frozen dataclass + `THEMES` dict + `get_theme` whitelist (no `gi`/`Gdk` import; whole suite runs without GTK/Vte).
- Dracula is byte-identical to `theme.py`: `bg/fg/cursor/palette` are imported from the existing `DRACULA_*` constants, so the default look can never shift.
- 4 dark themes keyed by slug — `dracula`, `nord`, `solarized-dark`, `gruvbox-dark` — each with the full union of VTE palette + UI colors.
- The two `set_colors`-protecting invariants (exactly 16 palette colors; every color field matches `^#[0-9a-fA-F]{6}$`) are proven by tests over every theme (Pitfall 6 / T-05-06a).
- `get_theme` closed whitelist: `None`/`""`/`"nope"`/wrong-case all return `DRACULA`; the name is never used to build a path (T-05-03).

## The Theme field contract (what window.py Plan 03 reads)

`Theme(name, display_name, bg, fg, cursor, palette, surface, accent, branch, dot_active, dot_waiting, dot_ready, dot_idle, dot_hibernated)` where:
- `name` = slug (`"dracula"`, `"solarized-dark"`); `display_name` = menu label (`"Dracula"`, `"Solarized Dark"`).
- `palette` = `tuple[str, ...]` of EXACTLY 16 `#rrggbb` ANSI colors (the `set_colors` contract).
- `bg`/`fg`/`cursor` = the VTE foreground/background/cursor.
- `surface` (was `_BG2`), `accent` (was `_FOCUS_RING` — IS the focus ring + badge + hint-key; **no separate `focus_ring` field**), `branch` (was `_BRANCH_PINK`), and the 5 status-dot colors (`dot_active`/`dot_waiting`/`dot_ready`/`dot_idle`/`dot_hibernated`) are the UI colors `window._CSS` hardcodes today.

The 4 slugs: `dracula` (default), `nord`, `solarized-dark`, `gruvbox-dark`.

## Task Commits

1. **Task 1 (RED): failing tests for the registry** - `23f831e` (test)
2. **Task 1 (GREEN): Theme dataclass + THEMES + get_theme** - `89ad5f3` (feat)

No REFACTOR commit — the implementation is the locked plan contract and needed no cleanup.

## Files Created/Modified
- `src/arduis/themes.py` - Frozen `Theme` dataclass, `DRACULA`/`NORD`/`SOLARIZED_DARK`/`GRUVBOX_DARK` instances, `THEMES` registry, `get_theme` whitelist. GTK-free; imports `DRACULA_*` from `arduis.theme`.
- `tests/test_themes.py` - 13 tests: registry shape (4 slugs), get_theme fallbacks (None/empty/unknown/case-insensitive/known), name==slug coherence, 16-color invariant, valid-hex invariant over every field + palette entry, non-empty display_name, Dracula fidelity vs theme.py, GTK-free source assertion, frozen-dataclass assertion.

## Decisions Made
- **`accent` IS the focus ring** — `window._CSS` used the same `_FOCUS_RING` value for both the ring and the badge, so there is no separate `focus_ring` field; window.py maps `accent` onto both. (Followed plan.)
- **Default palette imported, never re-typed** — `DRACULA.palette = tuple(DRACULA_PALETTE)` from `theme.py`, so a later edit to `theme.py` cannot desync the default. (Followed plan.)
- **`get_theme` is a pure dict whitelist** — `THEMES.get((name or "dracula").lower(), DRACULA)`; the name never touches the filesystem (T-05-03). (Followed plan.)

## Hex Fidelity vs RESEARCH DESIGN tables (for Plan 04 UAT)

All non-Dracula palettes (Nord, Solarized Dark, Gruvbox Dark — palette + UI colors) were entered **verbatim from 05-RESEARCH §DESIGN** with no deviations. Dracula matches `theme.py` verbatim. Per Assumption A1, the 3 non-Dracula palettes are training-recalled from each project's published spec; a wrong shade is cosmetic (Pitfall 6's parse guard + the valid-hex test prevent a crash). **No hex differed from the RESEARCH tables — Plan 04 UAT should still eyeball the 3 non-Dracula palettes against their upstream specs.**

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The color contract is locked and test-pinned. **Plan 03 (window.py)** can read every UI/VTE color from the active `Theme` (`_make_terminal` -> `self._current_theme`; `_build_css` from theme fields) and convert hex -> `Gdk.RGBA` at apply time.
- **Plan 02 (appconfig)** can validate the `[theme] name` slug against the same closed set / `get_theme` whitelist.
- Full GTK-free suite green: 185 passed (172 baseline + 13 new).

## Self-Check: PASSED

- `src/arduis/themes.py` — FOUND on disk; contains `THEMES`, `get_theme`, frozen `Theme`; 0 `gi` imports.
- `tests/test_themes.py` — FOUND on disk; 13 tests pass.
- Commit `23f831e` (test RED) — FOUND in git log.
- Commit `89ad5f3` (feat GREEN) — FOUND in git log.
- Full suite: 185 passed (baseline 172 + 13 new), exit 0.

---
*Phase: 05-agent-swap-tmux-keybindings-themes*
*Completed: 2026-06-13*
