---
phase: 08-review-cleanup
verified: 2026-06-15T14:00:00Z
status: human_needed
score: 4/4 must-haves verified
re_verification: false
human_verification:
  - test: "Right-click a task row, select 'Ver diff > <repo>', observe the VTE pane"
    expected: "A new pane opens showing `git diff` output WITH color; the pane is read-only (typing does nothing, no keystrokes reach the shell)"
    why_human: "set_input_enabled(False) is wired headlessly; actual VTE rendering, color, and keystroke rejection require a live display and a task with uncommitted changes"
  - test: "Ensure gh is authenticated, right-click a task row, select 'Abrir PR (web)'"
    expected: "Browser opens the GitHub PR creation form for the task's branch; after returning to arduis, the sidebar subline refreshes to show the new PR number and state"
    why_human: "gh pr create --web opens a browser tab — requires real GitHub, real user interaction, and real subline update visible on screen"
  - test: "With a task row selected, observe the sidebar subline, then right-click and select 'Atualizar status'"
    expected: "Subline shows 'feat/x · ↑N ↓M · PR #NN open' (or 'sem PR' if none); rapid clicking 'Atualizar status' multiple times does not spam gh (TTL + debounce); after `gh auth logout`, subline shows 'gh não autenticado' without crashing"
    why_human: "Throttle behavior (TTL cache suppression, debounce drop) and degrade rendering require a live display with a real repo and a real gh auth state"
  - test: "Create a task with a clean worktree, right-click, select 'Concluir task', click 'Concluir' in the dialog"
    expected: "Task disappears from sidebar; worktree directories are removed on disk; source repo directories and the branch still exist; task-folder symlink links are gone but their targets survive"
    why_human: "End-to-end conclude UX (dialog → teardown → sidebar removal) requires a live display and real worktrees; on-disk verification requires opening a terminal to check"
  - test: "Create a task, make an uncommitted change in one worktree, right-click, select 'Concluir task', click 'Concluir'"
    expected: "A pt-BR dialog appears naming the dirty repo(s); NO worktrees are removed; task remains in sidebar; no --force is used"
    why_human: "Dirty-tree refusal dialog rendering and the user-facing message require a live display; verifying 'nothing removed on disk' requires inspecting actual worktree dirs"
---

# Phase 8: Review + Cleanup Verification Report

**Phase Goal:** close the work + resource loops — read-only diff, branch/PR status via git/gh (read-only, throttled), and "Concluir task" with the SAFE teardown order (never force-deleting a dirty tree).
**Verified:** 2026-06-15T14:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Read-only diff of a worktree's changes | VERIFIED | `_open_diff_leaf` in window.py (line 3026): `_make_terminal()` → `set_input_enabled(False)` → `_make_leaf(badge_label="diff")` → `spawn_async(cwd=worktree_dir, ["zsh","-l","-i","-c","git --no-pager diff; exec zsh -i"])`. Menu entry `win.ver_diff` wired in `_append_review_menu_items` (line 1417) appended in both active+hibernated branches. Test: `grep set_input_enabled(False)` confirmed present; `tests/test_review.py` pins `argv_diff` shape; 21 unit tests pass. |
| 2 | Open a PR via gh + read/display PR status (read-only) | VERIFIED | `gh.py`: `argv_pr_view(branch)` → `["gh","pr","view",branch,"--json",PR_VIEW_FIELDS]`, `argv_pr_create_web()` → `["gh","pr","create","--web"]`. `_on_open_pr` in window.py (line 3229) runs `gh.argv_pr_create_web()` via `run_git_async(cwd=primary_worktree)`, toasts rc==0/"PR aberto no navegador" + force-refreshes status, rc==4/GH_UNAUTH_MSG. Offered only when `gh.gh_available()`. `tests/test_gh.py` (19 tests) pins argv shapes, parse_pr_view garbage guard, degrade constants, subline formatters — gh never invoked in tests. |
| 3 | Branch+PR status via git/gh (read-only, throttled) | VERIFIED | `_refresh_task_status(task, *, force=False)` (line 3135): reads branch → ahead/behind → PR for `task.repos[0]`. PR read gated on `gh.gh_available()` (absent → `GH_ABSENT_MSG`, skip gh), then `ReviewCache.fresh_payload(sid, now, GH_TTL_S)` (skip if fresh unless force), then `_pr_busy` drop (debounce). Auto-reads fire at `_finalize_task_creation` tail (create) and `_on_row_activated` (ACTIVE only). No poll. `_pr_busy` (line 287), `ReviewCache` (line 286), `GH_TTL_S` (line 75) all present. `tests/test_review_cache.py` (13 tests) pins TTL logic. |
| 4 | "Concluir" follows safe order, NEVER force-deletes a dirty tree | VERIFIED | `_conclude_task` (line 3295): (a) `_teardown_session_terminals` + `_clear_task_state_files` → (b) `_container_down` → (c) `_conclude_clean_gate` (all-or-nothing porcelain check, refuses if ANY dirty, zero remove argv) → (d) `_conclude_remove_worktrees` (NO `--force`) → (e) `_conclude_prune` → (f) `_conclude_clean_task_folder` (`islink`-guarded unlink + `rmdir`, NO `rmtree`) → (g) `_conclude_finalize`. grep confirms: `--force`/`-f` appear ONLY in comments/docstrings; `shutil.rmtree` ABSENT from window.py; `os.path.islink` guard present. `tests/test_window_conclude.py` (3 tests): pins order (a→g), dirty refusal (zero remove argv, task not dropped), never-force. `tests/test_review_cleanup_smoke.py` (4 tests): real-git clean remove + source/branch survive (D-10), dirty refuses, D-10 islink-unlink keeps target, gh degrade. |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/arduis/review.py` | argv_diff, argv_diff_stat, argv_status_porcelain, parse_porcelain_clean, argv_worktree_remove (no --force), argv_worktree_prune, argv_current_branch, argv_ahead_behind, parse_ahead_behind | VERIFIED | All 9 functions present. GTK-free (0 `gi` imports). `argv_worktree_remove` structurally never emits `--force`/`-f`. |
| `src/arduis/review_cache.py` | is_fresh(ts, now, ttl) + ReviewCache (put/get/fresh_payload) + GIT_TTL_S=30.0 + GH_TTL_S=120.0 | VERIFIED | All present. GTK-free (0 `gi` imports). Strict `<` bound confirmed. |
| `src/arduis/gh.py` | PR_VIEW_FIELDS, argv_pr_view, argv_pr_create_web, parse_pr_view, gh_available, degrade_message, format_pr_subline, format_branch_subline, GH_ABSENT_MSG, GH_UNAUTH_MSG, GH_EXIT_NEEDS_AUTH | VERIFIED | All present. GTK-free (0 `gi` imports). parse_pr_view raises on garbage (not returns None). |
| `src/arduis/git_service.py` | run_git_async(argv, on_done, runner=None, cwd=None) backward-compatible optional cwd | VERIFIED | `cwd: str | None = None` as last param. `cwd is None` → `Gio.Subprocess.new` (byte-identical). `cwd` set → `Gio.SubprocessLauncher.new(flags)` + `set_cwd` + `spawnv`. |
| `src/arduis/window.py` | _open_diff_leaf (set_input_enabled(False)), _refresh_task_status (TTL+debounce), _on_open_pr, _conclude_task (FIXED order), _conclude_clean_gate (all-or-nothing), no --force, no rmtree, islink guard | VERIFIED | All methods present and correctly implemented. See truth 1-4 evidence above. |
| `tests/test_review.py` | REVIEW-01/03 + GIT-01 unit coverage incl. never-force guard, porcelain clean/dirty, ahead/behind parse | VERIFIED | 21 tests. Passes. |
| `tests/test_review_cache.py` | TTL is_fresh logic + cache round-trip + GIT_TTL_S/GH_TTL_S | VERIFIED | 13 tests. Passes. |
| `tests/test_gh.py` | REVIEW-02/GIT-01: argv shapes, parse_pr_view garbage guard, gh_available, exit-4/absent degrade, subline formatter | VERIFIED | 19 tests. Passes. gh never invoked. |
| `tests/test_git_service_cwd.py` | run_git_async cwd= signature + real-cwd proof via GLib loop + temp repo | VERIFIED | 2 tests. Passes. Real temp git repo used. |
| `tests/test_window_conclude.py` | REVIEW-03 order assertion + dirty-tree refusal (no remove argv, no --force) | VERIFIED | 3 tests. Passes. Sequence recorder confirms exact order; dirty case: zero remove argv + task not dropped. |
| `tests/test_review_cleanup_smoke.py` | Clean removes (D-10), dirty refuses (no --force), islink D-10, gh degrade | VERIFIED | 4 tests. Passes. Real git repo + worktrees. Located at `tests/test_review_cleanup_smoke.py` (not in `tests/smoke/`). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `window.py _open_diff_leaf` | `review.argv_diff + Vte.Terminal.set_input_enabled(False)` | spawn read-only leaf with `git --no-pager diff` cwd=worktree | WIRED | `set_input_enabled(False)` at line 3061; spawn uses `["zsh","-l","-i","-c","git --no-pager diff; exec zsh -i"]` with cwd=worktree_dir |
| `window.py _refresh_task_status` | `gh.argv_pr_view / review.argv_current_branch + run_git_async(cwd=worktree)` | TTL-cache + debounce-gated read, parse, render subline | WIRED | `gh.argv_pr_view(repo.branch)` at line 3172; `review.argv_current_branch` at line 3151; `cwd=repo.worktree_dir` throughout |
| `window.py _conclude_task` | `_teardown_session_terminals → _container_down → review.argv_status_porcelain → review.argv_worktree_remove → review.argv_worktree_prune → os.unlink symlinks → _store.remove` | FIXED ordered teardown chain (D-04) with porcelain clean-gate before any removal | WIRED | Full chain implemented at lines 3295-3510; all intermediate methods present and correctly sequenced |
| `tests/test_window_conclude.py` | `window.py _conclude_task` | mock channels, record call order, assert order + dirty refusal + never-force + D-10 | WIRED | Sequence recorder confirms `_teardown → _clear_state → _container_down → [porcelain] → [remove] → [prune] → _clean_folder → _finalize` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `window.py _refresh_task_status` | `_subline_by_sid[sid]` label text | `run_git_async(review.argv_current_branch(...), cwd=worktree)` → `run_git_async(gh.argv_pr_view(...), cwd=worktree)` | Yes — real git/gh subprocess calls via `Gio.SubprocessLauncher`; parse result written to `_set_status_subline` | FLOWING |
| `window.py _open_diff_leaf` | VTE terminal content | `spawn_async(cwd=worktree_dir, ["zsh","-l","-i","-c","git --no-pager diff; exec zsh -i"])` | Yes — real git diff subprocess; VTE PTY stream | FLOWING (visual output is host-only live UAT) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| review.py: 9 argv builders return correct list-form argv | `pytest tests/test_review.py -q -p no:warnings` | 21 passed | PASS |
| review_cache.py: is_fresh TTL + ReviewCache round-trip | `pytest tests/test_review_cache.py -q -p no:warnings` | 13 passed | PASS |
| gh.py: argv shapes, parse_pr_view raises on garbage, degrade, sublines | `pytest tests/test_gh.py -q -p no:warnings` | 19 passed | PASS |
| git_service.py: cwd= backward-compat + real-cwd proof | `pytest tests/test_git_service_cwd.py -q -p no:warnings` | 2 passed | PASS |
| window.py conclude: fixed order + dirty refusal + never-force | `pytest tests/test_window_conclude.py -q -p no:warnings` | 3 passed | PASS |
| Real-git smoke: clean removes (D-10), dirty refuses, islink, gh degrade | `pytest tests/test_review_cleanup_smoke.py -q -p no:warnings` | 4 passed | PASS |
| Full suite: no regression | `pytest tests/ -p no:warnings` | **406 passed** | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| REVIEW-01 | 08-01, 08-03 | Usuário vê o diff (read-only) das mudanças de uma worktree | SATISFIED (headless) | `argv_diff`/`argv_diff_stat` pinned by unit tests; `_open_diff_leaf` with `set_input_enabled(False)` wired in window.py; menu entry `win.ver_diff` registered + appended in both menu branches. Live rendering: human UAT item 1. |
| REVIEW-02 | 08-02, 08-03 | Usuário abre PR via `gh` (shell-out); o app lê o status do PR | SATISFIED (headless) | `argv_pr_view` + `parse_pr_view` + degrade helpers unit-tested; `_on_open_pr` wired (`gh pr create --web`); `Abrir PR (web)` menu item gh-gated. Live PR creation: human UAT item 2. |
| REVIEW-03 | 08-01, 08-04 | "Concluir worktree" → remove a worktree (+ teardown de containers) with safe order | SATISFIED (headless + real-git) | `_conclude_task` FIXED order wired; `_conclude_clean_gate` ALL-OR-NOTHING dirty refusal; NO `--force` anywhere (grep verified); `islink`-guarded unlink, no `rmtree`; order+refusal proven by `test_window_conclude.py` (mocked) + `test_review_cleanup_smoke.py` (real git). Live UX: human UAT items 4-5. |
| GIT-01 | 08-01, 08-02, 08-03 | O app lê e exibe branch + status de PR via git/`gh` (somente leitura, throttled) | SATISFIED (headless) | `review.argv_current_branch`/`argv_ahead_behind`/`parse_ahead_behind` + `ReviewCache`/`is_fresh`/`GIT_TTL_S`/`GH_TTL_S` unit-tested; `_refresh_task_status` wired with gh_available gate + TTL cache + `_pr_busy` debounce; auto-reads on create+row-activate, no poll. Live throttle feel: human UAT item 3. |

### Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| `src/arduis/window.py` line 3480 | `os.rmdir(task.task_dir)` — comment says "only succeeds if empty — never rmtree" | Info | This is correct behavior: `os.rmdir` raises `OSError` if non-empty (swallowed), so it cannot recursively delete. Not a stub. |
| `tests/test_review_cleanup_smoke.py` line 62 | `(os.path.join(wt, "f.txt"))` — parenthesized expression, effectively a no-op | Info | Dead code line; the actual modification is on line 63-64 (`open(...).write(...)`). The dirty-tree test still works correctly. Not a blocker. |

No blockers found. The load-bearing safety invariants are all verified:
- NO `git worktree remove --force` anywhere in window.py (only docstring prose about the rule)
- NO `shutil.rmtree` in window.py
- `os.path.islink` guard present in `_conclude_clean_task_folder`

### Human Verification Required

These items require a live display, real git repos, and/or a real GitHub account. All underlying logic and safety properties are proven headless. The 08-HUMAN-UAT.md tracks these formally.

**1. Read-only diff pane (REVIEW-01)**

**Test:** Right-click a task row that has uncommitted changes, select "Ver diff > <repo>". Try typing in the diff pane.
**Expected:** A new VTE pane opens showing the colored `git diff` output. Keystrokes do not appear (pane is read-only). Scrolling and copy still work.
**Why human:** VTE rendering, color output, and keystroke rejection require a live display.

**2. Open PR via browser (REVIEW-02)**

**Test:** Ensure gh is authenticated. Right-click a task row on a branch without an existing PR, select "Abrir PR (web)".
**Expected:** Browser opens the GitHub PR creation form for that branch. After creating the PR and returning to arduis, the sidebar subline shows "PR #NN open".
**Why human:** Requires real GitHub, a real gh auth session, and browser interaction.

**3. Status throttle + degrade (GIT-01)**

**Test:** (a) Observe the sidebar subline for a task. Right-click "Atualizar status" multiple times rapidly. (b) Run `gh auth logout`, then force a status refresh.
**Expected:** (a) Subline updates once; rapid refreshes do not cause multiple gh calls (debounce). (b) Subline shows "gh não autenticado" without crashing; re-auth restores normal behavior.
**Why human:** Throttle feel (cache suppression, debounce) and live degrade rendering require a real display and real gh state.

**4. Clean conclude UX + on-disk verification (REVIEW-03)**

**Test:** Create a task with clean worktrees. Right-click "Concluir task", read the dialog body (should say "branch ficam intactos"), click "Concluir".
**Expected:** Task disappears from sidebar. Worktree directories are removed on disk. Source repo directories and the branch still exist (`git branch --list` in the source repo shows the branch). Task-folder symlink links are gone but their targets (e.g. `docker-compose.yml`) survive.
**Why human:** End-to-end UX (dialog, sidebar disappearance) and on-disk verification require a live display and real worktrees.

**5. Dirty-tree refusal UX (REVIEW-03 criterion 4 — the load-bearing safety)**

**Test:** Create a task, make an uncommitted change in one worktree. Right-click "Concluir task", click "Concluir".
**Expected:** A pt-BR dialog appears naming the dirty repo. NO worktrees are removed. The task remains in the sidebar. The dialog offers no "force" button. After committing or discarding the change, conclude succeeds.
**Why human:** The dialog text, the visual refusal feedback, and the on-disk confirmation that nothing was deleted require a live display and real worktrees.

### Gaps Summary

No gaps found. All automated must-haves are verified. The 5 human verification items are architectural requirements of the phase (visual rendering, real browser interaction, live gh degrade) — they are not implementation gaps. The 08-HUMAN-UAT.md documents them formally for the developer to run on a real display.

**Key safety verifications passed:**
- `git worktree remove --force` does not appear anywhere in window.py (only in comments explaining the absence)
- `shutil.rmtree` does not appear in window.py
- `os.path.islink` guard confirmed in `_conclude_clean_task_folder`
- All-or-nothing dirty refusal confirmed by both mocked sequence test and real-git smoke
- GTK-free discipline confirmed for review.py, review_cache.py, and gh.py (0 gi imports each)
- 406 tests pass with 0 failures, 0 regressions

---

_Verified: 2026-06-15T14:00:00Z_
_Verifier: Claude (gsd-verifier)_
