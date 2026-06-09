# Roadmap: arduis

## Overview

arduis is built as a ladder of **vertical "degraus"** — each phase is installable and usable on its own, following Accelerate/DORA (small batches, trunk-based, `main` always working, dogfood early). arduis ships as **native packages** (`.deb` on Ubuntu, AUR on Arch) using the system VTE — Flatpak is out of v1, which removes the sandbox and the entire `flatpak-spawn --host` risk class. The journey starts with the foundation: one real VTE terminal running the host shell via a **direct native PTY** (like BridgeMind), behind a thin `HostRunner` seam that is a no-op for native builds but keeps a single place to reintroduce an optional Flatpak channel later (Phase 1). It then builds the product's heart — "new worktree → env → agent in seconds" (Phase 2) — and makes parallelism visible with a sidebar and RAM groundwork (Phase 3). The Core Value pillar, hooks-first attention detection ("which agent is waiting for me"), lands in Phase 4. Phases 5–6 respect the tmux-centric user (agent-as-command, configurable chords, themes) and make worktrees "ready to work" via `.arduis.toml` setup. Phase 7 adds opt-in isolated docker-compose stacks (the heaviest RAM line item, hence after RAM groundwork), Phase 8 closes the loop with read-only review + correct teardown, and Phase 9 ships it team-installable on Ubuntu + Arch as native packages. **RAM management is woven across Phases 2/3/4/7, not a single late phase.** Swarm is explicitly Phase-2-of-the-product / out of v1 — kept cheap via the GTK-free `SessionStore` and `AgentSpec` seams, never built here.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Terminal** - One real VTE terminal running host zsh via a direct native PTY, behind a thin no-op `HostRunner` seam, with Ctrl+C/job-control/exit-status acceptance tests
- [ ] **Phase 2: Core Loop (new worktree → env → agent)** - "+New worktree" creates a worktree and opens a terminal with `claude` running; births the GTK-free SessionStore
- [ ] **Phase 3: Parallel Worktrees + Sidebar + RAM Groundwork** - N worktrees side by side, free pane layout, sidebar with focus/switch, per-worktree RAM visibility and active caps
- [ ] **Phase 4: Attention Detection (who's waiting)** - Hooks-first status (running/waiting/idle/ready), sidebar+pane dots, desktop notification, idle auto-suspend
- [ ] **Phase 5: Agent Swap + tmux Keybindings + Themes** - Agent = configurable command (Ctrl+C swaps), tmux-style chords, Dracula default + swappable themes
- [ ] **Phase 6: Per-Worktree Setup via `.arduis.toml`** - Repo config with sensible defaults; setup commands run on worktree creation via the login shell
- [ ] **Phase 7: Opt-in Isolated Containers** - Per-worktree docker-compose isolation with stable project name, auto port offset + probing, port badges, guaranteed teardown
- [ ] **Phase 8: Review + Cleanup** - Read-only diff, branch/PR status via git/gh, "conclude worktree" with correct teardown order
- [ ] **Phase 9: Packaging (AUR + .deb)** - Team-installable on Ubuntu + Arch under real Wayland as native packages using the system VTE; Flatpak deferred to v2

## Phase Details

### Phase 1: Terminal
**Goal**: A GTK4/libadwaita window with one real VTE terminal running the user's host `zsh` via a **direct native PTY** (no sandbox). All host execution still funnels through a thin `HostRunner` seam — a no-op for native builds — so an optional Flatpak channel can later prepend `flatpak-spawn --host` in one place without reshaping the code.
**Depends on**: Nothing (first phase)
**Requirements**: TERM-01
**Success Criteria** (what must be TRUE):
  1. User opens arduis and gets a working shell inside the window, running their host `zsh` with their own config and prompt, rendered in the **app's theme palette** (Dracula default — the app owns terminal colors, not the shell)
  2. `claude`, `gh`, and `docker` resolve inside the embedded terminal (host login-shell PATH and version-manager shims work)
  3. Ctrl+C interrupts a host subprocess and Ctrl+Z/`fg` job control work
  4. Exit codes and signals are decoded correctly (`os.waitstatus_to_exitcode`); closing the window kills the host `zsh`/agent with no orphans
  5. Runs on Ubuntu 24.04 (system `gir1.2-vte-3.91` 0.76) and Arch (`vte4` 0.84) under real Wayland; code targets the VTE 0.76 API floor; `HostRunner` is a no-op seam (direct spawn) with the Flatpak path stubbed but unused
**Plans**: 2 plans
Plans:
- [ ] 01-01-PLAN.md — GTK-free tested seams + Wave-0 infra: HostRunner (no-op/Flatpak-stub), Dracula palette, exit-status decode, spawn argv builder, pytest config
- [ ] 01-02-PLAN.md — GTK wiring: refactor draft into arduis package, spawn host zsh via the seam, apply palette, no-orphan close-request teardown, native run.sh, manual acceptance checklist
**UI hint**: yes

### Phase 2: Core Loop (new worktree → env → agent)
**Goal**: The heart of the product — clicking "+New worktree", choosing a branch, and getting a terminal with the default agent (`claude`) already running in the new worktree directory in seconds. Establishes the Presentation→Domain→Service direction and the GTK-free, serializable `SessionStore` (first swarm seam), with RAM fields on the model from day one.
**Depends on**: Phase 1
**Requirements**: WT-01, WT-02, WT-03, RAM-01
**Success Criteria** (what must be TRUE):
  1. User clicks "+New worktree", picks a new or existing branch, and a worktree is created via `git worktree add` at the configured location/base
  2. A terminal opens in the new worktree directory with the default agent (`claude`) already running
  3. Picking an already-checked-out branch is handled gracefully (focus existing / clear message) — never `--force`d
  4. User can hibernate a worktree (agent process killed, directory kept) and resume it later, freeing the agent's RAM
**Plans**: TBD
**UI hint**: yes

### Phase 3: Parallel Worktrees + Sidebar + RAM Groundwork
**Goal**: Parallelism made visible and bounded — many worktrees open at once, a sidebar bound to the `SessionStore`, a free (split/drag) pane layout instead of a fixed grid, and the RAM groundwork (ResourceMonitor + per-worktree RSS visibility + active caps) that makes the lightweight promise real at the 5–12 worktree working set.
**Depends on**: Phase 2
**Requirements**: PAR-01, PAR-02, PAR-03, LAYOUT-01, RAM-02, RAM-03
**Success Criteria** (what must be TRUE):
  1. User keeps several worktrees open simultaneously, each with its own terminal
  2. A sidebar lists all worktrees; selecting one focuses it, and the user can switch via tmux-style shortcuts
  3. User can split and rearrange panes freely (tmux-like) rather than being locked to a fixed grid
  4. Each worktree shows its current RAM usage in the UI
  5. A configurable cap on simultaneously active agents/containers is enforced when opening new worktrees
**Plans**: TBD
**UI hint**: yes

### Phase 4: Attention Detection (who's waiting)
**Goal**: Solve the Core Value pillar — always knowing which agent is waiting for you — using a HOOKS-FIRST mechanism (Claude Code `Notification`/`Stop` hooks write per-worktree state files arduis watches), with terminal BEL/OSC as a secondary signal and activity-timeout as a soft fallback. Reliability of the status dot is the differentiator; scraping is explicitly NOT the primary signal (STATUS-04 scraping fallback for non-Claude agents is v2).
**Depends on**: Phase 3
**Requirements**: STATUS-01, STATUS-02, STATUS-03, RAM-04
**Success Criteria** (what must be TRUE):
  1. When a `claude` agent pauses for input, its status flips to "waiting" via Claude Code hooks (state file), not screen-scraping
  2. Each worktree shows a status indicator (running / waiting / idle / ready) in the sidebar and the pane header
  3. The waiting state survives a Claude Code TUI redraw mid-response (no false orange) and fires for a real approval prompt (no missed orange)
  4. User gets a desktop notification (libnotify) + optional sound when an agent enters waiting and the window is unfocused
  5. Idle worktrees can be auto-suspended based on the detected idle status
**Plans**: TBD
**UI hint**: yes

### Phase 5: Agent Swap + tmux Keybindings + Themes
**Goal**: Respect the tmux-centric user's muscle memory and finalize the "agent = configurable command" abstraction (second swarm seam). The shell is the durable PTY child; agents are ephemeral commands run inside it, so Ctrl+C drops to the shell to launch another agent with zero re-spawn.
**Depends on**: Phase 2
**Requirements**: AGENT-01, UI-01, UI-02
**Success Criteria** (what must be TRUE):
  1. Agent is a configurable command (default `claude`); Ctrl+C drops to the shell and the user can run a different agent in the same pane
  2. tmux-style keybindings work (`C-Space`, `C-h/j/k/l`, split `-`/`=`, zoom `z`) and are configurable
  3. Keybindings work as app-scoped shortcuts under real Wayland (not just XWayland)
  4. App and terminal use a Dracula theme by default, and the user can switch to other themes (UI palette + VTE palette)
**Plans**: TBD
**UI hint**: yes

### Phase 6: Per-Worktree Setup via `.arduis.toml`
**Goal**: A new worktree is born "ready to work" — `.arduis.toml` is read with sensible defaults (works with no file), and its `setup` commands run on creation through the same resolved login shell as the agent.
**Depends on**: Phase 2
**Requirements**: ENV-01, ENV-02
**Success Criteria** (what must be TRUE):
  1. arduis reads `.arduis.toml` per repo and works correctly with sensible defaults when the file is absent
  2. Configured `setup` commands (e.g. `npm install`, `cp .env`, migrate, seed) run automatically on worktree creation, visibly in a pane
  3. Setup commands run via the host login shell so `npm`/`docker`/version-manager shims resolve identically on Ubuntu and Arch
  4. Setup from an unfamiliar repo's `.arduis.toml` is treated as trusted-repo-only (confirmation on first run)
**Plans**: TBD

### Phase 7: Opt-in Isolated Containers
**Goal**: Per-worktree isolated docker-compose stacks, off by default — the thing the user misses most and the heaviest RAM line item, landing after the RAM groundwork. Docker calls run on the host directly through the `HostRunner` seam (no-op on native builds); snap-docker on Ubuntu and native docker on Arch both work. The container half of RAM management matures here.
**Depends on**: Phase 6
**Requirements**: CONT-01, CONT-02, CONT-03, CONT-04, CONT-05
**Success Criteria** (what must be TRUE):
  1. arduis auto-detects `docker-compose.yml`; container integration is opt-in per worktree (default off)
  2. Turning on isolation for a worktree brings up its own stack with a stable, persisted `COMPOSE_PROJECT_NAME` and a generated `docker-compose.override.yml` (whole `ports` list rewritten) using compose-base from `main`
  3. Host ports are probed free before `up` (deterministic offset + retry on collision) and the resolved ports are shown as UI badges
  4. Removing a worktree tears down its containers (`down --remove-orphans --volumes`); a startup pass reconciles orphaned `arduis-*` projects after a crash
  5. All docker compose calls go through the `HostRunner` seam and work with snap docker on Ubuntu and native docker on Arch
**Plans**: TBD
**UI hint**: yes

### Phase 8: Review + Cleanup
**Goal**: Close both the work loop and the resource loop — read-only diff, branch/PR status via git/gh, and a "conclude worktree" action with the correct teardown order. The worktree-remove half is shippable independently; container teardown is gained from Phase 7.
**Depends on**: Phase 2 (worktree-remove); Phase 7 (container teardown)
**Requirements**: REVIEW-01, REVIEW-02, REVIEW-03, GIT-01
**Success Criteria** (what must be TRUE):
  1. User sees a read-only diff of a worktree's changes
  2. User opens a PR via `gh` (shell-out) and arduis reads and displays the PR status (read-only)
  3. arduis reads and displays the branch + PR status via git/`gh` (read-only, throttled)
  4. "Conclude worktree" follows the safe teardown order (kill agent → compose down → verify clean → `git worktree remove` → `prune`), never force-deleting a dirty tree
**Plans**: TBD
**UI hint**: yes

### Phase 9: Packaging (AUR + .deb)
**Goal**: Make arduis team-installable — the reason the project exists — as **native packages** on both target distros, using the system VTE (no bundling). Flatpak is out of v1 (deferred to v2 as an optional secondary channel that re-enables the `HostRunner` Flatpak path).
**Depends on**: Phase 8
**Requirements**: DIST-02, DIST-03, DIST-04
**Success Criteria** (what must be TRUE):
  1. A native AUR package (PKGBUILD depending on system `vte4` 0.84, `python-gobject`, `gtk4`, `libadwaita`) installs and runs on Arch
  2. A native `.deb` package installs and runs on Ubuntu 24.04 (depends on system `gir1.2-vte-3.91` 0.76, `python3-gi`, `gir1.2-gtk-4.0`, `libadwaita`)
  3. A clean install runs on both Ubuntu and Arch under real Wayland (hard gate)
  4. `HostRunner` confirmed as a no-op on native builds (direct PTY spawn; no `flatpak-spawn` dependency)
**Plans**: TBD

## Cross-Cutting: RAM Management & Swarm Seams (not phases)

**RAM management** is woven, not monolithic:
- Agent-half (model RAM fields, hibernate/kill, lazy-start-on-focus) — Phase 2 (RAM-01)
- ResourceMonitor + per-worktree RSS visibility + active caps — Phase 3 (RAM-02, RAM-03)
- Idle auto-suspend (depends on attention/idle detection) — Phase 4 (RAM-04)
- Container-half (compose stop/teardown, container RSS, `down -v`) matures with — Phase 7

**Swarm seams** stay free (no v1 cost, no v1 build): keep `SessionStore` GTK-free + serializable (Phase 2) and `AgentSpec` a plain command (Phase 5); leave `swarm/` a named empty directory. No mailbox/roles/MCP until v1 is dogfooded.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9
(Note: Phases 5 and 6 depend on Phase 2, not on 3/4 — they may be planned in parallel with the 3→4 line if desired.)

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Terminal | 0/2 | Planned | - |
| 2. Core Loop | 0/TBD | Not started | - |
| 3. Parallel + Sidebar + RAM | 0/TBD | Not started | - |
| 4. Attention Detection | 0/TBD | Not started | - |
| 5. Agent Swap + Keys + Themes | 0/TBD | Not started | - |
| 6. Setup via `.arduis.toml` | 0/TBD | Not started | - |
| 7. Isolated Containers | 0/TBD | Not started | - |
| 8. Review + Cleanup | 0/TBD | Not started | - |
| 9. Packaging | 0/TBD | Not started | - |
