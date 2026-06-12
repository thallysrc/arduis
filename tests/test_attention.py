"""Tests for the GTK-free attention/status policy brain (Phase 4).

Pins the cardinal-sin rules: ``waiting`` is never silently downgraded by time
(Pitfall 2); a dead hook pid retires ``running``/``waiting`` to ``ended`` (Pitfall
5); a generous stale ceiling degrades only ``running`` to ``ready`` (Pitfall 7);
aggregation excludes shell terminals and fileless agents (Pitfall 8); a hostile
term_id yields a flat in-dir leaf (T-04-06); ``read_state`` swallows every parse
failure (T-04-07); ``clear_status_dir`` unlinks only plain files, never following
symlinks or recursing (T-04-11).
"""
import json
import os

from arduis import attention
from arduis.attention import (
    AgentStatus,
    StateDoc,
    aggregate_task,
    clear_status_dir,
    effective_status,
    read_state,
    sanitize_term_id,
    state_file_path,
    status_dir,
)
from arduis.session import TerminalRecord


# --- AgentStatus ---------------------------------------------------------------
def test_agent_status_values():
    assert AgentStatus.RUNNING.value == "running"
    assert AgentStatus.WAITING.value == "waiting"
    assert AgentStatus.READY.value == "ready"
    assert AgentStatus.IDLE.value == "idle"
    assert AgentStatus.ENDED.value == "ended"


# --- status_dir (D-04) ---------------------------------------------------------
def test_status_dir_xdg_runtime():
    d = status_dir({"XDG_RUNTIME_DIR": "/run/user/1000"})
    assert d == "/run/user/1000/arduis/status"


def test_status_dir_home_fallback():
    d = status_dir({"HOME": "/home/u"})
    assert d == "/home/u/.cache/arduis/status"


# --- sanitize / state_file_path (T-04-06) --------------------------------------
def test_state_file_path_keeps_colon_replaces_slash():
    p = state_file_path("/run/x", "feat/x:t0")
    assert p == "/run/x/feat-x:t0.json"


def test_state_file_path_hostile_id_is_flat_leaf():
    # T-04-06: a traversal-shaped term_id must yield a flat leaf inside dir.
    d = "/run/user/1000/arduis/status"
    p = state_file_path(d, "../../etc:t0")
    assert os.path.dirname(p) == d  # never escapes the status dir
    leaf = os.path.basename(p)
    assert os.sep not in leaf
    assert ".." not in leaf


def test_sanitize_never_empty_or_traversal():
    # The invariant is: result is never "", ".", ".." and never holds a separator.
    for hostile in ("..", "", "///", "../..", "."):
        out = sanitize_term_id(hostile)
        assert out not in ("", ".", "..")
        assert os.sep not in out
        assert ".." not in out
    # an all-unsafe input still yields a non-empty leaf fallback.
    assert sanitize_term_id("") == "term"


# --- clear_status_dir (T-04-11, Pitfall 5) -------------------------------------
def test_clear_status_dir_unlinks_files_ignores_subdir_and_symlink(tmp_path):
    d = tmp_path / "status"
    d.mkdir()
    (d / "x.json").write_text("{}")
    (d / ".arduis-tmpABC").write_text("leftover")
    sub = d / "sub"
    sub.mkdir()
    (sub / "keep.json").write_text("{}")
    # a symlink pointing OUTSIDE the dir must not be followed/deleted-through.
    outside = tmp_path / "outside.json"
    outside.write_text("precious")
    link = d / "link.json"
    os.symlink(outside, link)

    clear_status_dir(str(d))

    assert not (d / "x.json").exists()
    assert not (d / ".arduis-tmpABC").exists()
    assert sub.is_dir()  # subdir untouched (no recursion)
    assert (sub / "keep.json").exists()
    assert outside.read_text() == "precious"  # symlink target never followed
    assert not link.is_symlink() or outside.exists()  # link itself left or removed harmlessly


def test_clear_status_dir_missing_is_noop_creates(tmp_path):
    d = tmp_path / "nope" / "status"
    clear_status_dir(str(d))
    assert d.is_dir()


# --- read_state (T-04-07) ------------------------------------------------------
def test_read_state_roundtrips(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(
        json.dumps(
            {
                "state": "ready",
                "ts": 1760000000.0,
                "event": "Stop",
                "session_id": "abc",
                "cwd": "/x",
                "message": "done",
                "pid": 12345,
            }
        )
    )
    doc = read_state(str(p))
    assert doc is not None
    assert doc.state == "ready"
    assert doc.ts == 1760000000.0
    assert doc.event == "Stop"
    assert doc.message == "done"
    assert doc.pid == 12345


def test_read_state_missing_file_none(tmp_path):
    assert read_state(str(tmp_path / "absent.json")) is None


def test_read_state_empty_file_none(tmp_path):
    p = tmp_path / "e.json"
    p.write_text("")
    assert read_state(str(p)) is None


def test_read_state_garbage_none(tmp_path):
    p = tmp_path / "g.json"
    p.write_bytes(b"\x00\xff not json {{{")
    assert read_state(str(p)) is None


def test_read_state_missing_state_key_none(tmp_path):
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"ts": 1.0, "event": "Stop"}))
    assert read_state(str(p)) is None


# --- effective_status (D-03, Pitfalls 5/6/7) -----------------------------------
def _doc(state, ts, pid=999):
    return StateDoc(state=state, ts=ts, event="", message="", pid=pid)


def test_effective_ready_to_idle_threshold():
    idle_after = 600.0  # 10 min
    assert (
        effective_status(_doc("ready", 0.0), now=599.0, pid_alive=True, idle_after_s=idle_after)
        == AgentStatus.READY
    )
    assert (
        effective_status(_doc("ready", 0.0), now=600.0, pid_alive=True, idle_after_s=idle_after)
        == AgentStatus.IDLE
    )


def test_effective_running_dead_pid_ended():
    # Pitfall 5: SIGKILL'd claude never fired SessionEnd.
    assert (
        effective_status(_doc("running", 0.0), now=1.0, pid_alive=False, idle_after_s=600.0)
        == AgentStatus.ENDED
    )


def test_effective_running_stale_degrades_to_ready():
    # Pitfall 7: phantom-running guard, generous ceiling.
    assert (
        effective_status(
            _doc("running", 0.0), now=7201.0, pid_alive=True, idle_after_s=600.0
        )
        == AgentStatus.READY
    )


def test_effective_running_fresh_stays_running():
    assert (
        effective_status(_doc("running", 0.0), now=5.0, pid_alive=True, idle_after_s=600.0)
        == AgentStatus.RUNNING
    )


def test_effective_waiting_never_degrades_by_time():
    # Cardinal rule (Pitfall 2): waiting stays waiting at any age while pid alive.
    assert (
        effective_status(
            _doc("waiting", 0.0), now=10 ** 9, pid_alive=True, idle_after_s=600.0
        )
        == AgentStatus.WAITING
    )


def test_effective_waiting_dead_pid_ended():
    assert (
        effective_status(_doc("waiting", 0.0), now=10.0, pid_alive=False, idle_after_s=600.0)
        == AgentStatus.ENDED
    )


def test_effective_ended_stays_ended():
    assert (
        effective_status(_doc("ended", 0.0), now=10.0, pid_alive=True, idle_after_s=600.0)
        == AgentStatus.ENDED
    )


# --- aggregate_task (D-06, Pitfall 8) ------------------------------------------
def _agent(status):
    r = TerminalRecord("feat:t0", "agent")
    r.status = status
    return r


def _shell(status=None):
    r = TerminalRecord("feat:t1", "shell")
    r.status = status
    return r


def test_aggregate_precedence():
    assert aggregate_task([_agent("ready"), _agent("waiting"), _agent("running")]) == AgentStatus.WAITING
    assert aggregate_task([_agent("ready"), _agent("running")]) == AgentStatus.RUNNING
    assert aggregate_task([_agent("ready"), _agent("idle")]) == AgentStatus.READY
    assert aggregate_task([_agent("idle"), _agent("ended")]) == AgentStatus.IDLE
    assert aggregate_task([_agent("ended")]) == AgentStatus.ENDED


def test_aggregate_excludes_shell_terminals():
    # Pitfall 8: a shell never contributes even if a status is somehow set.
    assert aggregate_task([_shell("waiting"), _agent("ready")]) == AgentStatus.READY


def test_aggregate_excludes_none_status_agents():
    # an agent that never produced a file (status None) has no opinion.
    assert aggregate_task([_agent("ready"), _agent(None)]) == AgentStatus.READY


def test_aggregate_all_none_or_empty_is_none():
    assert aggregate_task([]) is None
    assert aggregate_task([_agent(None), _shell(None)]) is None
    assert aggregate_task([_shell("waiting")]) is None  # only shells -> no opinion


# --- GTK-free assertion --------------------------------------------------------
def test_attention_module_is_gtk_free():
    with open(attention.__file__, encoding="utf-8") as fh:
        assert "import gi" not in fh.read()
