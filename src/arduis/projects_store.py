"""GTK-free persistence for the remembered-projects set (D-05/D-06). Imports NO gi.

The 03.4 corrective makes "one arduis = one launch-dir project" obsolete: the topbar
lists multiple PROJECTS and must REMEMBER them across launches. This module owns the
``projects.json`` app-state file — the FIRST persisted app state in arduis (tasks stay
disk-discovered per project via ``_scan_tasks``; only the arbitrary project ROOTS, which
can't be rediscovered, are persisted, plus ``last_active_project`` so relaunch restores
focus).

``tomllib`` is read-only per CLAUDE.md, so app state that must be WRITTEN uses stdlib
``json`` (zero new dependency — not ``tomli-w``). The write mirrors the proven atomic
temp+rename pattern in ``appconfig.write_theme`` (mkstemp in the same dir → ``os.replace``)
so a torn write can never corrupt the file (T-03.4-01). The path is taken as an ARGUMENT
(the caller resolves ``GLib.get_user_config_dir()/arduis/projects.json`` in window.py) so
this module stays GTK-free and unit-testable in isolation.

Threats (03.4 register):
- T-03.4-01 Tampering: atomic write — a mid-write failure unlinks the temp and leaves the
  original intact; no stray non-temp target is left.
- T-03.4-02 Tampering/DoS-of-state: tolerant load — bad json / not-a-dict / missing file →
  ``([], None)``; one bad entry never aborts the whole load.
- T-03.4-04 Info disclosure (ACCEPTED): the file holds only directory paths the user
  already has on disk — no secrets.
"""
from __future__ import annotations

import json
import os
import tempfile

# Schema version of projects.json — bump to migrate the on-disk shape.
_VERSION = 1


def save_projects(path: str, roots: list[str], last_active: str | None) -> None:
    """Atomically persist the remembered project roots + last_active (D-05).

    Writes ``{"version":1,"projects":[{"root":r},...],"last_active_project":last}``
    to a same-dir temp file, then ``os.replace``s it onto ``path`` (atomic — a torn
    write can't corrupt the existing file, T-03.4-01). Best-effort, like
    ``appconfig.write_theme``: an OSError (uncreatable parent, read-only dir) is
    swallowed; a mid-write failure (e.g. ``json.dump`` raises) unlinks the temp and
    leaves the original file untouched, never leaving a stray non-temp target.
    """
    data = {
        "version": _VERSION,
        "projects": [{"root": r} for r in roots],
        "last_active_project": last_active,
    }
    try:
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".arduis-projects-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, path)  # atomic
        except (OSError, ValueError, TypeError):
            # mid-write failure: drop the temp, leave the original intact.
            try:
                os.unlink(tmp)
            except OSError:
                pass
    except OSError:
        pass  # best-effort persistence (mirrors write_theme)


def load_projects(path: str) -> tuple[list[str], str | None]:
    """Tolerant load of the remembered roots + last_active (D-05/D-06).

    Returns ``(valid_roots, last_active)``. Skips any root that is not
    ``os.path.isdir`` (D-06 — a remembered folder was deleted/moved → drop it, never
    crash). Drops ``last_active`` if it is not among the surviving roots. Any
    OSError / not-valid-json / not-a-dict degrades to ``([], None)`` (T-03.4-02 —
    one bad file never raises).
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return [], None
    if not isinstance(data, dict):
        return [], None
    raw = data.get("projects", [])
    if not isinstance(raw, list):
        raw = []
    roots: list[str] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        root = entry.get("root")
        if isinstance(root, str) and os.path.isdir(root) and root not in roots:
            roots.append(root)  # skip missing (D-06), dedup, preserve order
    last = data.get("last_active_project")
    if last not in roots:
        last = None  # invalid/missing last_active dropped (D-06)
    return roots, last
