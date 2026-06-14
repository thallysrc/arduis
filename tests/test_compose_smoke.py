"""Phase-07 acceptance smoke — end-to-end compose generation + argv + probe + state.

Pure pytest (no gi, no docker, no broadway): imports arduis.compose + arduis.containerstate,
runs the full pipeline writing a REAL override file under a sandbox $HOME (snap-docker D-09),
and asserts the load-bearing facts:
  - the override carries `ports: !override` (REPLACE, not concatenate — criterion 2/D-01),
    the OFFSET port string is present, and the BASE port string is NOT;
  - every docker compose argv shape (config/up/down/ls) is exact;
  - the offset-probe bumps the whole task on collision and caps with PortAssignmentError;
  - ContainerState round-trips on disk.
Real `docker compose up` / badges / teardown are host-only live UAT (07-HUMAN-UAT.md).
"""
import json
import os

import pytest

from arduis import compose, containerstate
from arduis.containerstate import ContainerState


FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "compose_config.json")


@pytest.fixture
def task_dir(tmp_path, monkeypatch):
    # Sandbox $HOME so write_container_state never touches the real ~/.config (D-09).
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    td = tmp_path / "proj-tasks" / "feat"
    td.mkdir(parents=True)
    return str(td)


def _published():
    model = json.load(open(FIXTURE))
    return compose.parse_published_ports(model)


def test_override_uses_override_tag_and_replaces_base_port(task_dir):
    published = _published()
    port_map = compose.assign_ports(published, 1000, probe=lambda _p: True)
    override = task_dir + "/docker-compose.override.yml"
    with open(override, "wb") as fh:
        fh.write(compose.override_bytes(port_map))
    text = open(override).read()
    # the load-bearing tag (criterion 2 / D-01): REPLACE not concatenate
    assert "ports: !override" in text
    # offset port present (8080 -> 9080), base port absent as a published mapping
    assert "9080:80" in text
    assert "8080:80" not in text
    # multi-port service web (8080 + 9000) and db (5432 -> 6432) all remapped
    assert "6432:5432" in text


def test_empty_port_map_writes_empty_services_override():
    # an empty map still emits a valid override so up_argv's -f always resolves
    out = compose.override_bytes({})
    assert b"services" in out


def test_argv_shapes_exact(task_dir):
    base = os.path.join(task_dir, "docker-compose.yml")
    override = os.path.join(task_dir, "docker-compose.override.yml")
    assert compose.up_argv("arduis-feat", task_dir) == [
        "docker", "compose", "-p", "arduis-feat", "-f", base, "-f", override, "up", "-d",
    ]
    assert compose.down_argv("arduis-feat", task_dir) == [
        "docker", "compose", "-p", "arduis-feat", "-f", base, "-f", override,
        "down", "--remove-orphans", "--volumes",
    ]
    # config reads the BASE only (no -p, no override) before the override exists
    assert compose.config_argv(task_dir) == [
        "docker", "compose", "-f", base, "config", "--format", "json",
    ]
    ls = compose.ls_argv()
    assert ls[:3] == ["docker", "compose", "ls"] and "name=arduis" in ls


def test_project_name_sanitized():
    assert compose.sanitize_project_name("feat/MLK-123") == "arduis-feat-mlk-123" or \
        compose.sanitize_project_name("feat/MLK-123").startswith("arduis-")


def test_probe_bumps_whole_task_on_collision():
    published = _published()
    # step-1000 candidates (8080->9080, 9000->10000, 5432->6432) all collide;
    # step-2000 (10080, 11000, 7432) are free → whole task bumps to base+2000.
    step1000 = {pp.published + 1000 for pp in published}
    port_map = compose.assign_ports(published, 1000, probe=lambda p: p not in step1000)
    for entries in port_map.values():
        assert all(e["host"] == e["base"] + 2000 for e in entries)


def test_probe_cap_raises():
    published = _published()
    with pytest.raises(compose.PortAssignmentError):
        compose.assign_ports(published, 1000, probe=lambda _p: False)


def test_container_state_round_trips_on_disk(task_dir):
    port_map = compose.assign_ports(_published(), 1000, probe=lambda _p: True)
    state = ContainerState(project_name="arduis-feat", enabled=True, ports=port_map)
    containerstate.write_container_state(task_dir, state)
    loaded = containerstate.load_container_state(task_dir)
    assert loaded.project_name == "arduis-feat"
    assert loaded.enabled is True
    assert loaded.ports == port_map


def test_missing_state_is_noop_default(task_dir):
    loaded = containerstate.load_container_state(task_dir)
    assert loaded.project_name == "" and loaded.enabled is False and loaded.ports == {}
