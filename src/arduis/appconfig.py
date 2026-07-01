"""GTK-free [theme] persistence (UI-02, D-09): read name + atomic section-preserving write.

tomllib is read-only and CLAUDE.md flags tomli-w optional, so write_theme is a tiny
read-parse-rewrite that preserves every OTHER section via a minimal serializer covering
only the value types arduis's own config uses (str/bool/int/float + one level of nested
tables: [keys.bindings]). Inline TOML comments are LOST on rewrite (documented, D-09).
Atomic tmp + os.replace mirrors the settings.json write — a torn write can't corrupt the
file. Best-effort: an OSError on write is swallowed (the in-memory switch already applied).
"""
from __future__ import annotations

import os
import tempfile
import tomllib

_DEFAULT_THEME = "parallel-dark"
# Deterministic top-level table order (others appended after, sorted, for stability).
_SECTION_ORDER = ("attention", "agent", "keys", "theme")


def load_theme_name(path: str) -> str:
    """Read ``[theme] name`` (UI-02); non-str/empty/missing/garbage -> ``"parallel-dark"``.

    Tolerant read mirroring attention.load_config. window.py passes the result to
    themes.get_theme, which re-whitelists, so a bogus-but-non-empty name is harmless.
    """
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return _DEFAULT_THEME
    section = data.get("theme")
    if not isinstance(section, dict):
        return _DEFAULT_THEME
    name = section.get("name")
    if not isinstance(name, str) or not name.strip():
        return _DEFAULT_THEME
    return name.strip()


def _fmt_scalar(v) -> str:
    """Serialize a scalar TOML value (bool before int — bool is an int subclass)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _emit_table(header: str, table: dict) -> list[str]:
    """Emit ``[header]`` + its scalar keys, then any nested sub-tables as ``[header.child]``."""
    lines = [f"[{header}]"]
    nested: list[tuple[str, dict]] = []
    for k, v in table.items():
        if isinstance(v, dict):
            nested.append((k, v))
        else:
            lines.append(f"{k} = {_fmt_scalar(v)}")
    out = lines
    for child_key, child in nested:
        out.append("")
        out.extend(_emit_table(f"{header}.{child_key}", child))
    return out


def _serialize(data: dict) -> str:
    """Serialize the config dict back to TOML in a deterministic section order.

    Known sections first (``_SECTION_ORDER``), any others sorted after for stability.
    Only dict-valued top-level keys become tables; scalars-at-root are dropped (arduis
    has none). Covers the value types arduis's own config uses (str/bool/int/float +
    one nested level: ``[keys.bindings]``).
    """
    keys = list(_SECTION_ORDER) + sorted(k for k in data if k not in _SECTION_ORDER)
    blocks: list[str] = []
    for key in keys:
        section = data.get(key)
        if isinstance(section, dict):
            blocks.append("\n".join(_emit_table(key, section)))
    return "\n\n".join(blocks) + "\n"


def write_theme(path: str, name: str) -> None:
    """Atomically persist ``[theme] name`` while preserving every other section (D-09).

    Reads + parses the existing file (missing/garbage -> ``{}``), sets
    ``theme.name``, re-serializes the WHOLE dict, writes to a same-dir tmp file and
    ``os.replace``s it onto ``path`` (atomic — a torn write can't corrupt the file).
    Best-effort: an OSError (uncreatable parent, read-only dir) is swallowed so the
    in-memory theme switch still applies; persistence is a convenience.
    """
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        if not isinstance(data, dict):
            data = {}
    except (OSError, tomllib.TOMLDecodeError):
        data = {}
    data.setdefault("theme", {})["name"] = name
    text = _serialize(data)
    try:
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".arduis-cfg-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    except OSError:
        pass  # best-effort persistence (D-09)
