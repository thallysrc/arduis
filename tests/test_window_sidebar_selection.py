"""Regression lock for the sidebar highlight tracking the ACTIVE workspace.

Bug (workspace-sidebar-highlight-wrong-item): the WORKSPACES list highlight is the
ListBox SINGLE-selection (`.arduis-sidebar row:selected`). At boot the pinned main
row is made active via `_open_shell_leaf` -> `_reflect_layout` (NOT `_swap_workspace`),
while the only prior `_rebuild_sidebar` ran with `_active_workspace_sid` still None —
so the active row was never selected and a stale row (e.g. "novo-teste") stayed
visually prominent. The fix centralizes the highlight on `_sync_sidebar_selection`.

window.py imports without a display; we build a bare window via `__new__` and drive
`_sync_sidebar_selection` against a recording fake ListBox — no GTK display needed.
"""
import arduis.window as W


class _FakeListBox:
    """Records selection so we can assert the highlight without a real ListBox."""

    def __init__(self, selected=None):
        self.selected = selected
        self.unselect_calls = 0

    def get_selected_row(self):
        return self.selected

    def select_row(self, row):
        self.selected = row

    def unselect_all(self):
        self.unselect_calls += 1
        self.selected = None


def _bare_window(monkeypatch, active_sid, rows):
    """A bare window whose `_active_workspace_sid` reads a stub bundle."""
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    monkeypatch.setattr(win, "_m", lambda: {"active_workspace_sid": active_sid})
    win._row_by_sid = rows
    return win


def test_sync_selects_active_main_row(monkeypatch):
    """The pinned main row is highlighted when it is the active workspace (boot case)."""
    main_row = object()
    win = _bare_window(monkeypatch, W._MAIN_SID, {W._MAIN_SID: main_row})
    win._listbox = _FakeListBox(selected=None)  # boot: nothing selected yet

    win._sync_sidebar_selection()

    assert win._listbox.get_selected_row() is main_row


def test_sync_moves_stale_selection_to_active(monkeypatch):
    """A stale selection on the wrong row (novo-teste) is corrected to the active row."""
    main_row = object()
    stale_row = object()
    win = _bare_window(
        monkeypatch, W._MAIN_SID, {W._MAIN_SID: main_row, "novo-teste": stale_row}
    )
    win._listbox = _FakeListBox(selected=stale_row)  # highlight stuck on novo-teste

    win._sync_sidebar_selection()

    assert win._listbox.get_selected_row() is main_row


def test_sync_unselects_when_no_active_workspace(monkeypatch):
    """None active workspace clears the highlight rather than leaving a stale row."""
    win = _bare_window(monkeypatch, None, {"novo-teste": object()})
    win._listbox = _FakeListBox(selected=object())

    win._sync_sidebar_selection()

    assert win._listbox.get_selected_row() is None
    assert win._listbox.unselect_calls == 1


def test_sync_noop_when_active_row_already_selected(monkeypatch):
    """Idempotent: no redundant select_row when the active row is already highlighted."""
    main_row = object()
    win = _bare_window(monkeypatch, W._MAIN_SID, {W._MAIN_SID: main_row})
    lb = _FakeListBox(selected=main_row)
    win._listbox = lb

    win._sync_sidebar_selection()

    assert lb.get_selected_row() is main_row
    assert lb.unselect_calls == 0


# --- reopened investigation (2026-07-02): _build_workspace_terminals gap ---
# The boot-only fix above left ONE write site unguarded: _build_workspace_terminals
# (shared by workspace CREATE-finalize and RESUME) sets _active_workspace_sid and
# calls _reflect_layout() directly -- NOT via _swap_workspace -- and relied on the
# CALLER to later call _rebuild_sidebar() to pick up the highlight. That is exactly
# how the reported "novo-teste panes visible, arduis still highlighted" regression
# happened. These tests lock the self-sufficient fix: the highlight updates the
# moment _build_workspace_terminals runs, with NO _rebuild_sidebar() involved.

def _bare_window_for_build(monkeypatch, active_row, target_row, target_sid):
    """A bare window that can run _build_workspace_terminals with GTK/VTE stubbed out."""
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    bundle = {"active_workspace_sid": None, "layouts": {}, "leaf_by_sid": {}, "term_by_sid": {}}
    monkeypatch.setattr(win, "_m", lambda: bundle)
    win._row_by_sid = {target_sid: target_row}
    win._listbox = _FakeListBox(selected=active_row)
    monkeypatch.setattr(win, "_make_workspace_leaf", lambda *a, **k: None)
    monkeypatch.setattr(win, "_reflect_layout", lambda: None)
    return win


def test_build_workspace_terminals_syncs_highlight_without_rebuild_sidebar(monkeypatch):
    """Creating/resuming a workspace highlights it immediately, no _rebuild_sidebar needed."""
    from arduis.session import Workspace

    stale_row = object()  # e.g. the pinned main row, selected since boot
    new_row = object()    # the freshly created/resumed workspace's row
    workspace = Workspace(
        workspace_id="novo-teste", branch="novo-teste",
        workspace_dir="/workspaces/novo-teste", repos=[],
    )
    win = _bare_window_for_build(monkeypatch, stale_row, new_row, "novo-teste")

    win._build_workspace_terminals(workspace, [])

    assert win._listbox.get_selected_row() is new_row
    assert win._active_workspace_sid == "novo-teste"


def test_restore_layout_syncs_highlight_without_rebuild_sidebar(monkeypatch):
    """Boot/resume restoring a saved grid highlights the restored workspace immediately."""
    from arduis import layout_store
    from arduis.project import Project
    from arduis.session import Workspace
    from arduis.layout import LeafNode

    stale_row = object()
    new_row = object()
    workspace = Workspace(
        workspace_id="novo-teste", branch="novo-teste",
        workspace_dir="/workspaces/novo-teste", repos=[],
    )
    class _FakeTerminal:
        def connect(self, *a, **k):
            pass

    store = type("S", (), {"get": lambda self, sid: workspace})()
    proj = Project.__new__(Project)
    proj.store = store
    win = _bare_window_for_build(monkeypatch, stale_row, new_row, "novo-teste")
    monkeypatch.setattr(win, "_bundle_for", lambda p: win._m())
    monkeypatch.setattr(win, "_make_terminal", lambda: _FakeTerminal())
    monkeypatch.setattr(win, "_make_leaf", lambda *a, **k: object())
    monkeypatch.setattr(win, "_spawn_into", lambda *a, **k: None)
    monkeypatch.setattr(W.os.path, "isdir", lambda path: True)  # fake cwd need not exist

    saved = {
        "tree": layout_store.tree_to_dict(LeafNode("novo-teste:t0")),
        "leaves": {"novo-teste:t0": {"kind": "agent", "cwd": "/workspaces/novo-teste"}},
        "focused_id": "novo-teste:t0",
    }

    ok = win._restore_layout(proj, "novo-teste", saved)

    assert ok is True
    assert win._listbox.get_selected_row() is new_row
    assert win._active_workspace_sid == "novo-teste"


# --- structural guard: every _active_workspace_sid write must sync the highlight ---
# Prevents a FUTURE write site from reintroducing this exact bug class (coordinator's
# explicit ask): any function assigning `self._active_workspace_sid = ...` must also
# call `self._sync_sidebar_selection(` somewhere in its own body.

def test_every_active_workspace_sid_write_site_syncs_the_highlight():
    import ast
    import inspect

    source = inspect.getsource(W)
    tree = ast.parse(source)

    class _Visitor(ast.NodeVisitor):
        def __init__(self):
            self.violations = []

        def visit_FunctionDef(self, node):
            assigns_sid = False
            calls_sync = False
            for child in ast.walk(node):
                if (
                    isinstance(child, ast.Assign)
                    and len(child.targets) == 1
                    and isinstance(child.targets[0], ast.Attribute)
                    and child.targets[0].attr == "_active_workspace_sid"
                ):
                    assigns_sid = True
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Attribute)
                    and child.func.attr == "_sync_sidebar_selection"
                ):
                    calls_sync = True
            if assigns_sid and not calls_sync:
                self.violations.append(node.name)
            self.generic_visit(node)

    visitor = _Visitor()
    visitor.visit(tree)

    assert visitor.violations == [], (
        f"Function(s) {visitor.violations} assign _active_workspace_sid without "
        "calling _sync_sidebar_selection() -- the sidebar highlight will drift "
        "(workspace-sidebar-highlight-wrong-item regression class)."
    )
