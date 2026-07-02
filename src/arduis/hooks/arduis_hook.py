#!/usr/bin/env python3
"""arduis attention hook (STATUS-01, D-01/D-03/D-04).

Registered at user level in ~/.claude/settings.json for 7 events; a guaranteed
no-op unless ARDUIS_STATE_FILE is set in the environment (arduis injects it per
terminal via the VTE spawn envv). stdlib-only on purpose: it must run under
/usr/bin/env python3 anywhere, with no arduis package on the path.

It must NEVER block claude: every failure path exits 0 (exit 2 would block).
"""
import json
import os
import sys
import tempfile
import time


def main() -> None:
    state_file = os.environ.get("ARDUIS_STATE_FILE")
    if not state_file:
        return  # outside arduis: guaranteed no-op (D-01)

    try:
        payload = json.load(sys.stdin)
    except Exception:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    event = payload.get("hook_event_name", "")
    # D-03 map. SessionStart -> ready per 04-RESEARCH Pattern 1 (claude is at its
    # input prompt awaiting the first message); see plan 04-01 plan_decisions.
    simple = {
        "SessionStart": "ready",
        "UserPromptSubmit": "running",
        "PostToolUse": "running",          # clears waiting after approval (Pitfall 3)
        "PostToolUseFailure": "running",
        "Stop": "ready",
        "SessionEnd": "ended",
    }
    state = simple.get(event)
    if event == "Notification":
        # The Notification payload carries NO type field — the type is selected
        # by the settings-group "matcher" (hooks docs, verified 2026-07-02), so
        # arduis registers one group per matcher and the state to write arrives
        # as the argv directive (attention.NOTIFICATION_MATCHERS).
        directive = sys.argv[1] if len(sys.argv) > 1 else ""
        if directive == "waiting":
            state = "waiting"              # permission_prompt / elicitation_dialog
        elif directive == "ready":
            # idle_prompt — Pitfall 2: upgrade ONLY running -> ready; never
            # touch waiting.
            try:
                with open(state_file) as f:
                    if json.load(f).get("state") == "running":
                        state = "ready"
            except Exception:
                pass
    if state is None:
        return

    doc = {
        "state": state,
        "ts": time.time(),
        "event": event,
        "session_id": payload.get("session_id"),
        "cwd": payload.get("cwd"),
        "message": payload.get("message", ""),
        "pid": os.getppid(),               # claude's pid (D-04 staleness handle)
    }
    d = os.path.dirname(state_file)
    os.makedirs(d, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=d, prefix=".arduis-")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(doc, f)
        os.replace(tmp, state_file)        # atomic — readers never see partial JSON
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
    sys.exit(0)                            # NEVER block claude
