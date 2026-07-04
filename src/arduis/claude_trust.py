"""GTK-free Claude Code trust propagation for workspace folders.

Claude Code gates each directory behind a per-path trust dialog recorded in
``~/.claude.json`` (``projects["<path>"].hasTrustDialogAccepted``). Every workspace
folder / worktree arduis creates is a NEW path, so ``claude`` launched there ignores the
repo's ``.claude/settings.local.json`` permissions until the user re-accepts trust —
exactly the friction arduis exists to remove.

Model (PROPAGATION, never origination): a workspace is a checkout of repos the user
already vetted at the project root. If — and only if — the project ROOT is already
trusted in ``~/.claude.json``, the workspace paths inherit that grant. An untrusted
root propagates nothing (the user never said yes, arduis must not say it for them).

Best-effort + fail-closed, mirroring ``trust.py``: an unreadable/garbage
``~/.claude.json`` is a silent no-op (claude just re-prompts — never corrupt the
file to avoid a dialog). Write is atomic (tmp + ``os.replace`` in the same dir) and
round-trips the WHOLE document (the file holds unrelated claude state). GTK-free:
imports no ``gi``.
"""
from __future__ import annotations

import json
import os
import tempfile


def default_claude_json_path() -> str:
    """The per-user claude config document (``~/.claude.json``)."""
    return os.path.expanduser("~/.claude.json")


def pretrust_paths(claude_json_path: str, source_root: str, paths: list[str]) -> None:
    """Propagate ``source_root``'s accepted trust dialog to each of ``paths``.

    No-op unless ``projects[source_root].hasTrustDialogAccepted`` is already ``True``
    (propagation, never origination). Already-trusted paths are left untouched
    (idempotent — an unchanged document is never rewritten). New entries also get
    ``hasCompletedProjectOnboarding: True`` so a fresh workspace skips the onboarding
    tour, not just the trust dialog. Any read/parse/write failure is swallowed:
    claude simply re-prompts, which is strictly better than a corrupted config.
    """
    try:
        with open(claude_json_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return
    if not isinstance(data, dict):
        return
    projects = data.get("projects")
    if not isinstance(projects, dict):
        return
    source = projects.get(source_root)
    if not (isinstance(source, dict) and source.get("hasTrustDialogAccepted") is True):
        return

    changed = False
    for path in paths:
        entry = projects.get(path)
        if not isinstance(entry, dict):
            entry = {}
            projects[path] = entry
        if entry.get("hasTrustDialogAccepted") is not True:
            entry["hasTrustDialogAccepted"] = True
            entry.setdefault("hasCompletedProjectOnboarding", True)
            changed = True
    if not changed:
        return

    try:
        d = os.path.dirname(claude_json_path) or "."
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".arduis-claude-trust-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, claude_json_path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    except OSError:
        pass  # best-effort: claude re-prompts, config never corrupted
