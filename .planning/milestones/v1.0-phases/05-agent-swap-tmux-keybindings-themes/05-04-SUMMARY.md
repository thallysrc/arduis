---
phase: 05-agent-swap-tmux-keybindings-themes
plan: 04
type: execute
status: complete
wave: 3
requirements: [AGENT-01, UI-01, UI-02]
---

# Plan 05-04 Summary: Phase Acceptance

## Outcome

Phase-5 acceptance executed in **autonomous mode** (user delegated decisions, AFK). Task 1
(headless smoke) ran for real and is committed at `tests/smoke/test_theme_switch_smoke.py`;
Task 2 (live human-verify checkpoint) was auto-resolved by persisting the live checklist to
`05-HUMAN-UAT.md` and proving everything provable without a display. No source modified beyond
the smoke file; the real `~/.config/arduis/arduis.toml` was never touched.

## Task 1 — Headless broadway smoke (DONE)

- **Full suite:** `240 passed` (172 pre-phase + 68 Phase-5: 13 themes + 55 config/keymap). Green.
- **Broadway smoke** (`tests/smoke/test_theme_switch_smoke.py`, sandbox HOME + synthetic git
  project, broadwayd `:95`, killed in finally): **9/9 checks PASS**.

| Check | Result |
|-------|--------|
| `[agent] command` from sandbox arduis.toml == "aider" | PASS |
| `[keys.bindings] "q"="zoom"` resolves into `win._keymap` | PASS |
| theme switch flips `win._current_theme` to nord | PASS |
| theme switch REPLACES the CssProvider (new object — Pitfall 1) | PASS |
| repeated dracula→nord→dracula→nord switches: no crash, provider keeps changing | PASS |
| terminal built after switch is born in the active theme (Pitfall 2) | PASS |
| `agent_feed_bytes("aider")` starts with `b"aider"` (AGENT-01) | PASS |
| real `~/.config/arduis/arduis.toml` untouched (T-05-08) | PASS |
| start theme was dracula (default) | PASS |

The smoke runs a real `ArduisWindow` under broadway and inspects the live seams
(`_apply_theme`, `_css_provider` identity, `_current_theme`, `_make_terminal`, `_agent_config`,
`_keymap`) — proving the switch mechanism + configured-feed/dispatch wiring without a display.

## Task 2 — Live acceptance (auto-resolved; persisted as UAT)

Per the 03.2/04 precedent, the live checklist is persisted to `05-HUMAN-UAT.md` (status:
partial) so it surfaces in `/gsd-progress` and `/gsd-verify-work`. Of 5 items: items 2/3/4 are
headless-proven for their wiring and await live confirmation; items 1 and 5 are live-only.

**Load-bearing item:** Criterion 3 — the C-Space prefix arming app-scoped under a REAL Wayland
session (`$XDG_SESSION_TYPE=wayland`, not XWayland). Research established this is satisfied by the
existing capture-phase controller (app-internal propagation, not a compositor grab), so it is a
verification, not new code — but it needs a human on a Wayland session to confirm.

## Deviations / observations recorded

- **Assumption A1** (Nord/Solarized/Gruvbox hex palettes training-recalled, not re-fetched — the
  Nord spec URL 404'd during planning): cosmetic, guarded by the 05-01 valid-hex unit invariant;
  flagged for live eyeballing in the UAT.
- **Assumption A2 / Pitfall 3** (C-Space collision): configurable prefix (`[keys] prefix`) is the
  mitigation; flagged for the user to rebind if their GNOME/zsh grabs C-Space.
- **Checkpoint auto-resolution:** the human-verify gate was satisfied by headless evidence +
  persisted UAT rather than a blocking wait, because the user explicitly delegated and is AFK.

## Self-Check: PASSED

Suite green (240), smoke 9/9, real config untouched, no process orphans, smoke file + UAT +
SUMMARY written, no source changes beyond the committed smoke.
