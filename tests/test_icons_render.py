"""Guard: every shipped SVG icon must be loadable by gdk-pixbuf.

gdk-pixbuf sniffs the file head to detect the SVG format; a large comment
block between the XML declaration and <svg> pushes the tag out of the sniff
window and the icon silently renders as NOTHING (blank launcher tile — how
the 1.0.0 app icon shipped invisible). Loading each icon here catches any
variant of that class before it reaches a package.
"""

from pathlib import Path

import pytest

gi = pytest.importorskip("gi")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib  # noqa: E402

ICONS_DIR = Path(__file__).resolve().parent.parent / "data" / "icons"
ICONS = sorted(ICONS_DIR.rglob("*.svg"))


def test_icons_exist():
    assert ICONS, f"no shipped icons found under {ICONS_DIR}"


@pytest.mark.parametrize("icon", ICONS, ids=lambda p: p.name)
def test_icon_loads_in_gdk_pixbuf(icon):
    try:
        pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(str(icon), 64, 64)
    except GLib.GError as err:
        pytest.fail(
            f"{icon.relative_to(ICONS_DIR)} is not loadable by gdk-pixbuf "
            f"(would ship as a BLANK icon): {err}"
        )
    assert pixbuf.get_width() > 0
