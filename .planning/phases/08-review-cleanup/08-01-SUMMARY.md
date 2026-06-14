---
phase: 08-review-cleanup
plan: 01
subsystem: review
tags: [git, argv, parser, ttl-cache, gtk-free, tdd, worktree, diff]

# Dependency graph
requires:
  - phase: 03.2-projects-tasks
    provides: "TASK = cross-repo worktrees; D-10 (never remove source repos/symlink targets)"
  - phase: 02-worktree-core
    provides: "worktree.py GTK-free argv-builder + tolerant-parser discipline (the pattern mirrored here); git_service.run_git_async (executes the argv)"
provides:
  - "review.py: argv_diff, argv_diff_stat, argv_status_porcelain, parse_porcelain_clean, argv_worktree_remove (NO --force), argv_worktree_prune, argv_current_branch, argv_ahead_behind, parse_ahead_behind"
  - "review_cache.py: is_fresh(ts, now, ttl), ReviewCache (put/get/fresh_payload), GIT_TTL_S=30.0, GH_TTL_S=120.0"
  - "The dirty-tree clean gate (parse_porcelain_clean) and the structurally never-force worktree-remove builder — the load-bearing conclude safety (criterion 4 / D-04)"
affects: [08-02-gh, 08-03-review-window, 08-04-conclude-orchestrator, wave-2, wave-3]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "GTK-free domain layer: list-form git argv builders + tolerant parsers, no gi, no I/O (mirrors worktree.py / compose.py)"
    - "Structural-not-runtime safety: argv_worktree_remove omits the force token; the never-force guard test pins it"
    - "Caller-supplied monotonic time for purity: ReviewCache takes now=time.monotonic() from the window, stays unit-testable with fixed floats"

key-files:
  created:
    - src/arduis/review.py
    - src/arduis/review_cache.py
    - tests/test_review.py
    - tests/test_review_cache.py
  modified: []

key-decisions:
  - "argv_worktree_remove is structurally never-force (no --force/-f token); git's own refusal to remove a dirty worktree IS the protection (criterion 4 / D-04 / T-08-02)"
  - "parse_porcelain_clean returns stdout.strip() == '' — empty porcelain => clean => safe to remove; any line => dirty => Wave-3 refuses removal"
  - "parse_ahead_behind tolerant: only a clean two-integer 'A\\tB' returns (ahead, behind); empty/garbage/single-token/3-token/negative/float all degrade to (0,0), never raises"
  - "review_cache is_fresh uses strict < ttl (delta == ttl is expired); None ts is never fresh"
  - "TTL defaults pinned for Wave 2 to import by name: GIT_TTL_S=30.0, GH_TTL_S=120.0"

patterns-established:
  - "Public-contract argv signatures frozen by tests so Wave 2/3 wire pure glue (run_git_async + react to parsed result) without re-deriving argv"
  - "Throttle = manual refresh + TTL cache + (Wave-2) in-flight debounce, NOT a poll (gh is rate-limited) — T-08-03"

requirements-completed: [REVIEW-01, REVIEW-03, GIT-01]

# Metrics
duration: 3min
completed: 2026-06-14
---

# Phase 8 Plan 01: Review Domain Layer Summary

**GTK-free `review.py` (read-only diff / porcelain clean-gate / never-`--force` worktree remove+prune / branch ahead-behind argv + tolerant parsers) and `review_cache.py` (TTL `is_fresh` + task-keyed `ReviewCache`), both TDD, 34 new tests, full suite 378 green.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-06-14T14:29:08Z
- **Completed:** 2026-06-14T14:31:58Z
- **Tasks:** 3 (2 TDD features + 1 full-suite gate)
- **Files modified:** 4 created (2 source, 2 test)

## Accomplishments
- Froze the Phase-8 git read-introspection **public contract** (the exact argv Wave 2/3 will call) and pinned it with tests.
- Closed the **cardinal-sin guard**: `argv_worktree_remove` structurally cannot emit `--force`/`-f` (pinned over 5 inputs including dirs whose leaf is `-rf`, `--force`, `-f`).
- Pinned the **dirty-tree clean gate** (`parse_porcelain_clean`) — empty/whitespace => clean, any porcelain line => dirty — that Wave 3 consults per repo before any removal.
- Built the **TTL throttle backbone** (`is_fresh` + `ReviewCache`) with the documented git 30s / gh 120s defaults Wave 2 imports by name. No poll exists (T-08-03).
- Both modules are **GTK-free** (grep count 0 for `import gi`/`from gi`); the suite runs fully headless.

## Public Contract for Wave 2/3

Wave 2 (status subline + diff leaf) and Wave 3 (conclude orchestrator) call these verbatim via `git_service.run_git_async` and react to the parsed result. **Do not re-derive — import by name.**

### `src/arduis/review.py` (REVIEW-01, REVIEW-03, GIT-01)

```python
# --- read-only diff (REVIEW-01) — feeds a read-only VTE leaf (D-02) ---
argv_diff(repo)          -> ["git","-C",repo,"--no-pager","diff"]
argv_diff_stat(repo)     -> ["git","-C",repo,"--no-pager","diff","--stat"]

# --- the dirty-tree clean gate (REVIEW-03, criterion 4 / D-04) ---
argv_status_porcelain(repo)   -> ["git","-C",repo,"status","--porcelain"]
parse_porcelain_clean(stdout) -> bool   # True iff stdout.strip()=="" (clean=>safe to remove)

# --- safe teardown (REVIEW-03) — NEVER --force is the safety ---
argv_worktree_remove(source_repo, worktree_dir)
    -> ["git","-C",source_repo,"worktree","remove",worktree_dir]   # NO --force / -f, EVER
argv_worktree_prune(source_repo)
    -> ["git","-C",source_repo,"worktree","prune"]

# --- branch + ahead/behind read (GIT-01) — the sidebar subline ---
argv_current_branch(repo)        -> ["git","-C",repo,"rev-parse","--abbrev-ref","HEAD"]
argv_ahead_behind(repo, branch)  -> ["git","-C",repo,"rev-list","--left-right","--count",
                                     f"{branch}...{branch}@{{u}}"]
parse_ahead_behind(stdout) -> tuple[int,int]
    # "3\t2"->(3,2); "0\t0"->(0,0); ""/"garbage"/"5"/"1\t2\t3"/"-1\t2"/"1.5\t2" -> (0,0); never raises
```

**Conclude order (Wave 3, D-04) consumes these as:** per-repo `argv_status_porcelain` → `parse_porcelain_clean`; if ANY repo dirty → REFUSE (surface dirty list, no force path); else `argv_worktree_remove` → `argv_worktree_prune`.

### `src/arduis/review_cache.py` (GIT-01 throttle backbone)

```python
GIT_TTL_S = 30.0    # git reads (local, cheap)
GH_TTL_S  = 120.0   # gh reads (network / rate-limited)

is_fresh(ts: float | None, now: float, ttl: float) -> bool
    # None => False; strict (now - ts) < ttl (delta == ttl is expired)

class ReviewCache:                          # keyed by task_id, holds (payload, ts)
    put(task_id, payload, now) -> None      # overwrites
    get(task_id) -> tuple[object, float] | None        # raw record or None
    fresh_payload(task_id, now, ttl) -> object | None  # payload only if within ttl, else None
```

`now` is supplied by the caller — the window passes `time.monotonic()`; the cache is monotonic-agnostic. Wave 2 gates every git/gh read on `fresh_payload(...)` + an in-flight debounce (mirror `_compose_busy`) — there is **no poll**.

### Cardinal-sin confirmation
`argv_worktree_remove` has **no `--force` path anywhere** — the only `--force`/`-f` occurrences in `review.py` are docstring prose explaining the rule. Pinned by `test_argv_worktree_remove_never_emits_force` over 5 inputs.

## Task Commits

1. **Task 1 RED: review.py tests** - `289165b` (test)
2. **Task 1 GREEN: review.py impl** - `1b0e0af` (feat)
3. **Task 2 RED: review_cache.py tests** - `f5c1062` (test)
4. **Task 2 GREEN: review_cache.py impl** - `f3389b3` (feat)
5. **Task 3: full-suite gate** - no code change (verification-only; 378 passed)

_No REFACTOR commits — both modules are flat pure functions, no cleanup needed._

## Files Created/Modified
- `src/arduis/review.py` - git read-introspection argv builders + tolerant parsers (REVIEW-01/03, GIT-01); the dirty-gate + never-force remove live here
- `src/arduis/review_cache.py` - TTL `is_fresh` + task-keyed `ReviewCache` + git/gh TTL constants (GIT-01)
- `tests/test_review.py` - 21 tests: diff argv, porcelain clean/dirty matrix, never-force guard, ahead/behind parse, GTK-free assertion
- `tests/test_review_cache.py` - 13 tests: is_fresh (None/expired/fresh/boundary), cache round-trip/overwrite/missing, fresh_payload TTL gating, TTL constants, GTK-free assertion

## Decisions Made
- Kept the argv exactly as the verified research shapes (no `--` separator added to `worktree remove` — the discrete-element argv already defends against flag injection, and the verified argv has no `--`).
- `parse_ahead_behind` rejects negative and float tokens (`-1`, `1.5`) via `str.isdigit()`, so only clean non-negative integer pairs parse — everything else degrades to `(0,0)`.
- Added a `test_is_fresh_exact_ttl_boundary_is_false` case beyond the plan's behavior list to lock the strict-`<` semantics (delta == ttl is expired), so Wave 2's debounce/TTL reasoning is unambiguous. [minor test addition, not a deviation — same module, tightens the contract]

## Deviations from Plan

None - plan executed exactly as written. Both TDD cycles went RED→GREEN cleanly on the first implementation (no debugging iterations, no auto-fixes). Task 3 confirmed zero regressions across the 344-test baseline.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required (`user_setup: []`).

## Next Phase Readiness
- **Wave 2 (08-02 gh.py + git_service `cwd=`)** and the status subline can import `argv_current_branch`/`argv_ahead_behind`/`parse_ahead_behind` and `ReviewCache`/`is_fresh`/`GIT_TTL_S`/`GH_TTL_S` directly. 08-02 runs in parallel and owns `gh.py` + `git_service.py` (disjoint from this plan's files).
- **Wave 3 (conclude orchestrator)** has the full safe-teardown primitive set: `argv_status_porcelain` + `parse_porcelain_clean` (the gate) → `argv_worktree_remove` (never-force) → `argv_worktree_prune`. The dirty-tree refusal is structurally guaranteed.
- No blockers.

## Self-Check: PASSED

- All 5 created files present on disk (review.py, review_cache.py, test_review.py, test_review_cache.py, 08-01-SUMMARY.md).
- All 4 task commits present in git history (289165b, 1b0e0af, f5c1062, f3389b3).
- Full suite: 378 passed (344 baseline + 34 new), 0 failures, 0 regressions.
- GTK-free grep: 0 matches for `import gi`/`from gi` in both source modules.

---
*Phase: 08-review-cleanup*
*Completed: 2026-06-14*
