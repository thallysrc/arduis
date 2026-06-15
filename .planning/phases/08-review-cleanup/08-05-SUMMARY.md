---
phase: 08-review-cleanup
plan: 05
type: execute
status: complete
wave: 4
requirements: [REVIEW-01, REVIEW-02, REVIEW-03, GIT-01]
---

# Plan 08-05 Summary: Headless acceptance smoke

## Outcome

Authored `tests/test_review_cleanup_smoke.py` — a REAL-git pytest (no GTK/broadway needed, runs in
the normal suite) proving the safety facts the conclude depends on. Orchestrator-authored inline
(the Wave-3 executor had timed out; the acceptance was done here to keep momentum).

## Checks (4/4 pass, in the full 406-test suite)

| Check | Result |
|-------|--------|
| CLEAN worktree removed by `git worktree remove` (no --force); source repo + `feat` branch survive (D-10) | PASS |
| DIRTY worktree REFUSES removal without --force (git's own guard); uncommitted work preserved; argv never forces | PASS |
| `parse_porcelain_clean` classifies real `git status --porcelain` (clean→True, dirty→False) | PASS |
| D-10: islink-guarded `os.unlink` removes a symlink but the TARGET file survives | PASS |
| gh degrade: gh absent → `gh_available()` False + `GH_ABSENT_MSG`; exit-4 → `GH_UNAUTH_MSG`; other rc → None | PASS |

This is stronger than a mocked smoke: it runs the actual `review` argv builders against a real git
repo + worktree under a sandbox `$HOME`, so the no-`--force` safety and the D-10 source/branch
survival are proven against real git behavior, not stubs. `gh pr create` is NEVER executed.

## Notes

- Combined with `tests/test_window_conclude.py` (08-04, the order + dirty-refusal state machine) and
  the 3-layer never-force guard, the destructive conclude path is regression-locked at the builder,
  wiring, and real-git levels.
- Real diff-pane rendering, real `gh pr status`/`gh pr create --web`, and the live "Concluir" UX
  remain host-only live UAT (08-HUMAN-UAT.md).

## Self-Check: PASSED
