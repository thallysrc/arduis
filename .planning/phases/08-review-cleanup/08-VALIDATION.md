# Phase 8: Review + Cleanup — Validation Strategy

**Nyquist validation: ON.** Every requirement maps to an automated test (unit/smoke) plus, where a
human must observe (color, browser PR, real conclude), a live UAT step. The conclude clean-gate
(criterion 4 — never destroy uncommitted work) is the security item and is covered TWICE: a mocked
order/refusal unit test (Plan 04) AND a real-git dirty-tree refusal smoke (Plan 05) AND a human
dirty-conclude step (Plan 06).

## Executor environment

- **Unit/smoke runner:** `/tmp/arduis-venv-ab12/bin/python -m pytest tests/ -q` (baseline ~344 green).
- **Headless GUI:** `gtk4-broadwayd :9N` + `GDK_BACKEND=broadway` (per MEMORY arduis-dev-environment).
  Do NOT override `XDG_RUNTIME_DIR`. Smoke SKIPS exit-0 if broadwayd absent.
- **Live host:** git 2.43 + gh 2.93 authed (`thallysrc`, ssh). Real `gh`/`git diff` are best as
  argv/parse asserts + a real-git dirty-tree fixture under sandbox `$HOME` for the conclude clean-gate.
- **NEVER run `gh pr create` in any test** — argv-shape assertion only; the real PR is a human UAT step.

## Requirement → Test Map

| Req ID | Behavior | Test Type | Automated Command | Plan / File |
|--------|----------|-----------|-------------------|-------------|
| REVIEW-01 | `argv_diff`/`argv_diff_stat` shape | unit | `pytest tests/test_review.py -x -q` | 08-01 / tests/test_review.py |
| REVIEW-01 | read-only diff leaf wired (`set_input_enabled(False)`, per-repo "Ver diff") | smoke + ast | `pytest tests/smoke/test_review_cleanup_smoke.py` + ast check | 08-03 / window.py, 08-05 |
| REVIEW-01 | diff renders WITH COLOR + rejects typing | live UAT | manual (08-HUMAN-UAT step 2) | 08-06 |
| REVIEW-02 | `parse_pr_view` json shape + garbage guard | unit | `pytest tests/test_gh.py -x -q` | 08-02 / tests/test_gh.py |
| REVIEW-02 | `argv_pr_create_web()` shape (the ONE allowed write — never executed) | unit | `pytest tests/test_gh.py -x -q` | 08-02 |
| REVIEW-02 | 'Abrir PR (web)' wired; gh-gated | smoke + ast | smoke + ast check | 08-03, 08-05 |
| REVIEW-02 | real PR create + real status in subline | live UAT | manual (08-HUMAN-UAT step 4) | 08-06 |
| REVIEW-03 | `parse_porcelain_clean` true/false (clean/dirty) | unit | `pytest tests/test_review.py -x -q` | 08-01 |
| REVIEW-03 | `argv_worktree_remove` NEVER contains `--force`/`-f` | unit (guard) | `pytest tests/test_review.py -x -q` | 08-01 |
| REVIEW-03 | conclude ORDER: kill→down→check→remove→prune + dirty REFUSAL | unit (sequence recorder, mocked) | `pytest tests/test_window_conclude.py -x -q` | 08-04 / tests/test_window_conclude.py |
| REVIEW-03 | real-git clean conclude removes worktrees, keeps source+branch+symlink-target (D-10); dirty REFUSED | smoke (real git) | `pytest tests/smoke/test_review_cleanup_smoke.py` | 08-05 |
| REVIEW-03 | live clean vs dirty conclude (criterion 4) | live UAT | manual (08-HUMAN-UAT steps 6-7) | 08-06 |
| GIT-01 | `parse_ahead_behind` parses `"3\t2"`/garbage | unit | `pytest tests/test_review.py -x -q` | 08-01 |
| GIT-01 | `review_cache.is_fresh` TTL logic + ReviewCache | unit | `pytest tests/test_review_cache.py -x -q` | 08-01 |
| GIT-01 | gh exit-4 → "não autenticado"; absent → "ausente" (degrade) | unit | `pytest tests/test_gh.py -x -q` | 08-02 |
| GIT-01 | `run_git_async(cwd=...)` backward-compatible + real-cwd | unit (GLib loop + temp repo) | `pytest tests/test_git_service_cwd.py -x -q` | 08-02 / tests/test_git_service_cwd.py |
| GIT-01 | status subline + TTL + `_pr_busy` debounce + gh_available gate (no poll) | smoke + ast | smoke + ast check | 08-03, 08-05 |
| GIT-01 | throttle + degrade behave live | live UAT | manual (08-HUMAN-UAT steps 3, 5) | 08-06 |

## Wave 0 Gaps (test scaffolds to create — all in Wave 1/2/3 plans)

- [ ] `tests/test_review.py` — argv builders, porcelain clean, **never-force guard**, ahead/behind (08-01)
- [ ] `tests/test_review_cache.py` — TTL `is_fresh` + ReviewCache round-trip + GIT/GH TTL constants (08-01)
- [ ] `tests/test_gh.py` — pr-view parse + garbage guard, degrade (absent/exit-4), subline formatters (08-02)
- [ ] `tests/test_git_service_cwd.py` — `run_git_async` cwd= signature + real-temp-repo cwd proof (08-02)
- [ ] `tests/test_window_conclude.py` — conclude order + dirty refusal + never-force + D-10 (mocked channels) (08-04)
- [ ] `tests/smoke/test_review_cleanup_smoke.py` — broadway acceptance: menu, real-git clean/dirty conclude, D-10 on-disk, gh-absent degrade (08-05)
- [ ] Real-temp-repo + real-relative-symlink fixture for the conclude clean-gate / D-10 smoke (08-05; built inline in the smoke harness, mirroring tests/smoke/test_topbar_chips_smoke.py)

## Headless vs Host-only-live split

**Headless / automated (Plans 01-05):**
- ALL GTK-free argv builders + parsers + cache TTL (review/gh/review_cache) — pure unit, no gi.
- `run_git_async` cwd= — GLib loop + a real temp git repo (no GUI).
- The conclude ORDER + dirty refusal — mocked channels, sequence recorder (no GUI, Plan 04).
- The conclude clean-gate + D-10 against REAL git — sandbox-`$HOME` temp fixtures + real
  `git worktree add`/`remove` + a real relative symlink (broadway smoke, Plan 05). The dirty guard
  is tested with a REAL dirty tree (porcelain non-empty → remove refused).
- Menu-entry presence + gh-absent degrade + gh argv shapes — broadway smoke (Plan 05).

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
  test) AND in the conclude wiring (08-04 ast check `--force`/`-f` absent + recorder test no-force)
  AND on disk (08-05 real-git dirty refusal). This is THE auditor check.
- **D-10 (never delete source/targets/branches):** 08-04 unit test (no source-path remove target, no
  branch-delete argv, real symlink target survives) + 08-05 on-disk proof (source dirs + branch +
  symlink target intact after a clean conclude; `os.path.islink`-guarded unlink, no `shutil.rmtree`).
- **gh degrade (no crash / no rate-storm):** 08-02 degrade unit + 08-05 gh-absent smoke; reads gated
  by `gh_available()` + TTL + `_pr_busy` debounce, no poll.
