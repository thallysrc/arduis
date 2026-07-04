"""Tests for GTK-free project/member-repo discovery (D-05/D-07; D-04 03.3).

Contract: ``detect_member_repos`` finds every direct subdir whose ``.git`` is a
**directory** (a true repo — D-04 / 03.3), EXCLUDING ``.git``-FILE subdirs (linked
worktrees / submodules), excludes the root's own ``.git``, never follows symlinked
subdirs, swallows OSError to ``[]``, and returns ``[]`` when there are no member
subdirs (the degenerate 1-repo project the caller special-cases).

D-04 NOTE (03.3): this REVERSES the 03.2 "Pitfall 1" decision that counted
``.git``-FILE subdirs as members. The PO's real ``Livon-Saude`` root has ~20
``backend-*``/``frontend-*`` linked worktrees (``.git`` is a FILE) that flooded the
topbar chip bar; a member repo is now a subdir whose ``.git`` is a DIRECTORY.
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


def test_detects_dir_git_excludes_file_git_and_plain(tmp_path):
    # backend/.git is a DIR (member), frontend/.git is a FILE (EXCLUDED — linked
    # worktree), docs/ has no .git (excluded).
    # D-04 (03.3): .git-FILE subdirs are linked worktrees, not members — the
    # change from 03.2 (which INCLUDED frontend) is intentional.
    root = str(tmp_path)
    _mk_repo(root, "backend", git_as_file=False)
    _mk_repo(root, "frontend", git_as_file=True)
    os.makedirs(os.path.join(root, "docs"), exist_ok=True)  # no .git
    assert detect_member_repos(root) == ["backend"]  # frontend(.git FILE) + docs excluded


def test_git_as_file_is_not_a_member(tmp_path):
    # D-04 (03.3): a sole subdir whose .git is a FILE is a linked worktree, NOT a
    # member -> []. REPLACES the 03.2 test_git_as_file_detected (which asserted it
    # WAS a member via os.path.exists); the reversal is intentional per D-04.
    root = str(tmp_path)
    _mk_repo(root, "svc", git_as_file=True)
    assert detect_member_repos(root) == []


def test_livon_saude_shape_excludes_worktrees(tmp_path):
    # D-04 acceptance: the PO's real Livon-Saude root — 2 true repos (.git DIR)
    # plus 20 backend-*/frontend-* linked worktrees (.git FILE) — returns exactly
    # the 2 true repos (sorted), NOT 22. This is what makes the chip bar usable.
    root = str(tmp_path)
    _mk_repo(root, "backend", git_as_file=False)
    _mk_repo(root, "frontend", git_as_file=False)
    for i in range(1, 11):
        _mk_repo(root, f"backend-feat-{i}", git_as_file=True)
        _mk_repo(root, f"frontend-feat-{i}", git_as_file=True)
    assert detect_member_repos(root) == ["backend", "frontend"]


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


def test_hidden_subdirs_are_not_members(tmp_path):
    # Dotdirs with a .git DIR (e.g. ~/.oh-my-zsh, ~/.nvm, ~/.zplug) are tooling
    # clones, not project members. Without this exclusion $HOME qualifies as a
    # "project" when arduis is launched from the desktop icon (cwd=$HOME) and a
    # phantom project named after the user is auto-registered every start.
    root = str(tmp_path)
    _mk_repo(root, ".oh-my-zsh", git_as_file=False)
    _mk_repo(root, ".nvm", git_as_file=False)
    _mk_repo(root, "backend", git_as_file=False)
    assert detect_member_repos(root) == ["backend"]


def test_only_hidden_subdirs_means_no_members(tmp_path):
    # A dir whose ONLY git subdirs are hidden (the typical $HOME) -> [] so the
    # cwd does not resolve as a project.
    root = str(tmp_path)
    _mk_repo(root, ".zplug", git_as_file=False)
    assert detect_member_repos(root) == []


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
