---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 9 automated gate green (5/5 plans, .deb builds+lints); awaiting hardware UAT on real Ubuntu+Arch (DIST-04)
last_updated: "2026-06-15T23:44:05.696Z"
last_activity: 2026-06-15
progress:
  total_phases: 13
  completed_phases: 12
  total_plans: 52
  completed_plans: 51
  percent: 98
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Tirar a ideia "quero começar uma branch nova" e ter um agente de IA rodando numa worktree isolada em segundos — gerenciando N agentes em paralelo e sempre sabendo qual deles te espera.
**Current focus:** Phase 09 — packaging-aur-deb

## Current Position

Phase: 09
Plan: Not started
Status: Executing Phase 09
Last activity: 2026-06-15

Progress: [██████░░░░] 60%

## Performance Metrics

**Velocity:**

- Total plans completed: 51
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 2 | - | - |
| 02 | 3 | - | - |
| 03 | 5 | - | - |
| 03.1 | 3 | - | - |
| 03.2 | 3 | - | - |
| 4 | 5 | - | - |
| 5 | 4 | - | - |
| 6 | 3 | - | - |
| 03.3 | 3 | - | - |
| 7 | 5 | - | - |
| 8 | 5 | - | - |
| 03.4 | 5 | - | - |
| 09 | 5 | - | - |

**Recent Trend:**

- Last 5 plans: -
- Trend: -

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Roadmap-shaping decisions affecting current work:

- Roadmap: 9 vertical "degraus" (Accelerate/DORA) — each phase installable + usable on its own.
- Distribution: **native (`.deb` + AUR), Flatpak out of v1** (2026-06-08) — removes the sandbox; VTE from system repos (Ubuntu 0.76 / Arch 0.84).
- Phase 1: native **direct PTY** (no sandbox); a thin `HostRunner` seam centralizes host execution (no-op natively, Flatpak path stubbed for v2). Ctrl+C/job-control/exit-status acceptance tests still mandatory. App owns the terminal theme palette (Dracula default), not the shell.
- Phase 4: attention detection is HOOKS-FIRST (Claude Code `Notification`/`Stop` → state file), BEL/OSC secondary, scraping fallback deferred to v2 (STATUS-04).
- RAM management is cross-cutting (Phases 2/3/4/7), not a single phase.
- Swarm is out of v1; kept cheap via GTK-free SessionStore (P2) + AgentSpec (P5) seams only.

### Roadmap Evolution

- Phase 03.1 inserted after Phase 3: worktree-as-terminal-workspace (URGENT)
- Phase 03.2 inserted after Phase 3 (2026-06-10): Projects and Cross-Repo Tasks (URGENT) — level-1 pivot: project = multi-repo root folder (meta-repo with root CLAUDE.md/compose/.arduis.toml); task = set of worktrees mirroring the root layout; sidebar = tasks, workspace = the task's terminals. Single-repo project is the degenerate case. DECIDED: single root docker-compose.yml per project (not per repo) — Phase 7 re-anchored to COMPOSE_PROJECT_NAME per task; Phase 4 re-anchored to per-task attention rollup (depends on 03.2 now). Supersedes the "topbar = single repos" reading of docs/MOTIVATION.md.
- Phase 03.4 inserted after Phase 3 (2026-06-15): Topbar = multi-PROJECT switcher (URGENT, corrective) — PO flagged GSD modeled the topbar at the WRONG LEVEL twice (03.2 D-06 name-only, then 03.3 repo-chips). Correct model: topbar lists multiple PROJECTS (each a multi-repo root: Livon-Saude, KarveLabs), switchable + "both alive" (other projects keep terminals/agents/containers running). "Open project" picker + remembered list persisted across launches (kills "one arduis = one launch-dir project"). Member repos move out of the topbar into the New-task dialog. Needs a real GTK-free `Project` model. **Supersedes Phase 03.3 (repo chips) and 03.2 D-06 in full.** Executes BEFORE Phase 9. GAP: .planning/phases/03.3-topbar-repo-chips/03.3-GAP-topbar-multi-project.md.

### Pending Todos

None yet.

### Blockers/Concerns

- **Distribution pivot (2026-06-08):** Flatpak dropped from v1 → native `.deb` (Ubuntu) + AUR (Arch). Kills the entire `flatpak-spawn --host` risk class. VTE comes from the system (Ubuntu 24.04 `gir1.2-vte-3.91` **0.76** in `main`, verified; Arch `vte4` **0.84**); code to the 0.76 API floor. fast_float/simdutf pins no longer relevant (were Flatpak VTE-bundle deps).
- Phase 1: direct native PTY (no sandbox); `HostRunner` is a thin no-op seam with the Flatpak path stubbed for a possible v2 channel. Ctrl+C/job-control/exit-status acceptance tests still mandatory (now native, much lower risk).
- Phase 4 (research flag): Claude Code hook event semantics evolving (`Notification` over-fires; no clean `waiting_for_user_action`); design the watcher to filter event types.
- Phase 7 (research flag): compose isolation edge cases + snap-docker-on-Ubuntu behavior (docker runs on host directly).
- ~~Uncommitted D1 draft / obsolete Flatpak manifest~~ **RESOLVED in Phase 1:** draft refactored into `src/arduis/{main,window}.py` (thin `src/main.py` shim kept, no `flatpak-spawn`); `data/*` committed; `io.github.thallys.Arduis.yml` + `dev.sh` deleted; native `run.sh` added (backups in `/tmp/arduis-untracked-bak/`).
- `CLAUDE.md` tech-stack section rewritten native-first (2026-06-08) — Flatpak/bundling contradiction resolved.

## Session Continuity

Last session: 2026-06-15T23:30:17.674Z
Stopped at: Phase 9 automated gate green (5/5 plans, .deb builds+lints); awaiting hardware UAT on real Ubuntu+Arch (DIST-04)
Resume with: phase verification for Phase 02 (orchestrator owns this next)
