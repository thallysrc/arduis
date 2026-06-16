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
| 4 | `window._on_status_event` + `_poll_ram` — status watcher + RAM poll scoped to the active project's bundle; a BACKGROUND project's agent entering WAITING is never surfaced (no dot, no notification) | High | **FIXED** (quick 260616-buk — route attention across all bundles; PO decision: notify + background RAM-poll, dots reconcile on switch) |
| 5 | `window._on_close_request` SIGKILL via `GLib.timeout_add` — the 1500ms timer never fires after the window closes (main loop ends); processes that ignore SIGHUP orphan | High | **FIXED** (quick 260615-tzk — synchronous sweep, early-exit common case) |
| 6 | `window._clear_task_state_files` — uses `_proj_term_id` (active root) when clearing a BACKGROUND project's task during close/remove → wrong path unlinked | Low | **FIXED** (quick 260616-buk — clear via the task's OWNING-root namespace `_proj_term_id_for`) |
| 7 | `appconfig.write_theme` `_serialize` — silently drops user-authored root-level scalar TOML keys on rewrite | Low | **DEFERRED — arduis has no root scalars; doc'd behavior** |

False alarms investigated and dismissed: `git_service get_exit_status` raw-waitstatus
(GLib's `get_exit_status()` returns the WEXITSTATUS-decoded code, so `gh rc==4` works);
`trust._serialize_trusted` empty-table (never reaches the zero-entry case);
`review.argv_ahead_behind` detached-HEAD (documented degrade path); `layout.resolve_selection`
return type (not called from production).

## Deferred findings — why they need your input

### #4 Multi-project attention surfacing (HIGH) — FIXED (quick 260616-buk)
> Resolved. `_on_status_event` now searches EVERY registered project's bundle for the touched
> path, and `_poll_ram` iterates all projects with each project's own bundle + owning-root
> status-file namespace, so a BACKGROUND project's WAITING agent fires the desktop notification,
> is RAM-polled, and is time-degraded. Per the PO decision: background tasks notify + keep
> RAM-polling; sidebar/pane dots reconcile automatically on switch (no per-frame background
> widget updates). Auto-suspend stays ACTIVE-project-only (the shared `_hibernate_task` body is
> bound to the active bundle's layout/workspace/sidebar maps — see SUMMARY decision (i)); all the
> surfacing value (notify + dots + RAM poll) works regardless of which project is active.

The original UX questions (now answered by the PO):
- Background WAITING agent fires a desktop **notification** — YES (the value prop).
- The **sidebar** reconciles a background project's dots on switch-back (not per-frame).
- RAM polling runs for ALL projects; auto-suspend is deferred to when the project is active.

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
See quick task(s) following this doc. All fixes shipped with regression tests; full suite green
(437 -> 448, 11 new tests).

- #1, #2, #3 -> quick 260615-trz
- #5 -> quick 260615-tzk
- #4, #6 -> quick 260616-buk
- #7 -> deferred (non-issue for v1: arduis writes no root-level scalar TOML keys)

## Adversarial verification of the attention fix (260616-buk / commit a6ff97f)
A focused code-reviewer re-examined the 313-line attention diff for regressions. **Result: no
high-confidence regressions; active-project path confirmed byte-identical.** Verified: single-project
`registry.all()` lookup == old active-bundle property; `_proj_term_id` delegation is identical for
active callers; `_poll_ram` `to_suspend` is correctly active-only (identity check); `_project_for_task`
identity match is sound; SHA1 owning-root namespacing is collision-free; no O(N) blowup; no stale
reference between ticks (GLib serializes callbacks; `registry.all()` re-read each tick).

**Latent (non-triggerable) note — not a live bug:** `_clear_repo_state_files` pops from the ACTIVE
bundle's `record_by_state_file`/`notif_by_tid` regardless of its `root` param. Its only caller passes
the default (active) root and is gated to ACTIVE tasks, so no wrong-bundle pop is reachable today. If a
future caller ever passes a non-active root, switch it to the owning bundle (mirror the
`_clear_task_state_files` pattern). Left unchanged to avoid an untested edit to teardown code.
