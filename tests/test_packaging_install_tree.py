"""DIST-02/03: meson DESTDIR install tree + importlib.resources hook smoke.

Runs ``meson setup`` + ``meson install --destdir <tmp>`` and asserts the
install tree is correct: a ``usr/bin/arduis`` executable, the hicolor SVG, and
that the staged ``arduis`` package is importable AND its packaged hook is
readable via ``importlib.resources`` (Pitfall 1).

The whole test is skip-guarded: it is a no-op skip until ``meson.build`` lands
in Plan 02 (and also skips if the ``meson`` toolchain is not installed), then
becomes the real install-tree gate.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
MESON_BUILD = REPO_ROOT / "meson.build"
ICON_REL = "io.github.thallys.Arduis.svg"


def _require_meson_project():
    if not MESON_BUILD.exists():
        pytest.skip("meson.build not present yet (lands in Plan 02)")
    if shutil.which("meson") is None:
        pytest.skip("meson toolchain not installed (apt install meson ninja-build)")


def test_meson_install_tree(tmp_path):
    _require_meson_project()

    builddir = tmp_path / "build"
    stage = tmp_path / "stage"

    subprocess.run(
        ["meson", "setup", str(builddir), str(REPO_ROOT)],
        check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["meson", "install", "-C", str(builddir), "--destdir", str(stage)],
        check=True, capture_output=True, text=True,
    )

    # (a) launcher on PATH and executable
    launcher = stage / "usr" / "bin" / "arduis"
    assert launcher.is_file(), f"missing launcher {launcher}"
    import os
    assert os.access(launcher, os.X_OK), "launcher not executable"

    # (b) hicolor scalable icon installed
    icons = list(stage.rglob(f"icons/hicolor/scalable/apps/{ICON_REL}"))
    assert icons, f"icon {ICON_REL} not found under hicolor scalable path in stage"

    # (c) staged arduis package importable + packaged hook readable (Pitfall 1)
    purelibs = list(stage.rglob("arduis/__init__.py"))
    assert purelibs, "arduis package not installed into the stage"
    site_root = purelibs[0].parents[1]  # .../site-packages
    code = (
        "import importlib.resources, arduis.hooks; "
        "print(importlib.resources.files('arduis.hooks')"
        ".joinpath('arduis_hook.py').read_text()[:1])"
    )
    env = {"PYTHONPATH": str(site_root), "PATH": "/usr/bin:/bin"}
    res = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env,
    )
    assert res.returncode == 0, f"importlib.resources hook load failed: {res.stderr}"
