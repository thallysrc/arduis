"""Tests for GTK-free workspace-folder layout builders (D-08/D-09).

Contract: ``workspace_dir_for`` groups worktrees under
``<parent>/<root_base>-tasks/<sanitized-branch>`` and sanitizes a malicious
branch (T-03.2-01); ``repo_worktree_dir`` nests a repo under the workspace dir keeping
its dir name (D-08); ``symlink_plan`` mirrors every top-level root entry EXCEPT
the chosen repos and the meta ``.git``, as raw ``(src, dst)`` pairs inside the
workspace dir (D-05/D-09, T-03.2-02).
"""
import os

from arduis import workspace_layout
from arduis.workspace_layout import repo_worktree_dir, symlink_plan, workspace_dir_for
from arduis.worktree import sanitize_branch_for_dir


def test_workspace_dir_for_basic():
    # <parent>/<base>-tasks/<sanitized-branch> (D-08).
    assert workspace_dir_for("/home/u/livon", "feat/x") == "/home/u/livon-tasks/feat-x"


def test_workspace_dir_for_trailing_slash():
    # trailing slash on root must not produce an empty base.
    assert workspace_dir_for("/home/u/livon/", "feat/x") == "/home/u/livon-tasks/feat-x"


def test_workspace_dir_for_sanitizes_traversal():
    # T-03.2-01: a "../../etc" branch yields a flat sanitized leaf, never an
    # escape; reuse sanitize_branch_for_dir (tested T-02-02 guard).
    d = workspace_dir_for("/home/u/livon", "../../etc")
    leaf = os.path.basename(d)
    assert ".." not in leaf
    assert os.sep not in leaf
    assert leaf not in ("", ".", "..")
    # the workspace-dir parent is always the <base>-tasks grouping folder.
    assert os.path.dirname(d) == "/home/u/livon-tasks"
    assert leaf == sanitize_branch_for_dir("../../etc")


def test_repo_worktree_dir():
    assert repo_worktree_dir("/home/u/livon-tasks/feat-x", "backend") == (
        "/home/u/livon-tasks/feat-x/backend"
    )


def test_symlink_plan_excludes_chosen_and_git(tmp_path):
    # root entries: backend, frontend, keycloak, CLAUDE.md, docker-compose.yml,
    # scripts, .git ; chosen = {backend, frontend}.
    root = str(tmp_path)
    for name in ("backend", "frontend", "keycloak", "scripts", ".git"):
        os.makedirs(os.path.join(root, name), exist_ok=True)
    for name in ("CLAUDE.md", "docker-compose.yml"):
        with open(os.path.join(root, name), "w", encoding="utf-8") as fh:
            fh.write("x\n")

    workspace_dir = "/home/u/livon-tasks/feat-x"
    plan = symlink_plan(root, workspace_dir, {"backend", "frontend"})

    mirrored = {os.path.basename(dst) for _src, dst in plan}
    # only the non-chosen, non-.git entries are mirrored.
    assert mirrored == {"keycloak", "CLAUDE.md", "docker-compose.yml", "scripts"}
    # chosen repos (real worktrees) and the meta .git are EXCLUDED.
    assert "backend" not in mirrored
    assert "frontend" not in mirrored
    assert ".git" not in mirrored


def test_symlink_plan_pairs_are_src_in_root_dst_in_workspace(tmp_path):
    # each pair is (absolute_src_in_root, dst_inside_workspace_dir); the function is
    # pure (returns raw pairs) — the relpath/os.symlink is the caller's job.
    root = str(tmp_path)
    os.makedirs(os.path.join(root, "scripts"), exist_ok=True)
    workspace_dir = "/home/u/livon-tasks/feat-x"
    plan = symlink_plan(root, workspace_dir, set())
    assert len(plan) == 1
    src, dst = plan[0]
    assert src == os.path.join(root, "scripts")  # absolute src inside root
    assert dst == os.path.join(workspace_dir, "scripts")  # dst inside workspace_dir
    # every dst is inside workspace_dir (T-03.2-02 — never escapes the workspace folder).
    for _s, d in plan:
        assert d.startswith(workspace_dir + os.sep)


def test_workspace_layout_module_is_gtk_free():
    with open(workspace_layout.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
