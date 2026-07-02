# Task → Workspace Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Rename the app's "Task" concept (one branch materialized as N git-worktrees across N member repos) to "Workspace" everywhere it appears in code, tests, UI strings, and living docs — freeing "task"/"Task" for an unrelated future Kanban feature.

**Architecture:** Pure rename, zero behavior change. `Task` (session.py) → `Workspace`. The low-level per-repo git-worktree module (`worktree.py`) is untouched — it never used the word "task" for its own concept and stays the implementation detail underneath a Workspace. The on-disk directory suffix (`<repo>-tasks/`) is **deliberately left unchanged** in this plan — it currently holds live git worktrees for real projects (arduis itself, Livon-Saude, sabores, grimorio) and migrating it safely is separate follow-up work (see "Deferred: on-disk suffix migration" below). This plan renames identifiers/strings only; a handful of docstrings/comments that describe the *actual* current on-disk path must keep saying `-tasks` until that follow-up lands.

**Tech Stack:** Python, GTK4/libadwaita (no gi imports in the touched model files except window.py), pytest.

## Global Constraints

- No behavior change. Every test that passes today must pass after, with only names changed inside assertions (never behavior).
- Do NOT touch: `worktree.py` (per-repo git worktree helpers — different, still-valid concept), `session.py`'s `RepoCheckout.worktree_dir` field (already correctly named), GSD's own "Quick Tasks Completed" bookkeeping in `.planning/STATE.md` (unrelated harness concept), `.planning/milestones/*` archives (historical record, not rewritten).
- Do NOT change the literal on-disk directory suffix `-tasks` anywhere it represents the actual folder name arduis reads/writes today (`workspace_dir_for`'s return value, and the 4 docstring/comment mentions of `<root>-tasks/` listed in Task 8). That is Plan B (separate, not part of this plan).
- UI strings are pt-BR. Use masculine grammatical agreement for "workspace" (`o workspace`, `um workspace`, `hibernado`/`suspenso`, not `-a`), consistent with how Portuguese tech usage treats English loanwords like `workspace`/`app`.
- Living docs in scope: `CLAUDE.md` (current architecture section), `.planning/PROJECT.md` (executive summary line + decisions table row only — NOT the dated historical narrative log). `.planning/STATE.md` needs no change (its only "task" mentions are inside dated historical log bullets).

---

### Task 1: Rename `session.py`'s `Task` model to `Workspace`

**Files:**
- Modify: `src/arduis/session.py`
- Test: `tests/test_session.py`

**Identifier renames (exact, apply throughout the file):**

| Old | New |
|---|---|
| `class Task` | `class Workspace` |
| field `task_id` | `workspace_id` |
| field `task_dir` | `workspace_dir` |
| `default_task_terminals(task_id)` | `default_workspace_terminals(workspace_id)` |
| `default_repo_terminals(task_id, repo_name)` param | `default_repo_terminals(workspace_id, repo_name)` |
| `SessionStore._tasks` | `SessionStore._workspaces` |
| `SessionStore.add(t: Task)` | `SessionStore.add(w: Workspace)` |
| `SessionStore.get(task_id)` | `SessionStore.get(workspace_id)` |
| `SessionStore.remove(task_id)` | `SessionStore.remove(workspace_id)` |
| `hibernate_fields(task: Task)` | `hibernate_fields(workspace: Workspace)` |
| module docstring "unit of work is a TASK" | "unit of work is a WORKSPACE" |
| all prose mentions of "task"/"a task's"/"the task" in docstrings | "workspace"/"a workspace's"/"the workspace" |

**Exception — do NOT change:** the comment on the `workspace_dir` field, `# ../<root_base>-tasks/<sanitized-branch>/` — the actual suffix is still `-tasks` today (Plan B territory). Keep that comment's path text as `-tasks`.

- [x] **Step 1:** Apply all renames in the table above across `session.py`. Use exact whole-identifier replacement (not a blind regex) so `RepoCheckout.worktree_dir` and `TerminalRecord` fields are untouched.
- [x] **Step 2:** Re-read the file; confirm the one exception comment still reads `-tasks` and every other "task" mention is gone.
- [x] **Step 3:** Update `tests/test_session.py`: rename every `Task(...)`, `.task_id`, `.task_dir`, `default_task_terminals` reference to the `Workspace`/`workspace_id`/`workspace_dir`/`default_workspace_terminals` equivalents. Test function names containing "task" (e.g. `test_task_has_terminals_list`, `test_task_auto_suspended_serializes`, `test_task_auto_suspended_trailing_field_defaults_false`, `test_multi_repo_task_serializable`, `test_multi_repo_task_counts_as_one`, `test_default_task_terminals`, `test_store_remove_drops_task`) → replace `task` with `workspace` in the name (e.g. `test_workspace_has_terminals_list`).
- [x] **Step 4:** Run `pytest tests/test_session.py -v` — expect all PASS.
- [x] **Step 5:** Commit.

```bash
git add src/arduis/session.py tests/test_session.py
git commit -m "refactor(session): rename Task model to Workspace"
```

---

### Task 2: Rename `task_layout.py` → `workspace_layout.py` (functions renamed, suffix untouched)

**Files:**
- Rename: `src/arduis/task_layout.py` → `src/arduis/workspace_layout.py`
- Rename: `tests/test_task_layout.py` → `tests/test_workspace_layout.py`
- Rename: `tests/test_task_create.py` → `tests/test_workspace_create.py`
- Modify (import sites): `src/arduis/window.py`

**Identifier renames:**

| Old | New |
|---|---|
| `task_dir_for(root, branch)` | `workspace_dir_for(root, branch)` |
| `repo_worktree_dir(task_dir, repo_name)` | `repo_worktree_dir(workspace_dir, repo_name)` (param rename only) |
| `symlink_plan(root, task_dir, chosen_repos)` | `symlink_plan(root, workspace_dir, chosen_repos)` (param rename only) |
| module docstring "A *task* is one branch..." | "A *workspace* is one branch..." |
| `resolve_repo_add` — no rename (name has no "task") | unchanged |

**Exception — do NOT change:** inside `workspace_dir_for`, the literal `f"{base}-tasks"` stays exactly as-is (this is the real, current on-disk suffix). Module docstring's `<parent-of-root>/<root_base>-tasks/<sanitized-branch>/` path mentions also stay `-tasks`.

- [x] **Step 1:** `git mv src/arduis/task_layout.py src/arduis/workspace_layout.py`
- [x] **Step 2:** Apply the identifier renames above inside the moved file. Leave the `-tasks` suffix literal and the two path-describing docstring/comment lines unchanged.
- [x] **Step 3:** `git mv tests/test_task_layout.py tests/test_workspace_layout.py`. Update its `from arduis.task_layout import ...` → `from arduis.workspace_layout import ...`. Rename test functions: `test_task_dir_for_basic` → `test_workspace_dir_for_basic`, `test_task_dir_for_sanitizes_traversal` → `test_workspace_dir_for_sanitizes_traversal`, `test_task_dir_for_trailing_slash` → `test_workspace_dir_for_trailing_slash`, `test_symlink_plan_pairs_are_src_in_root_dst_in_task` → `test_symlink_plan_pairs_are_src_in_root_dst_in_workspace`, `test_task_layout_module_is_gtk_free` → `test_workspace_layout_module_is_gtk_free`. **Assertions that check the literal returned path must keep asserting `-tasks` in the expected string** (e.g. `assert workspace_dir_for("/x/foo", "branch") == "/x/foo-tasks/branch"` — only the function name changed, not the expected value).
- [x] **Step 4:** `git mv tests/test_task_create.py tests/test_workspace_create.py`. Update `from arduis.task_layout import resolve_repo_add` → `from arduis.workspace_layout import resolve_repo_add`. The fixture path strings in this file (e.g. `"/r-tasks/feat/backend"`) are arbitrary example worktree dirs unrelated to any assertion about the real suffix — rename them to `/r-workspaces/feat/backend` style for consistency (safe, since nothing asserts they equal `workspace_dir_for`'s output). Rename test function `test_degenerate_single_repo_task_identical_shape` → `test_degenerate_single_repo_workspace_identical_shape`.
- [x] **Step 5:** Update `src/arduis/window.py`'s import: `from arduis.task_layout import (...)` → `from arduis.workspace_layout import (...)`, renaming any imported names per the table above.
- [x] **Step 6:** Run `pytest tests/test_workspace_layout.py tests/test_workspace_create.py -v` — expect all PASS.
- [x] **Step 7:** Commit.

```bash
git add -A src/arduis/workspace_layout.py src/arduis/task_layout.py tests/test_workspace_layout.py tests/test_task_layout.py tests/test_workspace_create.py tests/test_task_create.py src/arduis/window.py
git commit -m "refactor(layout): rename task_layout module to workspace_layout"
```

---

### Task 3: Rename `Task` references + UI strings + CSS class in `window.py`

**Files:**
- Modify: `src/arduis/window.py`
- Test: `tests/test_window_projects.py`, `tests/test_window_conclude.py`, `tests/test_window_attention_multiproject.py`, `tests/test_prompt_scan.py`, `tests/test_attention_ring.py`, `tests/smoke/test_setup_feed_smoke.py`, `tests/smoke/test_project_switch_smoke.py`

**Function/method renames (exact, whole-identifier):**

| Old | New |
|---|---|
| `_active_task` | `_active_workspace` |
| `_agent_task` | `_agent_workspace` |
| `_all_task_terminals` | `_all_workspace_terminals` |
| `_all_tasks` | `_all_workspaces` |
| `_begin_new_task` | `_begin_new_workspace` |
| `_build_task_workspace` | `_build_workspace_terminals` (avoids the nonsensical "task_workspace" double-name once Task→Workspace) |
| `_clear_task_state_files` | `_clear_workspace_state_files` |
| `_conclude_clean_task_folder` | `_conclude_clean_workspace_folder` |
| `_conclude_task` | `_conclude_workspace` |
| `_create_task` | `_create_workspace` |
| `_dir_is_task` | `_dir_is_workspace` |
| `_finalize_task_creation` | `_finalize_workspace_creation` |
| `_hibernate_task` | `_hibernate_workspace` |
| `_make_task_leaf` | `_make_workspace_leaf` |
| `_present_new_task_dialog` | `_present_new_workspace_dialog` |
| `_project_for_task` | `_project_for_workspace` |
| `_project_with_tasks` | `_project_with_workspaces` |
| `_refresh_task_status` | `_refresh_workspace_status` |
| `_resume_task` | `_resume_workspace` |
| `_scan_tasks` | `_scan_workspaces` |
| `_spawn_task_terminals` | `_spawn_workspace_terminals` |
| `_task_root_cwd` | `_workspace_root_cwd` |
| bare `_task(...)` helper (if present standalone) | `_workspace(...)` |
| every bare local variable / parameter named `task` | `workspace` |
| every `Task` type annotation (`Task`, `Task \| None`, `list[Task]`, `dict[str, Task]`) | `Workspace` equivalents |
| `Task` import from `arduis.session` | `Workspace` |

**UI-visible strings (exact):**

| Line (approx) | Old | New |
|---|---|---|
| 1924 | `Gtk.Button(label="+ Nova task")` | `Gtk.Button(label="+ Novo workspace")` |
| 1926 | `set_tooltip_text("Nova task")` | `set_tooltip_text("Novo workspace")` |
| 1934 | `self._section_title("TASKS")` | `self._section_title("WORKSPACES")` |
| 2123 | `menu.append("Concluir task", "win.conclude")` | `menu.append("Concluir workspace", "win.conclude")` |
| 2531 | `f"{task.branch} está hibernada"` | `f"{workspace.branch} está hibernado"` (gender agreement) |
| 2533 | `Gtk.Button(label="Retomar task")` | `Gtk.Button(label="Retomar workspace")` |
| 2920 | `set_tooltip_text("Nova task" if enabled else _NO_REPO_HINT)` | `set_tooltip_text("Novo workspace" if enabled else _NO_REPO_HINT)` |
| 3234 | `heading=f"Remover {proj.name} e encerrar suas tasks?"` | `heading=f"Remover {proj.name} e encerrar seus workspaces?"` |
| 3236-3237 | `"Isto encerra os agentes e containers das tasks ativas deste " "projeto. As worktrees e pastas no disco são preservadas."` | `"Isto encerra os agentes e containers dos workspaces ativos deste " "projeto. As worktrees e pastas no disco são preservadas."` |
| 3575 | `heading="Nova task"` | `heading="Novo workspace"` |
| 3852 | `self._show_error("Não foi possível criar a task", ...)` | `self._show_error("Não foi possível criar o workspace", ...)` |
| 4296 | `heading=f"Concluir {task.branch}?"` | `heading=f"Concluir {workspace.branch}?"` (via var rename) |
| 4298 | `"Remove as worktrees da task. O código-fonte, o histórico e a "` | `"Remove as worktrees do workspace. O código-fonte, o histórico e a "` |
| 4403 | `"Conclua ou descarte essas mudanças antes de concluir a task. "` | `"Conclua ou descarte essas mudanças antes de concluir o workspace. "` |
| 5232 | `f"{task.branch} suspensa"` | `f"{workspace.branch} suspenso"` (gender agreement, via var rename) |

**CSS class (2 locations):**

| Line | Old | New |
|---|---|---|
| 298 | `.arduis-new-task-btn {` (definition) | `.arduis-new-workspace-btn {` |
| 1925 | `add_css_class("arduis-new-task-btn")` | `add_css_class("arduis-new-workspace-btn")` |

**Exception — do NOT change (literal on-disk suffix, Plan B territory):**
- Line ~3367 docstring: `` Rediscover past tasks from ``../<root>-tasks/`` as HIBERNATED `` → rename "past tasks" to "past workspaces" but keep ` ../<root>-tasks/` unchanged.
- Line ~3396 comment: `` branch so the convention (``<parent>/<base>-tasks``) lives in one place. `` → keep `-tasks` unchanged (no other word to rename on this line).
- Line ~3471 docstring: `` dir under ``<root>-tasks/`` is never listed as a task `` → keep `<root>-tasks/` unchanged; rename the trailing "a task" → "a workspace".

- [x] **Step 1:** Apply every function/method rename from the table above via exact whole-identifier replacement across `window.py`.
- [x] **Step 2:** Rename every bare local variable/parameter `task` → `workspace` (the pervasive case). Also rename the `Task` type import and all its usages (`Task | None`, `list[Task]`, etc.) to `Workspace`.
- [x] **Step 3:** Apply the UI string table verbatim.
- [x] **Step 4:** Apply the CSS class rename at both locations.
- [x] **Step 5:** Fix the 3 exception lines so they read exactly as specified (word renamed, `-tasks` path preserved).
- [x] **Step 6:** Re-grep the file: `grep -nE "task|Task|TASK" src/arduis/window.py` — every remaining hit must be one of the 3 known exception lines. If anything else remains, fix it.
- [x] **Step 7:** Update the test files listed above: rename every `Task(...)` construction, `.task_id`/`.task_dir` access, and any test referencing the renamed `window.py` methods (e.g. via `win._scan_tasks` mocking, if present) to the `Workspace`/`workspace_id`/renamed-method equivalents. Rename test function names containing "task" accordingly (e.g. `test_hibernated_task_never_rings` → `test_hibernated_workspace_never_rings`, `test_notify_fires_for_background_task` → `test_notify_fires_for_background_workspace`, `test_escalate_marks_task_record_waiting_and_lights_ui` → `test_escalate_marks_workspace_record_waiting_and_lights_ui`, `test_deescalate_task_flips_waiting_to_running_and_clears_ui` → `test_deescalate_workspace_flips_waiting_to_running_and_clears_ui`, `test_hibernate_clears_task_level_terminals` → `test_hibernate_clears_workspace_level_terminals`, `test_remove_no_live_tasks_is_silent` → `test_remove_no_live_workspaces_is_silent`, `test_remove_with_live_tasks_tears_down_then_drops` → `test_remove_with_live_workspaces_tears_down_then_drops`).
- [x] **Step 8:** Run `pytest tests/ -v -k "window or prompt_scan or attention_ring or setup_feed_smoke or project_switch_smoke"` — expect all PASS.
- [x] **Step 9:** Commit.

```bash
git add src/arduis/window.py tests/test_window_projects.py tests/test_window_conclude.py tests/test_window_attention_multiproject.py tests/test_prompt_scan.py tests/test_attention_ring.py tests/smoke/test_setup_feed_smoke.py tests/smoke/test_project_switch_smoke.py
git commit -m "refactor(window): rename Task to Workspace across UI, methods, and CSS"
```

---

### Task 4: Rename remaining source files (`project.py`, `attention.py`, `compose.py`, `containerstate.py`, `topbar.py`)

**Files:**
- Modify: `src/arduis/project.py`, `src/arduis/attention.py`, `src/arduis/compose.py`, `src/arduis/containerstate.py`, `src/arduis/topbar.py`
- Test: `tests/test_projects_registry.py`, `tests/test_attention.py`, `tests/test_compose.py`, `tests/test_compose_smoke.py`, `tests/test_containerstate.py`, `tests/test_caps.py`, `tests/test_review_cleanup_smoke.py`

**Identifier renames:**

| File | Old | New |
|---|---|---|
| `project.py` | field `last_active_task` | `last_active_workspace` |
| `project.py` | docstring "its OWN tasks" / "task_id" / "task stores" | "its OWN workspaces" / "workspace_id" / "workspace stores" |
| `attention.py` | `aggregate_task` | `aggregate_workspace` |
| `compose.py` | param `task_dir` (in `compose_argv`, `up_argv`, `down_argv`, `config_argv`) | `workspace_dir` |
| `compose.py` | fallback string `"arduis-task"` | `"arduis-workspace"` |
| `compose.py` | docstring "falls back to ``arduis-task``" | "falls back to ``arduis-workspace``" |
| `containerstate.py` | param `task_dir` (in `state_path`, `load_container_state`, `write_container_state`) | `workspace_dir` |
| `containerstate.py` | docstrings/comments "per-task container state", "a task opts into", "task file's", "task creation or the startup scan", "a task with no isolation" (×2) | "per-workspace container state", "a workspace opts into", "workspace file's", "workspace creation or the startup scan", "a workspace with no isolation" |
| `topbar.py` | docstring `"Nova task" dialog` | `"Nova workspace" dialog` |

Note: `containerstate.py`'s persisted file is `arduis.container.toml` living *inside* whatever directory is passed in — renaming the Python parameter name has no effect on the TOML file's own keys (verified: it stores `project_name`/`enabled`/`ports`, never `task_dir` as a key). Zero persistence risk.

- [x] **Step 1:** Apply the renames above to each of the 5 files.
- [x] **Step 2:** Update the corresponding test files: rename any `last_active_task`, `aggregate_task`, or `task_dir=` keyword-argument usages to their `workspace` equivalents.
- [x] **Step 3:** Run `pytest tests/test_projects_registry.py tests/test_attention.py tests/test_compose.py tests/test_compose_smoke.py tests/test_containerstate.py tests/test_caps.py tests/test_review_cleanup_smoke.py -v` — expect all PASS.
- [x] **Step 4:** Commit.

```bash
git add src/arduis/project.py src/arduis/attention.py src/arduis/compose.py src/arduis/containerstate.py src/arduis/topbar.py tests/test_projects_registry.py tests/test_attention.py tests/test_compose.py tests/test_compose_smoke.py tests/test_containerstate.py tests/test_caps.py tests/test_review_cleanup_smoke.py
git commit -m "refactor(model): rename remaining Task references to Workspace"
```

---

### Task 5: Update living docs (`CLAUDE.md`, `PROJECT.md`)

**Files:**
- Modify: `CLAUDE.md`
- Modify: `.planning/PROJECT.md`

**Scope — CLAUDE.md:** the "Docker Compose Orchestration (Phase 7)" section (current lines ~111-130) describes today's architecture in present tense ("the isolation unit is the TASK..."). Reword every "TASK"/"task" mention there to "WORKSPACE"/"workspace":
- "the isolation unit is the **TASK**" → "the isolation unit is the **WORKSPACE**"
- "a unique project name per TASK" → "per WORKSPACE"
- "an isolated DB per task for free" → "per workspace for free"
- "the **task folder**" → "the **workspace folder**"
- "a per-task offset" → "a per-workspace offset"
- "persist the chosen ports per task" → "per workspace"
- "on task conclude/hibernate" → "on workspace conclude/hibernate"
- "conclude task" and app-exit handlers" → "conclude workspace" and app-exit handlers"

**Scope — PROJECT.md:** ONLY these two lines (NOT the dated historical narrative log further down, which stays as a factual record of what was decided/named at the time):
- Line ~22 (executive summary): "task cross-repo = worktrees + symlinks espelhando a raiz, 2 terminais VTE por task" → "workspace cross-repo = worktrees + symlinks espelhando a raiz, 2 terminais VTE por workspace"
- Line ~103 (decisions table row): "Isolamento por TASK (set de worktrees cross-repo), não por worktree" → "Isolamento por WORKSPACE (set de worktrees cross-repo), não por worktree"

**Do NOT touch:** `.planning/STATE.md` (its only "task" mentions are inside dated historical decision-log bullets describing past phases — leave as period-accurate record), `.planning/milestones/*` (archived).

- [x] **Step 1:** Apply the CLAUDE.md renames listed above.
- [x] **Step 2:** Apply the two PROJECT.md line renames listed above.
- [x] **Step 3:** `grep -nE "\bTASK\b|\btask\b" CLAUDE.md` — confirm zero remaining hits in the Phase 7 section (other unrelated hits, if any, should not exist per earlier audit).
- [x] **Step 4:** Commit.

```bash
git add CLAUDE.md .planning/PROJECT.md
git commit -m "docs: update Task references to Workspace in living docs"
```

---

### Task 6: Full-suite verification sweep

**Files:** none (verification only)

- [x] **Step 1:** Run the full test suite: `pytest tests/ -v`. Expect the same pass count as before this plan started (no test lost, none newly failing).
- [x] **Step 2:** Run a final repo-wide sweep for leftover forbidden identifiers, excluding the known exceptions:

```bash
grep -rnE "\btask\b|\bTask\b|\bTASK\b|\btasks\b|\bTasks\b|\bTASKS\b" src/ tests/ CLAUDE.md .planning/PROJECT.md \
  | grep -v -- '-tasks' \
  | grep -v '.planning/PROJECT.md.*Phase 03' \
  || echo "CLEAN"
```

Manually confirm every remaining hit is one of: (a) a `-tasks` on-disk-suffix mention (Plan B territory, expected), (b) inside `.planning/STATE.md` or `.planning/milestones/` (out of scope, expected — should show zero here since those paths aren't in the grep target above, this is a safety net only).

- [x] **Step 3:** Report final diff stat: `git diff main --stat` (or equivalent base) to summarize the change.

---

## Deferred: on-disk suffix migration (`<repo>-tasks/` → `<repo>-workspaces/`)

**Not part of this plan.** The directory suffix that `workspace_dir_for` returns is left as `-tasks` on purpose: real, live git worktrees exist today under this convention for multiple projects (arduis itself, and separately Livon-Saude, sabores, grimorio — each with real `git worktree` registrations and, for Livon-Saude, active `docker-compose.yml` stacks). Flipping the suffix in code without migrating those directories would make arduis stop finding them on the next scan.

Follow-up work (separate plan, separate session):
1. Write a migration script that, per existing `<root>-tasks/` folder: for each real git-worktree subdir, uses `git worktree move` (or `git worktree repair` after a plain `mv`, whichever proves reliable) to relocate it to `<root>-workspaces/` while keeping git's bookkeeping intact; relative symlinks (non-chosen repos, mirrored root files) survive a same-depth parent rename unchanged.
2. Validate the script against a disposable fixture repo (fake root + fake worktree, same directory shape) — confirm `git worktree list` and `git status` are clean post-migration — before touching any real directory.
3. Run it against each real project one at a time, with explicit confirmation before each, checking first whether that project has an active docker-compose stack that would need to come down/up around the move.
4. Only after all four real directories are migrated, flip the one literal string in `workspace_dir_for` (`f"{base}-tasks"` → `f"{base}-workspaces"`) and fix the 3 exception docstring/comment lines in `window.py` + the field comment in `session.py` in the same commit, so code and disk never disagree.
