"""Contract tests for projects.json persistence (D-05/D-06; T-03.4-01/02).

Pins the GTK-free app-state layer (imports NO ``gi``; stdlib ``json``): the remembered
set of PROJECT roots + ``last_active_project`` round-trips through an ATOMIC temp+rename
write (mirrors ``appconfig.write_theme``); a remembered root that no longer exists on
disk is SKIPPED on load (D-06), and a now-invalid ``last_active`` is dropped to None;
garbage / not-a-dict / missing-file reads degrade to ``([], None)`` (never an exception —
one bad entry never aborts the whole load); and a mid-write failure leaves the original
file intact with no stray non-temp target (T-03.4-01).
"""
import glob
import json
import os

from arduis import projects_store
from arduis.projects_store import load_projects, save_projects


def _mkdirs(tmp_path, *names):
    """Create real dirs under tmp_path; return their absolute paths."""
    out = []
    for n in names:
        d = tmp_path / n
        d.mkdir()
        out.append(str(d))
    return out


# --- round-trip ---------------------------------------------------------------
def test_save_then_load_roundtrips(tmp_path):
    a, b = _mkdirs(tmp_path, "a", "b")
    path = str(tmp_path / "projects.json")
    save_projects(path, [a, b], a)
    roots, last = load_projects(path)
    assert roots == [a, b]
    assert last == a


def test_save_writes_versioned_schema(tmp_path):
    (a,) = _mkdirs(tmp_path, "a")
    path = str(tmp_path / "projects.json")
    save_projects(path, [a], a)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    assert data["version"] == 1
    assert data["projects"] == [{"root": a}]
    assert data["last_active_project"] == a


# --- missing-root skipping (D-06) ---------------------------------------------
def test_load_skips_missing_root(tmp_path):
    (a,) = _mkdirs(tmp_path, "a")
    missing = str(tmp_path / "gone")  # never created
    path = str(tmp_path / "projects.json")
    # write a file that references both, by hand (save_projects only persists what
    # it is given; D-06 skipping is a LOAD-side guard).
    payload = {
        "version": 1,
        "projects": [{"root": a}, {"root": missing}],
        "last_active_project": a,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    roots, last = load_projects(path)
    assert roots == [a]  # missing dropped
    assert last == a


def test_load_last_active_dropped_if_invalid(tmp_path):
    (a,) = _mkdirs(tmp_path, "a")
    missing = str(tmp_path / "gone")
    path = str(tmp_path / "projects.json")
    payload = {
        "version": 1,
        "projects": [{"root": a}],
        "last_active_project": missing,  # points at a now-missing root
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    roots, last = load_projects(path)
    assert roots == [a]
    assert last is None  # invalid last_active dropped


# --- tolerant reads -----------------------------------------------------------
def test_load_bad_json_returns_empty(tmp_path):
    path = str(tmp_path / "projects.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("{not valid json,,,")
    assert load_projects(path) == ([], None)


def test_load_not_a_dict_returns_empty(tmp_path):
    path = str(tmp_path / "projects.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(["just", "a", "list"], fh)
    assert load_projects(path) == ([], None)


def test_load_missing_file_returns_empty(tmp_path):
    path = str(tmp_path / "nope.json")
    assert load_projects(path) == ([], None)


# --- atomicity (T-03.4-01) ----------------------------------------------------
def test_atomic_write_no_partial_on_failure(tmp_path, monkeypatch):
    (a, b) = _mkdirs(tmp_path, "a", "b")
    path = str(tmp_path / "projects.json")
    # seed a valid original so we can prove it survives a failed rewrite.
    save_projects(path, [a], a)
    original = open(path, encoding="utf-8").read()

    def boom(*args, **kwargs):
        raise OSError("disk full mid-write")

    monkeypatch.setattr(json, "dump", boom)
    save_projects(path, [a, b], b)  # must NOT raise

    # original untouched (atomic temp+rename never replaced it)
    assert open(path, encoding="utf-8").read() == original
    # no stray temp file left behind as the target or in the dir
    leftovers = glob.glob(str(tmp_path / ".arduis-projects-*"))
    assert leftovers == []


def test_save_leaves_no_tmp_file_on_success(tmp_path):
    (a,) = _mkdirs(tmp_path, "a")
    path = str(tmp_path / "projects.json")
    save_projects(path, [a], a)
    leftovers = glob.glob(str(tmp_path / ".arduis-projects-*"))
    assert leftovers == []


def test_save_uncreatable_parent_does_not_raise(tmp_path):
    # a path whose parent is a FILE -> OSError swallowed, no raise (best-effort).
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    path = str(blocker / "sub" / "projects.json")
    save_projects(path, [str(tmp_path)], None)  # must not raise


# --- GTK-free guard -----------------------------------------------------------
def test_projects_store_is_gtk_free():
    with open(projects_store.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
    assert "from gi" not in text
