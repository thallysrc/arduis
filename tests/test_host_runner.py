"""Tests for the HostRunner seam (T-01-03: Flatpak stub unreachable in v1)."""
import pytest

from arduis.host_runner import HostRunner


def test_native_noop_argv_is_identity_new_list():
    runner = HostRunner()
    argv = ["zsh", "-l", "-i"]
    result = runner.wrap_argv(argv)
    assert result == ["zsh", "-l", "-i"]
    # Must be a NEW list so callers cannot mutate internals.
    assert result is not argv


def test_native_noop_env_is_identity_new_list():
    runner = HostRunner()
    env = ["TERM=xterm-256color"]
    result = runner.wrap_env(env)
    assert result == ["TERM=xterm-256color"]
    assert result is not env


def test_flatpak_stub_argv_raises(monkeypatch):
    monkeypatch.setattr("arduis.host_runner._FLATPAK", True)
    with pytest.raises(NotImplementedError):
        HostRunner().wrap_argv(["zsh", "-l", "-i"])


def test_flatpak_stub_env_raises(monkeypatch):
    monkeypatch.setattr("arduis.host_runner._FLATPAK", True)
    with pytest.raises(NotImplementedError):
        HostRunner().wrap_env(["TERM=xterm-256color"])
