"""Contract tests for the GTK-free trust-gate primitives (``arduis.trust``).

Pins criterion 4 (D-07/D-09/D-10): a content hash that re-prompts on any change
(edit/add/remove/reorder), a fail-closed tolerant trust list (missing/garbage -> {},
non-str dropped), and an atomic best-effort writer that round-trips, preserves prior
entries, overwrites a changed hash, creates the parent dir, survives a non-writable
target without raising, and round-trips path keys containing /, ., -.
"""
import re

from arduis import trust
from arduis.trust import (
    is_trusted,
    load_trusted,
    record_trust,
    setup_hash,
)


def _write(tmp_path, text):
    p = tmp_path / "trusted_setups.toml"
    p.write_text(text, encoding="utf-8")
    return str(p)


# --- setup_hash (D-07) ---------------------------------------------------------
def test_hash_is_64_hex():
    assert re.fullmatch(r"[0-9a-f]{64}", setup_hash(["npm install"]))


def test_hash_stable_for_identical_lists():
    assert setup_hash(["npm install", "npm test"]) == setup_hash(["npm install", "npm test"])


def test_hash_changes_on_edit():
    assert setup_hash(["npm install"]) != setup_hash(["npm ci"])


def test_hash_changes_on_add():
    assert setup_hash(["a"]) != setup_hash(["a", "b"])


def test_hash_changes_on_remove():
    assert setup_hash(["a", "b"]) != setup_hash(["a"])


def test_hash_changes_on_reorder():
    assert setup_hash(["a", "b"]) != setup_hash(["b", "a"])


# --- load_trusted fail-closed tolerance (D-10) ---------------------------------
def test_load_missing_is_empty(tmp_path):
    assert load_trusted(str(tmp_path / "nope.toml")) == {}


def test_load_garbage_is_empty(tmp_path):
    p = _write(tmp_path, "not = = toml [[")
    assert load_trusted(p) == {}


def test_load_no_trusted_table_is_empty(tmp_path):
    p = _write(tmp_path, "[other]\nx = 1\n")
    assert load_trusted(p) == {}


def test_load_trusted_not_a_table_is_empty(tmp_path):
    p = _write(tmp_path, "trusted = 3\n")
    assert load_trusted(p) == {}


def test_load_drops_non_str_values(tmp_path):
    p = _write(tmp_path, '[trusted]\n"/r" = 5\n"/s" = "abc"\n')
    assert load_trusted(p) == {"/s": "abc"}


# --- record_trust / is_trusted round-trip (D-09/D-10) --------------------------
def test_record_round_trip_exactness(tmp_path):
    p = str(tmp_path / "trusted_setups.toml")
    record_trust(p, "/repo/a", "HASH1")
    assert is_trusted(p, "/repo/a", "HASH1") is True
    assert is_trusted(p, "/repo/a", "HASH2") is False
    assert is_trusted(p, "/repo/b", "HASH1") is False


def test_record_preserves_prior_entries(tmp_path):
    p = str(tmp_path / "trusted_setups.toml")
    record_trust(p, "/repo/a", "H1")
    record_trust(p, "/repo/b", "H2")
    loaded = load_trusted(p)
    assert loaded == {"/repo/a": "H1", "/repo/b": "H2"}


def test_record_overwrites_changed_hash(tmp_path):
    p = str(tmp_path / "trusted_setups.toml")
    record_trust(p, "/repo/a", "H1")
    record_trust(p, "/repo/a", "H2")
    assert is_trusted(p, "/repo/a", "H1") is False
    assert is_trusted(p, "/repo/a", "H2") is True


def test_record_writes_valid_toml_with_trusted_table(tmp_path):
    import tomllib

    p = str(tmp_path / "trusted_setups.toml")
    record_trust(p, "/repo/a", "H1")
    with open(p, "rb") as fh:
        data = tomllib.load(fh)
    assert "trusted" in data
    assert data["trusted"]["/repo/a"] == "H1"


def test_record_path_key_with_special_chars_round_trips(tmp_path):
    p = str(tmp_path / "trusted_setups.toml")
    record_trust(p, "/home/u/Projects/my-repo", "H")
    assert load_trusted(p)["/home/u/Projects/my-repo"] == "H"


def test_record_creates_parent_dir(tmp_path):
    p = str(tmp_path / "sub" / "trusted_setups.toml")
    record_trust(p, "/repo/a", "H")
    assert is_trusted(p, "/repo/a", "H") is True


def test_record_best_effort_swallows_oserror(tmp_path, monkeypatch):
    p = str(tmp_path / "trusted_setups.toml")

    def boom(*_a, **_k):
        raise OSError("nope")

    monkeypatch.setattr(trust.os, "replace", boom)
    record_trust(p, "/repo/a", "H")  # must not raise


# --- GTK-free ------------------------------------------------------------------
def test_trust_is_gtk_free():
    with open(trust.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
    assert "from gi" not in text
