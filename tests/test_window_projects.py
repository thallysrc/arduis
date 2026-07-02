"""Behavioral regression for the 03.4 multi-project launch wiring (window.py).

window.py needs no display to IMPORT (gi import is module-level; widget construction
is what needs a display). So — exactly like ``test_window_conclude`` — we build a bare
window via ``__new__`` (skip __init__/GTK), give it a real ``ProjectRegistry``, and stub
the GTK-touching + disk-scan helpers so we can drive ``_init_projects`` headless and
assert the registry outcome.

This file is created here (Plan 03 Workspace 2); Plan 04 Workspace 3 extends it with the four
project-lifecycle (switch / remove / teardown / app-exit) cases.
"""
import os
import tempfile

import arduis.window as W
from arduis import compose
from arduis.containerstate import ContainerState
from arduis.project import Project, ProjectRegistry
from arduis.session import RepoCheckout, SessionState, SessionStore, Workspace
from arduis import projects_store


def _bare_projects_window(monkeypatch, projects_json, cwd_root, cwd_members):
    """A bare window with a real registry; cwd + scan + GTK chrome stubbed."""
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    win._registry = ProjectRegistry()
    win._bootstrap = Project(root="")
    win._projects_json = projects_json

    # cwd resolves to (cwd_root, cwd_members) — no real getcwd/git rev-parse.
    monkeypatch.setattr(win, "_resolve_cwd_project", lambda: (cwd_root, cwd_members))
    # member detection for remembered roots: deterministic, no disk scan.
    monkeypatch.setattr(W, "detect_member_repos", lambda root: ["backend"])
    # compose detection + the per-project workspace scan are no-ops here.
    monkeypatch.setattr(win, "_detect_compose_path", lambda root: None)
    monkeypatch.setattr(win, "_scan_workspaces", lambda project=None: None)
    # GTK chrome is stubbed (no display).
    monkeypatch.setattr(win, "_refresh_project_chrome", lambda: None)
    monkeypatch.setattr(win, "_rebuild_sidebar", lambda: None)
    monkeypatch.setattr(win, "_reconcile_orphans", lambda: None)
    # _build_project_tabs is getattr-guarded in _init_projects; stub to a no-op so
    # the guard sees a callable and we exercise the (Workspace-3) render branch safely.
    monkeypatch.setattr(win, "_build_project_tabs", lambda: None, raising=False)
    return win


def test_init_projects_autoregisters_cwd_and_selects_it(monkeypatch, tmp_path):
    """D-07: cwd absent from the persisted list is auto-registered AND selected.

    persisted file lists ONLY rootB; the launch cwd is rootA. After _init_projects
    the registry holds BOTH roots and the ACTIVE project is rootA (the cwd was
    auto-registered and selected even though it was not in projects.json).
    """
    root_a = str(tmp_path / "Livon-Saude")
    root_b = str(tmp_path / "KarveLabs")
    os.makedirs(root_a)
    os.makedirs(root_b)

    # persisted list: ONLY rootB, last_active = rootB.
    projects_json = str(tmp_path / "projects.json")
    projects_store.save_projects(projects_json, [root_b], root_b)

    win = _bare_projects_window(monkeypatch, projects_json, cwd_root=root_a,
                                cwd_members=["backend"])

    win._init_projects()

    roots = {p.root for p in win._registry.all()}
    assert root_a in roots and root_b in roots  # both registered
    active = win._registry.active()
    assert active is not None and active.root == root_a  # cwd auto-registered + active


def test_init_projects_persists_newly_added_cwd_root(monkeypatch, tmp_path):
    """The auto-registered cwd root is written back to projects.json (D-05)."""
    root_a = str(tmp_path / "Livon-Saude")
    root_b = str(tmp_path / "KarveLabs")
    os.makedirs(root_a)
    os.makedirs(root_b)
    projects_json = str(tmp_path / "projects.json")
    projects_store.save_projects(projects_json, [root_b], root_b)

    win = _bare_projects_window(monkeypatch, projects_json, cwd_root=root_a,
                                cwd_members=["backend"])
    win._init_projects()

    saved_roots, saved_last = projects_store.load_projects(projects_json)
    assert root_a in saved_roots and root_b in saved_roots
    assert saved_last == root_a  # active moved to the cwd project (D-07)


def test_init_projects_cwd_project_wins_over_last_active(monkeypatch, tmp_path):
    """D-07: launching INSIDE a project lands you in it, even when last_active differs.

    Both roots remembered; last_active = rootB; the launch cwd is rootA (also
    remembered). The cwd project (rootA) is selected — launching inside a project
    always lands you in it.
    """
    root_a = str(tmp_path / "Livon-Saude")
    root_b = str(tmp_path / "KarveLabs")
    os.makedirs(root_a)
    os.makedirs(root_b)
    projects_json = str(tmp_path / "projects.json")
    projects_store.save_projects(projects_json, [root_a, root_b], root_b)

    win = _bare_projects_window(monkeypatch, projects_json, cwd_root=root_a,
                                cwd_members=["backend"])
    win._init_projects()

    active = win._registry.active()
    assert active is not None and active.root == root_a  # cwd wins (D-07)


def test_init_projects_neutral_cwd_honors_last_active(monkeypatch, tmp_path):
    """Launched from a neutral dir (cwd not a project) → last_active is restored."""
    root_a = str(tmp_path / "Livon-Saude")
    root_b = str(tmp_path / "KarveLabs")
    os.makedirs(root_a)
    os.makedirs(root_b)
    projects_json = str(tmp_path / "projects.json")
    projects_store.save_projects(projects_json, [root_a, root_b], root_b)

    win = _bare_projects_window(monkeypatch, projects_json, cwd_root=None,
                                cwd_members=[])
    win._init_projects()

    active = win._registry.active()
    assert active is not None and active.root == root_b  # last_active honored


def test_init_projects_tolerates_zero_projects(monkeypatch, tmp_path):
    """No persisted projects + cwd not a project → active None, no crash (D-07)."""
    projects_json = str(tmp_path / "projects.json")  # does not exist

    win = _bare_projects_window(monkeypatch, projects_json, cwd_root=None,
                                cwd_members=[])
    win._init_projects()

    assert win._registry.all() == []
    assert win._registry.active() is None


# ---------------------------------------------------------------------------
# Plan 04 lifecycle cases: cap-union gate (D-09), per-project remove teardown
# (D-10), app-exit teardown of ALL projects with per-project compose argv (D-11).
# Same bare-__new__ + monkeypatch-stub discipline as above (no display).
# ---------------------------------------------------------------------------

def _active_workspace(branch: str, *, enabled=False, project_name="") -> Workspace:
    """A live (ACTIVE) workspace with one repo; optionally container-enabled."""
    return Workspace(
        workspace_id=branch,
        branch=branch,
        workspace_dir=f"/workspaces/{branch}",
        repos=[RepoCheckout(repo_name="backend",
                            worktree_dir=f"/workspaces/{branch}/backend", branch=branch)],
        state=SessionState.ACTIVE,
    )


def _project_with_workspaces(root, workspaces, *, compose_path=None, container_state=None):
    """A Project carrying a real SessionStore seeded with ``workspaces``."""
    store = SessionStore()
    for t in workspaces:
        store.add(t)
    p = Project(root=root, member_repos=["backend"], store=store)
    p.compose_path = compose_path
    p.container_state = container_state or {}
    return p


def test_cap_gate_counts_union(monkeypatch):
    """D-09: the new-workspace gate counts agents across ALL projects, not one store.

    Two projects with 4 + 3 ACTIVE workspaces → ``_all_workspaces()`` is 7 (the union), and
    the cap gate (cap default 5) takes the prompt-hibernate branch. A bug that fed
    only the active store (3 workspaces, under cap) would WRONGLY proceed (Pitfall 4).
    """
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    win._registry = ProjectRegistry()
    proj_a = _project_with_workspaces("/A", [_active_workspace(f"a{i}") for i in range(4)])
    proj_b = _project_with_workspaces("/B", [_active_workspace(f"b{i}") for i in range(3)])
    win._registry.add(proj_a)
    win._registry.add(proj_b)
    win._registry.set_active("/B")  # active store has only 3 (under the cap)

    assert len(win._all_workspaces()) == 7  # the UNION, not the active store's 3

    # Drive the new-workspace gate: with 7 > cap(5), it must take the hibernate branch.
    prompted = []
    monkeypatch.setattr(win, "_prompt_hibernate_then",
                        lambda proceed: prompted.append(proceed))
    monkeypatch.setattr(win, "_begin_new_workspace",
                        lambda: prompted.append("BEGAN"))
    win._project_root = "/B"  # the early-guard `if not self._project_root`

    win._on_new_worktree_clicked(None)

    # The union is at/over cap → the gate prompts to hibernate, never begins.
    assert prompted and prompted[0] is win._begin_new_workspace
    assert "BEGAN" not in prompted


def test_remove_with_live_workspaces_tears_down_then_drops(monkeypatch):
    """D-10: removing a project with a live workspace tears it down, then drops it.

    No display: we drive the 'remove' confirm response path directly (the
    Adw.AlertDialog response callback is what _remove_project wires). Assert the
    live workspace's terminals were torn down, the container channel ran, the registry
    dropped the root, projects.json was rewritten — and NO disk-deletion call
    (there is none anywhere in the method).
    """
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    win._registry = ProjectRegistry()
    win._runner = W.HostRunner()
    win._docker_available = True
    win._projects_json = "/dev/null/ignored"  # save_projects swallows OSError

    workspace = _active_workspace("feat", enabled=True, project_name="arduis-feat")
    cstate = ContainerState(project_name="arduis-feat", enabled=True, ports={})
    proj = _project_with_workspaces("/Live", [workspace],
                              compose_path="/Live/docker-compose.yml",
                              container_state={"feat": cstate})
    other = _project_with_workspaces("/Other", [])
    win._registry.add(proj)
    win._registry.add(other)
    win._registry.set_active("/Live")

    teardowns, cleared, downed = [], [], []
    monkeypatch.setattr(win, "_teardown_session_terminals",
                        lambda t: teardowns.append(t.workspace_id))
    monkeypatch.setattr(win, "_clear_workspace_state_files",
                        lambda t: cleared.append(t.workspace_id))
    # capture the compose-down argv that would hit subprocess.run
    monkeypatch.setattr(W.subprocess, "run",
                        lambda argv, **k: downed.append(argv) or None)
    # GTK chrome no-ops (no display). _open_shell_leaf: dropping the active project
    # switches to /Other, which (03.4 UAT fix) seeds its main shell — stub the spawn.
    for n in ("_refresh_project_chrome", "_rebuild_sidebar", "_build_project_tabs",
              "_swap_workspace", "_open_shell_leaf"):
        monkeypatch.setattr(win, n, lambda *a, **k: None, raising=False)
    monkeypatch.setattr(projects_store, "save_projects",
                        lambda *a, **k: None)

    removed_roots = []
    real_remove = win._registry.remove
    monkeypatch.setattr(win._registry, "remove",
                        lambda root: removed_roots.append(root) or real_remove(root))

    # Compute the live workspaces + drive the confirm 'remove' response directly.
    proj_lookup = win._registry.get("/Live")
    live = [t for t in proj_lookup.store.all() if t.state == SessionState.ACTIVE]
    for t in live:
        win._teardown_session_terminals(t)
        win._clear_workspace_state_files(t)
    win._teardown_project_containers(proj_lookup)
    win._drop_project("/Live")

    assert teardowns == ["feat"]            # the live workspace's terminals killed
    assert cleared == ["feat"]              # its state files cleared
    assert len(downed) == 1                 # compose down -v issued once
    assert "arduis-feat" in downed[0]       # this project's OWN compose name
    assert removed_roots == ["/Live"]       # dropped from the registry
    assert win._registry.get("/Live") is None


def test_remove_no_live_workspaces_is_silent(monkeypatch):
    """D-10: a project with only HIBERNATED workspaces drops with NO dialog/teardown."""
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    win._registry = ProjectRegistry()
    win._projects_json = "/dev/null/ignored"

    hib = Workspace(workspace_id="old", branch="old", workspace_dir="/workspaces/old",
               repos=[RepoCheckout(repo_name="backend",
                                  worktree_dir="/workspaces/old/backend", branch="old")],
               state=SessionState.HIBERNATED)
    proj = _project_with_workspaces("/Dorm", [hib])
    keep = _project_with_workspaces("/Keep", [])
    win._registry.add(proj)
    win._registry.add(keep)
    win._registry.set_active("/Keep")  # removing a non-active project

    teardowns = []
    monkeypatch.setattr(win, "_teardown_session_terminals",
                        lambda t: teardowns.append(t.workspace_id))
    monkeypatch.setattr(win, "_clear_workspace_state_files", lambda t: None)
    for n in ("_refresh_project_chrome", "_rebuild_sidebar", "_build_project_tabs"):
        monkeypatch.setattr(win, n, lambda *a, **k: None, raising=False)
    monkeypatch.setattr(projects_store, "save_projects", lambda *a, **k: None)

    presented = []
    monkeypatch.setattr(W.Adw, "AlertDialog",
                        lambda *a, **k: presented.append(True))

    win._remove_project("/Dorm")

    assert not presented            # no dialog constructed (silent path)
    assert teardowns == []          # nothing torn down (no live workspaces)
    assert win._registry.get("/Dorm") is None   # dropped


def test_close_request_tears_down_all_projects(monkeypatch):
    """D-11: app-exit tears down EVERY project's workspaces with per-project compose argv.

    Two projects, EACH a distinct compose project_name/compose_path and EACH one
    live isolated workspace. After _on_close_request, assert (a) _teardown_session_terminals_now
    (the close-path, no-GLib-timer variant — Finding #5) fired ONCE PER WORKSPACE across BOTH
    projects (2 calls, not 1), and (b) the compose-down channel ran TWICE with TWO
    DISTINCT per-project names — a bug reusing the active project's name for all would
    produce two identical names and fail (Pitfall 3).
    """
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    win._registry = ProjectRegistry()
    win._runner = W.HostRunner()
    win._docker_available = True
    win._ram_source = None
    win._status_monitor = None
    win._shell_pid = None

    workspace_a = _active_workspace("alpha")
    workspace_b = _active_workspace("beta")
    cstate_a = ContainerState(project_name="arduis-alpha", enabled=True, ports={})
    cstate_b = ContainerState(project_name="arduis-beta", enabled=True, ports={})
    proj_a = _project_with_workspaces("/ProjA", [workspace_a],
                                compose_path="/ProjA/docker-compose.yml",
                                container_state={"alpha": cstate_a})
    proj_b = _project_with_workspaces("/ProjB", [workspace_b],
                                compose_path="/ProjB/docker-compose.yml",
                                container_state={"beta": cstate_b})
    win._registry.add(proj_a)
    win._registry.add(proj_b)
    win._registry.set_active("/ProjA")  # active project is A; B must STILL tear down

    teardowns, down_argvs = [], []
    # Close path uses the no-timer variant (_teardown_session_terminals_now); it
    # returns pgids that feed the synchronous sweep. Return [] so the sweep is a no-op.
    monkeypatch.setattr(win, "_teardown_session_terminals_now",
                        lambda t: teardowns.append(t.workspace_id) or [])
    monkeypatch.setattr(win, "_clear_workspace_state_files", lambda t: None)
    monkeypatch.setattr(W.subprocess, "run",
                        lambda argv, **k: down_argvs.append(argv) or None)

    win._on_close_request()

    # (a) EVERY project's workspace torn down — 2 calls, not just the active project's 1.
    assert sorted(teardowns) == ["alpha", "beta"]
    # (b) TWO compose-down calls, each carrying ITS OWN project's compose name.
    assert len(down_argvs) == 2
    names = {tok for argv in down_argvs for tok in argv}
    assert "arduis-alpha" in names and "arduis-beta" in names
    # the two argv carry DISTINCT project identifiers (not the active name reused).
    proj_names_in_argv = [argv for argv in down_argvs if "arduis-alpha" in argv]
    other_in_argv = [argv for argv in down_argvs if "arduis-beta" in argv]
    assert len(proj_names_in_argv) == 1 and len(other_in_argv) == 1


def test_switch_to_unseeded_project_seeds_its_main_shell(monkeypatch):
    """Regression (UAT): opening/switching to a project shown for the FIRST time
    spawns ITS pinned main scratch shell, so its workspace shows a terminal (D-07).

    The reported bug: launch arduis in repo A, "Abrir projeto" repo B → B's tab
    appears but the canvas is blank, because only __init__ seeds the launch
    project's main leaf. _switch_project must seed an unseeded project's shell.
    """
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    win._registry = ProjectRegistry()
    win._bootstrap = Project(root="")
    win._projects_json = "/tmp/does-not-matter.json"

    proj_a = Project(root="/tmp/A")
    proj_b = Project(root="/tmp/B")
    win._registry.add(proj_a)
    win._registry.add(proj_b)
    win._registry.set_active("/tmp/A")
    # A is already seeded (its bundle carries the spawned main leaf); B is not.
    win._bundle_for(proj_a)["leaf_by_sid"]["main:t0"] = object()

    seeded = []

    def fake_open_shell_leaf():
        # Simulate the real seed: spawn into the NOW-active project's bundle.
        win._leaf_by_sid["main:t0"] = object()
        seeded.append(win._registry.active().root)

    monkeypatch.setattr(win, "_open_shell_leaf", fake_open_shell_leaf)
    for n in ("_refresh_project_chrome", "_rebuild_sidebar", "_build_project_tabs",
              "_swap_workspace"):
        monkeypatch.setattr(win, n, lambda *a, **k: None, raising=False)
    monkeypatch.setattr(projects_store, "save_projects", lambda *a, **k: None)

    # Switching to the unseeded project B spawns B's main shell exactly once.
    win._switch_project("/tmp/B")
    assert seeded == ["/tmp/B"]

    # Switching back to the already-seeded A does NOT respawn (no double shell).
    win._switch_project("/tmp/A")
    assert seeded == ["/tmp/B"]


def test_reconcile_orphans_cross_project(monkeypatch):
    """_reconcile_orphans must scope ``live`` across ALL projects, not just the active store.

    Regression for the cosmetic v1.0 gap: a background project's compose stack was
    wrongly flagged as an orphan because ``live`` was built from ``self._store.all()``
    (the ACTIVE project only) instead of every registered project's workspaces.
    Audit ref: gaps.integration[reconcile-orphans-scope], window.py:1914.

    Drives the REAL ``_reconcile_orphans``/``_on_ls`` path: ``run_compose_async`` is
    stubbed to invoke the callback synchronously with a controlled ``docker compose ls``
    payload, and the toast is captured. With the bug, ``feat/alpha`` (background project)
    would surface as an orphan; with the fix, only the truly-unmatched stack does.
    """
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    win._registry = ProjectRegistry()
    win._runner = W.HostRunner()
    win._docker_available = True

    proj_a = _project_with_workspaces("/A", [_active_workspace("feat/alpha")])
    proj_b = _project_with_workspaces("/B", [_active_workspace("feat/beta")])
    win._registry.add(proj_a)
    win._registry.add(proj_b)
    win._registry.set_active("/B")
    # _store is the ACTIVE project's store — the bug reads only this.
    win._store = win._registry.active().store

    # docker compose ls payload: both projects' stacks + one true orphan.
    ls_payload = [
        {"Name": compose.sanitize_project_name("feat/alpha"), "Status": "running(1)"},
        {"Name": compose.sanitize_project_name("feat/beta"), "Status": "running(1)"},
        {"Name": compose.sanitize_project_name("feat/gamma"), "Status": "running(1)"},
        {"Name": "unrelated-stack", "Status": "running(1)"},  # non-arduis: ignored
    ]
    import json as _json

    def _fake_run_compose_async(argv, on_done, runner=None):
        on_done(0, _json.dumps(ls_payload), "")

    monkeypatch.setattr(W.docker_service, "run_compose_async", _fake_run_compose_async)

    toasts = []
    monkeypatch.setattr(win, "_toast", lambda msg: toasts.append(msg))

    win._reconcile_orphans()

    # Exactly one toast, naming exactly the gamma stack — alpha (background project)
    # and beta (active) are both live; the non-arduis stack is ignored.
    assert len(toasts) == 1
    gamma = compose.sanitize_project_name("feat/gamma")
    alpha = compose.sanitize_project_name("feat/alpha")
    assert gamma in toasts[0]
    assert alpha not in toasts[0]          # the background project is NOT an orphan
    assert "unrelated-stack" not in toasts[0]
    assert "1 stack" in toasts[0]          # exactly one orphan reported


# --- Finding #3: theme switch must re-color EVERY project's terminals --------

class _StubTerm:
    """A GTK-free stand-in for Vte.Terminal recording the recolor calls."""

    def __init__(self):
        self.colors_calls = 0
        self.cursor_calls = 0

    def set_colors(self, fg, bg, palette):  # noqa: D401 - mimic Vte signature
        self.colors_calls += 1

    def set_color_cursor(self, cursor):
        self.cursor_calls += 1


def test_apply_theme_recolors_terminals_in_all_projects():
    """Finding #3: _apply_theme must recolor terminals across ALL registered
    projects, not just the active bundle — a background project's live terminals
    must NOT keep the old palette after a theme switch.

    Headless: a bare window via __new__ with _display=None (skips the
    add_provider_for_display call) and stub terminals (no Vte/display) registered
    in two projects' bundles. The CssProvider build is pure (no display)."""
    from arduis.themes import get_theme

    win = W.ArduisWindow.__new__(W.ArduisWindow)
    win._registry = ProjectRegistry()
    win._bootstrap = Project(root="")
    # No display: the provider-build runs (pure CSS string) but the
    # add/remove_provider_for_display branches are skipped.
    win._css_provider = None
    win._display = None

    # Two registered projects, ACTIVE + BACKGROUND, each with a live terminal.
    active = Project(root="/proj/active", member_repos=["backend"])
    background = Project(root="/proj/background", member_repos=["backend"])
    win._registry.add(active)
    win._registry.add(background)
    win._registry.set_active("/proj/active")

    active_term = _StubTerm()
    bg_term = _StubTerm()
    win._bundle_for(active)["term_by_sid"]["active:t0"] = active_term
    win._bundle_for(background)["term_by_sid"]["bg:t0"] = bg_term

    win._apply_theme(get_theme("nord"))

    # BOTH projects' terminals were recolored — not just the active one.
    assert active_term.colors_calls == 1
    assert active_term.cursor_calls == 1
    assert bg_term.colors_calls == 1, "background project's terminal was NOT recolored"
    assert bg_term.cursor_calls == 1
    assert win._current_theme.name == "nord"
