---
review_date: 2026-06-15
scope: full src/arduis/ correctness + security pass (autonomous session)
reviewers: 3 parallel code-reviewer agents (domain, services/IO, window orchestrator)
suite_state: 437 passing at review time
---

# arduis Code Review — 2026-06-15

Autonomous correctness/security review of `src/arduis/` (post v1.0 milestone audit).
High-confidence findings only; style nits excluded. A recurring root cause emerged:
the Phase 03.4 "multi-project both alive" refactor left several handlers scoped to the
**active project only** — the same bug class as the already-fixed `_reconcile_orphans`
(quick task 260615-t37).

## Disposition

| # | Finding | Severity | Disposition |
|---|---------|----------|-------------|
| 1 | `git_service.run_git_async` — `Gio.Subprocess.new`/`spawnv` can raise `GLib.Error` (deleted cwd / missing exe); exception escapes uncaught, `on_done` never fires → UI stuck | High | **FIXED** (this session) |
| 2 | `layout.close_leaf` — closing the LAST pane (single-leaf root) early-returns, skipping `focused_id`/`_mru` cleanup → stale references | Medium | **FIXED** (this session) |
| 3 | `window._apply_theme` — re-colors only the active project's terminals; background-project terminals keep the old palette on theme switch (contradicts its own docstring "re-color EVERY live terminal") | Medium | **FIXED** (this session) |
| 4 | `window._on_status_event` + `_poll_ram` — status watcher + RAM poll scoped to the active project's bundle; a BACKGROUND project's agent entering WAITING is never surfaced (no dot, no notification) | High | **DEFERRED — needs UX decision** |
| 5 | `window._on_close_request` SIGKILL via `GLib.timeout_add` — the 1500ms timer never fires after the window closes (main loop ends); processes that ignore SIGHUP orphan | High | **FIXED** (quick 260615-tzk — synchronous sweep, early-exit common case) |
| 6 | `window._clear_task_state_files` — uses `_proj_term_id` (active root) when clearing a BACKGROUND project's task during close/remove → wrong path unlinked | Low | **DEFERRED — low impact** (status dir wiped at next startup) |
| 7 | `appconfig.write_theme` `_serialize` — silently drops user-authored root-level scalar TOML keys on rewrite | Low | **DEFERRED — arduis has no root scalars; doc'd behavior** |

False alarms investigated and dismissed: `git_service get_exit_status` raw-waitstatus
(GLib's `get_exit_status()` returns the WEXITSTATUS-decoded code, so `gh rc==4` works);
`trust._serialize_trusted` empty-table (never reaches the zero-entry case);
`review.argv_ahead_behind` detached-HEAD (documented degrade path); `layout.resolve_selection`
return type (not called from production).

## Deferred findings — why they need your input

### #4 Multi-project attention surfacing (HIGH)
With two projects "both alive", a background project's agent can enter WAITING — the exact
signal arduis exists to surface — but `_on_status_event` (window.py:947) looks up only the
active project's `_record_by_state_file`, so the event is dropped. Same for `_poll_ram`
(window.py:4161) → background tasks are never RAM-polled / auto-suspended / time-degraded.

**Why deferred:** the *right* fix depends on intended UX:
- Should a background project's WAITING agent fire a desktop **notification** (likely yes — that's the value prop)?
- Should the **sidebar** show background projects' task dots, or only reconcile status on switch-back? (The sidebar currently renders the active project's tasks only.)
- Should RAM polling / auto-suspend run for background projects continuously (RAM cost) or only the active one?

These are product decisions, not mechanical fixes. Recommend a small phase or discuss session.

### #5 Orphan-on-close (HIGH) — FIXED (quick 260615-tzk)
> Resolved with a synchronous SIGKILL sweep that early-exits when groups die on SIGHUP (≈0 added
> close latency in the common case) and only waits and SIGKILLs true SIGHUP-ignorers. The latency
> concern below was the reason it was originally flagged for review; the early-exit design neutralizes it.

`_teardown_pgid` sends SIGHUP synchronously (good) but schedules SIGKILL via a GLib timer
that won't run once the window closes. Most children die on SIGHUP; only SIGHUP-ignoring
processes orphan. The container teardown already uses synchronous `subprocess.run` at close.
**Why deferred:** the fix is a synchronous SIGKILL sweep, which adds up to `_SIGKILL_GRACE_MS`
(1500ms) to window-close latency — a UX tradeoff worth your call (shorten the grace? only
sleep if a pgid is still alive?).

## Fixed this session
See quick task(s) following this doc. All fixes shipped with regression tests; full suite green.
