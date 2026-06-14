"""GTK-free per-task container state persistence (CONT-02/03/04, D-06/D-07, OD-2).

The isolation unit is the TASK. When a task opts into an isolated docker-compose stack
(default OFF), arduis must durably remember three things so the feature survives an app
restart and a crash: the unique ``COMPOSE_PROJECT_NAME``, the on/off flag, and the
resolved base->host port map (so badges/URLs stay stable — criterion 3). That record
lives in ``<task_dir>/arduis.container.toml``.

**Disk is the source of truth** (matching 03.2's no-app-state-file model): there is no
in-memory registry to keep in sync; the startup scan rediscovers state by reading these
files. Two disciplines make that safe:

* **Tolerant read** — a missing, corrupt, or wrong-typed file is NOT an error: it yields
  ``ContainerState()`` (project_name="", enabled=False, ports={}), i.e. a task with no
  isolation. A forged/garbage file can never crash task creation or the startup scan
  (T-07-05); malformed port rows are dropped defensively, never raised.
* **Atomic write** — ``write_container_state`` writes a same-dir tmp file then
  ``os.replace`` (mirroring ``appconfig.write_theme``). A torn write can never corrupt the
  durable record (T-07-06): a crash mid-write leaves the previous file intact, and a failed
  write degrades best-effort to "no state" (re-derive) rather than a half-written record.

The ``ports`` value shape MUST equal ``compose.assign_ports``'s output (Plan 01):
``{service: [{"base": int, "host": int, "target": int, "host_ip": str | None}]}``.

GTK-free: stdlib only (``os``, ``tempfile``, ``tomllib``, ``dataclasses``). NEVER ``gi`` —
the whole module is unit-testable headless, the arduis config discipline.
"""
from __future__ import annotations

import os
import tempfile
import tomllib
from dataclasses import dataclass, field

# User-config default offset (CONT-03, D-06); the section is [containers] (plural) in the
# user-level arduis.toml, distinct from a task file's [container] (singular) table.
_DEFAULT_PORT_OFFSET = 1000

_STATE_FILENAME = "arduis.container.toml"


@dataclass
class ContainerState:
    """Durable per-task container state (CONT-04, D-07).

    The default ``ContainerState()`` — project_name="", enabled=False, ports={} — is the
    no-op: a task with no isolation, returned for any missing/garbage/wrong-typed file.

    ``ports`` matches ``compose.assign_ports``'s shape:
    ``{service: [{"base": int, "host": int, "target": int, "host_ip": str | None}]}``.
    """

    project_name: str = ""
    enabled: bool = False
    ports: dict[str, list[dict]] = field(default_factory=dict)


def state_path(task_dir: str) -> str:
    """Return ``<task_dir>/arduis.container.toml`` so window + tests agree on the name."""
    return os.path.join(task_dir, _STATE_FILENAME)


def _fmt_scalar(v) -> str:
    """Serialize a scalar TOML value (bool before int — bool is an int subclass)."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    s = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{s}"'


def _clean_port_entry(entry) -> dict | None:
    """Validate one port row; return a normalized dict or None to DROP a malformed row.

    Defensive (T-07-05): keep only entries with int ``base``/``host``/``target`` and a
    str-or-None ``host_ip``. A bool is rejected for the int fields (bool is an int subclass
    but not a valid port). Anything else is dropped so a partially-valid file still loads.
    """
    if not isinstance(entry, dict):
        return None
    out: dict = {}
    for key in ("base", "host", "target"):
        val = entry.get(key)
        if isinstance(val, bool) or not isinstance(val, int):
            return None
        out[key] = val
    host_ip = entry.get("host_ip")
    if host_ip is not None and not isinstance(host_ip, str):
        return None
    out["host_ip"] = host_ip
    return out


def _serialize(state: ContainerState) -> str:
    """Serialize a ContainerState to the on-disk TOML layout.

    Layout (round-trips verbatim through ``tomllib`` + ``load_container_state``):

        [container]
        project_name = "arduis-feat-x"
        enabled = true

        [[container.ports]]
        service = "web"
        base = 8080
        host = 9080
        target = 80
        host_ip = "127.0.0.1"   # omitted when None

    A FLAT array-of-tables with an explicit ``service`` key — simplest to emit/parse and a
    natural multi-port-per-service representation. ``load_container_state`` rebuilds the
    ``{service: [...]}`` dict by grouping rows by ``service``.
    """
    lines = [
        "[container]",
        f"project_name = {_fmt_scalar(state.project_name)}",
        f"enabled = {_fmt_scalar(state.enabled)}",
    ]
    for service, entries in state.ports.items():
        for entry in entries:
            lines.append("")
            lines.append("[[container.ports]]")
            lines.append(f"service = {_fmt_scalar(service)}")
            lines.append(f"base = {_fmt_scalar(entry['base'])}")
            lines.append(f"host = {_fmt_scalar(entry['host'])}")
            lines.append(f"target = {_fmt_scalar(entry['target'])}")
            host_ip = entry.get("host_ip")
            if host_ip is not None:
                lines.append(f"host_ip = {_fmt_scalar(host_ip)}")
    return "\n".join(lines) + "\n"


def load_container_state(task_dir: str) -> ContainerState:
    """Read ``<task_dir>/arduis.container.toml`` -> ``ContainerState`` (tolerant, CONT-04).

    Missing file / garbage TOML / no ``[container]`` table / wrong-typed keys all yield the
    no-op ``ContainerState()`` default — never raises (T-07-05). Malformed port rows are
    dropped; a partially-valid file yields the valid parts. The DOMINANT case (no file) is
    the no-op default, so a task with no isolation costs nothing.
    """
    try:
        with open(state_path(task_dir), "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return ContainerState()
    if not isinstance(data, dict):
        return ContainerState()
    section = data.get("container")
    if not isinstance(section, dict):
        return ContainerState()

    project_name = section.get("project_name")
    if not isinstance(project_name, str):
        project_name = ""

    enabled = section.get("enabled")
    if not isinstance(enabled, bool):
        enabled = False

    ports: dict[str, list[dict]] = {}
    rows = section.get("ports")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            service = row.get("service")
            if not isinstance(service, str) or not service:
                continue
            cleaned = _clean_port_entry(row)
            if cleaned is None:
                continue
            ports.setdefault(service, []).append(cleaned)

    return ContainerState(project_name=project_name, enabled=enabled, ports=ports)


def write_container_state(task_dir: str, state: ContainerState) -> None:
    """Atomically persist ``state`` to ``<task_dir>/arduis.container.toml`` (CONT-04, D-07).

    Serializes to TOML, writes a same-dir tmp file, then ``os.replace`` onto the target —
    atomic, so a crash mid-write can never corrupt the durable record (T-07-06). The parent
    dir is created if absent (``task_dir`` exists in production; harmless otherwise).
    Best-effort: an OSError (read-only dir, replace failure) is swallowed — a failed write
    degrades to "no state" (re-derive on next run), never a half-written file.
    """
    text = _serialize(state)
    path = state_path(task_dir)
    try:
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".arduis-container-")
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
        pass  # best-effort persistence (T-07-06)


def read_port_offset(config_path: str) -> int:
    """Read ``[containers] port_offset`` from the user config (CONT-03, D-06).

    Tolerant read of ``~/.config/arduis/arduis.toml``: returns the int if present and an int,
    else the safe default ``1000``. Missing file / garbage TOML / ``[containers]`` not a
    table / ``port_offset`` not an int (incl. bool — an int subclass) -> 1000 (T-07-07: a
    forged value just degrades to the default; the config is the user's own file).
    """
    try:
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return _DEFAULT_PORT_OFFSET
    if not isinstance(data, dict):
        return _DEFAULT_PORT_OFFSET
    section = data.get("containers")
    if not isinstance(section, dict):
        return _DEFAULT_PORT_OFFSET
    offset = section.get("port_offset")
    if isinstance(offset, bool) or not isinstance(offset, int):
        return _DEFAULT_PORT_OFFSET
    return offset
