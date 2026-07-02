"""Regression lock for the recoverable EMPTY STATE canvas (quick 260702-kzo).

A workspace whose panes are all closed (or restored empty) used to render a blank
``Gtk.Box`` — a black canvas with no way back. This locks the three behaviours that
make the empty canvas recoverable, all GTK-free via the bare-window ``__new__``
pattern (see test_window_conclude.py): construct the window without ``__init__``/GTK
and stub the GTK-touching + spawn helpers to record calls.

  - Test 1: ``_split_active_pane(None)`` on an EMPTY model ROOTS a new leaf (not a
    no-op), tracks a ``TerminalRecord`` kind "agent", and spawns with kind="agent"
    — the empty-state button / keyboard recovery path.
  - Test 2: ``_split_active_pane(tid)`` on a model WITH a leaf still uses
    ``model.split`` (2 visible leaves after) — the normal split path is unregressed.
  - Test 3: ``_close_terminal`` of the LAST pane stays in the workspace — it does NOT
    call ``_swap_workspace``; it re-reflects (empty state) + schedules a save.
  - Test 4: ``_reflect_layout`` picks the empty state for an ACTIVE model with
    ``root is None``, and the neutral placeholder when there is no active model.
"""
import arduis.window as W
from arduis.layout import LayoutModel, LeafNode
from arduis.session import Workspace, SessionState


class _FakeTerminal:
    """Stand-in for a Vte.Terminal — only needs ``connect`` for the split path."""

    def connect(self, *_a, **_k):
        return 0


def _bare_window(monkeypatch, model, workspace):
    """A bare window whose split/close chain records calls; GTK/spawn stubbed out."""
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    calls = []

    # _leaf_by_sid / _term_by_sid are read-only @property views onto the active
    # project's lazily-created (empty) map bundle — no assignment needed.
    win._active_workspace_sid = "feat"
    win._main_split_info = {}
    win._dialog_on_screen = set()
    win._store = type("S", (), {"get": lambda self, sid: workspace})()

    monkeypatch.setattr(win, "_workspace_layout", lambda sid: model)
    monkeypatch.setattr(win, "_active_layout", lambda: model)
    monkeypatch.setattr(win, "_make_terminal", lambda: _FakeTerminal())
    monkeypatch.setattr(
        win, "_make_leaf", lambda *a, **k: object()
    )
    monkeypatch.setattr(win, "_next_term_id", lambda sid: f"{sid}:t9")
    monkeypatch.setattr(win, "_workspace_root_cwd", lambda ws: "/workspaces/feat")
    monkeypatch.setattr(win, "_on_worktree_term_exited", lambda *a, **k: None)

    for name in ("_reflect_layout", "_schedule_layout_save", "_swap_workspace",
                 "_teardown_pgid", "_refresh_main_row_attention"):
        monkeypatch.setattr(
            win, name, (lambda n: (lambda *a, **k: calls.append(n)))(name)
        )

    spawn_calls = []
    monkeypatch.setattr(
        win, "_spawn_into",
        lambda terminal, cwd, ws, tid, kind="agent", resume=False:
            spawn_calls.append({"tid": tid, "kind": kind, "cwd": cwd}),
    )
    return win, calls, spawn_calls


def test_split_none_on_empty_model_roots_leaf_and_spawns_agent(monkeypatch):
    model = LayoutModel()  # empty: root is None
    workspace = Workspace(workspace_id="feat", branch="feat",
                          workspace_dir="/workspaces/feat", state=SessionState.ACTIVE)
    win, calls, spawn_calls = _bare_window(monkeypatch, model, workspace)

    win._split_active_pane(None, "h")

    # Rooted a NEW leaf (not a no-op) and focused it.
    assert isinstance(model.root, LeafNode)
    assert model.root.session_id == "feat:t9"
    assert model.focused_id == "feat:t9"
    assert model.visible_ids() == ["feat:t9"]
    # Tracked as an agent TerminalRecord + spawned as an agent.
    assert [t.term_id for t in workspace.terminals] == ["feat:t9"]
    assert workspace.terminals[0].kind == "agent"
    assert spawn_calls == [{"tid": "feat:t9", "kind": "agent", "cwd": "/workspaces/feat"}]
    assert "_reflect_layout" in calls and "_schedule_layout_save" in calls


def test_split_on_nonempty_model_uses_split_path(monkeypatch):
    model = LayoutModel()
    model.root = LeafNode("feat:t0")
    model.focused_id = "feat:t0"
    model.touch("feat:t0")
    workspace = Workspace(workspace_id="feat", branch="feat",
                          workspace_dir="/workspaces/feat", state=SessionState.ACTIVE)
    win, calls, spawn_calls = _bare_window(monkeypatch, model, workspace)
    # is_visible(focused_tid) must see the existing leaf -> takes the split branch.
    win._term_by_sid["feat:t0"] = object()

    win._split_active_pane("feat:t0", "h")

    # Normal split: two visible leaves now, new one focused.
    assert set(model.visible_ids()) == {"feat:t0", "feat:t9"}
    assert model.focused_id == "feat:t9"
    assert spawn_calls[0]["kind"] == "agent"


def test_close_last_pane_stays_in_workspace(monkeypatch):
    model = LayoutModel()
    model.root = LeafNode("feat:t0")
    model.focused_id = "feat:t0"
    model.touch("feat:t0")
    workspace = Workspace(workspace_id="feat", branch="feat",
                          workspace_dir="/workspaces/feat", state=SessionState.ACTIVE)
    win, calls, spawn_calls = _bare_window(monkeypatch, model, workspace)
    win._leaf_by_sid["feat:t0"] = object()
    win._term_by_sid["feat:t0"] = object()

    win._close_terminal("feat:t0")

    # Last pane gone, but we STAY in the workspace (no swap to main).
    assert model.visible_ids() == []
    assert "_swap_workspace" not in calls
    assert "_reflect_layout" in calls
    assert "_schedule_layout_save" in calls


def test_reflect_layout_picks_empty_state_vs_placeholder(monkeypatch):
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    # _leaf_by_sid is a read-only @property view onto the empty map bundle.

    class _Slot:
        def __init__(self):
            self.child = None
        def get_child(self):
            return self.child
        def set_child(self, c):
            self.child = c
    win._canvas_slot = _Slot()

    EMPTY = object()
    PLACEHOLDER = object()
    monkeypatch.setattr(win, "_make_empty_state", lambda: EMPTY)
    monkeypatch.setattr(win, "_build_widget", lambda node: PLACEHOLDER)
    monkeypatch.setattr(win, "_refresh_focus_ring", lambda *a, **k: None)

    # Active model with root None -> recoverable empty state.
    empty_model = LayoutModel()
    monkeypatch.setattr(win, "_active_layout", lambda: empty_model)
    win._reflect_layout()
    assert win._canvas_slot.get_child() is EMPTY

    # No active model (bootstrap) -> neutral placeholder box.
    monkeypatch.setattr(win, "_active_layout", lambda: None)
    win._reflect_layout()
    assert win._canvas_slot.get_child() is PLACEHOLDER
