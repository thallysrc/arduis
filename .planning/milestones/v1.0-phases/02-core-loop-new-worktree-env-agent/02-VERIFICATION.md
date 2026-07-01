---
phase: 02-core-loop-new-worktree-env-agent
verified: 2026-06-09T18:00:00Z
status: passed
score: 4/4 must-haves verified
re_verification: false
---

# Phase 2: Core Loop (New Worktree → Env → Agent) Verification Report

**Phase Goal:** "+New worktree" creates a worktree and opens a terminal with `claude` running; births the GTK-free SessionStore. Delivers the product's core loop: new worktree → env → agent in seconds.
**Verified:** 2026-06-09T18:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User clicks "+New worktree", picks a new or existing branch, and a worktree is created via `git worktree add` at the configured location/base | ✓ VERIFIED | `window.py` `_create_worktree` flow builds argv via `argv_worktree_add_new`/`argv_worktree_add_existing` and runs async via `git_service.run_git_async`; the dialog, branch listing, and sibling-dir computation are all wired. Human-verified PASS (SC#2). |
| 2 | A terminal opens in the new worktree directory with the default agent (`claude`) already running | ✓ VERIFIED | `window.py` `_spawn_into` feeds `AGENT_FEED` (b"claude\n") in the `spawn_async` callback after pid arrives (line 392). Human-verified PASS (SC#2). |
| 3 | Picking an already-checked-out branch is handled gracefully (focus existing / clear message) — never `--force`d | ✓ VERIFIED | `window.py` `_create_worktree` runs porcelain pre-check via `branch_checked_out_path`; focuses tracked tab or calls `_abort_already_checked_out`; `--force` appears nowhere in worktree.py or window.py (only in comments/doc strings). Human-verified PASS (SC#3). |
| 4 | User can hibernate a worktree (agent process killed, directory kept) and resume it later, freeing the agent's RAM | ✓ VERIFIED | `window.py` `_on_hibernate` calls `_teardown_pgid(session.pid)` + `hibernate_fields(session)` + `page.set_needs_attention(True)`; `_on_resume` cold-relaunches via `_spawn_into`. Directory is never removed (Phase 8 concern). Human-verified PASS (SC#4). |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `tests/test_worktree.py` | Failing unit tests for git-argv builders + parsers | ✓ VERIFIED | 5 named tests (test_default_branch_fallback, test_add_argv, test_sanitize_dir, test_detect_checked_out, test_infer_new_vs_existing); all 5 PASS (25-test suite green). |
| `tests/test_session.py` | Failing unit tests for AGENT_FEED, SessionStore, hibernate model | ✓ VERIFIED | 4 named tests (test_agent_feed_is_bytes, test_store_serializable, test_hibernate_model, test_session_module_is_gtk_free); all 4 PASS. |
| `src/arduis/worktree.py` | Pure git-argv builders + parsers; no `gi`; no `--force` | ✓ VERIFIED | 156 lines; contains `def argv_worktree_add_new`, `def sanitize_branch_for_dir`, `def branch_checked_out_path`; no `import gi`; `--force` absent entirely. |
| `src/arduis/session.py` | GTK-free SessionStore + WorktreeSession + AGENT_FEED + hibernate_fields | ✓ VERIFIED | 86 lines; contains `AGENT_FEED = b"claude\n"`, `rss_kb`, `def hibernate_fields`, `asdict`; no `import gi`. |
| `src/arduis/swarm/__init__.py` | Named-empty swarm seam | ✓ VERIFIED | Exists; contains only a module docstring stating it is intentionally empty in v1. |
| `src/arduis/git_service.py` | Gio.Subprocess async runner off GTK loop | ✓ VERIFIED | Contains `def run_git_async`, `communicate_utf8_async`, `wrap_argv` via HostRunner; no `threading`, no `asyncio`. |
| `src/arduis/window.py` | Adw.TabView core-loop UI with full create/hibernate/resume/close flow | ✓ VERIFIED | Contains `Adw.TabView`, `SessionStore()`, `feed_child(AGENT_FEED)`, `run_git_async`, `set_sensitive(False)`, `branch_checked_out_path`, `def _teardown_pgid`, `hibernate_fields`, `set_needs_attention`, `set_menu_model`, `Gio.SimpleAction`, `os.killpg`, iteration over `self._store.all()`. |
| `src/arduis/spawn.py` | `build_worktree_spawn` added alongside Phase-1 `build_spawn_command` | ✓ VERIFIED | `def build_worktree_spawn` present; reuses `SHELL_ARGV`/`TERM_ENV`; both functions route through `HostRunner`. |
| `docs/PHASE2-ACCEPTANCE.md` | Manual acceptance checklist for SC#2/#3/#4 | ✓ VERIFIED | Contains all three behaviors (SC#2 new-worktree tab, SC#3 already-checked-out, SC#4 hibernate/resume), no-orphans, and D-03 disabled-button step. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `window.py` | `worktree.py` + `git_service.py` | `run_git_async` called with argv from worktree.py builders | ✓ WIRED | `run_git_async` appears 7 times in window.py; worktree argv builders are imported at lines 54–66 and called in `_create_worktree`, `_resolve_base_then_add`, `_open_and_add`, `_on_new_worktree_clicked`. |
| `window.py` | `Vte.Terminal.feed_child(AGENT_FEED)` | feed in spawn callback after pid arrives | ✓ WIRED | Line 392: `terminal.feed_child(AGENT_FEED)` inside `_make_wt_spawn_cb` closure, gated on `pid != -1` and `error is None`. |
| `window.py` | `session.py SessionStore` | every worktree tab is a view of a WorktreeSession | ✓ WIRED | `self._store = SessionStore()` at line 92; `self._store.add(session)` in the `_add_done` callback; `self._store.all()` in close-request teardown. |
| `src/arduis/worktree.py` | git CLI argv | list-form argv routed through HostRunner by the caller | ✓ WIRED | Pattern `["git", "-C"` appears at every argv builder; `run_git_async` routes them through `HostRunner.wrap_argv`. |
| `src/arduis/session.py` | `dataclasses.asdict` | to_dict / to_list serialization | ✓ WIRED | `from dataclasses import asdict, dataclass`; `to_dict` calls `asdict(self)`; `to_list` calls `s.to_dict()` per session. |

### Data-Flow Trace (Level 4)

This is a native GUI app; data flows through in-memory structures (no DB queries or REST API) so the standard "does the API return real data" check is N/A. The relevant flow is: branch name (user input) → dialog → `_create_worktree` → porcelain pre-check → `_open_and_add` → `git worktree add` → `WorktreeSession` created → `SessionStore.add` → `_spawn_into` feeds `AGENT_FEED` into the live terminal.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `window.py _open_and_add` | `wt_dir`, `session` | User branch input + `worktree_dir_for` + `git worktree add` exit 0 | Yes — only created on exit 0 from git subprocess | ✓ FLOWING |
| `window.py _make_wt_spawn_cb` | `session.pid`, `AGENT_FEED` | `spawn_async` callback pid + `b"claude\n"` bytes constant | Yes — pid from VTE callback; feed is the literal bytes constant | ✓ FLOWING |
| `window.py _on_resume` | `session.worktree_dir` | `WorktreeSession` dataclass field set at creation | Yes — set from git-confirmed path at worktree creation | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full pytest suite (25 tests) passes | `.venv/bin/python -m pytest -q` | `25 passed in 0.03s` | ✓ PASS |
| `worktree.py` imports clean (GTK-free) | `grep "import gi" src/arduis/worktree.py` | no output (exit 1) | ✓ PASS |
| `session.py` imports clean (GTK-free) | `grep "import gi" src/arduis/session.py` | no output (exit 1) | ✓ PASS |
| `--force` absent from worktree.py | `grep "\-\-force" src/arduis/worktree.py` | no output | ✓ PASS |
| `--force` absent from window.py logic | `grep "\-\-force" src/arduis/window.py` | only in comments/docstrings | ✓ PASS |
| `git_service.py` module importable | `python -c "import arduis.git_service as g; assert hasattr(g,'run_git_async')"` | confirmed (git_service.py verified directly) | ✓ PASS |
| All phase-2 commits present | `git log --oneline` | f3ae6fb, db3b4bd, 55f6534, 058af28, 926a377, 6fb3366, 9a5a511, a76b24a, f8d5b3c, 54c9bd0 all confirmed | ✓ PASS |
| GUI behaviors (SC#2/#3/#4, D-03, no-orphans) | Manual — see PHASE2-ACCEPTANCE.md | Human-verified and APPROVED (02-02-SUMMARY.md checkpoint) | ✓ PASS (human) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| WT-01 | 02-00, 02-01, 02-02 | User creates a worktree from a branch via the "＋ Nova worktree" UI | ✓ SATISFIED | `window.py` `_on_new_worktree_clicked` → `_present_new_worktree_dialog` → `_create_worktree`; human-verified PASS SC#2 |
| WT-02 | 02-00, 02-01, 02-02 | Worktree created via `git worktree add` at the configured location/base | ✓ SATISFIED | `argv_worktree_add_new`/`argv_worktree_add_existing` builders; sibling-dir from `worktree_dir_for`; default-branch chain (origin → local); human-verified PASS SC#2 |
| WT-03 | 02-00, 02-01, 02-02 | A terminal opens in the new worktree dir with the agent (`claude`) already running | ✓ SATISFIED | `_spawn_into` with `cwd=wt_dir`; `feed_child(AGENT_FEED)` after pid arrives; `AGENT_FEED = b"claude\n"` bytes constant (0.76 floor); human-verified PASS SC#2 |
| RAM-01 | 02-00, 02-01, 02-02 | Hibernate kills agent + stops containers, keeps dir; resume after | ✓ SATISFIED | `_on_hibernate` teardown via `_teardown_pgid(os.killpg SIGHUP→SIGKILL)` + `hibernate_fields` (dir preserved); `_on_resume` cold-relaunches; human-verified PASS SC#4 |

All four requirements claimed for Phase 2 (WT-01, WT-02, WT-03, RAM-01) are satisfied. REQUIREMENTS.md marks all four as "Complete".

### Anti-Patterns Found

No blocking anti-patterns. The following planned-stub seams are intentional and documented:

| File | Item | Severity | Impact |
|------|------|----------|--------|
| `session.py` `rss_kb=None` | RAM field present day-one; intentionally unpopulated until Phase 3 RAM-02/03 | ℹ️ Info | Not a stub — field exists; Phase 3 will populate it |
| `swarm/__init__.py` (docstring-only) | Named-empty seam per roadmap; no code in v1 | ℹ️ Info | Not a stub — deliberate seam documented in plan |

### Human Verification Required

None — all GUI/teardown behaviors were manually verified and approved during the Task 4 `checkpoint:human-verify` (APPROVED, recorded in 02-02-SUMMARY.md).

Behaviors verified:
- SC#2 (new worktree tab opens with claude running): PASS
- SC#3 (already-checked-out graceful, no --force): PASS
- SC#4 (hibernate frees RAM + keeps dir, resume relaunches): PASS
- No orphans on window close: PASS
- "+" disabled outside a git repo (D-03): PASS (after run.sh fix 058af28)

### Gaps Summary

No gaps. All four roadmap success criteria are satisfied, all required artifacts exist and are substantive and wired, all 25 automated tests pass, and the manual acceptance gate was approved by the human.

The phase delivers exactly what the goal states: "+New worktree creates a worktree and opens a terminal with `claude` running; births the GTK-free SessionStore. Delivers the product's core loop: new worktree → env → agent in seconds."

---

_Verified: 2026-06-09T18:00:00Z_
_Verifier: Claude (gsd-verifier)_
