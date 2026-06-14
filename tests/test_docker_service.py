"""Unit coverage for the docker-compose async wrapper (CONT-05, D-08).

``docker_service`` imports gi/Gtk (the venv has system-site-packages, so this is
fine, same as any gi-importing module). To pin argv ROUTING + the on_done shape
WITHOUT spawning a real process (the real spawn is exercised by the Plan-05 host
smoke/UAT), we:

- pass a FAKE runner whose ``wrap_argv`` records the argv and returns a sentinel
  wrapped list, proving every compose call crosses the HostRunner seam (T-07-08);
- monkeypatch ``docker_service.Gio.Subprocess.new`` to a stub that captures the
  wrapped argv + flags and returns a fake proc whose ``communicate_utf8_async``
  immediately invokes the callback with a canned ``(True, "out", "")`` —
  asserting ``on_done`` fires with the decoded ``(exit_status, stdout, stderr)``.

The single untestable line (the real ``Gio.Subprocess.new`` host spawn) is the
Plan-05 smoke's job.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio

from arduis import docker_service


class _FakeRunner:
    """Records the argv passed to wrap_argv; returns a sentinel wrapped list."""

    def __init__(self):
        self.seen: list[str] | None = None

    def wrap_argv(self, argv: list[str]) -> list[str]:
        self.seen = list(argv)
        return ["WRAPPED", *argv]


class _FakeProc:
    """A fake Gio.Subprocess: fires the callback synchronously with canned output."""

    def __init__(self):
        self.exit_status = 0

    def communicate_utf8_async(self, stdin, cancellable, cb):
        cb(self, object())  # res is opaque — finish ignores it

    def communicate_utf8_finish(self, res):
        return (True, "out", "")

    def get_exit_status(self):
        return self.exit_status


def test_run_compose_async_routes_argv_through_seam_and_fires_on_done(monkeypatch):
    captured: dict = {}

    def _fake_new(wrapped_argv, flags):
        captured["argv"] = wrapped_argv
        captured["flags"] = flags
        return _FakeProc()

    monkeypatch.setattr(docker_service.Gio.Subprocess, "new", staticmethod(_fake_new))

    runner = _FakeRunner()
    results: list[tuple] = []
    argv = ["docker", "compose", "ls"]

    docker_service.run_compose_async(
        argv, lambda rc, out, err: results.append((rc, out, err)), runner=runner
    )

    # 1. argv crossed the HostRunner seam unchanged (the exact list).
    assert runner.seen == ["docker", "compose", "ls"]

    # 2. Gio.Subprocess.new got the WRAPPED argv (seam output), with both pipes.
    assert captured["argv"] == ["WRAPPED", "docker", "compose", "ls"]
    assert captured["flags"] == (
        Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
    )

    # 3. on_done fired with the decoded (exit_status, stdout, stderr) shape.
    assert results == [(0, "out", "")]


def test_run_compose_async_defaults_to_real_hostrunner(monkeypatch):
    """With no runner injected, a real HostRunner is used (no-op native: identity)."""
    captured: dict = {}

    def _fake_new(wrapped_argv, flags):
        captured["argv"] = wrapped_argv
        return _FakeProc()

    monkeypatch.setattr(docker_service.Gio.Subprocess, "new", staticmethod(_fake_new))

    argv = ["docker", "compose", "-p", "arduis-x", "up", "-d"]
    docker_service.run_compose_async(argv, lambda rc, out, err: None)

    # Native HostRunner is a no-op identity wrap → argv unchanged.
    assert captured["argv"] == argv
    assert captured["argv"] is not argv  # a NEW list (wrap_argv returns list(argv))
