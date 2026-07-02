"""Contract tests for the GTK-free layout persistence store (``arduis.layout_store``)."""
import glob
import json
import sys

from arduis.layout import LeafNode, SplitNode
from arduis import layout_store


# --- tree (de)serialization --------------------------------------------------
def test_leaf_round_trip():
    node = LeafNode("main:t0")
    d = layout_store.tree_to_dict(node)
    assert d == {"leaf": "main:t0"}
    back = layout_store.tree_from_dict(d)
    assert isinstance(back, LeafNode)
    assert back.session_id == "main:t0"


def test_nested_split_round_trip_preserves_ratio_and_orientation():
    tree = SplitNode(
        "h",
        LeafNode("main:t0"),
        SplitNode("v", LeafNode("main:t1"), LeafNode("main:t2"), ratio=0.3),
        ratio=0.7,
    )
    back = layout_store.tree_from_dict(layout_store.tree_to_dict(tree))
    assert isinstance(back, SplitNode)
    assert back.orientation == "h"
    assert back.ratio == 0.7
    assert isinstance(back.end, SplitNode)
    assert back.end.ratio == 0.3
    assert back.end.start.session_id == "main:t1"
    assert back.end.end.session_id == "main:t2"


def test_tree_to_dict_none():
    assert layout_store.tree_to_dict(None) is None


def test_tree_from_dict_tolerant_of_garbage():
    assert layout_store.tree_from_dict(None) is None
    assert layout_store.tree_from_dict({}) is None
    assert layout_store.tree_from_dict({"bogus": 1}) is None


def test_tree_from_dict_missing_ratio_defaults_half():
    tree = layout_store.tree_from_dict(
        {"split": "v", "start": {"leaf": "a"}, "end": {"leaf": "b"}}
    )
    assert isinstance(tree, SplitNode)
    assert tree.ratio == 0.5


def test_leaf_ids_in_order():
    tree = SplitNode(
        "h",
        LeafNode("a"),
        SplitNode("v", LeafNode("b"), LeafNode("c")),
    )
    assert layout_store.leaf_ids(tree) == ["a", "b", "c"]


def test_leaf_ids_skips_none_and_handles_none_tree():
    assert layout_store.leaf_ids(None) == []
    assert layout_store.leaf_ids(LeafNode(None)) == []


# --- file I/O: round trip ----------------------------------------------------
def _sample_snapshot():
    return {
        "version": 1,
        "projects": {
            "/home/u/proj": {
                "workspaces": {
                    "main": {
                        "focused_id": "main:t1",
                        "tree": {
                            "split": "v", "ratio": 0.5,
                            "start": {"leaf": "main:t0"},
                            "end": {"leaf": "main:t1"},
                        },
                        "leaves": {
                            "main:t0": {"kind": "shell", "cwd": "/home/u/proj"},
                            "main:t1": {"kind": "agent", "cwd": "/home/u/proj"},
                        },
                    }
                }
            }
        },
    }


def test_save_then_load_round_trip(tmp_path):
    path = str(tmp_path / "layouts.json")
    snap = _sample_snapshot()
    layout_store.save_layouts(path, snap)
    assert layout_store.load_layouts(path) == snap


def test_load_missing_file_returns_empty(tmp_path):
    out = layout_store.load_layouts(str(tmp_path / "nope.json"))
    assert out == {"version": 1, "projects": {}}


def test_load_bad_json_returns_empty(tmp_path):
    path = tmp_path / "layouts.json"
    path.write_text("{not json", encoding="utf-8")
    out = layout_store.load_layouts(str(path))
    assert out == {"version": 1, "projects": {}}


def test_load_not_a_dict_returns_empty(tmp_path):
    path = tmp_path / "layouts.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    out = layout_store.load_layouts(str(path))
    assert out == {"version": 1, "projects": {}}


def test_load_missing_projects_key_returns_empty_projects(tmp_path):
    path = tmp_path / "layouts.json"
    path.write_text('{"version": 1}', encoding="utf-8")
    out = layout_store.load_layouts(str(path))
    assert out["projects"] == {}


# --- atomicity (mirrors projects_store) --------------------------------------
def test_atomic_write_no_partial_on_failure(tmp_path, monkeypatch):
    path = str(tmp_path / "layouts.json")
    layout_store.save_layouts(path, _sample_snapshot())
    original = open(path, encoding="utf-8").read()

    def boom(*args, **kwargs):
        raise OSError("disk full mid-write")

    monkeypatch.setattr(json, "dump", boom)
    layout_store.save_layouts(path, {"version": 1, "projects": {}})  # must NOT raise

    assert open(path, encoding="utf-8").read() == original
    assert glob.glob(str(tmp_path / ".arduis-layouts-*")) == []


def test_save_leaves_no_tmp_on_success(tmp_path):
    path = str(tmp_path / "layouts.json")
    layout_store.save_layouts(path, _sample_snapshot())
    assert glob.glob(str(tmp_path / ".arduis-layouts-*")) == []


def test_save_uncreatable_parent_does_not_raise(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    path = str(blocker / "sub" / "layouts.json")
    layout_store.save_layouts(path, _sample_snapshot())  # must not raise


# --- GTK-free guard ----------------------------------------------------------
def test_module_imports_no_gi():
    with open(layout_store.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
    assert not hasattr(layout_store, "gi")
