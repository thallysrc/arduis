---
phase: 08-review-cleanup
plan: 02
subsystem: api
tags: [gh, git, github-cli, gio-subprocess, async, json, tdd]

# Dependency graph
requires:
  - phase: 07-containers
    provides: git_service.run_git_async (the argv-agnostic async runner reused verbatim)
provides:
  - "gh.py — GTK-free gh argv builders + JSON-shape parser + degrade helpers + subline formatters"
  - "argv_pr_view(branch) → read-only PR fetch via the stable --json contract (REVIEW-02)"
  - "argv_pr_create_web() → the ONE allowed write (gh pr create --web), AFK-safe (D-05)"
  - "parse_pr_view(stdout) → dict on valid JSON, raises ValueError/TypeError on garbage (T-08-05)"
  - "gh_available() + degrade_message(rc) → graceful gh-absent/exit-4 degrade (D-06)"
  - "format_pr_subline(pr) / format_branch_subline(branch, ahead, behind) → glanceable sublines (GIT-01)"
  - "run_git_async(argv, on_done, runner=None, cwd=None) → backward-compatible optional cwd (D-07)"
affects: [08-review-cleanup Wave 2 (status subline wiring), 08-review-cleanup Wave 3 (PR create / refresh)]

# Tech tracking
tech-stack:
  added: []  # zero new third-party deps — host gh CLI + stdlib json/shutil only
  patterns:
    - "gh argv-builder + json-shape-parse split (GTK-free), mirroring compose.py"
    - "gh is just another argv list on run_git_async — no new service module (D-01)"
    - "optional cwd= via Gio.SubprocessLauncher.new(flags) + set_cwd + spawnv, default path byte-identical"

key-files:
  created:
    - src/arduis/gh.py
    - tests/test_gh.py
    - tests/test_git_service_cwd.py
  modified:
    - src/arduis/git_service.py

key-decisions:
  - "gh pr create --web is the default builder for the ONE allowed write (D-05/A8) — never executed in tests"
  - "parse_pr_view RAISES on garbage/non-dict (does not return None) so the contract is explicit (T-08-05)"
  - "cwd=None path is byte-identical (Gio.Subprocess.new); cwd set uses SubprocessLauncher (D-07)"
  - "Degrade strings pinned: 'gh ausente' (absent) / 'gh não autenticado' (exit-4) (D-06)"

patterns-established:
  - "GTK-free gh domain: imports json/shutil only, no gi — asserted by source scan in test"
  - "Backward-compatible optional kwarg: new param last, None default preserves the prior path exactly"

requirements-completed: [REVIEW-02, GIT-01]

# Metrics
duration: 18 min
completed: 2026-06-14
---

# Phase 8 Plan 02: gh.py + run_git_async cwd= Summary

**GTK-free `gh.py` (read-only `gh pr view --json` parse, the ONE allowed write `gh pr create --web`, gh-absent/exit-4 graceful degrade, glanceable sublines) plus a backward-compatible optional `cwd=` on `run_git_async` so gh infers its repo from the worktree dir.**

## Performance

- **Duration:** ~18 min
- **Completed:** 2026-06-14
- **Tasks:** 3 (2 TDD RED+GREEN, 1 full-suite gate)
- **Files created/modified:** 4 (2 src, 2 tests)
- **Tests:** 365 passed (baseline 344 + 21 new: 19 gh + 2 cwd); zero regressions

## Accomplishments

- `src/arduis/gh.py`: GTK-free gh argv builders, the `--json` shape parser with a garbage guard, the `shutil.which` absence probe, the exit-4/absent degrade helpers (pinned pt-BR strings), and the two subline formatters — gh is never invoked in any test.
- `run_git_async` gained an optional `cwd=` (D-07), proven against a real temp git repo + the GLib loop; the `cwd=None` default path is byte-identical, so every existing caller is unaffected.
- Full suite green at 365 passed.

## Task Commits

1. **Task 1: gh.py (argv builders, parse_pr_view + guard, gh_available, degrade, sublines)** — `a52fee8` (feat)
2. **Task 2: run_git_async optional cwd= (D-07), backward-compatible** — `f4a5bb7` (feat)
3. **Task 3: full suite green** — no new files (verification-only; gh/cwd tests committed in Tasks 1/2)

_Note: per the plan, the TDD RED and GREEN phases for each feature were committed together as a single feat commit (the failing test + the implementation that makes it pass)._

## Public Contract for Wave 2/3

**This is the API Wave 2 (status subline wiring) and Wave 3 (PR create / refresh) will call.**

### `arduis.gh` (GTK-free — import freely, it pulls in NO gi)

```python
PR_VIEW_FIELDS = "state,number,title,url,isDraft,reviewDecision,mergeable,headRefName"
GH_ABSENT_MSG  = "gh ausente"            # show when gh_available() is False — never call gh
GH_UNAUTH_MSG  = "gh não autenticado"    # show on exit-code 4
GH_EXIT_NEEDS_AUTH = 4                    # VERIFIED: gh help exit-codes

def argv_pr_view(branch: str) -> list[str]:
    # ["gh","pr","view",branch,"--json",PR_VIEW_FIELDS] — run with cwd=<worktree>
def argv_pr_create_web() -> list[str]:
    # ["gh","pr","create","--web"] — the ONE allowed write (D-05); NEVER run in tests
def parse_pr_view(stdout: str) -> dict:
    # json.loads + dict shape-guard; RAISES ValueError (bad JSON) / TypeError (non-dict)
def gh_available() -> bool:               # shutil.which("gh") is not None
def degrade_message(rc: int) -> str | None:  # 4 -> GH_UNAUTH_MSG, else None
def format_pr_subline(pr: dict) -> str:   # "PR #42 open" / "PR #7 open (rascunho)" / "sem PR"
def format_branch_subline(branch, ahead, behind) -> str:  # "feat/x · ↑3 ↓0" / "feat/x" (in sync)
```

**Wave-2 caller shape (the degrade + parse contract):**

```python
def _on_done(rc, out, err):
    if rc == gh.GH_EXIT_NEEDS_AUTH:               # or: msg = gh.degrade_message(rc)
        self._set_status_subline(task, gh.GH_UNAUTH_MSG); return
    if rc != 0 or not out.strip():
        self._set_status_subline(task, "sem PR"); return
    try:
        pr = gh.parse_pr_view(out)                # RAISES on garbage — wrap it
    except (ValueError, TypeError):
        return                                    # never crash the GLib loop (T-08-05)
    self._set_status_subline(task, gh.format_pr_subline(pr))

# probe FIRST — if gh is absent, show GH_ABSENT_MSG and never invoke gh:
if not gh.gh_available():
    self._set_status_subline(task, gh.GH_ABSENT_MSG)
else:
    run_git_async(gh.argv_pr_view(repo.branch), _on_done,
                  runner=self._runner, cwd=repo.worktree_dir)
```

### `arduis.git_service.run_git_async` — NEW signature

```python
def run_git_async(argv: list[str], on_done, runner: HostRunner | None = None,
                  cwd: str | None = None) -> None
```

- **`cwd=None` (default): BYTE-IDENTICAL to before** — uses `Gio.Subprocess.new(wrapped, flags)`. Every existing caller (window.py branch/commit reads, etc.) is unaffected — proven by the full suite (365 passed).
- **`cwd=<dir>`: runs the child in that dir** via `Gio.SubprocessLauncher.new(flags)` + `launcher.set_cwd(cwd)` + `launcher.spawnv(wrapped)`. The `SubprocessLauncher` API was confirmed present at the 0.76 floor on the host (`new`/`set_cwd`/`spawnv` all available). Pass `cwd=repo.worktree_dir` so gh infers the repo and `git diff` can drop the `-C`.
- `cwd` is a **trusted internal path** (a worktree dir arduis built), never raw user input — T-02-01 posture (argv stays a list, no shell) unchanged.

## Decisions Made

- Followed the plan's locked decisions (D-01/D-05/D-06/D-07, A8). `gh pr create --web` is the default write builder (AFK-safe, browser form, read-only-in-app afterward).
- `parse_pr_view` raises rather than returning `None` so the garbage-guard contract is explicit and the caller's `try/except (ValueError, TypeError)` is the single degrade point.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. (gh is a host CLI already present + authed on the host per 08-RESEARCH; absent/unauthed degrade gracefully.)

## Next Phase Readiness

- **Wave 2** (status subline wiring) can call `gh.argv_pr_view` / `parse_pr_view` / `gh_available` / `degrade_message` / `format_*_subline` and `run_git_async(..., cwd=repo.worktree_dir)` directly — the full contract above is pinned.
- **Wave 3** (PR create / refresh) can call `gh.argv_pr_create_web()` for the ONE allowed write.
- **Parallel safety:** this plan owns `gh.py` + `git_service.py` + their tests only; Plan 01 owns `review.py` + `review_cache.py` (disjoint). The `cwd=` extension is backward-compatible — no call-site changes were made in `window.py` (that wiring is Wave 2/3).

## Self-Check: PASSED

- Files: src/arduis/gh.py, tests/test_gh.py, tests/test_git_service_cwd.py, .planning/phases/08-review-cleanup/08-02-SUMMARY.md — all FOUND.
- Commits: a52fee8 (Task 1), f4a5bb7 (Task 2) — both FOUND.
- git_service.py contains the `cwd` param; full suite 365 passed; gh.py gi-import count = 0.

---
*Phase: 08-review-cleanup*
*Completed: 2026-06-14*
