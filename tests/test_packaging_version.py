"""D-03: version is single-sourced as 1.0.0.

The AppStream metainfo must declare exactly one ``<release version="1.0.0">``.
Once Plan 02 lands ``meson.build``, the meson ``project(... version: ...)``
string must equal the metainfo release version — that half skips cleanly until
``meson.build`` exists so this file is green NOW and tightens after Plan 02.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
METAINFO = REPO_ROOT / "data" / "io.github.thallys.Arduis.metainfo.xml"
MESON_BUILD = REPO_ROOT / "meson.build"

EXPECTED_VERSION = "1.0.0"


def _metainfo_release_versions() -> list[str]:
    root = ET.parse(METAINFO).getroot()
    return [r.get("version") for r in root.findall("./releases/release")]


def test_metainfo_has_exactly_one_release():
    versions = _metainfo_release_versions()
    assert versions == [EXPECTED_VERSION], (
        f"expected exactly one <release version={EXPECTED_VERSION!r}>, got {versions}"
    )


def test_metainfo_has_homepage_url():
    """D-04 upstream URL present (needed for appstream validation)."""
    root = ET.parse(METAINFO).getroot()
    urls = {u.get("type"): (u.text or "").strip() for u in root.iterfind("url")}
    assert urls.get("homepage") == "https://github.com/thallysrc/arduis"


def test_meson_version_matches_metainfo():
    """meson project version == metainfo release (skips until Plan 02 lands meson.build)."""
    if not MESON_BUILD.exists():
        pytest.skip("meson.build not present yet (lands in Plan 02)")
    text = MESON_BUILD.read_text(encoding="utf-8")
    m = re.search(r"project\([^)]*version\s*:\s*['\"]([^'\"]+)['\"]", text, re.DOTALL)
    assert m is not None, "could not parse project(... version: ...) from meson.build"
    assert m.group(1) == EXPECTED_VERSION
    assert _metainfo_release_versions() == [m.group(1)]
