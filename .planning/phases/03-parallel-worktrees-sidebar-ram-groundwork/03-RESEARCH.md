# Phase 3: Parallel Worktrees + Sidebar + RAM Groundwork - Research

**Researched:** 2026-06-09
**Domain:** GTK4 widget-tree management (nested `GtkPaned`), GTK4 keyboard event handling (tmux-style prefix), Linux `/proc` RSS accounting, decoupled view/model design
**Confidence:** HIGH (all GTK4/VTE/`/proc` APIs verified on the host at the exact 0.76/GTK4.14 floor)

## Summary

Phase 3 is mechanically the highest-uncertainty phase so far, but the uncertainty is almost entirely about **which GTK4 idiom to pick**, not whether the platform supports it. Every load-bearing API — `Gtk.Paned` child get/set/replace, the GTK4 widget-tree walk (`get_first_child`/`get_next_sibling`/`get_parent`/`unparent`), `Gtk.EventControllerKey` capture-phase key handling, `Gtk.ListBox.bind_model`, `GLib.timeout_add_seconds`, and `/proc/<pid>/smaps_rollup` + `/proc/<pid>/stat` — was verified present and working on the host (VTE 0.76.0, GTK 4.14.5, libadwaita 1.5, Python 3.12.3) `[VERIFIED: host probe 2026-06-09]`. There is no missing capability and no new runtime dependency: the whole phase is buildable with the stdlib + system PyGObject the project already ships.

The architecture splits cleanly along the project's existing GTK-free seam. Three new **GTK-free, pytest-testable** modules carry the real logic — a **layout model** (a binary tree of split/leaf nodes that mirrors the eventual `GtkPaned` tree but holds no widgets), a **`ResourceMonitor`** (`/proc` parsing + process-group RSS summation), and a **cap policy** (a pure function over the `SessionStore`). `window.py` stays the only `gi`-importing presentation module: it reflects the layout model into actual `Gtk.Paned`/`Vte.Terminal` widgets, runs the `~2s` poll through a `GLib.timeout` + `Gio.Subprocess`-style off-loop read, and renders the sidebar/footer.

The single most important design call is the **tmux `C-Space` prefix state machine**: a prefix-then-key sequence (`C-Space` then a bare `h`) is a *two-event* interaction that `Gtk.ShortcutController`'s single-trigger model fits poorly. Use a **`Gtk.EventControllerKey` in the CAPTURE phase on the `Adw.ApplicationWindow`** holding a tiny GTK-free dispatcher (`armed: bool` + a keymap dict). This keeps the keymap constants in one GTK-free place Phase 5 can wrap in config without reshaping the dispatcher (D-10), and sidesteps the ShortcutController scope/native-surface caveats.

**Primary recommendation:** Build the layout tree, ResourceMonitor, and cap policy as three GTK-free modules with full pytest coverage; reflect the layout tree into `Gtk.Paned` in `window.py`; implement the prefix via a capture-phase `EventControllerKey` + GTK-free keymap; sum process-group RSS from `smaps_rollup` (fall back to `statm`) on a `~2s` `GLib.timeout`; enforce the cap with a pure policy function and the `Adw.AlertDialog` chooser per the UI-SPEC copy.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Pane layout (LAYOUT-01, PAR-01)**
- **D-01:** Multi-pane area is a single splittable canvas built from **nested `GtkPaned`** (binary, draggable dividers — tmux-style free splits), filling the main content area. **Replaces the Phase-2 `Adw.TabView`/`TabBar`** entirely; no visible tab bar. Tree shape: `GtkPaned ▸ GtkPaned ▸ Vte.Terminal`.
- **D-02:** **Sidebar and panes are decoupled** — sidebar holds **all** worktrees; pane canvas shows a **subset**. A worktree can be **active (agent running) without occupying a visible pane**.
- **D-03:** **Creating a new worktree splits the focused pane**, so the new agent shows immediately beside the current one.
- **D-04:** Phase 3 ships, beyond manual split/drag/close: a **zoom-focus toggle** (fullscreen the focused pane) **and preset layouts** (grid 2×2, columns). When a preset shows fewer cells than active worktrees, which subset fills the cells is **Claude's discretion** (suggest most-recently-focused).

**Sidebar (PAR-02)**
- **D-05:** Each sidebar row shows a **state dot + branch name + a RAM sub-line**. In Phase 3 the dot means **active (green) vs hibernated (grey)** only; Phase 4 enriches the same dot — do not build status semantics here.
- **D-06:** **Selecting a sidebar row focuses its pane if the worktree is already visible; otherwise it swaps that worktree into the currently-focused pane.**
- **D-07:** The **Phase-1/2 `$HOME` scratch shell appears as a pinned `main` sidebar entry** — always present, **not** a worktree session.
- **D-08:** **Hibernate/Resume move to the sidebar row's right-click context menu**, reusing the existing Phase-2 `win.hibernate`/`win.resume` actions + `SessionStore` transitions. Hibernated dimming/badge moves from the tab to the sidebar row.

**Switching shortcuts (PAR-03; full system is Phase 5 / UI-01)**
- **D-09:** Phase 3 ships keyboard switching for: **directional pane-focus move (`h/j/k/l`), worktree next/prev cycling, and jump-to-worktree by number**.
- **D-10:** **Build the tmux `C-Space` prefix mechanism now** (the prefix state machine) with **hardcoded** bindings. Keymap constants should live in a **single GTK-free place** so Phase 5 can wrap them in config without reshaping the dispatcher.
- **D-11:** Use **app-scoped** bindings from the start, but the **"works under real Wayland, not just XWayland" acceptance gate is Phase 5 (UI-01 SC#3)** — not duplicated as a Phase-3 gate.

**RAM groundwork (RAM-03 visibility, RAM-02 cap)**
- **D-12:** The per-worktree RAM number is the **whole process-group RSS** (`zsh` + `claude` + children), summed via the **`pgid` already tracked on `WorktreeSession`**.
- **D-13:** The `ResourceMonitor` **reads `/proc` directly** (`/proc/<pid>/stat` + `smaps_rollup`, walking the process group) — **zero new dependency**, GTK-free, Linux-only. **Not psutil.**
- **D-14:** RAM shown on **each sidebar row's sub-line** plus an **aggregate "N active · total RAM" footer**. Poll cadence **~2s** (exact value + format/units are Claude's discretion); polling must run **off the GTK main loop / not block it**.
- **D-15:** A **configurable cap on simultaneously active (non-hibernated) agents** enforced when opening a new worktree. **Default ~6, configurable.** Phase 3 stores it as an **interim app-level setting/constant** (exact storage is Claude's discretion; must be a **single place Phase 6 can source from `.arduis.toml`**).
- **D-16:** **Enforcement at the cap = prompt to hibernate one first.** Block launching, prompt, user picks which to hibernate, then creation proceeds. Not a silent allow, not create-hibernated.

### Claude's Discretion
- Exact `GtkPaned` tree management (how splits/closes mutate the tree; min pane size; focus tracking) and how the "decoupled" hidden-worktree set is represented.
- Preset-layout subset selection when worktrees > cells (suggest most-recently-focused).
- `ResourceMonitor` poll cadence (~2s), RSS aggregation details, and RAM display format/units.
- Interim cap-setting storage mechanism (constant vs simple app setting) — must be Phase-6 sourceable.
- Sidebar visual details (row height, dot styling, footer layout) within the Dracula palette.
- Whether closing a pane hibernates vs just hides the worktree (default: **hide** — the worktree stays active in the sidebar; hibernate stays an explicit action per D-08).

### Deferred Ideas (OUT OF SCOPE)
- **Attention status (running/waiting/idle/ready) dots + hooks-first watcher** → **Phase 4** (STATUS-01/02/03). Phase-3 dot is active-vs-hibernated only.
- **Idle auto-suspend** → **Phase 4 (RAM-04)**.
- **Full configurable keybindings + split/zoom chords + Wayland-not-XWayland gate** → **Phase 5 (UI-01)**. **Theme switching** → **Phase 5 (UI-02)**.
- **`.arduis.toml` cap/config + setup commands** → **Phase 6** (Phase 3 uses an interim app-level cap setting it can later source from the file).
- **Containers + their share of the active cap + port badges** → **Phase 7**.
- **Conclude/remove worktree + teardown ordering + diff/PR** → **Phase 8**. Phase 3 only hibernates (keeps the dir).
- **Persist layout / reopen worktrees across an arduis quit→restart** → **v2 (PERSIST-01)**.
- **Drag worktrees from the sidebar into specific panes** (vs the D-06 focus-or-swap default) → revisit if focus-or-swap proves limiting.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PAR-01 | Múltiplas worktrees abertas ao mesmo tempo, cada uma com seu terminal | Nested `GtkPaned` canvas (Architecture Pattern 1) hosts N `Vte.Terminal` widgets simultaneously; the visible-pane subset is a layout-tree concern decoupled from the full `SessionStore` (D-02). |
| PAR-02 | Sidebar lista todas as worktrees; selecionar foca | `Gtk.ListBox` driven from `SessionStore` (Pattern 4); D-06 focus-or-swap dispatch resolves a row selection to either focusing an existing pane or swapping into the focused pane. Pinned `main` row (D-07). |
| PAR-03 | Troca entre worktrees via UI e atalhos estilo tmux | `Gtk.EventControllerKey` capture-phase prefix state machine (Pattern 3); GTK-free keymap dispatcher for `h/j/k/l`, next/prev, jump-by-number. |
| LAYOUT-01 | Layout livre de panes — dividir/arrastar como tmux | Binary nested `GtkPaned` tree + a GTK-free layout model that drives splits/closes/presets/zoom (Pattern 1 + Pattern 2). |
| RAM-02 | Limite configurável de agentes ativos | GTK-free cap policy (pure function over `SessionStore`); interim module-level constant Phase 6 sources from `.arduis.toml`; `Adw.AlertDialog` prompt-to-hibernate (D-15/D-16). |
| RAM-03 | Visibilidade de RAM por worktree na UI | `ResourceMonitor` reads `/proc/<pid>/smaps_rollup` (fallback `statm`), walks the process group by `pgid`, writes `rss_kb` back onto each `WorktreeSession`; rendered in row sub-line + footer (Pattern 5). |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

These have the same authority as locked decisions. Plans must not contradict them.

- **Strict GTK-free core:** only `window.py` may import `gi`. The new layout model, `ResourceMonitor`, cap policy, and keymap/dispatcher constants **must be GTK-free and pytest-covered**. (`git_service.py` is the one thin `gi`-importing *service* exception; mirror its pattern, do not add more.)
- **Never block the GTK main loop.** The `~2s` RAM poll must read `/proc` off the loop. Use `GLib.timeout_add_seconds` to schedule, and do the actual read either via `Gio.Subprocess` (mirroring `git_service.run_git_async`) or a short non-blocking file read scheduled so it cannot stall the loop. **No `threading`, no `asyncio`** (mixing two event loops in a GTK app is a CLAUDE.md-forbidden footgun).
- **No new runtime dependency.** `psutil` is explicitly rejected (D-13) — it would have to be declared in the `.deb`/AUR packages. Use stdlib `/proc` parsing only. `[VERIFIED: grep — no psutil import anywhere in src/ or pyproject.toml]`
- **VTE 0.76 API floor.** One codebase for Ubuntu 0.76 / Arch 0.84. Do not call VTE/GTK APIs newer than the 0.76/GTK-4.x floor without a guard. (All Phase-3 GTK widgets used here — `Gtk.Paned`, `Gtk.ListBox`, `Gtk.EventControllerKey` — are GTK-4.0-era and predate the floor; safe.)
- **App owns the palette (Dracula).** Sidebar chrome, dots, focused-pane ring, and footer mirror `theme.py` hexes via a `Gtk.CssProvider`; no theme switching (Phase 5).
- **Build argv as lists via `HostRunner`**, never shell strings — unchanged; the spawn/teardown wiring is reused verbatim.
- **GSD workflow enforcement:** edits go through a GSD command, not ad-hoc.

## Standard Stack

No new packages. Everything is system PyGObject + Python stdlib already in use.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| PyGObject (`python3-gi`) | system | GTK4/GLib/Vte bindings | Project mandate; distro package, not pip `[CITED: CLAUDE.md]` |
| GTK4 | 4.14.5 (host) / 4.x floor | `Gtk.Paned`, `Gtk.ListBox`, `Gtk.EventControllerKey`, `Gtk.CssProvider` | All used widgets are GTK-4.0-era — under the floor `[VERIFIED: host probe]` |
| libadwaita | 1.5 (host) | `Adw.ApplicationWindow`/`ToolbarView`/`HeaderBar`/`AlertDialog` | Shell + cap-prompt dialog `[VERIFIED: host probe]` |
| VTE (Vte-3.91) | 0.76 floor | One `Vte.Terminal` per pane (reused `_make_terminal` factory) | Project mandate `[CITED: CLAUDE.md]` |
| Python stdlib `os` | 3.12 | `/proc` reads, `os.getpgid`, process-group enumeration | Zero-dep RAM accounting (D-13) |
| GLib (via PyGObject) | system | `timeout_add_seconds` for the poll; main-loop integration | Project's primary concurrency tool `[CITED: CLAUDE.md]` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `Gio.Subprocess` | system | Optional: read `/proc` files off-loop the same way `git_service` reads git | If a per-pid read must be fully off the GTK loop (see Pitfall 4) |
| `dataclasses` (stdlib) | 3.12 | Layout-node + monitor-sample model types | Mirrors `WorktreeSession` — serializable, GTK-free |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `/proc` parsing | `psutil` | REJECTED by D-13 — new runtime dep in `.deb`/AUR; `/proc` covers the exact need (RSS by pid) in ~20 lines |
| `Gtk.EventControllerKey` for the prefix | `Gtk.ShortcutController` | ShortcutController is single-trigger; a prefix→key *sequence* is two events. ShortcutController has GLOBAL/MANAGED scope + native-surface caveats that complicate app-wide capture. Use EventControllerKey for the **prefix sequence**; keep ShortcutController only for the existing single-chord clipboard shortcuts `[VERIFIED: docs.gtk.org + host probe]` |
| Nested `GtkPaned` tree | `Gtk.Grid` fixed grid | D-01 explicitly rejects a fixed grid; `GtkPaned` gives draggable free splits (tmux feel) |
| `Gtk.ListBox` sidebar | `Gtk.ListView` + factory | `ListView` is the newer scalable path, but at the 5–12 working set `ListBox` + `bind_model` (or manual rows) is simpler, fully under the floor, and easier to style per-row for the dot+sub-line `[VERIFIED: host probe — bind_model present]` |

**Installation:** none — `apt install` / AUR deps already declared in Phase 1/9 packaging; no `pip` additions.

**Version verification:** Host probe 2026-06-09 confirms `gir1.2-vte-3.91` **0.76.0-1ubuntu0.1**, GTK **4.14.5**, libadwaita **1.5**, Python **3.12.3**. `/proc/self/smaps_rollup` present and readable. `[VERIFIED: host probe]`

## Architecture Patterns

### Recommended Project Structure
Three new GTK-free modules + extensions to existing files. Keeps the Presentation→Domain→Service split intact.

```
src/arduis/
├── window.py          # ONLY gi module. Adw.TabView/TabBar REMOVED → sidebar + GtkPaned canvas.
│                      #   Reflects layout model into Gtk.Paned; runs the poll timeout; renders rows/footer.
├── layout.py          # NEW, GTK-free. Binary split/leaf tree: split/close/collapse, focus tracking,
│                      #   zoom toggle, preset rebuild, visible-pane subset. Pure data — no widgets.
├── resource_monitor.py# NEW, GTK-free. /proc parsing: process-group RSS sum (smaps_rollup → statm fallback),
│                      #   pgid walk. Pure functions over pids + a sample dataclass.
├── caps.py            # NEW, GTK-free. cap policy (pure fn over SessionStore) + interim ACTIVE_CAP constant
│                      #   (single Phase-6-sourceable place) + keymap constants live here or in keymap.py.
├── keymap.py          # NEW, GTK-free. Hardcoded C-Space prefix keymap (D-10) + dispatch logic (pure).
├── session.py         # EXTEND: SessionStore gains visibility/last-focused helpers if the layout model
│                      #   doesn't own them; rss_kb already present (Phase-2 reserved).
├── git_service.py     # UNCHANGED pattern; ResourceMonitor's off-loop read mirrors run_git_async.
├── theme.py, spawn.py, host_runner.py, exit_status.py, worktree.py  # UNCHANGED seams, reused.
└── swarm/             # untouched seam dir.
tests/
├── test_layout.py            # NEW — split/close/collapse/zoom/preset/focus invariants
├── test_resource_monitor.py  # NEW — /proc parse against fixture files + tmpdir fakes
├── test_caps.py              # NEW — cap policy boundary cases
├── test_keymap.py            # NEW — prefix dispatch table (armed/disarmed, h/j/k/l, next/prev, digit)
└── (existing) test_session/spawn/theme/host_runner/exit_decode/worktree
```

### Pattern 1: Nested binary `GtkPaned` tree (D-01, LAYOUT-01)
**What:** The pane canvas is a binary tree where internal nodes are `Gtk.Paned` and leaves are pane widgets (each a small container: pane-header + `Vte.Terminal`). Splitting a focused leaf replaces it with a `Gtk.Paned` whose two children are the old leaf and a new leaf.

**When to use:** Always, for the canvas — replaces Phase-2 `Adw.TabView`.

**Key verified API facts** `[VERIFIED: host probe + CITED: docs.gtk.org/gtk4/class.Paned.html]`:
- `Gtk.Paned` has exactly two slots: `set_start_child(w)` / `set_end_child(w)` (and `get_*`). A child may itself be a `Gtk.Paned` → nesting works.
- **Removing/replacing a child:** `set_start_child(None)` / `set_end_child(None)` detaches it. To move a widget from one parent to another, the GTK4 pattern is to `unparent()` it (or let `set_*_child(None)` drop the ref) before reparenting — a widget can only have one parent.
- **Minimum pane size:** set `set_shrink_start_child(False)` / `set_shrink_end_child(False)`. With shrink false, the child cannot go below its requested size, so set the leaf's `set_size_request(240, 120)` to enforce the UI-SPEC floor (~240px wide / ~120px tall). `[CITED: docs.gtk.org/gtk4/class.Paned.html]`
- `set_wide_handle(True)` gives a visible draggable gutter; `set_position()` controls the divider.
- **Tree walking** uses the GTK4 child API: `get_first_child()` / `get_next_sibling()` / `get_parent()` / `unparent()` — all verified present. (No GTK3 `get_children()`.)

**Split algorithm:**
```python
# In window.py — reflecting a layout-model split into widgets.
# focused_leaf is the pane container currently focused.
parent = focused_leaf.get_parent()          # a Gtk.Paned, or the canvas root slot
new_paned = Gtk.Paned(orientation=orientation)  # HORIZONTAL = side-by-side
new_paned.set_wide_handle(True)
new_paned.set_shrink_start_child(False)
new_paned.set_shrink_end_child(False)
# detach focused_leaf from its parent FIRST (single-parent rule)
if isinstance(parent, Gtk.Paned):
    if parent.get_start_child() is focused_leaf:
        parent.set_start_child(None)
        new_paned.set_start_child(focused_leaf)
        new_paned.set_end_child(new_leaf)
        parent.set_start_child(new_paned)
    else:
        parent.set_end_child(None)
        new_paned.set_start_child(focused_leaf)
        new_paned.set_end_child(new_leaf)
        parent.set_end_child(new_paned)
else:  # focused_leaf was the lone root → make new_paned the root
    canvas_slot.set_child(None)
    new_paned.set_start_child(focused_leaf)
    new_paned.set_end_child(new_leaf)
    canvas_slot.set_child(new_paned)
```

**Close-and-collapse:** when a leaf closes, its sibling must take the parent `Gtk.Paned`'s place (a `Gtk.Paned` with one child is degenerate). Detach the surviving sibling, then put it where the parent `Gtk.Paned` was (its grandparent slot or the root).

**Crucial decoupling (D-02, Claude's discretion):** keep all this tree mutation logic in **`layout.py` as a pure data tree** (`LeafNode(session_id)` / `SplitNode(orientation, start, end)`), and have `window.py` *reflect* the model tree into widgets. The benefit:
- The visible-pane subset is just "which `session_id`s appear as leaves in the tree" — a worktree can be active in `SessionStore` without being a leaf (D-02).
- Splits/closes/presets/zoom are tested in `test_layout.py` with **zero GTK** (Validation Architecture).
- Preset rebuild (D-04) = throw away the tree, build a fresh balanced tree from the most-recently-focused N session_ids that fill the preset's cell count.

### Pattern 2: Zoom-focus toggle + preset layouts (D-04)
**What:** Zoom = remember the current tree, then show only the focused leaf filling the canvas; un-zoom restores the saved tree. Preset = rebuild the tree into a canonical shape (2×2 = a `Gtk.Paned(VERTICAL)` of two `Gtk.Paned(HORIZONTAL)`; columns = a chain of `Gtk.Paned(HORIZONTAL)`).

**When to use:** the `⊞` pane-header control and `⌥ Layout` menu (UI-SPEC).

**Pattern:** model both as **pure tree transforms in `layout.py`**: `zoom(tree, focused) -> tree'` (and a saved `pre_zoom` snapshot) and `preset_grid_2x2(session_ids) -> tree`. `window.py` re-reflects. Subset selection when worktrees > cells: take the **most-recently-focused** ids (track a focus-order list in the layout model) — locked as the suggested heuristic by D-04.

### Pattern 3: tmux `C-Space` prefix state machine (D-09/D-10/D-11) — THE key decision
**What:** A two-step keyboard interaction (`Ctrl+Space`, then a bare key) cannot be expressed as a single `Gtk.ShortcutTrigger`. Implement it as a small state machine fed by a **capture-phase `Gtk.EventControllerKey` on the `Adw.ApplicationWindow`**.

**Why EventControllerKey, not ShortcutController** `[VERIFIED: docs.gtk.org + WebSearch cross-checked]`:
- ShortcutController activates one trigger→action; a prefix *sequence* is two distinct key events with a mode in between.
- ShortcutController GLOBAL/MANAGED scopes carry native-surface caveats ("event controllers used for managed/global scopes are limited to the same native") `[CITED: docs.gtk.org/gtk4/class.ShortcutController.html]` — awkward for clean app-wide capture.
- An EventControllerKey in the **CAPTURE** phase on the window sees keys *before* the focused `Vte.Terminal` consumes them, so the prefix is intercepted even while a terminal has focus. Set `set_propagation_phase(Gtk.PropagationPhase.CAPTURE)` `[VERIFIED: PropagationPhase.CAPTURE present on host]`.

**State machine (GTK-free dispatch in `keymap.py`, thin GTK glue in `window.py`):**
```python
# keymap.py — GTK-free. Phase 5 wraps these constants in config (D-10).
PREFIX_KEYVAL = "space"; PREFIX_MODS = "ctrl"   # C-Space
# action names, not GTK objects — the dispatcher returns an action string
KEYMAP = {
    "h": ("focus_dir", "left"), "j": ("focus_dir", "down"),
    "k": ("focus_dir", "up"),   "l": ("focus_dir", "right"),
    "n": ("worktree", "next"),  "p": ("worktree", "prev"),
    # digits 1..9 → ("jump", N) handled in dispatch()
}
def dispatch(key: str) -> tuple | None:
    if key.isdigit() and key != "0":
        return ("jump", int(key))
    return KEYMAP.get(key)
```
```python
# window.py — capture-phase controller on the window.
self._prefix_armed = False
kc = Gtk.EventControllerKey()
kc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
kc.connect("key-pressed", self._on_key)   # (controller, keyval, keycode, state)->bool
self.add_controller(kc)

def _on_key(self, _ctrl, keyval, _code, state):
    name = Gdk.keyval_name(keyval)
    if not self._prefix_armed:
        if name == "space" and (state & Gdk.ModifierType.CONTROL_MASK):
            self._prefix_armed = True
            return True            # swallow the prefix
        return False               # let the terminal have the key
    # armed: interpret the next key, then disarm
    self._prefix_armed = False
    action = keymap.dispatch(name)
    if action:
        self._run_action(action)   # focus_dir / worktree next-prev / jump
        return True                # swallow — don't leak into the terminal
    return False
```
**D-09 coverage:** `focus_dir h/j/k/l` (directional pane focus — resolve against the layout tree's geometry), `worktree next/prev` (cycle the sidebar selection → focus-or-swap per D-06), `jump N` (select the Nth sidebar row). Split/zoom *chords* and configurability are Phase 5 — do **not** add them to KEYMAP now (D-09/D-10).

**D-11 note:** app-scoped controller from the start; the Wayland-not-XWayland acceptance gate is **Phase 5**, not asserted here. Host session is currently `x11`/XWayland `[VERIFIED: XDG_SESSION_TYPE=x11]` — fine for Phase 3 dev; the real-Wayland gate is deferred per D-11.

### Pattern 4: Sidebar bound to `SessionStore` (PAR-02, D-05/D-06/D-07/D-08)
**What:** A left `Gtk.ListBox` (248px fixed-ish, UI-SPEC) of rows; each row = state dot (8px) + branch (13/600) + RAM sub-line (11/400). A pinned non-session `main` row at top (D-07). Right-click context menu → `win.hibernate`/`win.resume` (reuse Phase-2 actions, D-08).

**Selection dispatch (D-06):**
```python
def _on_row_activated(self, listbox, row):
    sid = self._sid_by_row[row]
    if self._layout.is_visible(sid):       # worktree already has a leaf
        self._focus_leaf(sid)
    else:                                    # swap it into the focused leaf
        self._layout.set_leaf_session(self._layout.focused, sid)
        self._reflect_layout()
```
**Rendering:** rebuild rows on `SessionStore` change; keep a `row ↔ session_id` map (replacing the Phase-2 `_page_by_sid`/`_sid_by_page`). Hibernated rows get the dimmed style + grey `#6272a4` dot; active rows green `#50fa7b` (UI-SPEC). The dot is **active-vs-hibernated only** — do not wire Phase-4 status colors.

### Pattern 5: Off-loop `~2s` RAM poll (RAM-03, D-12/D-14)
**What:** `GLib.timeout_add_seconds(2, self._poll_ram)` schedules a poll that, for each active session, sums process-group RSS from `/proc`, writes `rss_kb` onto the `WorktreeSession`, and refreshes the row sub-lines + footer. Return `GLib.SOURCE_CONTINUE` to keep polling; stop on window close.

**Off-loop discipline (CLAUDE.md):** reading a handful of small `/proc` files for 5–12 process groups is fast, but to honor "never block the GTK loop" strictly, do the read the `git_service` way — through `Gio.Subprocess` is overkill for file reads, so the cleaner option is: keep the per-poll work tiny and bounded (open/read/close ~3 small virtual files per pid), or move the whole walk into a `Gio.Subprocess` that execs nothing and instead... **simplest correct choice:** read `/proc` files synchronously inside the timeout but keep the working set bounded (5–12 groups) so a single poll is sub-millisecond; if profiling shows jank, escalate to a `Gio.Subprocess` helper. Document the bound. `[ASSUMED: sub-ms read cost — see Assumptions A1]`

### Anti-Patterns to Avoid
- **Putting layout/RSS/cap logic in `window.py`.** Breaks the GTK-free seam and makes it untestable. Keep widgets in `window.py`, logic in `layout.py`/`resource_monitor.py`/`caps.py`.
- **Using `Gtk.ShortcutController` for the prefix sequence.** Single-trigger model + scope/native caveats. Use capture-phase `EventControllerKey`.
- **Assuming `pgid == pid`.** Phase 2 already learned this (`os.getpgid(pid)` with a `ProcessLookupError` guard). Reuse that pattern; never hardcode.
- **Blocking `subprocess.run`/threads/asyncio for the poll.** CLAUDE.md-forbidden. Use `GLib.timeout` + bounded reads.
- **`get_children()` / GTK3 container idioms.** GTK4 uses `get_first_child()`/`get_next_sibling()`.
- **Reparenting a widget without detaching it first.** A GTK4 widget has one parent; `set_*_child(None)` / `unparent()` before reattaching.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Splittable pane container | A custom resizable split widget | Nested `Gtk.Paned` | Draggable handle, min-size, position all built in `[CITED: docs.gtk.org]` |
| Per-process RSS | Parse `top`/`ps` output | Read `/proc/<pid>/smaps_rollup` (`Rss:` line) or `statm` field 2 | Direct kernel numbers, no parse-fragility, no fork `[VERIFIED: host /proc probe]` |
| Process accounting library | Add `psutil` | stdlib `os` + `/proc` reads | D-13 forbids the dep; need is narrow (RSS by pid) |
| App-wide key capture | Manual GDK event filtering | `Gtk.EventControllerKey` capture phase | Idiomatic GTK4, sees keys before the terminal |
| Cap-prompt dialog | Custom modal window | `Adw.AlertDialog` with a chooser child | Already the Phase-2 pattern for the new-worktree + error dialogs |
| Process-group enumeration | Parse `ps -eo pgid` | Walk `/proc/[0-9]*/stat` field 5 (pgrp) | One scan, no subprocess; matches the pgid on the session `[VERIFIED: /proc/<pid>/stat field 5 = pgrp]` |

**Key insight:** The whole phase is assembling well-worn GTK4 primitives + a 3-field `/proc` read. The risk is *organizational* (keeping logic out of `window.py`), not *capability* — nothing here needs to be invented.

## Common Pitfalls

### Pitfall 1: `Gtk.Paned` single-parent reparent crash
**What goes wrong:** Moving a leaf into a new `Gtk.Paned` without first detaching it from its current parent → GTK warning / widget not appearing.
**Why it happens:** A GTK4 widget can only have one parent.
**How to avoid:** Always `set_*_child(None)` (or `unparent()`) the moving widget before `set_*_child(moving_widget)` on the new parent. (See the split snippet.)
**Warning signs:** "Trying to add a widget ... which already has a parent" console warnings; blank panes.

### Pitfall 2: Degenerate single-child `Gtk.Paned` after close
**What goes wrong:** Closing a leaf leaves its parent `Gtk.Paned` with one child and a dangling divider.
**Why it happens:** A `Gtk.Paned` is meant to hold two children.
**How to avoid:** On close, **collapse**: detach the surviving sibling and put it where the parent `Gtk.Paned` was (grandparent slot or root). Model this in `layout.py` (`close_leaf` returns the new tree) and reflect.
**Warning signs:** Empty half-pane, stuck divider.

### Pitfall 3: pid reuse / process exits mid-walk in the RAM poll
**What goes wrong:** A pid in the process group exits between enumerating it and reading its `/proc/<pid>/smaps_rollup` → `FileNotFoundError`; or a recycled pid yields a stranger's RSS.
**Why it happens:** `/proc` is racy by nature; pids are reused.
**How to avoid:** (a) Wrap each per-pid read in `try/except (FileNotFoundError, ProcessLookupError, PermissionError): continue`. (b) Re-derive group membership each poll from `/proc/[0-9]*/stat` field 5 == the session's `pgid`, rather than caching pid lists. (c) Skip sessions whose `pgid` is `None` (hibernated). `[VERIFIED: /proc semantics + Phase-2 pgid pattern]`
**Warning signs:** Intermittent tracebacks in the poll; RSS spikes from unrelated processes.

### Pitfall 4: Blocking the GTK loop in the poll
**What goes wrong:** A slow/large `/proc` walk inside the `GLib.timeout` stalls UI repaint.
**Why it happens:** The timeout callback runs *on* the main loop.
**How to avoid:** Bound the work (5–12 groups, ~3 tiny file reads each → sub-ms). If it ever isn't bounded, escalate to `Gio.Subprocess` mirroring `git_service.run_git_async`. Never `threading`/`asyncio` (CLAUDE.md). `[CITED: CLAUDE.md subprocess patterns]`
**Warning signs:** Visible hitching every ~2s.

### Pitfall 5: `smaps_rollup` permission / availability
**What goes wrong:** `smaps_rollup` can be unreadable for some processes or absent on exotic kernels.
**Why it happens:** Permission model + kernel config.
**How to avoid:** Prefer `smaps_rollup` `Rss:` (most accurate), **fall back to `/proc/<pid>/statm` field 2 (resident pages) × page size** (always readable for own processes) when `smaps_rollup` raises. Children spawned by the user's own shell are owned by the user → readable. `[VERIFIED: both files present and readable for self on host; PAGESIZE=4096]`
**Warning signs:** All RSS reads zero/None → wrong file or permission path.

### Pitfall 6: Capture-phase controller swallowing terminal input
**What goes wrong:** The prefix controller returns `True` for keys it shouldn't, so the terminal stops receiving normal typing.
**Why it happens:** Returning `True` from `key-pressed` consumes the event.
**How to avoid:** Return `True` **only** for (a) the prefix keystroke itself while disarmed, and (b) a recognized action key while armed. Return `False` everywhere else so the focused `Vte.Terminal` gets all normal input. An unrecognized key while armed should disarm and return `False` (or `True` to "eat" the stray — choose and test it).
**Warning signs:** Can't type in terminals; first char after `C-Space` lost.

### Pitfall 7: RAM display format (pt-BR + units)
**What goes wrong:** Showing `1.2 GB` or raw KB violates the UI-SPEC.
**How to avoid:** Format per UI-SPEC: **`MB` under 1024 MB, `GB` with one decimal above**, **pt-BR decimal comma** (`312 MB`, `1,2 GB`). Footer: `N agentes ativos · <total> RAM`, active count in green. Put the formatter in a GTK-free helper and unit-test it. `[CITED: 03-UI-SPEC.md]`

## Code Examples

### Sum process-group RSS from /proc (GTK-free, in resource_monitor.py)
```python
# resource_monitor.py — GTK-free. Verified against host /proc layout.
import os

_PAGE = os.sysconf("SC_PAGE_SIZE")  # 4096 on host

def _rss_kb_for_pid(pid: int) -> int:
    # Prefer smaps_rollup (accurate); fall back to statm resident pages.
    try:
        with open(f"/proc/{pid}/smaps_rollup", "r") as fh:
            for line in fh:
                if line.startswith("Rss:"):
                    return int(line.split()[1])  # already in kB
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
    try:
        with open(f"/proc/{pid}/statm", "r") as fh:
            resident_pages = int(fh.read().split()[1])  # field 2 = resident
            return resident_pages * _PAGE // 1024
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return 0

def _pids_in_group(pgid: int) -> list[int]:
    # /proc/<pid>/stat field 5 (1-indexed) is pgrp. comm may contain spaces/parens,
    # so split on the LAST ')' to find the field offset robustly.
    out = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", "r") as fh:
                data = fh.read()
            rparen = data.rfind(")")
            fields = data[rparen + 2:].split()  # state is fields[0] after comm
            pgrp = int(fields[2])               # pgrp is the 5th overall = 3rd after comm
            if pgrp == pgid:
                out.append(int(entry))
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
            continue
    return out

def group_rss_kb(pgid: int) -> int:
    """Total resident KB for every process in the group (D-12)."""
    return sum(_rss_kb_for_pid(p) for p in _pids_in_group(pgid))
```
*Source: derived from verified `/proc` layout on host (`/proc/self/stat` field 5 = pgrp; `smaps_rollup` `Rss:` line; `statm` field 2 = resident pages; PAGESIZE 4096).* `[VERIFIED: host probe]`
*Note: the `stat` field offset is the classic comm-with-parens trap — splitting after the last `)` is the standard robust parse; unit-test it with a fixture `stat` line containing a paren in comm.*

### Cap policy (GTK-free, in caps.py)
```python
# caps.py — GTK-free. Interim single source Phase 6 sources from .arduis.toml (D-15).
ACTIVE_CAP_DEFAULT = 6  # D-15: default ~6, configurable; Phase 6 overrides from TOML.

def active_count(sessions) -> int:
    return sum(1 for s in sessions if s.state.value == "active")

def at_cap(sessions, cap: int = ACTIVE_CAP_DEFAULT) -> bool:
    """True → opening a new worktree must prompt-to-hibernate first (D-16)."""
    return active_count(sessions) >= cap
```
*window.py routes the +New flow through `at_cap(self._store.all())`; if True, present the `Adw.AlertDialog` chooser (UI-SPEC copy), hibernate the chosen one, then proceed with creation.* `[CITED: 03-CONTEXT.md D-15/D-16]`

### Capture-phase prefix controller — see Pattern 3 snippet above.

### Min-size + nesting on a Gtk.Paned leaf
```python
leaf.set_size_request(240, 120)        # UI-SPEC min usable terminal
paned.set_shrink_start_child(False)    # so size_request is respected as a floor
paned.set_shrink_end_child(False)
paned.set_wide_handle(True)
```
`[CITED: docs.gtk.org/gtk4/class.Paned.html + VERIFIED host probe]`

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| GTK3 `container.add()` / `get_children()` | GTK4 `set_start/end_child()`, `get_first_child()`/`get_next_sibling()` | GTK4 (2021) | Tree walk + reparent use the new child API; no `get_children()` |
| GTK3 `add_accelerator` / `AccelGroup` | GTK4 `Gtk.ShortcutController` (single chords) + `Gtk.EventControllerKey` (sequences) | GTK4 | Prefix sequence needs EventControllerKey, not the accel/shortcut path |
| `Adw.TabView`/`TabBar` (Phase-2 interim) | Sidebar `Gtk.ListBox` + nested `Gtk.Paned` canvas | This phase (D-01) | Tab strip fully removed; same `SessionStore` binding |
| `psutil` for process stats | stdlib `/proc` reads | Project decision (D-13) | No new dep in `.deb`/AUR |

**Deprecated/outdated:**
- GTK3 event handling (`key-press-event` signal on widgets) — GTK4 uses event controllers. The Phase-2 code already uses `Gtk.ShortcutController` for clipboard; keep that, add `EventControllerKey` for the prefix.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A single RAM poll over 5–12 process groups (≈3 tiny `/proc` reads each) is sub-millisecond and safe to run synchronously inside the `GLib.timeout` without jank | Pattern 5 / Pitfall 4 | LOW — if it janks, escalate to a `Gio.Subprocess` off-loop helper (the seam is already modeled by `git_service`). Easy to measure during execution. |
| A2 | Directional pane focus (`h/j/k/l`) can be resolved from the layout tree's structure/geometry well enough for Phase 3 (tmux-exact directional geometry is a refinement) | Pattern 3 (D-09) | LOW — worst case, fall back to tree-order next/prev among visible leaves for a direction; the *feel* requirement (CONTEXT specifics) is satisfied by working directional movement, exact geometry is Phase-5-polish territory. |
| A3 | `set_shrink_*_child(False)` + `set_size_request` reliably enforces the ~240×120 min pane floor across nested panes | Pattern 1 / Code Examples | LOW — documented behavior `[CITED: docs.gtk.org]`; verify visually in the manual acceptance pass. |

**No assumptions touch compliance, security, retention, or data-loss surfaces.** All three are UI/perf refinements verifiable during execution.

## Open Questions

1. **Directional focus geometry precision**
   - What we know: `h/j/k/l` must move pane focus; the layout is a binary tree (Pattern 1).
   - What's unclear: whether Phase 3 needs true spatial "nearest pane to the left" geometry or tree-order traversal is acceptable.
   - Recommendation: Implement tree-aware directional movement (walk to the sibling subtree in the requested orientation); treat pixel-perfect spatial nearest-neighbor as Phase-5 polish (A2). The CONTEXT only requires the *feel* now.

2. **Close-pane default: hide vs hibernate**
   - What we know: D-04/discretion default is **hide** (worktree stays active in the sidebar; hibernate is the explicit menu action).
   - What's unclear: nothing blocking — locked as hide.
   - Recommendation: Closing a pane removes the leaf from the layout tree only; the `WorktreeSession` stays ACTIVE in `SessionStore` and visible in the sidebar. No confirmation dialog (UI-SPEC). RAM keeps counting (agent still alive) — which is the honest behavior.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| PyGObject (`python3-gi`) | all GTK | ✓ | system | — |
| GTK4 | panes/sidebar/key | ✓ | 4.14.5 | — (4.x floor) |
| libadwaita | shell + AlertDialog | ✓ | 1.5 | — |
| VTE (Vte-3.91) | per-pane terminal | ✓ | 0.76.0 | — (floor) |
| `/proc/<pid>/smaps_rollup` | RAM-03 accurate RSS | ✓ | kernel | `/proc/<pid>/statm` field 2 × pagesize |
| `/proc/<pid>/stat` | process-group walk | ✓ | kernel | — |
| Python 3.12 | all | ✓ | 3.12.3 | — |
| `psutil` | (rejected) | ✗ | — | stdlib `/proc` (the chosen path) |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** `smaps_rollup` → `statm` (both verified present for self; children are user-owned so readable).
`[VERIFIED: host probe 2026-06-09]`

## Validation Architecture

`workflow.nyquist_validation` is `true` in config → section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (`[tool.pytest.ini_options]` in `pyproject.toml`) |
| Config file | `/home/thallysrc/Projects/arduis/pyproject.toml` (`testpaths=["tests"]`, `pythonpath=["src"]`, `addopts="-q"`) |
| Quick run command | `python3 -m pytest tests/test_layout.py tests/test_caps.py tests/test_keymap.py -x -q` |
| Full suite command | `python3 -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| LAYOUT-01 | split focused leaf → balanced binary tree | unit | `pytest tests/test_layout.py::test_split_focused -x` | ❌ Wave 0 |
| LAYOUT-01 | close leaf collapses degenerate parent | unit | `pytest tests/test_layout.py::test_close_collapses -x` | ❌ Wave 0 |
| LAYOUT-01 | zoom toggle saves/restores tree | unit | `pytest tests/test_layout.py::test_zoom_roundtrip -x` | ❌ Wave 0 |
| LAYOUT-01 | preset 2×2 / columns from N session_ids (MRU subset) | unit | `pytest tests/test_layout.py::test_preset_subset -x` | ❌ Wave 0 |
| PAR-01/D-02 | visible-pane subset vs full store decoupling | unit | `pytest tests/test_layout.py::test_visibility_decoupled -x` | ❌ Wave 0 |
| PAR-03/D-09/D-10 | prefix dispatch: armed/disarmed, h/j/k/l, next/prev, digit jump | unit | `pytest tests/test_keymap.py -x` | ❌ Wave 0 |
| RAM-03/D-12 | group RSS sums all pids in pgid (fixture `/proc`) | unit | `pytest tests/test_resource_monitor.py::test_group_rss_sum -x` | ❌ Wave 0 |
| RAM-03 | `stat` comm-with-parens parse robustness | unit | `pytest tests/test_resource_monitor.py::test_stat_paren_comm -x` | ❌ Wave 0 |
| RAM-03 | smaps_rollup→statm fallback path | unit | `pytest tests/test_resource_monitor.py::test_rss_fallback -x` | ❌ Wave 0 |
| RAM-03/D-14 | pt-BR RAM formatter (MB/GB, comma) | unit | `pytest tests/test_resource_monitor.py::test_ram_format -x` | ❌ Wave 0 |
| RAM-02/D-15/D-16 | at_cap boundary (below/at/above default 6) | unit | `pytest tests/test_caps.py -x` | ❌ Wave 0 |
| PAR-02/D-06 | focus-or-swap dispatch decision (pure) | unit | `pytest tests/test_layout.py::test_focus_or_swap -x` | ❌ Wave 0 |
| PAR-01/PAR-02/LAYOUT-01 | live multi-pane render, drag dividers, sidebar focus, real RSS numbers, prefix keys under XWayland | manual | (manual acceptance checklist — GTK render/input) | n/a |

**Manual-only justification:** Live GTK rendering, divider dragging, real terminal spawning, and actual key capture require a display server; consistent with the Phase-1/2 manual-acceptance-checklist approach (Phase-1 D-14). The Wayland-not-XWayland gate is **Phase 5**, not here (D-11). All *logic* is pushed into GTK-free modules so the manual surface is thin.

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/test_layout.py tests/test_caps.py tests/test_keymap.py tests/test_resource_monitor.py -x -q`
- **Per wave merge:** `python3 -m pytest -q` (full suite)
- **Phase gate:** Full suite green + manual acceptance checklist (multi-pane, split/drag/close, sidebar focus-or-swap, RAM numbers, cap prompt, prefix keys) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_layout.py` — covers LAYOUT-01, PAR-01 (D-02), PAR-02 (D-06)
- [ ] `tests/test_resource_monitor.py` — covers RAM-03 (D-12/D-14); use a fixture `/proc` dir or monkeypatch `open`/`os.listdir` with fake `stat`/`smaps_rollup`/`statm` contents
- [ ] `tests/test_caps.py` — covers RAM-02 (D-15/D-16)
- [ ] `tests/test_keymap.py` — covers PAR-03 (D-09/D-10)
- [ ] No framework install needed — pytest already configured.

## Sources

### Primary (HIGH confidence)
- **Host probe 2026-06-09** — VTE 0.76.0, GTK 4.14.5, libadwaita 1.5, Python 3.12.3; `Gtk.Paned` set/get/shrink/wide-handle methods; `get_first_child`/`get_next_sibling`/`get_parent`/`unparent`; `EventControllerKey` + `PropagationPhase.CAPTURE`; `Gtk.ListBox.bind_model`; `GLib.timeout_add_seconds`; `/proc/self/{stat,statm,smaps_rollup}` layout; PAGESIZE 4096; no `psutil` in tree
- [docs.gtk.org/gtk4/class.Paned.html](https://docs.gtk.org/gtk4/class.Paned.html) — start/end child, set_*_child(None) removal, shrink/resize/min-size semantics, nesting
- [docs.gtk.org/gtk4/class.ShortcutController.html](https://docs.gtk.org/gtk4/class.ShortcutController.html) — scope semantics, runtime add/remove, native-surface caveat
- [docs.gtk.org/gtk4/class.EventControllerKey.html](https://docs.gtk.org/gtk4/class.EventControllerKey.html) — key-pressed signal, capture phase
- `CLAUDE.md`, `03-CONTEXT.md`, `03-UI-SPEC.md`, `02-CONTEXT.md`, `01-CONTEXT.md`, existing `src/arduis/*.py` + `tests/*.py`

### Secondary (MEDIUM confidence)
- [docs.gtk.org/gtk4/method.ShortcutController.set_scope.html](https://docs.gtk.org/gtk4/method.ShortcutController.set_scope.html) + WebSearch cross-check — LOCAL vs MANAGED vs GLOBAL, "limited to the same native" caveat
- [docs.gtk.org/gtk4/input-handling.html](https://docs.gtk.org/gtk4/input-handling.html) — event propagation (capture → bubble), why a window-level capture controller sees keys before the focused terminal

### Tertiary (LOW confidence)
- None requiring validation — all load-bearing claims verified on host or cited from official GTK docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every API verified present on the exact host floor; zero new deps
- Architecture (paned tree, prefix, /proc): HIGH — APIs probed live; algorithms are standard GTK4/`/proc` idioms
- Pitfalls: HIGH — derived from verified `/proc` semantics, GTK4 single-parent rule, and Phase-2's own pgid lesson
- Directional-focus geometry + poll-cost: MEDIUM (A1/A2) — verifiable cheaply during execution; safe fallbacks exist

**Research date:** 2026-06-09
**Valid until:** 2026-07-09 (30 days — stable system stack; GTK4/VTE floor is pinned by distro packaging)
