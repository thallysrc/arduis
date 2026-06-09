"""Tests for the GTK-free Dracula palette (D-06)."""
import re

from arduis import theme

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def test_palette_has_exactly_16_entries():
    # Valid Vte.Terminal.set_colors palette size: {0, 8, 16, 232, 256}.
    assert len(theme.DRACULA_PALETTE) == 16


def test_all_palette_entries_are_hex():
    for entry in theme.DRACULA_PALETTE:
        assert _HEX.match(entry), f"not a hex color: {entry!r}"


def test_fg_bg_cursor_are_hex():
    for entry in (theme.DRACULA_FG, theme.DRACULA_BG, theme.DRACULA_CURSOR):
        assert _HEX.match(entry), f"not a hex color: {entry!r}"
