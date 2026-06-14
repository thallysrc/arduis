"""GTK-free docker-compose translation layer for Phase 7 (CONT-01/02/03/05).

This is where ALL the real correctness for opt-in isolated containers lives. It
is the pure, unit-testable seam: branch -> ``COMPOSE_PROJECT_NAME`` sanitization
(D-03), the AUTHORITATIVE base-stack reader that parses ``docker compose config
--format json`` (D-02), the deterministic offset + socket-probe port assignment
with clustered collision-retry (D-06), the ``docker-compose.override.yml`` byte
generator, and every ``docker compose`` argv builder (D-05/D-12/D-13).

The load-bearing correctness point (D-01, verified LIVE on the host with docker
29.3.1 / compose v5.1.1): a PLAIN ``ports`` override CONCATENATES the base port
(``['8080', '19080']`` -> both bind -> host collision), while the Compose-spec
``ports: !override`` tag REPLACES it (``['19080']``). ``override_bytes`` MUST emit
that literal tag so round-tripping through ``docker compose config`` yields ONLY
the offset port. The CLAUDE.md note ("rewrite the whole ports list") was necessary
but INSUFFICIENT — the ``!override`` tag is what makes the replacement happen.

GTK-free discipline (CLAUDE.md / D-08): this module imports ``os``, ``re``,
``socket``, ``yaml`` ONLY — never ``gi``. The async IO + json.loads is the thin
``docker_service.py`` wrapper's job (Wave 2); persistence is ``containerstate.py``;
the window orchestration (Wave 3) is pure glue over the functions pinned here.

Threats (see 07-01-PLAN threat register):
- T-07-01 (tampering/EoP): ``sanitize_project_name`` is an allow-list regex and
  argv is always a Python LIST (no shell, no ``shell=True``).
- T-07-02 (tampering): override port strings are built only from INTEGERS plus an
  optional host_ip read from the authoritative ``config`` model — never raw text.
- T-07-03 (DoS): ``assign_ports`` caps at 10 attempts then raises.
"""
from __future__ import annotations

import os
import re
import socket
from dataclasses import dataclass

import yaml

__all__ = [
    "PublishedPort",
    "PortAssignmentError",
    "sanitize_project_name",
    "parse_published_ports",
    "port_free",
    "assign_ports",
    "override_bytes",
    "compose_argv",
    "up_argv",
    "down_argv",
    "config_argv",
    "ls_argv",
]


class PortAssignmentError(Exception):
    """Raised when 10 clustered offset attempts all collide (T-07-03 cap)."""


@dataclass
class PublishedPort:
    """One published port from the authoritative ``config --format json`` model.

    ``host_ip`` is preserved only when the base stack pinned it (e.g.
    ``127.0.0.1:9000:9000``); otherwise ``None``.
    """

    service: str
    target: int
    published: int
    host_ip: str | None = None


# --- branch -> COMPOSE_PROJECT_NAME (D-03, CONT-02, T-07-01) -----------------

_PROJECT_UNSAFE = re.compile(r"[^a-z0-9_-]+")
_PROJECT_DASH_RUNS = re.compile(r"-{2,}")


def sanitize_project_name(branch: str) -> str:
    """Reduce a branch name to a valid, stable ``arduis-<sanitized>`` project name.

    Compose project names are STRICTER than dir names: lowercase letters / digits
    / dashes / underscores only, and must BEGIN with a lowercase letter or digit.
    The ``arduis-`` prefix guarantees the leading-char rule. Empty-after-sanitize
    falls back to ``arduis-task`` so the result can NEVER be invalid.

    This is a SEPARATE sanitizer from ``worktree.sanitize_branch_for_dir`` (which
    allows ``.`` and uppercase — both invalid here). [CITED: docs.docker.com]
    """
    s = _PROJECT_UNSAFE.sub("-", branch.lower())
    s = _PROJECT_DASH_RUNS.sub("-", s).strip("-_")
    return f"arduis-{s}" if s else "arduis-task"


# --- authoritative base-stack reader (D-02, CONT-02/03) ----------------------

def parse_published_ports(config_model: dict) -> list[PublishedPort]:
    """Enumerate published ports from an already-``json.loads``-ed config model.

    Pure (the async service does the IO + json.loads). Iterates
    ``services.<name>.ports[]`` in deterministic order (services in dict order,
    ports in list order), yielding one ``PublishedPort`` per port dict that HAS a
    ``published`` key. Expose-only ports (no ``published``) are skipped. Tolerant:
    a missing ``services`` key or a service with no ``ports`` yields fewer entries
    and never raises.
    """
    result: list[PublishedPort] = []
    for service, spec in config_model.get("services", {}).items():
        for port in spec.get("ports", []) or []:
            if "published" not in port:
                continue  # expose-only — no host binding to remap
            result.append(
                PublishedPort(
                    service=service,
                    target=int(port["target"]),
                    published=int(port["published"]),
                    host_ip=port.get("host_ip"),
                )
            )
    return result


# --- port probe (D-06, 07-RESEARCH Pattern 4 — STRICT, no reuse) -------------

def port_free(host_port: int, host: str = "127.0.0.1") -> bool:
    """True if ``host_port`` can be bound on ``host`` right now.

    STRICT: ``SO_REUSEADDR`` is OFF so a port held by another process reads as
    taken. Probe-then-bind TOCTOU is accepted (D-06): the window is tiny and
    compose ``up`` fails visibly if the port is lost between probe and bind.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    try:
        s.bind((host, host_port))
        return True
    except OSError:
        return False
    finally:
        s.close()


# --- deterministic offset + probe + clustered retry (D-06, OD-6, CONT-03) ----

def assign_ports(published, offset, probe=port_free):
    """Map each base published port -> base + a clustered task offset, probed free.

    On EACH attempt every service's candidate host port is
    ``base_published + offset * (attempt + 1)`` (1000, 2000, ...). ALL candidates
    are probed; if ALL are free the map commits, otherwise the WHOLE task bumps to
    the next step (clustered / predictable) and re-probes. Capped at 10 attempts,
    then raises ``PortAssignmentError`` (T-07-03).

    ``probe`` is INJECTED with the contract ``probe(host_port: int) -> bool`` (one
    positional int arg; the host is fixed to ``127.0.0.1`` inside the default
    ``port_free``). Tests pass a mock so no real sockets are bound.

    Returns an ordered ``{service: [{"base", "host", "target", "host_ip"}, ...]}``
    map (services in input order). The per-service LIST supports multi-port
    services (e.g. ``web`` with two ports) so ``override_bytes`` can rebuild the
    whole ports list. Empty input -> ``{}`` (no raise).
    """
    if not published:
        return {}

    for attempt in range(10):
        step = offset * (attempt + 1)
        candidates = [(pp, pp.published + step) for pp in published]
        if all(probe(host_port) for _, host_port in candidates):
            port_map: dict = {}
            for pp, host_port in candidates:
                port_map.setdefault(pp.service, []).append(
                    {
                        "base": pp.published,
                        "host": host_port,
                        "target": pp.target,
                        "host_ip": pp.host_ip,
                    }
                )
            return port_map

    raise PortAssignmentError(
        f"could not find a free clustered offset after 10 attempts "
        f"(offset step {offset})"
    )


# --- the load-bearing override generator (D-01/D-04, CONT-02/03) -------------

class _Override(list):
    """A list that PyYAML serializes with the Compose-spec local ``!override`` tag."""


def _repr_override(dumper, data):
    return dumper.represent_sequence("!override", list(data))


yaml.add_representer(_Override, _repr_override)


def _port_string(entry: dict) -> str:
    """``"<host>:<target>"`` or ``"<host_ip>:<host>:<target>"`` when pinned."""
    host = entry["host"]
    target = entry["target"]
    host_ip = entry.get("host_ip")
    if host_ip:
        return f"{host_ip}:{host}:{target}"
    return f"{host}:{target}"


def override_bytes(port_map: dict) -> bytes:
    """Emit a ``docker-compose.override.yml`` byte payload (D-01 — load-bearing).

    For every service in ``port_map`` (the ``assign_ports`` shape) emit
    ``ports: !override`` (the literal tag — REPLACING, not appending) with the
    offset ``"<host>:<target>"`` strings (host_ip preserved as
    ``"<ip>:<host>:<target>"``). Round-tripping the bytes through
    ``docker compose config`` yields ONLY the offset port — never the base port.

    Empty-map case (D-05): ``override_bytes({})`` returns a valid minimal override
    with an empty ``services: {}`` map, so the window can ALWAYS write an override
    file even when a stack has no published ports (``up_argv`` unconditionally
    passes ``-f <override>``).
    """
    services: dict = {}
    for service, entries in port_map.items():
        services[service] = {"ports": _Override(_port_string(e) for e in entries)}

    body = yaml.dump(
        {"services": services},
        default_flow_style=False,
        sort_keys=False,
    )
    header = (
        "# Generated by arduis (Phase 7) — DO NOT EDIT.\n"
        "# Remaps each service's published ports via the Compose `!override` tag\n"
        "# (REPLACE, not append) so the offset host ports do not collide.\n"
    )
    return (header + body).encode("utf-8")


# --- docker compose argv builders (D-05/D-12/D-13, CONT-05, T-07-01) ---------

def compose_argv(project: str, task_dir: str, *cmd: str) -> list[str]:
    """``docker compose -p <project> -f <base> -f <override> <cmd...>`` as a LIST.

    Both ``-f`` paths live under ``task_dir`` (which is under ``$HOME`` — D-09 so
    snap-docker can read them). argv stays a LIST — never joined into a shell
    string (T-07-01).
    """
    base = os.path.join(task_dir, "docker-compose.yml")
    override = os.path.join(task_dir, "docker-compose.override.yml")
    return ["docker", "compose", "-p", project, "-f", base, "-f", override, *cmd]


def up_argv(project: str, task_dir: str) -> list[str]:
    """``docker compose ... up -d``."""
    return compose_argv(project, task_dir, "up", "-d")


def down_argv(project: str, task_dir: str) -> list[str]:
    """``docker compose ... down --remove-orphans --volumes`` (D-12 teardown)."""
    return compose_argv(project, task_dir, "down", "--remove-orphans", "--volumes")


def config_argv(task_dir: str) -> list[str]:
    """``docker compose -f <base> config --format json`` — base ONLY (D-02).

    No ``-p`` and no override: this enumerates the authoritative published ports
    BEFORE the override exists.
    """
    return [
        "docker",
        "compose",
        "-f",
        os.path.join(task_dir, "docker-compose.yml"),
        "config",
        "--format",
        "json",
    ]


def ls_argv() -> list[str]:
    """``docker compose ls --all --filter name=arduis --format json`` (D-13)."""
    return [
        "docker",
        "compose",
        "ls",
        "--all",
        "--filter",
        "name=arduis",
        "--format",
        "json",
    ]
