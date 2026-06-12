"""Tests for the GTK-free spawn argv/env builder (D-02/D-09/D-10/D-15).

Threat T-01-01/T-01-02: argv/env are list literals routed through the seam,
never shell strings, and carry no flatpak-spawn prefix in v1.
"""
import pytest

from arduis.host_runner import HostRunner
from arduis.spawn import (
    SHELL_ARGV,
    TERM_ENV,
    build_spawn_command,
    build_worktree_spawn,
)


def test_shell_argv_is_login_interactive_zsh():
    assert SHELL_ARGV == ["zsh", "-l", "-i"]  # D-09, Pitfall 4


def test_term_env_value():
    assert TERM_ENV == ["TERM=xterm-256color"]  # D-10


def test_build_spawn_command_routes_through_seam():
    argv, env = build_spawn_command(HostRunner())
    assert argv == ["zsh", "-l", "-i"]
    assert env == ["TERM=xterm-256color"]


def test_no_flatpak_prefix_in_argv():
    argv, _ = build_spawn_command(HostRunner())
    assert "flatpak-spawn" not in argv  # D-02/D-15
    assert "--host" not in argv


def test_build_spawn_command_inherits_flatpak_stub(monkeypatch):
    monkeypatch.setattr("arduis.host_runner._FLATPAK", True)
    with pytest.raises(NotImplementedError):
        build_spawn_command(HostRunner())


def test_build_worktree_spawn_matches_shell():
    """WT-03: the per-worktree shell is the same zsh -l -i, no flatpak prefix."""
    argv, env = build_worktree_spawn(HostRunner())
    assert argv == ["zsh", "-l", "-i"]
    assert env == ["TERM=xterm-256color"]
    assert "flatpak-spawn" not in argv  # D-02/D-15
    assert "--host" not in argv


# --------------------------------------------------------------------------- #
# Phase 4 STATUS-01/D-01: per-terminal extra_env injection (additive, argv-safe)
# --------------------------------------------------------------------------- #

def test_extra_env_appended_in_order_after_term():
    """envv == TERM_ENV + extra_env, order preserved (TERM first)."""
    extra = [
        "ARDUIS_STATE_FILE=/run/user/1000/arduis/status/feat:t0.json",
        "ARDUIS_SESSION_META=feat:t0",  # D-01 name (research draft called it ARDUIS_TERM_ID)
    ]
    argv, env = build_worktree_spawn(HostRunner(), extra_env=extra)
    assert env == [
        "TERM=xterm-256color",
        "ARDUIS_STATE_FILE=/run/user/1000/arduis/status/feat:t0.json",
        "ARDUIS_SESSION_META=feat:t0",
    ]
    # argv UNCHANGED — env never leaks into argv.
    assert argv == ["zsh", "-l", "-i"]


def test_extra_env_does_not_mutate_module_term_env():
    """Calling twice with different extras must not grow the module-level TERM_ENV."""
    build_worktree_spawn(HostRunner(), extra_env=["ARDUIS_STATE_FILE=/a.json"])
    build_worktree_spawn(HostRunner(), extra_env=["ARDUIS_SESSION_META=feat:t1"])
    assert TERM_ENV == ["TERM=xterm-256color"]
    assert len(TERM_ENV) == 1


def test_extra_env_none_matches_no_arg_call():
    argv_none, env_none = build_worktree_spawn(HostRunner(), extra_env=None)
    argv_bare, env_bare = build_worktree_spawn(HostRunner())
    assert argv_none == argv_bare == ["zsh", "-l", "-i"]
    assert env_none == env_bare == ["TERM=xterm-256color"]


def test_extra_env_empty_list_matches_no_arg_call():
    argv, env = build_worktree_spawn(HostRunner(), extra_env=[])
    assert argv == ["zsh", "-l", "-i"]
    assert env == ["TERM=xterm-256color"]
