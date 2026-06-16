"""RED contract tests for the GTK-free layout tree (``arduis.layout``).

These pin the exact behavioral contract that Plan 03-02 must satisfy. They fail
now (RED) because ``arduis.layout`` does not exist yet — a ``ModuleNotFoundError``
at import counts as RED.

Decisions pinned:
- D-01 / LAYOUT-01: a pure binary layout tree (``LeafNode``/``SplitNode``) is the
  single source of truth for what is visible; the GTK widgets are a view of it.
- D-02: visibility is DECOUPLED from existence — a session may be active in the
  store without being a visible leaf.
- D-03: ``split`` turns the focused leaf into a ``SplitNode`` with two leaves.
- D-04: closing a leaf collapses its now-degenerate parent (Pitfall 2).
- D-06: focus-or-swap — selecting a visible id focuses it; selecting a hidden id
  swaps it into the focused pane (a PURE decision, no GTK).
- zoom/unzoom save and restore the whole tree; presets pick from MRU focus order.
"""
from arduis import layout
from arduis.layout import (
    LayoutModel,
    LeafNode,
    SplitNode,
    resolve_selection,
)


def _leaf_ids(model: LayoutModel) -> set[str]:
    return set(model.visible_ids())


def test_split_focused():
    # D-03: a single leaf "a", split into "a"/"b" horizontally -> SplitNode root.
    model = LayoutModel()
    model.root = LeafNode("a")
    model.focused_id = "a"
    model.split("a", "b", "h")
    assert isinstance(model.root, SplitNode)
    assert model.root.orientation == "h"
    assert _leaf_ids(model) == {"a", "b"}
    assert sorted(model.visible_ids()) == ["a", "b"]


def test_close_collapses():
    # D-04 / Pitfall 2: closing "b" collapses the degenerate parent back to Leaf("a").
    model = LayoutModel()
    model.root = SplitNode("h", LeafNode("a"), LeafNode("b"))
    model.focused_id = "a"
    model.close_leaf("b")
    assert isinstance(model.root, LeafNode)
    assert model.root.session_id == "a"
    assert model.visible_ids() == ["a"]


def test_zoom_roundtrip():
    # zoom saves the tree and shows only one leaf; unzoom restores it.
    model = LayoutModel()
    model.root = SplitNode("h", LeafNode("a"), LeafNode("b"))
    model.focused_id = "a"
    model.zoom("a")
    assert model.is_zoomed() is True
    assert model.visible_ids() == ["a"]
    model.unzoom()
    assert model.is_zoomed() is False
    assert _leaf_ids(model) == {"a", "b"}


def test_preset_subset():
    # preset draws panes from the MRU order; grid2x2 -> 4 leaves, columns honors count.
    model = LayoutModel()
    model.root = LeafNode("a")
    model.focused_id = "a"
    for sid in ("a", "b", "c", "d", "e"):
        model.touch(sid)
    model.preset("grid2x2", ["a", "b", "c", "d", "e"])
    visible = model.visible_ids()
    assert len(visible) == 4
    # the four shown are the first four of the MRU order
    assert set(visible) == set(model.mru_order()[:4])

    model.preset("columns", ["a", "b", "c"])
    assert len(model.visible_ids()) == 3


def test_visibility_decoupled():
    # D-02: an id that exists in the store but is NOT a leaf is not visible.
    model = LayoutModel()
    model.root = SplitNode("h", LeafNode("a"), LeafNode("b"))
    model.focused_id = "a"
    assert model.is_visible("a") is True
    assert model.is_visible("b") is True
    assert model.is_visible("c") is False  # active in store, no visible pane


def test_focus_or_swap():
    # D-06: visible id -> ("focus", id); hidden id -> ("swap", focused_id). Pure.
    model = LayoutModel()
    model.root = SplitNode("h", LeafNode("a"), LeafNode("b"))
    model.focused_id = "a"
    assert resolve_selection(model, "b") == ("focus", "b")
    assert resolve_selection(model, "z") == ("swap", "a")


def test_three_terminal_split_keeps_all_visible():
    # Regression (UAT Failure 1): splitting a 2-terminal workspace a second time
    # (focused on the left leaf) must keep ALL THREE terminals visible — the model
    # must NOT drop a leaf. The narrow-single-column symptom was a GTK paned-position
    # bug in the reflection layer, not a model defect; this pins the model contract.
    model = LayoutModel()
    model.root = LeafNode("feat:t0")
    model.focused_id = "feat:t0"
    model.touch("feat:t0")
    model.split("feat:t0", "feat:t1", "h")  # eager 2-terminal default
    model.focused_id = "feat:t0"
    model.split("feat:t0", "feat:t2", "h")  # user splits again from the left pane
    assert set(model.visible_ids()) == {"feat:t0", "feat:t1", "feat:t2"}
    assert isinstance(model.root, SplitNode)


def test_close_every_terminal_empties_the_tree():
    # Regression (UAT Failure 2): closing terminals one by one must collapse cleanly
    # and end with an EMPTY tree (root is None) — the window then falls back to the
    # main workspace so the canvas is never left blank. Pins the empty-tree contract.
    model = LayoutModel()
    model.root = LeafNode("feat:t0")
    model.focused_id = "feat:t0"
    model.touch("feat:t0")
    model.split("feat:t0", "feat:t1", "h")
    model.close_leaf("feat:t1")
    assert model.visible_ids() == ["feat:t0"]
    model.close_leaf("feat:t0")
    assert model.visible_ids() == []
    assert model.root is None


def test_close_last_leaf_clears_focus_and_mru():
    # Finding #2: closing the LAST pane (single-leaf root) must run the SAME
    # cleanup as the non-root path — drop the dead id from MRU and reset
    # focused_id — not early-return and leave stale references behind.
    model = LayoutModel()
    model.root = LeafNode("solo")
    model.focused_id = "solo"
    model.touch("solo")
    assert "solo" in model.mru_order()

    model.close_leaf("solo")

    assert model.root is None
    assert model.focused_id is None
    assert "solo" not in model.mru_order()
    assert model.visible_ids() == []


def test_layout_is_gtk_free():
    # the domain module must not import gi (mirror test_session pattern).
    with open(layout.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
