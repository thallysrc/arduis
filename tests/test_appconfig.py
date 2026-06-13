"""Contract tests for the GTK-free [theme] config (``arduis.appconfig``).

Pins UI-02 (D-09): tolerant ``[theme] name`` read with a "dracula" default, and an
atomic section-preserving ``write_theme`` (tmp + os.replace, no tomli-w dependency)
that never corrupts arduis.toml or drops another section (T-05-04).
"""
import glob
import os
import tomllib

from arduis import appconfig
from arduis.attention import load_config
from arduis.appconfig import load_theme_name, write_theme


def _write(tmp_path, text, name="arduis.toml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# --- load_theme_name -----------------------------------------------------------
def test_load_missing_default(tmp_path):
    assert load_theme_name(str(tmp_path / "nope.toml")) == "dracula"


def test_load_name(tmp_path):
    p = _write(tmp_path, '[theme]\nname = "nord"\n')
    assert load_theme_name(p) == "nord"


def test_load_non_str_default(tmp_path):
    p = _write(tmp_path, "[theme]\nname = 123\n")
    assert load_theme_name(p) == "dracula"


def test_load_empty_default(tmp_path):
    p = _write(tmp_path, '[theme]\nname = ""\n')
    assert load_theme_name(p) == "dracula"


def test_load_invalid_toml_default(tmp_path):
    p = _write(tmp_path, "[theme]\nname = not valid =")
    assert load_theme_name(p) == "dracula"


def test_load_missing_section_default(tmp_path):
    p = _write(tmp_path, "[attention]\nidle_minutes = 5\n")
    assert load_theme_name(p) == "dracula"


# --- write_theme round-trip ----------------------------------------------------
def test_write_round_trip(tmp_path):
    p = str(tmp_path / "arduis.toml")
    write_theme(p, "nord")
    assert load_theme_name(p) == "nord"


def test_write_overwrites_not_appends(tmp_path):
    p = str(tmp_path / "arduis.toml")
    write_theme(p, "nord")
    write_theme(p, "gruvbox-dark")
    assert load_theme_name(p) == "gruvbox-dark"
    # only one name persists (overwrite, not duplicate)
    with open(p, "rb") as fh:
        data = tomllib.load(fh)
    assert data["theme"]["name"] == "gruvbox-dark"


def test_write_new_file(tmp_path):
    p = str(tmp_path / "fresh.toml")
    write_theme(p, "nord")
    with open(p, "rb") as fh:
        data = tomllib.load(fh)
    assert data == {"theme": {"name": "nord"}}


# --- section preservation (T-05-04) --------------------------------------------
def test_write_preserves_other_sections(tmp_path):
    seed = (
        "[attention]\n"
        "auto_suspend_minutes = 5\n\n"
        '[agent]\n'
        'command = "aider"\n\n'
        '[keys]\n'
        'prefix = "ctrl+b"\n\n'
        '[keys.bindings]\n'
        '"z" = "zoom"\n'
    )
    p = _write(tmp_path, seed)
    write_theme(p, "nord")

    with open(p, "rb") as fh:
        data = tomllib.load(fh)
    assert data["attention"]["auto_suspend_minutes"] == 5
    assert data["agent"]["command"] == "aider"
    assert data["keys"]["prefix"] == "ctrl+b"
    assert data["keys"]["bindings"]["z"] == "zoom"
    assert data["theme"]["name"] == "nord"


def test_rewritten_file_readable_by_attention_loader(tmp_path):
    seed = "[attention]\nauto_suspend_minutes = 5\nidle_minutes = 7\n"
    p = _write(tmp_path, seed)
    write_theme(p, "nord")
    cfg = load_config(p)
    assert cfg.auto_suspend_minutes == 5
    assert cfg.idle_minutes == 7


# --- atomicity / resilience ----------------------------------------------------
def test_write_leaves_no_tmp_file(tmp_path):
    p = str(tmp_path / "arduis.toml")
    write_theme(p, "nord")
    leftovers = glob.glob(str(tmp_path / ".*")) + glob.glob(str(tmp_path / "*.tmp"))
    # the persisted file itself is not a dotfile/tmp; no mkstemp leftover remains.
    assert leftovers == []


def test_write_uncreatable_parent_does_not_raise(tmp_path):
    # a path whose parent is a FILE (cannot be made a dir) -> OSError swallowed.
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    p = str(blocker / "sub" / "arduis.toml")
    write_theme(p, "nord")  # must not raise


# --- GTK-free ------------------------------------------------------------------
def test_appconfig_is_gtk_free():
    with open(appconfig.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
    assert "from gi" not in text
