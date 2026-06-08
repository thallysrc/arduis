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
- Phase 1: highest technical risk (`flatpak-spawn --host` Ctrl+C/job-control/exit-status) retired first via mandatory acceptance tests; one `HostRunner` seam centralizes all host execution.
- Phase 4: attention detection is HOOKS-FIRST (Claude Code `Notification`/`Stop` → state file), BEL/OSC secondary, scraping fallback deferred to v2 (STATUS-04).
- RAM management is cross-cutting (Phases 2/3/4/7), not a single phase.
- Swarm is out of v1; kept cheap via GTK-free SessionStore (P2) + AgentSpec (P5) seams only.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 1 (research flag): `flatpak-spawn --host` signal/ctty/exit-status across the sandbox needs a hands-on acceptance-test spike (flatpak#3697, #4827); have explicit-portal-SIGINT fallback ready.
- Phase 1: fast_float pin must be v8.1.0 (the uncommitted draft manifest uses v8.2.8 — drift to correct).
- Phase 4 (research flag): Claude Code hook event semantics evolving (`Notification` over-fires; no clean `waiting_for_user_action`); design the watcher to filter event types.
- Phase 7 (research flag): compose isolation edge cases + snap-docker-on-Ubuntu behavior.
- Phase 9 (research flag): verify Ubuntu 24.04 GTK4-VTE availability for the .deb (may need backport/PPA).
- Uncommitted D1 draft exists (`io.github.thallys.Arduis.yml`, `src/main.py`, `data/*`, `dev.sh`) — treat as a starting point to validate, not as done.

## Session Continuity

Last session: 2026-06-08
Stopped at: ROADMAP.md + STATE.md created; REQUIREMENTS.md traceability updated (33/33 mapped)
Resume file: None
