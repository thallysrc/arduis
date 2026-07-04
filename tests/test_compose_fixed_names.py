"""Fixed-name resources must be re-namespaced per workspace (CONT-07).

Root cause (reproduced live 2026-07-03, workspace ``bilu``): the root compose
declares networks with an explicit ``name:`` (``keycloak_net``) and 15 services
with a fixed ``container_name:``. ``COMPOSE_PROJECT_NAME`` prefixes only
DEFAULT-named resources — an explicit name is used verbatim, so the second
stack's ``up`` fails ("network keycloak_net exists but was not created for
project arduis-bilu") and container names would collide right after.

Fix: ``fixed_name_overrides`` parses the base compose and emits override
entries renaming every fixed-name resource with the workspace's project prefix
(also giving the user "workspace name inside the container name" for free);
``override_bytes`` merges them with the ports override.
"""
import yaml

from arduis import compose


BASE = """\
services:
  backend:
    image: x
    container_name: livon-backend
    networks: [minhalivon_net]
  keycloak:
    image: y
    container_name: livon-keycloak
  anon:
    image: z
networks:
  minhalivon_net:
    name: minhalivon_net
  keycloak_net:
    name: keycloak_net
  shared:
    external: true
    name: corp_net
volumes:
  postgres_data:
  named_vol:
    name: fixed_vol
"""


def test_fixed_name_overrides_renames_containers_networks_volumes():
    ov = compose.fixed_name_overrides(BASE, "arduis-bilu")
    assert ov["services"] == {
        "backend": {"container_name": "arduis-bilu-livon-backend"},
        "keycloak": {"container_name": "arduis-bilu-livon-keycloak"},
    }
    assert ov["networks"] == {
        "minhalivon_net": {"name": "arduis-bilu_minhalivon_net"},
        "keycloak_net": {"name": "arduis-bilu_keycloak_net"},
    }
    assert ov["volumes"] == {"named_vol": {"name": "arduis-bilu_fixed_vol"}}


def test_fixed_name_overrides_skips_external_and_default_named():
    ov = compose.fixed_name_overrides(BASE, "p")
    # external network is intentionally shared — NEVER renamed
    assert "shared" not in ov["networks"]
    # default-named volume already gets the project prefix from compose itself
    assert "postgres_data" not in ov["volumes"]
    # service without container_name needs no override
    assert "anon" not in ov["services"]


def test_fixed_name_overrides_tolerates_garbage():
    assert compose.fixed_name_overrides(":: broken [", "p") == {
        "services": {}, "networks": {}, "volumes": {}
    }
    assert compose.fixed_name_overrides("just text", "p") == {
        "services": {}, "networks": {}, "volumes": {}
    }


def test_override_bytes_merges_ports_and_names():
    port_map = {"backend": [{"base": 8000, "host": 9000, "target": 8000, "host_ip": None}]}
    names = compose.fixed_name_overrides(BASE, "arduis-bilu")
    data = yaml.safe_load(
        compose.override_bytes(port_map, names).decode("utf-8").replace("!override", "")
    )
    # backend carries BOTH the remapped ports and the renamed container
    assert data["services"]["backend"]["ports"] == ["9000:8000"]
    assert data["services"]["backend"]["container_name"] == "arduis-bilu-livon-backend"
    # keycloak has no published ports but still gets its rename
    assert data["services"]["keycloak"] == {"container_name": "arduis-bilu-livon-keycloak"}
    assert data["networks"]["keycloak_net"] == {"name": "arduis-bilu_keycloak_net"}
    assert data["volumes"]["named_vol"] == {"name": "arduis-bilu_fixed_vol"}


def test_override_bytes_without_names_keeps_old_shape():
    port_map = {"web": [{"base": 80, "host": 1080, "target": 80, "host_ip": None}]}
    text = compose.override_bytes(port_map).decode("utf-8")
    data = yaml.safe_load(text.replace("!override", ""))
    assert data == {"services": {"web": {"ports": ["1080:80"]}}}
    assert "networks" not in data and "volumes" not in data
