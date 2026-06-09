"""RED contract tests for the GTK-free active-agent cap policy (``arduis.caps``).

Pins the cap policy Plan 03-03 must satisfy. Fails now (RED) because
``arduis.caps`` does not exist yet.

Decisions pinned:
- D-15: ``ACTIVE_CAP_DEFAULT == 6`` — a single, Phase-6-sourceable constant
  (Phase 6 will let ``.arduis.toml`` override it; Phase 3 uses this default).
- D-16: ``at_cap`` triggers the prompt with ``>=`` (active_count >= cap), counting
  only sessions whose state is ACTIVE.
"""
from arduis import caps
from arduis.caps import ACTIVE_CAP_DEFAULT, active_count, at_cap
from arduis.session import SessionState, WorktreeSession


def _session(sid: str, state: SessionState) -> WorktreeSession:
    return WorktreeSession(
        session_id=sid,
        branch=sid,
        worktree_dir=f"/home/u/repo-{sid}",
        repo_root="/home/u/repo",
        state=state,
    )


def _active(n: int) -> list[WorktreeSession]:
    return [_session(f"a{i}", SessionState.ACTIVE) for i in range(n)]


def test_active_cap_default():
    # D-15: single Phase-6-sourceable constant, default ~6.
    assert ACTIVE_CAP_DEFAULT == 6


def test_active_count():
    sessions = [
        _session("a", SessionState.ACTIVE),
        _session("b", SessionState.HIBERNATED),
        _session("c", SessionState.ACTIVE),
        _session("d", SessionState.HIBERNATED),
    ]
    assert active_count(sessions) == 2


def test_at_cap_below():
    # 5 active, default cap 6 -> not at cap.
    assert at_cap(_active(5)) is False


def test_at_cap_at():
    # D-16: exactly 6 active -> at cap (>= triggers the prompt).
    assert at_cap(_active(6)) is True


def test_at_cap_custom():
    # configurable cap: 3 active with cap=3 -> at cap.
    assert at_cap(_active(3), cap=3) is True


def test_caps_is_gtk_free():
    with open(caps.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
