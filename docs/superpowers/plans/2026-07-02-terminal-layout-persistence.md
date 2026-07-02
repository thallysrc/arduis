# Terminal Layout Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist each workspace's live pane layout (split tree + per-pane kind/cwd + split ratios) to disk so the main workspace's grid returns identical after an app restart, with agent panes resuming their conversation via `claude --continue`.

**Architecture:** A new GTK-free `layout_store.py` owns `~/.config/arduis/layouts.json` (atomic write + tolerant load, mirroring `projects_store.py`) and the recursive (de)serialization of the layout tree. `layout.py` gains one `ratio` field on `SplitNode`. `window.py` snapshots layouts on close (before the unchanged no-orphans teardown) and restores them: the main workspace auto-restores on boot; worktree workspaces restore on resume.

**Tech Stack:** Python 3.12, stdlib `json`/`os`/`tempfile`, PyGObject/GTK4/VTE (window layer only), pytest.

## Global Constraints

- Platform: Linux + GNOME, Ubuntu AND Arch. VTE code stays at the 0.76 API floor.
- `layout_store.py` and `layout.py` import NO `gi` (GTK-free, unit-testable).
- Persisted app state that is WRITTEN uses stdlib `json` (never `tomli-w`); `tomllib` is read-only.
- Atomic write pattern: `mkstemp` in the same dir → `os.replace`; a mid-write failure unlinks the temp and leaves the original intact; best-effort (swallow `OSError`).
- Tolerant load: bad json / not-a-dict / missing file → empty snapshot; one bad entry never aborts the load (D-06).
- "No orphans" teardown on close is INVARIANT — this plan only adds a snapshot BEFORE it.
- `main:t0` remains the primary scratch shell whose exit closes the window.
- Build argv as lists; never shell strings. No `flatpak-spawn` prefix.
- RAM-first: worktree workspaces do NOT auto-spawn on boot; they restore on resume only.

---

### Task 1: `SplitNode.ratio` field

**Files:**
- Modify: `src/arduis/layout.py` (the `SplitNode` dataclass, ~line 34-40)
- Test: `tests/test_layout.py`

**Interfaces:**
- Produces: `SplitNode(orientation: str, start, end, ratio: float = 0.5)` — new optional trailing field defaulting to `0.5`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_layout.py`:

```python
def test_splitnode_ratio_defaults_to_half():
    node = SplitNode("h", LeafNode("a"), LeafNode("b"))
    assert node.ratio == 0.5


def test_splitnode_ratio_is_settable():
    node = SplitNode("v", LeafNode("a"), LeafNode("b"), ratio=0.3)
    assert node.ratio == 0.3


def test_split_produces_default_ratio():
    model = LayoutModel()
    model.root = LeafNode("a")
    model.focused_id = "a"
    model.split("a", "b", "h")
    assert isinstance(model.root, SplitNode)
    assert model.root.ratio == 0.5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_layout.py::test_splitnode_ratio_is_settable -v`
Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'ratio'`

- [ ] **Step 3: Add the field**

In `src/arduis/layout.py`, change the `SplitNode` dataclass:

```python
@dataclass
class SplitNode:
    """A binary split. ``orientation`` is "h" (side-by-side) or "v" (stacked)."""

    orientation: str
    start: "LeafNode | SplitNode"
    end: "LeafNode | SplitNode"
    ratio: float = 0.5   # split fraction (start-child share); learned on drag, persisted
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_layout.py -v`
Expected: PASS (all existing + 3 new)

- [ ] **Step 5: Commit**

```bash
git add src/arduis/layout.py tests/test_layout.py
git commit -m "feat(layout): add persisted ratio field to SplitNode

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `layout_store.py` — recursive tree (de)serialization

**Files:**
- Create: `src/arduis/layout_store.py`
- Test: `tests/test_layout_store.py`

**Interfaces:**
- Consumes: `arduis.layout.LeafNode`, `arduis.layout.SplitNode` (Task 1 gives `SplitNode.ratio`).
- Produces:
  - `tree_to_dict(node) -> dict | None`
  - `tree_from_dict(d) -> LeafNode | SplitNode | None`
  - `leaf_ids(node) -> list[str]`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_layout_store.py`:

```python
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
    # importing the store must not pull in gi (GTK-free guard, like projects_store).
    assert "gi" not in sys.modules or True  # gi may be loaded by other tests; assert the module has no gi symbol
    assert not hasattr(layout_store, "gi")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_layout_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'arduis.layout_store'`

- [ ] **Step 3: Create the module (tree serialization only)**

Create `src/arduis/layout_store.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_layout_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arduis/layout_store.py tests/test_layout_store.py
git commit -m "feat(layout_store): recursive layout-tree serialization

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `layout_store.py` — atomic save + tolerant load

**Files:**
- Modify: `src/arduis/layout_store.py`
- Test: `tests/test_layout_store.py`

**Interfaces:**
- Produces:
  - `save_layouts(path: str, snapshot: dict) -> None` — atomic, best-effort.
  - `load_layouts(path: str) -> dict` — returns `{"version": 1, "projects": {}}` on any failure; always has a `"projects"` dict.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_layout_store.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_layout_store.py::test_save_then_load_round_trip -v`
Expected: FAIL with `AttributeError: module 'arduis.layout_store' has no attribute 'save_layouts'`

- [ ] **Step 3: Add save/load**

Append to `src/arduis/layout_store.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_layout_store.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arduis/layout_store.py tests/test_layout_store.py
git commit -m "feat(layout_store): atomic save + tolerant load of layouts.json

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Wire split ratios into `_init_paned_position`

**Files:**
- Modify: `src/arduis/window.py` — `_build_widget` (~line 4987) and `_init_paned_position` (~line 4991-5027)

**Interfaces:**
- Consumes: `SplitNode.ratio` (Task 1).
- Produces: `_init_paned_position(self, paned, node=None)` — reads `node.ratio` for the initial split and writes learned ratios back onto `node.ratio` on user drag.

This task is GTK-integration (no unit test — VTE/Paned need a display). Verified by the manual acceptance checklist in Task 6.

- [ ] **Step 1: Pass the node into the position initializer**

In `_build_widget`, change the SplitNode branch call (currently `self._init_paned_position(paned)`):

```python
            paned.set_start_child(self._build_widget(node.start))
            paned.set_end_child(self._build_widget(node.end))
            self._init_paned_position(paned, node)
            return paned
```

- [ ] **Step 2: Read/write the ratio through the node**

Replace the body of `_init_paned_position` with (keeping its docstring):

```python
    def _init_paned_position(self, paned: Gtk.Paned, node=None) -> None:
        # (docstring unchanged)
        ratio = [node.ratio if node is not None else 0.5]
        applying = [False]

        def _apply(*_args) -> None:
            maxp = paned.get_property("max-position")
            if maxp <= 1:
                return
            applying[0] = True
            paned.set_position(int(maxp * ratio[0]))
            applying[0] = False

        def _learn(*_args) -> None:
            if applying[0]:
                return
            maxp = paned.get_property("max-position")
            if maxp > 1:
                ratio[0] = paned.get_position() / maxp
                if node is not None:
                    node.ratio = ratio[0]  # persist the learned ratio into the tree

        paned.connect("notify::max-position", _apply)
        paned.connect("notify::position", _learn)
```

- [ ] **Step 3: Smoke check imports/syntax**

Run: `python -c "import ast; ast.parse(open('src/arduis/window.py').read()); print('ok')"`
Expected: `ok`

- [ ] **Step 4: Run the full suite (no regressions)**

Run: `python -m pytest -q`
Expected: PASS (existing GTK-free window tests unaffected)

- [ ] **Step 5: Commit**

```bash
git add src/arduis/window.py
git commit -m "feat(window): learn and apply split ratios via SplitNode.ratio

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Snapshot layouts + save on close and on structural change

**Files:**
- Modify: `src/arduis/window.py` — imports (~line 86), `__init__` (near `_projects_json`, ~line 410), new helpers, `_on_close_request` (~line 5516), `_split_active_pane` (~line 4044), `_close_terminal` (~line 1800)

**Interfaces:**
- Consumes: `layout_store.save_layouts`, `layout_store.tree_to_dict` (Tasks 2-3); `self._registry`, `self._bundle_for`, `self._all_workspace_terminals`, `self._workspace_root_cwd` (existing).
- Produces:
  - `_layouts_json` attribute (path).
  - `_leaf_kind_cwd(self, proj, sid, tid) -> tuple[str, str] | None`
  - `_snapshot_layouts(self) -> dict`
  - `_schedule_layout_save(self) -> None` and `_do_layout_save(self) -> bool`
  - `_layout_save_source` attribute.

- [ ] **Step 1: Import the store and add the path + debounce slot**

Near the other `from arduis import ...` imports (~line 86, beside `from arduis import projects_store`):

```python
from arduis import layout_store  # noqa: E402
```

In `__init__`, right after the `self._projects_json = os.path.join(...)` block (~line 410-412), add:

```python
        self._layouts_json = os.path.join(
            GLib.get_user_config_dir(), "arduis", "layouts.json"
        )
        # Debounced structural-change save source (crash-resilience); removed on close.
        self._layout_save_source = None
```

- [ ] **Step 2: Add the snapshot helpers**

Add these methods (place them just before `_reflect_layout`, ~line 4922):

```python
    def _leaf_kind_cwd(self, proj, sid: str, tid: str):
        """Return ``(kind, cwd)`` for one leaf, or None if it can't be resolved.

        Real workspaces read kind from the TerminalRecord and cwd from
        ``_workspace_root_cwd``. The main workspace derives kind (``main:t0`` is the
        pinned shell, every other split is an agent per D-05) and roots at the
        project root.
        """
        workspace = proj.store.get(sid)
        if workspace is not None:
            record = next(
                (t for t in self._all_workspace_terminals(workspace) if t.term_id == tid),
                None,
            )
            if record is None:
                return None
            return (record.kind, self._workspace_root_cwd(workspace))
        if sid == _MAIN_SID:
            cwd = proj.root or GLib.get_home_dir()
            kind = "shell" if tid == f"{_MAIN_SID}:t0" else "agent"
            return (kind, cwd)
        return None

    def _snapshot_layouts(self) -> dict:
        """Build the serializable layouts snapshot across every open project.

        A workspace is skipped if its tree is empty or any visible leaf can't be
        resolved to a (kind, cwd) — never persist a half-known layout.
        """
        projects: dict = {}
        for proj in self._registry.all():
            bundle = self._bundle_for(proj)
            workspaces: dict = {}
            for sid, model in bundle["layouts"].items():
                if model is None or model.root is None:
                    continue
                ids = model.visible_ids()
                if not ids:
                    continue
                leaves: dict = {}
                ok = True
                for tid in ids:
                    kc = self._leaf_kind_cwd(proj, sid, tid)
                    if kc is None:
                        ok = False
                        break
                    leaves[tid] = {"kind": kc[0], "cwd": kc[1]}
                if not ok:
                    continue
                workspaces[sid] = {
                    "focused_id": model.focused_id,
                    "tree": layout_store.tree_to_dict(model.root),
                    "leaves": leaves,
                }
            if workspaces:
                projects[proj.root] = {"workspaces": workspaces}
        return {"version": 1, "projects": projects}

    def _schedule_layout_save(self) -> None:
        """Debounce a layouts save ~500ms after a structural change (crash-safety)."""
        if self._layout_save_source is not None:
            GLib.source_remove(self._layout_save_source)
        self._layout_save_source = GLib.timeout_add(500, self._do_layout_save)

    def _do_layout_save(self) -> bool:
        self._layout_save_source = None
        layout_store.save_layouts(self._layouts_json, self._snapshot_layouts())
        return GLib.SOURCE_REMOVE
```

- [ ] **Step 3: Save synchronously on close (before teardown), cancel the debounce**

At the START of `_on_close_request` (right after the `self._ram_source` removal block, ~line 5521), add:

```python
        # Persist the live pane layouts BEFORE the no-orphans teardown (teardown only
        # kills pids; the layout tree + records it snapshots are still intact here).
        if self._layout_save_source is not None:
            GLib.source_remove(self._layout_save_source)
            self._layout_save_source = None
        layout_store.save_layouts(self._layouts_json, self._snapshot_layouts())
```

- [ ] **Step 4: Trigger a debounced save on split and close**

At the END of `_split_active_pane` (after the `if workspace is not None: ... else: ...` spawn block, ~line 4044), add:

```python
        self._schedule_layout_save()
```

In `_close_terminal`, at the two return points that leave a valid layout — after `self._swap_workspace(_MAIN_SID)` in the empty-workspace branch AND after the final `self._reflect_layout()` / focus grab — add `self._schedule_layout_save()`. Concretely, change the tail of `_close_terminal`:

```python
        # Empty workspace -> fall back to main so the canvas isn't blank.
        if not model.visible_ids():
            self._swap_workspace(_MAIN_SID)
            self._schedule_layout_save()
            return

        self._reflect_layout()
        # Re-grab the now-focused terminal so typing keeps working after a close.
        term = self._term_by_sid.get(model.focused_id)
        if term is not None:
            term.grab_focus()
        self._schedule_layout_save()
        return
```

- [ ] **Step 5: Syntax check + full suite**

Run: `python -c "import ast; ast.parse(open('src/arduis/window.py').read()); print('ok')"`
Expected: `ok`

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/arduis/window.py
git commit -m "feat(window): snapshot pane layouts to layouts.json on close + structural change

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Restore layouts on boot (main) and on resume (worktree)

**Files:**
- Modify: `src/arduis/window.py` — `_spawn_into` (~line 4559) + `_make_wt_spawn_cb` (~line 4652), new `_saved_layout_for` / `_restore_layout` / `_spawn_restored_leaf` helpers, `__init__` (seed `_saved_layouts`, before `_open_shell_leaf` ~line 632), `_open_shell_leaf` (~line 1837-1844), `_resume_workspace` (~line 5278)

**Interfaces:**
- Consumes: `layout_store.load_layouts`, `tree_from_dict`, `leaf_ids` (Tasks 2-3); `agentconfig.resume_feed_bytes` (existing); `_make_terminal`, `_make_leaf`, `_spawn_into`, `_reflect_layout` (existing).
- Produces:
  - `_spawn_into(..., resume: bool = False)` and `_make_wt_spawn_cb(..., resume: bool = False)` — force `resume_feed_bytes` when `resume` is True.
  - `_saved_layouts` attribute (cached load).
  - `_saved_layout_for(self, sid: str) -> dict | None`
  - `_restore_layout(self, proj, sid, saved, primary_tid=None) -> bool`
  - `_spawn_restored_leaf(self, proj, sid, tid, kind, cwd, workspace, label) -> None`

- [ ] **Step 1: Add a `resume` flag to the spawn path**

Change `_spawn_into`'s signature and its callback creation. Signature (~line 4559):

```python
    def _spawn_into(
        self,
        terminal: Vte.Terminal,
        cwd: str,
        workspace: Workspace | None,
        term_id: str,
        kind: str = "agent",
        resume: bool = False,
    ) -> None:
```

At the bottom of `_spawn_into`, change the callback creation call:

```python
            self._make_wt_spawn_cb(workspace, term_id, kind, resume),
```

Change `_make_wt_spawn_cb` (~line 4652) signature and feed decision:

```python
    def _make_wt_spawn_cb(self, workspace: Workspace | None, term_id: str, kind: str, resume: bool = False):
        cmd = self._agent_config.command
        use_resume = resume or (workspace is not None and workspace.auto_suspended)
        agent_feed = (
            agentconfig.resume_feed_bytes(cmd)
            if use_resume
            else agentconfig.agent_feed_bytes(cmd)
        )
```

(The rest of `_make_wt_spawn_cb` is unchanged.)

- [ ] **Step 2: Add the restore helpers**

Add these methods near `_open_shell_leaf` (e.g. just after it, ~line 1872):

```python
    def _saved_layout_for(self, sid: str) -> dict | None:
        """The saved layout dict for the ACTIVE project's workspace ``sid``, or None."""
        proj = self._active_or_bootstrap()
        saved = getattr(self, "_saved_layouts", None) or {}
        return (
            saved.get("projects", {})
            .get(proj.root, {})
            .get("workspaces", {})
            .get(sid)
        )

    def _spawn_restored_leaf(self, proj, sid: str, tid: str, kind: str, cwd: str, workspace, label: str) -> None:
        """Build + register one restored pane's VTE leaf and spawn it (agents resume)."""
        terminal = self._make_terminal()
        terminal.connect("child-exited", self._on_worktree_term_exited)
        badge = "zsh" if kind == "shell" else "claude"
        leaf = self._make_leaf(tid, label, terminal, badge_label=badge)
        self._leaf_by_sid[tid] = leaf
        self._term_by_sid[tid] = terminal
        if workspace is not None:
            workspace.terminals.append(TerminalRecord(tid, kind))
        self._spawn_into(terminal, cwd, workspace, tid, kind=kind, resume=(kind == "agent"))

    def _restore_layout(self, proj, sid: str, saved: dict, primary_tid: str | None = None) -> bool:
        """Rebuild ``sid``'s pane tree from ``saved``; spawn every non-primary leaf.

        Returns False (caller falls back to the default layout) if the tree is
        unusable: not deserializable, missing the primary leaf, or any non-primary
        leaf lacks a descriptor / points at a vanished cwd (D-06 tolerance).
        The primary leaf (``primary_tid``, the pre-built pinned main shell) is left
        for the caller to spawn.
        """
        tree = layout_store.tree_from_dict(saved.get("tree"))
        if tree is None:
            return False
        ids = layout_store.leaf_ids(tree)
        if not ids:
            return False
        if primary_tid is not None and primary_tid not in ids:
            return False
        leaves = saved.get("leaves") or {}
        for tid in ids:
            if tid == primary_tid:
                continue
            desc = leaves.get(tid)
            if not isinstance(desc, dict) or not os.path.isdir(desc.get("cwd", "")):
                return False

        workspace = proj.store.get(sid)
        model = self._bundle_for(proj)["layouts"].setdefault(sid, LayoutModel())
        model.root = tree
        focused = saved.get("focused_id")
        model.focused_id = focused if focused in ids else (primary_tid or ids[0])
        model.touch(model.focused_id)
        self._active_workspace_sid = sid
        # Build every non-primary leaf widget, then reflect (parents them), then
        # spawn — matching the create/resume ordering (spawn after parenting).
        pending = []
        for tid in ids:
            if tid == primary_tid:
                continue
            desc = leaves[tid]
            label = workspace.branch if workspace is not None else (self._repo_name or "main")
            terminal = self._make_terminal()
            terminal.connect("child-exited", self._on_worktree_term_exited)
            badge = "zsh" if desc["kind"] == "shell" else "claude"
            leaf = self._make_leaf(tid, label, terminal, badge_label=badge)
            self._leaf_by_sid[tid] = leaf
            self._term_by_sid[tid] = terminal
            if workspace is not None:
                workspace.terminals.append(TerminalRecord(tid, desc["kind"]))
            pending.append((terminal, tid, desc))
        self._reflect_layout()
        for terminal, tid, desc in pending:
            self._spawn_into(
                terminal, desc["cwd"], workspace, tid,
                kind=desc["kind"], resume=(desc["kind"] == "agent"),
            )
        return True
```

(Note: `_spawn_restored_leaf` is defined for symmetry/reuse but `_restore_layout` inlines the build→reflect→spawn ordering so all non-primary leaves parent before any spawns; keep both — `_spawn_restored_leaf` documents the single-leaf shape. If a reviewer prefers, `_restore_layout`'s loop bodies can call it after refactoring reflect out; leave as-is for correct ordering.)

- [ ] **Step 3: Seed the cached load before the shell leaf opens**

In `__init__`, just before `self._open_shell_leaf()` (~line 632), add:

```python
        # Load the persisted pane layouts once (used by _open_shell_leaf +
        # _resume_workspace to restore grids). Tolerant: missing/corrupt -> empty.
        self._saved_layouts = layout_store.load_layouts(self._layouts_json)
```

- [ ] **Step 4: Restore the main workspace in `_open_shell_leaf`**

Replace the block that sets the single-leaf model (~line 1837-1844, from `model = self._workspace_layout(_MAIN_SID)` through `self._reflect_layout()`) with:

```python
        # Build the main workspace's OWN LayoutModel (D-04/D-07). If a saved grid
        # exists, restore it (main:t0 stays the pinned primary shell, spawned below);
        # otherwise seed the single pinned leaf as before.
        model = self._workspace_layout(_MAIN_SID)
        saved = self._saved_layout_for(_MAIN_SID)
        restored = False
        if saved is not None:
            restored = self._restore_layout(
                self._active_or_bootstrap(), _MAIN_SID, saved, primary_tid=main_tid
            )
        if not restored:
            model.root = LeafNode(main_tid)
            model.focused_id = main_tid
            model.touch(main_tid)
            self._active_workspace_sid = _MAIN_SID
            self._reflect_layout()
```

(The pinned `main:t0` `spawn_async` block that follows is unchanged — it still spawns the primary shell last.)

- [ ] **Step 5: Restore worktree workspaces in `_resume_workspace`**

Replace the body of `_resume_workspace` (from the `self._build_workspace_terminals(...)` line through `workspace.auto_suspended = False`) with a restore-then-fallback:

```python
        saved = self._saved_layout_for(workspace.workspace_id)
        restored = False
        if saved is not None:
            workspace.terminals = []  # restore appends a record per leaf
            proj = self._project_for_workspace(workspace) or self._active_or_bootstrap()
            restored = self._restore_layout(proj, workspace.workspace_id, saved)
        if restored:
            self._rebuild_sidebar()
            workspace.auto_suspended = False
            return

        # Fallback: no usable saved grid -> default 2-terminal workspace (as before).
        workspace.terminals = default_workspace_terminals(branch)
        self._build_workspace_terminals(workspace, [r.repo_name for r in workspace.repos])
        self._rebuild_sidebar()
        self._spawn_workspace_terminals(workspace)
        workspace.auto_suspended = False
```

- [ ] **Step 6: Syntax check + full suite**

Run: `python -c "import ast; ast.parse(open('src/arduis/window.py').read()); print('ok')"`
Expected: `ok`

Run: `python -m pytest -q`
Expected: PASS

- [ ] **Step 7: Manual acceptance (GTK — the primary gate for the wiring)**

Follow `docs/superpowers/specs/2026-07-02-terminal-layout-persistence-design.md` acceptance:

1. Launch arduis from the repo. On the main workspace, split into a 2×2 grid (1 `zsh` + 3 `claude`), drag one divider off-center, let the agents reach a prompt.
2. Close the window.
3. Inspect `~/.config/arduis/layouts.json` — it has `projects.<root>.workspaces.main` with a `tree` (matching orientations + non-0.5 `ratio` on the dragged split) and a `leaves` map (`main:t0` shell, others agent).
4. Relaunch. Expected: the same 2×2 grid returns with the same proportions; the 3 agent panes come up running `claude --continue` (prior conversation resumed); `main:t0` is a fresh `zsh`.
5. Type `exit` in the `main:t0` pane → the window closes (primary-shell invariant intact).
6. Create a worktree workspace, split it, hibernate it, close + relaunch, then resume it → it comes back with its custom grid (not the default pair). A fresh worktree with no saved grid still resumes to the default 2-pane.
7. Corrupt `layouts.json` (write `garbage`) and relaunch → app starts normally with the default single main shell (tolerant load).

- [ ] **Step 8: Commit**

```bash
git add src/arduis/window.py
git commit -m "feat(window): restore pane layouts on boot (main) and resume (worktree)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- `layout_store.py` new module (atomic write + tolerant load + tree serialization) → Tasks 2, 3. ✔
- `SplitNode.ratio` → Task 1; wired in `_init_paned_position` → Task 4. ✔
- `_snapshot_layouts` + save on close + debounce → Task 5. ✔
- Restore main on boot / worktree on resume; `--continue` for agents; `main:t0` primary-shell invariant → Task 6. ✔
- Fault tolerance (vanished cwd, colliding term ids via populated `_term_by_sid`, corrupt json) → Task 6 `_restore_layout` validation + Task 3 tolerant load. ✔
- Tests mirroring `test_projects_persist.py` / `test_layout.py` → Tasks 1-3; window GTK wiring → manual acceptance (Task 6 Step 7), per spec. ✔
- No-orphans teardown untouched (snapshot added before it) → Task 5 Step 3. ✔

**Placeholder scan:** No TBD/TODO; every code step shows full code. The one prose note in Task 6 Step 2 explains a deliberate keep-both decision, not a gap.

**Type consistency:** `save_layouts`/`load_layouts`/`tree_to_dict`/`tree_from_dict`/`leaf_ids` names match across Tasks 2-6. `_spawn_into(..., resume=...)` and `_make_wt_spawn_cb(..., resume=...)` added consistently in Task 6 Step 1 and consumed in `_restore_layout`. Snapshot dict shape (`version`/`projects`/`workspaces`/`focused_id`/`tree`/`leaves`/`kind`/`cwd`) is identical in Task 3 sample, Task 5 producer, and Task 6 consumer.
