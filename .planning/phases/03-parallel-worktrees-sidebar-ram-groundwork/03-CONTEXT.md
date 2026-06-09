# Phase 3: Parallel Worktrees + Sidebar + RAM Groundwork - Context

**Gathered:** 2026-06-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Make parallelism **visible and bounded**. Many worktrees open at once, each with its own
terminal (PAR-01); a **sidebar bound to the `SessionStore`** that lists every worktree and
focuses/switches between them (PAR-02) including **tmux-style switching shortcuts** (PAR-03);
a **free split/drag pane layout** (nested `GtkPaned`) replacing the Phase-2 `Adw.TabView`
tab strip instead of a fixed grid (LAYOUT-01); and the **RAM groundwork** — a `ResourceMonitor`
that surfaces **per-worktree RSS** in the UI (RAM-03) and enforces a **configurable
active-agent cap** when opening new worktrees (RAM-02). Covers **PAR-01, PAR-02, PAR-03,
LAYOUT-01, RAM-02, RAM-03**.

This phase replaces the interim Phase-2 tab UI with the real sidebar + panes, **binding to
the same `SessionStore`** (the Phase-2 tab strip was an explicit stepping stone per D-01/D-02,
not a throwaway) and **populates the `rss_kb` field reserved on the model in Phase 2 (D-13)**.

Out of scope for this phase (owned elsewhere): **attention/status detection** — the
running/waiting/idle/ready dots and hooks-first watcher are **Phase 4** (the Phase-3 dot only
distinguishes active vs hibernated); the **full configurable tmux keybinding system + the
split/zoom *chords* + the Wayland-not-XWayland acceptance gate** are **Phase 5 (UI-01)**;
**theme-switching UI** is **Phase 5 (UI-02)** (Phase 3 stays on the app-owned Dracula palette);
**`.arduis.toml` config + setup commands** are **Phase 6** (Phase 3 uses an interim app-level
cap setting); **containers** (and their share of the active cap) are **Phase 7**; **idle
auto-suspend** is **Phase 4 (RAM-04)**; **conclude/remove worktree + teardown ordering + diff/PR**
are **Phase 8**. Persisting layout/worktrees across an arduis quit→restart remains **v2
(PERSIST-01)**.

</domain>

<decisions>
## Implementation Decisions

### Pane layout (LAYOUT-01, PAR-01)
- **D-01:** The multi-pane area is a **single splittable canvas** built from **nested
  `GtkPaned`** (binary, draggable dividers — tmux-style free splits), filling the main content
  area. This **replaces the Phase-2 `Adw.TabView`/`TabBar`** entirely; there is no visible tab
  bar (matches the v1 mockup). Tree shape: `GtkPaned ▸ GtkPaned ▸ Vte.Terminal`.
- **D-02:** **Sidebar and panes are decoupled** — the sidebar holds **all** worktrees; the
  pane canvas shows a **subset**. A worktree can be **active (agent running) without occupying
  a visible pane**. This scales past what fits on screen at the 5–12 working set.
- **D-03:** **Creating a new worktree splits the focused pane**, so the new agent shows
  immediately beside the current one (keeps the "agent running in seconds, visible" promise).
- **D-04:** Phase 3 ships, beyond manual split/drag/close: a **zoom-focus toggle** (fullscreen
  the focused pane — the mockup's `C-Space z`, exposed as a control now; the *chord* lands in
  Phase 5) **and preset layouts** (the mockup's **"Layout" button** — e.g. grid 2×2, columns).
  When a preset shows fewer cells than there are active worktrees, which subset fills the cells
  is **Claude's discretion** (suggest most-recently-focused).

### Sidebar (PAR-02)
- **D-05:** Each sidebar row shows a **state dot + branch name + a RAM sub-line**. In Phase 3
  the dot means **active (green) vs hibernated (grey)** only; **Phase 4 enriches the same dot**
  to running/waiting/idle/ready (do not build status semantics here).
- **D-06:** **Selecting a sidebar row focuses its pane if the worktree is already visible;
  otherwise it swaps that worktree into the currently-focused pane** (coherent with the
  decoupled model, D-02).
- **D-07:** The **Phase-1/2 `$HOME` scratch shell appears as a pinned `main` sidebar entry**
  (the mockup's `main · zsh` row) — always present, **not** a worktree session.
- **D-08:** **Hibernate/Resume move to the sidebar row's right-click context menu**, reusing
  the existing Phase-2 `win.hibernate`/`win.resume` actions + `SessionStore` transitions
  (D-10/D-11/D-12 from Phase 2) — now triggered from the sidebar instead of the (removed) tab
  menu. The hibernated dimming/badge moves from the tab to the sidebar row.

### Switching shortcuts (PAR-03; full system is Phase 5 / UI-01)
- **D-09:** Phase 3 ships keyboard switching for: **directional pane-focus move (`h/j/k/l`),
  worktree next/prev cycling, and jump-to-worktree by number**. (Split/zoom chords + full
  configurability are Phase 5.)
- **D-10:** **Build the tmux `C-Space` prefix mechanism now** (the prefix state machine) with
  **hardcoded** bindings. Phase 5 (UI-01) makes the keymap **configurable** and adds the
  split/zoom chords. Keymap constants should live in a single GTK-free place so Phase 5 can
  wrap them in config without reshaping the dispatcher.
- **D-11:** Use **app-scoped** `Gtk.ShortcutController` bindings from the start, but the
  explicit **"works under real Wayland, not just XWayland" acceptance gate is Phase 5
  (UI-01 SC#3)** — not duplicated as a Phase-3 gate.

### RAM groundwork (RAM-03 visibility, RAM-02 cap)
- **D-12:** The per-worktree RAM number is the **whole process-group RSS** (`zsh` + `claude` +
  children), summed via the **`pgid` already tracked on `WorktreeSession`**. This is the true
  "what this worktree costs me" figure.
- **D-13:** The `ResourceMonitor` **reads `/proc` directly** (`/proc/<pid>/stat` +
  `smaps_rollup`, walking the process group) — **zero new dependency**, GTK-free, Linux-only
  (fine for this project), consistent with CLAUDE.md's minimal-deps + ResourceMonitor seam.
  **Not psutil** (avoids a new runtime dep to declare in the `.deb`/AUR packages).
- **D-14:** RAM is shown on **each sidebar row's sub-line** plus an **aggregate "N active ·
  total RAM" footer** in the sidebar (the v1 mockup footer). Poll cadence **~2s** (exact value
  + display format/units are Claude's discretion); polling must run **off the GTK main loop /
  not block it**.
- **D-15:** A **configurable cap on simultaneously active (non-hibernated) agents** is enforced
  when opening a new worktree. **What counts now: active agents** (containers join the **same**
  cap in Phase 7). **Default ~6, configurable.** Since `.arduis.toml` does not exist until
  Phase 6, Phase 3 stores the cap as an **interim app-level setting/constant** (exact storage
  is Claude's discretion; must be a single place Phase 6 can source from `.arduis.toml`).
- **D-16:** **Enforcement when at the cap = prompt to hibernate one first.** Block launching
  the new agent and prompt ("You're at N active agents — hibernate one to free RAM"); the user
  picks which to hibernate, then creation proceeds. Not a silent allow, not create-hibernated.

### Claude's Discretion
- Exact `GtkPaned` tree management (how splits/closes mutate the tree; min pane size; focus
  tracking) and how the "decoupled" hidden-worktree set is represented.
- Preset-layout subset selection when worktrees > cells (suggest most-recently-focused).
- `ResourceMonitor` poll cadence (~2s), RSS aggregation details, and RAM display format/units.
- Interim cap-setting storage mechanism (constant vs simple app setting) — must be Phase-6
  sourceable.
- Sidebar visual details (row height, dot styling, footer layout) within the Dracula palette.
- Whether closing a pane hibernates vs just hides the worktree (default: hide — the worktree
  stays active in the sidebar; hibernate stays an explicit action per D-08).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` § "Phase 3: Parallel Worktrees + Sidebar + RAM Groundwork" — goal +
  5 success criteria (the acceptance bar) + the cross-cutting RAM/swarm-seam notes
- `.planning/REQUIREMENTS.md` § PAR-01, PAR-02, PAR-03, LAYOUT-01, RAM-02, RAM-03 (+ the
  cross-cutting RAM note: RAM-02/03 owned here, RAM-04 in Phase 4, container-half in Phase 7)
- `.planning/PROJECT.md` § Key Decisions, § "RAM management as first-class"

### Prior phase context (carried-forward decisions)
- `.planning/phases/02-core-loop-new-worktree-env-agent/02-CONTEXT.md` — **D-01/D-02** (tab
  strip is an interim stepping stone Phase 3 absorbs, binding to the same `SessionStore`),
  **D-08/D-09** (feed `AGENT_FEED`, durable-shell/ephemeral-agent), **D-10/D-11/D-12**
  (hibernate via context menu, kill process group keep dir, resume cold-relaunch),
  **D-13** (`SessionStore` GTK-free/serializable, `rss_kb` reserved for Phase 3)
- `.planning/phases/01-terminal/01-CONTEXT.md` — HostRunner no-op seam, GTK-free spawn builder,
  `zsh -l -i` + `TERM=xterm-256color`, **app-owned Dracula palette**, **VTE 0.76 API floor**,
  **SIGHUP→SIGKILL no-orphan teardown** (reused by hibernate + window close)

### Product background & visual reference
- `docs/mockup/interface-v1.html` / `interface-v1.png` — **the Phase 3 visual target**:
  left WORKTREES rail (dot + branch + sub-line), the splittable pane canvas, the "Nova
  worktree" + "Layout" buttons, the footer aggregate ("N agentes ativos · portas…"), and the
  tmux hint bar ("C-Space n nova · C-Space hjkl mover · C-Space z zoom")
- `docs/mockup/interface-v2-bridgespace.html` / `interface-v2-bridgespace.png` — later-phase
  target (Command/Swarm/Review + swarm rail); informs direction, **not** Phase 3 scope
- `docs/ROADMAP.md` § "`.arduis.toml` (esboço)" — the `[worktree]` schema the interim Phase-3
  cap setting must be sourceable from in Phase 6; `docs/MOTIVATION.md` — anchor doc

### Code to evolve (Phase-2 base)
- `src/arduis/window.py` — the ONLY `gi` module; currently `Adw.TabView`/`TabBar` +
  per-session widget maps + spawn/feed/hibernate/teardown. Phase 3 swaps the tab strip for
  the sidebar + `GtkPaned` canvas, **keeping** the spawn/teardown/`SessionStore` wiring
- `src/arduis/session.py` — `SessionStore` + `WorktreeSession` (has `pgid` for D-12 and the
  `rss_kb` field to populate); add/extend GTK-free model for layout/visibility + cap state
- `src/arduis/git_service.py` — `run_git_async` (Gio.Subprocess) pattern to mirror for the
  GTK-free `ResourceMonitor` polling cadence
- `src/arduis/theme.py` — Dracula palette (sidebar + dots stay within it; no theme switching)
- `src/arduis/host_runner.py`, `src/arduis/spawn.py` — unchanged seams the new code reuses
- `tests/test_session.py` (+ `tests/`) — extend the GTK-free unit-test pattern to the layout
  model, `ResourceMonitor` `/proc` parsing, and cap logic

### Conventions (from CLAUDE.md)
- Strict **GTK-free core** (only `window.py` imports `gi`); `ResourceMonitor`, layout model,
  and cap logic must be GTK-free + pytest-covered
- `Gio.Subprocess` + GLib loop for non-blocking work; **never block the GTK main loop**
  (applies to the RAM poll)
- Target the **VTE 0.76 API floor**; one codebase for Ubuntu 0.76 / Arch 0.84

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `window.py`: the spawn (`_spawn_into` + `_make_wt_spawn_cb`), feed (`AGENT_FEED`), and
  **SIGHUP→SIGKILL process-group teardown** (`_teardown_pgid`/`_sigkill_if_alive`) are reused
  verbatim — Phase 3 changes the *container* (sidebar + `GtkPaned`), not the spawn/teardown.
  The `_make_terminal` factory (palette + clipboard shortcuts) is reused per pane.
- `session.py`: `SessionStore` (GTK-free, `add`/`get`/`by_branch`/`all`/`to_list`) is the
  binding source for the sidebar; `WorktreeSession.pgid` feeds the RAM monitor; `rss_kb` is the
  reserved field RAM-03 populates; `hibernate_fields` is reused by the sidebar menu.
- `git_service.run_git_async` — the async/off-main-loop pattern the `ResourceMonitor` mirrors.
- `tests/` already unit-tests the GTK-free seams (session, spawn argv, theme, host_runner,
  exit decode) — extend the same pattern to layout model, `/proc` RSS parsing, and cap logic.

### Established Patterns
- Presentation→Domain→Service with **only `window.py` importing `gi`**; everything testable
  (layout state, RAM math, cap rule) stays GTK-free.
- App owns the terminal/UI palette (Dracula); spawn is `zsh -l -i` login+interactive.
- VTE 0.76 API floor; `Adw.ApplicationWindow` + `Adw.ToolbarView`/`HeaderBar` shell.

### Integration Points
- `window.py` content goes from `Adw.TabView` → a horizontal split: **sidebar (left)** bound
  to `SessionStore` + **`GtkPaned` canvas (right)**. The per-session widget maps
  (`_page_by_sid`/`_term_by_sid`/`_sid_by_page`) become pane/row maps.
- New GTK-free `ResourceMonitor` (reads `/proc`, polls ~2s via GLib timeout/Gio) writes
  `rss_kb` back onto each `WorktreeSession`; the sidebar rows + footer render it.
- The `+New worktree` flow (D-03 split focused pane) routes through the cap check (D-15/D-16)
  before spawning.

### Obsolete / not applicable
- The visible `Adw.TabBar` and tab-context-menu wiring are replaced (actions survive, host
  moves to the sidebar).
- `.flatpak-builder/`, `build-dir/` — dropped Flatpak leftovers; ignore.

</code_context>

<specifics>
## Specific Ideas

- The **v1 mockup is the literal Phase 3 target**: WORKTREES rail with dot + branch + activity
  sub-line, a splittable pane canvas (not a locked grid), "Nova worktree" + "Layout" buttons,
  a footer aggregate, and the tmux hint bar.
- tmux muscle memory matters: `C-Space` prefix, `hjkl` to move focus — even though full
  configurability is Phase 5, the *feel* should be right now.
- "Lightweight with first-class RAM management" is the promise this phase makes real: the
  per-worktree RSS number and the active-agent cap are the visible proof at the 5–12 working set.

</specifics>

<deferred>
## Deferred Ideas

- **Attention status (running/waiting/idle/ready) dots + hooks-first watcher** → **Phase 4**
  (STATUS-01/02/03). Phase-3 dot is active-vs-hibernated only.
- **Idle auto-suspend** → **Phase 4 (RAM-04)** — depends on idle detection.
- **Full configurable keybindings + split/zoom chords + Wayland-not-XWayland gate** →
  **Phase 5 (UI-01)**. **Theme switching** → **Phase 5 (UI-02)**.
- **`.arduis.toml` cap/config + setup commands** → **Phase 6** (Phase 3 uses an interim
  app-level cap setting it can later source from the file).
- **Containers + their share of the active cap + port badges** → **Phase 7**.
- **Conclude/remove worktree + teardown ordering + diff/PR** → **Phase 8**. Phase 3 only
  hibernates (keeps the dir).
- **Persist layout / reopen worktrees across an arduis quit→restart** → **v2 (PERSIST-01)**.
- **Drag worktrees from the sidebar into specific panes** (vs the D-06 focus-or-swap default)
  → revisit if the focus-or-swap model proves limiting.

</deferred>

---

*Phase: 03-parallel-worktrees-sidebar-ram-groundwork*
*Context gathered: 2026-06-09*
