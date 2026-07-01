# Phase 04: Attention Detection (who's waiting) - Context

**Gathered:** 2026-06-12
**Status:** Ready for planning
**Mode:** Autonomous — the user delegated decisions ("tome as decisões por você mesmo enquanto estarei AFK"). Every decision below adopts the recommended default from 04-RESEARCH.md (HIGH-confidence research grounded in the installed Claude Code 2.1.175, the user's real `~/.claude/settings.json`, and local gi probes). Decisions are revisitable at UAT.

<domain>
## Phase Boundary

Solve the Core Value pillar — always knowing which agent is waiting for you — HOOKS-FIRST:
Claude Code hooks write per-terminal state files arduis watches; VTE `bell` + activity
timeout are the degraded fallback (user declines hook install). Sidebar rows are TASKS — a
task's status aggregates its agent terminals (any agent waiting → task waiting). Status
indicator in sidebar rows and pane headers; desktop notification (libnotify) + optional
sound when an agent enters waiting and the window is unfocused; idle tasks can be
auto-suspended (RAM-04, opt-in).

**Out of scope:** scraping the VTE buffer as a status signal (v2, non-Claude agents);
OSC 133/termprops (requires VTE 0.78+, our floor is 0.76 — verified); notification actions
(click-to-focus is nice-to-have, not required); per-agent custom commands (Phase 5).

</domain>

<decisions>
## Implementation Decisions

### Hook injection & consent
- **D-01:** ONE env-guarded, stdlib-only python3 hook script shipped by arduis and registered
  once at USER level (`~/.claude/settings.json`) via consent-gated ADDITIVE merge (dedupe,
  backup, idempotent). The script exits 0 unless `ARDUIS_STATE_FILE` is set, so it is a no-op
  for every claude the user runs outside arduis. arduis injects `ARDUIS_STATE_FILE` (+
  `ARDUIS_SESSION_META`) per terminal via the VTE spawn `envv` seam. Rejected: writing
  settings into the task folder (symlink_plan links the REAL project `.claude/` — would
  pollute the user's repo) and `--settings` in AGENT_FEED (breaks manual `claude` relaunch).
- **D-02:** Consent UX: first-launch `Adw.AlertDialog` (pt-BR) "Instalar" / "Agora não".
  Decline → degraded mode (bell + activity timeout) + subtle persistent hint; never silently
  write to the user's settings. Idempotence: if entries already present, no dialog.

### State model & files
- **D-03:** 5 states: `running / waiting / ready / idle / ended`. Event map: SessionStart→running,
  UserPromptSubmit→running, Notification(permission_prompt|elicitation_dialog)→waiting,
  Notification(idle_prompt)→only upgrades ready (never downgrades waiting), PostToolUse(+Failure)
  →running (clears waiting after approval — Pitfall 3), Stop→ready, SessionEnd→ended.
  IDLE is computed (ready + threshold), never derived from running (long tool calls).
- **D-04:** State files: atomic write+rename per TERMINAL under `$XDG_RUNTIME_DIR/arduis/status/`
  (fallback `~/.cache/arduis/status/`), keyed by terminal id; JSON payload includes state,
  timestamp, session pid for staleness checks (Pitfall 5: verify pid alive before trusting).
- **D-05:** Watching: `Gio.FileMonitor` on the status dir, GLib main loop only (no threads);
  time-based transitions (idle threshold, stale sweep) ride a coarse GLib timeout.

### Status surfacing
- **D-06:** Aggregation: a task's status = max-urgency over its AGENT terminals only
  (waiting > running > ready > idle); shell terminals never contribute (Pitfall 8).
  Dot colors extend the existing sidebar dots: waiting=orange, running=green,
  ready=cyan/blue, idle=grey-green, hibernated stays grey.
- **D-07:** Pane header shows the per-terminal status (agent terminals only); sidebar row
  shows the task aggregate. Both update from the same state store signal.

### Notifications & sound
- **D-08:** Notify on `waiting` ONLY in v1 (STATUS-03); `ready` notification is a config flag
  default-off. Only when the arduis window is unfocused (`is-active` property). Use libnotify
  (gir Notify 0.7, probed OK) — portal-friendly Gio.Notification rejected because arduis is
  not a portal app in v1 and Notify allows urgency/replace-id.
- **D-09:** Dedup with the user's OWN global Notification hook (they already notify-send):
  arduis notifications carry app identity + replace-id per terminal so a TUI burst doesn't
  stack; we do NOT suppress the user's hook (their file, their rule — Pitfall 10 accepted).
- **D-10:** Sound: config flag DEFAULT OFF. When on: try GSound (`message-new-instant`),
  fallback `Gdk.Display.beep()`. GSound listed as optional dep for Phase 9 packaging.

### Auto-suspend (RAM-04)
- **D-11:** Opt-in via NEW `~/.config/arduis/arduis.toml`: `[attention] auto_suspend_minutes = 30`
  (absent/0 = OFF — the default). Read with stdlib `tomllib` at startup.
- **D-12:** Auto-suspend = the EXISTING hibernate machinery (kills groups, no orphans), fired
  when a task has been idle (all agents ready/idle) past the threshold. Resume of an
  AUTO-SUSPENDED task feeds `claude --continue` (verified flag) so the conversation survives;
  MANUAL resume keeps plain `claude` (don't silently change Phase-2 semantics; revisit Phase 5).
  A task auto-suspended is visually distinct from user-hibernated (subline notes "suspensa").

### Degraded mode (consent declined)
- **D-13:** VTE `bell` signal → waiting hint (lower confidence, labeled differently);
  `contents-changed` recency → activity/idle timeout. No scraping. The status dot works but
  with documented reduced fidelity; a hint invites enabling hooks.

</decisions>

<specifics>
## Specific Ideas

- Hook script lives in the installed app (e.g. `src/arduis/hooks/arduis_hook.py`), referenced
  by ABSOLUTE path in settings entries; `$VARS`/`~` are not expanded in hook command strings
  (Pitfall 9) — resolve at merge time.
- The agent terminal runs at the TASK FOLDER ROOT (03.2 pivot) — state files are keyed by
  terminal id injected via env, NOT by cwd, so the multi-repo task root is a non-issue.
- Esc-interrupt phantom-running (Pitfall 7): conservative guard — `running` older than a
  generous ceiling with no events degrades to `ready` on the sweep; flagged for UAT.
- First-run workspace trust dialog (Pitfall 11): the task folder is new — claude may show a
  trust prompt BEFORE any hook fires; document that the spawn feed must tolerate it (it's a
  one-time per-folder prompt; hooks fire from SessionStart onward regardless).

</specifics>

<deferred>
## Deferred Ideas

- OSC 133 / termprops secondary signal → v2 or when the floor moves to VTE 0.78+ (Arch is
  already 0.84; Ubuntu 24.04 pins 0.76).
- Scraping fallback for non-Claude agents (STATUS-04) → v2 with Phase 5 agent-swap.
- Notification click-to-focus action; `ready` notifications default-on; per-task notification
  mute → post-UAT polish if requested.

</deferred>

---

*Phase: 04-attention-detection-who-s-waiting*
*Decisions: 13 locked (autonomous, research-recommended defaults)*
*Ready for: /gsd-plan-phase 4*
