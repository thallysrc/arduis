"""GTK-free theme registry (UI-02, D-06).

A frozen Theme dataclass carrying the full VTE palette (bg/fg/cursor + 16 ANSI
colors) AND the UI colors window._CSS hardcodes (surface/accent/branch + 5 status
dots). window.py (Plan 03) converts these hex strings to Gdk.RGBA at apply time, so
this module imports NO gi/Gdk and the whole suite runs without GTK/Vte.

Ship 4 DARK themes (so libadwaita FORCE_DARK stays consistent): dracula (default,
palette imported verbatim from theme.py), nord, solarized-dark, gruvbox-dark. The
non-Dracula hex tables come from 05-RESEARCH §DESIGN (a wrong shade is cosmetic —
Pitfall 6's parse guard + the valid-hex unit test prevent a crash).

get_theme(name) is a dict WHITELIST returning DRACULA for any unknown/None/empty
name (T-05-03: the name is never used as a filesystem path).
"""
from __future__ import annotations

from dataclasses import dataclass

from arduis.theme import (
    DRACULA_BG,
    DRACULA_CURSOR,
    DRACULA_FG,
    DRACULA_PALETTE,
)


@dataclass(frozen=True)
class Theme:
    name: str                 # slug, e.g. "solarized-dark"
    display_name: str         # menu label, e.g. "Solarized Dark"
    bg: str
    fg: str
    cursor: str
    palette: tuple[str, ...]  # EXACTLY 16 ANSI colors (set_colors contract)
    # UI colors window._CSS hardcodes (Dracula values are the existing look):
    surface: str              # _BG2  — sidebar/header/pane-header background
    accent: str               # _FOCUS_RING — focus ring + badge + hint-key
    branch: str               # _BRANCH_PINK — pane-header branch label
    dot_active: str           # _DOT_ACTIVE (green / running)
    dot_waiting: str          # _DOT_WAITING (orange — THE attention dot)
    dot_ready: str            # _DOT_READY (cyan)
    dot_idle: str             # _DOT_IDLE (muted grey-green)
    dot_hibernated: str       # _DOT_HIBERNATED (grey / ended)


DRACULA = Theme(
    name="dracula",
    display_name="Dracula",
    bg=DRACULA_BG,
    fg=DRACULA_FG,
    cursor=DRACULA_CURSOR,
    palette=tuple(DRACULA_PALETTE),
    surface="#21222c",
    accent="#bd93f9",
    branch="#ff79c6",
    dot_active="#50fa7b",
    dot_waiting="#ffb86c",
    dot_ready="#8be9fd",
    dot_idle="#7a9e7e",
    dot_hibernated="#6272a4",
)

NORD = Theme(
    name="nord",
    display_name="Nord",
    bg="#2e3440", fg="#d8dee9", cursor="#d8dee9",
    palette=(
        "#3b4252", "#bf616a", "#a3be8c", "#ebcb8b",
        "#81a1c1", "#b48ead", "#88c0d0", "#e5e9f0",
        "#4c566a", "#bf616a", "#a3be8c", "#ebcb8b",
        "#81a1c1", "#b48ead", "#8fbcbb", "#eceff4",
    ),
    surface="#3b4252", accent="#88c0d0", branch="#b48ead",
    dot_active="#a3be8c", dot_waiting="#d08770", dot_ready="#88c0d0",
    dot_idle="#8fbcbb", dot_hibernated="#4c566a",
)

SOLARIZED_DARK = Theme(
    name="solarized-dark",
    display_name="Solarized Dark",
    bg="#002b36", fg="#839496", cursor="#93a1a1",
    palette=(
        "#073642", "#dc322f", "#859900", "#b58900",
        "#268bd2", "#d33682", "#2aa198", "#eee8d5",
        "#002b36", "#cb4b16", "#586e75", "#657b83",
        "#839496", "#6c71c4", "#93a1a1", "#fdf6e3",
    ),
    surface="#073642", accent="#268bd2", branch="#d33682",
    dot_active="#859900", dot_waiting="#cb4b16", dot_ready="#2aa198",
    dot_idle="#586e75", dot_hibernated="#073642",
)

GRUVBOX_DARK = Theme(
    name="gruvbox-dark",
    display_name="Gruvbox Dark",
    bg="#282828", fg="#ebdbb2", cursor="#ebdbb2",
    palette=(
        "#282828", "#cc241d", "#98971a", "#d79921",
        "#458588", "#b16286", "#689d6a", "#a89984",
        "#928374", "#fb4934", "#b8bb26", "#fabd2f",
        "#83a598", "#d3869b", "#8ec07c", "#ebdbb2",
    ),
    surface="#3c3836", accent="#83a598", branch="#d3869b",
    dot_active="#98971a", dot_waiting="#fe8019", dot_ready="#8ec07c",
    dot_idle="#689d6a", dot_hibernated="#504945",
)

THEMES: dict[str, Theme] = {
    "dracula": DRACULA,
    "nord": NORD,
    "solarized-dark": SOLARIZED_DARK,
    "gruvbox-dark": GRUVBOX_DARK,
}


def get_theme(name: str | None) -> Theme:
    """Return the Theme for ``name`` (slug), or DRACULA for any unknown/None/empty.

    A dict whitelist — the name is NEVER used to build a filesystem path (T-05-03).
    Case-insensitive on the slug.
    """
    return THEMES.get((name or "dracula").lower(), DRACULA)
