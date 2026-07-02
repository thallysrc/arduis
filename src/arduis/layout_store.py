"""GTK-free persistence for per-project workspace pane layouts. Imports NO gi.

Companion to ``projects_store.py`` (which persists project roots). This module
owns ``layouts.json`` — the live split tree, per-pane kind/cwd, split ratios, and
focus per workspace — so the pane grid returns identical after an app restart.

The recursive (de)serialization of the ``arduis.layout`` tree lives here (it is the
one place that knows both node shapes); ``layout.py`` stays pure layout logic.

Mirrors ``projects_store``: atomic temp+rename write (a torn write never corrupts
the file) and tolerant load (bad json / not-a-dict / missing → empty snapshot).
"""
from __future__ import annotations

import json
import os
import tempfile

from arduis.layout import LeafNode, SplitNode

# Schema version of layouts.json — bump to migrate the on-disk shape.
_VERSION = 1


def tree_to_dict(node) -> dict | None:
    """Serialize a layout node recursively to a plain dict (None -> None)."""
    if node is None:
        return None
    if isinstance(node, LeafNode):
        return {"leaf": node.session_id}
    if isinstance(node, SplitNode):
        return {
            "split": node.orientation,
            "ratio": node.ratio,
            "start": tree_to_dict(node.start),
            "end": tree_to_dict(node.end),
        }
    return None


def tree_from_dict(d):
    """Rebuild a layout node from a dict; tolerant (garbage -> None)."""
    if not isinstance(d, dict):
        return None
    if "leaf" in d:
        return LeafNode(d.get("leaf"))
    if "split" in d:
        start = tree_from_dict(d.get("start"))
        end = tree_from_dict(d.get("end"))
        if start is None or end is None:
            return None
        try:
            ratio = float(d.get("ratio", 0.5))
        except (TypeError, ValueError):
            ratio = 0.5
        return SplitNode(d["split"], start, end, ratio=ratio)
    return None


def leaf_ids(node) -> list[str]:
    """In-order list of non-None leaf session ids under ``node``."""
    out: list[str] = []
    _collect(node, out)
    return out


def _collect(node, out: list[str]) -> None:
    if isinstance(node, LeafNode):
        if node.session_id is not None:
            out.append(node.session_id)
    elif isinstance(node, SplitNode):
        _collect(node.start, out)
        _collect(node.end, out)


def save_layouts(path: str, snapshot: dict) -> None:
    """Atomically persist the layouts snapshot (best-effort, mirrors save_projects).

    A mid-write failure unlinks the temp and leaves the original intact; an
    uncreatable parent / read-only dir is swallowed.
    """
    try:
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".arduis-layouts-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(snapshot, fh, indent=2)
            os.replace(tmp, path)  # atomic
        except (OSError, ValueError, TypeError):
            try:
                os.unlink(tmp)
            except OSError:
                pass
    except OSError:
        pass  # best-effort persistence (mirrors projects_store.save_projects)


def load_layouts(path: str) -> dict:
    """Tolerant load; always returns a dict with a ``projects`` dict.

    Bad json / not-a-dict / missing file -> ``{"version": 1, "projects": {}}``.
    """
    empty = {"version": _VERSION, "projects": {}}
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return empty
    if not isinstance(data, dict):
        return empty
    projects = data.get("projects")
    if not isinstance(projects, dict):
        data["projects"] = {}
    data.setdefault("version", _VERSION)
    return data
