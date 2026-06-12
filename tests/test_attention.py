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
from pathlib import Path

import pytest

from arduis import attention
from arduis.attention import (
    HOOK_EVENTS,
    MATCHER_EVENTS,
    AgentStatus,
    AttentionConfig,
    StateDoc,
    aggregate_task,
    clear_status_dir,
    declined_marker_path,
    effective_status,
    hook_command,
    hook_script_source,
    install_target_path,
    is_installed,
    load_config,
    merged_settings,
    read_state,
    sanitize_term_id,
    should_autosuspend,
    should_notify,
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


# --- Hook install helpers + settings merge (Pattern 3, Pitfall 9, T-04-08) -----
SCRIPT = "/home/u/.local/share/arduis/hooks/arduis_status_hook.py"

# A DEEP fixture modeled on a real hooks-dense ~/.claude/settings.json: an existing
# notify-send Notification hook, an existing PostToolUse matcher group with a node
# command, plus unrelated top-level keys. NEVER read the real settings.json.
RICH_SETTINGS = {
    "model": "claude-sonnet-4-5",
    "permissions": {"allow": ["Bash(git status)"], "deny": []},
    "statusLine": {"type": "command", "command": "~/.claude/statusline.sh"},
    "hooks": {
        "Notification": [
            {"hooks": [{"type": "command", "command": "notify-send claude", "timeout": 5}]}
        ],
        "PostToolUse": [
            {
                "matcher": "*",
                "hooks": [{"type": "command", "command": "node /home/u/.gsd/hook.js"}],
            }
        ],
    },
}


def test_hook_command_absolute_expansion_free():
    cmd = hook_command(SCRIPT)
    assert cmd == f"/usr/bin/env python3 {SCRIPT}"
    assert "~" not in cmd and "$" not in cmd


def test_hook_command_rejects_relative():
    with pytest.raises(ValueError):
        hook_command("relative/x.py")


def test_hook_command_expands_tilde():
    cmd = hook_command("~/x.py")
    assert "~" not in cmd
    assert cmd.startswith("/usr/bin/env python3 ")
    assert cmd.endswith("/x.py")


def test_install_target_path():
    assert (
        install_target_path("/home/u")
        == "/home/u/.local/share/arduis/hooks/arduis_status_hook.py"
    )


def test_declined_marker_path():
    assert declined_marker_path("/home/u") == "/home/u/.local/share/arduis/hooks_declined"


def test_is_installed_partial_false():
    settings, _ = merged_settings({}, SCRIPT)
    # drop 2 of the 7 events -> partial -> not installed.
    del settings["hooks"]["Stop"]
    del settings["hooks"]["SessionEnd"]
    assert is_installed(settings, SCRIPT) is False


def test_is_installed_full_true():
    settings, _ = merged_settings({}, SCRIPT)
    assert is_installed(settings, SCRIPT) is True


def test_merge_additive_preserves_everything():
    original = json.loads(json.dumps(RICH_SETTINGS))  # snapshot for mutation check
    out, changed = merged_settings(RICH_SETTINGS, SCRIPT)
    assert changed is True
    # input not mutated (deepcopy semantics).
    assert RICH_SETTINGS == original
    # unrelated top-level keys preserved byte-identical.
    assert out["model"] == RICH_SETTINGS["model"]
    assert out["permissions"] == RICH_SETTINGS["permissions"]
    assert out["statusLine"] == RICH_SETTINGS["statusLine"]
    # the user's existing hook entries are preserved as the FIRST entry per event.
    assert out["hooks"]["Notification"][0] == RICH_SETTINGS["hooks"]["Notification"][0]
    assert out["hooks"]["PostToolUse"][0] == RICH_SETTINGS["hooks"]["PostToolUse"][0]
    # arduis appended exactly one group per event.
    assert len(out["hooks"]["Notification"]) == 2
    assert len(out["hooks"]["PostToolUse"]) == 2
    assert all(event in out["hooks"] for event in HOOK_EVENTS)


def test_merge_idempotent():
    once, c1 = merged_settings(RICH_SETTINGS, SCRIPT)
    twice, c2 = merged_settings(once, SCRIPT)
    assert c1 is True
    assert c2 is False
    assert twice == once


def test_merge_matcher_placement():
    out, _ = merged_settings({}, SCRIPT)
    for event in MATCHER_EVENTS:
        # the appended arduis group for a matcher event carries "matcher": "*".
        group = out["hooks"][event][-1]
        assert group.get("matcher") == "*"
    for event in set(HOOK_EVENTS) - set(MATCHER_EVENTS):
        group = out["hooks"][event][-1]
        assert "matcher" not in group


def test_merge_entry_shape():
    out, _ = merged_settings({}, SCRIPT)
    entry = out["hooks"]["Stop"][-1]["hooks"][0]
    assert entry == {
        "type": "command",
        "command": hook_command(SCRIPT),
        "timeout": 5,
    }


def test_merge_empty_input_all_events_and_unmutated():
    src: dict = {}
    out, changed = merged_settings(src, SCRIPT)
    assert changed is True
    assert src == {}  # input untouched
    for event in HOOK_EVENTS:
        assert event in out["hooks"]
        assert _event_has_command(out["hooks"][event], SCRIPT)


def test_merge_handles_missing_and_existing_hooks_key():
    # missing "hooks" key entirely.
    out1, c1 = merged_settings({"model": "x"}, SCRIPT)
    assert c1 is True and "hooks" in out1
    # existing "hooks" with some events present.
    base = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}]}}
    out2, c2 = merged_settings(base, SCRIPT)
    assert c2 is True
    # the pre-existing Stop entry is preserved; arduis appended after it.
    assert out2["hooks"]["Stop"][0]["hooks"][0]["command"] == "echo hi"
    assert len(out2["hooks"]["Stop"]) == 2


def _event_has_command(groups, script_path):
    return any(
        script_path in str(hook.get("command", ""))
        for group in groups
        for hook in group.get("hooks", [])
    )


@pytest.mark.skipif(
    not Path("src/arduis/hooks/arduis_hook.py").exists(),
    reason="04-01 not yet merged (parallel wave-1 plan owns src/arduis/hooks/arduis_hook.py)",
)
def test_hook_script_source_returns_packaged_content():
    src = hook_script_source()
    assert src
    assert "ARDUIS_STATE_FILE" in src


# --- should_notify (D-08) ------------------------------------------------------
def test_notify_fires_on_transition_into_waiting_unfocused():
    assert should_notify("running", "waiting", window_active=False) is True
    assert should_notify(None, "waiting", window_active=False) is True


def test_notify_no_refire_on_waiting_to_waiting():
    assert should_notify("waiting", "waiting", window_active=False) is False


def test_notify_focused_window_never_fires():
    # D-08: window has focus -> the user is already looking.
    assert should_notify("running", "waiting", window_active=True) is False


def test_notify_ready_behind_flag_default_off():
    assert should_notify("running", "ready", window_active=False, notify_ready=False) is False
    assert should_notify("running", "ready", window_active=False, notify_ready=True) is True
    # even with the flag on, a ready->ready re-write does not re-fire.
    assert should_notify("ready", "ready", window_active=False, notify_ready=True) is False


# --- should_autosuspend (RAM-04, D-12, Pitfall 6) ------------------------------
def test_autosuspend_off_when_minutes_zero():
    assert should_autosuspend(AgentStatus.READY, 0.0, now=10 ** 9, minutes=0) is False


def test_autosuspend_calm_past_threshold():
    minutes = 30
    threshold = minutes * 60
    for calm in (AgentStatus.READY, AgentStatus.IDLE, AgentStatus.ENDED):
        assert should_autosuspend(calm, 0.0, now=threshold, minutes=minutes) is True
        assert should_autosuspend(calm, 0.0, now=threshold - 1, minutes=minutes) is False


def test_autosuspend_never_running_or_waiting_at_any_age():
    # Pitfall 6 / T-04-09: a 30-min tool call (running) or a pending approval
    # (waiting) must NEVER be killed, no matter how old.
    huge = 10 ** 9
    assert should_autosuspend(AgentStatus.RUNNING, 0.0, now=huge, minutes=1) is False
    assert should_autosuspend(AgentStatus.WAITING, 0.0, now=huge, minutes=1) is False


def test_autosuspend_none_aggregate_or_calm_since_never_suspends():
    # Pitfall 8 chain: a fileless task (None aggregate) never suspends.
    assert should_autosuspend(None, 0.0, now=10 ** 9, minutes=30) is False
    assert should_autosuspend(AgentStatus.READY, None, now=10 ** 9, minutes=30) is False


# --- load_config (D-11, T-04-10) -----------------------------------------------
def test_load_config_missing_file_defaults(tmp_path):
    cfg = load_config(str(tmp_path / "absent.toml"))
    assert cfg == AttentionConfig()
    assert cfg.auto_suspend_minutes == 0  # OFF by default
    assert cfg.idle_minutes == 10
    assert cfg.notify_ready is False
    assert cfg.sound is False


def test_load_config_reads_values(tmp_path):
    p = tmp_path / "arduis.toml"
    p.write_text("[attention]\nauto_suspend_minutes = 30\nsound = true\n")
    cfg = load_config(str(p))
    assert cfg.auto_suspend_minutes == 30
    assert cfg.idle_minutes == 10  # untouched default
    assert cfg.notify_ready is False
    assert cfg.sound is True


def test_load_config_invalid_toml_defaults(tmp_path):
    p = tmp_path / "bad.toml"
    p.write_text("[attention\nthis is not = = toml")
    assert load_config(str(p)) == AttentionConfig()


def test_load_config_wrong_types_fall_back_per_key(tmp_path):
    p = tmp_path / "wrong.toml"
    # string minutes + negative minutes must not enable the killer feature.
    p.write_text(
        '[attention]\nauto_suspend_minutes = "lots"\nidle_minutes = -5\nsound = "yes"\n'
    )
    cfg = load_config(str(p))
    assert cfg.auto_suspend_minutes == 0  # string -> default 0
    assert cfg.idle_minutes == 0  # negative -> 0 (T-04-10)
    assert cfg.sound is False  # non-bool -> default


def test_load_config_no_attention_section_defaults(tmp_path):
    p = tmp_path / "other.toml"
    p.write_text("[other]\nkey = 1\n")
    assert load_config(str(p)) == AttentionConfig()


# --- GTK-free assertion --------------------------------------------------------
def test_attention_module_is_gtk_free():
    with open(attention.__file__, encoding="utf-8") as fh:
        assert "import gi" not in fh.read()
