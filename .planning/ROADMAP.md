# Roadmap: arduis

## Overview

arduis is built as a ladder of **vertical "degraus"** — each phase is installable and usable on its own, following Accelerate/DORA (small batches, trunk-based, `main` always working, dogfood early). arduis ships as **native packages** (`.deb` on Ubuntu, AUR on Arch) using the system VTE — Flatpak is out of v1, which removes the sandbox and the entire `flatpak-spawn --host` risk class. The journey starts with the foundation: one real VTE terminal running the host shell via a **direct native PTY** (like BridgeMind), behind a thin `HostRunner` seam that is a no-op for native builds but keeps a single place to reintroduce an optional Flatpak channel later (Phase 1). It then builds the product's heart — "new worktree → env → agent in seconds" (Phase 2) — and makes parallelism visible with a sidebar and RAM groundwork (Phase 3). The Core Value pillar, hooks-first attention detection ("which agent is waiting for me"), lands in Phase 4. Phases 5–6 respect the tmux-centric user (agent-as-command, configurable chords, themes) and make worktrees "ready to work" via `.arduis.toml` setup. Phase 7 adds opt-in isolated docker-compose stacks (the heaviest RAM line item, hence after RAM groundwork), Phase 8 closes the loop with read-only review + correct teardown, and Phase 9 ships it team-installable on Ubuntu + Arch as native packages. **RAM management is woven across Phases 2/3/4/7, not a single late phase.** Swarm is explicitly Phase-2-of-the-product / out of v1 — kept cheap via the GTK-free `SessionStore` and `AgentSpec` seams, never built here.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Terminal** - One real VTE terminal running host zsh via a direct native PTY, behind a thin no-op `HostRunner` seam, with Ctrl+C/job-control/exit-status acceptance tests
- [x] **Phase 2: Core Loop (new worktree → env → agent)** - "+New worktree" creates a worktree and opens a terminal with `claude` running; births the GTK-free SessionStore
- [x] **Phase 3: Parallel Worktrees + Sidebar + RAM Groundwork** - N worktrees side by side, free pane layout, sidebar with focus/switch, per-worktree RAM visibility and active caps
- [x] **Phase 03.1: worktree-as-terminal-workspace (INSERTED)** - Canvas shows ONE worktree's terminals (workspace); per-worktree LayoutModel; sidebar swaps the whole workspace; re-targeted C-Space/RAM/hibernate semantics
- [x] **Phase 03.2: Projects and Cross-Repo Tasks (INSERTED)** - Project = multi-repo root folder; task = set of worktrees (one per chosen repo) mirroring the root layout; sidebar lists tasks, workspace shows a task's terminals (completed 2026-06-12)
- [x] **Phase 03.3: Topbar Repo Chips (INSERTED, corrective)** - Surface member repos as toggleable chips in the topbar (mockup affordance, supersedes 03.2 D-06 name-only); toggled set seeds New-task default; active task reflected; detection filters out linked worktrees (completed 2026-06-14)
- [x] **Phase 4: Attention Detection (who's waiting)** - Hooks-first status (running/waiting/idle/ready), sidebar+pane dots, desktop notification, idle auto-suspend (completed 2026-06-13)
- [x] **Phase 5: Agent Swap + tmux Keybindings + Themes** - Agent = configurable command (Ctrl+C swaps), tmux-style chords, Dracula default + swappable themes (completed 2026-06-13)
- [x] **Phase 6: Per-Worktree Setup via `.arduis.toml`** - Repo config with sensible defaults; setup commands run on worktree creation via the login shell (completed 2026-06-13)
- [x] **Phase 7: Opt-in Isolated Containers** - Per-worktree docker-compose isolation with stable project name, auto port offset + probing, port badges, guaranteed teardown (completed 2026-06-14)
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
- [x] 01-01-PLAN.md — GTK-free tested seams + Wave-0 infra: HostRunner (no-op/Flatpak-stub), Dracula palette, exit-status decode, spawn argv builder, pytest config
- [x] 01-02-PLAN.md — GTK wiring: refactor draft into arduis package, spawn host zsh via the seam, apply palette, no-orphan close-request teardown, native run.sh, manual acceptance checklist
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
**Plans**: 3 plans
Plans:
- [x] 02-00-PLAN.md — Wave 0: RED test scaffolds (tests/test_worktree.py + tests/test_session.py) pinning the GTK-free domain contract
- [x] 02-01-PLAN.md — GREEN GTK-free domain: worktree.py git-argv/parse builders + serializable SessionStore + swarm/ seam
- [x] 02-02-PLAN.md — GTK wiring: git_service async runner, Adw.TabView + New-worktree dialog, spawn+feed claude, Hibernate/Resume, manual acceptance
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
**Plans**: 5 plans
Plans:
- [x] 03-01-PLAN.md — Wave 0: RED test scaffolds for the four GTK-free modules (layout, keymap, resource_monitor, caps)
- [x] 03-02-PLAN.md — GREEN GTK-free canvas+keyboard: layout.py binary split/leaf tree + keymap.py C-Space prefix dispatch
- [x] 03-03-PLAN.md — GREEN GTK-free RAM: resource_monitor.py /proc process-group RSS + pt-BR format + caps.py active-agent cap policy
- [x] 03-04-PLAN.md — window.py: replace TabView with sidebar + nested GtkPaned canvas reflecting LayoutModel (PAR-01/PAR-02/LAYOUT-01)
- [x] 03-05-PLAN.md — window.py: C-Space prefix machine + ~2s RAM poll + cap prompt-to-hibernate + presets/zoom + manual acceptance (PAR-03/RAM-02/RAM-03)
**UI hint**: yes

### Phase 03.2: Projects and Cross-Repo Tasks (INSERTED)

**Goal:** Pivot level 1 of the interface from "topbar = single git repos" to **project = multi-repo root folder** (the user's real layout: a root dir holding e.g. `backend/`, `frontend/`, `keycloak/` + root `CLAUDE.md`/`docker-compose.yml`, ideally versioned as a small meta-repo). Introduce **task** as the unit of work: creating a task picks 1+ of the project's repos, creates a branch-named worktree in each, and materializes a **task folder mirroring the root layout** (worktrees keep the repo dir names, root compose/config linked) so the project's tooling runs verbatim inside the task. Sidebar pivots from "worktrees" to **tasks of the selected project**; the workspace shows the selected task's terminals (default: one agent + one shell per chosen repo, or a single agent with `--add-dir` across repos — to decide in discuss-phase). Single-repo project is the degenerate case (task = 1 worktree, current 03.1 behavior unchanged). Hibernate/RAM/cap/teardown re-target from worktree to task.
**Requirements**: PAR-01, PAR-02, RAM-02, RAM-03 (re-targeted from worktree to task semantics); new level-1 scope superseding the old "topbar = repos" reading of docs/MOTIVATION.md
**Depends on:** Phase 03.1
**Success Criteria** (what must be TRUE):
  1. A project = root folder with N member repos; arduis opens a project and lists its tasks in the sidebar (single-repo roots work with zero extra config)
  2. "New task" picks 1+ member repos, creates same-named branches/worktrees in each, and materializes the task folder mirroring the root layout
  3. The task workspace opens with terminals for every chosen repo (agent placement per discuss-phase decision); swap/keys/RAM/hibernate operate per task
  4. Concluding/hibernating a task tears down every worktree's process groups (no orphans), keeping directories on hibernate
  5. Phase 03.1 single-worktree behavior is preserved as the 1-repo task case (no special-casing)
**Plans:** 3/3 plans complete

Plans:
- [x] 03.2-01-PLAN.md — GTK-free domain (TDD): project.py member detection + task_layout.py dir/symlink/resolve builders + session.py Task/RepoCheckout replacing WorktreeSession
- [x] 03.2-02-PLAN.md — window.py structural pivot: project resolution + name-only topbar, New-task dialog (repo multi-pick), per-repo async create chain + relative-symlink materializer, Task-keyed sidebar
- [x] 03.2-03-PLAN.md — window.py lifecycle: per-task hibernate/resume/RAM/cap across repos, startup scan of ../<root>-tasks/, close-a-repository (never delete), no-orphan teardown + manual UAT

### Phase 03.3: Topbar Repo Chips (INSERTED, corrective)

**Goal:** Correct Phase 03.2 D-06 (which flattened the topbar to a bare project-name string) back to the approved design (`docs/mockup/interface-v2-bridgespace.png` + `docs/MOTIVATION.md` 3-level model): surface the project's member repos as **toggleable chips in the topbar**, each with a status bolinha. The toggled-ON set becomes the DEFAULT repo selection seeded into the New-task dialog (per-task override preserved); the active task's repos are reflected/highlighted in the chips. A mandatory sub-fix narrows member-repo detection to `.git`-DIRECTORY subdirs so the ~20 linked worktrees on the user's real `Livon-Saude` root no longer flood the bar. Designed so Phase 7's 07-04 container toggle + port badges sit ALONGSIDE these chips (07-04 runs after this phase; both touch the topbar → sequential).
**Requirements**: PAR-02 (corrects D-06; level-1/topbar). PO-directed design correction; authoritative spec is the 6 LOCKED decisions D-01..D-06 in 03.3-CONTEXT.md.
**Depends on:** Phase 03.2 (and runs BEFORE Phase 7's 07-04, which builds its container UI onto this new topbar)
**Success Criteria** (what must be TRUE):
  1. The topbar renders one toggleable chip per member repo (status bolinha reusing the sidebar dot CSS), project name still visible (D-01)
  2. The toggled-ON chip set seeds the New-task dialog's per-repo checkboxes; per-task override preserved (D-02)
  3. Selecting/activating a task reflects its repos in the chips; pinned main clears the reflection (D-03)
  4. detect_member_repos counts only `.git`-DIRECTORY subdirs — the ~20 linked worktrees are excluded; degenerate 1-repo preserved (D-04)
  5. Chip overflow folds into a +N menu (no horizontal scroll); the degenerate 1-repo renders one chip (D-05 / criterion 5)
**Plans:** 3/3 plans complete

Plans:
- [x] 03.3-01-PLAN.md — GTK-free (TDD): D-04 detection filter (.git-DIRECTORY only) in project.py + topbar.ChipState (toggle/default/reflect) + tests
- [x] 03.3-02-PLAN.md — window.py: render the chip bar (ChipState-backed, dot CSS reused, name kept), seed the New-task dialog from the toggled-ON set, reflect the active task, +N overflow; leaves room for 07-04 badges
- [x] 03.3-03-PLAN.md — acceptance: headless broadway smoke (chips per repo, Livon-Saude filter, toggle→default, reflect, 1-repo) + live human-verify on the real multi-repo root
**UI hint**: yes

### Phase 03.1: worktree-as-terminal-workspace (INSERTED)

**Goal:** Pivot the workspace model to the approved 3-level interface (docs/MOTIVATION.md): the pane canvas shows the terminals of ONE worktree at a time (workspace), not multiple worktrees side by side. Each worktree owns its own layout tree and 2 default terminals (agent + shell); selecting a sidebar row swaps the whole workspace (tmux: panes = terminals, windows = worktrees). Re-targets Phase-3's PAR/LAYOUT/RAM behaviors under the new semantics; topbar/multi-repo (level 1) is out of scope.
**Requirements**: PAR-01, PAR-02, PAR-03, LAYOUT-01, RAM-02, RAM-03 (re-targeted under workspace semantics; anchored to decisions D-02..D-11)
**Depends on:** Phase 3
**Plans:** 3/3 plans complete

Plans:
- [x] 03.1-01-PLAN.md — GTK-free session model: TerminalRecord + N terminals per worktree + N-terminal hibernate (TDD)
- [x] 03.1-02-PLAN.md — window.py structural pivot: per-worktree LayoutModel, workspace swap, eager 2-terminal default
- [x] 03.1-03-PLAN.md — window.py lifecycle: re-targeted C-Space keys, per-worktree RAM sum, hibernate-all/resume-default, no-orphan close + manual UAT

### Phase 4: Attention Detection (who's waiting)
**Goal**: Solve the Core Value pillar — always knowing which agent is waiting for you — using a HOOKS-FIRST mechanism (Claude Code `Notification`/`Stop` hooks write per-worktree state files arduis watches), with terminal BEL/OSC as a secondary signal and activity-timeout as a soft fallback. Reliability of the status dot is the differentiator; scraping is explicitly NOT the primary signal (STATUS-04 scraping fallback for non-Claude agents is v2). **Re-anchored by 03.2:** sidebar rows are TASKS — a task's status aggregates its agents (any agent waiting → task waiting); state files stay per-worktree (where hooks run) and roll up per task.
**Depends on**: Phase 03.2
**Requirements**: STATUS-01, STATUS-02, STATUS-03, RAM-04
**Success Criteria** (what must be TRUE):
  1. When a `claude` agent pauses for input, its status flips to "waiting" via Claude Code hooks (state file), not screen-scraping
  2. Each worktree shows a status indicator (running / waiting / idle / ready) in the sidebar and the pane header
  3. The waiting state survives a Claude Code TUI redraw mid-response (no false orange) and fires for a real approval prompt (no missed orange)
  4. User gets a desktop notification (libnotify) + optional sound when an agent enters waiting and the window is unfocused
  5. Idle worktrees can be auto-suspended based on the detected idle status
**Plans**: 5 plans
Plans:
- [x] 04-01-PLAN.md — GTK-free hook script (env-guarded, 7-event map, atomic state files) + spawn.py extra_env injection seam (TDD)
- [x] 04-02-PLAN.md — GTK-free attention.py: 5-state model, state-file read/wipe, aggregation, settings merge, notify/auto-suspend policies, arduis.toml config (TDD)
- [x] 04-03-PLAN.md — window.py wiring: consent-gated hook install, env injection, Gio.FileMonitor watcher, sidebar+pane status dots, libnotify on waiting+unfocused, state-file cleanup
- [x] 04-04-PLAN.md — RAM-04 auto-suspend via existing hibernate machinery + `claude --continue` resume + degraded bell mode (consent declined)
- [x] 04-05-PLAN.md — Acceptance: headless broadway smoke + live human-verify checklist (5 criteria + UAT flags A1/A2)
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
**Plans**: 4 plans (3 waves)
Plans:
- [x] 05-01-PLAN.md — GTK-free themes.py registry (Dracula+Nord+Solarized+Gruvbox) + tests (UI-02)
- [x] 05-02-PLAN.md — agentconfig/keyconfig/appconfig loaders + keymap split/zoom/refeed + tests (AGENT-01/UI-01/UI-02)
- [x] 05-03-PLAN.md — window.py wiring: configurable feed + prefix/bindings + runtime theme switch + Tema menu + persistence
- [x] 05-04-PLAN.md — headless broadway smoke + live human-verify (criterion 3 under real Wayland)
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
**Plans**: 3 plans
Plans:
- [x] 06-01-PLAN.md — GTK-free domain (TDD): repoconfig.py [setup] reader + setup_feed_bytes + trust.py content-hash trust list
- [x] 06-02-PLAN.md — window.py wiring: CREATE-only trust-gated setup feed into the shell terminal (consolidated dialog)
- [x] 06-03-PLAN.md — acceptance: headless broadway smoke + live human-verify checklist for the 4 criteria

### Phase 7: Opt-in Isolated Containers
**Goal**: Per-TASK isolated docker-compose stacks, off by default — the thing the user misses most and the heaviest RAM line item, landing after the RAM groundwork. Docker calls run on the host directly through the `HostRunner` seam (no-op on native builds); snap-docker on Ubuntu and native docker on Arch both work. The container half of RAM management matures here. **Re-anchored by 03.2 (decided 2026-06-10):** the compose base is a SINGLE `docker-compose.yml` at the project ROOT (meta-repo) covering all member services (backend/frontend/keycloak/db share one network → service discovery by name works, and duplication is atomic); `COMPOSE_PROJECT_NAME` is unique per TASK, the override is generated into the task folder (which mirrors the root layout, so relative build contexts/bind mounts resolve verbatim), and teardown wires into task conclude/hibernate.
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
| 1. Terminal | 2/2 | Complete | 2026-06-09 |
| 2. Core Loop | 3/3 | Complete | 2026-06-09 |
| 3. Parallel + Sidebar + RAM | 5/5 | Complete | 2026-06-09 |
| 03.1. worktree-as-terminal-workspace | 3/3 | Complete | 2026-06-10 |
| 03.2. Projects and Cross-Repo Tasks | 3/3 | Complete    | 2026-06-12 |
| 4. Attention Detection | 5/5 | Complete    | 2026-06-13 |
| 5. Agent Swap + Keys + Themes | 4/4 | Complete    | 2026-06-13 |
| 6. Setup via `.arduis.toml` | 3/3 | Complete    | 2026-06-13 |
| 7. Isolated Containers | 5/5 | Complete    | 2026-06-14 |
| 8. Review + Cleanup | 0/TBD | Not started | - |
| 9. Packaging | 0/TBD | Not started | - |
