"""Tests for the GTK-free serializable SessionStore (WT-03/RAM-01/PAR-01/RAM-03).

Contract: ``AGENT_FEED`` is the bytes literal ``b"claude\\n"`` (D-08, Pitfall 1
- ``feed_child`` rejects str at the 0.76 floor); each worktree owns a LIST of
terminals (default 2 — one ``agent``, one ``shell`` — D-02/D-03); the store is
JSON-serializable via ``asdict`` (D-13/A2) and recurses into the terminals list;
hibernate clears EVERY terminal's pid/pgid while KEEPING the directory (D-08/D-11,
Pitfall 3 — no group forgotten so RAM can't leak).
"""
import json

from arduis import session
from arduis.session import (
    AGENT_FEED,
    SessionState,
    SessionStore,
    TerminalRecord,
    WorktreeSession,
    default_terminals,
    hibernate_fields,
)


def test_agent_feed_is_bytes():
    # D-08 / Pitfall 1: must be bytes, not str (0.76 feed_child TypeError on str)
    assert AGENT_FEED == b"claude\n"
    assert isinstance(AGENT_FEED, bytes)


def test_default_terminals():
    # D-02/D-03: a worktree's default is exactly 2 terminals — agent + shell.
    terms = default_terminals("feat")
    assert len(terms) == 2
    assert terms[0].term_id == "feat:t0"
    assert terms[0].kind == "agent"
    assert terms[1].term_id == "feat:t1"
    assert terms[1].kind == "shell"
    # a session created via the default-terminals path carries the 2-terminal list
    s = WorktreeSession(
        session_id="feat",
        branch="feat",
        worktree_dir="/home/u/repo-feat",
        repo_root="/home/u/repo",
        terminals=default_terminals("feat"),
    )
    assert len(s.terminals) == 2


def test_hibernate_clears_all_terminals():
    # Pitfall 3: hibernate must clear EVERY terminal's pgid so no group leaks.
    s = WorktreeSession(
        session_id="feat",
        branch="feat",
        worktree_dir="/home/u/repo-feat",
        repo_root="/home/u/repo",
        terminals=[
            TerminalRecord("feat:t0", "agent", pid=4242, pgid=4242, rss_kb=12345),
            TerminalRecord("feat:t1", "shell", pid=4243, pgid=4243, rss_kb=200),
            TerminalRecord("feat:t2", "shell", pid=4244, pgid=4244, rss_kb=50),
        ],
    )
    hibernate_fields(s)
    assert s.state == SessionState.HIBERNATED
    # every terminal's pid AND pgid cleared (no group forgotten)
    for t in s.terminals:
        assert t.pid is None
        assert t.pgid is None
    # D-08: directory kept on disk
    assert s.worktree_dir == "/home/u/repo-feat"
    assert s.repo_root == "/home/u/repo"


def test_store_serializable():
    store = SessionStore()
    s = WorktreeSession(
        session_id="feat",
        branch="feat",
        worktree_dir="/home/u/repo-feat",
        repo_root="/home/u/repo",
        terminals=[
            TerminalRecord("feat:t0", "agent", pid=4242, pgid=4242, rss_kb=12345),
            TerminalRecord("feat:t1", "shell", pid=4243, pgid=4243, rss_kb=200),
        ],
    )
    store.add(s)
    # CRUD
    assert store.get("feat") is s
    assert store.by_branch("feat") is s
    assert store.by_branch("absent") is None
    assert store.all() == [s]
    # serializable: asdict recurses into the terminals list (A2)
    as_list = store.to_list()
    assert as_list[0]["state"] == "active"
    terms = as_list[0]["terminals"]
    assert isinstance(terms, list)
    assert terms[0] == {
        "term_id": "feat:t0",
        "kind": "agent",
        "pid": 4242,
        "pgid": 4242,
        "rss_kb": 12345,
    }
    assert set(terms[0].keys()) == {"term_id", "kind", "pid", "pgid", "rss_kb"}
    json.dumps(as_list)  # must not raise


def test_hibernate_model():
    s = WorktreeSession(
        session_id="feat",
        branch="feat",
        worktree_dir="/home/u/repo-feat",
        repo_root="/home/u/repo",
        terminals=[
            TerminalRecord("feat:t0", "agent", pid=4242, pgid=4242, rss_kb=12345),
            TerminalRecord("feat:t1", "shell", pid=4243, pgid=4243, rss_kb=200),
        ],
    )
    hibernate_fields(s)
    assert s.state == SessionState.HIBERNATED
    for t in s.terminals:
        assert t.pgid is None
    # D-08: directory kept on disk
    assert s.worktree_dir == "/home/u/repo-feat"
    assert s.repo_root == "/home/u/repo"
    # serializes cleanly post-hibernate
    assert s.to_dict()["state"] == "hibernated"


def test_session_module_is_gtk_free():
    # the domain module must not import gi
    src = session.__file__
    with open(src, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
