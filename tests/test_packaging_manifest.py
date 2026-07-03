"""Guard: every .py under src/arduis/ must be listed in src/meson.build.

A module missing from py.install_sources() ships a broken .deb/AUR package
(ImportError at launch on the installed copy — exactly how layout_store.py and
the voice modules escaped 1.0.0). meson has no recursive glob, so the explicit
list in src/meson.build MUST be kept in sync by hand; this test is the sync.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
MESON = SRC / "meson.build"


def test_meson_install_sources_lists_every_module():
    on_disk = {str(p.relative_to(SRC)) for p in (SRC / "arduis").rglob("*.py")}
    listed = set(re.findall(r"'(arduis/[^']+\.py)'", MESON.read_text()))

    missing = sorted(on_disk - listed)
    stale = sorted(listed - on_disk)

    assert not missing, (
        f"Modules on disk but NOT in src/meson.build (installed package would "
        f"be broken): {missing}"
    )
    assert not stale, (
        f"src/meson.build lists files that no longer exist: {stale}"
    )
