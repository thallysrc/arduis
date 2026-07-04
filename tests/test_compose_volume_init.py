"""Volume-init services fix root-owned volumes under CONT-08 (2026-07-03).

CONT-08 runs bind-mounting services as the HOST user — but a service that ALSO
mounts a volume (the classic anonymous ``node_modules`` shadow) then EACCESes:
a fresh workspace's fresh volume is initialized with the IMAGE's ownership
(root), and the uid-1000 process cannot write into it. Reproduced live
(workspace ``nova-feature``, Livon frontend: 243 restarts on
``npm ERR! EACCES /opt/frontend/app/node_modules``).

Fix: for every service that received the CONT-08 ``user:`` override AND mounts
a ``type == "volume"`` entry, ``volume_init_overrides`` emits into the SAME
generated override:

- a named volume replacing each anonymous one (the Compose merge keys service
  volumes by target path, so the entry swaps in cleanly; ``COMPOSE_PROJECT_NAME``
  keeps it per-workspace);
- a one-shot ``<svc>-arduis-init`` service using the SERVICE'S OWN image — the
  first mount happens there, so Docker's copy-from-image seeds the right
  content — running ``chown -R <uid>:<gid>`` as root over the mount targets;
- ``depends_on: {<init>: {condition: service_completed_successfully}}`` on the
  service, so it only starts on a chowned volume.

Services with only bind mounts, services the base pinned ``user:`` on (absent
from the CONT-08 dict), and services without a resolvable ``image`` (build-only)
get NO init.
"""
import yaml

from arduis import compose


MODEL = {
    "services": {
        "frontend": {
            "image": "node:14-alpine",
            "volumes": [
                {"type": "bind", "source": "/ws/frontend/app",
                 "target": "/opt/frontend/app", "bind": {}},
                {"type": "volume", "target": "/opt/frontend/app/node_modules",
                 "volume": {}},
            ],
        },
        "backend": {
            "image": "x",
            "volumes": [
                {"type": "bind", "source": "/ws/backend", "target": "/app"},
            ],
        },
        "cachey": {
            "image": "y",
            "volumes": [
                {"type": "bind", "source": "/ws/cachey", "target": "/src"},
                {"type": "volume", "source": "node_cache", "target": "/cache"},
            ],
        },
        "buildonly": {
            "build": {"context": "."},
            "volumes": [
                {"type": "bind", "source": "/ws/b", "target": "/b"},
                {"type": "volume", "target": "/b/node_modules"},
            ],
        },
    }
}

USERS = {
    "services": {
        "frontend": {"user": "1000:1000"},
        "backend": {"user": "1000:1000"},
        "cachey": {"user": "1000:1000"},
        "buildonly": {"user": "1000:1000"},
    }
}


def test_anonymous_volume_gets_named_volume_init_service_and_depends_on():
    ov = compose.volume_init_overrides(MODEL, USERS, 1000, 1000)
    key = "arduis-init-frontend-0"
    assert ov["volumes"][key] == {}
    assert ov["services"]["frontend"] == {
        "volumes": [f"{key}:/opt/frontend/app/node_modules"],
        "depends_on": {
            "frontend-arduis-init": {
                "condition": "service_completed_successfully"
            }
        },
    }
    assert ov["services"]["frontend-arduis-init"] == {
        "image": "node:14-alpine",
        "user": "0:0",
        "network_mode": "none",
        "restart": "no",
        "entrypoint": [
            "chown", "-R", "1000:1000", "/opt/frontend/app/node_modules"
        ],
        "volumes": [f"{key}:/opt/frontend/app/node_modules"],
    }


def test_named_volume_reuses_base_key_without_redeclaring():
    ov = compose.volume_init_overrides(MODEL, USERS, 1000, 1000)
    # the base already declares node_cache — no top-level redeclare, and the
    # service's own volume list is untouched (only depends_on is added).
    assert "node_cache" not in ov["volumes"]
    assert ov["services"]["cachey"] == {
        "depends_on": {
            "cachey-arduis-init": {
                "condition": "service_completed_successfully"
            }
        },
    }
    assert ov["services"]["cachey-arduis-init"]["volumes"] == [
        "node_cache:/cache"
    ]


def test_bind_only_and_buildonly_services_get_no_init():
    ov = compose.volume_init_overrides(MODEL, USERS, 1000, 1000)
    assert "backend" not in ov["services"]          # binds only — CONT-08 alone
    assert "buildonly" not in ov["services"]        # no image to run init with
    assert "buildonly-arduis-init" not in ov["services"]


def test_services_without_user_override_are_ignored():
    ov = compose.volume_init_overrides(MODEL, {"services": {}}, 1000, 1000)
    assert ov == {"services": {}, "volumes": {}}


def test_tolerates_garbage_model():
    assert compose.volume_init_overrides({}, USERS, 1, 1) == {
        "services": {}, "volumes": {}
    }
    assert compose.volume_init_overrides(
        {"services": None}, USERS, 1, 1
    ) == {"services": {}, "volumes": {}}
    assert compose.volume_init_overrides(
        {"services": {"frontend": {"image": "i", "volumes": ["junk", None]}}},
        USERS, 1, 1,
    ) == {"services": {}, "volumes": {}}
    assert compose.volume_init_overrides(
        {"services": {"frontend": {"image": "i",
                                   "volumes": [{"type": "volume"}]}}},
        USERS, 1, 1,
    ) == {"services": {}, "volumes": {}}  # volume without target — skipped


def test_override_bytes_carries_init_trio_end_to_end():
    # the window merges the init shape into the fixed-name/user shape before
    # the single override_bytes write — the yaml must round-trip all of it.
    names = {
        "services": {"frontend": {"container_name": "p-front",
                                  "user": "1000:1000"}},
        "networks": {},
        "volumes": {},
    }
    inits = compose.volume_init_overrides(MODEL, USERS, 1000, 1000)
    for svc, extra in inits["services"].items():
        names["services"].setdefault(svc, {}).update(extra)
    names["volumes"].update(inits["volumes"])

    doc = yaml.safe_load(compose.override_bytes({}, names).decode("utf-8"))
    front = doc["services"]["frontend"]
    assert front["container_name"] == "p-front"
    assert front["user"] == "1000:1000"
    assert front["volumes"] == [
        "arduis-init-frontend-0:/opt/frontend/app/node_modules"
    ]
    init = doc["services"]["frontend-arduis-init"]
    assert init["restart"] == "no"          # the STRING, not YAML-1.1 False
    assert init["entrypoint"][0] == "chown"
    assert doc["volumes"]["arduis-init-frontend-0"] == {}
