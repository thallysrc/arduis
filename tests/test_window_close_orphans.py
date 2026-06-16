"""Regression lock for the app-exit (close) no-orphan SIGKILL sweep (Finding #5, High).

`_teardown_pgid` schedules its SIGKILL via ``GLib.timeout_add`` — fine for the
hibernate/conclude paths (their loop keeps running), but on the CLOSE path the GLib
main loop ends the instant the last window closes, so that timer NEVER fires. Any child
process group that ignores/survives SIGHUP then becomes a permanent orphan, violating
CLAUDE.md's Phase-1 "closing the window kills the host zsh/agent with no orphans" bar.

The fix is ``_sync_sigkill_sweep`` (a staticmethod → callable WITHOUT a GTK display):
SIGHUP every group first, then synchronously poll + SIGKILL survivors. These tests
exercise the REAL behavior with a real SIGHUP-ignoring process group:

  - a process group that IGNORES SIGHUP is force-killed by the sweep (no orphan);
  - the empty-set fast path returns immediately (near-zero added latency on the common
    case where everything died on SIGHUP).
"""
import os
import signal
import subprocess
import time

import arduis.window as W


# A child that puts itself in its OWN session/pgid (start_new_session=True) and
# explicitly IGNORES SIGHUP, then sleeps. SIGHUP alone will NOT kill it — only the
# sweep's SIGKILL will. This is the genuine orphan-risk case. It prints a readiness
# token AFTER installing the handler so the parent can avoid the startup race where
# SIGHUP arrives before SIG_IGN is in place.
_IGNORE_SIGHUP_SRC = (
    "import signal, sys, time; "
    "signal.signal(signal.SIGHUP, signal.SIG_IGN); "
    "sys.stdout.write('ready\\n'); sys.stdout.flush(); "
    "time.sleep(30)"
)


def _spawn_sighup_ignorer() -> subprocess.Popen:
    proc = subprocess.Popen(
        ["python3", "-c", _IGNORE_SIGHUP_SRC],
        start_new_session=True,  # own process group → killpg(pgid, ...) targets only it
        stdout=subprocess.PIPE,
        text=True,
    )
    # Block until the child confirms its SIGHUP handler is installed (no race).
    line = proc.stdout.readline()
    assert line.strip() == "ready", f"child failed to signal readiness: {line!r}"
    return proc


def _pgid_alive(pgid: int) -> bool:
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def test_sync_sweep_sigkills_a_sighup_ignoring_group():
    """A real SIGHUP-ignoring group must be SIGKILLed by the synchronous sweep."""
    proc = _spawn_sighup_ignorer()
    pgid = os.getpgid(proc.pid)
    try:
        # Sanity: SIGHUP does NOT kill it (it ignores SIGHUP).
        os.killpg(pgid, signal.SIGHUP)
        time.sleep(0.1)
        assert proc.poll() is None, "child should survive SIGHUP (it ignores it)"

        # The sweep must force-kill the survivor within the grace window.
        W.ArduisWindow._sync_sigkill_sweep([pgid], grace_ms=300)

        # Reap and assert it died by SIGKILL → no orphan.
        rc = proc.wait(timeout=2)
        assert rc == -signal.SIGKILL, f"expected SIGKILL, got rc={rc}"
        assert not _pgid_alive(pgid), "process group must be gone after the sweep"
    finally:
        # Never leak a process even if an assertion fails mid-test.
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            pass


def test_sync_sweep_empty_set_returns_immediately():
    """The empty live-set fast path must return at once (no sleep, no raise)."""
    start = time.monotonic()
    # None entries (already-gone groups from _teardown_pgid_now) are skipped.
    W.ArduisWindow._sync_sigkill_sweep([None, None], grace_ms=5000)
    elapsed = time.monotonic() - start
    assert elapsed < 0.05, f"empty-set sweep must be near-instant, took {elapsed:.3f}s"


def test_sync_sweep_already_dead_group_is_fast_and_quiet():
    """A group that already died (SIGHUP'd default-disposition child) → fast early-exit."""
    proc = subprocess.Popen(
        ["python3", "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    pgid = os.getpgid(proc.pid)
    try:
        # Default disposition: SIGHUP terminates it.
        os.killpg(pgid, signal.SIGHUP)
        proc.wait(timeout=2)
        assert not _pgid_alive(pgid)

        start = time.monotonic()
        W.ArduisWindow._sync_sigkill_sweep([pgid], grace_ms=5000)  # must not raise
        elapsed = time.monotonic() - start
        # One 50ms poll slice detects death and exits early — well under the grace.
        assert elapsed < 0.2, f"dead-group sweep should early-exit, took {elapsed:.3f}s"
    finally:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            pass
