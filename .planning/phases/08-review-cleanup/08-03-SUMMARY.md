---
phase: 08-review-cleanup
plan: 03
subsystem: ui
tags: [gtk4, vte, window, diff, gh, pr, status-subline, ttl-cache, debounce, review]

# Dependency graph
requires:
  - phase: 08-review-cleanup
    provides: "Plan 01 review.py (argv_current_branch/argv_ahead_behind/parse_ahead_behind, ReviewCache/GH_TTL_S); Plan 02 gh.py (argv_pr_view/argv_pr_create_web/parse_pr_view/gh_available/GH_*_MSG/GH_EXIT_NEEDS_AUTH/format_*_subline) + run_git_async(cwd=)"
  - phase: 07-containers
    provides: "_compose_busy in-flight busy-guard pattern (mirrored for _pr_busy); _toast; run_git_async"
provides:
  - "window.py _open_diff_leaf: a read-only (set_input_enabled(False)) VTE leaf running git --no-pager diff per repo worktree (REVIEW-01)"
  - "window.py _refresh_task_status: branch + ahead/behind + PR status subline behind gh_available gate + TTL cache + _pr_busy debounce (GIT-01/REVIEW-02, D-03)"
  - "window.py _on_open_pr: gh pr create --web (the ONE allowed write) gated on gh availability (REVIEW-02/D-05)"
  - "row-menu entries Ver diff ▸ / Atualizar status / Abrir PR (web) via win.ver_diff/win.refresh_status/win.open_pr"
affects: [08-04-conclude-orchestrator]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "window.py is pure glue over the Plan-01/02 GTK-free argv builders: build argv list → run_git_async(cwd=worktree) → react to the parsed result on the GLib loop"
    - "Status throttle = gh_available gate → ReviewCache.fresh_payload(TTL) → _pr_busy in-flight debounce (drop, never queue) → auto-read on create+row-activate; NO poll (mirrors _compose_busy)"
    - "Read-only VTE viewer: set_input_enabled(False) + `git --no-pager diff; exec zsh -i` keeps the buffer alive for scroll/copy while no keystroke reaches the child"

key-files:
  created: []
  modified:
    - src/arduis/window.py

key-decisions:
  - "Diff leaf teardown: NO TerminalRecord — layout/widget-map only; _close_terminal's record-None branch drops the leaf cleanly (the diff child dies with its PTY). No pgid kill needed (it is not an agent / writes no state file)."
  - "Auto-read on create fires at the END of _finalize_task_creation (after the task has its repos in the store), not at _store.add (where task.repos is still empty) — the plan's 'after _store.add' intent is the create completion point."
  - "Status uses task.repos[0] (primary repo) — aggregate-in-subline per the plan; the subline shares the existing _subline_by_sid label (the ~2s RAM poll also writes it — see Known Interaction)."
  - "Branch/ahead-behind chained: current-branch read → ahead/behind read → PR read, each cwd=worktree; the parsed branch name (falling back to repo.branch) prefixes the PR subline."

patterns-established:
  - "Pattern: row-menu review entries appended via _append_review_menu_items(menu, session) in BOTH active+hibernated branches (Plan 04 adds 'Concluir task' to the SAME _make_row_menu_cb)"
  - "Pattern: gh-gated menu item (Abrir PR only when gh.gh_available()); gh-absent → subline GH_ABSENT_MSG, never invokes gh"

requirements-completed: [REVIEW-01, REVIEW-02, GIT-01]

# Metrics
duration: 12 min
completed: 2026-06-15
---

# Phase 8 Plan 03: Review Read Surfaces Wired into window.py Summary

**Read-only `git --no-pager diff` VTE leaf (`set_input_enabled(False)`), a branch + ahead/behind + PR-status sidebar subline behind a `gh_available` gate + `ReviewCache` TTL + `_pr_busy` in-flight debounce (no poll), and the `gh pr create --web` write — all wired as pure glue over the Plan-01/02 GTK-free argv builders via `run_git_async(cwd=worktree)`.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 3 (all auto)
- **Files modified:** 1 (src/arduis/window.py)
- **Tests:** 399 passed (baseline 399), zero regression

## Accomplishments
- **REVIEW-01 (read-only diff leaf):** `_open_diff_leaf(task, repo)` spawns a new leaf in the active workspace — `_make_terminal()` → `terminal.set_input_enabled(False)` → `_make_leaf(badge_label="diff")` → register in `_leaf_by_sid`/`_term_by_sid` → `LayoutModel.split` beside the focused pane (or root it) → `_reflect_layout()` → `spawn_async(cwd=worktree_dir, ["zsh","-l","-i","-c","git --no-pager diff; exec zsh -i"])`. A duplicate `win.ver_diff` for the same repo just refocuses the existing leaf.
- **GIT-01/REVIEW-02 (status subline + throttle):** `_refresh_task_status(task, *, force=False)` reads branch → ahead/behind → PR for `task.repos[0]`, rendering through `gh.format_branch_subline`/`format_pr_subline` into the existing `_subline_by_sid` label. PR read is gated on `gh.gh_available()` (absent → `GH_ABSENT_MSG`, never calls gh), then the TTL cache (`fresh_payload`/`GH_TTL_S`) unless `force`, then `_pr_busy` (drop). `_on_pr` always clears `_pr_busy`, maps exit-4 → `GH_UNAUTH_MSG`, rc!=0/empty → "sem PR", and wraps `parse_pr_view` in `try/except (ValueError, TypeError)` so garbage never crashes the GLib loop.
- **REVIEW-02/D-05 (the ONE allowed write):** `_on_open_pr` runs `gh.argv_pr_create_web()` via `run_git_async(cwd=primary worktree)`, toasts the result (rc 0 → "PR aberto no navegador" + force-refresh; exit-4 → `GH_UNAUTH_MSG`; else a short pt-BR error from `err`'s first line). The menu item is offered ONLY when `gh.gh_available()`.
- **Auto-read gating (D-03):** fires ONCE at the end of `_finalize_task_creation` (create) and ONCE in `_on_row_activated` for an ACTIVE task. The TTL cache makes rapid row-switching a no-op for gh. NO poll tick was added.

## New window.py methods + actions
- `_open_diff_leaf(self, task, repo)`, `_make_diff_spawn_cb(self, diff_tid)`, `_on_ver_diff(self, _action, param)` — action `win.ver_diff` (string target = repo_name)
- `_append_review_menu_items(self, menu, session)` — Ver diff ▸ submenu (per-repo / single for 1-repo) + Atualizar status + Abrir PR (web, gh-gated), appended in both active+hibernated branches
- `_set_status_subline(self, sid, text)`, `_refresh_task_status(self, task, *, force=False)`, `_on_refresh_status(self, _action, _param)` — action `win.refresh_status` (no target)
- `_on_open_pr(self, _action, _param)` — action `win.open_pr` (no target)
- `__init__` fields: `self._review_cache = ReviewCache()`, `self._pr_busy: set[str] = set()`
- imports: `from arduis import gh, review`; `from arduis.review_cache import ReviewCache, GH_TTL_S`

## 0.76 API confirmations
- `Vte.Terminal.set_input_enabled` is present at the 0.76 floor (verified live on host: `hasattr(Vte.Terminal,'set_input_enabled') is True`). Used to make the diff pane a read-only viewer (scroll/copy still work; no keystroke reaches the child — T-08-08).

## Diff-leaf teardown approach (PINNED)
The diff leaf is **layout/widget-map only — NO TerminalRecord**. It is not an agent and writes no state file, so `_close_terminal`'s `record is None` path drops it from the LayoutModel + `_leaf_by_sid`/`_term_by_sid` without a pgid kill; the diff child dies with its PTY when the leaf's `✕` closes it. `_make_diff_spawn_cb` is a benign no-op (records no pid). This is the cleaner of the two plan-offered options (record vs layout-only).

## Task Commits
1. **Task 1: read-only diff leaf + 'Ver diff' menu (REVIEW-01)** — `5c1e998` (feat)
2. **Task 2: branch+PR status subline + TTL/debounce throttle (GIT-01/REVIEW-02)** — `a447177` (feat)
3. **Task 3: 'Abrir PR (web)' — the ONE allowed write (REVIEW-02/D-05)** — `3d50589` (feat)

## Files Created/Modified
- `src/arduis/window.py` — added the diff-leaf spawn, the status-subline read chain behind the throttle, the PR-create write, and the three row-menu entries/actions; pure glue over Plan 01/02.

## Decisions Made
- See key-decisions frontmatter. Notably: diff leaf is record-less (layout cleanup only); create auto-read at `_finalize_task_creation` tail (repos present) rather than `_store.add` (repos empty); status on `task.repos[0]` aggregated into the shared subline.

## Deviations from Plan

None - plan executed exactly as written. The plan said "after `_store.add`" for the create auto-read; the literal `_store.add` point has `task.repos == []` (repos are added asynchronously), so the auto-read was placed at the create-completion point (`_finalize_task_creation` tail, where the task is fully in the store with its repos) — this matches the plan's intent ("ONCE on task create ... after the task is in the store") and is not a behavioral deviation.

## Known Interaction
The status subline reuses the EXISTING `_subline_by_sid` label, which the ~2s RAM poll (`claude · <ram>`) also writes. They share one label by design (the plan specifies updating that label in place). Status reads are event-driven (create / row-activate / manual refresh + TTL + debounce); the RAM poll is periodic and will overwrite the branch/PR text on its next tick. This is the accepted single-subline tradeoff for v1 (aggregate-in-subline, A6); a dedicated status line is out of scope. Live UAT (Wave 4 smoke) observes the actual rendered cadence.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. gh is a host CLI; absent/unauthed degrade gracefully (`gh ausente` / `gh não autenticado`).

## Note for Plan 04
The row menu now has **Ver diff ▸ / Atualizar status / Abrir PR (web)** appended via `_append_review_menu_items` in BOTH the active and hibernated branches of `_make_row_menu_cb`. Plan 04 (the conclude/teardown wave) adds **"Concluir task"** to the SAME `_make_row_menu_cb` — the two window.py waves are sequential and never edit the file concurrently.

## Next Phase Readiness
- Wave 4 headless smoke can assert the menu entries appear (`win.ver_diff`/`win.refresh_status`/`win.open_pr`) and the argv shapes (`git --no-pager diff`, `gh pr view`, `gh pr create --web`) without ever executing the write.
- Plan 04 (conclude orchestrator) is unblocked — the safe-teardown primitives (Plan 01) and the row menu seam are both in place.

## Self-Check: PASSED

- `src/arduis/window.py` modified; `.planning/phases/08-review-cleanup/08-03-SUMMARY.md` present on disk.
- All 3 task commits present in git history: `5c1e998` (Task 1), `a447177` (Task 2), `3d50589` (Task 3).
- Full suite: 399 passed (= 399 baseline), 0 regressions; window.py parses (`ast.parse`) and imports clean headless (broadway).
- Wiring assertions green: `set_input_enabled(False)`, `_open_diff_leaf`, `_refresh_task_status`, `_pr_busy`, `gh_available`, `monotonic`, `argv_pr_create_web`, `win.ver_diff`/`win.refresh_status`/`win.open_pr` all present; no `Placeholder` strings remain.
