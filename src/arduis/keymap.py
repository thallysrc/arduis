"""GTK-free tmux-style C-Space prefix keymap + pure dispatcher.

Deals in key-NAME strings (not Gdk objects), so it imports NO ``gi``. window.py
(Plans 03-04/05) matches a real ``Gdk`` keyval-name + ``CONTROL_MASK`` against the
prefix constants here, then feeds the bare action key into ``dispatch``.

Decisions:
- D-09: a tmux-style prefix (Ctrl+Space) precedes the bare action key; Phase 3
  shipped h/j/k/l (focus directions) + n/p (worktree cycle) + digit jump.
- D-10: the keymap was HARDCODED in Phase 3 and is the single GTK-free place
  Phase 5 (UI-01) wraps in config WITHOUT reshaping the dispatcher. Phase 5 has
  now ADDED the split (``-``/``=``), zoom (``z``) and refeed-agent (``a``) chords
  to ``KEYMAP`` and exposed ``DEFAULT_KEYMAP`` as the named default that
  ``keyconfig.resolve_keymap`` merges user ``[keys.bindings]`` over (closed set).
"""
from __future__ import annotations

PREFIX_KEYVAL = "space"  # Gdk keyval-name of the prefix key
PREFIX_MODS = "ctrl"     # modifier required with the prefix (Ctrl+Space)

KEYMAP: dict[str, tuple] = {
    "h": ("focus_dir", "left"),
    "j": ("focus_dir", "down"),
    "k": ("focus_dir", "up"),
    "l": ("focus_dir", "right"),
    "n": ("worktree", "next"),
    "p": ("worktree", "prev"),
    "-": ("split", "v"),         # Phase 5 (UI-01) — vertical split
    "=": ("split", "h"),         # Phase 5 (UI-01) — horizontal split
    "z": ("zoom", None),         # Phase 5 (UI-01) — zoom/unzoom the focused pane
    "a": ("refeed", None),       # Phase 5 (AGENT-01) — re-feed the agent command
}
# Named default for keyconfig.resolve_keymap (UI-01); the same object as KEYMAP.
DEFAULT_KEYMAP = KEYMAP


def dispatch(key: str) -> tuple | None:
    """Map a bare action key to an action tuple, or ``None`` for unknown keys.

    Digits "1".."9" become ``("jump", n)``; mapped keys return their KEYMAP tuple.
    The closed action set covers focus/worktree/split/zoom/refeed (Phase 5); an
    unknown key returns ``None`` so no action is ever fabricated from untrusted
    input (closed action set, T-03-03).
    """
    if len(key) == 1 and "1" <= key <= "9":
        return ("jump", int(key))
    return KEYMAP.get(key)
