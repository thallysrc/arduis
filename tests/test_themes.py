"""Tests for the GTK-free theme registry (UI-02, D-06).

Pins the contracts window.py (Plan 03) depends on BEFORE any wiring exists:
- the closed 4-theme registry keyed by slug,
- the get_theme whitelist degrading to Dracula (T-05-03),
- the 16-color / valid-hex invariants protecting Vte.Terminal.set_colors (Pitfall 6),
- Dracula being byte-identical to theme.py so the default look never shifts,
- the module being GTK-free (no gi import) so the whole suite runs without GTK/Vte,
- Theme being a frozen (immutable/hashable) dataclass.
"""
import dataclasses
import re

import pytest

from arduis import theme
from arduis.themes import DRACULA, PARALLEL_DARK, THEMES, Theme, get_theme

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Every non-palette color field a Theme carries (the set_colors / CSS contract).
_COLOR_FIELDS = (
    "bg",
    "fg",
    "cursor",
    "surface",
    "accent",
    "branch",
    "dot_active",
    "dot_waiting",
    "dot_ready",
    "dot_idle",
    "dot_hibernated",
)


def test_registry_keys_are_exactly_the_five_slugs():
    assert set(THEMES) == {
        "dracula", "nord", "solarized-dark", "gruvbox-dark", "parallel-dark"
    }
    assert len(THEMES) == 5


def test_get_theme_none_falls_back_to_parallel_dark():
    assert get_theme(None) is PARALLEL_DARK


def test_get_theme_empty_falls_back_to_parallel_dark():
    assert get_theme("") is PARALLEL_DARK


def test_get_theme_unknown_falls_back_to_parallel_dark():
    assert get_theme("nope") is PARALLEL_DARK


def test_get_theme_is_case_insensitive_on_the_slug():
    assert get_theme("DRACULA") is DRACULA
    assert get_theme("Nord") is THEMES["nord"]


def test_get_theme_known_slug_returns_that_theme():
    assert get_theme("nord") is THEMES["nord"]
    assert get_theme("solarized-dark") is THEMES["solarized-dark"]
    assert get_theme("gruvbox-dark") is THEMES["gruvbox-dark"]


def test_each_theme_name_equals_its_registry_key():
    for slug, t in THEMES.items():
        assert t.name == slug, f"{slug!r} theme has name {t.name!r}"


def test_every_theme_has_exactly_16_palette_colors():
    # Vte.Terminal.set_colors only accepts palette sizes {0, 8, 16, 232, 256};
    # the registry pins 16 (Pitfall 6).
    for slug, t in THEMES.items():
        assert len(t.palette) == 16, f"{slug!r} palette has {len(t.palette)} colors"


def test_every_color_field_is_a_parseable_hex_string():
    # Proves set_colors / Gdk.RGBA.parse will accept every value (no gi needed).
    for slug, t in THEMES.items():
        for field in _COLOR_FIELDS:
            value = getattr(t, field)
            assert _HEX.match(value), f"{slug!r}.{field} is not #rrggbb: {value!r}"
        for i, entry in enumerate(t.palette):
            assert _HEX.match(entry), f"{slug!r}.palette[{i}] is not #rrggbb: {entry!r}"


def test_every_theme_has_a_nonempty_display_name():
    for slug, t in THEMES.items():
        assert isinstance(t.display_name, str)
        assert t.display_name.strip(), f"{slug!r} has empty display_name"


def test_dracula_is_byte_identical_to_theme_py():
    # The default look must never shift: DRACULA imports the theme.py constants.
    assert DRACULA.bg == theme.DRACULA_BG
    assert DRACULA.fg == theme.DRACULA_FG
    assert DRACULA.cursor == theme.DRACULA_CURSOR
    assert list(DRACULA.palette) == theme.DRACULA_PALETTE


def test_module_is_gtk_free():
    import arduis.themes

    source = open(arduis.themes.__file__).read()
    assert "import gi" not in source
    assert "from gi" not in source


def test_theme_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        DRACULA.bg = "#000000"  # type: ignore[misc]
