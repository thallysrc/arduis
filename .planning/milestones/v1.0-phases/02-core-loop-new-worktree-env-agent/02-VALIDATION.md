---
phase: 2
slug: core-loop-new-worktree-env-agent
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-09
validated: 2026-06-15
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (in `/tmp/arduis-venv`, not on PATH) |
| **Config file** | `pyproject.toml` (`pythonpath = ["src"]`) |
| **Quick run command** | `/tmp/arduis-venv/bin/python -m pytest tests/test_session.py tests/test_worktree.py -q` |
| **Full suite command** | `/tmp/arduis-venv/bin/python -m pytest` |
| **Estimated runtime** | ~0.03 seconds (actual measured) |

---

## Sampling Rate

- **After every task commit:** Run `/tmp/arduis-venv/bin/python -m pytest -q`
- **After every plan wave:** Run `/tmp/arduis-venv/bin/python -m pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

> All GTK-free seams have automated unit tests. GUI/teardown behaviors are manual-acceptance
> (see below), consistent with Phase-1 D-14.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 2-00-01 | 00 | 0 | WT-01/02/03, RAM-01 | T-02-01, T-02-02 | List-form argv, no `--force`, no path traversal | unit | `/tmp/arduis-venv/bin/python -m pytest tests/test_worktree.py tests/test_session.py -q` | ✅ | ✅ green (26 passed) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Requirement → Test Map

| Requirement | Description | Covering Tests | Count |
|-------------|-------------|----------------|-------|
| **WT-01** | New worktree creation: git argv builders, default-branch fallback, new-vs-existing inference | `test_add_argv`, `test_default_branch_fallback`, `test_infer_new_vs_existing`, `test_repo_has_commit_argv` | 4 |
| **WT-02** | Env/agent spawn prep: bytes feed constant, session shape serializable, agent resume feed | `test_agent_feed_is_bytes`, `test_agent_feed_unchanged`, `test_agent_resume_feed_is_bytes`, `test_default_repo_terminals`, `test_default_task_terminals`, `test_task_has_terminals_list`, `test_multi_repo_task_serializable`, `test_degenerate_single_repo_task_identical_shape`, `test_store_crud_and_serializable`, `test_store_remove_drops_task`, `test_terminal_record_has_repo_name_field`, `test_session_module_is_gtk_free`, `test_worktree_session_removed` | 13 |
| **WT-03** | Already-checked-out detection; `--force` never emitted; porcelain parse | `test_detect_checked_out`, `test_add_argv` (asserts `--force not in` argv), `test_sanitize_dir` (path-traversal guard, T-02-02) | 3 |
| **RAM-01** | Hibernate frees pid/pgid across all repos/terminals, keeps dirs, rss_kb untouched; auto_suspended idempotent | `test_hibernate_clears_all_repos_all_terminals`, `test_hibernate_clears_task_level_terminals`, `test_hibernate_fields_does_not_touch_auto_suspended`, `test_task_auto_suspended_trailing_field_defaults_false`, `test_task_auto_suspended_serializes`, `test_terminal_record_status_fields_appended_last`, `test_terminal_record_status_serializes` | 7 |

**Total: 26 tests, 26 passed, 0 failed — confirmed 2026-06-15.**

---

## Wave 0 Requirements

- [x] `tests/test_worktree.py` — git argv builders, default-branch fallback (no `origin`), directory-name sanitize, `git worktree list --porcelain` parse, infer new-vs-existing (WT-01, WT-02, WT-03)
- [x] `tests/test_session.py` — bytes-feed constant (`b"claude\n"`), `SessionStore` CRUD + serialization (GTK-free, RAM fields), hibernate model state (RAM-01)
- [x] pytest already installed in venv — no framework install needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| New worktree tab opens with `claude` running | WT-01, WT-02 | Requires live GTK/VTE rendering + agent install | Launch arduis inside the repo, click `+`, type a new branch name, confirm a tab opens in `../<repo>-<branch>` with `claude` running |
| Already-checked-out branch handled gracefully | WT-03 | Live UI focus/abort message | Pick a branch already in a tracked worktree → existing tab focused; pick the main checkout's branch → clear abort message, no `--force` |
| Hibernate frees RAM, keeps directory; resume relaunches | RAM-01 | Live process-group teardown + RAM observation | Right-click tab → Hibernate; confirm pgid killed (no orphan), tab dimmed/badged, directory still on disk; Resume → fresh `zsh`+`claude` |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-06-15 (post-execution reconcile)

---

## Validation Audit 2026-06-15

| Metric | Value |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Tests run | 26 |
| Tests passed | 26 |
| Tests failed | 0 |
| Manual-only items | 3 (all legitimate — require live GTK/VTE) |

This document was a stale plan-time draft (`status: draft`, `nyquist_compliant: false`,
`wave_0_complete: false`) — it was authored before Plan 00/01/02 executed and never
reconciled after the phase shipped.

**What is genuinely covered by automated tests (26 passing):**

- `tests/test_worktree.py` (6 tests): git argv builders for default-branch detection
  (origin + local fallback), worktree-add for new and existing branches (no `--force`,
  no shell strings), directory-name sanitization with path-traversal guard, porcelain
  parse of `git worktree list`, already-checked-out detection, new-vs-existing inference,
  and the `rev-parse --verify` born-HEAD guard.

- `tests/test_session.py` (20 tests): `AGENT_FEED = b"claude\n"` (bytes, not str — 0.76
  floor compliance), `AGENT_RESUME_FEED = b"claude --continue\n"`, `SessionStore` CRUD
  and JSON-serialization, multi-repo `Task`/`RepoCheckout`/`TerminalRecord` shape,
  hibernate model clearing pid/pgid across every terminal in every repo (no leaks), dirs
  preserved post-hibernate, `auto_suspended` field idempotency, GTK-import absence
  assertion, `WorktreeSession` removal confirmation (03.2 pivot).

**What remains manual-only (correct, not a gap):**

Three behaviors require live GTK/VTE rendering, real process groups, and RAM observation:
new-worktree tab opening with `claude` running; already-checked-out branch UI handling;
and the full hibernate/resume cycle with pgid kill + RAM drop. These are listed in the
Manual-Only table above and do not block `nyquist_compliant`.

No gaps were found. No escalations required.
