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
