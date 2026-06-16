---
quick_id: 260615-tzk
description: Fix orphan-on-close — synchronous SIGKILL sweep at app-exit
date: 2026-06-15
source: .planning/CODE-REVIEW-2026-06-15.md (finding #5, High)
tasks: 1
---

# Quick Task 260615-tzk — Plan

## Problem (Finding #5, High — violates a hard acceptance criterion)

`_teardown_pgid` (`src/arduis/window.py`, ~line 4720) sends `SIGHUP` synchronously, then schedules
the `SIGKILL` sweep via `GLib.timeout_add(_SIGKILL_GRACE_MS, self._sigkill_if_alive, pgid)`.
In `_on_close_request` the app closes the (single) window → `Adw.Application` quits → the GLib
main loop ends, so the 1500ms timer **never fires**. Any child process group that ignores or
survives SIGHUP becomes a permanent orphan. CLAUDE.md lists "closing the window kills the host
zsh/agent with **no orphans**" as a Phase-1 hard acceptance criterion, so this is a correctness
bug, not a preference. The container teardown already uses synchronous `subprocess.run` at close
for exactly this reason (see the comment near window.py:4816).

## Task 1 — Synchronous SIGKILL sweep on close

**File:** `src/arduis/window.py`, `tests/` (new or existing window test)

Add a close-path teardown that does NOT rely on the GLib timer. Keep the existing
`_teardown_pgid` (with its timer) UNCHANGED for the hibernate/conclude paths (the loop keeps
running there, so the timer is correct). Only the app-exit path needs the synchronous variant.

Implement:
1. A helper `_teardown_pgid_now(pid) -> int | None` that does `pgid = os.getpgid(pid)`,
   `os.killpg(pgid, SIGHUP)`, and RETURNS the pgid (or `None` on `ProcessLookupError`). No timer.
2. A helper `_sync_sigkill_sweep(pgids, grace_ms=_SIGKILL_GRACE_MS)` that:
   - Builds the set of live pgids (skip `None`).
   - Polls in short slices (e.g. 50ms via `time.sleep`) up to `grace_ms` total, dropping any pgid
     whose `os.killpg(pgid, 0)` raises `ProcessLookupError` (it died on SIGHUP — the common case,
     so the loop exits early when the set empties → near-zero added latency).
   - After the grace window, `os.killpg(pgid, SIGKILL)` every survivor (swallow `ProcessLookupError`).
   - Swallow `OSError` throughout; this must never raise out of close.
   - IMPORTANT: if the live set is empty up front, return immediately (no sleep) — the overwhelming
     common case is everything dies on SIGHUP, so close stays fast.
3. In `_on_close_request`: collect pgids instead of calling the timer variant. Replace the
   `self._teardown_pgid(self._shell_pid)` + per-session `_teardown_session_terminals` calls on the
   CLOSE path with collection into a `pgids` list (via `_teardown_pgid_now` for the shell and a new
   close-path variant of the terminal sweep that returns pgids), then a single
   `self._sync_sigkill_sweep(pgids)` AFTER all SIGHUPs are sent (so every group gets the full grace
   in parallel, not serially). Keep `_clear_task_state_files` and the container teardown loop as-is.
   - Simplest structure: add `_teardown_session_terminals_now(task) -> list[int]` that mirrors
     `_teardown_session_terminals` but uses `_teardown_pgid_now` and returns the pgids; aggregate
     across `self._registry.all()` → all projects → sessions (the close loop already iterates all
     projects). Do not change hibernate/conclude call sites.
   - `import time` if not already imported (it is used elsewhere in window.py — reuse).

**Test:** add `tests/test_window_close_orphans.py` (or extend an existing window test) that:
- Spawns a real child process whose process group IGNORES SIGHUP (e.g. `subprocess.Popen` of
  `python3 -c "import signal,time; signal.signal(signal.SIGHUP, signal.SIG_IGN); time.sleep(30)"`
  with `start_new_session=True` so it has its own pgid).
- Calls `_sync_sigkill_sweep([pgid], grace_ms=300)` directly (does not need a GTK window — call it
  on a bare instance via the existing `ArduisWindow.__new__` seam, or make `_sync_sigkill_sweep`
  callable without GTK state; prefer a staticmethod/free helper if that keeps the test GTK-free).
- Asserts the process is dead afterward (`os.killpg(pgid, 0)` raises `ProcessLookupError`, or
  `proc.wait(timeout=2)` returns a negative SIGKILL status).
- Also asserts the EARLY-EXIT fast path: a pgid that already died returns quickly (optional:
  assert no exception and near-zero time).
- Clean up the child in a `finally` (SIGKILL) so the test never leaks a process.

Keep the change minimal and the success/hibernate paths byte-identical.

## Verification
- `/tmp/arduis-venv/bin/python -m pytest` → all green (≥440 + new test).
- Manual reasoning: on close, everything that dies on SIGHUP adds ~0 latency; only true
  SIGHUP-ignorers cost up to the grace window, then are SIGKILLed — no orphans.
