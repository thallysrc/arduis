---
phase: 07-opt-in-isolated-containers
plan: 05
type: execute
status: complete
wave: 4
requirements: [CONT-01, CONT-02, CONT-03, CONT-04, CONT-05]
---

# Plan 07-05 Summary: Phase Acceptance

## Outcome

Acceptance executed autonomously (user delegated, AFK). Task 1 (headless end-to-end smoke) ran for
real and is committed at `tests/test_compose_smoke.py` (a pure pytest — no gi/docker/broadway);
Task 2 (live UAT on a real docker host) auto-resolved by persisting the checklist to
`07-HUMAN-UAT.md`.

## Task 1 — Headless smoke (DONE)

- **Full suite:** `344 passed` (336 pre-plan + 8 compose-smoke). Green.
- The smoke runs the full pipeline (parse base `config` JSON → assign_ports → override_bytes →
  write a REAL override under a sandbox `$HOME`) and asserts the load-bearing facts:

| Check | Result |
|-------|--------|
| override contains `ports: !override` (REPLACE not concatenate — D-01/criterion 2) | PASS |
| offset port `9080:80` present, base `8080:80` ABSENT, multi-port + db remapped | PASS |
| empty port-map still writes a valid `services:` override (up_argv -f always resolves) | PASS |
| up/down/config/ls argv shapes exact (base+override under task_dir; config = base-only) | PASS |
| COMPOSE_PROJECT_NAME sanitized (`arduis-…`) | PASS |
| probe bumps the WHOLE task on collision (base+2000) | PASS |
| probe cap raises PortAssignmentError | PASS |
| ContainerState round-trips on disk under sandbox $HOME | PASS |
| missing state = no-op default | PASS |

## Task 2 — Live acceptance (persisted as UAT)

`07-HUMAN-UAT.md` (status: partial), 5 criteria. All HEADLESS-testable logic is proven; what
remains is host-only: a real `docker compose up` bringing an isolated stack with offset ports +
badges, real teardown/reconcile. Docker 29.3.1 is on the host, so the user can run it for real.

## Notes

- The `ports: !override` tag (not a plain port list) is the central correctness point the research
  caught live — a plain override CONCATENATES and re-binds the base port. The smoke proves the tag
  on real disk.
- snap-docker D-09: smoke stages compose files under a sandbox `$HOME`, never `/tmp`.

## Self-Check: PASSED

Suite green (344), compose-smoke 8/8, real ~/.config untouched (sandbox $HOME), smoke file + UAT +
SUMMARY written.
