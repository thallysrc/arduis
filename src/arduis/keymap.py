"""GTK-free tmux-style C-Space prefix keymap + pure dispatcher.

Deals in key-NAME strings (not Gdk objects), so it imports NO ``gi``. window.py
(Plans 03-04/05) matches a real ``Gdk`` keyval-name + ``CONTROL_MASK`` against the
prefix constants here, then feeds the bare action key into ``dispatch``.

Decisions:
- D-09: a tmux-style prefix (Ctrl+Space) precedes the bare action key; Phase 3
  ships h/j/k/l (focus directions) + n/p (worktree cycle) + digit jump. Split and
  zoom chords are deliberately NOT in the map yet.
- D-10: the keymap is HARDCODED in Phase 3. These constants are the single
  GTK-free place Phase 5 (UI-01) will wrap in config WITHOUT reshaping the
  dispatcher — keep all key tables here.
"""
from __future__ import annotations

PREFIX_KEYVAL = "space"  # Gdk keyval-name of the prefix key
PREFIX_MODS = "ctrl"     # modifier required with the prefix (Ctrl+Space)

KEYMAP: dict[str, tuple[str, str]] = {
    "h": ("focus_dir", "left"),
    "j": ("focus_dir", "down"),
    "k": ("focus_dir", "up"),
    "l": ("focus_dir", "right"),
    "n": ("worktree", "next"),
    "p": ("worktree", "prev"),
}


def dispatch(key: str) -> tuple | None:
    """Map a bare action key to an action tuple, or ``None`` for unknown keys.

    Digits "1".."9" become ``("jump", n)``; mapped keys return their KEYMAP tuple.
    Split/zoom chords are Phase 5 (D-09/D-10) — unknown keys return ``None`` so no
    action is ever fabricated from untrusted input (closed action set, T-03-03).
    """
    if len(key) == 1 and "1" <= key <= "9":
        return ("jump", int(key))
    return KEYMAP.get(key)
