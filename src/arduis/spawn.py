"""GTK-free spawn argv/env builder routed through HostRunner.

This is the GTK-free assembly of the (argv, envv) pair that Plan 02's GTK
layer feeds to ``Vte.Terminal.spawn_async``. It routes through HostRunner so
the v2 Flatpak path has a single home (D-04/D-05) and carries NO
``flatpak-spawn --host`` prefix in v1 (D-02/D-15).

Threat T-01-01/T-01-02: argv/env are list literals; there is no ``shell=True``
path and nothing is joined into a shell string.
"""
from __future__ import annotations

from arduis.host_runner import HostRunner

SHELL_ARGV: list[str] = ["zsh", "-l", "-i"]      # D-09 login + interactive
TERM_ENV: list[str] = ["TERM=xterm-256color"]    # D-10


def build_spawn_command(runner: HostRunner) -> tuple[list[str], list[str]]:
    """Assemble the (argv, envv) for the host shell, routed through the seam.

    Returns ``(wrapped_argv, wrapped_env)``. On native builds this is the
    identity pair; under a future Flatpak build the seam owns the rewrite.
    """
    return runner.wrap_argv(SHELL_ARGV), runner.wrap_env(TERM_ENV)
