---
phase: 04-attention-detection-who-s-waiting
plan: 03
subsystem: attention
tags: [gio-filemonitor, libnotify, vte-spawn, env-injection, settings-merge, gtk4, status-dots]

# Dependency graph
requires:
  - phase: 04-attention-detection-who-s-waiting
    provides: "attention.py policy brain (read_state/effective_status/aggregate_task/merged_settings/should_notify/load_config), hook install path/source helpers, TerminalRecord.status/.status_ts fields"
  - phase: 04-attention-detection-who-s-waiting
    provides: "spawn.build_worktree_spawn(runner, extra_env) seam; arduis_hook.py env contract (ARDUIS_STATE_FILE + ARDUIS_SESSION_META)"
  - phase: 03.2-projects-and-cross-repo-tasks
    provides: "window.py Task/TerminalRecord wiring (_all_task_terminals, _spawn_into, _make_row/_make_leaf, _poll_ram, hibernate/close/teardown paths)"
provides:
  - "window.py attention wiring: startup infra (_setup_attention 4-branch consent), per-terminal env injection at spawn, Gio.FileMonitor watcher, sidebar task-aggregate + pane-header per-terminal status dots, libnotify waiting-notifications, state-file cleanup on every teardown path"
  - "Seams Plan 04 builds on: _record_by_state_file map, _apply_state_file/_refresh_status_ui pipeline, _dot_css_for status→class map, _notif_by_tid replace-id scheme, self._degraded flag"
affects: [04-04 auto-suspend + degraded-mode hint, 05-agent-swap]

# Tech tracking
tech-stack:
  added: [libnotify (gir Notify 0.7, optional/guarded), Gio.FileMonitor (status-dir watch), GSound (gir 1.0, optional sound path)]
  patterns:
    - "Guarded optional gir import: try gi.require_version + import → module flag (_HAS_NOTIFY); a box without the gir silently disables the feature instead of crashing"
    - "Watcher on the GLib main loop only (Gio.FileMonitor 'changed' → O(1) dict lookup → record.status); no threads anywhere"
    - "Time-based transitions (idle/staleness) ride the existing 2s _poll_ram tick; instant transitions ride the FileMonitor — both call _apply_state_file"
    - "ONE Notification per terminal (update+show on the same object) → server-side replace, never stacks (replace-id by terminal)"
    - "State-file deletion is the ONLY filesystem removal in window.py and composes paths exclusively via attention.state_file_path under self._status_dir (T-04-16 scoping)"

key-files:
  created: []
  modified:
    - "src/arduis/window.py (attention startup + env injection + watcher + dots + notifications + cleanup — 523 insertions, only file touched in the wave)"

key-decisions:
  - "Consent is gated by an Adw.AlertDialog ONLY when settings is parseable AND not installed AND no declined marker; unparseable settings → degraded + never write (T-04-12)"
  - "The status monitor starts in EVERY branch (incl. before the async consent response) so a same-session accept is watched immediately"
  - "pid liveness probes the terminal pgid first (killpg(pgid,0)), falling back to the hook-written doc.pid; no pgid and no pid → assume alive (never wrongly retire a fresh record)"
  - "close-repo clears ONLY the closed repo's state files; the task-level agent pair keeps running so its files stay live (Pitfall 5b scoping)"
  - "Optional sound: GSound → Gtk.Widget.error_bell → silence (error_bell is floor-safe vs Gdk.Display.beep which may be unbound at the 0.76 floor)"

patterns-established:
  - "Attention status surface: window.py is the only gi-importing module; all decisions delegate to GTK-free attention.py — dots/notifications are pure reflection of record.status flipped by the watcher/tick"
  - "Stub-then-fill across tasks: Task 1 landed _apply_state_file/_refresh_status_ui/_maybe_notify as no-op stubs so the monitor wiring was runnable; Tasks 2/3 replaced them"

requirements-completed: [STATUS-01, STATUS-02, STATUS-03]

# Metrics
duration: 18 min
completed: 2026-06-12
---

# Phase 4 Plan 03: Attention Wiring in window.py Summary

**Wired the tested Phase-4 domain into the GTK window: a 4-branch consent-gated hook installer, per-agent-terminal `ARDUIS_STATE_FILE` env injection, a `Gio.FileMonitor` that flips `TerminalRecord.status` on the main loop, live sidebar task-aggregate + pane-header per-terminal status dots (Dracula colors), `libnotify` waiting-notifications with a per-terminal replace-id, and state-file cleanup on every teardown path — Core Value "sempre sabendo qual deles te espera" is now visible in primary (hooks) mode.**

## Performance

- **Duration:** ~18 min
- **Tasks:** 3 (all `type=auto`)
- **Files modified:** 1 (`src/arduis/window.py` — exclusive wave ownership)
- **Tests:** suite 167 passed (baseline 167; this plan adds GTK-window wiring covered by the manual/headless checklist, no new GTK-free unit tests)

## Accomplishments

- **Startup infra (Task 1):** `_setup_attention` refreshes the installed hook script atomically (tmp + `os.replace`), reads `~/.claude/settings.json` (missing → `{}`, unparseable → degraded + never write — T-04-12), and routes through 4 branches (unparseable / already-installed / declined-marker / first-run consent). The consent dialog (pt-BR `Adw.AlertDialog`) installs via backup + atomic additive `merged_settings` on "Instalar" or touches the declined marker on "Agora não". The `Gio.FileMonitor` starts in every branch.
- **Env injection + dots (Task 2):** `_spawn_into` injects `ARDUIS_STATE_FILE` + `ARDUIS_SESSION_META` for task AGENT terminals (shells/pinned-main get none — Pitfall 8), registers the state-file path in `_record_by_state_file`, and reveals the pane dot. `_apply_state_file` reads the doc, computes effective status (pgid/pid liveness), writes `record.status`/`.status_ts`, and refreshes the UI. Sidebar dots show the task aggregate; pane-header dots show per-terminal status. The 2s `_poll_ram` tick re-applies registered state files for idle/staleness transitions.
- **Notifications + cleanup (Task 3):** `_maybe_notify` fires a single per-terminal libnotify notification (escaped body, `update`+`show` replace-id) only on a transition INTO waiting while unfocused; optional sound degrades GSound→beep→silence. `_clear_task_state_files` / `_clear_repo_state_files` delete state files (status-dir-only paths, T-04-16) and are wired into hibernate, close-repo (repo-scoped), and window-close; the monitor is cancelled on close.

## Wiring Contract (the seams Plan 04 builds on)

**`_setup_attention` 4 branches** (all start the monitor):
1. settings UNPARSEABLE → `self._degraded = True`, never write
2. `is_installed(settings, target)` → silent no-op (idempotent)
3. declined marker present → `self._degraded = True`
4. else → `_present_hook_consent` (install backup+merge, or mark declined)

**Env-injection point:** `_spawn_into(terminal, cwd, task, term_id, kind)` — when `task is not None and kind == "agent"`, builds `extra_env=[ARDUIS_STATE_FILE=<state_file>, ARDUIS_SESSION_META=<term_id>]` and registers `self._record_by_state_file[state_file] = (task, record)`.

**`_record_by_state_file` lifecycle:** populated at agent spawn; entries popped in `_clear_task_state_files`/`_clear_repo_state_files` (hibernate / close-repo / window-close).

**Dot CSS classes/colors (`_dot_css_for`):** not-active → `arduis-dot-hibernated` (#6272a4); WAITING → `arduis-dot-waiting` (#ffb86c orange); RUNNING / None → `arduis-dot-active` (#50fa7b); READY → `arduis-dot-ready` (#8be9fd); IDLE → `arduis-dot-idle` (#7a9e7e); ENDED → `arduis-dot-hibernated`. `_set_dot_class` removes the other `arduis-dot-*` classes then adds the chosen one.

**Notification replace-id scheme:** ONE `Notify.Notification` kept in `self._notif_by_tid[term_id]`; subsequent waitings `.update(title, body, icon)` + `.show()` the same object (server-side replace, no stacking). `Notify.init("arduis")` once in `_setup_attention` (guarded by `_HAS_NOTIFY`).

## Task Commits

1. **Task 1: startup attention infra (status dir wipe, hook install + consent, watcher)** - `5e8c087` (feat)
2. **Task 2: env injection at spawn + status store + sidebar/pane dots** - `373d168` (feat)
3. **Task 3: libnotify waiting-notifications + state-file cleanup on teardown** - `031751c` (feat)

## Files Created/Modified

- `src/arduis/window.py` — all attention wiring: imports (`attention`, guarded `Notify`), `__init__` fields, `_setup_attention`/`_present_hook_consent`/`_install_hooks`/`_start_status_monitor`/`_on_status_event`, `_apply_state_file`/`_pid_alive`/`_refresh_status_ui`/`_dot_css_for`/`_set_dot_class`, `_maybe_notify`/`_play_attention_sound`, `_clear_task_state_files`/`_clear_repo_state_files`, env injection in `_spawn_into`, dot handles in `_make_row`/`_make_leaf`/`_rebuild_sidebar`, time-based re-apply in `_poll_ram`, cleanup in `_on_hibernate`/`_on_close_repo`/`_on_close_request`.

## Decisions Made

See `key-decisions` frontmatter. All adopt plan/research/CONTEXT defaults (user AFK); no architectural deviations.

## Deviations from Plan

None - plan executed exactly as written.

The plan's open implementation choices were resolved to the documented defaults: the optional-sound beep path uses `self.error_bell()` (the plan flagged `Gdk.Display.beep()` as possibly unbound at the 0.76 floor and named `error_bell` as the floor-safe fallback), and the GSound context is cached on `self._gsound_ctx` on first use as the plan specified. These are plan-specified branches, not deviations.

## Issues Encountered

None. The worktree base was not an ancestor of the expected base `9ba48af` (it carried unrelated roadmap commits from another branch); `git reset --hard 9ba48af` restored the correct Wave-1 base (which lands `arduis_hook.py`, the `spawn.py extra_env` seam, and `attention.py`) before any work, then execution was clean.

## User Setup Required

None — no external service configuration required. (The hook install into `~/.claude/settings.json` is consent-gated at runtime, not a build-time setup step.)

## Next Phase Readiness

- Phase success criteria 1–4 are functionally wired in primary (hooks) mode: hook → state file → `Gio.FileMonitor` → `record.status` → sidebar/pane dots; waiting + unfocused → libnotify (+ optional sound). Live UAT (real claude in an arduis task) remains the phase gate per 04-RESEARCH.
- Plan 04 builds auto-suspend (RAM-04, `should_autosuspend` on the `_poll_ram` tick using `_att_config.auto_suspend_minutes`) and the degraded-mode hint (the `self._degraded` flag + `_build_hint_bar` content) on these exact seams.
- **UAT flags carried forward (from 04-01/04-02):** verify SessionStart→ready vs running; Esc-interrupt / idle_prompt self-heal timing; the first-run workspace-trust prompt is invisible to hooks (Pitfall 11, accepted v1 gap).

## Self-Check: PASSED

- `src/arduis/window.py` exists on disk; full suite 167 passed.
- All three task commits reachable: `5e8c087`, `373d168`, `031751c`.
- Verification greps all FOUND: `_setup_attention`, `ARDUIS_STATE_FILE`, `ARDUIS_SESSION_META`, `monitor_directory`, `arduis-dot-waiting`, `should_notify`, `_clear_task_state_files`, `arduis-backup`.
- D-10 guard: the only `os.unlink` deletions are inside `_clear_task_state_files`/`_clear_repo_state_files` (paths via `attention.state_file_path` under `self._status_dir`); no other filesystem removal added.
- No-threads check: `grep -c "threading\|Thread("` == 0.

---
*Phase: 04-attention-detection-who-s-waiting*
*Completed: 2026-06-12*
