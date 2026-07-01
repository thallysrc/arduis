---
status: partial
phase: 05-agent-swap-tmux-keybindings-themes
source: [05-04-PLAN.md]
started: 2026-06-13T12:18:06-03:00
updated: 2026-06-13T12:18:06-03:00
---

## Current Test

[awaiting human testing on a REAL Wayland display]

## Tests

### 1. Criterion 3 — C-Space prefix arms under REAL Wayland (THE locked gate)
expected: `echo $XDG_SESSION_TYPE` prints `wayland` (not `x11`/XWayland). With arduis focused: `C-Space h/j/k/l` moves pane focus, `C-Space z` zooms, `C-Space -` / `C-Space =` split. App-scoped, native Wayland. If C-Space collides with a GNOME/zsh binding, set `[keys] prefix = "ctrl+b"`, relaunch, confirm the new prefix arms.
result: [pending — live only] — the capture-phase controller is app-internal propagation (research: not a compositor grab, no inhibit protocol needed). MUST be confirmed on a real Wayland session.

### 2. Criterion 1 (AGENT-01) — configurable agent, Ctrl+C → shell → re-feed, no respawn
expected: default config opens an agent pane running `claude`; Ctrl+C exits claude and lands at the live zsh (same pane, scrollback intact); typing another agent or `C-Space a` launches in the SAME pane (no respawn). `[agent] command = "claude --model opus"` (or another agent) → that command is what runs.
result: passed headless (live confirmation pending) — smoke proved `agent_feed_bytes(configured command)` drives the feed (`b"aider"` from a fixture). The durable-shell / Ctrl+C / re-feed-no-respawn behavior is live-only.

### 3. Criterion 2 (UI-01) — tmux chords work and are configurable
expected: the chords above behave; editing `[keys.bindings]` and relaunching applies the override; a garbage binding is ignored (default stands).
result: passed headless (live confirmation pending) — smoke proved a fixture `[keys.bindings] "q"="zoom"` resolves into `win._keymap`. Live: confirm dispatch on a real display.

### 4. Criterion 4 (UI-02) — theme switch (UI + every VTE), persisted, section-preserving
expected: header "Tema" menu → Nord → BOTH app chrome (sidebar/header/pane-header, focus ring, branch, status dots) AND every open terminal re-color immediately (incl. a pane split/resumed AFTER the switch — born Nord). Cycle Dracula→Nord→Solarized Dark→Gruvbox Dark→Dracula: no drift/lag/crash (provider replaced, not stacked). Relaunch → reopens in the last theme; `[theme] name` matches and `[attention]/[agent]/[keys]` sections still intact.
result: partially headless (live confirmation pending) — smoke proved the runtime switch flips `_current_theme`, REPLACES the CssProvider (new object, no stacking) across repeated switches, and a terminal built after a switch is born in the active theme. Live: eyeball the actual colors (incl. the 3 non-Dracula palettes — Assumption A1) and confirm persistence + section preservation in the real config file.

### 5. No orphans on close
expected: close the app with agents running → no orphan zsh/claude (`ps -eo pgid,cmd | grep -i claude`).
result: [pending — live only] — teardown machinery unchanged from prior phases (no-orphan verified there); confirm with real agents.

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

(Note: items 2/3/4 are headless-proven for their wiring and await only live confirmation; items 1 and 5 are live-only. Criterion 3 under native Wayland is the load-bearing gate.)

## Gaps
