"""RED contract tests for the GTK-free active-agent cap policy (``arduis.caps``).

Pins the cap policy over the 03.2 ``Task`` model. ``caps.py`` itself is unchanged
— it only needs ``state.value == "active"`` over a Task list, and a fat multi-repo
Task counts as ONE active (D-14).

Decisions pinned:
- D-15: ``ACTIVE_CAP_DEFAULT == 6`` — a single, Phase-6-sourceable constant.
- D-16: ``at_cap`` triggers the prompt with ``>=`` (active_count >= cap), counting
  only Tasks whose state is ACTIVE.
- D-14: a single multi-repo Task counts as 1 active (not 1-per-repo).
"""
from arduis import caps
from arduis.caps import ACTIVE_CAP_DEFAULT, active_count, at_cap
from arduis.session import RepoCheckout, SessionState, Task, default_repo_terminals


def _task(task_id: str, state: SessionState, repo_names=("repo",)) -> Task:
    repos = [
        RepoCheckout(
            repo_name=name,
            worktree_dir=f"/home/u/livon-tasks/{task_id}/{name}",
            branch=task_id,
            terminals=default_repo_terminals(task_id, name),
        )
        for name in repo_names
    ]
    return Task(task_id=task_id, branch=task_id, task_dir=f"/home/u/livon-tasks/{task_id}",
                repos=repos, state=state)


def _active(n: int) -> list[Task]:
    return [_task(f"a{i}", SessionState.ACTIVE) for i in range(n)]


def test_active_cap_default():
    # D-15: single Phase-6-sourceable constant, default ~6.
    assert ACTIVE_CAP_DEFAULT == 6


def test_active_count():
    tasks = [
        _task("a", SessionState.ACTIVE),
        _task("b", SessionState.HIBERNATED),
        _task("c", SessionState.ACTIVE),
        _task("d", SessionState.HIBERNATED),
    ]
    assert active_count(tasks) == 2


def test_multi_repo_task_counts_as_one():
    # D-14: a single 3-repo Task counts as 1 active, not 3.
    fat = _task("big", SessionState.ACTIVE, repo_names=("backend", "frontend", "keycloak"))
    assert len(fat.repos) == 3
    assert active_count([fat]) == 1
    assert at_cap([fat]) is False


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
