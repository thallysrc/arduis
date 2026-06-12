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


def build_worktree_spawn(
    runner: HostRunner, extra_env: list[str] | None = None
) -> tuple[list[str], list[str]]:
    """Assemble the (argv, envv) for a per-worktree shell, routed through the seam.

    Same shell/env as ``build_spawn_command`` — the cwd differs per worktree but
    is a ``spawn_async`` argument, NOT part of argv, so this reuses
    ``SHELL_ARGV``/``TERM_ENV``. The separate name documents intent (the
    worktree-tab spawn path, WT-03) and gives a unit-test handle distinct from
    tab 0's Phase-1 ``build_spawn_command``.

    ``extra_env`` (Phase 4, STATUS-01/D-01): per-terminal additions such as
    ``ARDUIS_STATE_FILE=...`` and ``ARDUIS_SESSION_META=<term_id>``. VTE's
    ``spawn_async`` envv is ADDITIVE to the inherited environment (Phase-1
    empirically proven), so these ride alongside HOME/PATH/etc. A NEW list is
    returned — ``TERM_ENV`` is never mutated.

    Threat T-01-01/T-01-02: still list literals through the seam — env entries
    are discrete "KEY=value" strings, never joined into a shell string; argv is
    untouched regardless of ``extra_env``. No ``flatpak-spawn`` prefix in v1.
    """
    envv = TERM_ENV + (extra_env or [])
    return runner.wrap_argv(SHELL_ARGV), runner.wrap_env(envv)
