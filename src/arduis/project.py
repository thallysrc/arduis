"""GTK-free project/member-repo discovery (D-05/D-07; D-04 03.3). Imports NO gi.

A *project* is a root folder; its direct subdirs whose ``.git`` is a **directory**
(a true repo) are its member repos. A subdir whose ``.git`` is a FILE is a linked
worktree / submodule and is NOT a member (D-04 / 03.3). The root's OWN ``.git`` is
never a member (D-05) and there is no walk-up-the-tree (D-07). A project with no
member subdirs is the degenerate 1-repo case: the caller treats ``[]`` as "this
root is itself the single repo" and builds a one-``RepoCheckout`` Workspace (criterion 5).

Threats (see 03.2 threat register):
- T-03.2-04: scanned dir names are returned verbatim and only ever land as
  discrete ``-C <path>`` git-argv elements (list form, never a shell string), so a
  newline/space in a dir name cannot be interpolated into a command.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field

from arduis.session import SessionStore


def detect_member_repos(root: str) -> list[str]:
    """Direct subdirs of ``root`` whose ``.git`` is a **directory** (a true repo).

    The root's own ``.git`` is NOT a member (D-05): ``scandir`` only yields
    direct children, so the root's ``.git`` is never in the subdir scan. D-04
    (03.3): the membership test is ``os.path.isdir(.../.git)`` — a ``.git`` FILE
    (linked worktree / submodule) is NOT a member, REVERSING the 03.2 "Pitfall 1"
    behavior that counted it via ``os.path.exists``. The PO's real ``Livon-Saude``
    root has ~20 ``backend-*``/``frontend-*`` worktrees (``.git`` is a FILE) that
    would otherwise flood the topbar chip bar. Symlinked subdirs are not followed
    (``follow_symlinks=False`` — T-03.3-03 still guarded). Returns sorted names;
    ``[]`` on error or when none (caller treats ``[]`` as the degenerate 1-repo
    project).
    """
    members: list[str] = []
    try:
        with os.scandir(root) as it:
            for e in it:
                if e.is_dir(follow_symlinks=False) and os.path.isdir(
                    os.path.join(e.path, ".git")
                ):
                    members.append(e.name)
    except OSError:
        return []
    return sorted(members)


@dataclass
class Project:
    """One open PROJECT: a multi-repo root + its OWN workspaces + live state (D-01/D-02).

    The 03.4 corrective lifts ``window.py``'s one-project singletons
    (``_project_root``/``_member_repos``/single ``_store``) into this GTK-free
    object so N projects can be "both alive" behind a ``ProjectRegistry``. Each
    Project owns its OWN ``SessionStore`` (D-02 — workspace stores are never shared; the
    window renders the active project's store and re-points it on switch).

    Fields:
    - ``root``: absolute project root (the meta-repo dir; also the registry key).
    - ``member_repos``: ``detect_member_repos(root)`` result, computed ONCE at open
      time and stored here (RESEARCH anti-pattern: never re-detect on every switch).
    - ``store``: this project's ``SessionStore`` (its workspaces).
    - ``last_active_workspace``: the workspace_id (or pinned-main sid) to swap back to when the
      project is re-selected; None until the project has been worked in.
    - ``compose_path`` / ``container_state``: per-project Phase-7 state moves here
      (a different root may have a different root ``docker-compose.yml``); plain
      attributes window.py populates — annotated GTK-free (``dict``), no gi import.
    """

    root: str
    member_repos: list[str] = field(default_factory=list)
    store: SessionStore = field(default_factory=SessionStore)
    last_active_workspace: str | None = None
    compose_path: str | None = None
    container_state: dict = field(default_factory=dict)

    @property
    def name(self) -> str:
        """Display label = the root's basename (``/x/Livon-Saude`` -> ``Livon-Saude``)."""
        return os.path.basename(self.root.rstrip("/"))


class ProjectRegistry:
    """Open projects + the single active pointer (D-01). GTK-free, in-memory.

    Keyed by absolute ``root`` (stable, unique). Only the SET of roots is persisted
    (``projects_store``); the registry itself is rebuilt at startup. The window reads
    ``active()`` wherever it previously read the project singletons; switching a
    project re-points ``_active`` and the window re-renders that project's store.
    """

    def __init__(self) -> None:
        self._projects: dict[str, Project] = {}
        self._active: str | None = None

    def add(self, p: Project) -> None:
        """Insert (or replace by root — dedup, never duplicate)."""
        self._projects[p.root] = p

    def get(self, root: str) -> Project | None:
        return self._projects.get(root)

    def all(self) -> list[Project]:
        """Open projects in insertion order."""
        return list(self._projects.values())

    def active(self) -> Project | None:
        """The active Project, or None until one is selected."""
        if self._active is None:
            return None
        return self._projects.get(self._active)

    def set_active(self, root: str) -> None:
        self._active = root

    def remove(self, root: str) -> None:
        """Drop a project from the registry; clear the active pointer if it was it.

        In-memory only — process/container TEARDOWN on remove (D-10) is window.py's
        job; this never touches disk.
        """
        self._projects.pop(root, None)
        if self._active == root:
            self._active = None


def ensure_project(
    registry: ProjectRegistry, root: str, member_repos: list[str]
) -> Project:
    """Idempotently register ``root`` and return its Project (D-07 launch helper).

    If ``root`` is already open, return the EXISTING instance (no duplicate, member
    repos untouched — they were detected at first open). Otherwise build a fresh
    ``Project(root, member_repos)``, add it, and return it. The caller selects it as
    active. This preserves today's single-project launch as the degenerate case:
    the cwd project is auto-registered on startup if absent.
    """
    existing = registry.get(root)
    if existing is not None:
        return existing
    p = Project(root=root, member_repos=list(member_repos))
    registry.add(p)
    return p


def project_term_id(project_root: str, term_id: str) -> str:
    """Namespace a term_id with a stable per-project discriminator (A3, Pitfall 1).

    ``workspace_id`` defaults to the branch name and ``term_id`` is ``{workspace_id}:tN``, so
    two DIFFERENT projects each with a ``feat`` workspace both yield ``feat:t0`` — which
    would collide on the GLOBAL attention status-file path
    (``attention.state_file_path(status_dir, term_id)``). Prefix the id with the
    first 8 hex of ``sha1(project_root)`` so ``/a/Foo`` and ``/b/Foo`` produce
    distinct, stable ids and never share a status file. The result is fed straight
    into ``attention.state_file_path``; hex digits + ":" are all inside
    ``attention.sanitize_term_id``'s allowlist (``[A-Za-z0-9._:-]``), so the
    namespaced id introduces no unsafe char and survives sanitization unchanged.
    """
    disc = hashlib.sha1(project_root.encode("utf-8")).hexdigest()[:8]
    return f"{disc}:{term_id}"
