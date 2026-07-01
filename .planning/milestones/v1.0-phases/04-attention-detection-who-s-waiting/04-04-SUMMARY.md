---
phase: 04-attention-detection-who-s-waiting
plan: 04
subsystem: attention
tags: [auto-suspend, ram-04, degraded-mode, vte-bell, contents-changed, hibernate, claude-continue, tomllib, libnotify]

# Dependency graph
requires:
  - phase: 04-attention-detection-who-s-waiting
    provides: "attention.py policy brain (should_autosuspend, aggregate_task, AttentionConfig.auto_suspend_minutes/idle_minutes, load_config) + AgentStatus 5-state model"
  - phase: 04-attention-detection-who-s-waiting
    provides: "window.py attention wiring from Plan 03 (_setup_attention 4-branch consent, _present_hook_consent/_install_hooks, _apply_state_file/_refresh_status_ui, _maybe_notify, _clear_task_state_files, _poll_ram status re-apply, self._degraded flag, _record_by_state_file, env injection at spawn)"
  - phase: 03.2-projects-and-cross-repo-tasks
    provides: "window.py hibernate/resume/teardown machinery (_on_hibernate, _resume_task, _spawn_task_terminals, _make_wt_spawn_cb, _teardown_session_terminals, _all_task_terminals)"
provides:
  - "RAM-04 opt-in idle auto-suspend: _calm_since tracking on the 2s _poll_ram tick → should_autosuspend gate → shared _hibernate_task path; AGENT_RESUME_FEED (claude --continue) on auto-suspend resume only; visible 'suspensa' sidebar distinction; always-on suspension notification"
  - "Degraded mode (D-13): VTE bell→waiting (sticky, 'esperando?' badge) + contents-changed→running/idle (1s-throttled), no ready/no auto-suspend; 'status limitado' re-invite button → _show_consent_dialog (no FileMonitor duplication)"
  - "Seams Plan 05 verifies live: _hibernate_task shared body, _auto_suspend single call site, _make_bell_cb/_make_activity_cb, AGENT_RESUME_FEED feed selection in _make_wt_spawn_cb"
affects: [05-agent-swap]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared-body extraction: _hibernate_task carries the no-orphan teardown/state-clear/layout-drop/rebuild body; _on_hibernate (manual) and _auto_suspend (idle) both route through it — one proven path, two entrypoints (T-04-18)"
    - "Closure-captured feed decision: _make_wt_spawn_cb reads task.auto_suspended at callback-creation time so the resume can clear the flag immediately after spawn without leaking --continue into a later cycle"
    - "Single-gate process-kill: _auto_suspend reachable ONLY via the should_autosuspend gate inside _poll_ram (verified single call site) — running/waiting immune at any age, degraded excluded"
    - "Suspend-after-iterate: _poll_ram collects to_suspend during the store walk and suspends AFTER the loop (suspend mutates layouts/widgets/sidebar — never during iteration)"
    - "Degraded signals gated by self._degraded at spawn: bell/contents-changed connected ONLY in degraded mode so BEL never fights authoritative hooks in primary mode"

key-files:
  created: []
  modified:
    - "src/arduis/session.py (AGENT_RESUME_FEED bytes constant + Task.auto_suspended trailing field — 15 insertions)"
    - "src/arduis/window.py (auto-suspend tick + _hibernate_task extraction + --continue resume + degraded bell/activity wiring + re-invite hint — 319 insertions)"
    - "tests/test_session.py (5 new tests: AGENT_RESUME_FEED bytes, AGENT_FEED unchanged, auto_suspended trailing/serializable/untouched-by-hibernate — 55 insertions)"

key-decisions:
  - "Degraded mode NEVER auto-suspends (D-12/D-13): no ready state + killing on a coarse activity timeout risks SIGKILL'ing a working agent (Pitfall 6) — auto-suspend requires hook-derived calm states; gated by `not self._degraded`"
  - "calm_since = wall-clock when the aggregate ENTERED ready/idle/ended; reset to None on running/waiting/None or non-ACTIVE; recomputed AFTER the status re-apply pass so it reflects the freshest idle/staleness transitions"
  - "Suspension notification ALWAYS fires (even focused) via _notify_suspended bypassing the _maybe_notify focus gate — arduis killed processes on the user's behalf and that must never be silent (T-04-22)"
  - "auto_suspended cleared on EVERY resume immediately after _spawn_task_terminals (the spawn closure already captured the feed decision) so one --continue never leaks into a later manual hibernate→resume cycle"
  - "Degraded bell is sticky waiting until the next contents-changed activity burst clears it; badge down-labeled 'esperando?' (with the question mark, D-13 lower confidence) vs the dot-only primary treatment"
  - "Re-invite calls _show_consent_dialog (recomputes settings + calls _present_hook_consent) NOT _setup_attention — avoids a duplicate Gio.FileMonitor on the status dir"

patterns-established:
  - "Pattern: a process-killing feature has exactly one reachable call site behind one policy gate (should_autosuspend), default OFF (auto_suspend_minutes 0), excluded from the low-confidence path (degraded)"
  - "Pattern: degraded-mode handles (badge label, activity ts, last-handled throttle) are keyed by terminal id and dropped on hibernate via the same {sid}: prefix-pop as pane-dot/notif handles"

requirements-completed: [RAM-04, STATUS-01]

# Metrics
duration: ~12 min
completed: 2026-06-12
---

# Phase 4 Plan 04: Auto-suspend + Degraded Mode Summary

**Opt-in idle auto-suspend (RAM-04) rides the 2s `_poll_ram` tick through a single `should_autosuspend` gate into the proven no-orphan `_hibernate_task` path, feeds `claude --continue` on resume so suspension costs nothing, and marks the row "suspensa"; consent-decliners get a 0.76-floor degraded signal (VTE `bell`→waiting, `contents-changed`→running/idle) with a "status limitado" re-invite — both verified live on a real `Vte.Terminal`.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 3 (1 TDD, 2 auto)
- **Files modified:** 3 (`session.py`, `window.py`, `test_session.py`)
- **Tests:** suite 172 passed (baseline 167 + 5 new session tests)

## Accomplishments

- **Task 1 (TDD):** `AGENT_RESUME_FEED = b"claude --continue\n"` (bytes, 0.76 `feed_child` floor) added next to `AGENT_FEED` (unchanged); `Task.auto_suspended: bool = False` appended as the LAST field (positional construction preserved, serializable, untouched by `hibernate_fields`). RED→GREEN with 5 new tests.
- **Task 2 (auto-suspend):** Extracted `_hibernate_task` shared body from `_on_hibernate` (teardown → state-file clear → `hibernate_fields` → layout/widget drop → main fallback → rebuild) so the manual menu path and the idle tick share one no-orphan machinery. `_poll_ram` now tracks `_calm_since` per ACTIVE task (ready/idle/ended) and fires `attention.should_autosuspend` (`not self._degraded`-gated) collecting tasks into `to_suspend`, suspended AFTER the loop. `_auto_suspend` sets `auto_suspended`, hibernates, and always notifies via `_notify_suspended`. Resume feeds `AGENT_RESUME_FEED` for auto-suspended tasks (flag captured in the spawn closure, cleared right after `_spawn_task_terminals`). Sidebar subline shows "claude · suspensa".
- **Task 3 (degraded mode):** `_spawn_into` connects `bell` + `contents-changed` for agent terminals ONLY when `self._degraded`. `_make_bell_cb` flips the record to sticky `waiting`, badge to "esperando?", routes `_maybe_notify`. `_make_activity_cb` (1s-throttled) clears the bell hint → `running`, restores the badge. `_poll_ram` degrades agent terminals with no activity for `idle_minutes` to `idle` (no `ready`, no auto-suspend). A "status limitado — instalar hooks?" flat button (shown only when degraded) re-presents consent via `_show_consent_dialog` (no FileMonitor duplication); install/decline clear/refresh the hint.

## Wiring Contract (the seams Plan 05 verifies)

- **`_hibernate_task(self, task)`** — shared body; `_on_hibernate` = `_menu_session()` guard + call; `_auto_suspend` = set `auto_suspended` + call + `_notify_suspended`. `_clear_task_state_files` is part of the body (after teardown, Plan-03 ordering) so EVERY caller cleans state files.
- **Auto-suspend gate (single call site):** `_poll_ram` → `agg = aggregate_task(terms)` (after the status re-apply) → `_calm_since.setdefault/pop` → `not self._degraded and should_autosuspend(agg, calm_since, now, auto_suspend_minutes)` → `to_suspend.append` → post-loop `_auto_suspend`.
- **Resume feed selection:** `_make_wt_spawn_cb` captures `agent_feed = AGENT_RESUME_FEED if (task and task.auto_suspended) else AGENT_FEED` at creation; `_resume_task` clears `task.auto_suspended = False` after `_spawn_task_terminals` and drops the `suspend:<task_id>` notification slot.
- **Degraded signals:** connected in `_spawn_into` iff `self._degraded and record is not None`; `_make_bell_cb`/`_make_activity_cb` close over `(task, record)`; badge handle in `_badge_by_tid[term_id]`; activity epoch in `_activity_ts`, throttle in `_activity_last_handled` — all dropped on the `{sid}:` prefix-pop in `_hibernate_task`.
- **Suspension notification slot:** `_notif_by_tid["suspend:<task_id>"]` (distinct from agent waiting slots), cleared on resume.

## Task Commits

1. **Task 1: AGENT_RESUME_FEED + Task.auto_suspended** - `80e459e` (feat, RED+GREEN)
2. **Task 2: opt-in idle auto-suspend + --continue resume + "suspensa"** - `8f87aae` (feat)
3. **Task 3: degraded mode bell/activity + re-invite hint** - `efcb33b` (feat)

## Files Created/Modified

- `src/arduis/session.py` — `AGENT_RESUME_FEED` bytes constant; `Task.auto_suspended` trailing field (window sets it, `hibernate_fields` never touches it).
- `src/arduis/window.py` — `__init__` fields (`_calm_since`, `_activity_ts`, `_activity_last_handled`, `_badge_by_tid`, `_degraded_hint_btn`); `_hibernate_task` extraction; `_auto_suspend`/`_notify_suspended`; `_poll_ram` calm-tracking + suspend pass + degraded idle; `_make_wt_spawn_cb` feed selection; `_resume_task` flag clearing + slot drop; `_make_bell_cb`/`_make_activity_cb`; `_spawn_into` degraded connect + `_badge_by_tid` reveal; `_make_leaf` badge handle; `_build_hint_bar` re-invite button + `_refresh_degraded_hint`/`_show_consent_dialog`; `_install_hooks`/`_present_hook_consent` hint refresh.
- `tests/test_session.py` — 5 new tests covering the feed constant and the trailing field.

## Decisions Made

See `key-decisions` frontmatter. All adopt plan/CONTEXT (D-11/D-12/D-13) and RESEARCH (Pattern 6/7) defaults; user AFK, no architectural deviations.

## Deviations from Plan

None - plan executed exactly as written.

The plan's open implementation choices were resolved to the documented defaults: the suspension-notification slot is keyed `suspend:<task_id>` (distinct from the per-agent-terminal waiting slot so the two never collide) and cleared on resume; the degraded re-invite extracts `_show_consent_dialog` (recompute settings + call `_present_hook_consent`) exactly as the plan specified to avoid a second `Gio.FileMonitor`. These are plan-specified branches, not deviations.

## Issues Encountered

The worktree base was not an ancestor of the expected base `0b8aa9a` (HEAD carried only older docs commits, missing the Wave-2 attention wiring); `git reset --hard 0b8aa9a` restored the correct base before any work, then execution was clean.

## User Setup Required

None — no external service configuration required. Auto-suspend is opt-in via `~/.config/arduis/arduis.toml` (`[attention] auto_suspend_minutes`, absent/0 = OFF — the default), read at startup; nothing to configure for the default behavior.

## Next Phase Readiness

- RAM-04 and the degraded fallback are functionally wired. Plan 05 verifies LIVE: (1) a real idle claude auto-suspends only past the threshold and resumes its conversation via `--continue`; (2) the "suspensa" row + suspension notification appear; (3) running/waiting agents are never suspended at any age; (4) degraded bell→"esperando?" + activity→running/idle behaves within the 0.76 floor; (5) the "status limitado" re-invite installs without duplicating the monitor.
- **UAT flags carried forward (04-01/02/03):** SessionStart→ready vs running; Esc-interrupt / idle_prompt self-heal timing; first-run workspace-trust prompt invisible to hooks (Pitfall 11, accepted v1 gap). Degraded BEL spoofing (T-04-19) is accepted by design (lower-confidence, never a kill).

## Self-Check: PASSED

- `src/arduis/session.py`, `src/arduis/window.py`, `tests/test_session.py` all exist on disk; full suite 172 passed.
- All three task commits reachable: `80e459e`, `8f87aae`, `efcb33b`.
- Verification greps all FOUND in window.py: `_hibernate_task` (6), `_auto_suspend` (4), `should_autosuspend` (4), `AGENT_RESUME_FEED` (2), `"bell"` (1), `contents-changed` (6), `esperando?` (5), `status limitado` (2); session.py: `AGENT_RESUME_FEED` (1), `auto_suspended` (2), `import gi` (0).
- Pitfall-6 wiring: `_auto_suspend` is reachable ONLY via the `should_autosuspend` gate inside `_poll_ram` (single call site at the post-loop pass; definition at the hibernate region) — confirmed by `grep -n`.
- No-threads check: `grep -cE 'threading|Thread\('` == 0.
- `bell` / `contents-changed` / `child-exited` verified connectable on a real `Vte.Terminal` (broadway headless) at the 0.76 binding.

---
*Phase: 04-attention-detection-who-s-waiting*
*Completed: 2026-06-12*
