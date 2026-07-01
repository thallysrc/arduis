---
phase: 08-review-cleanup
plan: 06
subsystem: review-cleanup
tags: [human-uat, checkpoint, risk-acceptance, review-01, review-02, review-03, git-01]
requires:
  - "08-01..08-05 (diff read-only, PR/branch status, conclude gate, headless smoke): all logic proven under sandbox"
  - "08-HUMAN-UAT.md checklist produced (this plan's Task 1)"
provides:
  - "Phase 8 human-verify gate CLOSED via explicit user risk acceptance (2026-07-01)"
  - "08-HUMAN-UAT.md status: accepted — 5 live items skipped, to be confirmed opportunistically in real use"
affects:
  - "v1 milestone completion — Phase 8 no longer blocks lifecycle"
tech-stack:
  added: []
  patterns:
    - "Risk-accepted closure of an irreducibly-manual gate, mirroring Phase 9's PO acceptance (09-HUMAN-UAT.md): everything a command CAN verify ran green first (448 tests, real-git conclude smoke, dirty-refusal, no --force), the display-only half is accepted as a known open risk"
key-files:
  created:
    - .planning/phases/08-review-cleanup/08-06-SUMMARY.md
  modified:
    - .planning/phases/08-review-cleanup/08-HUMAN-UAT.md
decisions:
  - "User (PO) declined to run the live UAT ('não quero testar, modo yolo') — explicit risk acceptance on 2026-07-01; the 5 live items (color diff render, real gh pr create --web, subline with a real PR, clean conclude on disk, dirty refusal live) move from pending to skipped/risk-accepted"
  - "Reopen as gap closure if any live item fails in real use — same reopen contract as Phase 9 hardware UAT"
metrics:
  duration: "checkpoint (started 2026-06-15, closed 2026-07-01)"
  tasks: 2 of 2 (Task 1: checklist produced; Task 2: human gate closed by risk acceptance)
  files: 2
  completed: 2026-07-01
---

# Phase 8 Plan 06: Human-Acceptance Checkpoint — Closed by User Risk Acceptance

**The live human-acceptance checklist (08-HUMAN-UAT.md) was produced and the checkpoint closed on 2026-07-01 by explicit user risk acceptance without running the live items — all load-bearing logic and destructive safety (teardown order, dirty-tree refusal, no `--force`, D-10) are proven headless against real git with the full suite green (448 passed), and the 5 display/GitHub-dependent confirmations are recorded as skipped/risk-accepted, to be confirmed opportunistically in real use.**

## What was verified automatically (before acceptance)

- Full pytest suite: 448 passed (2026-07-01)
- Conclude order + dirty-refusal + zero `remove --force` argv: `tests/test_window_conclude.py`
- Real-git conclude smoke (clean task removed, source repos + branches survive): `tests/test_review_cleanup_smoke.py`
- Read-only diff mechanism: leaf VTE with `set_input_enabled(False)` + `git --no-pager diff`

## What was risk-accepted (skipped live)

1. Color + read-only diff on a real display (REVIEW-01)
2. Real PR subline + throttled refresh + gh degrade (GIT-01/REVIEW-02)
3. `gh pr create --web` opens the browser (REVIEW-02)
4. Clean conclude on a real task, confirmed on disk (REVIEW-03)
5. Dirty conclude refusal, live (REVIEW-03 safety)

Reopen contract: any live failure reopens as a Phase 8 gap-closure plan.
