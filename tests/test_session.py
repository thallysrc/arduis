"""Tests for the GTK-free serializable SessionStore (WT-03/RAM-01).

Contract: ``AGENT_FEED`` is the bytes literal ``b"claude\\n"`` (D-08, Pitfall 1
- ``feed_child`` rejects str at the 0.76 floor); the store is JSON-serializable
via ``asdict`` (D-13) and carries the ``rss_kb`` RAM field from day one; the
hibernate transition clears pid/pgid and flips state while KEEPING the directory
(D-11).
"""
import json

from arduis import session
from arduis.session import (
    AGENT_FEED,
    SessionState,
    SessionStore,
    WorktreeSession,
    hibernate_fields,
)


def test_agent_feed_is_bytes():
    # D-08 / Pitfall 1: must be bytes, not str (0.76 feed_child TypeError on str)
    assert AGENT_FEED == b"claude\n"
    assert isinstance(AGENT_FEED, bytes)


def test_store_serializable():
    store = SessionStore()
    s = WorktreeSession(
        session_id="feat",
        branch="feat",
        worktree_dir="/home/u/repo-feat",
        repo_root="/home/u/repo",
    )
    store.add(s)
    # CRUD
    assert store.get("feat") is s
    assert store.by_branch("feat") is s
    assert store.by_branch("absent") is None
    assert store.all() == [s]
    # RAM field present from day one (D-13)
    assert s.rss_kb is None
    # serializable: str-Enum dumps as its value, whole store is JSON-round-trippable
    as_list = store.to_list()
    assert as_list[0]["state"] == "active"
    assert as_list[0]["rss_kb"] is None
    json.dumps(as_list)  # must not raise


def test_hibernate_model():
    s = WorktreeSession(
        session_id="feat",
        branch="feat",
        worktree_dir="/home/u/repo-feat",
        repo_root="/home/u/repo",
        pid=4242,
        pgid=4242,
        rss_kb=12345,
    )
    hibernate_fields(s)
    assert s.state == SessionState.HIBERNATED
    assert s.pid is None
    assert s.pgid is None
    # D-11: directory kept on disk; rss_kb left untouched
    assert s.worktree_dir == "/home/u/repo-feat"
    assert s.repo_root == "/home/u/repo"
    assert s.rss_kb == 12345
    # serializes cleanly post-hibernate
    assert s.to_dict()["state"] == "hibernated"


def test_session_module_is_gtk_free():
    # the domain module must not import gi
    src = session.__file__
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
