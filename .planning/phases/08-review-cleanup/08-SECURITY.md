---
phase: 08-review-cleanup
threats_open: 0
threats_total: 18
threats_closed: 18
asvs_level: 1
audited: 2026-06-15
verdict: SECURED
---

# Security Audit — Phase 08 (review-cleanup)

Verification of every threat declared in the Phase-8 PLAN.md `<threat_model>` blocks
(plans 08-01..08-05; T-08-01 .. T-08-18) against the implemented code. Implementation
files are read-only here — this audit reports presence/absence of each declared
mitigation. **All 18 threats closed. 406/406 tests pass.**

## Trust Boundary (the destructive surface)

The phase's high-stakes surface is the **"Concluir task"** destructive teardown. Two
operations can delete on-disk state, and both are scoped + guarded:

1. **`git worktree remove`** — scoped to the task's worktree dirs, run with `cwd=`SOURCE
   member repo, **never `--force`/`-f`**. Git's own refusal to remove a dirty/locked
   worktree is the safety; the app refuses BEFORE git is even invoked when any repo is
   dirty (all-or-nothing porcelain gate).
2. **Symlink unlink** — `os.unlink` only on `os.path.islink(dst)` targets (the LINK,
   never the target), followed by `os.rmdir` only-if-empty. No `shutil.rmtree`, no
   `realpath`+delete.

Everything else in the phase is read-only: `git diff`/`status`/`rev-parse`/`rev-list`
and `gh pr view --json`. The ONLY write to the outside world is `gh pr create --web`
(browser-driven, AFK-safe). Inputs (branch names, worktree dirs) cross into git/gh as
discrete LIST-form argv elements through `HostRunner`/`run_git_async` — no shell, no
`shell=True`, nothing string-joined. git/gh output is displayed only — never eval'd,
never used to build a path or command.

## Threat Verification

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-08-01 | Tampering/EoP (branch→git argv) | mitigate | CLOSED | review.py: all builders return LIST argv, repo/dir/branch discrete (`argv_diff`/`argv_status_porcelain`/`argv_worktree_remove` etc. L33-96); no `shell=True` in src (grep clean) |
| T-08-02 | Tampering/data loss (force-remove) | mitigate | CLOSED | review.py:63-71 `argv_worktree_remove` omits `--force`/`-f`; pinned by `tests/test_review.py:73 test_argv_worktree_remove_never_emits_force` incl. adversarial `/tasks/--force/b` input |
| T-08-03 | DoS self (unbounded reads) | mitigate | CLOSED | review_cache.py `is_fresh`/`ReviewCache.fresh_payload` L25-61; TTL consts GIT_TTL_S=30 / GH_TTL_S=120 L21-22 |
| T-08-04 | Tampering/EoP (branch→gh argv) | mitigate | CLOSED | gh.py:72-80 `argv_pr_view` LIST argv, branch discrete element; no shell |
| T-08-05 | Injection (gh JSON as code/path) | mitigate | CLOSED | gh.py:95-110 `parse_pr_view` json.loads + dict shape-guard, RAISES on garbage; window.py:3186-3189 caller wraps `except (ValueError, TypeError)`; output displayed only via `format_pr_subline` |
| T-08-06 | DoS self (gh rate-limit) | mitigate | CLOSED | window.py:3158 `gh_available()` short-circuit; :3162 TTL `fresh_payload`; :3168-3170 `_pr_busy` debounce; degrade_message exit-4 static (gh.py:124-132); no poll |
| T-08-07 | Tampering (the ONE write) | accept | CLOSED | gh.py:83-90 `argv_pr_create_web` = `gh pr create --web` only; documented as sanctioned write (see Accepted Risks); never executed in tests |
| T-08-08 | EoP (diff leaf input→child) | mitigate | CLOSED | window.py:3061 `terminal.set_input_enabled(False)` set BEFORE spawn |
| T-08-09 | Injection (branch→spawned diff cmd) | mitigate | CLOSED | window.py:3078-3089 spawn argv is fixed LIST `["zsh","-l","-i","-c","git --no-pager diff; exec zsh -i"]` with `cwd=worktree_dir` — branch never interpolated |
| T-08-10 | DoS self (status reads) | mitigate | CLOSED | window.py:3138-3176 gate→TTL→`_pr_busy` debounce; auto-read only on create (:1796/:2857) + row-activate; no poll tick |
| T-08-11 | Tampering (the ONE write, UI) | accept | CLOSED | window.py:1449-1450 'Abrir PR (web)' appended only when `gh.gh_available()`; :3253 runs `argv_pr_create_web`; see Accepted Risks |
| T-08-12 | Tampering/data loss (force dirty) | mitigate | CLOSED | window.py:3328-3370 `_conclude_clean_gate` ALL-OR-NOTHING: any dirty repo → refuse, `return` before `_conclude_remove_worktrees` — zero remove argv when dirty; pinned by `tests/test_window_conclude.py:75 test_dirty_repo_refuses_whole_conclude_no_remove` + smoke real-git L60 |
| T-08-13 | Tampering/data loss (source/target/branch) | mitigate | CLOSED | window.py:3391-3428 remove runs `cwd=`SOURCE repo, targets only worktree dir; :3455-3482 symlink cleanup `os.path.islink` guard + `os.rmdir` empty-only; no `branch -d/-D`, no `shutil.rmtree`; smoke L43/L74 proves source+branch+symlink-target survive |
| T-08-14 | Tampering/lock (process pins worktree) | mitigate | CLOSED | window.py:3320-3326 fixed order kills agents (a) + container down (b) before remove (d); :3406-3417 git rc!=0 → STOP, no `--force` escalation |
| T-08-15 | EoP (branch/dir→git argv) | mitigate | CLOSED | window.py conclude uses review.py LIST builders via `run_git_async` (runner=HostRunner); no shell |
| T-08-16 | DoS (RAM leak — orphan stack) | mitigate | CLOSED | window.py:3324 `_container_down` (step b) runs before remove; self-guards no-op if isolation off |
| T-08-17 | Tampering test-time (smoke touches real repos) | mitigate | CLOSED | tests/test_review_cleanup_smoke.py: all fixtures under pytest `tmp_path` (`repo_and_worktree` L26); no host paths |
| T-08-18 | Tampering (accidental gh pr create in CI) | mitigate | CLOSED | smoke argv-asserts shape only; `gh pr create` never executed (L11 docstring + no invocation); gh-absent section PATH-stubbed L85 |

## Threat Flags (from SUMMARYs)

None. The 08-01..08-05 SUMMARY.md files contain no `## Threat Flags` section — the
executor detected no new attack surface beyond the registered threat model.

## Unregistered Flags

None.

## Accepted Risks

- **T-08-07 / T-08-11 — `gh pr create --web` (the ONE allowed write).** Opening a PR is
  roadmap-sanctioned (REVIEW-02). The `--web` form keeps it browser-driven and
  read-only-in-app afterward; the menu item appears only when `gh` is available; the
  builder is argv-shape-asserted and NEVER executed by any test. Accepted: arduis
  performs exactly one outbound write, scoped to PR creation via the user's authenticated
  `gh`, with the destructive surface unchanged.

## ASVS Posture

No `<config>` block (asvs_level/block_on) was supplied; defaulting to **ASVS Level 1**.
The applicable categories for this phase are injection-class (V5): all git/gh invocation
is LIST-form argv with discrete elements through a no-shell runner, and all command/JSON
output is display-only. No authentication, session, or crypto surface is introduced.
