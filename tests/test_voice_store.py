"""voice_store.py — persisted spoken-prompt history (GTK-free, atomic JSON)."""
import json
import os

from arduis import voice_store


def _path(tmp_path):
    return str(tmp_path / "voice_history.json")


def test_load_missing_file_returns_empty(tmp_path):
    assert voice_store.load_history(_path(tmp_path)) == []


def test_append_then_load_round_trip(tmp_path):
    p = _path(tmp_path)
    entries = voice_store.append_entry(p, "fix the login bug", "2026-07-02T10:00:00")
    assert entries == [{"text": "fix the login bug", "ts": "2026-07-02T10:00:00", "count": 1}]
    assert voice_store.load_history(p) == entries


def test_newest_first(tmp_path):
    p = _path(tmp_path)
    voice_store.append_entry(p, "first", "2026-07-02T10:00:00")
    entries = voice_store.append_entry(p, "second", "2026-07-02T10:01:00")
    assert [e["text"] for e in entries] == ["second", "first"]


def test_repeat_text_moves_to_top_and_bumps_count(tmp_path):
    p = _path(tmp_path)
    voice_store.append_entry(p, "run the tests", "2026-07-02T10:00:00")
    voice_store.append_entry(p, "other", "2026-07-02T10:01:00")
    entries = voice_store.append_entry(p, "run the tests", "2026-07-02T10:02:00")
    assert [e["text"] for e in entries] == ["run the tests", "other"]
    assert entries[0]["count"] == 2
    assert entries[0]["ts"] == "2026-07-02T10:02:00"  # ts refreshed on reuse


def test_cap_trims_oldest(tmp_path):
    p = _path(tmp_path)
    for i in range(5):
        voice_store.append_entry(p, f"prompt {i}", f"2026-07-02T10:0{i}:00", cap=3)
    entries = voice_store.load_history(p)
    assert [e["text"] for e in entries] == ["prompt 4", "prompt 3", "prompt 2"]


def test_garbage_file_degrades_to_empty(tmp_path):
    p = _path(tmp_path)
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("{not json!!")
    assert voice_store.load_history(p) == []
    # and append still works on top of the garbage
    entries = voice_store.append_entry(p, "recovered", "2026-07-02T10:00:00")
    assert [e["text"] for e in entries] == ["recovered"]


def test_non_dict_document_degrades_to_empty(tmp_path):
    p = _path(tmp_path)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump([1, 2, 3], fh)
    assert voice_store.load_history(p) == []


def test_bad_entries_skipped(tmp_path):
    p = _path(tmp_path)
    doc = {
        "version": 1,
        "prompts": [
            {"text": "good", "ts": "2026-07-02T10:00:00", "count": 1},
            {"ts": "no text"},
            "not a dict",
            {"text": 42, "ts": "wrong type", "count": 1},
        ],
    }
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(doc, fh)
    entries = voice_store.load_history(p)
    assert [e["text"] for e in entries] == ["good"]


def test_no_stray_temp_files_after_write(tmp_path):
    p = _path(tmp_path)
    voice_store.append_entry(p, "clean", "2026-07-02T10:00:00")
    assert os.listdir(tmp_path) == ["voice_history.json"]


def test_creates_parent_dir(tmp_path):
    p = str(tmp_path / "nested" / "voice_history.json")
    entries = voice_store.append_entry(p, "hello", "2026-07-02T10:00:00")
    assert [e["text"] for e in entries] == ["hello"]
    assert voice_store.load_history(p) == entries
