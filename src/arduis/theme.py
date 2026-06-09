"""Dracula palette constants (D-06).

GTK-free on purpose: these are plain hex strings. The Gdk.RGBA conversion
lives in the GTK layer (Plan 02), so this module imports no ``gi``/``Gdk``
and the whole Plan-01 suite runs without importing GTK/Vte.
"""

# Paleta Dracula (a mesma do tmux/nvim do usuário), lifted from src/main.py.
DRACULA_BG = "#282a36"
DRACULA_FG = "#f8f8f2"
DRACULA_CURSOR = "#f8f8f2"
DRACULA_PALETTE = [
    "#21222c", "#ff5555", "#50fa7b", "#f1fa8c",
    "#bd93f9", "#ff79c6", "#8be9fd", "#f8f8f2",
    "#6272a4", "#ff6e6e", "#69ff94", "#ffffa5",
    "#d6acff", "#ff92df", "#a4ffff", "#ffffff",
]
