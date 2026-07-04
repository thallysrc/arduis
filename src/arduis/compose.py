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
    "env_file_paths",
    "env_copy_plan",
    "fixed_name_overrides",
    "user_overrides",
    "volume_init_overrides",
    "volume_clone_plan",
    "volume_exists_argv",
    "volume_create_argv",
    "volume_clone_argv",
    "volume_remove_argv",
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
    falls back to ``arduis-workspace`` so the result can NEVER be invalid.

    This is a SEPARATE sanitizer from ``worktree.sanitize_branch_for_dir`` (which
    allows ``.`` and uppercase — both invalid here). [CITED: docs.docker.com]
    """
    s = _PROJECT_UNSAFE.sub("-", branch.lower())
    s = _PROJECT_DASH_RUNS.sub("-", s).strip("-_")
    return f"arduis-{s}" if s else "arduis-workspace"


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
    """Map each base published port -> base + a clustered workspace offset, probed free.

    On EACH attempt every service's candidate host port is
    ``base_published + offset * (attempt + 1)`` (1000, 2000, ...). ALL candidates
    are probed; if ALL are free the map commits, otherwise the WHOLE workspace bumps to
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


def override_bytes(port_map: dict, name_overrides: dict | None = None) -> bytes:
    """Emit a ``docker-compose.override.yml`` byte payload (D-01 — load-bearing).

    For every service in ``port_map`` (the ``assign_ports`` shape) emit
    ``ports: !override`` (the literal tag — REPLACING, not appending) with the
    offset ``"<host>:<target>"`` strings (host_ip preserved as
    ``"<ip>:<host>:<target>"``). Round-tripping the bytes through
    ``docker compose config`` yields ONLY the offset port — never the base port.

    ``name_overrides`` (CONT-07, the ``fixed_name_overrides`` shape) is merged
    in: per-service ``container_name`` renames plus top-level ``networks``/
    ``volumes`` sections — scalar keys, so the plain compose merge REPLACES them
    (no ``!override`` tag needed).

    Empty-map case (D-05): ``override_bytes({})`` returns a valid minimal override
    with an empty ``services: {}`` map, so the window can ALWAYS write an override
    file even when a stack has no published ports (``up_argv`` unconditionally
    passes ``-f <override>``).
    """
    names = name_overrides or {}
    services: dict = {}
    for service, entries in port_map.items():
        services[service] = {"ports": _Override(_port_string(e) for e in entries)}
    for service, extra in names.get("services", {}).items():
        services.setdefault(service, {}).update(extra)

    doc: dict = {"services": services}
    for section in ("networks", "volumes"):
        if names.get(section):
            doc[section] = names[section]

    body = yaml.dump(
        doc,
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

def compose_argv(project: str, workspace_dir: str, *cmd: str) -> list[str]:
    """``docker compose -p <project> -f <base> -f <override> <cmd...>`` as a LIST.

    Both ``-f`` paths live under ``workspace_dir`` (which is under ``$HOME`` — D-09 so
    snap-docker can read them). argv stays a LIST — never joined into a shell
    string (T-07-01).
    """
    base = os.path.join(workspace_dir, "docker-compose.yml")
    override = os.path.join(workspace_dir, "docker-compose.override.yml")
    return ["docker", "compose", "-p", project, "-f", base, "-f", override, *cmd]


def up_argv(project: str, workspace_dir: str) -> list[str]:
    """``docker compose ... up -d``."""
    return compose_argv(project, workspace_dir, "up", "-d")


def down_argv(project: str, workspace_dir: str) -> list[str]:
    """``docker compose ... down --remove-orphans --volumes`` (D-12 teardown)."""
    return compose_argv(project, workspace_dir, "down", "--remove-orphans", "--volumes")


def config_argv(workspace_dir: str) -> list[str]:
    """``docker compose -f <base> config --format json`` — base ONLY (D-02).

    No ``-p`` and no override: this enumerates the authoritative published ports
    BEFORE the override exists.
    """
    return [
        "docker",
        "compose",
        "-f",
        os.path.join(workspace_dir, "docker-compose.yml"),
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


# --- root-only env files → workspace (CONT-06) --------------------------------
#
# Fresh worktrees carry NO gitignored files. When the base compose points
# ``env_file:`` inside a member repo (``./backend/app/.env``) the file exists in
# the ROOT checkout but not in a new worktree, and ``docker compose config``
# exits 1 before the isolation chain even starts. These two pure helpers let the
# window copy exactly the files compose will ask for — nothing else.

def env_file_paths(base_text: str) -> list[str]:
    """Relative ``env_file`` paths declared by ``services.*`` in the base compose.

    Tolerant of all three Compose-spec forms (string, list of strings, list of
    ``{path, required}`` maps) and of garbage input (broken YAML / non-mapping
    services → ``[]``). Absolute paths are skipped — they resolve identically
    from the workspace, so there is nothing to materialize. Deduped, in
    declaration order.
    """
    try:
        model = yaml.safe_load(base_text)
    except yaml.YAMLError:
        return []
    if not isinstance(model, dict):
        return []
    services = model.get("services")
    if not isinstance(services, dict):
        return []
    out: list[str] = []
    for svc in services.values():
        if not isinstance(svc, dict):
            continue
        raw = svc.get("env_file")
        if raw is None:
            continue
        for item in raw if isinstance(raw, list) else [raw]:
            if isinstance(item, dict):
                item = item.get("path")
            if not isinstance(item, str) or not item or os.path.isabs(item):
                continue
            if item not in out:
                out.append(item)
    return out


def env_copy_plan(
    root: str, workspace_dir: str, rel_paths: list[str]
) -> list[tuple[str, str]]:
    """``(src, dst)`` pairs for env files present in the root layout but missing
    from the workspace.

    Skips: traversal outside the roots (T-03.2-01 discipline — the rel path
    comes from a user-editable compose file), missing sources, existing
    destinations (a per-workspace edit wins), and any destination whose parent
    resolves OUTSIDE the workspace dir — a non-chosen repo is a symlink into the
    shared root (D-09) and must never be written through.
    """
    ws_real = os.path.realpath(workspace_dir)
    root_real = os.path.realpath(root)
    plan: list[tuple[str, str]] = []
    for rel in rel_paths:
        norm = os.path.normpath(rel)
        if os.path.isabs(norm) or norm == ".." or norm.startswith(".." + os.sep):
            continue
        src = os.path.join(root_real, norm)
        dst = os.path.join(workspace_dir, norm)
        if not os.path.isfile(src):
            continue
        if os.path.lexists(dst):
            continue
        parent_real = os.path.realpath(os.path.dirname(dst))
        if parent_real != ws_real and not parent_real.startswith(ws_real + os.sep):
            continue
        plan.append((src, dst))
    return plan


# --- bind-mounted services run as the HOST user (CONT-08) ---------------------
#
# App containers running as root write build artifacts (__pycache__, .venv,
# node_modules) through the bind mounts into the worktrees. The conclude
# clean-gate passes (all gitignored) but ``git worktree remove`` then hits
# EACCES on the root-owned files — conclude blocked on every workspace whose
# stack ever ran (reproduced live 2026-07-03, ``feat-teste``: 3042 root files).

def user_overrides(config_model: dict, uid: int, gid: int) -> dict:
    """``user: "<uid>:<gid>"`` override entries for every bind-mounting service.

    Walks the AUTHORITATIVE ``docker compose config --format json`` model (the
    ``parse_published_ports`` input — volumes already normalized to long form,
    so bind detection is ``type == "bind"``, never short-syntax string parsing).
    Only services that bind-mount get the override: they are the ones writing
    into the worktree. Services on named volumes alone (e.g. postgres, whose
    initdb breaks under an arbitrary uid) and services whose base already pins
    ``user:`` are left untouched. Tolerant of garbage input (non-dict services/
    volumes → skipped). The shape merges into ``fixed_name_overrides``'s
    per-service dicts for a single ``override_bytes`` write.
    """
    out: dict = {"services": {}}
    services = config_model.get("services")
    if not isinstance(services, dict):
        return out
    for svc, body in services.items():
        if not isinstance(body, dict):
            continue
        if body.get("user"):
            continue  # base pinned a user — its call, never overridden
        volumes = body.get("volumes")
        if not isinstance(volumes, list):
            continue
        if any(
            isinstance(v, dict) and v.get("type") == "bind" for v in volumes
        ):
            out["services"][svc] = {"user": f"{uid}:{gid}"}
    return out


# --- volume-init services: chown volumes for CONT-08 services (CONT-09) -------
#
# A CONT-08 service that ALSO mounts a volume (the anonymous ``node_modules``
# shadow) EACCESes on a fresh workspace: the fresh volume is initialized with
# the IMAGE's ownership (root) and the host-uid process cannot write into it
# (reproduced live 2026-07-03, Livon frontend: 243 restarts on ``npm ERR!
# EACCES``). Anonymous volumes are promoted to named ones (the Compose merge
# keys service volumes by TARGET, so the override entry swaps in; the project
# name keeps them per-workspace) so a one-shot init service can mount the same
# volume, chown it as root, and gate the app service via ``depends_on``.

def volume_init_overrides(
    config_model: dict, users: dict, uid: int, gid: int
) -> dict:
    """Init-service override entries for every CONT-08 service mounting volumes.

    For each service in ``users["services"]`` (the ``user_overrides`` output)
    whose model entry mounts ``type == "volume"`` volumes, returns
    ``{"services": {...}, "volumes": {...}}`` carrying: named-volume
    declarations replacing anonymous mounts, a ``<svc>-arduis-init`` one-shot
    running ``chown -R <uid>:<gid>`` as root over the targets, and a
    ``service_completed_successfully`` ``depends_on`` on the service. The init
    reuses the SERVICE'S OWN image so Docker's copy-from-image seeds the volume
    with the right content before the chown. Build-only services (no ``image``
    in the model) are skipped — there is no resolvable image to run the init
    with. Tolerant of garbage input (non-dict services/volumes → skipped).
    """
    out: dict = {"services": {}, "volumes": {}}
    services = config_model.get("services")
    if not isinstance(services, dict):
        return out
    for svc in users.get("services", {}):
        body = services.get(svc)
        if not isinstance(body, dict):
            continue
        image = body.get("image")
        if not image:
            continue
        volumes = body.get("volumes")
        if not isinstance(volumes, list):
            continue
        mounts: list[str] = []       # "<key>:<target>" for the init service
        replacements: list[str] = []  # anon → named swaps on the app service
        for vol in volumes:
            if not isinstance(vol, dict) or vol.get("type") != "volume":
                continue
            target = vol.get("target")
            if not target:
                continue
            source = vol.get("source")
            if not source:
                # ordinal among the volume mounts — stable however many bind
                # mounts precede it in the service's list
                source = f"arduis-init-{svc}-{len(mounts)}"
                out["volumes"][source] = {}
                replacements.append(f"{source}:{target}")
            mounts.append(f"{source}:{target}")
        if not mounts:
            continue
        init = f"{svc}-arduis-init"
        out["services"][init] = {
            "image": image,
            "user": "0:0",
            "network_mode": "none",
            "restart": "no",
            "entrypoint": [
                "chown", "-R", f"{uid}:{gid}",
                *(m.split(":", 1)[1] for m in mounts),
            ],
            "volumes": mounts,
        }
        entry: dict = {
            "depends_on": {
                init: {"condition": "service_completed_successfully"}
            },
        }
        if replacements:
            entry = {"volumes": replacements, **entry}
        out["services"][svc] = entry
    return out


# --- clone root-stack volume DATA into the workspace volumes (CONT-10) --------
#
# fixed_name_overrides / COMPOSE_PROJECT_NAME give each workspace its own named
# volumes — isolated but EMPTY. Duplicating the stack must duplicate the data
# (dogfooding 2026-07-03): a workspace postgres/mongo/keycloak-db starts as a
# snapshot of the root stack's volume at creation time. The window runs the
# plan BEFORE `up`: dest exists → skip (re-isolation keeps data); source
# missing → skip; else create dest with compose-compatible labels and copy the
# bytes via a throwaway alpine container. A failed copy removes the dest so
# compose falls back to a fresh empty volume instead of adopting partial data.

def volume_clone_plan(config_model: dict, project: str) -> list[dict]:
    """``[{"key", "source", "dest"}]`` for every top-level named volume.

    source: the root stack's volume — explicit ``name:`` when the base pins one,
    else ``<root_project>_<key>`` (compose default naming; the model's top-level
    ``name`` is the root project). dest: ``<project>_<key>``, matching what the
    workspace override / ``COMPOSE_PROJECT_NAME`` produce. ``external: true``
    volumes are shared by design and never cloned. Tolerant of garbage input.
    """
    plan: list[dict] = []
    volumes = config_model.get("volumes")
    if not isinstance(volumes, dict):
        return plan
    root = config_model.get("name")
    for key, body in volumes.items():
        if not isinstance(body, dict) or body.get("external"):
            continue
        source = body.get("name") or (root and f"{root}_{key}")
        if not source:
            continue  # no explicit name and no root project — underivable
        plan.append({"key": key, "source": source, "dest": f"{project}_{key}"})
    return plan


def volume_exists_argv(name: str) -> list[str]:
    """``docker volume inspect <name>`` — rc 0 iff the volume exists."""
    return ["docker", "volume", "inspect", name]


def volume_create_argv(name: str, project: str, key: str) -> list[str]:
    """``docker volume create`` with the labels compose matches on at ``up``."""
    return [
        "docker", "volume", "create",
        "--label", f"com.docker.compose.project={project}",
        "--label", f"com.docker.compose.volume={key}",
        name,
    ]


def volume_clone_argv(source: str, dest: str) -> list[str]:
    """Copy every byte of ``source`` into ``dest`` via a throwaway container.

    ``cp -a`` preserves ownership/permissions (postgres refuses a data dir with
    the wrong owner); the source mounts read-only so a bug here can never touch
    the root stack's data.
    """
    return [
        "docker", "run", "--rm",
        "-v", f"{source}:/from:ro",
        "-v", f"{dest}:/to",
        "alpine", "cp", "-a", "/from/.", "/to/",
    ]


def volume_remove_argv(name: str) -> list[str]:
    """``docker volume rm -f`` — the failed-clone cleanup path."""
    return ["docker", "volume", "rm", "-f", name]


# --- fixed-name resources → per-workspace names (CONT-07) ----------------------
#
# ``COMPOSE_PROJECT_NAME`` isolates only DEFAULT-named resources. An explicit
# ``container_name:`` / network ``name:`` / volume ``name:`` is used VERBATIM, so
# the second workspace's ``up`` collides with the root stack ("network
# keycloak_net exists but was not created for project ..."). Renaming them with
# the project prefix restores isolation — and puts the workspace name in the
# container names, which is also the wanted UX.

def fixed_name_overrides(base_text: str, project: str) -> dict:
    """Override entries renaming every fixed-name resource in the base compose.

    Returns ``{"services": {svc: {"container_name": "<project>-<orig>"}},
    "networks"/"volumes": {key: {"name": "<project>_<orig>"}}}`` — empty dicts
    for anything absent. ``external: true`` resources are intentionally shared
    and never renamed. Tolerant of garbage input (broken YAML → all empty).
    """
    out: dict = {"services": {}, "networks": {}, "volumes": {}}
    try:
        model = yaml.safe_load(base_text)
    except yaml.YAMLError:
        return out
    if not isinstance(model, dict):
        return out

    services = model.get("services")
    if isinstance(services, dict):
        for svc, body in services.items():
            if not isinstance(body, dict):
                continue
            orig = body.get("container_name")
            if isinstance(orig, str) and orig:
                out["services"][svc] = {"container_name": f"{project}-{orig}"}

    for section, sep in (("networks", "_"), ("volumes", "_")):
        entries = model.get(section)
        if not isinstance(entries, dict):
            continue
        for key, body in entries.items():
            if not isinstance(body, dict):
                continue
            if body.get("external"):
                continue  # shared on purpose — never renamed
            orig = body.get("name")
            if isinstance(orig, str) and orig:
                out[section][key] = {"name": f"{project}{sep}{orig}"}

    return out
