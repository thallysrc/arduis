"""RED contract tests for the GTK-free active-agent cap policy (``arduis.caps``).

Pins the cap policy over the 03.2 ``Workspace`` model. ``caps.py`` itself is unchanged
— it only needs ``state.value == "active"`` over a Workspace list, and a fat multi-repo
Workspace counts as ONE active (D-14).

Decisions pinned:
- D-15: ``ACTIVE_CAP_DEFAULT == 6`` — a single, Phase-6-sourceable constant.
- D-16: ``at_cap`` triggers the prompt with ``>=`` (active_count >= cap), counting
  only Workspaces whose state is ACTIVE.
- D-14: a single multi-repo Workspace counts as 1 active (not 1-per-repo).
"""
from arduis import caps
from arduis.caps import ACTIVE_CAP_DEFAULT, active_count, at_cap
from arduis.project import Project
from arduis.session import RepoCheckout, SessionState, Workspace, default_repo_terminals


def _workspace(workspace_id: str, state: SessionState, repo_names=("repo",)) -> Workspace:
    repos = [
        RepoCheckout(
            repo_name=name,
            worktree_dir=f"/home/u/livon-workspaces/{workspace_id}/{name}",
            branch=workspace_id,
            terminals=default_repo_terminals(workspace_id, name),
        )
        for name in repo_names
    ]
    return Workspace(workspace_id=workspace_id, branch=workspace_id, workspace_dir=f"/home/u/livon-workspaces/{workspace_id}",
                repos=repos, state=state)


def _active(n: int) -> list[Workspace]:
    return [_workspace(f"a{i}", SessionState.ACTIVE) for i in range(n)]


def test_active_cap_default():
    # D-15: single Phase-6-sourceable constant, default ~6.
    assert ACTIVE_CAP_DEFAULT == 6


def test_active_count():
    workspaces = [
        _workspace("a", SessionState.ACTIVE),
        _workspace("b", SessionState.HIBERNATED),
        _workspace("c", SessionState.ACTIVE),
        _workspace("d", SessionState.HIBERNATED),
    ]
    assert active_count(workspaces) == 2


def test_multi_repo_workspace_counts_as_one():
    # D-14: a single 3-repo Workspace counts as 1 active, not 3.
    fat = _workspace("big", SessionState.ACTIVE, repo_names=("backend", "frontend", "keycloak"))
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


def test_cap_counts_union_across_projects():
    # D-09: the active-agent cap is GLOBAL across all open projects — RAM is a
    # machine-global resource. Each Project owns its OWN store (D-02); the cap is
    # fed the FLAT UNION of every project's workspaces, not one store.
    a = Project(root="/home/u/Livon-Saude")
    b = Project(root="/home/u/KarveLabs")
    for i in range(4):
        a.store.add(_workspace(f"a{i}", SessionState.ACTIVE))
    for i in range(3):
        b.store.add(_workspace(f"b{i}", SessionState.ACTIVE))

    union = [t for p in (a, b) for t in p.store.all()]
    assert active_count(union) == 7  # 4 + 3, machine-wide
    assert at_cap(union) is True  # 7 >= ACTIVE_CAP_DEFAULT (6)

    # Pitfall 4 regression guard: feeding ONE store alone would NOT trip the cap —
    # only the union does, which is exactly the bug this locks against.
    assert active_count(a.store.all()) == 4
    assert active_count(b.store.all()) == 3
    assert at_cap(a.store.all()) is False
    assert at_cap(b.store.all()) is False


def test_cap_union_hibernated_excluded():
    # A HIBERNATED workspace in EITHER project's store is not counted toward the cap.
    a = Project(root="/home/u/Livon-Saude")
    b = Project(root="/home/u/KarveLabs")
    a.store.add(_workspace("a0", SessionState.ACTIVE))
    a.store.add(_workspace("a1", SessionState.HIBERNATED))
    b.store.add(_workspace("b0", SessionState.ACTIVE))
    b.store.add(_workspace("b1", SessionState.HIBERNATED))

    union = [t for p in (a, b) for t in p.store.all()]
    assert active_count(union) == 2  # the two ACTIVE, hibernated excluded
    assert at_cap(union) is False


def test_caps_is_gtk_free():
    with open(caps.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
