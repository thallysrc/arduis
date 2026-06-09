---
phase: 02-core-loop-new-worktree-env-agent
plan: 01
subsystem: domain
tags: [worktree, session, git-argv, serialization, ram, swarm-seam, tdd, gtk-free]
requires: [01]
provides:
  - "worktree.py: pure git-argv builders + parsers (default-branch fallback, add argv, sanitize, porcelain parse, infer new/existing)"
  - "session.py: GTK-free serializable SessionStore + WorktreeSession + SessionState + AGENT_FEED + hibernate_fields"
  - "swarm/: named-empty seam directory"
affects:
  - "Plan 02 window.py (GTK wiring) consumes these argv builders + SessionStore"
  - "Phase 3 sidebar binds to the same SessionStore"
tech-stack:
  added: []
  patterns:
    - "GTK-free pure-domain modules (stdlib only, unit-tested) — Phase-1 layering extended"
    - "List-form git argv routed through HostRunner by the caller (no shell strings)"
    - "str-Enum + dataclasses.asdict for JSON-serializable session model"
key-files:
  created:
    - src/arduis/worktree.py
    - src/arduis/session.py
    - src/arduis/swarm/__init__.py
    - tests/test_worktree.py
    - tests/test_session.py
  modified: []
decisions:
  - "Sanitization scheme (D-05/A2): replace non-[A-Za-z0-9._-] with '-', collapse dash runs, strip leading/trailing '.-', fallback to 'branch' if the result would be empty/'.'/'..' — guarantees a safe flat dir leaf (T-02-02)."
metrics:
  duration: ~12m
  completed: 2026-06-09
  tasks: 2
  files: 5
  commits: 4
  tests_added: 9
---

# Phase 2 Plan 01: Pure Worktree + Session Domain Layer Summary

GTK-free domain brain of the core loop: list-form git-argv builders with an origin->local default-branch fallback and path-traversal-safe sibling-dir sanitization (`worktree.py`), plus a JSON-serializable `SessionStore` carrying the `rss_kb` RAM field day-one, the `b"claude\n"` bytes feed constant, and a hibernate transition that keeps the directory (`session.py`) — all nine Wave-0 unit tests GREEN, and the named-empty `swarm/` seam in place.

## What Was Built

**Task 1 — `src/arduis/worktree.py` (pure git-argv builders + parsers):**
- Default-branch detection chain (D-04): `argv_default_branch_via_origin` + `argv_default_branch_local` fallback; `parse_default_branch` strips the `refs/remotes/origin/` prefix. No hardcoded `main`.
- `argv_worktree_add_new` (`-b <branch> <dir> <base>`) and `argv_worktree_add_existing` (`<dir> <branch>`) — the force flag is emitted nowhere (D-07/T-02-03).
- `sanitize_branch_for_dir` + `worktree_dir_for` — branch -> safe `[A-Za-z0-9._-]` leaf, dir derived from `repo_root`'s parent; `..`/separators can never survive (D-05/T-02-02).
- `argv_list_local_branches` + `parse_local_branches` + `infer_new_vs_existing` (WT-01/D-06).
- `argv_worktree_list_porcelain` + `parse_worktrees` + `branch_checked_out_path` — already-checked-out detection (D-07).
- All argv are Python list literals (T-02-01); no `gi` import.

**Task 2 — `src/arduis/session.py` + `src/arduis/swarm/__init__.py`:**
- `AGENT_FEED = b"claude\n"` (bytes, D-08/Pitfall 1 — `feed_child` rejects str at the 0.76 floor).
- `SessionState(str, Enum)` ACTIVE/HIBERNATED (serializes to its value).
- `WorktreeSession` dataclass with `rss_kb` RAM field present day-one (D-13); `to_dict()` via `asdict`.
- `SessionStore` add/get/by_branch/all/to_list — `to_list()` is JSON-serializable.
- `hibernate_fields(session)` — state=HIBERNATED, clears pid/pgid, leaves `worktree_dir`/`repo_root`/`rss_kb` untouched (D-11: kill agent, KEEP directory).
- `swarm/__init__.py` — named-empty seam (roadmap requirement, no code in v1).

## How It Was Verified

- `.venv/bin/python -m pytest tests/test_worktree.py -q` -> 5 passed.
- `.venv/bin/python -m pytest tests/test_session.py -q` -> 4 passed.
- `.venv/bin/python -m pytest -q` (full suite) -> 24 passed (15 Phase-1 + 9 new), no regression.
- `grep -rL "import gi"` lists both domain modules (confirming they never import `gi`).
- The force-flag literal is absent from `worktree.py` (argv builders + docs).

> Note: the main checkout's `.venv` (pytest 9.0.3, Python 3.12.3) was used to run the suite — this worktree has no separate `.venv`, and git worktrees share the same source tree the venv resolves via `pythonpath=["src"]`.

## TDD Flow

Each task followed RED -> GREEN (no REFACTOR needed; code was clean on first GREEN):
1. `test(02-01)` failing `tests/test_worktree.py` (ImportError) -> `feat(02-01)` `worktree.py` GREEN.
2. `test(02-01)` failing `tests/test_session.py` (ImportError) -> `feat(02-01)` `session.py` + swarm seam GREEN.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Wrote the Wave-0 RED test files (`tests/test_worktree.py`, `tests/test_session.py`)**
- **Found during:** Task 1 setup (before any implementation).
- **Issue:** The plan (`depends_on: [00]`, `type: tdd`) assumes Plan 00 / Wave 0 already created the RED tests these GREEN tasks must satisfy, but neither test file existed in this worktree — the `verify` and `acceptance_criteria` could not run without them. This is a missing-dependency blocker.
- **Fix:** Authored both test files verbatim to the plan's `<behavior>` contract and the verified literals in 02-RESEARCH.md (default-branch chain, add argv, porcelain parse, bytes feed, store CRUD/serialize, hibernate transition). Committed each as a `test(02-01)` RED commit before its GREEN implementation, preserving the TDD flow.
- **Files modified:** `tests/test_worktree.py`, `tests/test_session.py`
- **Commits:** f8d5b3c (test_worktree RED), 6fb3366 (test_session RED)

**2. [Rule 3 - Blocking] Used the main checkout's `.venv` to run pytest**
- **Found during:** Task 1 verification.
- **Issue:** This git worktree has no `.venv`; `python3` on PATH has no pytest.
- **Fix:** Ran the suite via `/home/thallysrc/Projects/arduis/.venv/bin/python` (the main checkout's venv, pytest 9.0.3). No code change — just the runner path.
- **Commits:** n/a (tooling only)

### Out of Scope (not fixed)

- **ruff not installed in `.venv`** — the verification's optional `grep` gi-free check passed; lint (`ruff`) is absent from the venv (no fallback). Not a plan gate (the gate is the pytest suite, which is green). Logged here, not fixed.

## Known Stubs

The `rss_kb` field is intentionally `None` in Phase 2 (D-13 — RAM field carried day-one, populated in Phase 3 RAM-02/03). `swarm/__init__.py` is intentionally empty (roadmap swarm seam — no code in v1). Both are planned-stub seams documented by the plan, not blocking stubs.

## Self-Check: PASSED

- Files: all 5 created files FOUND on disk.
- Commits: f8d5b3c, 9a5a511, 6fb3366, 926a377 all FOUND in git history.
- Tests: full suite 24/24 GREEN.
