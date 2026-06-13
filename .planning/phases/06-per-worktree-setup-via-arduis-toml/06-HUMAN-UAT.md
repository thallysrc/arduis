---
status: partial
phase: 06-per-worktree-setup-via-arduis-toml
source: [06-03-PLAN.md]
started: 2026-06-13T12:50:40-03:00
updated: 2026-06-13T12:50:40-03:00
---

## Current Test

[awaiting human testing on a real display]

## Tests

### 1. Criterion 1 — reads .arduis.toml per repo, no-op when absent
expected: A repo WITHOUT `.arduis.toml` creates a task exactly as today — no dialog, no setup feed, no error. A repo WITH `[setup] commands=[...]` is read correctly.
result: passed headless (live confirmation pending) — smoke proved absent-file is a strict no-op (neither terminal fed) and a present `[setup]` parses. Live: confirm a real no-file repo is unaffected.

### 2. Criterion 2 — setup runs automatically on creation, visibly in a pane
expected: Create a task in a repo with `[setup] commands = ["npm install", ...]`; after trusting, the commands run VISIBLY in the task's shell pane (you see `npm install` scrolling).
result: passed headless for the feed mechanism (live confirmation pending) — smoke proved the bytes `cd '<wt>' && \n npm install ...` are fed into the SHELL terminal `t1` (never the agent `t0`). Live: eyeball the commands actually running in the pane.

### 3. Criterion 3 — setup runs via the host login shell (shims resolve)
expected: Setup commands resolve `npm`/`docker`/nvm/asdf/mise shims because they run in the same `zsh -l -i` login shell as the agent (fed into the existing shell terminal, not a separate subprocess).
result: passed headless for the path (live confirmation pending) — the feed targets the existing `zsh -l -i` VTE terminal (inherits login env for free). Live: confirm a shim-dependent command (e.g. `node -v` under nvm) resolves.

### 4. Criterion 4 — trust gate (trusted-repo-only, confirmation on first run) [THE security item]
expected: First task in a repo with `[setup]` → ONE consolidated dialog showing the EXACT commands grouped per repo, "Confiar e rodar" / "Pular". Accept → commands run + trust persists (`~/.config/arduis/trusted_setups.toml`). Next create of the same unchanged setup → runs silently (no dialog). EDIT the repo's `.arduis.toml` (change a command) → the dialog RE-PROMPTS (content-hash changed). "Pular" → worktree created, nothing run, nothing persisted.
result: partially headless (live confirmation REQUIRED) — smoke proved the trust MECHANISM: first run untrusted, record_trust → silent feed, a CHANGED setup re-prompts (hash not path), real trust list untouched. The dialog RENDER + click-accept showing exact commands is live-UAT only. MUST confirm the dialog appears with the literal commands before they run.

### 5. No orphans / setup failure doesn't crash
expected: A failing setup command (e.g. `npm install` in a non-node repo) shows its error in the pane but does NOT crash task creation or block the agent. Closing the app leaves no orphans.
result: [pending — live] — D-06 wraps the feed in try/except (a feed error never breaks creation); the live shell shows failures naturally. Confirm with a deliberately-failing setup.

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

(Note: items 1/2/3 are headless-proven for their mechanism and await live confirmation; item 4's trust mechanism is proven headless but the DIALOG render+accept showing exact commands is the load-bearing live gate; item 5 is live-only.)

## Gaps
