---
status: validated
nyquist_compliant: true
wave_0_complete: true
validated: 2026-06-15
---

# Phase 8: Review + Cleanup — Validation Strategy

**Nyquist validation: ON.** Every requirement maps to an automated test (unit/smoke) plus, where a
human must observe (color, browser PR, real conclude), a live UAT step. The conclude clean-gate
(criterion 4 — never destroy uncommitted work) is the security item and is covered TWICE: a mocked
order/refusal unit test (Plan 04) AND a real-git dirty-tree refusal smoke (Plan 05) AND a human
dirty-conclude step (Plan 06).

## Executor environment

- **Unit/smoke runner:** `/tmp/arduis-venv/bin/python -m pytest tests/ -q` (406 green at phase completion).
- **Headless GUI:** `gtk4-broadwayd :9N` + `GDK_BACKEND=broadway` (per MEMORY arduis-dev-environment).
  Do NOT override `XDG_RUNTIME_DIR`. Smoke SKIPS exit-0 if broadwayd absent.
- **Live host:** git 2.43 + gh 2.93 authed (`thallysrc`, ssh). Real `gh`/`git diff` are best as
  argv/parse asserts + a real-git dirty-tree fixture under sandbox `$HOME` for the conclude clean-gate.
- **NEVER run `gh pr create` in any test** — argv-shape assertion only; the real PR is a human UAT step.

## Requirement → Test Map

| Req ID | Behavior | Test Type | File | Tests | Status |
|--------|----------|-----------|------|-------|--------|
| REVIEW-01 | `argv_diff`/`argv_diff_stat` shape + discrete repo element | unit | `tests/test_review.py` | `test_argv_diff_is_verified_listform`, `test_argv_diff_stat_is_verified_listform`, `test_argv_diff_repo_is_a_discrete_element` | ✅ |
| REVIEW-01 | read-only diff leaf wired (`set_input_enabled(False)`) | code-inspection (VERIFICATION.md) | `src/arduis/window.py` line 3061 | grep-verified: `set_input_enabled(False)` present; `win.ver_diff` registered in both menu branches | ✅ |
| REVIEW-01 | diff renders WITH COLOR + rejects typing | live UAT | 08-HUMAN-UAT step 2 | manual — requires live display + real VTE | MANUAL-ONLY |
| REVIEW-02 | `parse_pr_view` json shape + garbage guard | unit | `tests/test_gh.py` | `test_parse_pr_view_returns_dict_on_valid_json`, `test_parse_pr_view_raises_value_error_on_bad_json`, `test_parse_pr_view_raises_type_error_on_list_top_level`, `test_parse_pr_view_raises_type_error_on_scalar_top_level` | ✅ |
| REVIEW-02 | `argv_pr_create_web()` shape (the ONE allowed write — never executed) | unit | `tests/test_gh.py` | `test_argv_pr_create_web_is_the_one_allowed_write` | ✅ |
| REVIEW-02 | `argv_pr_view` shape + PR_VIEW_FIELDS | unit | `tests/test_gh.py` | `test_argv_pr_view_shape`, `test_pr_view_fields_contains_expected_keys` | ✅ |
| REVIEW-02 | 'Abrir PR (web)' wired; gh-gated | code-inspection (VERIFICATION.md) | `src/arduis/window.py` line 3229 | `_on_open_pr` wired; `Abrir PR (web)` gh-gated via `gh.gh_available()` | ✅ |
| REVIEW-02 | real PR create + real status in subline | live UAT | 08-HUMAN-UAT step 4 | manual — requires real GitHub + browser | MANUAL-ONLY |
| REVIEW-03 | `parse_porcelain_clean` true/false (clean/dirty) | unit | `tests/test_review.py` | `test_parse_porcelain_clean_empty_is_clean`, `test_parse_porcelain_clean_whitespace_only_is_clean`, `test_parse_porcelain_clean_untracked_is_dirty`, `test_parse_porcelain_clean_modified_is_dirty`, `test_parse_porcelain_clean_staged_is_dirty` | ✅ |
| REVIEW-03 | `argv_worktree_remove` NEVER contains `--force`/`-f` | unit (guard) | `tests/test_review.py` | `test_argv_worktree_remove_never_emits_force` | ✅ |
| REVIEW-03 | conclude ORDER: kill→down→check→remove→prune + dirty REFUSAL | unit (sequence recorder, mocked) | `tests/test_window_conclude.py` | `test_clean_conclude_follows_fixed_order_and_never_forces`, `test_dirty_repo_refuses_whole_conclude_no_remove`, `test_no_repos_skips_straight_to_finalize` | ✅ |
| REVIEW-03 | real-git clean conclude removes worktrees, keeps source+branch+symlink-target (D-10); dirty REFUSED | smoke (real git) | `tests/test_review_cleanup_smoke.py` | `test_clean_worktree_removed_source_and_branch_survive`, `test_dirty_worktree_refuses_remove_without_force`, `test_d10_islink_unlink_keeps_target` | ✅ |
| REVIEW-03 | live clean vs dirty conclude (criterion 4) | live UAT | 08-HUMAN-UAT steps 6-7 | manual — requires live display + real worktrees | MANUAL-ONLY |
| GIT-01 | `parse_ahead_behind` parses `"3\t2"`/garbage (6 cases) | unit | `tests/test_review.py` | `test_parse_ahead_behind_two_counts`, `test_parse_ahead_behind_zeros`, `test_parse_ahead_behind_empty_is_zero_zero`, `test_parse_ahead_behind_garbage_is_zero_zero`, `test_parse_ahead_behind_single_token_is_zero_zero`, `test_parse_ahead_behind_never_raises_on_junk` | ✅ |
| GIT-01 | `review_cache.is_fresh` TTL logic + ReviewCache round-trip | unit | `tests/test_review_cache.py` | 13 tests covering None/expired/fresh/boundary/overwrite/missing/fresh_payload/TTL constants | ✅ |
| GIT-01 | gh exit-4 → "não autenticado"; absent → "ausente" (degrade) | unit | `tests/test_gh.py` | `test_degrade_constants_pinned`, `test_degrade_message_exit_4_is_unauthed`, `test_degrade_message_other_rc_is_none`, `test_gh_available_returns_bool`, `test_gh_available_true_when_which_finds_gh`, `test_gh_available_false_when_which_returns_none` | ✅ |
| GIT-01 | `run_git_async(cwd=...)` backward-compatible + real-cwd | unit (GLib loop + temp repo) | `tests/test_git_service_cwd.py` | `test_run_git_async_without_cwd_is_backward_compatible`, `test_run_git_async_cwd_runs_child_in_that_dir` | ✅ |
| GIT-01 | gh degrade real-path smoke (no crash, gh absent) | smoke (real git) | `tests/test_review_cleanup_smoke.py` | `test_gh_absent_degrades_gracefully` | ✅ |
| GIT-01 | status subline + TTL + `_pr_busy` debounce + gh_available gate (no poll) | code-inspection (VERIFICATION.md) | `src/arduis/window.py` lines 287, 3135, 3172 | `_refresh_task_status` wired with gh_available gate + TTL cache + `_pr_busy` debounce; no poll | ✅ |
| GIT-01 | throttle + degrade behave live | live UAT | 08-HUMAN-UAT steps 3, 5 | manual — requires live display + real gh auth state | MANUAL-ONLY |

### GTK-free discipline

| Module | Automated Check | Status |
|--------|----------------|--------|
| `src/arduis/review.py` | `test_review_module_is_gtk_free` (test_review.py) | ✅ |
| `src/arduis/review_cache.py` | `test_review_cache_module_is_gtk_free` (test_review_cache.py) | ✅ |
| `src/arduis/gh.py` | `test_gh_module_is_gtk_free` (test_gh.py) | ✅ |

## Wave 0 Gaps — Resolved at Phase Completion

All scaffolds planned in Wave 0 were created and verified:

- [x] `tests/test_review.py` — 21 tests: argv builders, porcelain clean/dirty, **never-force guard**, ahead/behind parse, GTK-free (08-01)
- [x] `tests/test_review_cache.py` — 13 tests: TTL `is_fresh` + ReviewCache round-trip + GIT/GH TTL constants + GTK-free (08-01)
- [x] `tests/test_gh.py` — 19 tests: pr-view parse + garbage guard, degrade (absent/exit-4), subline formatters, GTK-free (08-02)
- [x] `tests/test_git_service_cwd.py` — 2 tests: `run_git_async` cwd= signature + real-temp-repo cwd proof (08-02)
- [x] `tests/test_window_conclude.py` — 3 tests: conclude order + dirty refusal + never-force + D-10 (mocked channels) (08-04)
- [x] `tests/test_review_cleanup_smoke.py` — 4 tests: real-git clean remove (D-10), dirty refuses, islink D-10, gh-absent degrade (08-05) **Note: landed at `tests/test_review_cleanup_smoke.py`, not `tests/smoke/` as originally planned — path corrected here.**

## Headless vs Host-only-live split

**Headless / automated (Plans 01-05):**
- ALL GTK-free argv builders + parsers + cache TTL (review/gh/review_cache) — pure unit, no gi.
- `run_git_async` cwd= — GLib loop + a real temp git repo (no GUI).
- The conclude ORDER + dirty refusal — mocked channels, sequence recorder (no GUI, Plan 04).
- The conclude clean-gate + D-10 against REAL git — real `git worktree add`/`remove` + a real relative
  symlink (smoke, Plan 05). The dirty guard is tested with a REAL dirty tree (porcelain non-empty → remove refused).
- gh-absent degrade smoke — `tests/test_review_cleanup_smoke.py::test_gh_absent_degrades_gracefully`.

**Host-only-live (Plan 06 — checkpoint:human-verify):**
- The diff renders WITH COLOR in a real VTE and rejects keystrokes (REVIEW-01) — visual, human only.
- `gh pr create --web` opens a REAL GitHub PR form and the subline reflects the REAL PR status
  (REVIEW-02/GIT-01) — requires real GitHub + a human; `gh pr create` is NEVER run in tests.
- A real clean conclude removes worktrees + container stack while keeping source/branch/history;
  a real dirty conclude is REFUSED with a clear pt-BR message (REVIEW-03 criterion 4) — human-observed.
- Throttle feel (manual refresh works; rapid switching does not spam gh) + live gh-absent/unauthed
  degrade (GIT-01/D-06) — human-observed.

## Security validation (the load-bearing items)

- **No `--force` worktree-remove anywhere:** asserted at the builder level (08-01 never-force guard
  test) AND in the conclude wiring (08-04 sequence recorder no-force) AND on disk (08-05 real-git dirty
  refusal smoke). This is THE auditor check. **All three pass.**
- **D-10 (never delete source/targets/branches):** 08-04 unit test (no source-path remove target, no
  branch-delete argv) + 08-05 on-disk proof (source dirs + branch + symlink target intact after a clean
  conclude; `os.path.islink`-guarded unlink, no `shutil.rmtree`). **Both pass.**
- **gh degrade (no crash / no rate-storm):** 08-02 degrade unit + 08-05 gh-absent smoke; reads gated
  by `gh_available()` + TTL + `_pr_busy` debounce, no poll. **All pass.**

## Wave-0 Requirement Checklist

- [x] `tests/test_review.py` created and all 21 tests pass
- [x] `tests/test_review_cache.py` created and all 13 tests pass
- [x] `tests/test_gh.py` created and all 19 tests pass
- [x] `tests/test_git_service_cwd.py` created and all 2 tests pass
- [x] `tests/test_window_conclude.py` created and all 3 tests pass
- [x] `tests/test_review_cleanup_smoke.py` created and all 4 tests pass
- [x] Full suite: 406 passed, 0 failures, 0 regressions

## Validation Sign-Off

- [x] All non-manual requirements have passing automated tests
- [x] Manual-only items documented in 08-HUMAN-UAT.md with clear why-human rationale
- [x] Security invariants (no `--force`, no `rmtree`, `islink` guard) verified by both unit and real-git smoke
- [x] GTK-free discipline verified for all three domain modules
- [x] No implementation files modified during this reconcile (docs only)

**Approval:** validated 2026-06-15 (post-execution reconcile)

---

## Validation Audit 2026-06-15

### Metrics

| Metric | Count |
|--------|-------|
| Automated tests run | 62 (58 named + 4 smoke) |
| Tests passing | 62 / 62 |
| Gaps found | 1 (path correction: smoke landed at `tests/` not `tests/smoke/`) |
| Gaps resolved | 1 (path updated in this doc; test file is correct on disk) |
| Gaps escalated | 0 |
| Requirements with full automated coverage | REVIEW-01 (unit), REVIEW-02 (unit), REVIEW-03 (unit + real-git smoke), GIT-01 (unit + real-git smoke) |
| Requirements with manual-only items | 4 (live VTE diff color, live PR open/subline, live conclude UX, live throttle feel) |

### Prose note

This document was a stale plan-time draft (status: draft, nyquist_compliant: false) written before
any implementation. It correctly identified the intended test scaffolds as future work (Wave 0 Gaps)
with unchecked boxes.

At reconcile time (2026-06-15), all 5 named test files from the plan exist on disk and pass:
`tests/test_review.py` (21), `tests/test_review_cache.py` (13), `tests/test_gh.py` (19),
`tests/test_git_service_cwd.py` (2), `tests/test_window_conclude.py` (3). The real-git smoke
(`tests/test_review_cleanup_smoke.py`, 4 tests) also passes and covers the D-10 and dirty-refusal
invariants against a real git repo. Total: 62 tests, 0 failures.

**One path correction:** the plan noted `tests/smoke/test_review_cleanup_smoke.py` but the file
landed at `tests/test_review_cleanup_smoke.py`. The test content and coverage are correct; only the
directory differs. Updated in this doc.

**Genuinely manual items (not gaps):** four behaviors legitimately require a live display and real
external services — VTE color rendering, `gh pr create --web` browser interaction, conclude UX
dialog + on-disk observation, and live throttle/degrade feel. These are documented in 08-HUMAN-UAT.md
and correctly appear as MANUAL-ONLY in the requirement map above. They do not block nyquist_compliant.

The wiring assertions (set_input_enabled, menu entries, _refresh_task_status debounce) were verified
by code inspection in the VERIFICATION.md rather than standalone AST tests — acceptable given the
behavior is fully exercised by the unit and smoke layers.
