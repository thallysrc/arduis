# Phase 2: Core Loop (new worktree → env → agent) - Context

**Gathered:** 2026-06-09
**Status:** Ready for planning

<domain>
## Phase Boundary

The heart of the product: clicking **"+New worktree"**, choosing a branch (new or
existing), and getting a terminal with the default agent (`claude`) already running in the
new worktree directory in seconds — plus **hibernate/resume** to reclaim the agent's RAM
while keeping the directory. Establishes the Presentation→Domain→Service direction and the
**GTK-free, serializable `SessionStore`** (first swarm seam) with RAM fields on the model
from day one. Covers **WT-01, WT-02, WT-03, RAM-01**.

Out of scope for this phase (owned elsewhere): the sidebar + multiple side-by-side panes +
per-worktree RAM visibility + active caps (Phase 3); attention/status detection (Phase 4);
agent = configurable command + tmux keybindings + theme-switching UI (Phase 5);
`.arduis.toml` reading + setup commands (Phase 6); containers (Phase 7); **conclude/remove
worktree + teardown ordering + diff/PR** (Phase 8). Reattaching to live agents or persisting
worktrees across an app quit/restart is **v2 (PERSIST-01)**.

</domain>

<decisions>
## Implementation Decisions

### Worktree UI shape (interim — sidebar/parallel panes are Phase 3)
- **D-01:** Worktrees are presented as a **tab strip** (`Adw.TabView` / `Adw.TabBar`). Each
  worktree is a tab; the user can see that multiple worktrees exist and switch between them.
  Phase 3 replaces this with the real sidebar + free panes, **binding to the same
  `SessionStore`** (the tab UI is the stepping stone, not a throwaway).
- **D-02:** **Tab 0 keeps the Phase-1 `$HOME` shell** unchanged (zero regression; stays a
  scratch shell). The **`+` ("New worktree") button lives on the tab bar**; new worktrees add
  tabs alongside tab 0.

### Repo / branch / location (no `.arduis.toml` until Phase 6 → hardcoded sensible defaults)
- **D-03:** The repo is resolved from **arduis's launch working directory**
  (`git rev-parse --show-toplevel`), terminal-centric (`arduis` run from inside the repo,
  like `code .`). If launched **outside a git repo**, the "+New worktree" button is
  **disabled with a hint**.
- **D-04:** A **new** branch is created off the repo's **auto-detected default branch**
  (`origin/HEAD` → `main`/`master`), matching the `docs/ROADMAP.md` `base = "main"` intent and
  the "environment based on trunk" principle — **without hardcoding the literal `main`**.
- **D-05:** The worktree directory is a **sibling**: **`../<repo>-<branch>`** (matches
  `docs/ROADMAP.md` `location = "../"`). Branch names with slashes/unsafe chars are
  **sanitized** for the directory name.
- **D-06:** The "+New worktree" dialog uses a **single editable combo (type-or-pick)**: typing
  a new name creates the branch; picking from the dropdown (populated via `git branch`) checks
  out an existing one. arduis **infers new-vs-existing** automatically.
- **D-07:** **Never `--force`.** If the chosen branch is already checked out in a worktree
  arduis tracks, **focus that worktree's existing tab** instead of duplicating. If it's
  checked out somewhere arduis doesn't track (e.g. the main working copy), show a **clear
  message** and abort. (Satisfies Success Criterion #3.)

### Agent launch & Ctrl+C (durable shell, ephemeral agent — roadmap cross-cutting rule)
- **D-08:** Launch is **feed-into-PTY**: spawn **`zsh -l -i`** in the worktree directory
  (same spawn path as Phase 1, just a different `cwd`), then write **`claude\n`** via
  `Vte.Terminal.feed_child()`. The **shell is the durable PTY child**; `claude` is a child of
  that zsh.
- **D-09:** Because the agent runs *inside* zsh, **Ctrl+C / agent exit lands you back at the
  worktree zsh prompt** — the pane stays useful and a different agent/command can be run there
  (sets up AGENT-01 / Phase 5 with zero re-spawn). A **missing or failed `claude` needs no
  special handling**: you simply get the normal shell (`command not found` if uninstalled) and
  the tab stays open. **No in-app error banner** in Phase 2 (agent-exit detection overlaps
  Phase 4 status work).

### Hibernate / resume (RAM-01)
- **D-10:** Hibernate is triggered from the **worktree tab's context menu** (right-click →
  "Hibernate"). A hibernated tab **stays visible but dimmed/badged** as suspended; "Resume"
  (menu) brings it back. The Phase-3 sidebar later inherits the same `SessionStore` state +
  actions.
- **D-11:** Hibernate **kills the whole worktree PTY process group** (`zsh` + `claude` child)
  via the **Phase-1 teardown path (SIGHUP → SIGKILL grace)**, reclaiming all the agent's RAM,
  while **keeping the worktree directory** on disk. (Phase 2 does **not** remove worktrees —
  that's Phase 8.)
- **D-12:** **Resume re-spawns** `zsh -l -i` in the worktree dir and **re-feeds `claude`** —
  identical to fresh creation (D-08). It is a **cold relaunch**, not a reattach to the previous
  live agent (reattach = v2 / PERSIST-01).

### SessionStore & persistence scope
- **D-13:** The `SessionStore` is **GTK-free and serializable** (the swarm seam the roadmap
  requires) and carries **RAM fields on the model from day one**, but is **in-memory only** in
  Phase 2 — **no disk persistence**. Serializable ≠ persisted.
- **D-14:** **OS suspend/resume** (system sleep/hibernate) is a **non-feature**: processes are
  frozen/restored by the OS, so arduis, the worktree shells, and the agents all survive
  intact — nothing to build. Persisting/re-listing worktrees across an **arduis quit/restart**
  (cold-reopen) is **deferred to v2** (alongside PERSIST-01). On quit→relaunch arduis returns
  to its initial state (tab 0 = `$HOME`); the worktrees remain on disk/in git for manual
  reopen.

### Claude's Discretion
- Exact `SessionStore` shape, model fields, and serialization format (must be GTK-free,
  serializable, with RAM fields).
- Concrete Presentation→Domain→Service module/file layout; git argv construction details.
- **Creation progress feedback** during `git worktree add → open terminal → launch claude`
  (spinner / disabled button vs. just opening the tab and letting the terminal show progress).
- **Worktree tab label format** (branch name vs repo/branch vs dir name) and long-name
  truncation.
- The empty named `swarm/` seam directory.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` § "Phase 2: Core Loop (new worktree → env → agent)" — goal + 4
  success criteria (the acceptance bar) + the cross-cutting RAM/swarm-seam notes
- `.planning/REQUIREMENTS.md` § WT-01, WT-02, WT-03, RAM-01
- `.planning/PROJECT.md` § Key Decisions, § Active requirements (core loop, RAM as
  first-class)

### Prior phase context (carried-forward decisions)
- `.planning/phases/01-terminal/01-CONTEXT.md` — HostRunner seam (D-04/D-05), GTK-free spawn
  builder, `zsh -l -i` + `TERM=xterm-256color` (D-09/D-10), app-owned Dracula palette,
  VTE 0.76 API floor, no-orphan SIGHUP→SIGKILL teardown (reused by hibernate)

### Product background
- `docs/ROADMAP.md` § "`.arduis.toml` (esboço)" — `[worktree] base/location/setup` schema that
  the Phase-2 defaults mirror (base=default branch, location=sibling); § "Degrau 2"
- `docs/MOTIVATION.md` — base motivation/anchor document

### Visual reference (approved mockups — inform the eventual shell, not this interim tab UI)
- `docs/mockup/interface-v1.html` / `interface-v1.png` — v1 Dracula 2×2 grid (Phase 3 target)
- `docs/mockup/interface-v2-bridgespace.html` / `interface-v2-bridgespace.png` — v2
  BridgeSpace-style rail (later-phase target)

### Code to evolve (Phase-1 base)
- `src/arduis/window.py` — single-terminal window; the spawn/teardown/palette wiring to
  generalize for tabbed worktree terminals
- `src/arduis/spawn.py` — `build_spawn_command` (GTK-free argv/env via HostRunner); extend for
  a per-worktree `cwd` + agent feed
- `src/arduis/host_runner.py` — the no-op seam `git worktree add` / `git branch` must route
  through
- `src/arduis/main.py` — `Adw.Application` entry point

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/arduis/window.py`: working `Adw.ApplicationWindow` + `Adw.ToolbarView`/`HeaderBar` +
  `Vte.Terminal` with Dracula palette, font, scrollback, **`feed_child` is available on the
  terminal** (used for clipboard paste pattern), and a tested **SIGHUP→SIGKILL process-group
  teardown** (`_on_close_request`/`_sigkill_if_alive`) that hibernate reuses verbatim.
- `src/arduis/spawn.py`: `build_spawn_command(runner)` returns the GTK-free `(argv, env)` pair
  routed through `HostRunner` — generalize to accept a worktree `cwd`.
- `src/arduis/host_runner.py`: `wrap_argv`/`wrap_env` no-op seam — `git worktree add`,
  `git branch`, `git rev-parse` calls go through it.
- `tests/` already covers exit-decode, host_runner, spawn argv, theme — extend the GTK-free
  pattern to `SessionStore` + git-argv builders (unit-testable, no GTK).

### Established Patterns
- Strict **GTK-free core** (spawn/theme/exit_status/host_runner) with `window.py` as the only
  `gi`-importing module + pytest on the seams. `SessionStore` and git-argv builders must
  follow this (GTK-free, unit-tested).
- `Vte.Terminal.spawn_async(PtyFlags.DEFAULT, cwd, argv, env, ...)` is the spawn entry point;
  Phase 2 changes `cwd` per worktree and follows with `feed_child("claude\n")`.
- App owns the terminal palette; spawn is login+interactive so PATH/shims resolve.

### Integration Points
- New domain/service layer: a `SessionStore` (GTK-free, serializable, RAM fields) + a git
  worktree service (argv via `HostRunner`, `Gio.Subprocess` async for non-PTY `git`/`git
  branch` queries so the GTK loop never blocks).
- `window.py` grows a `Adw.TabView`/`TabBar`; each worktree tab owns its own `Vte.Terminal`
  spawned with the worktree `cwd`.
- Short read-only git queries (`git rev-parse`, `git branch`, default-branch detection) →
  `Gio.Subprocess` + `communicate_utf8_async` per CLAUDE.md subprocess patterns.

### Obsolete / not applicable
- `.flatpak-builder/`, `build-dir/` — leftovers from the dropped Flatpak path; ignore.

</code_context>

<specifics>
## Specific Ideas

- "Igual BridgeMind / BridgeSpace" — the core loop is the product's heart: idea → isolated
  worktree with an agent running, in seconds. The mockups show the *eventual* multi-pane
  shell; Phase 2 ships the interim **tabbed** version that the Phase-3 sidebar absorbs.
- Terminal-centric: arduis launched **from inside the repo** (no repo-picker chrome in v1),
  matching how the user lives in the terminal/tmux.
- The durable-shell / ephemeral-agent model is deliberate: Ctrl+C always drops you to a usable
  worktree shell, never killing the pane.

</specifics>

<deferred>
## Deferred Ideas

- **Conclude / remove worktree + correct teardown ordering** (kill agent → compose down →
  verify clean → `git worktree remove` → prune) → **Phase 8** (REVIEW-03). Phase 2 only
  hibernates (keeps the directory); it never removes worktrees.
- **Persist `SessionStore` to disk / cold-reopen worktrees across an arduis quit-restart** →
  **v2** (with PERSIST-01). Per user: "isso fica para v2."
- **Reattach to a live agent after quitting the app** → **v2 (PERSIST-01)** — needs a
  host-side tmux/abduco layer.
- **Repo folder-picker / multiple-repo switching** → not Phase 2; launch-cwd is the v1 repo
  source. Revisit if/when arduis needs to manage worktrees across repos in one window.
- **`.arduis.toml` `[worktree] base/location/setup`** → **Phase 6**; Phase 2 uses hardcoded
  equivalents (default branch / sibling location) so the file is a later override, not a
  prerequisite.
- **Agent = configurable command / Ctrl+C swaps to another agent** → **Phase 5** (AGENT-01);
  Phase 2 hardcodes `claude` but the feed-into-shell mechanism already supports it.

</deferred>

---

*Phase: 02-core-loop-new-worktree-env-agent*
*Context gathered: 2026-06-09*
