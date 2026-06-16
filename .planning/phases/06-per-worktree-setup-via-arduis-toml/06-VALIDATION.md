---
status: validated
nyquist_compliant: true
wave_0_complete: true
validated: 2026-06-15
phase: 06-per-worktree-setup-via-arduis-toml
---

# Phase 6 — Validation Architecture

**Derived from:** 06-RESEARCH.md §"Validation Architecture" (nyquist_validation: ON).
**Baseline:** 240 unit tests passing before this phase.

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Interpreter | `/tmp/arduis-venv/bin/python` (system-site-packages venv per MEMORY arduis-dev-environment) |
| Quick run (Wave 1) | `/tmp/arduis-venv/bin/python -m pytest tests/test_repoconfig.py tests/test_trust.py -x -q` |
| Full suite | `/tmp/arduis-venv/bin/python -m pytest tests/ -q` |
| Headless GTK | `gtk4-broadwayd :96 &` then `GDK_BACKEND=broadway BROADWAY_DISPLAY=:96 <python> tests/smoke/test_setup_feed_smoke.py` (do NOT override XDG_RUNTIME_DIR) |

## Phase Requirements → Test Map

| Req / Criterion | Behavior | Test Type | Automated Command | File | Status | Test Count |
|-----------------|----------|-----------|-------------------|------|--------|------------|
| ENV-01 | Missing/garbage/empty `.arduis.toml` → `RepoSetup([])` (no-op default, criterion 1) | unit | `pytest tests/test_repoconfig.py -x` | `tests/test_repoconfig.py` | ✅ | 5 tolerance tests |
| ENV-01 | Valid `[setup].commands` parsed in order; non-str/blank dropped; unknown keys ignored | unit | `pytest tests/test_repoconfig.py -x` | `tests/test_repoconfig.py` | ✅ | 4 parsing tests |
| ENV-02 | `setup_feed_bytes` → bytes, cd-guarded, newline-joined (not &&-chained), order preserved | unit | `pytest tests/test_repoconfig.py -x` | `tests/test_repoconfig.py` | ✅ | 5 feed-bytes tests + 1 GTK-free assertion (15 total in file) |
| crit-4 | `setup_hash` stable for identical lists; changes on edit/add/remove/reorder | unit | `pytest tests/test_trust.py -x` | `tests/test_trust.py` | ✅ | 6 hash stability/change tests |
| crit-4 | Trust list tolerant read (missing/garbage → {}, fail-closed) + atomic round-trip + `is_trusted` exactness | unit | `pytest tests/test_trust.py -x` | `tests/test_trust.py` | ✅ | 12 round-trip/tolerant-read/atomic/best-effort/GTK-free tests (19 total in file) |
| ENV-02 / crit-2/3 | Setup feeds into the SHELL terminal (t1, not agent t0), CREATE-only, login shell, cd-guard | smoke + live UAT | `tests/smoke/test_setup_feed_smoke.py` + 06-HUMAN-UAT.md | `tests/smoke/test_setup_feed_smoke.py` | ✅ (mechanism automated 7/7; live pane render MANUAL-ONLY) | 7 smoke checks |
| crit-4 | Trust dialog shows exact commands; accept persists hash + feeds; already-trusted silent; changed-hash re-prompts; skip persists nothing | smoke (mechanism) + live UAT (dialog render) | `tests/smoke/test_setup_feed_smoke.py` + 06-HUMAN-UAT.md | `tests/smoke/test_setup_feed_smoke.py` | ✅ (mechanism proven; dialog render/click MANUAL-ONLY) | included in 7 smoke checks |
| crit-1 | Absent-file create behaves exactly as today (no dialog, no feed) | smoke + live UAT | `tests/smoke/test_setup_feed_smoke.py` | `tests/smoke/test_setup_feed_smoke.py` | ✅ | included in 7 smoke checks |

## Wave 0 Gaps (test files that MUST be created first)

- [x] `tests/test_repoconfig.py` — ENV-01 tolerant parse + ordering + drop-blank/non-str + unknown-key forward-compat + `setup_feed_bytes` cd-guard/bytes/empty-list. **Created in Plan 06-01, Task 1. 15 tests, all passing.**
- [x] `tests/test_trust.py` — `setup_hash` stability/change (edit/add/remove/reorder) + tolerant fail-closed read + atomic round-trip + `is_trusted` exactness + preserve-prior + overwrite-changed + path-key round-trip + best-effort no-raise. **Created in Plan 06-01, Task 2. 19 tests, all passing.**
- [x] `tests/smoke/test_setup_feed_smoke.py` — headless broadway acceptance (absent-file no-op, trusted→silent feed into shell, agent never fed setup, changed-hash re-prompt, CREATE-only, real trust list untouched). **Created in Plan 06-03, Task 1. 7/7 checks PASS.**
- [x] `.planning/phases/06-per-worktree-setup-via-arduis-toml/06-HUMAN-UAT.md` — live checklist for the 4 success criteria. **Created in Plan 06-03, Task 2.**

## Sampling Rate

- **Per task commit:** `/tmp/arduis-venv/bin/python -m pytest tests/test_repoconfig.py tests/test_trust.py -x -q`
- **Per wave merge:** `/tmp/arduis-venv/bin/python -m pytest tests/ -q` (must stay ≥ 240 + new, zero regression)
- **Phase gate:** full suite green + `tests/smoke/test_setup_feed_smoke.py` green (7/7) + the live 06-HUMAN-UAT.md criteria confirmed before `/gsd-verify-work`. **All automated gates passed.**

## Security Validation (this phase IS a security feature — criterion 4)

| ASVS | Control | Validated by | Status |
|------|---------|--------------|--------|
| V1 Trust Boundaries | repo `.arduis.toml` treated as UNTRUSTED; content-pinned consent gate | trust dialog (06-02) + smoke trusted/changed checks (06-03) | ✅ |
| V5 Input Validation | tolerant parse; only `[setup].commands` strings; never crash | `test_repoconfig.py` garbage/wrong-type cases (06-01) | ✅ |
| V4 Access Control | no setup runs without per-repo, per-content approval | `is_trusted` gate + dialog accept/skip (06-01/06-02) | ✅ (mechanism proven; dialog interaction MANUAL-ONLY) |
| V6 Cryptography (partial) | `hashlib.sha256` content fingerprint (not a secret) | `test_trust.py` hash stability/change (06-01) | ✅ |

**Fail-closed invariant:** a missing/corrupt trust list → `{}` → everything re-prompts (never fail-open). Pinned by `test_trust.py` tolerant-read cases (`test_load_missing_is_empty`, `test_load_garbage_is_empty`, `test_load_no_trusted_table_is_empty`, `test_load_trusted_not_a_table_is_empty`).

## Validation Sign-Off

- [x] Wave 0: all required test files created and passing
- [x] Unit tests: 34/34 passing (`tests/test_repoconfig.py` 15 + `tests/test_trust.py` 19)
- [x] Full suite: 274 passed (240 baseline + 34 new), zero regressions
- [x] Smoke: `tests/smoke/test_setup_feed_smoke.py` 7/7 checks PASS
- [x] ENV-01 covered: tolerant `.arduis.toml` parse with sensible defaults, fail-safe on absent/garbage/wrong-type
- [x] ENV-02 covered: `setup_feed_bytes` cd-guard, newline-join, bytes, order preserved; shell t1 targeting proven by smoke
- [x] crit-4 covered: `setup_hash` stability/change (6 tests), fail-closed trust list (5 tests), atomic round-trip (7 tests)
- [x] GTK-free domain modules: verified by `test_repoconfig_is_gtk_free` and `test_trust_is_gtk_free`
- [x] Manual-only items correctly scoped to 06-HUMAN-UAT.md (live dialog render, live pane output, shim resolution)

**Approval:** validated 2026-06-15 (post-execution reconcile)

---

## Validation Audit 2026-06-15

### Metrics

| Metric | Count |
|--------|-------|
| Gaps found (stale plan-time placeholders) | 4 (Wave-0 checkboxes unchecked, frontmatter `status: draft`, `nyquist_compliant: false`, per-task map had no Status/File-Exists columns) |
| Resolved | 4 (all checked against live test run and SUMMARY/VERIFICATION evidence) |
| Escalated | 0 |

### Audit Note

This document was a stale **plan-time draft** generated before execution began. It reflected
intended test architecture, not delivered state. The phase shipped on 2026-06-13 (Plans 01–03
complete; see 06-01-SUMMARY.md, 06-03-SUMMARY.md, 06-VERIFICATION.md).

**What is genuinely automated (34 unit + 7 smoke = 41 checks):**

- `tests/test_repoconfig.py` (15 tests): full ENV-01 tolerant parse coverage (absent, garbage
  TOML, no `[setup]` table, `[setup]` not a table, `commands` not a list, empty list), ordered
  parse, blank/non-str drop, unknown-key forward-compat, and all `setup_feed_bytes` shape
  cases (cd-guard, newline-join not &&-chain, bytes type, space-in-path quoting, raw commands).
- `tests/test_trust.py` (19 tests): `setup_hash` SHA-256 format + stability/change for all
  mutation kinds (edit, add, remove, reorder), `load_trusted` fail-closed for all failure modes,
  `record_trust` round-trip exactness + prior-entry preservation + hash overwrite + valid TOML
  output + path-key special-char round-trip + parent-dir creation + OSError best-effort.
- `tests/smoke/test_setup_feed_smoke.py` (7 checks): headless broadway acceptance — absent-file
  no-op, first-run untrusted, `record_trust`→silent feed into shell `t1` with exact cd-guarded
  bytes, agent terminal `t0` never fed, changed hash re-prompts, real trust list untouched.

**What remains manual-only (correct; does NOT block nyquist_compliant):**

- Live VTE pane rendering: eyeballing that setup commands visibly scroll in the shell pane after
  dialog accept (criterion 2). `Adw.AlertDialog` cannot be driven headlessly via broadway.
- Login-shell shim resolution (criterion 3): requires a real machine with nvm/asdf/mise installed.
- Trust dialog render and button interaction (criterion 4 — security crux): the user must see the
  literal commands in the dialog before authorizing. The trust mechanism (hash, record, gate) is
  headless-proven; only the GTK render + click is live-only.
- Failing-setup no-crash (criterion 5 / resilience): requires real command execution in a live
  terminal.

These items are tracked in `06-HUMAN-UAT.md`.
