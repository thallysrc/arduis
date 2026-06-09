"""Async git runner — the one new gi-importing SERVICE module (thin).

This executes the list-form argv built by the GTK-free ``worktree.py`` off the
GTK main loop via ``Gio.Subprocess`` and hands back parsed strings on the main
loop, so the ``on_done`` callback may safely mutate widgets / ``SessionStore``.

It is deliberately tiny: it builds nothing and parses nothing — ``worktree.py``
owns argv construction and ``window.py`` owns orchestration. argv route through
``HostRunner`` (the single host-execution funnel, no-op on native builds).

Threats:
- T-02-01 (tampering/EoP): argv arrive as Python lists from the tested
  ``worktree.py`` and are passed to ``Gio.Subprocess.new`` — there is no shell,
  no ``shell=True``, and the branch stays a discrete argv element.

Concurrency (CLAUDE.md): ``Gio.Subprocess`` + ``communicate_utf8_async`` on the
GLib main loop — never a blocking call on the GTK loop, and NEVER threading /
asyncio (mixing two event loops in a GTK app is a footgun).
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from arduis.host_runner import HostRunner  # noqa: E402


def run_git_async(argv: list[str], on_done, runner: HostRunner | None = None) -> None:
    """Run a git argv off the GTK loop; ``on_done(exit_status, stdout, stderr)``.

    The callback fires on the GLib main loop, so it is safe to mutate widgets /
    the ``SessionStore`` directly from it. argv route through ``HostRunner`` so
    the v2 Flatpak path has a single home.
    """
    wrapped = (runner or HostRunner()).wrap_argv(argv)  # route through the seam
    proc = Gio.Subprocess.new(
        wrapped,
        Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
    )

    def _cb(p, res):
        ok, out, err = p.communicate_utf8_finish(res)
        on_done(p.get_exit_status(), out or "", err or "")

    proc.communicate_utf8_async(None, None, _cb)
