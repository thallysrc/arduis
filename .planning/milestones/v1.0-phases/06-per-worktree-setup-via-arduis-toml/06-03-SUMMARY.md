---
phase: 06-per-worktree-setup-via-arduis-toml
plan: 03
type: execute
status: complete
wave: 3
requirements: [ENV-01, ENV-02]
---

# Plan 06-03 Summary: Phase Acceptance

## Outcome

Phase-6 acceptance executed in **autonomous mode** (user delegated, AFK). Task 1 (headless
smoke) ran for real and is committed at `tests/smoke/test_setup_feed_smoke.py`; Task 2 (live
human-verify checkpoint) was auto-resolved by persisting the live checklist to `06-HUMAN-UAT.md`
and proving everything provable without a display. No source modified beyond the smoke file; the
real `~/.config/arduis/trusted_setups.toml` was never written.

## Task 1 — Headless broadway smoke (DONE)

- **Full suite:** `274 passed` (240 pre-phase + 34 Phase-6: 15 repoconfig + 19 trust). Green.
- **Broadway smoke** (`tests/smoke/test_setup_feed_smoke.py`, sandbox HOME + synthetic git
  project, broadwayd `:96`, killed in finally): **7/7 checks PASS**.

| Check | Result |
|-------|--------|
| trust-list path is sandboxed (inside the fake HOME) | PASS |
| ABSENT .arduis.toml → strict no-op (neither terminal fed) — criterion 1 | PASS |
| first run of a `[setup]` is UNTRUSTED (no silent feed) | PASS |
| after record_trust → feeds the SHELL terminal `feat:t1` with `cd '<wt>' && … npm install` | PASS |
| the AGENT terminal `feat:t0` is NEVER fed (Pitfall 2) | PASS |
| a CHANGED .arduis.toml (different commands → different hash) is NOT trusted — re-prompts | PASS |
| the real `~/.config/arduis/trusted_setups.toml` is untouched | PASS |

The smoke runs a real `ArduisWindow` under broadway and exercises `_run_repo_setups` +
`trust.record_trust`/`is_trusted` + the feed path, monkeypatching `feed_child` to capture the
exact bytes — proving the trust mechanism + feed-shape + agent-isolation without a display. The
`Adw.AlertDialog` render/click is the live-UAT half (can't be driven headlessly).

## Task 2 — Live acceptance (auto-resolved; persisted as UAT)

Per the 03.2/04/05 precedent, the live checklist is persisted to `06-HUMAN-UAT.md` (status:
partial). Of 5 items: 1/2/3 are headless-proven for their mechanism; item 4's trust mechanism is
headless-proven but the dialog render+accept showing the exact commands is the **load-bearing
live gate** (criterion 4 — the security control: the user must see the literal commands before
authorizing arbitrary repo-committed execution); item 5 is live-only.

## Deviations / observations recorded

- Wave 1 corrected the plan's `setup_feed_bytes` snippet (`shlex.quote` left ordinary paths bare,
  contradicting the documented `cd '<dir>' &&` byte contract) → deterministic POSIX single-quoting.
  TDD caught it; the byte shape is now locked and the smoke asserts it.
- **Checkpoint auto-resolution:** the human-verify gate was satisfied by headless evidence +
  persisted UAT rather than a blocking wait, because the user explicitly delegated and is AFK.

## Self-Check: PASSED

Suite green (274), smoke 7/7, real trust list untouched, no process orphans, smoke file + UAT +
SUMMARY written, no source changes beyond the committed smoke.
