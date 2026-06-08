# Feature Research

**Domain:** Desktop orchestrator for parallel AI coding agents (Claude Code) in git worktrees, terminal-centric, Linux/GNOME
**Researched:** 2026-06-08
**Confidence:** HIGH (grounded in 10+ named competitor tools verified via web; one critical mechanism — status detection — verified against workmux source/docs and Claude Code hook issues)

---

## Competitive Landscape (what these tools actually are)

Two architectural camps emerged, and arduis straddles them deliberately:

| Tool | Form | Worktree | Terminal model | Status detection | Container/sandbox | Diff/PR | Notes |
|------|------|----------|----------------|------------------|-------------------|---------|-------|
| **BridgeSpace / BridgeSwarm** | Mac/Win/Linux desktop | yes | multi-pane terminals (up to 10) | UI badges, real-time status | — | inline + Kanban | The visual reference. Up to 16 agents, swarm w/ roles+mailbox+file-ownership (this is arduis's Phase 2) |
| **Conductor** | Mac desktop | yes (1 worktree/workspace) | embedded terminal | "see at a glance what they're working on" | — | inline diff + comments, agent iterates | Closest UX analog. Mac-only (the gap arduis fills) |
| **Crystal → Nimbalyst** | Electron desktop | yes | embedded | session list w/ attention info | no (uses local worktrees) | diff view | Crystal deprecated Feb 2026; successor adds visual editing |
| **Claude Squad** | TUI (Go) | yes | tmux sessions | states: running/ready/paused (mechanism undocumented) | no | diff/preview tab, checkout, commit+push | autoyes/yolo background mode |
| **workmux** | CLI + TUI (Go) | yes | tmux windows | **Claude Code hook plugin → state files → emoji in window name** (🤖/💬/✅); 10s no-output = interrupted | symlink/copy .env per worktree | merge cmd auto-cleans worktree+window+branch | `post_create` hooks, pane layouts. Best teardown model |
| **agent-of-empires** | TUI + Web | yes | tmux sessions | per-session | optional Docker sandbox | — | mobile web access; session persistence on SSH drop |
| **agent-deck** | TUI | yes | terminal sessions | "Conductor" sessions watch & escalate | — | — | MCP toggling, conversation forking |
| **Sculptor (Imbue)** | Desktop | no (containers instead) | — | history per agent | **Docker container per agent** (devcontainer spec) | Pairing Mode syncs to local | Containers always-on, not opt-in (RAM-heavy) |
| **Vibe Kanban** | Web/desktop | yes | — | Kanban "ready to review" | yes | syntax-highlighted inline diff approve/edit/reject | sunsetting → community OSS |

**The arduis position:** Conductor's UX (embedded terminals, attention surfacing, per-workspace env) + workmux's mechanism rigor (hook-driven status, clean teardown) + tmux-native keybindings, on Linux/GNOME, opt-in containers, RAM-first. Swarm (BridgeSwarm-style) is explicitly Phase 2.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Missing any of these makes the product feel broken relative to every competitor above.

| Feature | Why Expected | Complexity | Notes / arduis mapping |
|---------|--------------|------------|------------------------|
| Real embedded terminal running host shell | The whole category is "terminals + orchestration"; Conductor/BridgeSpace/Crystal all embed | MEDIUM | VTE `Vte.Terminal` spawning host `zsh`. **Degrau 1.** Foundation for everything. |
| Core loop: new worktree → env → agent running, in seconds | Every tool's headline. Conductor "spin up a workspace, give a task"; workmux automates it | MEDIUM | `git worktree add` → spawn VTE in dir → auto-run `claude`. **Degrau 2.** This IS the product. |
| N agents in parallel, isolated per worktree | Defining feature of the category — zero-conflict parallel edits | LOW (given core loop) | One VTE+worktree per "session". **Degrau 3.** |
| Sidebar/list of sessions with per-session status | Claude Squad list, Crystal session list, Conductor glance-view, workmux dashboard | MEDIUM | Sidebar w/ status dot per worktree. **Degrau 3–4.** |
| "Agent needs attention" surfacing | First-class in BridgeSpace badges, Conductor, workmux emoji, agent-deck escalation, Crystal "needs input" | MEDIUM-HIGH | See dedicated section below. **Degrau 4.** First-class requirement. |
| Session persistence / re-attach | Claude Squad & agent-of-empires keep agents alive when TUI closes / SSH drops | MEDIUM | Agents must survive window close. Background process model, re-attach VTE. |
| Diff / review of changes | Conductor inline, Claude Squad diff tab, Vibe Kanban approve/reject, Crystal diff | LOW-MEDIUM (read-only) | Read-only via `git diff`. arduis scope = *read* git/gh only. **Degrau 8.** |
| Worktree teardown / cleanup | workmux merge auto-cleans; without it you accumulate stale worktrees | MEDIUM | "Conclude worktree" → remove worktree (+ container teardown). **Degrau 8.** workmux is the model. |
| Agent = configurable command | Claude Squad/workmux/aoe all agent-agnostic via launch commands | LOW | `[agents]` in `.arduis.toml`; default `claude`; Ctrl+C → shell → other agent. **Degrau 5.** |
| Per-worktree setup commands on create | workmux `post_create`, copy/symlink `.env`; without it the worktree isn't "ready to work" | LOW-MEDIUM | `setup = [...]` in `.arduis.toml`. **Degrau 6.** |
| Read git/gh info (branch, PR status) | Users expect to see what branch/PR a session maps to | LOW | Shell-out, read-only. Throughout. |

### Differentiators (Competitive Advantage)

Where arduis competes. Aligned with Core Value ("agente rodando em segundos + sempre saber qual te espera") and the unfilled Linux gap.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Linux/GNOME native, team-installable (Flatpak)** | The entire premium tier (Conductor, BridgeSpace-quality desktop UX) is Mac-first. No polished GNOME option exists | MEDIUM (packaging) | One Flatpak build covers Ubuntu+Arch; VTE bundled. **Degrau 9.** This is *the* reason the project exists. |
| **First-class RAM management** (hibernate, limits, per-worktree visibility) | No competitor exposes this. Sculptor's always-on containers are the cautionary tale (RAM-heavy). Real cost = agents (Node 100–300MB) + containers (0.5–2GB) | HIGH | Hibernate = kill agent + stop containers, keep dir; configurable active limit; RAM badge per worktree; teardown guaranteed. **Distinct, hard, high-value.** |
| **tmux-native keybindings + themes** | The target user lives in tmux; competitors impose their own bindings. `C-Space`, `C-h/j/k/l`, split `-`/`=`, zoom `z` | MEDIUM | Configurable; Dracula default, swappable themes. **Degrau 5.** Direct muscle-memory respect. |
| **Opt-in isolated containers per worktree** w/ auto port offset, compose-base from `main` | Sculptor forces containers (always); worktree tools (workmux) leave runtime un-isolated. arduis: off by default, isolate when you need it | HIGH | `COMPOSE_PROJECT_NAME` unique + generated `docker-compose.override.yml` w/ port offset; UI badge `db :5433`. **Degrau 7.** Pattern verified (worktree-compose, `20000+port+index`). |
| **Hook-driven attention detection** (vs fragile scraping) | workmux proves hooks beat output-parsing; doing it cleanly = reliable "te espera" | MEDIUM | See dedicated section. The differentiator is *reliability* of the status dot. |
| **Visual status grid / command-blocks (v2 mockup)** | BridgeSpace-class visual richness on Linux | MEDIUM-HIGH | Mockups approved; defer polish past MVP. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative (arduis approach) |
|---------|---------------|-----------------|-------------------------------|
| Always-on container per worktree (Sculptor model) | "Perfect isolation, no dep reinstall" | 0.5–2GB RAM each → kills the lightweight promise; violates RAM-first constraint | Opt-in isolated containers, shared default, hibernate |
| Coordinated swarm in v1 (roles/mailbox/MCP, BridgeSwarm) | Looks impressive, "AI team" | Monolithic build kills momentum (Accelerate); most value is in simple parallelism | Explicit Phase 2, degrau-by-degrau, can stop anywhere |
| Build a terminal emulator from scratch | "Full control over rendering" | Massive scope; Wayland complexity; solo-maintainable killer | Embed VTE (GNOME Terminal engine) |
| Embedded code editor | "One app for everything" | Competes with neovim user already has; huge surface | Out of scope; user edits in neovim |
| Credential / Jira / issue management | "Integrate the whole workflow" | Security surface, scope explosion, not the pain | Read-only git/gh; user configures by hand |
| autoyes / yolo auto-accept by default (Claude Squad has it) | "Fully autonomous" | Dangerous defaults for a team tool; runs commands unattended | Not a v1 priority; if added, opt-in per session, never default |
| Inline diff *comments that the agent reads* (Conductor) | "Review like a PR" | arduis is read-only on git/gh; writing comments back = deep agent integration | Read-only diff; iterate by typing in the terminal directly |
| PR creation/management UI in-app | "Don't leave the app" | Credential mgmt + GitHub API surface, out of scope | Shell-out `gh pr create`; arduis only *reads* PR status |
| Mobile / web remote access (agent-of-empires) | "Check agents from phone" | Network/auth/security surface; not the desktop-GNOME thesis | Out of scope |
| Snap as primary distribution | "Ubuntu default store" | Confinement breaks a tool that drives docker/git/ssh | Flatpak primary, AUR + .deb native |

---

## "Agent Needs Your Attention" — Detection & Notification (first-class)

This is a Core Value pillar ("sempre sabendo qual deles te espera"), so it gets its own analysis. **This is the single most important mechanism decision in the project.**

### How competitors do it

- **workmux (verified):** Installs a **Claude Code hook plugin** (`claude plugin marketplace add raine/workmux`). Hooks write **state files** to `~/.local/state/workmux/agents/`; a watcher renders emoji (🤖 working / 💬 waiting / ✅ done) into the tmux window name. Fallback heuristic: an agent in "working" with **no pane output for 10s → flagged interrupted**.
- **Claude Code native hooks (verified via issues):** `Notification` hook fires when Claude wants the user; `Stop` hook fires when a turn finishes. *Known caveat:* current `idle`/`Notification` events don't cleanly distinguish "genuinely waiting for input" from "completed/idle with background tasks" — multiple open issues (#11665, #12048, #13024, #36885, cmux #2576) request a dedicated `waiting_for_user_action` event. So hooks are good but imperfect at the edges.
- **Conductor / BridgeSpace / Crystal:** Surface as **UI badges / colored status in the session list** ("see at a glance", "whether the agent needs attention"). Mechanism undisclosed but clearly event/state driven, not pure scraping.
- **agent-deck:** Goes further — "Conductor" sessions *watch* others and **escalate to the human** when they can't auto-respond.

### Recommended arduis approach (HIGH confidence on direction)

1. **Primary: Claude Code hooks → state file → UI.** Ship a small hook config (or document one) so `Notification`/`Stop`/`SessionStart` write a per-worktree state file. arduis watches and updates the sidebar dot + pane header. This is exactly workmux's proven model and is far more reliable than scraping VTE bytes.
2. **Fallback for non-hookable agents (codex/aider/shell):** VTE output heuristics — detect prompt patterns + "no output for N seconds while marked running" (workmux's 10s rule). The ROADMAP Degrau 4 phrasing ("lendo a saída do VTE") should be **upgraded**: hooks first, scraping as fallback.
3. **Status taxonomy:** `running` / `waiting-for-input` (the orange dot) / `idle` / `ready/done` — matches ROADMAP Degrau 4 and workmux's 3-state + done.
4. **Notification surface:** at minimum sidebar dot + pane header badge (Degrau 4). Desktop notification (libnotify/GNOME) and optional sound are cheap add-ons — defer to v1.x. The whole point is "pull attention back only when needed."

**Complexity:** MEDIUM (hooks + watcher + UI binding). The fallback scraper is the fiddly part — keep it simple and treat hooks as the source of truth.

---

## RAM / Resource Management & Visibility (first-class)

No competitor treats this as first-class — it's a genuine differentiator and a hard constraint (lightweight + team machines).

| Capability | Why | Complexity | Mapping |
|------------|-----|------------|---------|
| Hibernate worktree (kill agent + stop containers, keep dir) | Reclaim 0.1–2GB without losing work | MEDIUM-HIGH | Needs clean agent-kill + `docker compose stop` + state restore |
| Configurable limit of active agents/containers | Prevent runaway RAM on a laptop | LOW-MEDIUM | Counter + gate on new-session |
| Per-worktree RAM visibility in UI | "Which session is eating my RAM" | MEDIUM | Read process RSS + container stats; badge per worktree |
| Suspend idle sessions | Auto-reclaim | MEDIUM | Tie to idle status from attention detection |
| Guaranteed teardown on close/remove | No orphan containers/worktrees | MEDIUM | workmux's merge-cleanup is the model; must be atomic-ish |
| Shared-by-default containers | Don't pay RAM unless you opt in | LOW (it's the default = do nothing) | Default mode `off` |

**Dependency:** RAM visibility & hibernate depend on (a) container integration (Degrau 7) for the container half, and (b) attention/idle detection (Degrau 4) for auto-suspend. The agent-process half (kill/measure agent RAM) only needs the core loop.

---

## Feature Dependencies

```
Embedded VTE terminal (D1)
   └──requires──> nothing (foundation)

Core loop: new worktree → env → agent (D2)
   └──requires──> Embedded VTE (D1)

N parallel worktrees + sidebar (D3)
   └──requires──> Core loop (D2)

Attention detection / status dot (D4)
   └──requires──> sidebar (D3)
   └──enhanced-by──> Claude Code hooks (state files)
   └──fallback──> VTE output scraping

Agent switching + tmux keybindings + themes (D5)
   └──requires──> Embedded VTE (D1)

Per-worktree setup commands (D6)
   └──requires──> Core loop (D2) + .arduis.toml parsing

Isolated containers opt-in + port offset (D7)
   └──requires──> Core loop (D2) + .arduis.toml + docker compose shell-out

Review + cleanup (diff / gh PR / teardown) (D8)
   └──requires──> Core loop (D2)
   └──requires──> container teardown <──depends── Containers (D7)

RAM management (hibernate / limits / visibility)
   └──requires──> Core loop (D2)         [agent half]
   └──requires──> Containers (D7)         [container half]
   └──enhanced-by──> Attention/idle (D4)  [auto-suspend]

Packaging Flatpak/AUR/.deb (D9)
   └──requires──> everything shippable (cross-cutting; VTE bundling is the hard part)

Swarm (Phase 2) ──requires──> all of v1 (parallelism + sidebar + status)
```

### Dependency Notes

- **Attention detection enhanced by hooks, fallback to scraping:** hooks need an agent that supports them (Claude Code does); scraping covers arbitrary agents. Build hooks-first so the dot is reliable for the default agent.
- **Review/cleanup depends on containers for full teardown:** "conclude worktree" can ship before D7 (just remove worktree), then gain container teardown after D7. Don't block D8 on D7.
- **RAM management spans two phases:** the agent-process half is shippable early (after D2); the container half lands with/after D7. Sequence accordingly — don't treat RAM as one monolithic feature.
- **Packaging (D9) conflicts with sandbox needs:** Flatpak confinement vs. a tool driving docker/git/ssh — the manifest must grant the right holes (host talk, docker socket). This is a known integration risk, flag for deeper research at D9.

---

## MVP Definition

### Launch With (v1 — Simple Parallelism)

Maps 1:1 to ROADMAP Degraus 1–9. This is the validated MVP scope.

- [ ] Embedded VTE terminal running host zsh (D1) — foundation
- [ ] Core loop: new worktree → env → `claude` running (D2) — *this is the product*
- [ ] N parallel worktrees + sidebar with status (D3) — parallelism made visible
- [ ] Attention detection: running/waiting/idle/ready dot, hooks-first (D4) — Core Value pillar
- [ ] Agent = configurable command + tmux keybindings + Dracula/themes (D5) — muscle-memory
- [ ] Per-worktree setup commands from `.arduis.toml` (D6) — "ready to work"
- [ ] Opt-in isolated containers w/ auto port offset + UI badges (D7) — the thing user misses most
- [ ] Review (read-only diff) + conclude/cleanup w/ teardown (D8) — close the loop
- [ ] Flatpak (primary) + AUR + .deb packaging (D9) — team-installable
- [ ] RAM management (hibernate, active limit, per-worktree visibility) — first-class; woven across D2/D4/D7, not a single degrau

### Add After Validation (v1.x)

- [ ] Desktop notifications (libnotify) + optional sound — trigger: dot alone proves insufficient when window unfocused
- [ ] Session persistence across full app restart (not just window) — trigger: users lose work on crash/restart
- [ ] Richer scraping fallback for non-Claude agents — trigger: users adopt codex/aider heavily
- [ ] Command-blocks / v2 BridgeSpace-style visual polish — trigger: core validated, time for UX depth
- [ ] Free pane layout (split/drag like tmux) vs fixed grid — trigger: fixed grid feels constraining

### Future Consideration (v2+)

- [ ] **Swarm: shared context file → manual board → agents read board → Coordinator writes board → file ownership → MCP → auto-reviewer** (Phase 2 track, degrau-by-degrau, stoppable anywhere) — defer: would kill v1 momentum; only build if simple parallelism validates and user wants it
- [ ] Auto-respond / escalation (agent-deck "Conductor") — defer: needs swarm plumbing
- [ ] Mini-Kanban of cards — defer: part of swarm/visual v2

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Core loop (worktree→env→agent) | HIGH | MEDIUM | P1 |
| Embedded VTE terminal | HIGH | MEDIUM | P1 |
| Parallel worktrees + sidebar | HIGH | LOW-MEDIUM | P1 |
| Attention detection (hooks-first) | HIGH | MEDIUM | P1 |
| tmux keybindings + themes | HIGH | MEDIUM | P1 |
| Agent = configurable command | MEDIUM | LOW | P1 |
| Per-worktree setup commands | MEDIUM | LOW-MEDIUM | P1 |
| RAM mgmt (hibernate/limits/visibility) | HIGH | HIGH | P1 (woven) |
| Opt-in isolated containers + ports | HIGH | HIGH | P1 |
| Review (read-only diff) + cleanup | HIGH | MEDIUM | P1 |
| Flatpak/AUR/.deb packaging | HIGH | MEDIUM-HIGH | P1 |
| Desktop notification + sound | MEDIUM | LOW | P2 |
| Full session persistence (restart) | MEDIUM | MEDIUM | P2 |
| Scraping fallback (non-Claude agents) | LOW-MEDIUM | MEDIUM | P2 |
| Free/draggable pane layout | MEDIUM | MEDIUM | P2 |
| Command-blocks / v2 visual polish | MEDIUM | MEDIUM-HIGH | P3 |
| Swarm (roles/mailbox/MCP) | MEDIUM | HIGH | P3 |
| Auto-respond / escalation | MEDIUM | HIGH | P3 |
| Mini-Kanban | LOW | MEDIUM | P3 |

---

## Competitor Feature Analysis (arduis's approach per feature)

| Feature | Conductor (Mac) | Claude Squad (TUI) | workmux (CLI/tmux) | Sculptor (containers) | arduis approach |
|---------|-----------------|--------------------|--------------------|-----------------------|-----------------|
| Worktree core loop | yes, 1/workspace | yes | yes, automated | no (containers) | yes — VTE in worktree, auto-run agent (D2) |
| Embedded real terminal | yes | tmux (TUI) | tmux | no | yes — VTE host shell (D1) |
| Attention surfacing | UI badges | states (opaque) | **hook→state→emoji** | history | **hooks-first** + scraping fallback, sidebar dot (D4) |
| Diff/review | inline + agent reads comments | diff tab | dashboard diff | Pairing Mode | **read-only** `git diff` (D8) |
| PR | — | commit+push | merge cmd | — | `gh pr create` shell-out, read PR status only (D8) |
| Cleanup/teardown | archive | kill session | **merge auto-cleans all** | container destroy | conclude → remove worktree + container teardown (D8) |
| Containers/env | — | — | .env copy/symlink | **always-on Docker** | **opt-in isolated**, port offset, shared default (D7) |
| Session persistence | desktop | tmux survives close | tmux survives | container | survives window close (P1); full-restart deferred (P2) |
| Keybindings | app defaults | TUI keys | tmux-native | app | **tmux-native configurable** (D5) |
| RAM management | — | — | — | container start optimization | **first-class**: hibernate/limits/visibility (P1) |
| Platform | Mac | cross (TUI) | cross (tmux) | desktop | **Linux/GNOME native**, Flatpak (D9) |
| Swarm | — | — | — | — | **Phase 2 opt-in** (file ownership like BridgeSwarm) |

---

## Sources

- Conductor — https://www.conductor.build/ and https://julianastrada.com/blog/conductor-parallel-agents (MEDIUM — marketing site light on detail)
- Claude Squad — https://github.com/smtg-ai/claude-squad (HIGH for feature list; status mechanism undocumented = LOW)
- workmux — https://github.com/raine/workmux and https://raine.dev/blog/introduction-to-workmux/ (HIGH — status/teardown mechanism documented)
- Crystal/Nimbalyst — https://github.com/stravu/crystal , https://nimbalyst.com/crystal/ (HIGH — Crystal deprecated Feb 2026 confirmed)
- Vibe Kanban — https://vibekanban.com/ (HIGH for features; project sunsetting → community OSS)
- Sculptor (Imbue) — https://github.com/imbue-ai/sculptor , https://imbue.com/blog/containers (HIGH — container-per-agent model)
- BridgeSpace/BridgeSwarm — https://www.bridgemind.ai/products/bridgespace , https://www.bridgemind.ai/bridgeswarm (HIGH — roles/mailbox/file-ownership swarm model)
- agent-deck — https://github.com/asheshgoplani/agent-deck (MEDIUM — escalation/Conductor model)
- agent-of-empires — https://github.com/njbrake/agent-of-empires (MEDIUM — session persistence, Docker sandbox)
- Claude Code hooks for attention — https://github.com/anthropics/claude-code/issues/11665 , /issues/12048 , /issues/13024 , /issues/36885 ; cmux #2576 (HIGH — confirms Notification/Stop hooks + the waiting-vs-idle ambiguity caveat)
- Claude Code notification/sound setup — https://alexop.dev/posts/claude-code-notification-hooks/ , https://www.scalebloom.com/blog/claude-code-notification-sounds/ (MEDIUM)
- Container/port-offset pattern — https://www.worktree-compose.com/ , https://www.penligent.ai/hackinglabs/git-worktrees-need-runtime-isolation-for-parallel-ai-agent-development/ (MEDIUM-HIGH — confirms `base+index*offset` pattern + .git pointer caveat)

---
*Feature research for: parallel AI coding agent orchestrator (Linux/GNOME, terminal-centric)*
*Researched: 2026-06-08*
