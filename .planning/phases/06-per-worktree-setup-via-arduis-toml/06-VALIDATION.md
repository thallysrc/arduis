# Phase 6 — Validation Architecture

**Derived from:** 06-RESEARCH.md §"Validation Architecture" (nyquist_validation: ON).
**Baseline:** 240 unit tests passing before this phase.

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Interpreter | `/tmp/arduis-venv-ab12/bin/python` (system-site-packages venv per MEMORY arduis-dev-environment) |
| Quick run (Wave 1) | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_repoconfig.py tests/test_trust.py -x -q` |
| Full suite | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/ -q` |
| Headless GTK | `gtk4-broadwayd :96 &` then `GDK_BACKEND=broadway BROADWAY_DISPLAY=:96 <python> tests/smoke/test_setup_feed_smoke.py` (do NOT override XDG_RUNTIME_DIR) |

## Phase Requirements → Test Map

| Req / Criterion | Behavior | Test Type | Automated Command | File | Plan |
|-----------------|----------|-----------|-------------------|------|------|
| ENV-01 | Missing/garbage/empty `.arduis.toml` → `RepoSetup([])` (no-op default, criterion 1) | unit | `pytest tests/test_repoconfig.py -x` | `tests/test_repoconfig.py` | 06-01 |
| ENV-01 | Valid `[setup].commands` parsed in order; non-str/blank dropped; unknown keys ignored | unit | `pytest tests/test_repoconfig.py -x` | `tests/test_repoconfig.py` | 06-01 |
| ENV-02 | `setup_feed_bytes` → bytes, cd-guarded, newline-joined (not &&-chained), order preserved | unit | `pytest tests/test_repoconfig.py -x` | `tests/test_repoconfig.py` | 06-01 |
| crit-4 | `setup_hash` stable for identical lists; changes on edit/add/remove/reorder | unit | `pytest tests/test_trust.py -x` | `tests/test_trust.py` | 06-01 |
| crit-4 | Trust list tolerant read (missing/garbage → {}, fail-closed) + atomic round-trip + `is_trusted` exactness | unit | `pytest tests/test_trust.py -x` | `tests/test_trust.py` | 06-01 |
| ENV-02 / crit-2/3 | Setup feeds into the SHELL terminal (t1, not agent t0), CREATE-only, login shell, cd-guard | smoke + live UAT | `<python> tests/smoke/test_setup_feed_smoke.py` + 06-HUMAN-UAT.md | `tests/smoke/test_setup_feed_smoke.py` | 06-02 / 06-03 |
| crit-4 | Trust dialog shows exact commands; accept persists hash + feeds; already-trusted silent; changed-hash re-prompts; skip persists nothing | smoke (mechanism) + live UAT (dialog render) | `<python> tests/smoke/test_setup_feed_smoke.py` + 06-HUMAN-UAT.md | `tests/smoke/test_setup_feed_smoke.py` | 06-02 / 06-03 |
| crit-1 | Absent-file create behaves exactly as today (no dialog, no feed) | smoke + live UAT | `<python> tests/smoke/test_setup_feed_smoke.py` | `tests/smoke/test_setup_feed_smoke.py` | 06-03 |

## Sampling Rate

- **Per task commit:** `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_repoconfig.py tests/test_trust.py -x -q`
- **Per wave merge:** `/tmp/arduis-venv-ab12/bin/python -m pytest tests/ -q` (must stay ≥ 240 + new, zero regression)
- **Phase gate:** full suite green + `tests/smoke/test_setup_feed_smoke.py` green (or clean SKIP) + the live 06-HUMAN-UAT.md criteria confirmed before `/gsd-verify-work`.

## Wave 0 Gaps (test files that MUST be created first)

- [ ] `tests/test_repoconfig.py` — ENV-01 tolerant parse + ordering + drop-blank/non-str + unknown-key forward-compat + `setup_feed_bytes` cd-guard/bytes/empty-list. **Created in Plan 06-01, Task 1.**
- [ ] `tests/test_trust.py` — `setup_hash` stability/change (edit/add/remove/reorder) + tolerant fail-closed read + atomic round-trip + `is_trusted` exactness + preserve-prior + overwrite-changed + path-key round-trip + best-effort no-raise. **Created in Plan 06-01, Task 2.**
- [ ] `tests/smoke/test_setup_feed_smoke.py` — headless broadway acceptance (absent-file no-op, trusted→silent feed into shell, agent never fed setup, changed-hash re-prompt, CREATE-only, real trust list untouched). **Created in Plan 06-03, Task 1.**
- [ ] `.planning/phases/06-per-worktree-setup-via-arduis-toml/06-HUMAN-UAT.md` — live checklist for the 4 success criteria. **Created in Plan 06-03, Task 2.**

## Security Validation (this phase IS a security feature — criterion 4)

| ASVS | Control | Validated by |
|------|---------|--------------|
| V1 Trust Boundaries | repo `.arduis.toml` treated as UNTRUSTED; content-pinned consent gate | trust dialog (06-02) + smoke trusted/changed checks (06-03) |
| V5 Input Validation | tolerant parse; only `[setup].commands` strings; never crash | `test_repoconfig.py` garbage/wrong-type cases (06-01) |
| V4 Access Control | no setup runs without per-repo, per-content approval | `is_trusted` gate + dialog accept/skip (06-01/06-02) |
| V6 Cryptography (partial) | `hashlib.sha256` content fingerprint (not a secret) | `test_trust.py` hash stability/change (06-01) |

**Fail-closed invariant:** a missing/corrupt trust list → `{}` → everything re-prompts (never fail-open). Pinned by `test_trust.py` tolerant-read cases.
