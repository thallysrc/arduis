"""Async docker-compose runner — the one new gi-importing SERVICE module (thin).

This executes the list-form argv built by the GTK-free ``compose.py`` (Wave 1)
off the GTK main loop via ``Gio.Subprocess`` and hands back parsed strings on
the GLib main loop, so the ``on_done`` callback may safely mutate widgets /
``SessionStore`` and ``json.loads`` the ``config``/``ls`` output.

It is the SINGLE async boundary for every ``docker compose`` call (CONT-05,
D-08): a near-verbatim clone of ``git_service.run_git_async`` — the only line it
adds over git_service is the function name. It is deliberately tiny: it builds
nothing and parses nothing — ``compose.py`` owns argv construction (up/down/
config/ls) and ``window.py`` (Wave 3) owns orchestration (the ``on_done`` does
the ``json.loads`` for config/ls). argv route through ``HostRunner`` (the single
host-execution funnel, no-op on native builds) so the v2 Flatpak path has a
single home — no ``flatpak-spawn`` prefix on native.

Threats (see 07-03-PLAN threat register):
- T-07-08 (tampering/EoP): argv arrive as Python lists from the tested
  ``compose.py`` and are passed to ``Gio.Subprocess.new`` — there is no shell,
  no ``shell=True``, and nothing is joined. Identical posture to git_service
  T-02-01. Pinned by the argv-routing test.

Concurrency (CLAUDE.md / Pitfall 3): ``docker compose up -d`` can block for
minutes on a first image pull. This wrapper uses ``Gio.Subprocess`` +
``communicate_utf8_async`` on the GLib main loop — never a blocking
``subprocess.run`` on the GTK loop, and NEVER threading / asyncio (mixing two
event loops in a GTK app is a footgun). The clone of git_service guarantees this
by construction (T-07-09).
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import Gio  # noqa: E402

from arduis.host_runner import HostRunner  # noqa: E402


def run_compose_async(argv: list[str], on_done, runner: HostRunner | None = None) -> None:
    """Run a docker-compose argv off the GTK loop; ``on_done(exit_status, stdout, stderr)``.

    The callback fires on the GLib main loop, so it is safe to mutate widgets /
    the ``SessionStore`` and ``json.loads`` the output directly from it. argv
    route through ``HostRunner`` so the v2 Flatpak path has a single home.
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
