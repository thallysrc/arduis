---
status: partial
phase: 04-attention-detection-who-s-waiting
source: [04-05-PLAN.md]
started: 2026-06-13T11:32:09-03:00
updated: 2026-06-13T11:32:09-03:00
---

## Current Test

[awaiting human testing on a real display + real claude TUI]

## Tests

### 1. Consent dialog + user hooks preserved (D-02)
expected: First launch shows the pt-BR install dialog. Accept → `~/.claude/settings.json.arduis-backup` exists; your own hooks (GSD, notify-send) still fire in a claude session OUTSIDE arduis (env-guard: the arduis hook is a no-op without `ARDUIS_STATE_FILE`).
result: passed headless (live confirmation pending) — smoke proved backup creation, additive merge preserving the fixture's pre-existing Notification/Stop hooks, arduis entries for all 7 events, idempotent re-merge, and the REAL ~/.claude untouched. Live: confirm the dialog renders and outside-arduis hooks still fire.

### 2. Criterion 1+2 — status flips via hooks, dot in sidebar + pane (STATUS-01/02)
expected: Create a task. When claude is at its prompt → CIANO (ready). Send a prompt → VERDE (running). Ask for a command needing approval ("rode docker ps") → LARANJA in ≤1s, in both the sidebar row and the pane header.
result: passed headless (live confirmation pending) — smoke fed the REAL arduis_hook.py as a subprocess (permission_prompt → waiting/orange, PostToolUse → running/green, Stop → ready/cyan) and asserted the sidebar dot CSS class flipped each time. Live: confirm timing (≤1s) and pane-header dot against a real claude TUI.

### 3. [UAT-D03] SessionStart dot color
expected: The moment claude opens, BEFORE any prompt, the dot should be CIANO (ready), not VERDE (running). The plan implemented `SessionStart → ready` (per verified research) over the CONTEXT's "→running" line.
result: [pending] — if VERDE proves to be the correct/expected behavior in practice, record as a D-03 deviation and flip the hook map.

### 4. Criterion 3 (the gate) — no false orange on TUI redraw, clears on approve
expected: While claude streams a long response (TUI repainting), the dot NEVER goes orange without a real prompt. Approve the pending permission → orange clears to green immediately (PostToolUse).
result: partially headless (live confirmation REQUIRED) — the PostToolUse→running clear is proven in the smoke; "survives a TUI redraw with no false orange" is ONLY provable against a real claude TUI and is the phase's differentiator. MUST be confirmed live.

### 5. [UAT-A1] Pending approval not downgraded by idle_prompt
expected: Leave an approval pending >60s — orange must NOT be downgraded to ready/idle by an idle_prompt notification.
result: [pending] — `effective_status` keeps WAITING regardless of age while the pid is alive (unit-tested); live confirmation pending.

### 6. [UAT-A2] Esc-interrupt mid-response
expected: Press Esc mid-response — dot returns to cyan within ~60s via idle_prompt self-heal; record the real Stop behavior.
result: [pending] — live only.

### 7. Criterion 4 — desktop notification when unfocused (STATUS-03)
expected: Unfocus the window, provoke an approval prompt → desktop notification arrives; with the window FOCUSED, no notification. Bursts don't stack (replace-id per terminal).
result: [pending] — `should_notify` gate (waiting + unfocused, no re-fire) is unit-tested; libnotify wiring present (`_HAS_NOTIFY`). Live: confirm an actual notification appears unfocused and is suppressed focused. (Your personal notify-send may duplicate — Pitfall 10, accepted.)

### 8. Criterion 5 — auto-suspend + --continue resume (RAM-04)
expected: `~/.config/arduis/arduis.toml` with `[attention]\nauto_suspend_minutes = 1`; converse with an agent, leave it ready >1min → task auto-suspended (notification + "suspensa" subline, processes killed, RAM freed). Resume via the "Retomar" card → agent returns with `claude --continue` and the PREVIOUS CONVERSATION is intact. Manual hibernate/resume still opens a clean claude.
result: passed headless (live confirmation pending) — smoke proved a backdated calm task suspends (auto_suspended=True via the no-orphan hibernate path) and a running task at the same age never suspends (Pitfall 6); the AGENT_RESUME_FEED (`claude --continue`) contract is wired for auto-suspended tasks. Live: confirm the conversation actually survives `--continue` and the toml is read.

### 9. Degraded mode (D-13)
expected: Decline the dialog (or touch `~/.local/share/arduis/hooks_declined`): dot works via VTE bell ("esperando?" badge) + a visible, clickable "status limitado — instalar hooks?" hint that re-presents consent.
result: [pending] — bell/contents-changed connectability verified on a real Vte.Terminal in 04-04; live: confirm the badge + re-invite UX.

### 10. No orphans on close
expected: Close the app with agents running → no orphaned zsh/claude (`ps -eo pgid,cmd | grep -i claude`); status dir clean on next launch.
result: passed headless for the status-file half (cleanup on hibernate proven; startup wipe is wired) — live: confirm no process orphans after a real window close.

## Summary

total: 10
passed: 0
issues: 0
pending: 10
skipped: 0
blocked: 0

(Note: 5 of 10 items are headless-proven and await only live confirmation; 5 require a real claude TUI / display. Criterion 3 live confirmation is the load-bearing gate.)

## Gaps
