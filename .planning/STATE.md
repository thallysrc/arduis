---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: planning
stopped_at: Phase 1 context gathered (native pivot)
last_updated: "2026-06-09T01:11:50.583Z"
last_activity: 2026-06-08 — Roadmap created (9 degraus, RAM woven across 2/3/4/7)
progress:
  total_phases: 9
  completed_phases: 0
  total_plans: 0
  completed_plans: 0
  percent: 0
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-06-08)

**Core value:** Tirar a ideia "quero começar uma branch nova" e ter um agente de IA rodando numa worktree isolada em segundos — gerenciando N agentes em paralelo e sempre sabendo qual deles te espera.
**Current focus:** Phase 1 — Terminal + Sandbox Seam

## Current Position

Phase: 1 of 9 (Terminal + Sandbox Seam)
Plan: 0 of TBD in current phase
Status: Ready to plan
Last activity: 2026-06-08 — Roadmap created (9 degraus, RAM woven across 2/3/4/7)

Progress: [░░░░░░░░░░] 0%

## Performance Metrics

**Velocity:**

- Total plans completed: 0
- Average duration: -
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| - | - | - | - |

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
- Uncommitted D1 draft exists (`src/main.py`, `data/*`); the Flatpak manifest (`io.github.thallys.Arduis.yml`) and `dev.sh` are now **obsolete** (need a native run/build script); `main.py` keeps as a base but drops `flatpak-spawn`.
- **Follow-up:** `CLAUDE.md` still carries a large Flatpak/VTE-bundling/`flatpak-spawn` tech-stack section that now contradicts this pivot — needs a cleanup pass.

## Session Continuity

Last session: 2026-06-09T01:11:50.574Z
Stopped at: Phase 1 context gathered (native pivot)
Resume file: .planning/phases/01-terminal/01-CONTEXT.md
