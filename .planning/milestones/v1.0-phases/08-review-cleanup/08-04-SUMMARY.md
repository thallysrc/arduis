---
phase: 08-review-cleanup
plan: 04
type: execute
status: complete
wave: 3
requirements: [REVIEW-03]
---

# Plan 08-04 Summary: "Concluir task" — safe ordered teardown

## Outcome

The "Concluir task" action with the D-04 safe teardown order is wired and regression-locked.
The executor agent timed out (stream idle) AFTER writing the conclude wiring into window.py but
BEFORE committing or writing the unit test. The orchestrator reviewed the uncommitted wiring
(found it sound — correct order, no `--force`, D-10 honored), committed it, and authored the
regression test.

## What shipped (src/arduis/window.py)

`_on_conclude_action` (row menu `win.conclude`) → DESTRUCTIVE-styled confirm dialog → `_conclude_task`,
a small async state machine in the FIXED D-04 order:
1. `_teardown_session_terminals` (kill agent/shell process groups, killpg)
2. `_clear_task_state_files` (runtime state — arduis-owned)
3. `_container_down` (Phase-7 compose-down channel — separate from killpg; no-op if isolation OFF)
4. **CLEAN-GATE** `_conclude_clean_gate`: per-repo `git status --porcelain`, ALL-OR-NOTHING — any
   dirty repo REFUSES the whole conclude (toast + `_conclude_refuse_dialog`), ZERO remove argv issued
5. `_conclude_remove_worktrees`: `review.argv_worktree_remove(source, worktree)` per repo, cwd=SOURCE,
   **never `--force`**
6. `_conclude_prune`: `git worktree prune` per source repo
7. `_conclude_clean_task_folder`: unlink only `os.path.islink` dsts (the LINK, never the target —
   D-10), `os.rmdir` only-if-empty (never `rmtree`)
8. `_conclude_finalize`: drop from store, rebuild sidebar, fall back to main, drop widget maps.

## Verification

- Full suite: **402 passed** (399 + 3 conclude regression tests).
- `tests/test_window_conclude.py` (orchestrator-authored): bare window via `__new__` + synchronous
  `run_git_async` monkeypatch + recording stubs. Pins: (a) the fixed order (agents→state→container→
  status→remove→prune→folder→finalize); (b) a DIRTY repo refuses the whole conclude — zero remove
  argv, task NOT dropped; (c) NO `--force`/`-f` in any worktree-remove argv; (d) no-repos → straight
  to finalize.
- grep: no `git worktree remove --force` anywhere in window.py (only docstring mentions of its absence).
- D-10: symlink cleanup is `islink`-guarded unlink + rmdir-if-empty; no `rmtree`; source repos /
  branches / symlink targets never touched.

## Notes

- Real-git clean/dirty conclude + on-disk D-10 (symlink targets survive) is additionally covered by
  the 08-05 acceptance smoke (real git fixture under sandbox $HOME).
- Deviation: the conclude unit test was authored by the orchestrator (not the timed-out executor);
  the wiring itself was the executor's, reviewed before commit.

## Self-Check: PASSED
