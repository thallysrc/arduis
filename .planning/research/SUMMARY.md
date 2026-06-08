# Project Research Summary

**Project:** arduis
**Domain:** Lightweight Linux/GNOME desktop app orchestrating parallel AI coding agents (Claude Code) in git worktrees, with embedded VTE terminals, opt-in isolated docker-compose stacks, Flatpak-first distribution driving the host via `flatpak-spawn --host`
**Researched:** 2026-06-08
**Confidence:** HIGH

## Executive Summary

arduis is the Linux/GNOME, terminal-centric answer to Mac-only tools like BridgeSpace and Conductor: a single GTK4/libadwaita desktop process that supervises N long-lived AI agents, each in its own git worktree with a real embedded VTE terminal, optionally backed by an isolated docker-compose stack. The expert-validated way to build this is **single-threaded and event-driven**: each `Vte.Terminal` owns its own PTY and child, lifecycle and attention signals arrive as GLib signals on the main loop, and the control plane (git/gh/docker compose) is async `Gio.Subprocess` — never Python threads, never a hand-rolled PTY layer. The chosen stack (Python + PyGObject 3.56 + GTK4 + libadwaita + VTE 0.84.0, all from GNOME SDK 50, with VTE compiled in the Flatpak manifest) is current and sound. Two version notes: **fast_float must be pinned to `v8.1.0`** to match VTE 0.84.0's own wrap (the draft's `v8.2.8` is a drift), and **simdutf `v7.7.1` is correct**.

The single biggest decision in the product is **how to detect "an agent is waiting for you."** Research is unanimous and reshapes the original Degrau 4 requirement ("read VTE output"): detection must be **HOOKS-FIRST** — Claude Code `Notification`/`Stop` hooks write per-worktree state files that arduis watches — with terminal BEL/OSC notifications as a secondary signal and output-scraping only as a last-resort fallback for non-hookable agents. Scraping as the primary signal is fragile against Claude Code's heavy TUI repaints and will rot on every release; treating it as primary is an explicit anti-pattern. The second-biggest risk concentrates at the sandbox boundary: all host execution must funnel through one **`HostRunner`** seam, host commands need a **login shell** (env/PATH and version-manager shims are not inherited by `flatpak-spawn --host`), and docker compose must always route `--host` (so no docker-socket permission is ever needed — important because the user's docker is a snap).

The product's lightweight promise lives or dies on **RAM management, which is cross-cutting, not a late feature** — agents (~100–300 MB Node each) and isolated stacks (0.5–2 GB each) are the real cost, so hibernate/limits/visibility must be designed into the model from Degrau 2/3 and matured at Degrau 7, with containers defaulting to off. Finally, two cheap architectural seams — a **GTK-free, serializable `SessionStore`** and **`AgentSpec` = a configurable command** — are both already required by v1 and are exactly the attach points that keep the Phase-2 swarm tax-free, so they must be honored even though swarm itself is explicitly out of v1 scope.

## Key Findings

### Recommended Stack

The pinned stack is confirmed current and correct (see STACK.md). Everything but the C++ deps comes from GNOME SDK/Platform 50; VTE for GTK4 (Vte-3.91) is NOT in the runtime or Ubuntu 24.04 apt, so it is compiled in the manifest via three ordered modules (fast_float → simdutf → vte). Concurrency is GLib-loop-based; the agent terminals ARE the PTY-backed processes (VTE owns the PTY), and control-plane shell-outs use `Gio.Subprocess` async. No Python docker SDK — shell out `docker compose` through the host.

**Core technologies:**
- **Python 3.12 + PyGObject 3.56** (from SDK 50, do NOT pip-install) — app language + GTK/GLib/Vte bindings; RAM bottleneck is agents/containers not the GUI, so staying Python is correct.
- **GTK4 + libadwaita 1.x** (SDK 50) — native GNOME UI, adaptive widgets already used in the draft.
- **VTE 0.84.0 (Vte-3.91)** — embedded real terminal, same engine as GNOME Terminal; compiled in-manifest. **fast_float pinned `v8.1.0`** (matches VTE 0.84.0 wrap — correct the draft's v8.2.8); **simdutf pinned `v7.7.1`** (correct).
- **Flatpak runtime org.gnome.{Platform,Sdk} 50** — dev env == distribution; one build covers Ubuntu + Arch (primary), AUR + .deb native (where `flatpak-spawn` indirection drops away).
- **`tomllib`** (stdlib, read-only) for `.arduis.toml`; `Gio.Subprocess` + GLib loop for control plane; `Vte.spawn_async` for agent PTYs.

### Expected Features

The MVP maps 1:1 to ROADMAP Degraus 1–9 (see FEATURES.md). arduis's position = Conductor's embedded-terminal UX + workmux's mechanism rigor (hook-driven status, clean teardown) + tmux-native bindings, on Linux/GNOME, opt-in containers, RAM-first.

**Must have (table stakes):**
- Embedded VTE terminal running host zsh (D1) — foundation.
- Core loop: new worktree → env → agent running in seconds (D2) — *this is the product*.
- N parallel worktrees, isolated, with a sidebar + per-session status (D3).
- "Agent needs attention" surfacing (D4) — Core Value pillar; **hooks-first**.
- Agent = configurable command + tmux keybindings + Dracula/themes (D5).
- Per-worktree setup commands from `.arduis.toml` (D6).
- Read-only diff/review + conclude/cleanup with teardown (D8).
- Flatpak + AUR + .deb packaging (D9).

**Should have (competitive differentiators):**
- **Linux/GNOME native, team-installable Flatpak** — the unfilled gap; the reason the project exists.
- **First-class RAM management** (hibernate, limits, per-worktree visibility) — no competitor exposes this; Sculptor's always-on containers are the cautionary tale.
- **Opt-in isolated containers** per worktree with auto port offset, compose-base from `main` (D7) — off by default.
- **Hook-driven attention detection** — the differentiator is *reliability* of the status dot.

**Defer (v1.x / v2+):**
- Desktop notifications + sound, full session persistence across restart, richer scraping fallback for non-Claude agents (v1.x).
- Coordinated **swarm** (roles/mailbox/MCP/file-ownership) — explicit Phase 2, would kill v1 momentum.
- autoyes/yolo defaults, in-app PR creation UI, embedded editor, mobile/web — out of scope.

### Architecture Approach

A single GUI process in three horizontal layers (Presentation → Domain → Services) plus one host-driver seam (see ARCHITECTURE.md). The cardinal rule: Presentation observes Domain (GObject notify), Domain commands Services, Services touch the host ONLY through `HostRunner`. Data plane (terminal bytes) flows inside VTE's PTY at zero app cost; control plane (create/inspect/destroy) is explicit async shell-out. Crucially, VTE owns the PTY, so the worst `flatpak-spawn` job-control/SIGWINCH bugs are sidestepped — `flatpak-spawn --host zsh` is just the leaf command, and Ctrl+C/resize happen at the VTE↔PTY layer (but must still be acceptance-tested in Degrau 1).

**Major components:**
1. **PaneWidget** — one `Vte.Terminal` + header (status dot, port badges); owns PTY+child; maps VTE `bell`/`child-exited`/`contents-changed`/termprops → state events.
2. **SessionStore** (Domain) — THE source of truth: GTK-free, serializable `Gio.ListStore<Worktree>`; persistence + re-attach. **First swarm seam.**
3. **Services** — `WorktreeService`, `ComposeService`, `ConfigService`, `GitInfoService`, `ResourceMonitor` — stateless, async, all shelling out via `HostRunner`.
4. **HostRunner** — the single sandbox chokepoint: prepends `flatpak-spawn --host` (Flatpak) or no-ops (native AUR/.deb). Detect via `/.flatpak-info`/`FLATPAK_ID`.
5. **status/agent_state.py** — the Degrau-4 brain: event-first detection, scrape only as fallback.
6. **AgentSpec** = name→command (the "agent = configurable command" model). **Second swarm seam.** The shell is the durable PTY child; the agent is ephemeral, so agent-level state comes from the status layer, pane-level lifecycle from `child-exited`.

### Critical Pitfalls

1. **Status detection by screen-scraping is fundamentally fragile.** Claude Code's TUI repaints heavily → false positives/negatives, rots on every release. **Avoid:** HOOKS-FIRST (`Notification`/`Stop` → state file arduis watches), BEL/OSC secondary, activity-timeout scrape only as last resort. Reshapes Degrau 4; flag for a research spike.
2. **`flatpak-spawn --host` Ctrl+C / job-control / exit-status across the sandbox (Degrau 1's hidden weight).** Ctrl+C may not land on the host child; `child-exited` reports `flatpak-spawn`'s status, not the agent's; `tcsetpgrp` errors break job control (flatpak#3697, exit-status mangling flatpak-xdg-utils#10). **Avoid:** ensure VTE PTY is ctty, decode status with `os.waitstatus_to_exitcode`, use `--watch-bus`, and make Ctrl+C/Ctrl+Z/exit-decode **Degrau-1 acceptance tests** — not deferred to Degrau 5.
3. **Env/PATH not inherited by host commands.** `claude`/`gh`/`docker` and version-manager shims (asdf/mise/nvm) are missing under the portal's minimal PATH. **Avoid:** run agents/setup through a **login shell** (`flatpak-spawn --host zsh -l -c …`); never exec the binary directly or pass `None` env. Balance against pitfall 2 (fewer process-group hops).
4. **Docker via the wrong path + compose isolation leaks.** **Avoid:** route ALL docker compose through `--host` (no socket permission, handles snap-docker on Ubuntu); stable persisted `COMPOSE_PROJECT_NAME` (not dir-derived); probe free ports before `up`; `down --remove-orphans --volumes` on conclude; startup reconciliation of `arduis-*` projects.
5. **RAM blow-up blamed on GTK/Python.** N agents + N stacks = 3–15 GB. **Avoid:** RAM management is **cross-cutting from Degrau 2/3** (caps, hibernate, lazy-start-on-focus, per-worktree RSS visibility), containers default off, measure don't guess. Do not defer all RAM work to "later."

## Implications for Roadmap

The architecture is built outside-in along the existing degraus; each degrau is a runnable vertical slice introducing exactly one new layer/module. The suggested phase structure keeps that mapping while surfacing the cross-cutting concerns (RAM, HostRunner, swarm seams) explicitly.

### Phase 1: Terminal in a window + the sandbox seam (Degrau 1)
**Rationale:** Highest technical risk lives here — retire it first with one terminal. The `flatpak-spawn --host` boundary could invalidate the whole approach, and it is cheapest to discover now.
**Delivers:** A VTE terminal running host zsh via `HostRunner`; green offline Flatpak build (VTE + fast_float **v8.1.0** + simdutf v7.7.1).
**Addresses:** Embedded VTE terminal (table stakes).
**Avoids:** Pitfalls 1, 2, 3, 8. **Mandatory acceptance tests:** Ctrl+C interrupts a host subprocess, Ctrl+Z/fg work, exit codes/signals decoded (`os.waitstatus_to_exitcode`), closing the window kills host `claude`/`zsh` (no orphans), login-shell PATH resolves `claude`/`gh`/`docker`, sane scrollback default.

### Phase 2: Core loop — new worktree → env → agent (Degrau 2)
**Rationale:** This IS the product. Establishes the Presentation→Domain→Service direction and the model boundary.
**Delivers:** "+New worktree" → `git worktree add` → spawn VTE in dir → auto-run agent.
**Uses:** `WorktreeService` (async git shell-out via HostRunner), `tomllib`-backed config later.
**Implements:** `SessionStore` + `Worktree` model (**first swarm seam — GTK-free, serializable**); RAM fields land on the model here.
**Avoids:** Pitfall 9 (handle "branch already checked out" — never `--force`); RAM lazy-start-on-focus is a design decision here.

### Phase 3: Many worktrees + sidebar + RAM groundwork (Degrau 3)
**Rationale:** Parallelism made visible; the realistic working set (5–12 worktrees) is where RAM starts to matter.
**Delivers:** Sidebar bound to `Gio.ListStore`, pane grid, per-session status placeholder, ResourceMonitor scaffolding + per-worktree RSS visibility + active caps.
**Implements:** Reactive observe pattern; `ResourceMonitor`; cross-distro smoke test starts here (Wayland, Ubuntu + Arch).
**Avoids:** Pitfall 7 (RAM design, not a late add) and Pitfall 10 (dogfood both distros early).

### Phase 4: Attention detection — who's waiting (Degrau 4)
**Rationale:** Core Value pillar and the single most important mechanism decision. Reshaped by research from "read VTE output" to hooks-first.
**Delivers:** `status/agent_state.py`; sidebar dot + pane-header badge; status taxonomy running/waiting/idle/ready.
**Implements:** **HOOKS-FIRST** (Claude Code `Notification`/`Stop` → per-worktree state file watcher) → BEL/OSC termprops secondary → activity-timeout scrape last-resort fallback. Consumes the decoded exit-status from Phase 1.
**Avoids:** Pitfall 3. Filter hook event types (`Notification` over-fires); never claim certainty from heuristic state.

### Phase 5: Agent swap + tmux keybindings + themes (Degrau 5)
**Rationale:** The target user's #1 requirement (tmux muscle memory). Finalizes the "agent = command" abstraction.
**Delivers:** `AgentSpec` from `[agents]`, Ctrl+C-swaps-agent, app-scoped configurable chords, Dracula default + swappable themes.
**Implements:** **`AgentSpec` (second swarm seam)**; shell-is-durable-child model proven.
**Avoids:** Pitfall 10 (chords app-scoped, tested under real Wayland not XWayland); re-verify Pitfall 1.

### Phase 6: Per-worktree setup via `.arduis.toml` (Degrau 6)
**Rationale:** Without setup commands the worktree isn't "ready to work." Low cost on top of the core loop.
**Delivers:** `ConfigService` (tomllib load + defaults merge); setup-runner in WorktreeService, run through the same login shell.
**Avoids:** Pitfall 4 (same resolved env) and the security note (treat `.arduis.toml` setup as trusted-repo-only; confirm on first run).

### Phase 7: Opt-in isolated containers + port offset (Degrau 7)
**Rationale:** The thing the user misses most; also the heaviest RAM line item, so it lands after RAM groundwork.
**Delivers:** `ComposeService` + `ContainerStack` model; generated `docker-compose.override.yml` (whole `ports` list, not appended), stable persisted `COMPOSE_PROJECT_NAME`, probed free ports, port/RAM badges; container half of RAM management matures here.
**Implements:** Compose-base from `main`; `down --remove-orphans --volumes` teardown; startup reconciliation of `arduis-*` projects.
**Avoids:** Pitfalls 5 (always via `--host`, no socket perm, snap-docker safe) and 6 (isolation leaks).

### Phase 8: Review + cleanup (Degrau 8)
**Rationale:** Closes the loop and the resource loop; can ship the worktree-remove half before D7 then gain container teardown after.
**Delivers:** Read-only `git diff` view, read PR status via `gh`, "conclude worktree" with correct teardown order.
**Implements:** `GitInfoService` (throttled, read-only).
**Avoids:** Pitfall 9 (teardown order: kill agent → compose down → check clean → `worktree remove` → `prune`; never `rm -rf`, never force-delete dirty trees).

### Phase 9: Packaging — Flatpak / AUR / .deb (Degrau 9)
**Rationale:** Team-installability is the reason the project exists; proves the single-seam design across channels.
**Delivers:** Flathub-ready manifest (primary), AUR PKGBUILD (system `vte4` 0.84), .deb (verify Ubuntu 24.04 GTK4-VTE — may need backport).
**Implements:** `HostRunner` no-op for native builds.
**Avoids:** Pitfall 8 (reproducible offline VTE build, dep-triplet documented) and Pitfall 10 (hard gate: clean Ubuntu + Arch install under real Wayland).

### Cross-cutting (not a phase): RAM management & the swarm seams
- **RAM management** is woven through D2 (model fields, lazy-start), D3 (ResourceMonitor + caps + visibility), D7 (container hibernate/teardown). Do not treat as one degrau.
- **Swarm seams** are paid for free if Phases 2 and 5 keep `SessionStore` GTK-free/serializable and `AgentSpec` as a plain command. The `swarm/` directory stays a named, empty seam in v1. No mailbox/roles/MCP until v1 is dogfooded (Pitfall 11).

### Phase Ordering Rationale
- **Dependencies:** VTE foundation (D1) → core loop (D2) → everything. Attention (D4) needs the sidebar (D3); review/cleanup (D8) gains container teardown only after D7; RAM's container half follows D7.
- **Risk-first:** the sandbox seam (D1) and the detection mechanism (D4) are the two highest-uncertainty pieces and are scheduled to retire risk early, with explicit acceptance tests / a research spike.
- **Pitfall avoidance:** ordering puts the cheap seams (GTK-free model, AgentSpec) and RAM groundwork before the heavy container phase, so isolation and hibernate land on a model that already supports them.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 1 (Degrau 1):** `flatpak-spawn --host` Ctrl+C/job-control/exit-status across the sandbox — needs hands-on acceptance-test spike (flatpak#3697, #4827). Hidden weight; do not assume it "just works."
- **Phase 4 (Degrau 4):** hooks-first attention detection — focused spike on Claude Code hook payloads/event filtering and the state-file watcher; the `Notification` vs `waiting_for_user_action` ambiguity is evolving upstream.
- **Phase 7 (Degrau 7):** compose isolation edge cases (port probing, stable project IDs, bind-mount non-isolation, startup reconciliation) and snap-docker-on-Ubuntu behavior.
- **Phase 9 (Degrau 9):** verify Ubuntu 24.04 GTK4-VTE availability for the .deb (may need backport/PPA).

Phases with standard patterns (lighter research):
- **Phases 2, 3 (Degraus 2, 3):** git worktree mechanics + GTK4 ListView/ListStore are well documented; the model boundary is a known pattern.
- **Phases 5, 6 (Degraus 5, 6):** keymap→actions, theming, tomllib config are established; main risk is Wayland keybinding testing, not unknowns.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Core stack verified against GitLab tags, Arch packages, Flathub, PyGObject release notes. One concrete correction (fast_float v8.1.0); operational caveats around `flatpak-spawn` are MEDIUM. |
| Features | HIGH | Grounded in 10+ named competitor tools; the critical status-detection mechanism verified against workmux source and Claude Code hook issues. |
| Architecture | HIGH | Concurrency/PTY model and component boundaries verified against VTE + GLib docs and the flatpak issue tracker. MEDIUM only on exact VTE 0.84 termprop symbol names and the (unshipped) swarm seams. |
| Pitfalls | HIGH | Flatpak/VTE/git/docker mechanics verified against upstream issues, manpages, docs. MEDIUM for Claude Code detection behavior (evolving) and RAM thresholds (synthesized, not benchmarked). |

**Overall confidence:** HIGH

### Gaps to Address
- **Exact VTE 0.84 termprop symbol names** for OSC 9/777 notifications — verify against the SDK 50 `Vte-3.91` typelib during Degrau 4 (architecture confirmed the family exists, not every symbol).
- **`flatpak-spawn --host` signal/ctty behavior in the SDK 50 runtime** — only validatable by running the Degrau-1 acceptance tests; have the fallback (explicit portal SIGINT to host PID) ready.
- **Claude Code hook event semantics** (`Notification` over-fire, no clean `waiting_for_user_action` yet) — evolving upstream; design the watcher to filter event types and tolerate schema changes.
- **RAM thresholds / caps defaults** — synthesized, not benchmarked; tune against real dogfooding at 5–12 worktrees.
- **Ubuntu 24.04 GTK4-VTE for .deb** — per-release availability check at Degrau 9.
- **Port-offset vs. auto-probe** — research resolves toward deterministic offset-by-slot + probe + persist; confirm during Degrau 7.

## Sources

### Primary (HIGH confidence)
- VTE GitLab tags / `fast_float.wrap` (v8.1.0) / `simdutf.wrap` (v7.7.1) at tag 0.84.0 — version pins.
- Arch `vte4` 0.84.0-1, Vte-3.91 GTK4 reference docs — native VTE availability + bindings.
- Flathub org.gnome.{Platform,Sdk} 50, GNOME Foundation 2026-03-20, PyGObject 3.56.0 notes — runtime currency.
- Flatpak sandbox-permissions + `flatpak-spawn(1)`; flatpak issues #3697/#4827; flatpak-xdg-utils PR #10 + Will Thompson exit-code post — host-spawn signal/exit/job-control semantics.
- VTE `spawn_with_fds_async`/`watch_child`, GLib `child_watch_add`, GNOME/VTE issue #8, VTE scrollback docs — concurrency model + scrape caveats.
- Claude Code hooks guide + issue #36850 (BEL/OSC on waiting) + OSC 133 shell integration — hooks-first detection.
- Docker Compose project-name isolation + override-merge docs; compose orphan/`--remove-orphans` issues — container isolation.
- git-worktree docs (already-checked-out, prune, submodules) — worktree lifecycle.
- workmux (hook→state-file→emoji), Sculptor (always-on containers), Conductor — competitive mechanism/UX references.

### Secondary (MEDIUM confidence)
- Contour OSC 133 + PyGObject threading guide — semantic-prompt + idle_add patterns.
- Debian `libvte-2.91-gtk4-0` (sid) — GTK4 VTE packaging; verify Ubuntu 24.04.
- Claude Code attention issues #11665/#12048/#13024/#36885, cmux #2576 — `Notification` vs waiting ambiguity (evolving).
- worktree-compose / runtime-isolation writeups — `base+index*offset` port pattern.
- flatpak issues #5278/#2418, zed/codium env issues — PATH-not-inherited evidence.

### Tertiary (LOW confidence)
- Conductor/BridgeSpace marketing sites — UX intent, mechanism undisclosed.
- Claude Squad status mechanism — feature list HIGH, mechanism undocumented.
- RAM thresholds (~100–300 MB/agent, 0.5–2 GB/stack) — synthesized, needs dogfooding benchmark.

---
*Research completed: 2026-06-08*
*Ready for roadmap: yes*
