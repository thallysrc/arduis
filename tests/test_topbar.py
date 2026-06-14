"""Tests for the GTK-free topbar chip-state (D-02/D-03/D-06).

Contract: ``ChipState`` holds a project's member-repo set + the user's toggled-ON
DEFAULT subset (which seeds a new task's repo selection, D-02) and, SEPARATELY,
the repos of the currently-active task to reflect/highlight (D-03) without
disturbing the default. It is pure data + logic — no I/O, no ``gi``. Mirrors the
pure-function style of tests/test_project.py.
"""
from arduis import topbar
from arduis.topbar import ChipState


def test_construct_defaults_all_members_selected():
    # D-02: .members preserves the given order; .selected (toggled-ON default)
    # starts as ALL members ("checked by default").
    cs = ChipState(["backend", "frontend", "iam"])
    assert cs.members == ["backend", "frontend", "iam"]  # order preserved
    assert cs.selected == {"backend", "frontend", "iam"}  # all on by default
    assert cs.active_repos is None  # nothing reflected yet


def test_empty_members_no_crash():
    # Degenerate project before resolution -> empty, no crash.
    cs = ChipState([])
    assert cs.members == []
    assert cs.selected == set()
    assert cs.active_repos is None


def test_toggle_off_then_on():
    # Toggling an ON repo turns it OFF; toggling again turns it back ON.
    cs = ChipState(["backend", "frontend"])
    cs.toggle("backend")
    assert cs.selected == {"frontend"}
    cs.toggle("backend")
    assert cs.selected == {"backend", "frontend"}


def test_toggle_never_mutates_members():
    cs = ChipState(["backend", "frontend"])
    cs.toggle("backend")
    cs.toggle("frontend")
    assert cs.members == ["backend", "frontend"]  # unchanged by toggling


def test_toggle_non_member_is_noop():
    # Chips can only toggle real members; an unknown repo is ignored.
    cs = ChipState(["backend"])
    cs.toggle("ghost")
    assert cs.selected == {"backend"}
    assert cs.members == ["backend"]


def test_default_selection_in_members_order():
    # D-02: seeds the New-task dialog checkboxes — toggled-ON members in
    # .members order.
    cs = ChipState(["backend", "frontend", "iam"])
    assert cs.default_selection() == ["backend", "frontend", "iam"]  # all on
    cs.toggle("frontend")
    assert cs.default_selection() == ["backend", "iam"]  # remaining, in order


def test_default_selection_single_member_parity():
    # Criterion 5: a 1-member ChipState toggled ON returns that single member via
    # the identical path — no special case.
    cs = ChipState(["solo"])
    assert cs.default_selection() == ["solo"]


def test_reflect_active_does_not_change_selected():
    # D-03: reflecting an active task sets .active_repos WITHOUT touching the
    # toggled-ON default (.selected) — reflecting is non-destructive.
    cs = ChipState(["backend", "frontend"])
    before = set(cs.selected)
    cs.reflect_active({"backend"})
    assert cs.active_repos == {"backend"}
    assert cs.selected == before  # default selection untouched


def test_reflect_active_none_clears():
    # Selecting the pinned `main` row / no task restores the plain default
    # highlight: reflect_active(None) clears .active_repos.
    cs = ChipState(["backend", "frontend"])
    cs.reflect_active({"backend"})
    cs.reflect_active(None)
    assert cs.active_repos is None


def test_is_active_reflects_active_set():
    cs = ChipState(["backend", "frontend"])
    assert cs.is_active("backend") is False  # nothing reflected
    cs.reflect_active({"backend"})
    assert cs.is_active("backend") is True
    assert cs.is_active("frontend") is False


def test_is_selected_reflects_toggled_on_set():
    cs = ChipState(["backend", "frontend"])
    assert cs.is_selected("backend") is True
    cs.toggle("backend")
    assert cs.is_selected("backend") is False
    assert cs.is_selected("frontend") is True


def test_topbar_module_is_gtk_free():
    with open(topbar.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
