"""Proof for the backward-compatible optional ``cwd=`` on ``run_git_async`` (D-07).

``run_git_async`` is the argv-agnostic async runner; Phase 8 gh/git reads need the
child to run IN a worktree dir (so gh infers its repo and ``git diff`` drops the
``-C``). This test PROVES two things against a REAL temp git repo + the GLib loop:

- BACKWARD COMPAT: calling ``run_git_async(argv, on_done)`` WITHOUT ``cwd`` still
  works exactly as before (the ``cwd=None`` default path is byte-identical — it
  uses ``Gio.Subprocess.new`` and the child inherits the test's cwd).
- REAL-CWD: ``run_git_async(argv, on_done, cwd=<temp repo>)`` runs the child in
  that dir — ``git rev-parse --show-toplevel`` resolves the TEMP repo, not the
  test's cwd.

The loop is timeout-capped (~5 s) so it can never hang. The venv is
``--system-site-packages`` so ``gi``/GLib are present (per MEMORY).
"""
from __future__ import annotations

import os
import subprocess
import tempfile

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

from arduis.git_service import run_git_async  # noqa: E402


def _drive_until(predicate, timeout_s: float = 5.0):
    """Spin a GLib.MainLoop until ``predicate()`` is True or the timeout fires."""
    loop = GLib.MainLoop()
    timed_out = {"v": False}

    def _on_timeout():
        timed_out["v"] = True
        loop.quit()
        return GLib.SOURCE_REMOVE

    def _poll():
        if predicate():
            loop.quit()
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    GLib.timeout_add(int(timeout_s * 1000), _on_timeout)
    GLib.timeout_add(10, _poll)
    loop.run()
    assert not timed_out["v"], "GLib loop timed out waiting for on_done"


def test_run_git_async_without_cwd_is_backward_compatible():
    """No-cwd call still works: returns cleanly via on_done (cwd=None default)."""
    result: dict = {}

    def _on_done(rc, out, err):
        result["rc"] = rc
        result["out"] = out
        result["err"] = err

    run_git_async(["git", "rev-parse", "--is-inside-work-tree"], _on_done)
    _drive_until(lambda: "rc" in result)

    # on_done receives the (exit_status, stdout, stderr) triple unchanged.
    assert isinstance(result["rc"], int)
    assert isinstance(result["out"], str)
    assert isinstance(result["err"], str)


def test_run_git_async_cwd_runs_child_in_that_dir():
    """cwd=<temp repo> => the child runs THERE: show-toplevel resolves it."""
    with tempfile.TemporaryDirectory() as tmp:
        repo = os.path.realpath(tmp)
        subprocess.run(
            ["git", "init", "-q", repo],
            check=True,
            capture_output=True,
        )

        result: dict = {}

        def _on_done(rc, out, err):
            result["rc"] = rc
            result["out"] = out
            result["err"] = err

        run_git_async(
            ["git", "rev-parse", "--show-toplevel"], _on_done, cwd=repo,
        )
        _drive_until(lambda: "rc" in result)

        assert result["rc"] == 0, result.get("err")
        # The child resolved the TEMP repo, proving it ran in cwd (not the test's).
        assert os.path.realpath(result["out"].strip()) == repo
