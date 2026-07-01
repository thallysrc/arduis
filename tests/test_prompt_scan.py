"""Instant-waiting accelerator (user feedback 2026-07-01): Claude Code only
fires the permission Notification ~6s after the "Do you want to proceed?"
prompt renders (measured; no bell, no config to shorten it). The terminal TEXT
is the only instant signal, so ``attention.looks_like_permission_prompt``
detects the prompt markers in a VTE tail snapshot. Escalate-only: the hook
events remain authoritative and correct the state afterwards.
"""
from arduis.attention import looks_like_permission_prompt


_REAL_PERMISSION_TAIL = """\
 Bash command
   for i in 1 2 3; do echo loop $i; done
   Run for loop printing loop 1-3
 Contains simple_expansion
 Do you want to proceed?
 ❯ 1. Yes
   2. No
 Esc to cancel · Tab to amend · ctrl+e to explain
"""

_TRUST_TAIL = """\
 Do you trust the files in this folder?
 /tmp/arduis-hook-repro
 ❯ 1. Yes, proceed
   2. No, exit
"""

_RUNNING_TAIL = """\
● Vou rodar um contador de 10 segundos no shell.
  Running 1 shell command…
  $ for i in $(seq 1 10); do echo "segundo $i"; done
✻ Brewed for 23s (esc to interrupt)
"""

_IDLE_SHELL_TAIL = """\
→ arduis (master) ✗
zsh: command not found: aqui
→ arduis (master) ✗ █
"""


def test_detects_real_permission_prompt():
    assert looks_like_permission_prompt(_REAL_PERMISSION_TAIL) is True


def test_detects_workspace_trust_prompt():
    assert looks_like_permission_prompt(_TRUST_TAIL) is True


def test_ignores_streaming_running_output():
    assert looks_like_permission_prompt(_RUNNING_TAIL) is False


def test_ignores_idle_shell():
    assert looks_like_permission_prompt(_IDLE_SHELL_TAIL) is False


def test_ignores_empty_and_none_safe():
    assert looks_like_permission_prompt("") is False


def test_ignores_prompt_text_merely_quoted_in_chat():
    # Claude ECHOING the phrase in prose (no option list) must not escalate —
    # the real dialog always renders numbered options under the question.
    assert looks_like_permission_prompt(
        "● O TUI mostra 'Do you want to proceed?' quando precisa de aprovação.\n"
    ) is False


# --- escalate-only wiring: _escalate_waiting --------------------------------

import arduis.window as W  # noqa: E402
from arduis.attention import AttentionConfig  # noqa: E402
from arduis.project import Project, ProjectRegistry  # noqa: E402
from arduis.session import (  # noqa: E402
    SessionState, SessionStore, Task, TerminalRecord,
)


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


def _win():
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
    win._att_config = AttentionConfig()
    return win


def test_escalate_marks_task_record_waiting_and_lights_ui():
    win = _win()
    task = Task(task_id="alpha", branch="alpha", task_dir="/t", repos=[],
                state=SessionState.ACTIVE,
                terminals=[TerminalRecord("alpha:t0", "agent", status="running")])
    win._escalate_waiting(task, "alpha:t0", "/sf.json")
    assert task.terminals[0].status == "waiting"
    assert win._row_by_sid["alpha"].has_css_class("arduis-row-attention")
    assert win._leaf_by_sid["alpha:t0"].has_css_class("attention")


def test_escalate_main_split_lights_main_row():
    win = _win()
    dot, leaf = _FakeWidget(), _FakeWidget()
    win._main_split_info["/sf.json"] = {
        "root": "/projA", "tid": "main:t1", "dot": dot, "leaf": leaf,
        "status": "running",
    }
    win._escalate_waiting(None, "main:t1", "/sf.json")
    assert win._main_split_info["/sf.json"]["status"] == "waiting"
    assert dot.has_css_class("arduis-dot-waiting")
    assert leaf.has_css_class("attention")
    assert win._row_by_sid[W._MAIN_SID].has_css_class("arduis-row-attention")


def test_escalate_is_noop_when_already_waiting():
    win = _win()
    task = Task(task_id="alpha", branch="alpha", task_dir="/t", repos=[],
                state=SessionState.ACTIVE,
                terminals=[TerminalRecord("alpha:t0", "agent", status="waiting")])
    ts_before = task.terminals[0].status_ts
    win._escalate_waiting(task, "alpha:t0", "/sf.json")
    assert task.terminals[0].status_ts == ts_before  # untouched — no churn
