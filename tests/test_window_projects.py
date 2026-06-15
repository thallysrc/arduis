"""Behavioral regression for the 03.4 multi-project launch wiring (window.py).

window.py needs no display to IMPORT (gi import is module-level; widget construction
is what needs a display). So — exactly like ``test_window_conclude`` — we build a bare
window via ``__new__`` (skip __init__/GTK), give it a real ``ProjectRegistry``, and stub
the GTK-touching + disk-scan helpers so we can drive ``_init_projects`` headless and
assert the registry outcome.

This file is created here (Plan 03 Task 2); Plan 04 Task 3 extends it with the four
project-lifecycle (switch / remove / teardown / app-exit) cases.
"""
import os
import tempfile

import arduis.window as W
from arduis.project import Project, ProjectRegistry
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
    # compose detection + the per-project task scan are no-ops here.
    monkeypatch.setattr(win, "_detect_compose_path", lambda root: None)
    monkeypatch.setattr(win, "_scan_tasks", lambda project=None: None)
    # GTK chrome is stubbed (no display).
    monkeypatch.setattr(win, "_refresh_project_chrome", lambda: None)
    monkeypatch.setattr(win, "_rebuild_sidebar", lambda: None)
    monkeypatch.setattr(win, "_reconcile_orphans", lambda: None)
    # _build_project_tabs is getattr-guarded in _init_projects; stub to a no-op so
    # the guard sees a callable and we exercise the (Task-3) render branch safely.
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
