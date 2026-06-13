"""Contract tests for the GTK-free [keys] config layer (``arduis.keyconfig``).

Pins UI-01 (D-04/D-05): a configurable prefix parsed to ``(keyval, mods)`` and a
flat char->action-name bindings map merged over ``keymap.DEFAULT_KEYMAP`` through a
CLOSED action set (unknown action names / bad keys dropped, mirroring dispatch->None).
"""
from arduis import keyconfig
from arduis.keymap import DEFAULT_KEYMAP
from arduis.keyconfig import resolve_keymap, resolve_prefix


# --- resolve_prefix ------------------------------------------------------------
def test_prefix_none_default():
    assert resolve_prefix(None) == ("space", "ctrl")


def test_prefix_ctrl_space():
    assert resolve_prefix("ctrl+space") == ("space", "ctrl")


def test_prefix_ctrl_b():
    assert resolve_prefix("ctrl+b") == ("b", "ctrl")


def test_prefix_case_insensitive():
    assert resolve_prefix("CTRL+B") == ("b", "ctrl")


def test_prefix_garbage_default():
    assert resolve_prefix("garbage") == ("space", "ctrl")


def test_prefix_unsupported_mod_default():
    assert resolve_prefix("alt+x") == ("space", "ctrl")


def test_prefix_empty_default():
    assert resolve_prefix("") == ("space", "ctrl")


def test_prefix_no_plus_default():
    assert resolve_prefix("space") == ("space", "ctrl")


# --- resolve_keymap ------------------------------------------------------------
def test_keymap_none_is_defaults_copy():
    result = resolve_keymap(None)
    assert result == dict(DEFAULT_KEYMAP)
    assert result is not DEFAULT_KEYMAP  # a copy, not the live default object


def test_keymap_bind_default_key():
    result = resolve_keymap({"-": "split_v"})
    assert result["-"] == ("split", "v")
    # every other default left intact
    assert result["h"] == ("focus_dir", "left")
    assert result["n"] == ("worktree", "next")


def test_keymap_bind_new_key():
    result = resolve_keymap({"x": "focus_left"})
    assert result["x"] == ("focus_dir", "left")


def test_keymap_rebind_default_key():
    result = resolve_keymap({"h": "worktree_next"})
    assert result["h"] == ("worktree", "next")


def test_keymap_unknown_action_dropped():
    # closed set: unknown action name leaves the key at its DEFAULT.
    result = resolve_keymap({"h": "nuke_everything"})
    assert result["h"] == ("focus_dir", "left")


def test_keymap_non_single_char_key_dropped():
    result = resolve_keymap({"toolong": "zoom"})
    assert result == dict(DEFAULT_KEYMAP)


def test_keymap_non_str_action_dropped():
    result = resolve_keymap({"z": 123})
    # z keeps its default (zoom) — the bad action is ignored.
    assert result["z"] == ("zoom", None)


def test_keymap_refeed_split_zoom_actions():
    assert resolve_keymap({"a": "refeed_agent"})["a"] == ("refeed", None)
    assert resolve_keymap({"=": "split_h"})["="] == ("split", "h")
    assert resolve_keymap({"q": "zoom"})["q"] == ("zoom", None)


# --- GTK-free ------------------------------------------------------------------
def test_keyconfig_is_gtk_free():
    with open(keyconfig.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
    assert "from gi" not in text
