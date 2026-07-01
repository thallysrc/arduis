---
phase: 02-core-loop-new-worktree-env-agent
plan: 00
subsystem: testing
tags: [pytest, tdd, git-worktree, session-store, vte, dataclasses]

# Dependency graph
requires:
  - phase: 01-terminal
    provides: "GTK-free domain layering (spawn.py/exit_status.py) + pytest suite conventions reused for the new test files"
provides:
  - "tests/test_worktree.py — RED contract for arduis.worktree (default-branch fallback, add argv, sanitize, porcelain parse, infer new/existing)"
  - "tests/test_session.py — RED contract for arduis.session (AGENT_FEED bytes, SessionStore CRUD/serialize, hibernate_fields model)"
  - "Locked function signatures for the Plan-01 GTK-free domain layer"
affects: [02-01, 02-02]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Wave-0 RED-first: tests import not-yet-existing modules to pin the domain contract before implementation"
    - "GTK-free serializable domain layer pinned via json.dumps roundtrip assertion"

key-files:
  created:
    - tests/test_worktree.py
    - tests/test_session.py
  modified: []

key-decisions:
  - "Used the main-repo .venv (worktree has no local .venv) to run pytest from the worktree dir; pythonpath=src resolves to the worktree src"
  - "Encoded path-traversal guard (T-02-02) directly as test_sanitize_dir assertions on the resulting basename"

patterns-established:
  - "Wave-0 RED test files import the target module at top-level so the failure is a clean ModuleNotFoundError until the impl lands"

requirements-completed: []

# Metrics
duration: 6min
completed: 2026-06-09
---

# Phase 2 Plan 00: Wave-0 Test Scaffolds Summary

**RED pytest contracts (tests/test_worktree.py + tests/test_session.py) pinning the GTK-free git-worktree argv/parse builders and the serializable SessionStore + bytes-feed/hibernate model, before any Phase-2 domain code exists.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-09T16:18:00Z
- **Completed:** 2026-06-09T16:23:56Z
- **Tasks:** 2
- **Files modified:** 2 (both created)

## Accomplishments
- `tests/test_worktree.py`: 5 named tests (test_default_branch_fallback, test_add_argv, test_sanitize_dir, test_detect_checked_out, test_infer_new_vs_existing) pinning the `arduis.worktree` contract using the verified argv/porcelain literals from 02-RESEARCH.md.
- `tests/test_session.py`: 3 named tests (test_agent_feed_is_bytes, test_store_serializable, test_hibernate_model) pinning the `arduis.session` contract — bytes feed constant, JSON-serializable store with the day-one `rss_kb` RAM field, and the hibernate model transition that keeps `worktree_dir`.
- Both files are RED via `ModuleNotFoundError` (no implementation yet) — the deliberate end-of-Wave-0 state.
- Phase-1's 15 tests remain green (no regression).

## Task Commits

Each task was committed atomically (TDD RED):

1. **Task 1: RED — tests/test_worktree.py** - `54c9bd0` (test)
2. **Task 2: RED — tests/test_session.py** - `a76b24a` (test)

_TDD note: this plan is RED-only; the GREEN implementation is Plan 01. No feat/refactor commits here by design._

## Files Created/Modified
- `tests/test_worktree.py` - Failing contract for the pure git-worktree argv builders + parsers (D-04/D-05/D-06/D-07); encodes threats T-02-01 (list argv, no `--force`) and T-02-02 (path-traversal guard).
- `tests/test_session.py` - Failing contract for `AGENT_FEED` bytes constant (D-08), `SessionStore` CRUD + serialization with `rss_kb` (D-13), and `hibernate_fields` model transition keeping the dir (D-11).

## Decisions Made
- **Run pytest via the main-repo `.venv`.** This worktree has no local `.venv`; the project venv lives at `/home/thallysrc/Projects/arduis/.venv`. Running `/home/thallysrc/Projects/arduis/.venv/bin/python -m pytest` from the worktree dir resolves `pythonpath=["src"]` to the worktree's `src`, so the worktree's code/tests are exercised with the shared interpreter. The plan's `.venv/bin/python` literal is a worktree-relative path that does not exist here.
- **Path-traversal guard encoded in `test_sanitize_dir`** by asserting `".."` cannot appear in `sanitize_branch_for_dir(...)` output nor in the basename of `worktree_dir_for(...)` for `"../escape"` / `"/abs"` inputs (T-02-02).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Verification command venv path adjusted for the worktree**
- **Found during:** Task 1 (running the RED verify command)
- **Issue:** The plan's verify/test commands use a worktree-relative `.venv/bin/python`, but this parallel worktree has no local `.venv` — only the main repo at `/home/thallysrc/Projects/arduis/.venv` does. The verbatim command fails with "No such file or directory".
- **Fix:** Ran the identical pytest invocation through the main-repo venv interpreter (`/home/thallysrc/Projects/arduis/.venv/bin/python -m pytest ...`) executed from the worktree directory, so `pythonpath=["src"]` resolves to the worktree's `src`. Test content is unchanged from the plan's contract.
- **Files modified:** None (execution-environment adjustment only).
- **Verification:** `RED-OK` printed for both files; Phase-1 suite (15 tests) green when run in isolation.
- **Committed in:** N/A (no file change).

---

**Total deviations:** 1 auto-fixed (1 blocking — environment path).
**Impact on plan:** No change to test content or contract. The two files are exactly the RED scaffolds the plan specified.

## Issues Encountered
- Running the full suite (`pytest -q`) reports the two new files as collection-time `ModuleNotFoundError` and interrupts before Phase-1 tests execute. This is the expected RED state, not a regression — confirmed Phase-1's 15 tests still pass by running the four Phase-1 files in isolation.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 01 can now implement `src/arduis/worktree.py` and `src/arduis/session.py` against a fixed, executable contract (8 named tests across the two files). Turning RED → GREEN is the explicit Plan-01 success gate.
- No blockers.

## Known Stubs
None — this is a test-only plan; the intentional RED state (modules absent) is the contract, not a stub.

## Self-Check: PASSED
- FOUND: tests/test_worktree.py
- FOUND: tests/test_session.py
- FOUND commit: 54c9bd0
- FOUND commit: a76b24a

---
*Phase: 02-core-loop-new-worktree-env-agent*
*Completed: 2026-06-09*
