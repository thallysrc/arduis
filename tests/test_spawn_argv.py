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
