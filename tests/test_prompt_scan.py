"""Instant-waiting accelerator (user feedback 2026-07-01): Claude Code only
fires the Notification event seconds after a dialog renders (~6s permission,
3-4s option-select; no bell, no config to shorten it). The terminal TEXT is the
only instant signal, so ``attention.looks_like_pending_dialog`` detects the
dialog in a VTE tail snapshot — approval prompts by marker phrase + "1. Yes"
row, option-select dialogs by their TUI-chrome footer. Escalate-only: the hook
events remain authoritative and correct the state afterwards.
"""
from arduis.attention import looks_like_pending_dialog


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
    assert looks_like_pending_dialog(_REAL_PERMISSION_TAIL) is True


def test_detects_workspace_trust_prompt():
    assert looks_like_pending_dialog(_TRUST_TAIL) is True


def test_ignores_streaming_running_output():
    assert looks_like_pending_dialog(_RUNNING_TAIL) is False


def test_ignores_idle_shell():
    assert looks_like_pending_dialog(_IDLE_SHELL_TAIL) is False


def test_ignores_empty_and_none_safe():
    assert looks_like_pending_dialog("") is False


def test_ignores_prompt_text_merely_quoted_in_chat():
    # Claude ECHOING the phrase in prose (no option list) must not escalate —
    # the real dialog always renders numbered options under the question.
    assert looks_like_pending_dialog(
        "● O TUI mostra 'Do you want to proceed?' quando precisa de aprovação.\n"
    ) is False


# Option-select dialog (AskUserQuestion / MCP elicitation) — real tail captured
# from a user screenshot 2026-07-02. Question + options are model-generated, so
# the stable signal is the TUI-chrome footer key-hint row.
_SELECT_DIALOG_TAIL = """\
 Escolha
 Qual dessas opções descreve o que você quer fazer agora?
 ❯ 1. Opção A
      Primeira alternativa de teste
   2. Opção B
      Segunda alternativa de teste
   3. Opção C
      Terceira alternativa de teste
   4. Type something.
   5. Chat about this
 Enter to select · ↑/↓ to navigate · Esc to cancel
"""


def test_detects_option_select_dialog():
    assert looks_like_pending_dialog(_SELECT_DIALOG_TAIL) is True


def test_ignores_partial_footer_fragments_in_prose():
    # Fragments of the footer in prose (e.g. claude explaining the UI) must not
    # escalate — only the full chrome row counts.
    assert looks_like_pending_dialog(
        "● Pressione Enter to select quando o seletor abrir.\n"
    ) is False
    assert looks_like_pending_dialog("Esc to cancel\n") is False


# --- escalate-only wiring: _escalate_waiting --------------------------------

import arduis.window as W  # noqa: E402
from arduis.attention import AttentionConfig  # noqa: E402
from arduis.project import Project, ProjectRegistry  # noqa: E402
from arduis.session import (  # noqa: E402
    SessionState, SessionStore, Workspace, TerminalRecord,
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
    # _maybe_notify reads GTK window props — stub it on this __new__-built window
    # (tests that assert on the notify gate override this with a recorder).
    win._maybe_notify = lambda *a: None
    return win


def test_escalate_marks_workspace_record_waiting_and_lights_ui():
    win = _win()
    workspace = Workspace(workspace_id="alpha", branch="alpha", workspace_dir="/t", repos=[],
                state=SessionState.ACTIVE,
                terminals=[TerminalRecord("alpha:t0", "agent", status="running")])
    win._escalate_waiting(workspace, "alpha:t0", "/sf.json")
    assert workspace.terminals[0].status == "waiting"
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
    workspace = Workspace(workspace_id="alpha", branch="alpha", workspace_dir="/t", repos=[],
                state=SessionState.ACTIVE,
                terminals=[TerminalRecord("alpha:t0", "agent", status="waiting")])
    ts_before = workspace.terminals[0].status_ts
    win._escalate_waiting(workspace, "alpha:t0", "/sf.json")
    assert workspace.terminals[0].status_ts == ts_before  # untouched — no churn


# --- symmetric clear: dialog answered -> running (user feedback 2026-07-01) --

from arduis.attention import next_scan_action  # noqa: E402


def test_scan_action_escalates_on_dialog():
    assert next_scan_action(False, True, "running") == "escalate"


def test_scan_action_deescalates_when_answered():
    # We SAW the dialog in this terminal and it vanished while still waiting:
    # the user answered (approve/reject/Esc) — flip to running immediately.
    assert next_scan_action(True, False, "waiting") == "deescalate"


def test_scan_action_never_clears_waiting_it_never_saw():
    # A hook-set waiting whose dialog never appeared in the tail (e.g. an
    # elicitation question) must NOT be cleared by the scanner.
    assert next_scan_action(False, False, "waiting") is None


def test_scan_action_idle_when_no_dialog_and_not_waiting():
    assert next_scan_action(False, False, "running") is None
    assert next_scan_action(True, False, "running") is None


def test_scan_action_noop_while_dialog_still_shown():
    assert next_scan_action(True, True, "waiting") is None


def test_deescalate_workspace_flips_waiting_to_running_and_clears_ui():
    win = _win()
    workspace = Workspace(workspace_id="alpha", branch="alpha", workspace_dir="/t", repos=[],
                state=SessionState.ACTIVE,
                terminals=[TerminalRecord("alpha:t0", "agent", status="waiting")])
    win._leaf_by_sid["alpha:t0"].add_css_class("attention")
    win._row_by_sid["alpha"].add_css_class("arduis-row-attention")
    win._deescalate_running(workspace, "alpha:t0", "/sf.json")
    assert workspace.terminals[0].status == "running"
    assert not win._leaf_by_sid["alpha:t0"].has_css_class("attention")
    assert not win._row_by_sid["alpha"].has_css_class("arduis-row-attention")


def test_deescalate_main_split_clears_main_row():
    win = _win()
    dot, leaf = _FakeWidget(), _FakeWidget()
    leaf.add_css_class("attention")
    win._main_split_info["/sf.json"] = {
        "root": "/projA", "tid": "main:t1", "dot": dot, "leaf": leaf,
        "status": "waiting",
    }
    win._row_by_sid[W._MAIN_SID].add_css_class("arduis-row-attention")
    win._deescalate_running(None, "main:t1", "/sf.json")
    assert win._main_split_info["/sf.json"]["status"] == "running"
    assert dot.has_css_class("arduis-dot-active")
    assert not leaf.has_css_class("attention")
    assert not win._row_by_sid[W._MAIN_SID].has_css_class("arduis-row-attention")


def test_deescalate_noop_unless_waiting():
    win = _win()
    workspace = Workspace(workspace_id="alpha", branch="alpha", workspace_dir="/t", repos=[],
                state=SessionState.ACTIVE,
                terminals=[TerminalRecord("alpha:t0", "agent", status="ready")])
    win._deescalate_running(workspace, "alpha:t0", "/sf.json")
    assert workspace.terminals[0].status == "ready"  # untouched


# --- scanner waiting vs the ~2s poll re-read (attention.preserve_scan_waiting) --

import json  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402


def _state_file(tmp_path, state: str, ts: float) -> str:
    sf = tmp_path / "sf.json"
    sf.write_text(json.dumps({"state": state, "ts": ts, "pid": os.getpid()}))
    return str(sf)


def test_stale_reread_does_not_stomp_scanner_waiting(tmp_path):
    """The poll tick re-reads the SAME (older) doc every ~2s — it must not flip
    a scanner-escalated waiting back to the file's stale opinion."""
    win = _win()
    win._maybe_notify = lambda *a: None
    workspace = Workspace(workspace_id="alpha", branch="alpha", workspace_dir="/t", repos=[],
                state=SessionState.ACTIVE,
                terminals=[TerminalRecord("alpha:t0", "agent", status="running")])
    record = workspace.terminals[0]
    path = _state_file(tmp_path, "running", time.time() - 30)
    win._escalate_waiting(workspace, "alpha:t0", path)
    assert record.status == "waiting"
    win._apply_state_file(workspace, record, path)
    assert record.status == "waiting"  # stale re-read preserved the orange


def test_newer_hook_event_overrides_scanner_waiting(tmp_path):
    """A hook event NEWER than the escalation stays authoritative."""
    win = _win()
    win._maybe_notify = lambda *a: None
    workspace = Workspace(workspace_id="alpha", branch="alpha", workspace_dir="/t", repos=[],
                state=SessionState.ACTIVE,
                terminals=[TerminalRecord("alpha:t0", "agent", status="running")])
    record = workspace.terminals[0]
    win._escalate_waiting(workspace, "alpha:t0", str(tmp_path / "sf.json"))
    path = _state_file(tmp_path, "running", record.status_ts + 1)
    win._apply_state_file(workspace, record, path)
    assert record.status == "running"


def test_escalate_routes_through_notify_gate():
    """The scanner usually beats the hook's Notification event; without this the
    later hook write sees old == waiting and D-08 would never fire."""
    win = _win()
    calls = []
    win._maybe_notify = lambda ws, rec, old, new, doc: calls.append((old, new))
    workspace = Workspace(workspace_id="alpha", branch="alpha", workspace_dir="/t", repos=[],
                state=SessionState.ACTIVE,
                terminals=[TerminalRecord("alpha:t0", "agent", status="running")])
    win._escalate_waiting(workspace, "alpha:t0", "/sf.json")
    assert calls == [("running", "waiting")]


def test_main_split_scanner_green_survives_batched_older_stop(tmp_path):
    """User report 2026-07-02: Gio.FileMonitor batches events, so the Stop(ready)
    doc can be DELIVERED after the scanner already painted busy-green — on a
    static pane (frozen banner, clipped agents strip) nothing repaints and the
    blue would stick. The preserve guard must also cover the main-split path."""
    win = _win()
    dot, leaf = _FakeWidget(), _FakeWidget()
    stop_ts = time.time() - 5
    sf = tmp_path / "sf.json"
    sf.write_text(json.dumps(
        {"state": "ready", "ts": stop_ts, "event": "Stop", "pid": os.getpid()}
    ))
    win._main_split_info[str(sf)] = {
        "root": "/projA", "tid": "main:t2", "dot": dot, "leaf": leaf,
        "status": "ready", "status_ts": stop_ts,
    }
    win._scan_set_status(None, "main:t2", str(sf),
                         AgentStatus.RUNNING.value, win._SCAN_FROM_CALM)
    assert win._main_split_info[str(sf)]["status"] == "running"
    # late batched delivery of the OLDER Stop doc — must NOT paint blue.
    win._apply_main_state_file(str(sf))
    assert win._main_split_info[str(sf)]["status"] == "running"
    assert dot.has_css_class("arduis-dot-active")
    # a genuinely NEWER hook event stays authoritative.
    sf.write_text(json.dumps(
        {"state": "ready", "ts": time.time() + 1, "event": "Stop", "pid": os.getpid()}
    ))
    win._apply_main_state_file(str(sf))
    assert win._main_split_info[str(sf)]["status"] == "ready"
    assert dot.has_css_class("arduis-dot-ready")


# --- liveness probe: the hook pid IS claude; the pgid is only the pane shell ----

# --- background-busy banner wiring: _scan_set_status ------------------------

from arduis.attention import AgentStatus  # noqa: E402


def _busy_workspace(status):
    return Workspace(workspace_id="alpha", branch="alpha", workspace_dir="/t", repos=[],
                     state=SessionState.ACTIVE,
                     terminals=[TerminalRecord("alpha:t0", "agent", status=status)])


def test_busy_flip_ready_to_running_lights_green():
    win = _win()
    workspace = _busy_workspace("ready")
    win._scan_set_status(workspace, "alpha:t0", "/sf.json",
                         AgentStatus.RUNNING.value, win._SCAN_FROM_CALM)
    assert workspace.terminals[0].status == "running"
    assert workspace.terminals[0].status_ts is not None


def test_busy_flip_refuses_from_waiting():
    # the busy flip is calm-only: an orange approval must never be repainted
    # green by the banner.
    win = _win()
    workspace = _busy_workspace("waiting")
    win._scan_set_status(workspace, "alpha:t0", "/sf.json",
                         AgentStatus.RUNNING.value, win._SCAN_FROM_CALM)
    assert workspace.terminals[0].status == "waiting"


def test_unbusy_flip_running_back_to_ready():
    win = _win()
    workspace = _busy_workspace("running")
    win._scan_set_status(workspace, "alpha:t0", "/sf.json",
                         AgentStatus.READY.value, (AgentStatus.RUNNING.value,))
    assert workspace.terminals[0].status == "ready"
    assert win._row_by_sid["alpha"].has_css_class("arduis-row-attention-ready")


def test_busy_flip_main_split_updates_dot_and_rings():
    win = _win()
    dot, leaf = _FakeWidget(), _FakeWidget()
    leaf.add_css_class("attention-ready")
    win._main_split_info["/sf.json"] = {
        "root": "/projA", "tid": "main:t1", "dot": dot, "leaf": leaf,
        "status": "ready",
    }
    win._scan_set_status(None, "main:t1", "/sf.json",
                         AgentStatus.RUNNING.value, win._SCAN_FROM_CALM)
    assert win._main_split_info["/sf.json"]["status"] == "running"
    assert dot.has_css_class("arduis-dot-active")
    assert not leaf.has_css_class("attention-ready")


def test_pid_alive_prefers_hook_pid_over_pane_pgid():
    """A SIGKILL'd claude must read dead even while the pane's zsh (the record
    pgid) is still alive — otherwise running/waiting sticks forever."""
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    record = TerminalRecord("alpha:t0", "agent", pgid=os.getpgrp())  # pane alive
    child = subprocess.Popen([sys.executable, "-c", ""])
    child.wait()  # reaped → the pid is gone

    class _Doc:
        pid = child.pid

    assert win._pid_alive(record, _Doc()) is False
    # with no hook pid the pane pgid remains the fallback.
    class _NoPid:
        pid = None

    assert win._pid_alive(record, _NoPid()) is True
