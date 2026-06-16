---
quick_id: 260615-tzk
description: Fix orphan-on-close — synchronous SIGKILL sweep at app-exit
date: 2026-06-15
status: complete
source: .planning/CODE-REVIEW-2026-06-15.md (finding #5, High)
commits:
  - 1b326ab fix(260615-tzk): synchronous SIGKILL sweep on app-exit (no orphans)
tests: 443 passed (440 prior + 3 new)
---

# Quick Task 260615-tzk — Summary

## Problem (Finding #5, High — violated a hard acceptance criterion)

On the app-exit/close path, `_teardown_pgid` SIGHUP'd each child process group and scheduled the
SIGKILL sweep via `GLib.timeout_add(_SIGKILL_GRACE_MS, ...)`. But closing the last window quits the
`Adw.Application` and ends the GLib main loop immediately, so the 1500ms timer **never fired** — any
SIGHUP-ignoring child group became a permanent orphan. CLAUDE.md lists "closing the window kills the
host zsh/agent with **no orphans**" as a Phase-1 hard acceptance criterion.

## Fix (`src/arduis/window.py`)

- `_teardown_pgid_now(pid) -> int | None` (staticmethod) — SIGHUP the group, return its pgid, no timer.
- `_sync_sigkill_sweep(pgids, grace_ms=_SIGKILL_GRACE_MS)` (staticmethod) — returns immediately on an
  empty set; polls in 50ms slices with early-exit the moment the live set empties (≈0 added latency in
  the common case where everything dies on SIGHUP); SIGKILLs survivors; swallows
  `ProcessLookupError`/`OSError` so it never raises out of close.
- `_teardown_session_terminals_now(task) -> list[int]` — close-path mirror returning pgids.
- `_on_close_request` now collects pgids across all projects, SIGHUPs every group, then runs ONE
  combined synchronous sweep (full grace in parallel, not serial).

The timer variants `_teardown_pgid` / `_teardown_session_terminals` are byte-identical and still used
by the hibernate/conclude paths (the main loop keeps running there, so the timer is correct).

## Test

`tests/test_window_close_orphans.py` spawns a real `start_new_session=True` child that installs a
SIGHUP-ignore handler (with a readiness handshake to avoid the install race), confirms it survives
SIGHUP, then asserts `_sync_sigkill_sweep` SIGKILLs it (negative SIGKILL exit / pgid gone). Also
asserts the empty-set fast path and the already-dead early-exit. Child reaped in a `finally`.

Deviation (Rule 1): `tests/test_window_projects.py::test_close_request_tears_down_all_projects` was
updated to stub the new close-path method `_teardown_session_terminals_now` (the close call moved to
it). Committed atomically with the fix.

## Verification
- `/tmp/arduis-venv/bin/python -m pytest` → **443 passed**, 4 pre-existing warnings, 0 failures.
- Common-case close latency unchanged (early-exit); only true SIGHUP-ignorers cost up to the grace
  window before SIGKILL — no orphans either way.

## Deferred findings still open (need PO/UX input)
#4 multi-project attention surfacing, #6 state-file namespace (low), #7 appconfig root-scalar (low).
See `.planning/CODE-REVIEW-2026-06-15.md`.
