"""Criterion-4: HostRunner is a native no-op (no live flatpak-spawn in v1).

Packaging is native-only in v1 (CLAUDE.md). The HostRunner seam must wrap argv
as identity and the Flatpak flag must be off. A repo grep guards against any
LIVE ``flatpak-spawn`` token sneaking into argv anywhere in ``src/`` — only
comment/docstring mentions and the dead ``if _FLATPAK:`` branch are allowed.
"""
from __future__ import annotations

import io
import tokenize
from pathlib import Path

from arduis import host_runner

SRC_DIR = Path(__file__).resolve().parents[1] / "src" / "arduis"


def test_flatpak_disabled():
    """The single v2 re-enable flag stays off in v1."""
    assert host_runner._FLATPAK is False


def test_wrap_argv_is_identity():
    """wrap_argv returns argv unchanged (no flatpak-spawn prefix)."""
    r = host_runner.HostRunner()
    assert r.wrap_argv(["zsh", "-l", "-i"]) == ["zsh", "-l", "-i"]


def test_wrap_argv_returns_copy():
    """wrap_argv returns a fresh list, not the caller's reference."""
    r = host_runner.HostRunner()
    argv = ["zsh", "-l", "-i"]
    out = r.wrap_argv(argv)
    assert out == argv
    assert out is not argv


def test_wrap_env_is_identity():
    """wrap_env returns env unchanged on native."""
    r = host_runner.HostRunner()
    env = ["TERM=xterm-256color", "FOO=bar"]
    assert r.wrap_env(env) == env


def _string_and_comment_lines(source: str) -> set[int]:
    """Line numbers (1-based) any part of which is a STRING or COMMENT token.

    Uses the tokenizer so docstrings, quoted literals, and ``#`` comments are
    identified robustly — far more reliable than substring heuristics.
    """
    lines: set[int] = set()
    toks = tokenize.generate_tokens(io.StringIO(source).readline)
    for tok in toks:
        if tok.type in (tokenize.STRING, tokenize.COMMENT) or (
            hasattr(tokenize, "FSTRING_MIDDLE") and tok.type == tokenize.FSTRING_MIDDLE
        ):
            for ln in range(tok.start[0], tok.end[0] + 1):
                lines.add(ln)
    return lines


def test_no_live_flatpak_spawn_in_src():
    """No reachable ``flatpak-spawn`` token anywhere under src/arduis.

    Every existing mention is in a docstring/comment (research-confirmed) or the
    dead ``if _FLATPAK:`` branch (a quoted list literal — a STRING token). A
    match on a non-string, non-comment line would be LIVE code and must fail.
    """
    offenders: list[str] = []
    for py in sorted(SRC_DIR.rglob("*.py")):
        source = py.read_text(encoding="utf-8")
        non_code = _string_and_comment_lines(source)
        for n, line in enumerate(source.splitlines(), 1):
            if "flatpak-spawn" in line and n not in non_code:
                offenders.append(f"{py.relative_to(SRC_DIR.parent)}:{n}: {line.strip()}")
    assert offenders == [], "live flatpak-spawn found:\n" + "\n".join(offenders)
