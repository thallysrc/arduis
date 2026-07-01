---
phase: 06-per-worktree-setup-via-arduis-toml
verified: 2026-06-13T00:00:00Z
status: human_needed
score: 9/9 must-haves verified (automated); 4/4 roadmap SCs pass automated checks
re_verification: false
human_verification:
  - test: "Criterion 2 — setup commands visible in pane"
    expected: "After accepting the trust dialog for a repo with [setup] commands, the commands appear scrolling in the task's shell pane (not a blank/silent terminal). e.g. `echo arduis-setup-ran` prints visibly."
    why_human: "Requires a real display to eyeball the VTE pane content. The smoke proves bytes are fed to t1; human confirms rendering."
  - test: "Criterion 3 — login-shell shims resolve"
    expected: "A setup command like `node --version` or `asdf current` or `mise current` in .arduis.toml runs without `command not found` — the shim resolves because setup feeds into the existing `zsh -l -i` terminal."
    why_human: "Requires a real machine + version manager + shim installed. Cannot simulate headlessly."
  - test: "Criterion 4 (live dialog render) — Adw.AlertDialog shows exact commands with correct labels"
    expected: "On first create with an untrusted [setup]: ONE consolidated dialog appears with heading 'Rodar setup destes repositórios?', body listing each command verbatim grouped under the repo name, and two responses 'Pular' (close) and 'Confiar e rodar' (SUGGESTED/default)."
    why_human: "Adw.AlertDialog cannot be rendered or clicked headlessly via broadway. The smoke proves the trust mechanism (record_trust + feed bytes); human confirms the dialog text and button appearance."
  - test: "Criterion 4 (accept+persist) — 'Confiar e rodar' runs commands + second create silent"
    expected: "Clicking 'Confiar e rodar' causes setup commands to run in the pane AND a second create from the same unchanged repo does NOT re-prompt. Editing .arduis.toml DOES re-prompt."
    why_human: "Requires live interaction with the dialog and observing state across two task-create flows."
  - test: "Criterion 4 (skip) — 'Pular' leaves worktree un-setup, nothing persisted"
    expected: "Clicking 'Pular' on an untrusted repo: the task opens normally but NO commands run in the pane, and the next create from that repo re-prompts again (not silently skipped)."
    why_human: "Requires live dialog interaction and verifying absence of side effects."
  - test: "Criterion — failing setup does not crash creation"
    expected: "A deliberately failing setup command (e.g. `exit 1` or `npm install` in a non-node repo) shows its failure in the pane but does NOT block the agent from starting or crash the app."
    why_human: "Requires real command execution in a live terminal."
---

# Phase 6: Per-Worktree Setup via `.arduis.toml` Verification Report

**Phase Goal:** A new worktree is born "ready to work" — per-repo `.arduis.toml` read with sensible defaults (works with NO file), `[setup]` commands run on CREATION, visibly, through the host login shell (so npm/docker/version-manager shims resolve), gated by a trusted-repo-only confirmation.
**Verified:** 2026-06-13
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GTK-free `load_repo_setup(repo_dir)` returns `RepoSetup([])` on absent/garbage/wrong-type; returns ordered command list on valid `[setup]` | ✓ VERIFIED | `src/arduis/repoconfig.py` lines 31-52; 15 unit tests covering all tolerance cases; `test_repoconfig.py` suite passes 34/34 |
| 2 | `setup_feed_bytes(dir, cmds)` returns cd-guarded, newline-joined bytes (not &&-chained); `[]` returns `b""`; POSIX-single-quoted dir target | ✓ VERIFIED | `src/arduis/repoconfig.py` lines 55-75; `test_feed_exact_cd_guard_newline_joined` passes; shlex.quote deviation was caught by TDD and fixed to deterministic POSIX single-quoting |
| 3 | `setup_hash(commands)` is sha256 hex, stable for identical lists, changes on any edit/add/remove/reorder | ✓ VERIFIED | `src/arduis/trust.py` line 38; 6 hash-change tests covering all cases pass |
| 4 | `load_trusted(path)` is fail-closed: missing/garbage/wrong-type → `{}`; non-str values dropped | ✓ VERIFIED | `src/arduis/trust.py` lines 41-56; 5 tolerant-read tests pass |
| 5 | `record_trust(path, repo_id, hash)` atomically persists via tmp+os.replace; is_trusted exact; preserves prior; creates parent dir; survives OSError | ✓ VERIFIED | `src/arduis/trust.py` lines 84-110; 7 round-trip/atomic/best-effort tests pass |
| 6 | Both modules import no `gi` (GTK-free) | ✓ VERIFIED | `grep -c "import gi\|from gi" repoconfig.py trust.py` = 0/0; GTK-free test assertions in both test files |
| 7 | `_run_repo_setups(task)` is called only from `_finalize_task_creation` (CREATE path), never from `_resume_task`; feeds silently for already-trusted (repo_realpath, hash), gates the rest via `_present_setup_trust` | ✓ VERIFIED | `window.py` line 2186: call site confirmed in `_finalize_task_creation` body; `_resume_task` body (line 2928) confirmed to not contain `_run_repo_setups`; `_run_repo_setups` body verified to call `repoconfig.load_repo_setup`, `trust.setup_hash`, `trust.is_trusted`, `_feed_repo_setup`, `_present_setup_trust` |
| 8 | `_feed_repo_setup` targets the SHELL terminal `{task}:t1` only, never `{task}:t0` (agent); None-check + try/except guards | ✓ VERIFIED | `window.py` line 2257: `self._term_by_sid.get(f"{task.task_id}:t1")`; t0 not referenced; try/except on `feed_child`; smoke check `agent_terminal_never_fed` PASS |
| 9 | Headless broadway smoke 7/7: absent-file no-op, first-run untrusted, trusted→silent feed into t1 with cd-guarded bytes, agent t0 never fed, changed hash reprompts, real trust list untouched | ✓ VERIFIED | `tests/smoke/test_setup_feed_smoke.py` committed at `a53de7d`; 7/7 checks confirmed in 06-03-SUMMARY.md |

**Score:** 9/9 truths verified (automated)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/arduis/repoconfig.py` | Tolerant `[setup]` reader + `setup_feed_bytes` | ✓ VERIFIED | Exists, substantive (76 lines, full implementation), wired via `import repoconfig` in `window.py` |
| `src/arduis/trust.py` | `setup_hash` + fail-closed trust list + atomic writer | ✓ VERIFIED | Exists, substantive (111 lines, full implementation), wired via `import trust` in `window.py` |
| `tests/test_repoconfig.py` | 15 ENV-01/ENV-02 unit tests | ✓ VERIFIED | 15 tests passing; covers all tolerance + ordering + feed-bytes cases |
| `tests/test_trust.py` | 19 criterion-4 security tests | ✓ VERIFIED | 19 tests passing; covers hash stability/change, fail-closed read, atomic round-trip, best-effort |
| `src/arduis/window.py` (modified) | Trust-gated setup feed wired into `_finalize_task_creation` | ✓ VERIFIED | 3 new methods + call site present; `repoconfig` and `trust` imported; `_trusted_setups_path` set in `__init__` |
| `tests/smoke/test_setup_feed_smoke.py` | Headless broadway acceptance harness | ✓ VERIFIED | Exists, substantive (158 lines), 7/7 checks defined and passing per SUMMARY |
| `.planning/phases/06-per-worktree-setup-via-arduis-toml/06-HUMAN-UAT.md` | Live checklist for 4 criteria | ✓ VERIFIED | Exists, non-empty, contains "Confiar e rodar", covers all 4 criteria |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| `tests/test_repoconfig.py` | `src/arduis/repoconfig.py` | `import load_repo_setup, RepoSetup, setup_feed_bytes` | ✓ WIRED | Direct import at top of test file; all symbols exercised |
| `tests/test_trust.py` | `src/arduis/trust.py` | `import setup_hash, load_trusted, record_trust, is_trusted` | ✓ WIRED | Direct import at top of test file; all symbols exercised |
| `src/arduis/window.py` | `src/arduis/repoconfig.py` | `import repoconfig; load_repo_setup + setup_feed_bytes` | ✓ WIRED | Line 86: `from arduis import ... repoconfig, trust`; `repoconfig.load_repo_setup` in `_run_repo_setups`; `repoconfig.setup_feed_bytes` in `_feed_repo_setup` |
| `src/arduis/window.py` | `src/arduis/trust.py` | `import trust; setup_hash + is_trusted + record_trust` | ✓ WIRED | All three trust calls present in `_run_repo_setups` / `_present_setup_trust` |
| `window.py _feed_repo_setup` | shell terminal `{task}:t1` | `self._term_by_sid.get(f"{task.task_id}:t1").feed_child(...)` | ✓ WIRED | Line 2257-2261: exact pattern confirmed; t0 never referenced in this method |
| `tests/smoke/test_setup_feed_smoke.py` | `src/arduis/window.py` | drives `ArduisWindow._run_repo_setups` under broadway | ✓ WIRED | Imports `ArduisWindow`; calls `win._run_repo_setups(task)` directly |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `_run_repo_setups` | `setup.commands` | `repoconfig.load_repo_setup(repo.worktree_dir)` reads actual `.arduis.toml` from the worktree filesystem | Yes — reads real file; tolerant fallback to `[]` on absent/garbage | ✓ FLOWING |
| `_feed_repo_setup` | bytes fed to t1 | `repoconfig.setup_feed_bytes(repo.worktree_dir, commands)` | Yes — builds deterministic `cd '<dir>' &&\n<cmds>\n` bytes from real worktree dir + real command list | ✓ FLOWING |
| `_present_setup_trust` | `to_confirm` list | collected in `_run_repo_setups` from repos with non-empty commands that fail `is_trusted` | Yes — real repos, real trust check | ✓ FLOWING |
| Trust persistence | trust list file | `trust.record_trust(self._trusted_setups_path, repo_id, h)` on dialog accept | Yes — atomic write to `~/.config/arduis/trusted_setups.toml` | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 34 unit tests (repoconfig + trust) pass | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_repoconfig.py tests/test_trust.py` | 34 passed in 0.06s | ✓ PASS |
| Full suite 274 tests, no regression | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/ --ignore=tests/smoke` | 274 passed in 1.19s | ✓ PASS |
| window.py parses cleanly | `python -c "import ast; ast.parse(open('src/arduis/window.py').read())"` | `parse-ok` | ✓ PASS |
| GTK-free: no `gi` import in domain modules | `grep -c "import gi\|from gi" repoconfig.py trust.py` | 0/0 | ✓ PASS |
| _run_repo_setups called once in _finalize_task_creation | source inspection | 1 call at line 2186, after `_spawn_task_terminals` | ✓ PASS |
| _resume_task does not call _run_repo_setups | source inspection of `_resume_task` body | body confirmed free of `_run_repo_setups` | ✓ PASS |
| Headless broadway smoke 7/7 | `tests/smoke/test_setup_feed_smoke.py` (documented in 06-03-SUMMARY) | 7/7 PASS | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ENV-01 | 06-01-PLAN.md | `.arduis.toml` per repo read with sensible defaults; works without the file | ✓ SATISFIED | `load_repo_setup` tolerant reader; 9 tolerance + ordering tests passing; smoke `absent_file_is_noop` PASS |
| ENV-02 | 06-01-PLAN.md, 06-02-PLAN.md | Setup commands run on worktree creation via host login shell | ✓ SATISFIED | `setup_feed_bytes` + `_feed_repo_setup` feed into t1 (the `zsh -l -i` terminal); smoke `trusted_feeds_shell_t1` PASS; human UAT pending for shim resolution |

Both ENV-01 and ENV-02 are owned by Phase 6 per REQUIREMENTS.md traceability table. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | — | No TODO/FIXME/placeholder/return null/hardcoded empty data found in any Phase-6 file | — | — |

No anti-patterns detected across `repoconfig.py`, `trust.py`, `tests/test_repoconfig.py`, `tests/test_trust.py`, or `tests/smoke/test_setup_feed_smoke.py`.

### Human Verification Required

The automated checks (unit tests, smoke, code inspection) cover all mechanical properties:

- Tolerant parse (criterion 1): proven
- Feed bytes to shell t1, not agent t0 (criteria 2/3 mechanism): proven
- Trust mechanism (hash stability, is_trusted exactness, record_trust atomic, changed-hash reprompts, real trust list untouched): proven
- CREATE-only (not on resume): proven by code inspection

The following require a real display and live execution:

**1. Setup visibly runs in pane (criterion 2)**
**Test:** Add `[setup]\ncommands = ["echo arduis-setup-ran", "pwd"]` to a repo's `.arduis.toml`, create a task, accept the dialog.
**Expected:** `arduis-setup-ran` and the worktree path scroll in the shell pane.
**Why human:** Requires eyeballing VTE rendering on a real display.

**2. Login-shell shims resolve (criterion 3)**
**Test:** Set `commands = ["node --version"]` (or `asdf current` / `mise current`), create + accept.
**Expected:** The version prints — NOT `command not found`.
**Why human:** Requires a real machine with version-manager shims installed.

**3. Trust dialog render + exact commands shown (criterion 4 — the security crux)**
**Test:** First create with an untrusted `[setup]`.
**Expected:** ONE consolidated `Adw.AlertDialog` with heading "Rodar setup destes repositórios?", body listing the EXACT commands grouped by repo name, responses "Pular" and "Confiar e rodar" (SUGGESTED/default).
**Why human:** `Adw.AlertDialog` cannot be rendered or clicked headlessly. The smoke proves the trust mechanism; human must confirm the user sees the literal commands before authorizing.

**4. Accept+persist+silent-reuse (criterion 4)**
**Test:** Accept → confirm commands run; create a second task from the same unchanged repo.
**Expected:** Second create does NOT re-prompt. Editing `.arduis.toml` DOES re-prompt.
**Why human:** Requires live dialog interaction and state across two create flows.

**5. Skip leaves worktree un-setup (criterion 4)**
**Test:** Click "Pular" on untrusted repo.
**Expected:** Task opens, no commands run in pane, next create re-prompts.
**Why human:** Requires live dialog interaction + verifying absence of side effects.

**6. Failing setup does not crash creation**
**Test:** Use a deliberately failing command (e.g. `exit 1`).
**Expected:** Error shows in pane; agent starts normally; no crash.
**Why human:** Requires real command execution in a live terminal.

These items are documented in `06-HUMAN-UAT.md` with copy-pasteable steps.

### Gaps Summary

No gaps. All automated must-haves are verified. The phase is mechanically complete and correct. The `human_needed` status reflects that live-display confirmation (dialog render, shim resolution, visual pane output) has not yet been performed — these are inherently display-only checks, not code deficiencies.

The security-crux item (criterion 4 dialog showing exact commands) is the most important human check: it is the user's only checkpoint before arbitrary repo-committed commands execute on their machine.

---

_Verified: 2026-06-13_
_Verifier: Claude (gsd-verifier)_
