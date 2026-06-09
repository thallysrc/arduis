"""RED contract tests for the GTK-free prefix keymap (``arduis.keymap``).

Pins the dispatch contract Plan 03-02 must satisfy. Fails now (RED) because
``arduis.keymap`` does not exist yet.

Decisions pinned:
- D-09: a tmux-style prefix (C-Space) precedes the bare action key.
- D-10: the keymap is HARDCODED in Phase 3 (Phase 5 makes it configurable):
  h/j/k/l focus directions, n/p cycle worktrees, digits jump, all else is None.
  Split/zoom chords are deliberately NOT in the map yet (Phase 5).
"""
from arduis import keymap
from arduis.keymap import (
    KEYMAP,
    PREFIX_KEYVAL,
    PREFIX_MODS,
    dispatch,
)


def test_prefix_constants():
    # D-09: the prefix is Ctrl+Space.
    assert PREFIX_KEYVAL == "space"
    assert PREFIX_MODS == "ctrl"


def test_dispatch_directions():
    # h/j/k/l -> focus_dir left/down/up/right (vim-style).
    assert dispatch("h") == ("focus_dir", "left")
    assert dispatch("j") == ("focus_dir", "down")
    assert dispatch("k") == ("focus_dir", "up")
    assert dispatch("l") == ("focus_dir", "right")


def test_dispatch_worktree_cycle():
    # n/p cycle the worktree selection.
    assert dispatch("n") == ("worktree", "next")
    assert dispatch("p") == ("worktree", "prev")


def test_dispatch_digit_jump():
    # digits 1..9 jump to the nth pane.
    assert dispatch("3") == ("jump", 3)
    assert dispatch("9") == ("jump", 9)


def test_dispatch_unknown():
    # D-10: split/zoom chords are Phase 5 — NOT in KEYMAP now -> None.
    assert dispatch("z") is None
    assert "z" not in KEYMAP


def test_keymap_is_gtk_free():
    with open(keymap.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
