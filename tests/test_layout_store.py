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


# --- GTK-free guard ----------------------------------------------------------
def test_module_imports_no_gi():
    with open(layout_store.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
    assert not hasattr(layout_store, "gi")
