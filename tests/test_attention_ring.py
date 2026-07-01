"""A WAITING agent must be LOUD (user feedback 2026-07-01): the 8px dot alone is
easy to miss, so the whole card rings in the attention color ("attention" class
on the leaf) and the sidebar row highlights ("arduis-row-attention") — for task
agents AND for main-workspace agent splits (whose sidebar row is the pinned
main row; the user reported waiting in main while working inside a task and
seeing nothing).

GTK-free (mirrors test_window_attention_multiproject.py): a bare window via
``ArduisWindow.__new__`` with a 1-project registry (the widget maps are
bundle-backed properties) and fake widgets that record css classes.
"""
import json
import os
import time

import arduis.window as W
from arduis.attention import AttentionConfig
from arduis.project import Project, ProjectRegistry
from arduis.session import SessionState, SessionStore, Task, TerminalRecord
from arduis.themes import PARALLEL_DARK


class _FakeWidget:
    def __init__(self):
        self.classes: set[str] = set()
        self.visible = False

    def add_css_class(self, c):
        self.classes.add(c)

    def remove_css_class(self, c):
        self.classes.discard(c)

    def has_css_class(self, c):
        return c in self.classes

    def set_visible(self, v):
        self.visible = v


def _task(status):
    return Task(
        task_id="alpha",
        branch="alpha",
        task_dir="/tasks/alpha",
        repos=[],
        state=SessionState.ACTIVE,
        terminals=[TerminalRecord("alpha:t0", "agent", status=status)],
    )


def _win():
    """Bare window + 1-project registry; fills the bundle maps with fakes."""
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    win._registry = ProjectRegistry()
    win._bootstrap = Project(root="")
    proj = Project(root="/projA", member_repos=[], store=SessionStore())
    win._registry.add(proj)
    win._registry.set_active("/projA")
    bundle = win._bundle_for(proj)
    bundle["dot_by_sid"]["alpha"] = _FakeWidget()
    bundle["dot_by_sid"][W._MAIN_SID] = _FakeWidget()
    bundle["pane_dot_by_tid"]["alpha:t0"] = _FakeWidget()
    bundle["leaf_by_sid"]["alpha:t0"] = _FakeWidget()
    win._row_by_sid = {"alpha": _FakeWidget(), W._MAIN_SID: _FakeWidget()}
    win._main_split_info = {}
    return win


# --- CSS contract -----------------------------------------------------------

def test_build_css_declares_attention_ring_and_row_highlight():
    css = W._build_css(PARALLEL_DARK)
    assert ".arduis-leaf.attention" in css
    ring = css.split(".arduis-leaf.attention", 1)[1][:220]
    assert PARALLEL_DARK.dot_waiting in ring  # ring is the attention color
    assert ".arduis-row-attention" in css


def test_attention_ring_declared_after_focus_so_it_wins():
    css = W._build_css(PARALLEL_DARK)
    assert css.index(".arduis-leaf.focus") < css.index(".arduis-leaf.attention")


# --- task agents: _refresh_status_ui ----------------------------------------

def test_waiting_agent_rings_card_and_highlights_row():
    win = _win()
    win._refresh_status_ui(_task("waiting"))
    assert win._leaf_by_sid["alpha:t0"].has_css_class("attention")
    assert win._row_by_sid["alpha"].has_css_class("arduis-row-attention")


def test_running_agent_clears_ring_and_row_highlight():
    win = _win()
    win._leaf_by_sid["alpha:t0"].add_css_class("attention")
    win._row_by_sid["alpha"].add_css_class("arduis-row-attention")
    win._refresh_status_ui(_task("running"))
    assert not win._leaf_by_sid["alpha:t0"].has_css_class("attention")
    assert not win._row_by_sid["alpha"].has_css_class("arduis-row-attention")


def test_hibernated_task_never_rings():
    win = _win()
    task = _task("waiting")
    task.state = SessionState.HIBERNATED
    win._leaf_by_sid["alpha:t0"].add_css_class("attention")
    win._row_by_sid["alpha"].add_css_class("arduis-row-attention")
    win._refresh_status_ui(task)
    assert not win._leaf_by_sid["alpha:t0"].has_css_class("attention")
    assert not win._row_by_sid["alpha"].has_css_class("arduis-row-attention")


# --- main-workspace agent splits: _apply_main_state_file ---------------------

def _main_win(tmp_path, state):
    win = _win()
    win._att_config = AttentionConfig()
    path = str(tmp_path / "main-t1.json")
    with open(path, "w") as fh:
        json.dump(
            {"state": state, "ts": time.time(), "event": "Notification",
             "pid": os.getpid()},
            fh,
        )
    dot, leaf = _FakeWidget(), _FakeWidget()
    win._main_split_info[path] = {
        "root": "/projA", "tid": "main:t1", "dot": dot, "leaf": leaf,
        "status": None,
    }
    return win, path, dot, leaf


def test_main_split_waiting_rings_card_and_lights_main_row(tmp_path):
    win, path, dot, leaf = _main_win(tmp_path, "waiting")
    win._apply_main_state_file(path)
    assert dot.has_css_class("arduis-dot-waiting")
    assert leaf.has_css_class("attention")
    # THE user-reported gap: working inside a task, the sidebar main row must
    # light up when a main-split agent waits.
    assert win._dot_by_sid[W._MAIN_SID].has_css_class("arduis-dot-waiting")
    assert win._row_by_sid[W._MAIN_SID].has_css_class("arduis-row-attention")


def test_main_split_running_clears_ring_and_main_row(tmp_path):
    win, path, dot, leaf = _main_win(tmp_path, "running")
    leaf.add_css_class("attention")
    win._row_by_sid[W._MAIN_SID].add_css_class("arduis-row-attention")
    win._apply_main_state_file(path)
    assert dot.has_css_class("arduis-dot-active")
    assert not leaf.has_css_class("attention")
    assert not win._row_by_sid[W._MAIN_SID].has_css_class("arduis-row-attention")
    assert win._dot_by_sid[W._MAIN_SID].has_css_class("arduis-dot-active")


def test_background_project_main_split_does_not_light_active_main_row(tmp_path):
    win, path, dot, leaf = _main_win(tmp_path, "waiting")
    win._main_split_info[path]["root"] = "/projB"  # belongs to a BACKGROUND project
    win._apply_main_state_file(path)
    assert leaf.has_css_class("attention")  # its own card still rings
    assert not win._row_by_sid[W._MAIN_SID].has_css_class("arduis-row-attention")
