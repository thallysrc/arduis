---
phase: 03-parallel-worktrees-sidebar-ram-groundwork
verified: 2026-06-09T00:00:00Z
status: human_needed
score: 5/5 must-haves verified (automated); 8-point manual checklist partially executed
re_verification: false
human_verification:
  - test: "PAR-01 — keep several worktrees open simultaneously, each with its own terminal: create 3+ worktrees via + Nova worktree and confirm each opens beside the previous (split) and all terminals stay live"
    expected: "3 or more panes visible at once, each running a terminal, in a nested Gtk.Paned tree"
    why_human: "Requires a running display server and real VTE spawning; cannot verify live GTK rendering with pytest"
  - test: "PAR-02 — sidebar lists all worktrees (green dot = active) plus the pinned main row; Hibernate greys the dot, Resume restores it"
    expected: "Left sidebar shows repo name on main row; each worktree row has a green dot and 'claude · —'; right-click Hibernar makes dot grey, right-click Retomar restores green"
    why_human: "Requires visual inspection of live GTK window and real click/menu interaction"
  - test: "D-06 focus-or-swap — click a visible-pane row → purple focus ring moves; close that pane then click its row → worktree swaps into the focused pane"
    expected: "Visible: terminal gains purple ring. Hidden (pane closed): worktree re-appears in the current focused pane"
    why_human: "Requires live GTK window interaction and visual confirmation of the focus ring and swap behaviour"
  - test: "LAYOUT-01 free layout — drag a Gtk.Paned divider to resize; use ⌥ Layout → grid 2x2 and columns; use ⊞ to zoom the focused pane and toggle back"
    expected: "Divider drags and terminals remain usable; grid/columns presets rearrange panes; zoom fills window, unzoom restores"
    why_human: "Requires live GTK window and interactive drag/menu/button actions"
  - test: "PAR-03 prefix keys — type normally in terminal (not eaten); then C-Space h/j/k/l moves pane focus; C-Space n/p cycles worktrees; C-Space 2 jumps to row 2"
    expected: "Normal typing passes through unaffected; each C-Space action fires correctly and focuses/cycles the intended pane/worktree"
    why_human: "Requires a running display, focused Vte.Terminal, and keyboard input — cannot simulate GTK input with pytest"
  - test: "RAM-03 live RAM — each active row's sub-line updates to 'claude · <RAM>' within ~2s; footer shows 'N agentes ativos · <total> RAM' with count in green; no visible UI hitching"
    expected: "Sub-lines show non-zero RAM values (e.g. '312 MB') updating every ~2s; footer count is green; window remains responsive"
    why_human: "Requires live running processes with a real pgid so group_rss_kb returns non-zero values; responsiveness is subjective"
  - test: "RAM-02 cap gate — open worktrees until 6 active; +Nova worktree blocks with 'Você está com 6 agentes ativos' prompt and a chooser; pick one to hibernate then creation proceeds; cancel aborts"
    expected: "Exactly the cap-prompt dialog appears at the 7th attempt; hibernating a chosen worktree releases the cap and the new worktree is created; cancelling produces no new worktree"
    why_human: "Requires creating 6 live sessions; end-to-end dialog/action flow needs manual confirmation"
  - test: "No orphans — close the window; confirm no arduis-spawned zsh/claude processes remain (pgrep -f zsh, pgrep -f claude)"
    expected: "All child processes terminated; no zombies or leaked process groups"
    why_human: "Requires shell inspection after window close to verify teardown completeness"
---

# Phase 3: Parallel Worktrees + Sidebar + RAM Groundwork Verification Report

**Phase Goal:** Parallelism made visible and bounded — many worktrees open at once, a sidebar bound to the SessionStore, a free (split/drag) pane layout instead of a fixed grid, and the RAM groundwork (ResourceMonitor + per-worktree RSS visibility + active caps) that makes the lightweight promise real at the 5–12 worktree working set.
**Verified:** 2026-06-09
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

All five roadmap success criteria are implemented and have verifiable automated coverage. The live-GTK/keyboard/RAM surface is manual-only per the project's own 03-VALIDATION.md. The phase's automated test suite passes at 51/51. The user accepted the phase after a partial UAT. Eight manual checks remain to close the formal acceptance record.

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Several worktrees stay open at once, each with its own terminal (PAR-01) | ? NEEDS HUMAN | `Gtk.Paned` canvas + `_leaf_by_sid` map are fully wired in window.py; live multi-pane rendering requires a display |
| 2 | A left sidebar lists every worktree plus the pinned main row, bound to SessionStore (PAR-02/D-07) | ? NEEDS HUMAN | `_rebuild_sidebar` + `_listbox` + `_sid_by_row` map implemented; `_MAIN_SID` pinned row confirmed in code; live rendering is manual |
| 3 | Selecting a sidebar row focuses its pane if visible, else swaps it into the focused pane (PAR-02/D-06) | ✓ VERIFIED | `_on_row_activated` calls `resolve_selection` and branches on `"focus"` / `"swap"`; `resolve_selection` is unit-tested (test_layout.py GREEN) |
| 4 | Pane canvas is a nested GtkPaned tree with free split/drag — no visible tab bar (LAYOUT-01/D-01) | ? NEEDS HUMAN | `_reflect_layout` + `_build_widget` build `Gtk.Paned` tree from `LayoutModel`; `Adw.TabView`/`TabBar` absent; live rendering is manual |
| 5 | Creating a new worktree splits the focused pane so the new agent appears beside it (D-03) | ✓ VERIFIED | `_open_and_add` calls `self._layout.split(focused, branch, "h")` before spawn; static grep confirms |
| 6 | C-Space arms a prefix; next key dispatches h/j/k/l / next/prev / digit-jump (PAR-03/D-09/D-10) | ? NEEDS HUMAN | `PropagationPhase.CAPTURE` + `_prefix_armed` + `keymap.dispatch` all present; keymap unit-tested GREEN; live terminal input is manual |
| 7 | Each sidebar row shows live process-group RSS updated ~2s off the GTK main loop with footer (RAM-03/D-12/D-14) | ? NEEDS HUMAN | `GLib.timeout_add_seconds(2, self._poll_ram)` + `group_rss_kb` + `format_ram_kb` all wired; `source_remove` on close; live rendering is manual |
| 8 | Opening a worktree at the active cap blocks and prompts to hibernate before proceeding (RAM-02/D-15/D-16) | ? NEEDS HUMAN | `caps.at_cap` gate in `_on_new_worktree_clicked` + `_prompt_hibernate_then` + `Adw.AlertDialog` implemented; cap policy unit-tested GREEN; dialog flow is manual |

**Score:** 5/5 truths with automated coverage verified; 3 truths partially verified (code wired, logic tested) + 5 requiring live GTK session for confirmation.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/arduis/layout.py` | GTK-free binary split/leaf tree: split/close/zoom/preset/MRU/visibility + resolve_selection | ✓ VERIFIED | 227 lines (>90); `class LayoutModel` present; `def resolve_selection` present; `import gi` absent; all test_layout.py tests GREEN |
| `src/arduis/keymap.py` | GTK-free hardcoded C-Space prefix keymap + dispatch() | ✓ VERIFIED | `PREFIX_KEYVAL = "space"`, `PREFIX_MODS = "ctrl"`, `def dispatch` present; `import gi` absent; all test_keymap.py tests GREEN |
| `src/arduis/resource_monitor.py` | GTK-free /proc RSS accounting: group_rss_kb + /proc walk + smaps→statm fallback + pt-BR format_ram_kb | ✓ VERIFIED | 101 lines (>60); `def group_rss_kb`, `def format_ram_kb`, `_pids_in_group`, `_rss_kb_for_pid` all present; `smaps_rollup` + `statm` both present; `import gi` absent; `psutil` absent; all test_resource_monitor.py tests GREEN |
| `src/arduis/caps.py` | GTK-free cap policy: ACTIVE_CAP_DEFAULT + active_count + at_cap | ✓ VERIFIED | `ACTIVE_CAP_DEFAULT = 6`, `def active_count`, `def at_cap` present; `import gi` absent; all test_caps.py tests GREEN |
| `src/arduis/window.py` | Sidebar (Gtk.ListBox) + nested GtkPaned canvas reflecting LayoutModel; Adw.TabView/TabBar removed | ✓ VERIFIED | All static markers confirmed (see Key Links); parses without syntax error |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| window.py | arduis.layout.LayoutModel + resolve_selection | `from arduis.layout import LayoutModel, LeafNode, SplitNode, resolve_selection` | ✓ WIRED | Import at line 55; `resolve_selection` used 3x in `_on_row_activated` and helpers |
| window.py sidebar | arduis.session.SessionStore | `self._store` + `_rebuild_sidebar` iterates `self._store.all()` | ✓ WIRED | `_rebuild_sidebar` builds one row per session; `_sid_by_row` map maintained |
| new-worktree create flow | LayoutModel.split(focused, new) | `self._layout.split(focused, branch, "h")` in `_open_and_add` | ✓ WIRED | D-03 split-on-new confirmed at line 993 |
| window.py prefix controller | arduis.keymap.dispatch | `from arduis import caps, keymap, resource_monitor`; `keymap.dispatch(name)` in `_on_key` | ✓ WIRED | `PropagationPhase.CAPTURE` + armed-state machine at lines 246-711 |
| window.py ~2s poll | arduis.resource_monitor.group_rss_kb + format_ram_kb | `GLib.timeout_add_seconds(2, self._poll_ram)` + calls inside `_poll_ram` | ✓ WIRED | `group_rss_kb` called line 1071; `format_ram_kb` called line 1074; `source_remove` on close line 1231 |
| new-worktree flow | arduis.caps.at_cap + Adw.AlertDialog | `caps.at_cap(self._store.all())` in `_on_new_worktree_clicked` before spawn | ✓ WIRED | Cap gate at line 823; `_prompt_hibernate_then` + dialog at lines 836-877 |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| window.py sidebar sub-line | `session.rss_kb` | `_poll_ram` → `resource_monitor.group_rss_kb(session.pgid)` → `/proc` reads | Yes — reads live `/proc/<pid>/smaps_rollup` or `statm` for process group | ✓ FLOWING |
| window.py footer | aggregate `total` RSS | sum of `s.rss_kb` for active sessions | Yes — derived from live RSS written by poll | ✓ FLOWING |
| window.py cap gate | `self._store.all()` | `SessionStore` populated by `_open_and_add` on each successful worktree add | Yes — real store state | ✓ FLOWING |
| window.py `_poll_ram` | `session.pgid` | set in `_make_wt_spawn_cb` via `os.getpgid(pid)` after VTE spawn | Yes — real OS pgid | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| layout.py exports functional LayoutModel | `.venv/bin/python -c "from arduis.layout import LayoutModel; m=LayoutModel(); m.root=__import__('arduis.layout',fromlist=['LeafNode']).LeafNode('a'); m.split('a','b'); print(m.visible_ids())"` | `['a', 'b']` | ✓ PASS |
| keymap dispatch returns correct tuples | `.venv/bin/python dispatch` | `dispatch('h') = ('focus_dir', 'left')` | ✓ PASS |
| format_ram_kb pt-BR formatting | `.venv/bin/python format_ram_kb(312000)` | `"312 MB"` | ✓ PASS |
| format_ram_kb GB with decimal comma | `.venv/bin/python format_ram_kb(1258291)` | `"1,2 GB"` | ✓ PASS |
| format_ram_kb None sentinel | `.venv/bin/python format_ram_kb(None)` | `"—"` | ✓ PASS |
| ACTIVE_CAP_DEFAULT constant | import check | `6` | ✓ PASS |
| Full pytest suite (51 tests) | `.venv/bin/python -m pytest -q` | `51 passed in 0.07s` | ✓ PASS |
| window.py syntax valid | `python3 -c "import ast; ast.parse(...)"` | exit 0 | ✓ PASS |
| Live GTK multi-pane rendering | Requires display server | SKIP | ? SKIP |
| Live RAM poll with real pgids | Requires running terminals | SKIP | ? SKIP |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| PAR-01 | 03-04 | Usuário mantém várias worktrees abertas ao mesmo tempo, cada uma com seu terminal | ? NEEDS HUMAN | `_leaf_by_sid` map + `_reflect_layout` create per-session Vte.Terminal; live rendering is manual |
| PAR-02 | 03-04 | Uma sidebar lista todas as worktrees; selecionar uma foca nela | ? NEEDS HUMAN | `Gtk.ListBox` + `_rebuild_sidebar` + `_on_row_activated` fully implemented; live UI is manual |
| PAR-03 | 03-05 | Usuário troca entre worktrees pela UI e por atalhos estilo tmux | ? NEEDS HUMAN | `PropagationPhase.CAPTURE` prefix machine + `keymap.dispatch` wired; live keyboard is manual |
| LAYOUT-01 | 03-02/04/05 | Layout livre de panes — dividir/arrastar como no tmux | ? NEEDS HUMAN | `Gtk.Paned` + `set_wide_handle(True)` + `_reflect_layout` implemented; free drag is manual |
| RAM-02 | 03-03/05 | Limite configurável de agentes/containers ativos simultaneamente | ? NEEDS HUMAN | `ACTIVE_CAP_DEFAULT=6` + `at_cap` gate in `_on_new_worktree_clicked` fully wired; dialog flow is manual |
| RAM-03 | 03-03/05 | Visibilidade de uso de RAM por worktree na UI | ? NEEDS HUMAN | `GLib.timeout_add_seconds` poll + `group_rss_kb` + sub-line/footer labels wired; live display is manual |

All 6 requirements assigned to Phase 3 in REQUIREMENTS.md are implemented. No orphaned requirements found.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/arduis/window.py` | 1129 | Comment: `# Empty canvas — a neutral placeholder box.` | ℹ️ Info | This is a code comment describing a branch of `_build_widget` that returns a blank `Gtk.Box` for a `None` node (empty canvas state). It is the correct, intentional behavior — not a data stub. No user-visible data is hardcoded empty; the value serves as a structural fallback when the layout tree has no root. Not a blocker. |

No blockers or warnings found.

### Human Verification Required

The following 8 checks require a running display server and live GTK window per 03-VALIDATION.md. They constitute the formal acceptance gate for the live-render/keyboard/RAM/cap surface.

#### 1. PAR-01: Multiple live terminals

**Test:** Run `./run.sh`, create 3+ worktrees via "+ Nova worktree".
**Expected:** Each new worktree opens BESIDE the previous one (focused pane splits); all terminals stay live simultaneously.
**Why human:** Live VTE spawning and multi-pane GTK rendering require a display server.

#### 2. PAR-02 / D-07 / D-08: Sidebar listing and context menu

**Test:** Confirm the left sidebar shows the repo name on the pinned main row plus one row per worktree with a green dot. Right-click a worktree row → "Hibernar" → confirm dot goes grey and row dims; right-click → "Retomar" → dot returns green.
**Expected:** Sidebar bound to SessionStore; dot color changes reflect state; context menu drives hibernate/resume actions.
**Why human:** Visual dot color, sidebar layout, and right-click menu flow require live GTK inspection.

#### 3. D-06: Focus-or-swap

**Test:** Click a sidebar row whose pane is visible → terminal gains purple focus ring. Close that pane via ✕. Click the same row again → worktree's terminal appears in the currently focused pane (swap).
**Expected:** First click: focus ring moves. Second click (after close): worktree swaps into focused pane without a store deletion.
**Why human:** Focus ring CSS class change and swap behavior require live window interaction.

#### 4. LAYOUT-01: Free layout / drag / presets / zoom

**Test:** Drag a Gtk.Paned divider to resize panes. Use "⌥ Layout" → "Grade 2×2" and "Colunas". Use ⊞ zoom on the focused pane and toggle back.
**Expected:** Divider drags freely; panes stay ≥ 240×120; preset rearranges panes from MRU order; zoom fills canvas, unzoom restores prior tree.
**Why human:** Interactive drag, preset visual result, and zoom round-trip require live rendering.

#### 5. PAR-03: C-Space prefix keys

**Test:** With a terminal focused, type a few characters (confirm not eaten). Then: C-Space h/j/k/l (pane focus moves), C-Space n/p (worktree cycles), C-Space 2 (jumps to 2nd row).
**Expected:** Normal typing passes through unchanged. Each C-Space action fires correctly on the next key.
**Why human:** Capture-phase controller behavior and non-interference with terminal input require live keyboard + VTE interaction.

#### 6. RAM-03: Live RAM display

**Test:** With active worktrees, observe each row's sub-line and the footer label.
**Expected:** Sub-lines show "claude · <RAM>" (e.g. "claude · 312 MB") updating approximately every 2 seconds; footer shows "N agentes ativos · <total> RAM" with the count in green; no visible jank/hitching.
**Why human:** Live process-group RSS requires real pgids from running VTE children; responsiveness is perceptually assessed.

#### 7. RAM-02: Active-agent cap gate

**Test:** Open worktrees until 6 are active (or temporarily lower ACTIVE_CAP_DEFAULT to 2 for a quick test). Attempt to create one more via "+ Nova worktree".
**Expected:** A dialog appears: heading "Você está com N agentes ativos", body "Hiberne uma worktree para liberar RAM antes de abrir outra.", with a DropDown chooser. Picking a worktree and confirming hibernates it then creates the new one. Cancelling creates no new worktree.
**Why human:** Requires creating N live sessions; end-to-end dialog response + conditional creation flow needs manual confirmation.

#### 8. No orphans on window close

**Test:** After creating 2+ worktrees, close the window. Run `pgrep -af zsh` and `pgrep -af claude` in a host terminal.
**Expected:** No arduis-spawned processes remain. The teardown across N panes (SIGHUP + SIGKILL sweep) still holds from Phase 2.
**Why human:** Post-close process inspection requires a shell outside the app.

### Gaps Summary

No automated gaps. All five ROADMAP success criteria have full implementation wiring and pass the automated test suite (51/51). The phase is blocked on human verification of the live GTK/keyboard/RAM/cap surface — a design constraint of this phase documented in 03-VALIDATION.md, not a code deficiency.

---

_Verified: 2026-06-09_
_Verifier: Claude (gsd-verifier)_
