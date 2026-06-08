# Architecture Research

**Domain:** Python/GTK4/libadwaita/VTE desktop app that supervises N long-lived AI-agent processes, each in a git worktree, optionally with isolated docker-compose stacks, inside a Flatpak sandbox driving the host via `flatpak-spawn --host`.
**Researched:** 2026-06-08
**Confidence:** HIGH for the concurrency/PTY model and component boundaries (verified against VTE + GLib docs and flatpak issue tracker); MEDIUM for the precise VTE 0.84 signal/termprop names (verified family-of-features, not every symbol) and the swarm seams (design reasoning, not a shipped reference).

---

## Headline Findings (read these first)

1. **There is no "threading for many terminals" problem.** Each `Vte.Terminal` owns its own PTY, runs its own child, reads its own output, and reports lifecycle events as GLib signals on the main loop. N terminals = N event sources on one GLib main loop. **The default and correct concurrency model is single-threaded, event-driven.** You never read PTY bytes yourself, and you never block the UI doing so. Threads are needed only for the *control plane* shell-outs (`git`, `gh`, `docker compose`), and even those should use async GLib subprocess, not Python threads. (HIGH — confirmed: VTE watches the child via `vte_terminal_watch_child()` and emits `child-exited`; GLib provides `child_watch_add`/`io_add_watch`/async subprocess for the control plane.)

2. **"Waiting for input" detection should be event-based, not text-scraping.** Claude Code already emits a terminal **BEL** (and OSC 9 / OSC 777 desktop-notification sequences) when it pauses for input or tool-approval. VTE surfaces these: the `bell` signal, plus **termprops** (since VTE 0.78, present in the pinned 0.84) that translate legacy OSC 9/99/777 notifications. Listen for those signals → set state. Text-scraping (`get_text()` + regex) is the **fallback**, not the primary. This is the single most important architectural decision in the status layer and it makes Degrau 4 cheap and robust. (HIGH for BEL/OSC behaviour of Claude Code; HIGH that VTE forwards them; MEDIUM on the exact 0.84 termprop symbol names.)

3. **VTE owns the PTY, which sidesteps the worst `flatpak-spawn` bugs.** The known flatpak-spawn pain (`#4827` SIGWINCH/job-control, `#3697` `tcsetpgrp`) bites apps that *create their own PTY and relay through* flatpak-spawn. Here, **VTE creates the PTY**; `flatpak-spawn --host` is just the leaf `argv[0]` running inside that PTY. Window resize → VTE writes the new winsize to *its* PTY → the kernel delivers SIGWINCH to the foreground process group on that PTY. Ctrl+C is a control byte VTE writes into the PTY, processed by the host shell's line discipline — not a signal that has to traverse the portal. Exit-code propagation through flatpak-spawn is fixed in modern flatpak. **Net: the sandbox boundary is benign for the interactive case** — but verify resize + Ctrl+C end-to-end in Degrau 1 because the portal hop is the one place this could surprise us. (MEDIUM-HIGH — reasoning from how VTE PTYs and flatpak-spawn work; flagged as a Degrau-1 acceptance test.)

---

## Standard Architecture

The system is a **single GUI process** organized as three horizontal layers plus a thin host-driver seam. The agents and containers are *external OS processes the app supervises* — they are not in-process.

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│  PRESENTATION  (GTK4 / libadwaita widgets — main thread only)          │
│  ┌────────────┐  ┌──────────────────────────────────────────────┐     │
│  │ Sidebar    │  │ Pane grid / tabs                              │     │
│  │ (worktree  │  │ ┌──────────┐ ┌──────────┐ ┌──────────┐        │     │
│  │  list +    │  │ │Vte.Term  │ │Vte.Term  │ │Vte.Term  │  ...   │     │
│  │  status    │  │ │+ header  │ │+ header  │ │+ header  │        │     │
│  │  dots +    │  │ │(badges)  │ │(badges)  │ │(badges)  │        │     │
│  │  RAM bars) │  │ └────┬─────┘ └────┬─────┘ └────┬─────┘        │     │
│  └─────┬──────┘  └──────┼────────────┼────────────┼──────────────┘     │
│        │ observes       │ owns PTY   │            │  (signals: bell,    │
│        │ (GObject       │ child-exited, contents-changed, termprops)   │
│        ▼ notify)        ▼            ▼            ▼                     │
├──────────────────────────────────────────────────────────────────────┤
│  DOMAIN / STATE  (plain Python GObjects — the single source of truth)  │
│  ┌──────────────────────────────────────────────────────────────┐     │
│  │ SessionStore: Gio.ListStore<Worktree>                         │     │
│  │   Worktree { path, branch, base, status, agent_cmd,           │     │
│  │              AgentProcess?, ContainerStack?, rss_kb,          │     │
│  │              hibernated:bool }                                │     │
│  │   AgentProcess { pid, command, state, term_ref }              │     │
│  │   ContainerStack { project_name, mode, port_map, state }      │     │
│  └──────────────────────────────────────────────────────────────┘     │
│        │ commands (create/hibernate/teardown/...)                      │
│        ▼                                                                │
├──────────────────────────────────────────────────────────────────────┤
│  SERVICES  (stateless modules — orchestrate the host via async calls)  │
│  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐   │
│  │ WorktreeSvc │ │ ComposeSvc   │ │ ConfigSvc    │ │ GitInfoSvc   │   │
│  │ (git wktree │ │ (override    │ │ (.arduis.toml│ │ (git/gh read │   │
│  │  add/remove)│ │  gen, ports, │ │  + defaults) │ │  branch/PR)  │   │
│  │             │ │  up/down)    │ │              │ │              │   │
│  └──────┬──────┘ └──────┬───────┘ └──────────────┘ └──────┬───────┘   │
└─────────┼───────────────┼──────────────────────────────────┼──────────┘
          │ flatpak-spawn --host  (the ONLY way out of the sandbox)      │
          ▼               ▼                                  ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  HOST:  git · gh · docker compose · zsh · claude (agents)     │
   └──────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility (what it OWNS) | Implementation |
|-----------|------------------------------|----------------|
| **PaneWidget** | One VTE terminal + its header (title, status dot, container/port badges). Owns the PTY+child. Translates VTE signals → state events. | `Vte.Terminal` subclass/composite; connects `child-exited`, `bell`, `contents-changed`, termprops-changed. |
| **Sidebar / GridView** | Renders `SessionStore` reactively. No business logic. Emits user intents (new worktree, focus, hibernate, conclude). | `Gtk.ListView`/`Adw` bound to `Gio.ListStore`. |
| **SessionStore** | THE source of truth: list of `Worktree` GObjects + their agent/container/status. Persisted to disk. | `Gio.ListStore` of `GObject.Object` subclasses with notifiable properties. |
| **AgentProcess (model)** | What command runs, its lifecycle state, link to its PaneWidget. The "agent = configurable command" abstraction lives here. | Plain GObject; the actual process lives in VTE's PTY. |
| **ContainerStack (model)** | Per-worktree compose identity: `COMPOSE_PROJECT_NAME`, mode (off/isolated), port map, up/down state. | Plain GObject. |
| **WorktreeService** | `git worktree add/list/remove`, branch resolution, setup-command execution. Stateless. | Async shell-out via `Gio.Subprocess` → `flatpak-spawn --host git …`. |
| **ComposeService** | Detect `docker-compose.yml`, generate `docker-compose.override.yml` (port offset), pick `COMPOSE_PROJECT_NAME`, `up -d`/`down -v`, parse running ports. | Async shell-out to `docker compose`. |
| **ConfigService** | Load/merge `.arduis.toml` over hard-coded defaults; expose typed config. | `tomllib` (stdlib). |
| **GitInfoService** | Read-only `git`/`gh` polling: branch, dirty state, PR status. | Async shell-out; throttled. |
| **HostRunner** | The single seam that prepends `flatpak-spawn --host …` (or no-op in native .deb/AUR builds). Everyone shells out *through* this. | Thin wrapper around `Gio.Subprocess` / VTE spawn argv. |
| **ResourceMonitor** | Periodic RSS accounting per worktree (sum agent + container RSS); feeds RAM bars; triggers/enforces hibernate limits. | GLib timeout reading `/proc/<pid>/smaps_rollup` (host) + `docker stats --no-stream`. |

**The cardinal boundary rule:** Presentation observes Domain; Domain commands Services; Services touch the host only through HostRunner. Presentation NEVER shells out directly, and Services NEVER touch widgets. This is what keeps the swarm layer (below) cheap to add — it plugs into Domain, not into widgets.

---

## Recommended Project Structure

```
src/arduis/
├── app.py                  # Adw.Application, window, action wiring
├── window.py               # main window: sidebar + pane grid layout
├── host.py                 # HostRunner: flatpak-spawn --host seam (the ONLY exit)
│
├── model/                  # DOMAIN — plain GObjects, no GTK widget imports
│   ├── session_store.py    # Gio.ListStore<Worktree>, persistence, re-attach
│   ├── worktree.py         # Worktree GObject (status, paths, refs)
│   ├── agent.py            # AgentProcess GObject + AgentSpec ("agent = command")
│   └── container_stack.py  # ContainerStack GObject (project_name, ports, mode)
│
├── services/               # SERVICES — stateless, async shell-out via host.py
│   ├── worktree_service.py # git worktree add/list/remove + setup runner
│   ├── compose_service.py  # override gen, port offset, up/down, port parse
│   ├── config_service.py   # .arduis.toml load + defaults merge (tomllib)
│   ├── gitinfo_service.py  # read-only git/gh polling
│   └── resource_monitor.py # per-worktree RSS accounting, hibernate enforcement
│
├── widgets/                # PRESENTATION — GTK4/Adw only, observes model
│   ├── pane.py             # Vte.Terminal composite + header + status dot
│   ├── sidebar.py          # worktree list bound to SessionStore
│   ├── status_dot.py       # running/waiting/idle/ready indicator
│   └── badges.py           # container/port badges
│
├── status/                 # STATUS DETECTION (the Degrau-4 brain)
│   └── agent_state.py      # maps VTE bell/OSC/termprops → AgentProcess.state
│
├── keybinds.py             # tmux-style keymap (configurable) → Gtk actions
├── theme.py                # Dracula default + swappable palettes
│
└── swarm/                  # PHASE 2 ONLY — empty/absent in v1 (see seams below)
    ├── shared_state.py     # shared context/board file reader-writer
    ├── mcp_server.py        # exposes board over MCP
    └── coordinator.py       # a Claude with a prompt + tools
```

### Structure Rationale

- **`model/` has zero GTK-widget imports.** This is the seam that lets the swarm layer and persistence read/write state without going through the UI. If `import Gtk` appears in `model/`, the boundary has leaked.
- **`host.py` is a single chokepoint.** Native (.deb/AUR) builds flip one flag and drop the `flatpak-spawn --host` prefix. Tests stub it. Sandbox vs. host concerns live in exactly one file.
- **`status/` is its own module**, not buried in the pane widget, because status detection is the hardest-to-get-right per-agent logic and will gain per-agent-type strategies (claude vs. codex vs. aider) over time.
- **`swarm/` is a named, empty seam in v1** so the directory's existence documents the intended attach point without any v1 cost.

---

## Architectural Patterns

### Pattern 1: Event-driven supervision on a single GLib main loop (NO worker threads for terminals)

**What:** Each terminal is `Vte.Terminal` which internally creates a PTY, spawns the child via `spawn_async`, and calls `watch_child` so GLib watches the PID. The app connects to signals; GLib delivers them on the main loop. N terminals scale as N independent event sources — no per-terminal thread, no select loop you write, no UI blocking.

**When to use:** Always, for terminal I/O and lifecycle. This is VTE's designed model.

**Trade-offs:** You must keep signal handlers *fast* (they run on the UI thread). Anything slow (a `git`/`docker` call) must be async (`Gio.Subprocess` with callback) — never synchronous in a handler.

**Example:**
```python
def spawn_agent(term: Vte.Terminal, worktree_path: str, agent_argv: list[str]):
    argv = host.wrap(["zsh", "-i", "-c", " ".join(agent_argv)])  # -> flatpak-spawn --host ...
    term.spawn_async(
        Vte.PtyFlags.DEFAULT, worktree_path, argv, None,
        GLib.SpawnFlags.DEFAULT, None, None, -1, None, on_spawned,
    )

# Lifecycle: VTE already watch_child'd the pid for us.
term.connect("child-exited", lambda t, status: store.mark_exited(wt, status))
# Status: agent asked for attention.
term.connect("bell", lambda t: store.set_status(wt, Status.WAITING))
# Resize/SIGWINCH is handled by VTE<->PTY automatically; nothing to do here.
```

### Pattern 2: Status detection — event-first, scrape-fallback

**What:** Map agent attention signals to `Worktree.status`. Primary inputs are VTE's `bell` signal and OSC-9/777 notifications (surfaced as termprops in VTE ≥0.78). Fallback is a debounced `contents-changed`-driven scan: if no output for T seconds *and* the tail matches a known "waiting" pattern, mark WAITING; output resuming → RUNNING; child-exited → READY/IDLE.

**When to use:** Degrau 4. Build the event path first (covers Claude Code's BEL/OSC); add the scrape heuristic only for agents that don't emit signals.

**Trade-offs:** `contents-changed` also fires on resize and can't alone distinguish new output (GNOME VTE issue #8) — so the scrape path must track last cursor row/col to disambiguate, and must be debounced to avoid burning CPU per byte. Prefer never relying on it for Claude.

**State machine:**
```
SPAWNING ──spawned──▶ RUNNING ──bell/OSC──▶ WAITING ──output──▶ RUNNING
   │                     │                                         │
   │                     └────idle timeout (no output T s)────▶ IDLE
   └──child-exited──▶ READY (clean) / ERROR (nonzero)   ◀──────────┘
```

### Pattern 3: Per-worktree compose isolation via project name + generated override

**What:** Isolation is achieved with three host-level primitives, no app-level container runtime:
1. `COMPOSE_PROJECT_NAME = arduis_<repo>_<branch-slug>` → separate networks/volumes/container names → empty isolated DB for free.
2. A generated `docker-compose.override.yml` rewriting host port mappings by `port_offset * worktree_index` (e.g. base `5432` → `5433`, `5434`…). Compose auto-merges override on top of base.
3. Base compose always taken from the **`main`** checkout, not the branch worktree (trunk-based env), per the decided constraint.

**When to use:** Degrau 7, opt-in per worktree (default off).

**Trade-offs:** Auto-assigned offsets need a collision check (probe the host port before `up`); the open question "auto vs. fixed predictable ports" from MOTIVATION resolves toward *deterministic offset by worktree slot index*, displayed in the badge, with a fallback scan if taken. Teardown must be `down -v` (drop volumes) on worktree conclude, or isolated DBs leak disk.

**Example (generation sketch):**
```python
def make_override(base_ports: dict[str, int], offset: int) -> dict:
    # base_ports: {"db": 5432, "api": 8080} parsed from main's compose
    return {"services": {svc: {"ports": [f"{p+offset}:{p}"]}
                         for svc, p in base_ports.items()}}
# run: docker compose -p <project> -f main/compose.yml -f .override.yml up -d
```

### Pattern 4: "Agent = configurable command" + Ctrl+C swap

**What:** An `AgentSpec` is just a name→command string from `[agents]` in `.arduis.toml`. A pane always runs `zsh` first; the app *types* the default agent command into the PTY (or spawns `zsh -ic '<cmd>'`). Ctrl+C is a normal control byte the user sends to the foreground agent; when it dies, the host shell is revealed (because the shell is the actual PTY child, the agent is a child of the shell). The user (or app via a quick-switcher) then runs another agent command in the same shell.

**Why this is the right shape:** It means "swap agent" requires zero process re-parenting and zero VTE re-spawn — the pane/PTY/shell persist across agent swaps. The agent is ephemeral; the shell is the durable child VTE watches. This also means `child-exited` fires on *shell* exit (pane closed), not on agent exit — so agent-level state (running/waiting/exited) comes from the status layer (Pattern 2), while pane-level lifecycle comes from `child-exited`. Keep these two lifecycles distinct.

**Trade-off:** Because the shell is the watched child, detecting "the agent exited but shell is alive" relies on the status layer (prompt re-appearance / OSC 133 `D` command-finished), not on `child-exited`. Acceptable, and OSC 133 (emitted by the vte.sh shell integration) gives a clean signal for "back at the prompt."

### Pattern 5: Persistence & re-attach across app restart

**What:** `SessionStore` serializes to `~/.local/share/arduis/sessions.json` (inside sandbox; maps to host via portal). On restart, worktrees on disk still exist (git worktrees are durable) and isolated containers may still be running (`docker compose ls` to discover by project-name prefix). The app **re-discovers** rather than trusting stale PIDs: list worktrees from git, list compose projects matching `arduis_*`, and re-create panes (cold — agent not auto-rerun unless configured). Agent processes themselves do NOT survive (their PTY died with the app); re-attach means "rebuild the workspace view + reconnect to still-running containers," not "reattach to a live agent PTY."

**Trade-off:** True agent-process reattach would require running agents under a host-side multiplexer (tmux/abduco) — explicitly heavier and out of scope for v1. Document it as a deliberate limitation: closing arduis kills agents but preserves worktrees and containers.

---

## Data Flow

### "New worktree" core loop (Degrau 2, the heart)

```
[＋ New worktree click]
   ↓ (UI intent)
Window → SessionStore.create_worktree(branch, base)
   ↓ (command)
WorktreeService.add()  ──flatpak-spawn--host──▶  git worktree add ../slug -b branch main
   ↓ (async callback on success)
ConfigService.load(repo)  → setup commands
WorktreeService.run_setup() ──host──▶ npm install / cp .env / migrate   (in a pane, visible)
   ↓
SessionStore.append(Worktree{...})  → property notify
   ↓ (observed)
Sidebar adds row;  PaneWidget spawns Vte.Terminal in worktree dir
   ↓
PaneWidget types default agent command (claude)
```

### Status flow (Degrau 4)

```
agent pauses for input
   ↓ emits BEL / OSC 9 / OSC 777
Vte.Terminal "bell" / termprops-changed signal  (main loop)
   ↓
status/agent_state.py → Worktree.status = WAITING  (property notify)
   ↓ observed (no polling)
Sidebar dot turns orange + pane header dot turns orange
```

### Control-plane vs. data-plane (the key separation)

- **Data plane** (terminal bytes, agent I/O): flows *inside* VTE's PTY. The app never touches these bytes except to observe signals. High volume, zero app cost.
- **Control plane** (create/destroy/inspect): explicit async `Gio.Subprocess` calls through HostRunner, low frequency, results marshalled back to the model. This is where threads/async matter — and `Gio.Subprocess` keeps it off worker threads entirely.

---

## Scaling Considerations

"Scale" here = number of concurrent worktrees/agents/containers on one developer machine, bounded by RAM, not users.

| Scale | Adjustments |
|-------|-------------|
| 1–4 worktrees | Trivial. Everything live. No RAM management needed (but build the hooks). |
| 5–12 worktrees | RAM matters: agents ~100–300 MB each (Node), isolated stacks 0.5–2 GB each. ResourceMonitor + configurable active-agent/active-container caps + hibernate. This is the realistic working set and the design target. |
| 12+ worktrees | UI: switch pane grid to lazy/virtualized (don't keep 20 live VTEs rendered). Force-hibernate idle worktrees; show them as cold rows. GLib main loop handles the event count fine; RAM is the wall, hence hibernate is first-class, not an afterthought. |

### Scaling priorities (what breaks first)

1. **RAM from isolated containers** breaks first (GBs). Mitigation: default containers OFF; `down` (keep volumes) on hibernate, `down -v` on conclude; cap concurrent stacks.
2. **RAM from agents** second. Mitigation: hibernate kills the agent (`SIGTERM` to the agent's process group via the PTY), keeps the worktree dir; "wake" re-spawns.
3. **Render cost of many live VTEs** third. Mitigation: virtualize the grid; only foreground/visible panes stay live.

---

## Anti-Patterns

### Anti-Pattern 1: Python threads (or a hand-rolled select loop) to read PTY output
**What people do:** Spawn a thread per terminal to read the PTY and marshal to the UI with `idle_add`.
**Why it's wrong:** VTE already does all of this on the main loop, correctly, with backpressure. Adding threads invites GTK-thread-safety bugs (GTK widgets are main-thread-only) and buys nothing.
**Do this instead:** Let `Vte.Terminal` own the PTY; connect signals. Use threads for *nothing* terminal-related; use `Gio.Subprocess` (not threads) even for control-plane shell-outs.

### Anti-Pattern 2: Polling `get_text()` on a timer to detect agent state
**What people do:** Every 500 ms, scrape the whole terminal buffer and regex for "waiting."
**Why it's wrong:** CPU waste at scale, fragile to prompt themes/locales, and unnecessary because the agent already signals via BEL/OSC.
**Do this instead:** Event-first (Pattern 2). Reserve a *debounced* scrape only for agents that emit no signals, and disambiguate `contents-changed` with cursor-position tracking.

### Anti-Pattern 3: Relaying a self-created PTY through `flatpak-spawn`
**What people do:** Create their own PTY, run `flatpak-spawn --host` as a relay, and try to forward SIGWINCH/job-control manually (hitting flatpak issues #4827/#3697).
**Why it's wrong:** That path has unresolved TTY/job-control bugs.
**Do this instead:** Let VTE create the PTY and put `flatpak-spawn --host zsh` as the leaf command. Resize and Ctrl+C are handled at the VTE↔PTY/line-discipline layer, not across the portal. (Still: add a Degrau-1 acceptance test for resize + Ctrl+C end to end.)

### Anti-Pattern 4: Business logic in widgets / shelling out from the UI layer
**What people do:** Call `git worktree add` directly from a button handler and mutate widgets from the result.
**Why it's wrong:** Destroys the model boundary the swarm layer needs; makes persistence and testing impossible.
**Do this instead:** Button → intent → SessionStore command → Service → model mutation → widgets observe. One direction.

### Anti-Pattern 5: Building swarm scaffolding in v1
**What people do:** Add a coordinator/mailbox/MCP "because we'll need it."
**Why it's wrong:** Pays the swarm tax up front, against the explicit milestone goal.
**Do this instead:** Just keep the model boundary clean and leave the `swarm/` directory empty. The seams below are *free* if Patterns 1–4 are followed.

---

## Integration Points

### External (host) services — all via HostRunner / `flatpak-spawn --host`

| Service | Integration | Gotchas |
|---------|-------------|---------|
| `git` (worktree) | async `Gio.Subprocess` | worktree path must be sibling per `[worktree].location`; branch-exists check before add. |
| `gh` (read-only) | async, throttled poll | network latency → never on UI thread; cache PR status. |
| `docker compose` | async; `-p <project>` + `-f base -f override` | port collisions → probe before up; `down -v` on conclude; `compose ls` for re-discovery. |
| `zsh` + agent | **inside VTE PTY** (not Gio.Subprocess) | this is the data plane; OSC 133 shell-integration (vte.sh) gives prompt boundaries for status. |
| flatpak portal | `--talk-name=org.freedesktop.Flatpak`, `--filesystem=home` | already in manifest; native builds bypass via HostRunner no-op. |

### Internal boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Presentation ↔ Domain | GObject property notify (observe) + intent method calls | one-directional data; widgets never mutate services |
| Domain ↔ Services | direct async method calls + callbacks | services are stateless; model holds state |
| Services ↔ Host | HostRunner only | the single sandbox seam |
| Domain ↔ **Swarm (Phase 2)** | reads/writes `SessionStore` + a shared-state file | the attach point — see below |

---

## The Swarm Seams (keep Phase-2 cheap, pay nothing in v1)

The swarm ladder (shared context file → board → coordinator → MCP) attaches at exactly two places, **both already required by v1 for other reasons**:

1. **`SessionStore` as a serializable, observable model.** v1 needs this for persistence/re-attach anyway. Phase 2's shared-state file and board are *additional* serialized GObjects in the same store, observed by the same sidebar. No new plumbing.
2. **`AgentSpec` = configurable command.** v1 needs this for agent-swap anyway. The Coordinator is just another `AgentSpec` (a `claude` with a different prompt + tools) spawned into a pane. Builders are ordinary agents whose command points at a task file. **No special-casing in the process model.**

Concretely, leave these (free) seams in v1:
- **Model is GTK-free and serializable** → swarm reads/writes it directly.
- **A `~/.local/share/arduis/<repo>/` data dir exists** (for sessions.json) → the shared board file lands beside it.
- **Spawning an agent is "run a command in a pane"** → spawning a Coordinator or an MCP server is the same call.
- **Status is event-derived per agent** → a Reviewer/Coordinator can read the same `Worktree.status` values to sequence work.

What v1 must NOT do (the swarm tax to avoid): no mailbox abstraction, no role enums, no MCP server, no inter-agent messaging bus. File ownership/exclusivity (the BridgeMind trick) is a *Phase-2* concern enforced by the coordinator's prompt + a lock file, not by v1 architecture.

---

## Build Order Implications (aligned to the degraus / vertical slices)

The architecture is built outside-in along the existing degraus; each degrau is a runnable vertical slice and each *introduces exactly one new layer/module*, so the boundaries emerge incrementally rather than up front.

| Degrau | New architectural piece | Boundary established |
|--------|------------------------|----------------------|
| **1** Terminal in a window | `PaneWidget` + `HostRunner` seam | **Acceptance test: resize (SIGWINCH) + Ctrl+C work through flatpak-spawn.** Establishes the sandbox seam early — highest technical risk, retire it first. |
| **2** New worktree → core loop | `SessionStore`, `Worktree` model, `WorktreeService` | Presentation→Domain→Service direction locked in. The model boundary (the swarm seam) is born here. |
| **3** Many worktrees + sidebar | Sidebar bound to `Gio.ListStore`; pane grid | Reactive observe pattern; virtualization hook (even if not yet needed). |
| **4** Status: who's waiting | `status/agent_state.py`; VTE `bell`/OSC/termprops listeners | Event-first detection. **Build the event path before any scraping.** |
| **5** Agent swap + tmux keys | `AgentSpec`, `keybinds.py`, `theme.py` | "Agent = command" abstraction finalized — second swarm seam. Shell-is-durable-child model proven. |
| **6** Setup via `.arduis.toml` | `ConfigService` + defaults | Config layer; setup-runner in WorktreeService. |
| **7** Isolated containers (opt-in) | `ComposeService`, `ContainerStack` model, badges | Override generation + port offset + project-name; teardown discipline. |
| **8** Review + cleanup | `GitInfoService`; conclude action (worktree remove + `down -v`) | Read-only git/gh; guaranteed teardown closes the resource loop. |
| **9** Packaging | (no new layer) — flatpak/AUR/.deb; HostRunner no-op for native | Proves the single-seam design across distribution channels. |
| **(RAM mgmt)** woven through | `ResourceMonitor`; hibernate/wake on Worktree | Hooks added at 2–3 (model fields), enforcement matures 7–8. Not a separate degrau — first-class field on the model from Degrau 2. |

**Critical ordering note:** Degrau 1 must include the flatpak-spawn resize/Ctrl+C acceptance test. It is the one place the sandbox could invalidate the whole approach, and it's cheapest to discover with one terminal. Everything else is incremental and low-risk given the event-driven model.

---

## Sources

- [Vte.Terminal `spawn_with_fds_async` / `watch_child` (VTE GTK4 docs)](https://gnome.pages.gitlab.gnome.org/vte/gtk4/method.Terminal.spawn_with_fds_async.html) — HIGH: VTE watches the child PID and emits `child-exited` with exit status.
- [Vte 3.91 GTK4 namespace index (termprops since 0.78)](https://gnome.pages.gitlab.gnome.org/vte/gtk4/index.html) — MEDIUM: confirms termprops family exists in pinned 0.84; exact symbol names not enumerated here.
- [GLib `child_watch_add` (manage many subprocesses without threads)](https://docs.gtk.org/glib/func.child_watch_add.html) — HIGH.
- [GNOME/VTE issue #8 — detecting new output (`contents-changed` ambiguity)](https://gitlab.gnome.org/GNOME/vte/-/issues/8) — HIGH: confirms scrape-path caveats and cursor-tracking workaround.
- [flatpak issue #4827 — TTY job control / SIGWINCH forwarding](https://github.com/flatpak/flatpak/issues/4827) — MEDIUM: the relay pitfall avoided by letting VTE own the PTY.
- [flatpak issue #3697 — `flatpak-spawn --host` and `tcsetpgrp`](https://github.com/flatpak/flatpak/issues/3697) — MEDIUM.
- [flatpak-xdg-utils PR #10 — exit-code propagation fix](https://github.com/flatpak/flatpak-xdg-utils/pull/10) / [Will Thompson, "When is an exit code not an exit code?"](https://blogs.gnome.org/wjjt/2018/06/08/when-is-an-exit-code-not-an-exit-code/) — HIGH: exit propagation is fixed in modern flatpak.
- [Claude Code issue #36850 — terminal BEL when waiting for tool approval](https://github.com/anthropics/claude-code/issues/36850) + [Claude Code terminal config docs](https://code.claude.com/docs/en/terminal-config) — HIGH: Claude emits BEL/OSC 9/OSC 777 on idle/permission prompts → the event-first status signal.
- [OSC 133 shell integration (semantic prompt)](https://contour-terminal.org/vt-extensions/osc-133-shell-integration/) — HIGH: prompt-boundary marking for "back at the shell" detection.
- [Running multiple instances of one Docker Compose app (`--project-name`)](https://www.essamamdani.com/blog/running-multiple-instances-of-a-single-docker-compose-application) + [Docker Compose override files](https://oneuptime.com/blog/post/2026-01-25-docker-compose-override-files/view) — HIGH: project-name isolation + override merge is the documented mechanism.

---
*Architecture research for: multi-agent VTE/GTK4 worktree orchestrator in a Flatpak sandbox*
*Researched: 2026-06-08*
