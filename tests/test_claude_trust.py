"""claude_trust: propagate the project root's Claude Code trust to workspace paths.

The contract under test: ``pretrust_paths`` grants ``hasTrustDialogAccepted`` to new
workspace/worktree paths ONLY when the source root already holds an accepted trust
dialog (propagation, never origination); it round-trips the rest of the document,
is idempotent, and treats every failure as a silent no-op (fail-closed: claude
re-prompts, the file is never corrupted).
"""
import json
import os

from arduis import claude_trust


def _write(path: str, doc) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2)


def _read(path: str):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _doc(root_trusted: bool = True) -> dict:
    return {
        "numStartups": 7,
        "theme": "dark-ansi",
        "projects": {
            "/proj/root": {
                "hasTrustDialogAccepted": root_trusted,
                "allowedTools": ["Bash"],
            },
        },
    }


def test_propagates_trust_to_new_paths(tmp_path):
    cfg = str(tmp_path / "claude.json")
    _write(cfg, _doc())
    claude_trust.pretrust_paths(cfg, "/proj/root", ["/tasks/ws", "/tasks/ws/repo"])
    projects = _read(cfg)["projects"]
    for p in ("/tasks/ws", "/tasks/ws/repo"):
        assert projects[p]["hasTrustDialogAccepted"] is True
        assert projects[p]["hasCompletedProjectOnboarding"] is True


def test_untrusted_root_propagates_nothing(tmp_path):
    cfg = str(tmp_path / "claude.json")
    _write(cfg, _doc(root_trusted=False))
    claude_trust.pretrust_paths(cfg, "/proj/root", ["/tasks/ws"])
    assert "/tasks/ws" not in _read(cfg)["projects"]


def test_unknown_root_propagates_nothing(tmp_path):
    cfg = str(tmp_path / "claude.json")
    _write(cfg, _doc())
    claude_trust.pretrust_paths(cfg, "/other/root", ["/tasks/ws"])
    assert "/tasks/ws" not in _read(cfg)["projects"]


def test_round_trips_unrelated_document_state(tmp_path):
    cfg = str(tmp_path / "claude.json")
    _write(cfg, _doc())
    claude_trust.pretrust_paths(cfg, "/proj/root", ["/tasks/ws"])
    doc = _read(cfg)
    assert doc["numStartups"] == 7
    assert doc["theme"] == "dark-ansi"
    assert doc["projects"]["/proj/root"]["allowedTools"] == ["Bash"]


def test_existing_entry_upgraded_without_dropping_keys(tmp_path):
    cfg = str(tmp_path / "claude.json")
    doc = _doc()
    doc["projects"]["/tasks/ws"] = {
        "hasTrustDialogAccepted": False,
        "hasCompletedProjectOnboarding": False,
        "lastCost": 1.5,
    }
    _write(cfg, doc)
    claude_trust.pretrust_paths(cfg, "/proj/root", ["/tasks/ws"])
    entry = _read(cfg)["projects"]["/tasks/ws"]
    assert entry["hasTrustDialogAccepted"] is True
    # setdefault: an entry the user has already onboarded keeps ITS value...
    assert entry["hasCompletedProjectOnboarding"] is False
    # ...and unrelated keys survive.
    assert entry["lastCost"] == 1.5


def test_idempotent_no_rewrite_when_already_trusted(tmp_path):
    cfg = str(tmp_path / "claude.json")
    doc = _doc()
    doc["projects"]["/tasks/ws"] = {"hasTrustDialogAccepted": True}
    _write(cfg, doc)
    before = os.stat(cfg).st_mtime_ns
    with open(cfg, encoding="utf-8") as fh:
        raw = fh.read()
    claude_trust.pretrust_paths(cfg, "/proj/root", ["/tasks/ws"])
    with open(cfg, encoding="utf-8") as fh:
        assert fh.read() == raw
    assert os.stat(cfg).st_mtime_ns == before


def test_missing_file_is_silent_noop(tmp_path):
    cfg = str(tmp_path / "absent.json")
    claude_trust.pretrust_paths(cfg, "/proj/root", ["/tasks/ws"])
    assert not os.path.exists(cfg)


def test_garbage_file_is_silent_noop(tmp_path):
    cfg = str(tmp_path / "claude.json")
    with open(cfg, "w", encoding="utf-8") as fh:
        fh.write("{not json")
    claude_trust.pretrust_paths(cfg, "/proj/root", ["/tasks/ws"])
    with open(cfg, encoding="utf-8") as fh:
        assert fh.read() == "{not json"  # never rewritten, never corrupted


def test_non_dict_projects_is_silent_noop(tmp_path):
    cfg = str(tmp_path / "claude.json")
    _write(cfg, {"projects": ["weird"]})
    claude_trust.pretrust_paths(cfg, "/proj/root", ["/tasks/ws"])
    assert _read(cfg) == {"projects": ["weird"]}
