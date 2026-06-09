"""Wave-0 RED contract for the GTK-free SessionStore domain layer.

Pins the pure (stdlib-only) API of `src/arduis/session.py`, which Plan 01
implements. Until then this file is RED (ModuleNotFoundError at import).

Decision IDs covered:
- D-08 / Pitfall 1: the agent feed MUST be `bytes` (`b"claude\n"`); a `str`
  raises TypeError on the VTE 0.76 `feed_child` binding.
- D-11: hibernate clears pid/pgid, sets state HIBERNATED, KEEPS worktree_dir.
- D-13: SessionStore is GTK-free + serializable, with RAM fields (rss_kb)
  on the model from day one (unpopulated in Phase 2).
"""
import json

from arduis.session import (
    AGENT_FEED,
    SessionState,
    WorktreeSession,
    SessionStore,
    hibernate_fields,
)


def test_agent_feed_is_bytes():
    # D-08 / Pitfall 1: str raises TypeError on the 0.76 feed_child binding.
    assert isinstance(AGENT_FEED, bytes)
    assert AGENT_FEED == b"claude\n"


def test_store_serializable():
    # D-13: GTK-free, serializable store; day-one RAM field rss_kb present.
    store = SessionStore()
    session = WorktreeSession(
        session_id="feat",
        branch="feat",
        worktree_dir="/p/r-feat",
        repo_root="/p/r",
    )
    store.add(session)

    assert store.get("feat") is session
    assert store.by_branch("feat") is session
    assert len(store.all()) == 1

    listed = store.to_list()
    assert isinstance(listed, list)
    # JSON-roundtrippable proves GTK-free serializability (no gi objects).
    json.dumps(listed)

    d = listed[0]
    for key in (
        "session_id",
        "branch",
        "worktree_dir",
        "repo_root",
        "state",
        "pid",
        "pgid",
        "rss_kb",
    ):
        assert key in d


def test_hibernate_model():
    # D-11: hibernate model transition — clear pid/pgid, state HIBERNATED,
    # keep worktree_dir; rss_kb field still present (defaults None).
    session = WorktreeSession(
        session_id="feat",
        branch="feat",
        worktree_dir="/p/r-feat",
        repo_root="/p/r",
        state=SessionState.ACTIVE,
        pid=1234,
        pgid=1234,
    )

    hibernate_fields(session)

    assert session.state == SessionState.HIBERNATED
    assert session.pid is None
    assert session.pgid is None
    assert session.worktree_dir == "/p/r-feat"  # dir kept (D-11)
    assert session.rss_kb is None  # RAM field present, unpopulated
