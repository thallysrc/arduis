"""Subprocess round-trip tests of the arduis attention hook (STATUS-01, D-01/D-03/D-04).

Each test runs the REAL script the way claude executes it: stdin JSON + inherited
env via ``subprocess.run([sys.executable, SCRIPT], input=..., env=...)``. This is the
production contract, not a shortcut — the env guard, the 7-event map, atomicity, and the
never-block-claude (returncode == 0 ALWAYS) invariant are all pinned here, GTK-free.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Source of truth: the script lives in the app package (Plan 03 installs a copy at a
# stable path; here we exercise the package copy directly).
SCRIPT = Path(__file__).resolve().parents[1] / "src" / "arduis" / "hooks" / "arduis_hook.py"


def run_hook(
    payload: dict | bytes | None,
    state_file: str | None,
    tmp: Path,
    directive: str | None = None,
) -> subprocess.CompletedProcess:
    """Run the hook as claude would: stdin JSON + a copied env.

    ``payload`` may be a dict (json-encoded), raw bytes (garbage stdin), or None
    (empty stdin). ``state_file`` None drops ARDUIS_STATE_FILE entirely (no-env case).
    ``directive`` is the Notification argv word arduis registers per settings
    matcher (attention.NOTIFICATION_MATCHERS) — the payload carries NO
    notification-type field.
    """
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp),
    }
    if state_file is not None:
        env["ARDUIS_STATE_FILE"] = state_file

    if payload is None:
        stdin: bytes = b""
    elif isinstance(payload, bytes):
        stdin = payload
    else:
        stdin = json.dumps(payload).encode()

    argv = [sys.executable, str(SCRIPT)]
    if directive is not None:
        argv.append(directive)
    return subprocess.run(
        argv,
        input=stdin,
        env=env,
        capture_output=True,
        timeout=10,
    )


def _read(state_file: Path) -> dict:
    with open(state_file) as f:
        return json.load(f)


# --------------------------------------------------------------------------- #
# Env guard (D-01)
# --------------------------------------------------------------------------- #

def test_no_env_is_noop_and_leaves_dir_empty(tmp_path):
    """No ARDUIS_STATE_FILE → exit 0, tmp stays EMPTY (no file, no .arduis-* droppings)."""
    cp = run_hook({"hook_event_name": "SessionStart"}, state_file=None, tmp=tmp_path)
    assert cp.returncode == 0
    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------- #
# Event map (D-03, research Pattern 1)
# --------------------------------------------------------------------------- #

def test_session_start_maps_to_ready(tmp_path):
    sf = tmp_path / "x.json"
    cp = run_hook({"hook_event_name": "SessionStart"}, str(sf), tmp_path)
    assert cp.returncode == 0
    assert _read(sf)["state"] == "ready"  # see plan_decisions (D-03 wording resolution)


def test_user_prompt_submit_maps_to_running(tmp_path):
    sf = tmp_path / "x.json"
    cp = run_hook({"hook_event_name": "UserPromptSubmit"}, str(sf), tmp_path)
    assert cp.returncode == 0
    assert _read(sf)["state"] == "running"


def test_notification_waiting_directive_maps_to_waiting(tmp_path):
    """The permission_prompt/elicitation_dialog matchers register the 'waiting'
    argv directive — that is what flips the orange dot."""
    sf = tmp_path / "x.json"
    cp = run_hook(
        {"hook_event_name": "Notification"}, str(sf), tmp_path, directive="waiting"
    )
    assert cp.returncode == 0
    assert _read(sf)["state"] == "waiting"


def test_notification_without_directive_writes_nothing(tmp_path):
    """A matcher-less Notification registration (the pre-matcher arduis shape, or
    a foreign one) carries no directive → the hook must write NOTHING: the
    payload has no notification-type field to decide from."""
    sf = tmp_path / "x.json"
    cp = run_hook({"hook_event_name": "Notification"}, str(sf), tmp_path)
    assert cp.returncode == 0
    assert not sf.exists()
    assert list(tmp_path.iterdir()) == []


def test_idle_prompt_upgrades_running_to_ready(tmp_path):
    """Pitfall 7 self-heal: the idle_prompt matcher ('ready' directive) over an
    existing 'running' → 'ready'."""
    sf = tmp_path / "x.json"
    sf.write_text(json.dumps({"state": "running"}))
    cp = run_hook(
        {"hook_event_name": "Notification"}, str(sf), tmp_path, directive="ready"
    )
    assert cp.returncode == 0
    assert _read(sf)["state"] == "ready"


def test_idle_prompt_never_downgrades_waiting(tmp_path):
    """Pitfall 2 — the cardinal sin guard: idle_prompt must NOT clear a real 'waiting'."""
    sf = tmp_path / "x.json"
    sf.write_text(json.dumps({"state": "waiting", "message": "approve?"}))
    cp = run_hook(
        {"hook_event_name": "Notification"}, str(sf), tmp_path, directive="ready"
    )
    assert cp.returncode == 0
    # File UNCHANGED — still waiting.
    assert _read(sf)["state"] == "waiting"


def test_idle_prompt_with_no_existing_file_writes_nothing(tmp_path):
    """idle_prompt with NO prior file → exit 0, no file written (nothing to upgrade)."""
    sf = tmp_path / "x.json"
    cp = run_hook(
        {"hook_event_name": "Notification"}, str(sf), tmp_path, directive="ready"
    )
    assert cp.returncode == 0
    assert not sf.exists()
    assert list(tmp_path.iterdir()) == []


def test_directive_does_not_leak_into_other_events(tmp_path):
    """A stray directive on a non-Notification event must not change its state."""
    sf = tmp_path / "x.json"
    cp = run_hook({"hook_event_name": "Stop"}, str(sf), tmp_path, directive="waiting")
    assert cp.returncode == 0
    assert _read(sf)["state"] == "ready"


def test_post_tool_use_maps_to_running(tmp_path):
    """Pitfall 3: PostToolUse clears 'waiting' after approval → 'running'."""
    sf = tmp_path / "x.json"
    sf.write_text(json.dumps({"state": "waiting"}))
    cp = run_hook({"hook_event_name": "PostToolUse"}, str(sf), tmp_path)
    assert cp.returncode == 0
    assert _read(sf)["state"] == "running"


def test_post_tool_use_failure_maps_to_running(tmp_path):
    sf = tmp_path / "x.json"
    cp = run_hook({"hook_event_name": "PostToolUseFailure"}, str(sf), tmp_path)
    assert cp.returncode == 0
    assert _read(sf)["state"] == "running"


def test_stop_maps_to_ready(tmp_path):
    sf = tmp_path / "x.json"
    cp = run_hook({"hook_event_name": "Stop"}, str(sf), tmp_path)
    assert cp.returncode == 0
    assert _read(sf)["state"] == "ready"


def test_session_end_maps_to_ended(tmp_path):
    sf = tmp_path / "x.json"
    cp = run_hook({"hook_event_name": "SessionEnd"}, str(sf), tmp_path)
    assert cp.returncode == 0
    assert _read(sf)["state"] == "ended"


def test_unknown_event_is_noop(tmp_path):
    """Unknown event (e.g. PreCompact) → exit 0, no file."""
    sf = tmp_path / "x.json"
    cp = run_hook({"hook_event_name": "PreCompact"}, str(sf), tmp_path)
    assert cp.returncode == 0
    assert not sf.exists()
    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------- #
# Payload shape (D-04)
# --------------------------------------------------------------------------- #

def test_payload_has_expected_keys_and_types(tmp_path):
    sf = tmp_path / "x.json"
    before = time.time()
    cp = run_hook(
        {
            "hook_event_name": "UserPromptSubmit",
            "session_id": "sess-123",
            "cwd": "/some/where",
            "message": "hi",
        },
        str(sf),
        tmp_path,
    )
    after = time.time()
    assert cp.returncode == 0
    doc = _read(sf)
    assert set(doc) >= {"state", "ts", "event", "session_id", "cwd", "message", "pid"}
    assert doc["state"] == "running"
    assert doc["event"] == "UserPromptSubmit"
    assert doc["session_id"] == "sess-123"
    assert doc["cwd"] == "/some/where"
    assert isinstance(doc["ts"], float)
    # ts ~ now (allow ±60s clock slack)
    assert before - 60 <= doc["ts"] <= after + 60
    # pid is the SUBPROCESS's getppid(), not the test runner's — assert positive int only.
    assert isinstance(doc["pid"], int)
    assert doc["pid"] > 0


def test_notification_message_lands_in_file(tmp_path):
    """The notification body 'message' feeds the desktop notification → preserved."""
    sf = tmp_path / "x.json"
    cp = run_hook(
        {
            "hook_event_name": "Notification",
            "message": "Allow Bash to run?",
        },
        str(sf),
        tmp_path,
        directive="waiting",
    )
    assert cp.returncode == 0
    assert _read(sf)["message"] == "Allow Bash to run?"


# --------------------------------------------------------------------------- #
# Robustness — never block claude
# --------------------------------------------------------------------------- #

def test_garbage_stdin_does_not_crash(tmp_path):
    sf = tmp_path / "x.json"
    cp = run_hook(b"not json{{", str(sf), tmp_path)
    assert cp.returncode == 0
    # No derivable event → no file written.
    assert not sf.exists()


def test_empty_stdin_does_not_crash(tmp_path):
    sf = tmp_path / "x.json"
    cp = run_hook(None, str(sf), tmp_path)
    assert cp.returncode == 0
    assert not sf.exists()


def test_unwritable_target_dir_is_swallowed(tmp_path):
    """ARDUIS_STATE_FILE under a child of a regular FILE → write fails → exit 0."""
    blocker = tmp_path / "f"
    blocker.write_text("i am a file, not a dir")
    sf = blocker / "x.json"  # cannot makedirs under a regular file
    cp = run_hook({"hook_event_name": "Stop"}, str(sf), tmp_path)
    assert cp.returncode == 0
    assert not sf.exists()


def test_missing_parent_dirs_are_created(tmp_path):
    sf = tmp_path / "a" / "b" / "x.json"
    cp = run_hook({"hook_event_name": "Stop"}, str(sf), tmp_path)
    assert cp.returncode == 0
    assert sf.exists()
    assert _read(sf)["state"] == "ready"


# --------------------------------------------------------------------------- #
# Atomicity
# --------------------------------------------------------------------------- #

def test_write_leaves_no_temp_droppings(tmp_path):
    sf = tmp_path / "x.json"
    cp = run_hook({"hook_event_name": "Stop"}, str(sf), tmp_path)
    assert cp.returncode == 0
    names = {p.name for p in tmp_path.iterdir()}
    assert names == {"x.json"}
    assert not any(n.startswith(".arduis-") for n in names)


def test_script_is_stdlib_only_and_uses_os_replace():
    src = SCRIPT.read_text()
    assert "os.replace" in src
    assert "import gi" not in src
    # Only json/os/sys/tempfile/time imported — assert each, and no third-party import.
    import_lines = [
        ln.strip()
        for ln in src.splitlines()
        if ln.strip().startswith(("import ", "from "))
    ]
    allowed = {
        "import json",
        "import os",
        "import sys",
        "import tempfile",
        "import time",
    }
    assert set(import_lines) == allowed, import_lines
