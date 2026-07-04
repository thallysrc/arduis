"""Workspace volumes are CLONED from the root stack's data (CONT-10, 2026-07-03).

``fixed_name_overrides`` gives each workspace its own named volumes
(``<project>_<key>``) — isolation works, but the databases are born EMPTY.
Dogfooding feedback (2026-07-03): duplicating a stack must duplicate the DATA
— a workspace postgres/mongo/keycloak-db should start as a snapshot of the
root stack's volumes at creation time.

``volume_clone_plan`` maps each top-level named volume of the AUTHORITATIVE
``docker compose config --format json`` model to a (source, dest) pair:

- source: the ROOT stack's volume — the explicit ``name:`` when the base pins
  one, else ``<root_project>_<key>`` (compose default naming; the model's
  top-level ``name`` is the root project).
- dest: ``<project>_<key>`` — the same name the workspace override /
  ``COMPOSE_PROJECT_NAME`` produces (verified live: ``arduis-feat-teste_keycloak_db``).

``external: true`` volumes are shared BY DESIGN and never cloned. The window
runs the plan BEFORE ``docker compose up``: dest already exists → skip (a
re-isolated workspace keeps its data); source missing → skip (nothing to
clone); else ``docker volume create`` with compose-compatible labels + a
throwaway ``alpine cp -a`` container copies the bytes.
"""
from arduis import compose


MODEL = {
    "name": "livon-saude",
    "volumes": {
        "keycloak_db": {"name": "livon-saude_keycloak_db"},
        "mongo_data": {"name": "livon-saude_mongo_data"},
        "plain": {},
        "shared": {"name": "org_shared", "external": True},
    },
}


def test_plan_maps_explicit_and_default_named_volumes():
    plan = compose.volume_clone_plan(MODEL, "arduis-ws")
    assert {p["key"]: (p["source"], p["dest"]) for p in plan} == {
        "keycloak_db": ("livon-saude_keycloak_db", "arduis-ws_keycloak_db"),
        "mongo_data": ("livon-saude_mongo_data", "arduis-ws_mongo_data"),
        "plain": ("livon-saude_plain", "arduis-ws_plain"),
    }


def test_plan_skips_external_volumes():
    plan = compose.volume_clone_plan(MODEL, "arduis-ws")
    assert not any(p["key"] == "shared" for p in plan)


def test_plan_tolerates_garbage_model():
    assert compose.volume_clone_plan({}, "p") == []
    assert compose.volume_clone_plan({"volumes": None}, "p") == []
    assert compose.volume_clone_plan(
        {"volumes": {"v": "notadict"}}, "p"
    ) == []
    # no root project name and no explicit name -> source underivable -> skip
    assert compose.volume_clone_plan({"volumes": {"v": {}}}, "p") == []


def test_volume_exists_argv():
    assert compose.volume_exists_argv("livon-saude_mongo_data") == [
        "docker", "volume", "inspect", "livon-saude_mongo_data",
    ]


def test_volume_create_argv_carries_compose_labels():
    # compose must ADOPT the pre-created volume on `up` — it matches by name
    # and project/volume labels, so both labels are load-bearing.
    assert compose.volume_create_argv("arduis-ws_mongo_data", "arduis-ws", "mongo_data") == [
        "docker", "volume", "create",
        "--label", "com.docker.compose.project=arduis-ws",
        "--label", "com.docker.compose.volume=mongo_data",
        "arduis-ws_mongo_data",
    ]


def test_volume_clone_argv_copies_source_readonly():
    assert compose.volume_clone_argv("src_vol", "dst_vol") == [
        "docker", "run", "--rm",
        "-v", "src_vol:/from:ro",
        "-v", "dst_vol:/to",
        "alpine", "cp", "-a", "/from/.", "/to/",
    ]


def test_volume_remove_argv():
    # cleanup path: a failed clone must not leave a half-copied volume behind
    # (compose would adopt it and postgres would crash on partial data).
    assert compose.volume_remove_argv("dst_vol") == [
        "docker", "volume", "rm", "-f", "dst_vol",
    ]
