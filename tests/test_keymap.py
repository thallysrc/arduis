"""RED contract tests for the GTK-free prefix keymap (``arduis.keymap``).

Pins the dispatch contract Plan 03-02 must satisfy. Fails now (RED) because
``arduis.keymap`` does not exist yet.

Decisions pinned:
- D-09: a tmux-style prefix (C-Space) precedes the bare action key.
- D-10: the Phase-3 keymap (h/j/k/l focus, n/p cycle, digit jump) is now extended
  by Phase 5 (UI-01) with the split (``-``/``=``), zoom (``z``) and refeed (``a``)
  chords, and exposes ``DEFAULT_KEYMAP`` for the config layer. An unmapped key
  (e.g. ``q``) still dispatches to None (closed action set).
"""
from arduis import keymap
from arduis.keymap import (
    DEFAULT_KEYMAP,
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


def test_dispatch_split():
    # Phase 5 (UI-01): '-' vertical split, '=' horizontal split.
    assert dispatch("-") == ("split", "v")
    assert dispatch("=") == ("split", "h")


def test_dispatch_zoom():
    # Phase 5 (UI-01): 'z' zooms/unzooms the focused pane.
    assert dispatch("z") == ("zoom", None)


def test_dispatch_refeed():
    # Phase 5 (AGENT-01): 'a' re-feeds the configured agent command.
    assert dispatch("a") == ("refeed", None)


def test_default_keymap_alias():
    # keyconfig merges over keymap.DEFAULT_KEYMAP — the same object as KEYMAP.
    assert DEFAULT_KEYMAP is KEYMAP
    for key in ("-", "=", "z", "a"):
        assert key in KEYMAP


def test_dispatch_unknown():
    # Closed action set: a genuinely-unmapped key dispatches to None.
    # (Was 'z' in Phase 3; 'z' is now zoom — the planned Phase-3->5 change.)
    assert dispatch("q") is None
    assert "q" not in KEYMAP


def test_keymap_is_gtk_free():
    with open(keymap.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
