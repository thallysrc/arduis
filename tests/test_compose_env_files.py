"""Root-only env files must reach the workspace before compose runs (CONT-06).

Root cause (reproduced live 2026-07-03, workspace ``testin``): fresh worktrees do
not carry gitignored files, so when the root compose points ``env_file:`` inside
a member repo (``./backend/minhalivon/.env``) the file exists in the ROOT
checkout but not in the new worktree — ``docker compose config`` exits 1 and the
whole isolation chain aborts (auto-enable persisted ``enabled=false`` with only a
toast). Fix: parse the base compose for ``env_file`` entries and COPY the missing
ones from the root layout into the workspace before dispatching ``config``.

Copy — never symlink — so per-workspace edits never leak back to the root.
"""
import os

import arduis.window as W
from arduis import compose
from arduis.session import Workspace, RepoCheckout, SessionState


# --- env_file_paths: tolerant extraction from the base compose text ----------

def test_env_file_paths_string_form():
    text = "services:\n  web:\n    env_file: ./backend/app/.env\n"
    assert compose.env_file_paths(text) == ["./backend/app/.env"]


def test_env_file_paths_list_and_dict_forms():
    text = (
        "services:\n"
        "  web:\n"
        "    env_file:\n"
        "      - ./backend/app/.env\n"
        "      - path: ./IAM/.env\n"
        "        required: false\n"
    )
    assert compose.env_file_paths(text) == ["./backend/app/.env", "./IAM/.env"]


def test_env_file_paths_dedupes_across_services():
    text = (
        "services:\n"
        "  a:\n    env_file: ./shared/.env\n"
        "  b:\n    env_file: ./shared/.env\n"
    )
    assert compose.env_file_paths(text) == ["./shared/.env"]


def test_env_file_paths_skips_absolute_and_junk():
    text = (
        "services:\n"
        "  a:\n    env_file: /etc/secret.env\n"
        "  b:\n    env_file: 42\n"
        "  c: not-a-mapping\n"
    )
    assert compose.env_file_paths(text) == []


def test_env_file_paths_tolerates_garbage_yaml():
    assert compose.env_file_paths(":: not yaml [") == []
    assert compose.env_file_paths("just a string") == []
    assert compose.env_file_paths("services: []") == []


# --- env_copy_plan: which files actually move ---------------------------------

def _layout(tmp_path):
    root = tmp_path / "root"
    ws = tmp_path / "ws"
    (root / "backend" / "app").mkdir(parents=True)
    (ws / "backend" / "app").mkdir(parents=True)  # worktree dir exists, .env doesn't
    (root / "backend" / "app" / ".env").write_text("SECRET=1\n")
    return str(root), str(ws)


def test_plan_copies_missing_env_from_root(tmp_path):
    root, ws = _layout(tmp_path)
    plan = compose.env_copy_plan(root, ws, ["./backend/app/.env"])
    assert plan == [
        (os.path.join(root, "backend/app/.env"), os.path.join(ws, "backend/app/.env"))
    ]


def test_plan_skips_when_dst_already_exists(tmp_path):
    root, ws = _layout(tmp_path)
    (tmp_path / "ws" / "backend" / "app" / ".env").write_text("MINE=1\n")
    assert compose.env_copy_plan(root, ws, ["./backend/app/.env"]) == []


def test_plan_skips_when_src_missing(tmp_path):
    root, ws = _layout(tmp_path)
    assert compose.env_copy_plan(root, ws, ["./nope/.env"]) == []


def test_plan_rejects_traversal(tmp_path):
    root, ws = _layout(tmp_path)
    (tmp_path / "outside.env").write_text("X=1\n")
    assert compose.env_copy_plan(root, ws, ["../outside.env"]) == []
    assert compose.env_copy_plan(root, ws, ["/etc/passwd"]) == []


def test_plan_never_writes_through_symlinked_repo_dir(tmp_path):
    # A NON-chosen member repo is a symlink into the root (D-09): the dst path
    # resolves into the shared root — copying there would mutate the root.
    root, ws = _layout(tmp_path)
    (tmp_path / "root" / "IAM").mkdir()
    os.symlink(
        os.path.relpath(os.path.join(root, "IAM"), ws), os.path.join(ws, "IAM")
    )
    assert compose.env_copy_plan(root, ws, ["./IAM/.env"]) == []


def test_plan_dst_parent_may_not_exist_yet(tmp_path):
    # env_file inside a fully-gitignored subdir: worktree lacks the dir itself.
    root, ws = _layout(tmp_path)
    (tmp_path / "root" / "backend" / "conf").mkdir()
    (tmp_path / "root" / "backend" / "conf" / ".env").write_text("A=1\n")
    plan = compose.env_copy_plan(root, ws, ["./backend/conf/.env"])
    assert plan == [
        (os.path.join(root, "backend/conf/.env"), os.path.join(ws, "backend/conf/.env"))
    ]


# --- window wiring: _enable_isolation copies BEFORE dispatching `config` ------

def test_enable_isolation_materializes_env_files_first(monkeypatch, tmp_path):
    root = tmp_path / "root"
    ws = tmp_path / "ws"
    (root / "backend" / "app").mkdir(parents=True)
    (ws / "backend" / "app").mkdir(parents=True)
    (root / "backend" / "app" / ".env").write_text("SECRET=1\n")
    (root / "docker-compose.yml").write_text(
        "services:\n  web:\n    env_file: ./backend/app/.env\n"
    )
    # workspace mirrors the root: base compose is a relative symlink (D-09)
    os.symlink(
        os.path.relpath(str(root / "docker-compose.yml"), str(ws)),
        str(ws / "docker-compose.yml"),
    )

    win = W.ArduisWindow.__new__(W.ArduisWindow)
    win._compose_busy = set()
    win._compose_pending = {}
    win._config_path = str(tmp_path / "arduis.toml")
    win._runner = None
    monkeypatch.setattr(win, "_isolation_available", lambda: True)
    monkeypatch.setattr(win, "_rebuild_sidebar", lambda: None)

    dispatched = []
    env_at_dispatch = []

    def _fake_run(argv, on_done, runner=None):
        dispatched.append(argv)
        env_at_dispatch.append((ws / "backend" / "app" / ".env").exists())

    monkeypatch.setattr(W.docker_service, "run_compose_async", _fake_run)

    workspace = Workspace(
        workspace_id="feat", branch="feat", workspace_dir=str(ws),
        repos=[RepoCheckout(repo_name="backend", worktree_dir=str(ws / "backend"), branch="feat")],
        state=SessionState.ACTIVE,
    )
    win._enable_isolation(workspace)

    assert dispatched and dispatched[0][:2] == ["docker", "compose"]
    # the gitignored env file was copied from the root BEFORE config ran
    assert env_at_dispatch == [True]
    assert (ws / "backend" / "app" / ".env").read_text() == "SECRET=1\n"
    # a real copy, not a symlink — per-workspace edits must not leak to the root
    assert not os.path.islink(ws / "backend" / "app" / ".env")
