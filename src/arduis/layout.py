"""GTK-free binary split/leaf layout tree — the single source of truth for what is visible.

This module carries ALL the layout *logic* (split / close-and-collapse / zoom /
preset / focus-or-swap) with zero GTK. The live ``GtkPaned`` tree built in
window.py (Plans 03-04/05) is a thin *reflection* of this model — no logic lives
in the widget layer. Imports NO ``gi``.

Decisions:
- D-01 / LAYOUT-01: a pure binary tree (``LeafNode`` / ``SplitNode``) is the single
  source of truth for what is visible; the GTK widgets are a view of it.
- D-02: visibility is DECOUPLED from existence — a session may be active in the
  store without being a visible leaf (``is_visible`` only checks the tree).
- D-03: ``split`` turns the focused leaf into a ``SplitNode`` with two leaves and
  focuses the new one.
- D-04: closing a leaf collapses its now-degenerate parent back to the surviving
  sibling subtree (Pitfall 2 — never leave a one-child SplitNode).
- D-06: focus-or-swap — ``resolve_selection`` returns a PURE decision: focus a
  visible id, or swap a hidden id into the focused pane.

No widgets here. This is data + decisions only.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LeafNode:
    """A single pane carrying a session_id key (no widget). None = empty leaf."""

    session_id: str | None


@dataclass
class SplitNode:
    """A binary split. ``orientation`` is "h" (side-by-side) or "v" (stacked)."""

    orientation: str
    start: "LeafNode | SplitNode"
    end: "LeafNode | SplitNode"


Node = "LeafNode | SplitNode"


@dataclass
class LayoutModel:
    """The mutable layout tree + focus + MRU focus order + zoom snapshot."""

    root: LeafNode | SplitNode | None = None
    focused_id: str | None = None
    _mru: list[str] = field(default_factory=list)
    _pre_zoom: LeafNode | SplitNode | None = None

    # --- tree mutation ---------------------------------------------------

    def split(self, session_id: str, new_session_id: str, orientation: str = "h") -> None:
        """Replace the leaf showing ``session_id`` with a SplitNode of two leaves (D-03)."""
        replacement = SplitNode(orientation, LeafNode(session_id), LeafNode(new_session_id))
        if isinstance(self.root, LeafNode) and self.root.session_id == session_id:
            self.root = replacement
        else:
            self._replace_leaf_node(self.root, session_id, replacement)
        self.focused_id = new_session_id
        self.touch(new_session_id)

    def close_leaf(self, session_id: str) -> None:
        """Remove the leaf for ``session_id``; collapse the degenerate parent (D-04, Pitfall 2)."""
        if isinstance(self.root, LeafNode):
            if self.root.session_id == session_id:
                self.root = None
            # Fall through to the shared cleanup so closing the LAST pane also
            # drops the dead id from _mru and resets focused_id (no early return).
        else:
            self.root = self._remove_from(self.root, session_id)
        if self._mru and session_id in self._mru:
            self._mru.remove(session_id)
        if self.focused_id == session_id:
            visible = self.visible_ids()
            self.focused_id = visible[0] if visible else None

    def _remove_from(self, node: LeafNode | SplitNode | None, session_id: str) -> LeafNode | SplitNode | None:
        """Return ``node`` with the matching leaf removed, collapsing degenerate splits."""
        if node is None or isinstance(node, LeafNode):
            return node
        # node is a SplitNode
        if isinstance(node.start, LeafNode) and node.start.session_id == session_id:
            return node.end  # collapse: surviving sibling replaces the split
        if isinstance(node.end, LeafNode) and node.end.session_id == session_id:
            return node.start
        node.start = self._remove_from(node.start, session_id)
        node.end = self._remove_from(node.end, session_id)
        return node

    def _replace_leaf_node(
        self,
        node: LeafNode | SplitNode | None,
        session_id: str,
        replacement: LeafNode | SplitNode,
    ) -> bool:
        """Find the leaf for ``session_id`` and swap it for ``replacement`` in place."""
        if node is None or isinstance(node, LeafNode):
            return False
        if isinstance(node.start, LeafNode) and node.start.session_id == session_id:
            node.start = replacement
            return True
        if isinstance(node.end, LeafNode) and node.end.session_id == session_id:
            node.end = replacement
            return True
        return self._replace_leaf_node(node.start, session_id, replacement) or \
            self._replace_leaf_node(node.end, session_id, replacement)

    # --- visibility (D-02) ----------------------------------------------

    def visible_ids(self) -> list[str]:
        """In-order walk of the tree, returning each non-empty leaf's session_id."""
        out: list[str] = []
        self._collect(self.root, out)
        return out

    def _collect(self, node: LeafNode | SplitNode | None, out: list[str]) -> None:
        if node is None:
            return
        if isinstance(node, LeafNode):
            if node.session_id is not None:
                out.append(node.session_id)
            return
        self._collect(node.start, out)
        self._collect(node.end, out)

    def is_visible(self, session_id: str) -> bool:
        """True iff ``session_id`` is a leaf in the current tree (decoupled from store, D-02)."""
        return session_id in self.visible_ids()

    def set_leaf_session(self, target_id: str, new_id: str) -> None:
        """Swap the session_id carried by the leaf showing ``target_id`` (or focused) to ``new_id`` (D-06)."""
        if not self._set_leaf(self.root, target_id, new_id) and self.focused_id is not None:
            self._set_leaf(self.root, self.focused_id, new_id)
        self.focused_id = new_id
        self.touch(new_id)

    def _set_leaf(self, node: LeafNode | SplitNode | None, target_id: str, new_id: str) -> bool:
        if node is None:
            return False
        if isinstance(node, LeafNode):
            if node.session_id == target_id:
                node.session_id = new_id
                return True
            return False
        return self._set_leaf(node.start, target_id, new_id) or \
            self._set_leaf(node.end, target_id, new_id)

    # --- zoom ------------------------------------------------------------

    def zoom(self, session_id: str) -> None:
        """Snapshot the tree, then show only ``session_id`` as the sole leaf."""
        self._pre_zoom = self.root
        self.root = LeafNode(session_id)
        self.focused_id = session_id

    def unzoom(self) -> None:
        """Restore the pre-zoom tree (no-op if not zoomed)."""
        if self._pre_zoom is not None:
            self.root = self._pre_zoom
            self._pre_zoom = None

    def is_zoomed(self) -> bool:
        return self._pre_zoom is not None

    # --- presets (D-04) --------------------------------------------------

    def preset(self, kind: str, session_ids: list[str]) -> None:
        """Build a fresh balanced tree from the MRU-ordered subset of ``session_ids`` (D-04)."""
        self._pre_zoom = None
        mru_first = [sid for sid in self.mru_order() if sid in session_ids]
        # include any ids not yet in the MRU list, preserving call order
        for sid in session_ids:
            if sid not in mru_first:
                mru_first.append(sid)

        if kind == "grid2x2":
            cells = mru_first[:4]
            leaves = [LeafNode(c) for c in cells]
            while len(leaves) < 4:
                leaves.append(LeafNode(None))
            a, b, c, d = leaves
            self.root = SplitNode("v", SplitNode("h", a, b), SplitNode("h", c, d))
        elif kind == "columns":
            cells = mru_first[: len(session_ids)]
            self.root = self._right_chain([LeafNode(c) for c in cells], "h")
        else:
            cells = mru_first[: len(session_ids)]
            self.root = self._right_chain([LeafNode(c) for c in cells], "h")

        visible = self.visible_ids()
        if visible:
            self.focused_id = visible[0]

    def _right_chain(self, leaves: list[LeafNode], orientation: str) -> LeafNode | SplitNode | None:
        """Build a right-leaning chain of SplitNodes from a list of leaves."""
        if not leaves:
            return None
        if len(leaves) == 1:
            return leaves[0]
        return SplitNode(orientation, leaves[0], self._right_chain(leaves[1:], orientation))

    # --- MRU focus order -------------------------------------------------

    def touch(self, session_id: str) -> None:
        """Move ``session_id`` to the front of the MRU list (most-recent first)."""
        if session_id in self._mru:
            self._mru.remove(session_id)
        self._mru.insert(0, session_id)

    def mru_order(self) -> list[str]:
        """The MRU focus order, most-recent first."""
        return list(self._mru)


def resolve_selection(model: LayoutModel, session_id: str) -> tuple[str, str]:
    """Pure focus-or-swap decision (D-06).

    Returns ``("focus", session_id)`` if the id has a visible pane, else
    ``("swap", model.focused_id)`` — the hidden id should be swapped into the
    currently focused pane. No GTK; window.py acts on this decision.
    """
    if model.is_visible(session_id):
        return ("focus", session_id)
    return ("swap", model.focused_id)
