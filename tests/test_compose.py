"""Unit coverage for the GTK-free compose translation layer (CONT-01/02/03/05).

Pure imports of ``arduis.compose`` — NO gi, NO real sockets (the probe is
injected), NO docker invoked (the parser reads a captured ``config --format
json`` fixture). The load-bearing assertion is that ``override_bytes`` emits the
literal ``ports: !override`` tag (Pitfall 1: a plain override CONCATENATES the
base port; the tag REPLACES it).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from arduis.compose import (
    PortAssignmentError,
    PublishedPort,
    assign_ports,
    compose_argv,
    config_argv,
    down_argv,
    ls_argv,
    override_bytes,
    parse_published_ports,
    sanitize_project_name,
    up_argv,
)

FIXTURE = Path(__file__).parent / "fixtures" / "compose_config.json"
VALID_PROJECT = re.compile(r"^arduis-[a-z0-9][a-z0-9_-]*$")


# --- Task 1: sanitize_project_name (D-03, CONT-02) ---------------------------

def test_sanitize_lowercases_and_replaces_slash():
    assert sanitize_project_name("feature/Cool_Thing") == "arduis-feature-cool_thing"


def test_sanitize_empty_after_strip_falls_back():
    assert sanitize_project_name("---") == "arduis-task"


def test_sanitize_single_char_and_valid_pattern():
    assert sanitize_project_name("a") == "arduis-a"
    assert VALID_PROJECT.match(sanitize_project_name("a"))


def test_sanitize_uppercase_and_dash_collapse():
    assert sanitize_project_name("UPPER--Mix") == "arduis-upper-mix"


def test_sanitize_results_always_valid_compose_names():
    for branch in ["feat/X", "...weird...", "/", "MiXeD/Case-99", "a/b/c"]:
        assert VALID_PROJECT.match(sanitize_project_name(branch)), branch


# --- Task 1: parse_published_ports (D-02, CONT-02/03) ------------------------

def test_parse_returns_ordered_entries_from_fixture():
    model = json.loads(FIXTURE.read_text())
    ports = parse_published_ports(model)

    assert ports == [
        PublishedPort(service="web", target=80, published=8080, host_ip=None),
        PublishedPort(
            service="web", target=9000, published=9000, host_ip="127.0.0.1"
        ),
        PublishedPort(service="db", target=5432, published=5432, host_ip=None),
    ]


def test_parse_empty_model_returns_empty():
    assert parse_published_ports({}) == []


def test_parse_service_with_no_ports_returns_empty():
    assert parse_published_ports({"services": {"x": {}}}) == []


def test_parse_skips_expose_only_port():
    model = {
        "services": {
            "svc": {
                "ports": [
                    {"mode": "ingress", "target": 8000},  # no "published"
                    {"mode": "ingress", "target": 80, "published": "8080"},
                ]
            }
        }
    }
    ports = parse_published_ports(model)
    assert ports == [
        PublishedPort(service="svc", target=80, published=8080, host_ip=None)
    ]


# --- Task 1: argv builders (D-05/D-12/D-13, CONT-05) -------------------------

def test_compose_argv_full_shape():
    assert compose_argv("arduis-x", "/h/u/proj-tasks/x", "up", "-d") == [
        "docker",
        "compose",
        "-p",
        "arduis-x",
        "-f",
        "/h/u/proj-tasks/x/docker-compose.yml",
        "-f",
        "/h/u/proj-tasks/x/docker-compose.override.yml",
        "up",
        "-d",
    ]


def test_up_argv_ends_with_up_d():
    assert up_argv("arduis-x", "/h/u/proj-tasks/x")[-2:] == ["up", "-d"]


def test_down_argv_teardown_flags():
    assert down_argv("arduis-x", "/h/u/proj-tasks/x")[-3:] == [
        "down",
        "--remove-orphans",
        "--volumes",
    ]


def test_config_argv_reads_base_only():
    assert config_argv("/h/u/proj-tasks/x") == [
        "docker",
        "compose",
        "-f",
        "/h/u/proj-tasks/x/docker-compose.yml",
        "config",
        "--format",
        "json",
    ]


def test_ls_argv_reconcile_query():
    assert ls_argv() == [
        "docker",
        "compose",
        "ls",
        "--all",
        "--filter",
        "name=arduis",
        "--format",
        "json",
    ]


# --- Task 1 + 2: GTK-free discipline (CLAUDE.md / D-08) ----------------------

def test_compose_module_is_gtk_free():
    source = Path(__file__).parent.parent / "src" / "arduis" / "compose.py"
    text = source.read_text()
    assert "import gi" not in text
    assert "from gi" not in text


# --- Task 2: assign_ports (D-06, OD-6, CONT-03) ------------------------------

def _published_three():
    """The fixture's three ports, in order."""
    return [
        PublishedPort(service="web", target=80, published=8080, host_ip=None),
        PublishedPort(
            service="web", target=9000, published=9000, host_ip="127.0.0.1"
        ),
        PublishedPort(service="db", target=5432, published=5432, host_ip=None),
    ]


def test_assign_ports_all_free_offset_1000():
    port_map = assign_ports(_published_three(), 1000, probe=lambda p: True)

    assert port_map == {
        "web": [
            {"base": 8080, "host": 9080, "target": 80, "host_ip": None},
            {"base": 9000, "host": 10000, "target": 9000, "host_ip": "127.0.0.1"},
        ],
        "db": [
            {"base": 5432, "host": 6432, "target": 5432, "host_ip": None},
        ],
    }


def test_assign_ports_collision_bumps_whole_task():
    # Free only at step 2000 (base + 2000) — whole task bumps together (clustered).
    free_at = {8080 + 2000, 9000 + 2000, 5432 + 2000}

    def probe(host_port):
        return host_port in free_at

    port_map = assign_ports(_published_three(), 1000, probe=probe)

    assert port_map["web"][0]["host"] == 10080  # 8080 + 2000
    assert port_map["web"][1]["host"] == 11000  # 9000 + 2000
    assert port_map["db"][0]["host"] == 7432  # 5432 + 2000


def test_assign_ports_caps_at_ten_attempts():
    with pytest.raises(PortAssignmentError):
        assign_ports(_published_three(), 1000, probe=lambda p: False)


def test_assign_ports_empty_input_returns_empty():
    assert assign_ports([], 1000, probe=lambda p: True) == {}


# --- Task 2: override_bytes — the load-bearing !override tag (D-01) ----------

def _offset_map():
    return assign_ports(_published_three(), 1000, probe=lambda p: True)


def test_override_bytes_contains_literal_override_tag_per_service():
    text = override_bytes(_offset_map()).decode("utf-8")
    # Both remapped services carry the literal tag (Pitfall 1 closure).
    assert text.count("ports: !override") == 2


def test_override_bytes_renders_host_target_strings():
    text = override_bytes(_offset_map()).decode("utf-8")
    assert "9080:80" in text  # web base 8080 -> host 9080
    assert "6432:5432" in text  # db base 5432 -> host 6432


def test_override_bytes_preserves_host_ip():
    text = override_bytes(_offset_map()).decode("utf-8")
    assert "127.0.0.1:10000:9000" in text  # web's pinned second port


def test_override_bytes_never_emits_base_port():
    text = override_bytes(_offset_map()).decode("utf-8")
    # The base published ports must NOT survive (the concatenate trap).
    assert "8080" not in text
    assert "5432:5432" not in text  # base db host:target would be 5432:5432


def test_override_bytes_round_trips_through_yaml_with_override_tag():
    raw = override_bytes(_offset_map())

    # Register the local !override tag so SafeLoader can read it back — this
    # proves the tag is emitted as a REAL YAML local tag, not inline text.
    yaml.add_constructor(
        "!override",
        lambda loader, node: loader.construct_sequence(node),
        Loader=yaml.SafeLoader,
    )
    loaded = yaml.load(raw, Loader=yaml.SafeLoader)

    assert loaded["services"]["web"]["ports"] == ["9080:80", "127.0.0.1:10000:9000"]
    assert loaded["services"]["db"]["ports"] == ["6432:5432"]


def test_override_bytes_empty_map_is_valid_minimal_override():
    raw = override_bytes({})
    text = raw.decode("utf-8")
    assert "services: {}" in text

    loaded = yaml.safe_load(raw)
    assert loaded == {"services": {}}
