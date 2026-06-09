---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: Phase 1 complete & verified — Phase 2 not started
last_updated: "2026-06-09T11:40:34.730Z"
last_activity: 2026-06-09
progress:
  total_phases: 9
  completed_phases: 1
  total_plans: 2
  completed_plans: 2
  percent: 100
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Tirar a ideia "quero começar uma branch nova" e ter um agente de IA rodando numa worktree isolada em segundos — gerenciando N agentes em paralelo e sempre sabendo qual deles te espera.
**Current focus:** Phase 2 — Core Loop (new worktree → env → agent). Phase 1 (Terminal) complete & verified.

## Current Position

Phase: 2
Plan: Not started
Status: Phase 1 complete & verified (5/5) — ready to discuss/plan Phase 2
Last activity: 2026-06-09

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 2
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 2 | - | - |

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

Last session: 2026-06-09T01:11:50.574Z
Stopped at: Phase 1 complete & verified (5/5 must-haves; manual acceptance approved 2026-06-09). Next: discuss/plan Phase 2.
Resume with: /gsd-discuss-phase 2  (or /gsd-plan-phase 2)
