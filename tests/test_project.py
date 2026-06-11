"""Tests for GTK-free project/member-repo discovery (D-05/D-07).

Contract: ``detect_member_repos`` finds every direct subdir containing a ``.git``
entry (dir OR file — Pitfall 1), excludes the root's own ``.git``, never follows
symlinked subdirs, swallows OSError to ``[]``, and returns ``[]`` when there are
no member subdirs (the degenerate 1-repo project the caller special-cases).
"""
import os

from arduis import project
from arduis.project import detect_member_repos


def _mk_repo(parent, name, git_as_file=False):
    """Create ``parent/name`` and give it a ``.git`` dir (or FILE if git_as_file)."""
    d = os.path.join(parent, name)
    os.makedirs(d, exist_ok=True)
    git_path = os.path.join(d, ".git")
    if git_as_file:
        with open(git_path, "w", encoding="utf-8") as fh:
            fh.write("gitdir: /somewhere/.git/worktrees/x\n")
    else:
        os.makedirs(git_path, exist_ok=True)
    return d


def test_detects_dir_and_file_git_excludes_plain(tmp_path):
    # backend/.git is a DIR, frontend/.git is a FILE, docs/ has no .git.
    root = str(tmp_path)
    _mk_repo(root, "backend", git_as_file=False)
    _mk_repo(root, "frontend", git_as_file=True)
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)  # no .git
    assert detect_member_repos(root) == ["backend", "frontend"]  # sorted; docs excluded


def test_git_as_file_detected(tmp_path):
    # Pitfall 1: a .git FILE (linked worktree/submodule) is a member via
    # os.path.exists, not only isdir.
    root = str(tmp_path)
    _mk_repo(root, "svc", git_as_file=True)
    assert detect_member_repos(root) == ["svc"]


def test_root_own_git_not_a_member(tmp_path):
    # The root's OWN .git (meta-repo) is never a member: scandir is direct
    # children only, so the root .git is never in the subdir scan (D-05).
    root = str(tmp_path)
    os.makedirs(os.path.join(root, ".git"), exist_ok=True)  # the meta-repo .git
    _mk_repo(root, "backend", git_as_file=False)
    members = detect_member_repos(root)
    assert ".git" not in members
    assert members == ["backend"]


def test_no_members_returns_empty(tmp_path):
    # No member subdirs -> [] (caller treats as degenerate 1-repo project).
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)
    os.makedirs(os.path.join(root, "scripts"), exist_ok=True)
    assert detect_member_repos(root) == []


def test_unreadable_root_returns_empty():
    # A non-existent / unreadable root -> [] (OSError swallowed, no traceback).
    assert detect_member_repos("/no/such/path/arduis-xyz-123") == []


def test_symlinked_subdir_not_followed(tmp_path):
    # A symlinked subdir is NOT followed as a member
    # (is_dir(follow_symlinks=False)).
    root = str(tmp_path)
    real = _mk_repo(str(tmp_path.parent), "external-repo", git_as_file=False)
    link = os.path.join(root, "linked")
    os.symlink(real, link)
    assert detect_member_repos(root) == []


def test_project_module_is_gtk_free():
    with open(project.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
