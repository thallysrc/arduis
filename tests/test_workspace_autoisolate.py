"""Auto-isolation on workspace creation (Phase 7 follow-up, 2026-07-03).

Pivot: CONT-04 originally said "Never auto-enable" — the user decided (2026-07-03)
that CREATING a workspace in a project with a root compose + docker on PATH must
bring up its isolated stack automatically (override de portas + projeto compose
próprio), instead of requiring the manual "Isolar containers" menu toggle.

Same display-free pattern as test_window_conclude.py: bare window via ``__new__``,
record-only stubs for the GTK-touching helpers, real ``load_container_state``
against a tmp workspace dir. Locks:

  - available (compose + docker) → ``_enable_isolation`` fires ONCE, AFTER the
    terminals are spawned (containers pull async; terminals must not wait);
  - unavailable → never fires (menu-toggle behavior unchanged);
  - zombie path (zero repos succeeded) → never fires.
"""
import arduis.window as W
from arduis.session import Workspace, RepoCheckout, SessionState


def _bare_window(monkeypatch, available):
    # bare __new__ window: _store/_layouts/_container_state resolve through the
    # lazy bootstrap Project (the supported display-free test path).
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    calls = []
    monkeypatch.setattr(win._store, "remove",
                        lambda sid: calls.append(("store.remove", sid)))

    for name in ("_build_workspace_terminals", "_spawn_workspace_terminals",
                 "_run_repo_setups", "_rebuild_sidebar", "_refresh_workspace_status",
                 "_show_error", "_swap_workspace"):
        monkeypatch.setattr(win, name,
                            (lambda n: (lambda *a, **k: calls.append((n,))))(name))
    monkeypatch.setattr(win, "_isolation_available", lambda: available)
    monkeypatch.setattr(win, "_enable_isolation",
                        lambda workspace: calls.append(("_enable_isolation", workspace.workspace_id)))
    return win, calls


def _workspace(tmp_path, repos):
    return Workspace(workspace_id="feat", branch="feat", workspace_dir=str(tmp_path),
                     repos=repos, state=SessionState.ACTIVE)


def test_create_auto_enables_isolation_when_available(monkeypatch, tmp_path):
    win, calls = _bare_window(monkeypatch, available=True)
    repos = [RepoCheckout(repo_name="backend", worktree_dir=str(tmp_path / "backend"), branch="feat")]

    win._finalize_workspace_creation(_workspace(tmp_path, repos), ["backend"], [])

    enables = [c for c in calls if c[0] == "_enable_isolation"]
    assert enables == [("_enable_isolation", "feat")]  # exactly once, right workspace
    # terminals first — the agent pair must never wait on a slow image pull
    assert calls.index(("_spawn_workspace_terminals",)) < calls.index(("_enable_isolation", "feat"))


def test_create_skips_isolation_when_unavailable(monkeypatch, tmp_path):
    win, calls = _bare_window(monkeypatch, available=False)
    repos = [RepoCheckout(repo_name="backend", worktree_dir=str(tmp_path / "backend"), branch="feat")]

    win._finalize_workspace_creation(_workspace(tmp_path, repos), ["backend"], [])

    assert not any(c[0] == "_enable_isolation" for c in calls)
    assert ("_spawn_workspace_terminals",) in calls  # creation itself unaffected


def test_zombie_workspace_never_auto_enables(monkeypatch, tmp_path):
    # zero repos succeeded → workspace torn down; no containers for a zombie
    win, calls = _bare_window(monkeypatch, available=True)

    win._finalize_workspace_creation(_workspace(tmp_path, []), ["backend"], ["backend: boom"])

    assert not any(c[0] == "_enable_isolation" for c in calls)
    assert ("store.remove", "feat") in calls
