"""GTK-free persistence for the spoken-prompt history (voice agent). Imports NO gi.

Owns ``voice_history.json`` — the list of prompts the user dictated, newest first, so
any past prompt can be re-run from the history popover. Same discipline as
``projects_store``: the path is an ARGUMENT (window.py resolves
``GLib.get_user_config_dir()/arduis/voice_history.json``), writes are atomic
(same-dir mkstemp → ``os.replace``), loads are tolerant (garbage file / bad entry →
skip, never raise). Re-dictating an existing prompt moves it to the top and bumps its
``count`` instead of duplicating the row.
"""
from __future__ import annotations

import json
import os
import tempfile

# Schema version of voice_history.json — bump to migrate the on-disk shape.
_VERSION = 1

DEFAULT_CAP = 200


def load_history(path: str) -> list[dict]:
    """Tolerant load: list of ``{"text": str, "ts": str, "count": int}``, newest first.

    Missing file / bad json / wrong shapes degrade to ``[]``; one bad entry never
    aborts the whole load.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return []
    if not isinstance(data, dict):
        return []
    raw = data.get("prompts", [])
    if not isinstance(raw, list):
        return []
    entries: list[dict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        text = entry.get("text")
        ts = entry.get("ts")
        if not isinstance(text, str) or not isinstance(ts, str):
            continue
        count = entry.get("count")
        if not isinstance(count, int) or count < 1:
            count = 1
        entries.append({"text": text, "ts": ts, "count": count})
    return entries


def append_entry(path: str, text: str, ts: str, cap: int = DEFAULT_CAP) -> list[dict]:
    """Put ``text`` at the top of the history and persist atomically.

    If ``text`` is already present, the existing row moves to the top with ``count``
    incremented and ``ts`` refreshed. The list is trimmed to ``cap``. Returns the new
    list (also what a reload would see). Best-effort write, like ``save_projects``.
    """
    entries = load_history(path)
    count = 1
    for i, entry in enumerate(entries):
        if entry["text"] == text:
            count = entry["count"] + 1
            del entries[i]
            break
    entries.insert(0, {"text": text, "ts": ts, "count": count})
    del entries[cap:]
    _save(path, entries)
    return entries


def _save(path: str, entries: list[dict]) -> None:
    """Atomic best-effort write (mirrors ``projects_store.save_projects``)."""
    data = {"version": _VERSION, "prompts": entries}
    try:
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".arduis-voice-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, path)  # atomic
        except (OSError, ValueError, TypeError):
            try:
                os.unlink(tmp)
            except OSError:
                pass
    except OSError:
        pass
