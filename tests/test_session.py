"""Tests for the GTK-free serializable SessionStore over Tasks (03.2 pivot).

Contract: ``AGENT_FEED`` is the bytes literal ``b"claude\\n"`` (D-08, Pitfall 1 —
``feed_child`` rejects str at the 0.76 floor); the unit of work is a ``Task`` that
owns N ``RepoCheckout``s, each owning its own LIST of terminals (default 2 — one
``agent``, one ``shell`` — D-01) with OQ1 structured ids ``{task}:{repo}:tN`` plus
a ``repo_name`` field; a 1-repo project is a Task with ONE RepoCheckout through
the identical shape (criterion 5); the store is JSON-serializable via ``asdict``
recursing repos → terminals (D-13/A2); hibernate clears EVERY terminal's pid/pgid
across EVERY repo while KEEPING every dir (D-08/D-11, Pitfall 3 — no group
forgotten so RAM can't leak). ``WorktreeSession`` is gone (OQ3).
"""
import json

from arduis import session
from arduis.session import (
    AGENT_FEED,
    RepoCheckout,
    SessionState,
    SessionStore,
    Task,
    TerminalRecord,
    default_repo_terminals,
    hibernate_fields,
)


def _repo(task_id: str, repo_name: str, branch: str = "feat") -> RepoCheckout:
    return RepoCheckout(
        repo_name=repo_name,
        worktree_dir=f"/home/u/livon-tasks/{task_id}/{repo_name}",
        branch=branch,
        terminals=default_repo_terminals(task_id, repo_name),
    )


def test_agent_feed_is_bytes():
    # D-08 / Pitfall 1: must be bytes, not str (0.76 feed_child TypeError on str).
    assert AGENT_FEED == b"claude\n"
    assert isinstance(AGENT_FEED, bytes)


def test_default_repo_terminals():
    # D-01 + OQ1: exactly 2 terminals per repo (agent + shell) with structured
    # ids {task}:{repo}:tN and the repo_name field set.
    terms = default_repo_terminals("feat", "backend")
    assert len(terms) == 2
    assert terms[0].term_id == "feat:backend:t0"
    assert terms[0].kind == "agent"
    assert terms[0].repo_name == "backend"
    assert terms[1].term_id == "feat:backend:t1"
    assert terms[1].kind == "shell"
    assert terms[1].repo_name == "backend"


def test_terminal_record_has_repo_name_field():
    # OQ1 backward-fields preserved; repo_name added (defaults None).
    t = TerminalRecord("feat:backend:t0", "agent", repo_name="backend")
    assert t.pid is None and t.pgid is None and t.rss_kb is None
    assert t.repo_name == "backend"
    # positional construction still works (repo_name is the LAST field).
    t2 = TerminalRecord("feat:backend:t1", "shell", 10, 10, 99)
    assert t2.repo_name is None


def test_multi_repo_task_serializable():
    # A multi-repo Task: 2 RepoCheckouts × 2 terminals = 4 terminals total.
    task = Task(
        task_id="feat",
        branch="feat",
        task_dir="/home/u/livon-tasks/feat",
        repos=[_repo("feat", "backend"), _repo("feat", "frontend")],
    )
    assert len(task.repos) == 2
    total_terms = sum(len(r.terminals) for r in task.repos)
    assert total_terms == 4
    d = task.to_dict()
    assert d["state"] == "active"  # str-Enum serializes to its value
    json.dumps(d)  # asdict recurses repos → terminals; must not raise
    # the repo_name field is present in the serialized terminals.
    assert d["repos"][0]["terminals"][0]["repo_name"] == "backend"


def test_degenerate_single_repo_task_identical_shape():
    # Criterion 5: a 1-repo project is a Task with exactly one RepoCheckout with
    # 2 terminals — identical structure, NO special branch.
    task = Task(
        task_id="solo",
        branch="solo",
        task_dir="/home/u/livon-tasks/solo",
        repos=[_repo("solo", "livon")],
    )
    assert len(task.repos) == 1
    assert len(task.repos[0].terminals) == 2
    json.dumps(task.to_dict())


def test_hibernate_clears_all_repos_all_terminals():
    # Pitfall 3: hibernate clears EVERY terminal's pid AND pgid across EVERY repo
    # (2 repos × 2 terms → all 4 cleared); dirs kept; rss_kb untouched.
    backend = _repo("feat", "backend")
    frontend = _repo("feat", "frontend")
    for r in (backend, frontend):
        for i, t in enumerate(r.terminals):
            t.pid = 4000 + i
            t.pgid = 4000 + i
            t.rss_kb = 1234
    task = Task(
        task_id="feat",
        branch="feat",
        task_dir="/home/u/livon-tasks/feat",
        repos=[backend, frontend],
    )
    hibernate_fields(task)
    assert task.state == SessionState.HIBERNATED
    cleared = 0
    for r in task.repos:
        for t in r.terminals:
            assert t.pid is None
            assert t.pgid is None
            assert t.rss_kb == 1234  # untouched
            cleared += 1
    assert cleared == 4
    # dirs kept on disk (D-08/D-11).
    assert task.task_dir == "/home/u/livon-tasks/feat"
    assert task.repos[0].worktree_dir == "/home/u/livon-tasks/feat/backend"
    # serializes cleanly post-hibernate.
    assert task.to_dict()["state"] == "hibernated"


def test_store_crud_and_serializable():
    store = SessionStore()
    task = Task(
        task_id="feat",
        branch="feat",
        task_dir="/home/u/livon-tasks/feat",
        repos=[_repo("feat", "backend")],
    )
    store.add(task)
    assert store.get("feat") is task
    assert store.by_branch("feat") is task
    assert store.by_branch("absent") is None
    assert store.all() == [task]
    as_list = store.to_list()
    assert as_list[0]["state"] == "active"
    assert as_list[0]["task_id"] == "feat"
    json.dumps(as_list)  # must not raise


def test_store_remove_drops_task():
    # GAP 2: a create where every repo aborts must be removable from the store
    # (no zombie row, not counted by caps). remove() touches memory only — never disk.
    store = SessionStore()
    task = Task(
        task_id="feat",
        branch="feat",
        task_dir="/home/u/livon-tasks/feat",
        repos=[_repo("feat", "backend")],
    )
    store.add(task)
    assert store.get("feat") is task
    store.remove("feat")
    assert store.get("feat") is None
    assert store.all() == []
    store.remove("absent")  # idempotent — removing a missing id is a no-op


def test_session_module_is_gtk_free():
    with open(session.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text


def test_worktree_session_removed():
    # OQ3: WorktreeSession is fully replaced by Task — no parallel model.
    assert not hasattr(session, "WorktreeSession")
