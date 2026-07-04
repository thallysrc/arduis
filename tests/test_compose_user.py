"""Bind-mounted services must run as the HOST user (CONT-08, 2026-07-03).

Root cause (reproduced live, workspace ``feat-teste``): the stack's app
containers run as root and write build artifacts (``__pycache__``, ``.venv``,
``node_modules``, ``.nuxt``) through the bind mounts into the worktrees — 3042
root-owned files. The conclude clean-gate passes (all gitignored) but ``git
worktree remove`` then fails with EACCES, blocking conclude on EVERY workspace
whose stack ever ran.

Fix: ``user_overrides`` walks the AUTHORITATIVE ``docker compose config
--format json`` model (volumes already normalized to long form) and emits a
``user: "<uid>:<gid>"`` override for every service that bind-mounts — the ones
that write into the worktree. Services without bind mounts (e.g. postgres on a
named volume, whose init breaks under an arbitrary uid) and services whose base
already pins ``user:`` are left alone.
"""
import yaml

from arduis import compose


MODEL = {
    "services": {
        "backend": {
            "image": "x",
            "volumes": [
                {"type": "bind", "source": "/root/backend", "target": "/app"},
            ],
        },
        "frontend": {
            "image": "y",
            "volumes": [
                {"type": "bind", "source": "/root/frontend", "target": "/src"},
                {"type": "volume", "source": "node_cache", "target": "/cache"},
            ],
        },
        "db": {
            "image": "postgres",
            "volumes": [
                {"type": "volume", "source": "pgdata", "target": "/var/lib/postgresql/data"},
            ],
        },
        "keycloak": {"image": "z"},
        "pinned": {
            "image": "w",
            "user": "root",
            "volumes": [
                {"type": "bind", "source": "/root/pinned", "target": "/work"},
            ],
        },
    }
}


def test_user_overrides_targets_bind_mounted_services_only():
    ov = compose.user_overrides(MODEL, 1000, 1000)
    assert ov == {
        "services": {
            "backend": {"user": "1000:1000"},
            "frontend": {"user": "1000:1000"},
        }
    }


def test_user_overrides_respects_explicit_base_user():
    ov = compose.user_overrides(MODEL, 1000, 1000)
    assert "pinned" not in ov["services"]  # base said user: root — its call


def test_user_overrides_skips_named_volume_and_volumeless_services():
    ov = compose.user_overrides(MODEL, 1000, 1000)
    assert "db" not in ov["services"]        # arbitrary uid breaks pg initdb
    assert "keycloak" not in ov["services"]  # writes nothing into the worktree


def test_user_overrides_tolerates_garbage_model():
    assert compose.user_overrides({}, 1, 1) == {"services": {}}
    assert compose.user_overrides({"services": None}, 1, 1) == {"services": {}}
    assert compose.user_overrides(
        {"services": {"a": None, "b": {"volumes": ["notadict", None]}}}, 1, 1
    ) == {"services": {}}


def test_override_bytes_merges_user_with_fixed_names():
    # the window merges user entries into the fixed-name shape before
    # override_bytes — the same service must carry BOTH keys in the yaml.
    names = {
        "services": {"backend": {"container_name": "p-livon-backend"}},
        "networks": {},
        "volumes": {},
    }
    users = compose.user_overrides(MODEL, 1000, 1000)
    for svc, extra in users["services"].items():
        names["services"].setdefault(svc, {}).update(extra)

    doc = yaml.safe_load(compose.override_bytes({}, names).decode("utf-8"))
    assert doc["services"]["backend"] == {
        "container_name": "p-livon-backend",
        "user": "1000:1000",
    }
    assert doc["services"]["frontend"] == {"user": "1000:1000"}
