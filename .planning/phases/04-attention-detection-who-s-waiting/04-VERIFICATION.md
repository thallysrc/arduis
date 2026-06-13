---
phase: 04-attention-detection-who-s-waiting
verified: 2026-06-13T15:00:00-03:00
status: human_needed
score: 9/10 must-haves verified
re_verification: false
human_verification:
  - test: "First launch shows pt-BR consent dialog; accept → arduis-backup created; your own hooks (GSD, notify-send) still fire in an outside-arduis claude session"
    expected: "Dialog renders; ~/.claude/settings.json.arduis-backup exists; outside hooks unaffected by env-guard (ARDUIS_STATE_FILE unset)"
    why_human: "Real ~/.claude/settings.json on a display; outside-arduis hook execution requires a real claude invocation"
  - test: "Create a task; observe sidebar dot color when claude first opens (before any prompt)"
    expected: "CIANO (ready), not VERDE (running) — UAT-D03: SessionStart→ready (plan decision vs CONTEXT wording)"
    why_human: "Live claude TUI; hook fires in real claude process"
  - test: "Send a prompt → VERDE (running); ask claude to run a command needing approval → LARANJA in ≤1s in both the sidebar row and pane header"
    expected: "Status flips to waiting within 1 second via Notification/permission_prompt hook (no scraping)"
    why_human: "Real approval prompt in a live claude TUI; timing is not deterministic in headless"
  - test: "While claude streams a long response (TUI repainting), dot NEVER goes orange without a real prompt; approve pending permission → orange clears to green immediately"
    expected: "No false orange on TUI redraw; PostToolUse clears to running"
    why_human: "The phase differentiator — only provable against a real claude TUI where the screen repaints heavily"
  - test: "[UAT-A1] Leave an approval pending >60s — orange must NOT be downgraded by an idle_prompt notification"
    expected: "waiting stays waiting; idle_prompt guard (Pitfall 2) holds in production"
    why_human: "Requires 60+ seconds of real claude idle with a pending approval"
  - test: "[UAT-A2] Press Esc mid-response — dot returns to cyan within ~60s via idle_prompt self-heal"
    expected: "Stop or idle_prompt fires; dot goes CIANO within the self-heal window"
    why_human: "Live claude TUI interaction; Stop signal timing"
  - test: "Unfocus the window, provoke an approval prompt → desktop notification arrives; focused window → no notification; bursts don't stack"
    expected: "libnotify 'branch aguarda você' arrives; focus suppresses; replace-id prevents stacking"
    why_human: "Requires a real notification daemon and real window focus state"
  - test: "Create ~/.config/arduis/arduis.toml with [attention] auto_suspend_minutes = 1; leave a ready agent >1min → task auto-suspended (notification + 'suspensa' subline, processes killed); resume via 'Retomar' → claude --continue restores the previous conversation"
    expected: "RAM freed; conversation continues; manual hibernate/resume still opens clean claude"
    why_human: "Requires a real claude conversation + RAM observation + toml read at startup"
  - test: "Decline the consent dialog (or touch ~/.local/share/arduis/hooks_declined); observe bell→'esperando?' badge + 'status limitado' visible hint"
    expected: "Degraded mode shows lower-confidence VTE-bell signal; re-invite button works"
    why_human: "Live VTE terminal BEL + GTK rendering"
  - test: "Close the app with agents running → no orphaned zsh/claude processes; status dir clean on next launch"
    expected: "ps shows no orphans; next launch status dir empty (cleared by startup wipe)"
    why_human: "Process table inspection after real window close"
---

# Phase 4: Attention Detection Verification Report

**Phase Goal:** Solve the Core Value pillar — always knowing which agent is waiting for you — HOOKS-FIRST (Claude Code Notification/Stop hooks write per-terminal state files arduis watches), terminal BEL as secondary signal, activity-timeout soft fallback. Reliability of the status dot is the differentiator; scraping is NOT primary. Sidebar rows are TASKS — a task's status aggregates its agents.

**Verified:** 2026-06-13T15:00:00-03:00
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | claude pauses for input → status flips to "waiting" via hooks (state file), not scraping | ✓ VERIFIED | Hook script subprocess test: Notification/permission_prompt → state="waiting" written atomically (test_hook_script.py 21/21 pass); env guard confirmed (no ARDUIS_STATE_FILE → exits 0, no file); broadway smoke proved real hook subprocess → FileMonitor → arduis-dot-waiting CSS class |
| 2 | Each worktree/task shows a status indicator (running/waiting/idle/ready) in sidebar AND pane header, both updating live from the same store change | ✓ VERIFIED | `_refresh_status_ui`, `_dot_by_sid`, `_pane_dot_by_tid` all present and wired; `arduis-dot-waiting/ready/idle/active` CSS classes confirmed; broadway smoke proved dot CSS class flips for waiting→running→ready transitions |
| 3 (headless half) | PostToolUse clears waiting; effective_status keeps WAITING regardless of age while pid is alive | ✓ VERIFIED | test_attention.py: `test_waiting_never_auto_degraded` passes; PostToolUse→running confirmed in hook script tests and broadway smoke |
| 3 (live half) | Waiting survives a TUI redraw (no false orange) and fires for a real approval prompt (no missed orange) | ? HUMAN NEEDED | Phase differentiator — only provable against a real claude TUI; see 04-HUMAN-UAT.md criterion 3 |
| 4 | Desktop notification (libnotify) + optional sound when waiting and window unfocused | ✓ VERIFIED (code) | `_maybe_notify`, `should_notify` gate, `_HAS_NOTIFY`, `Notify.Notification` replace-id scheme (`_notif_by_tid`) all present; `GLib.markup_escape_text` on body (T-04-14); `should_notify` unit-tested (fires only on transition INTO waiting while unfocused); live notification daemon confirmation is human-needed |
| 5 | Idle tasks auto-suspendable (RAM-04) | ✓ VERIFIED (code + headless) | `should_autosuspend` unit-tested (calm-only, never running/waiting, default OFF); `_auto_suspend` wired to `_hibernate_task` at single call site behind `should_autosuspend` gate in `_poll_ram`; broadway smoke: backdated calm task suspends, running task at same age never suspends; `AGENT_RESUME_FEED = b"claude --continue\n"` present; live end-to-end conversation survival is human-needed |

**Score:** 9/10 truths verified (automated + headless); 1 has a human-needed component (criterion 3 live half) and 2 more have live-confirmation aspects. All 5 roadmap success criteria have code-verified coverage with live confirmation pending.

### Deferred Items

None. All must-haves are either verified or classified as human_needed (live display/TUI required). No items are addressed by later phases.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/arduis/hooks/arduis_hook.py` | stdlib-only env-guarded hook script (STATUS-01 sensor) | ✓ VERIFIED | 86 lines; contains `ARDUIS_STATE_FILE`, `os.replace`, `os.getppid`, `sys.exit(0)`; imports only json/os/sys/tempfile/time; no `import gi`; no non-stdlib imports |
| `src/arduis/hooks/__init__.py` | Package marker for importlib.resources | ✓ VERIFIED | Exists; enables `hook_script_source()` via `importlib.resources.files("arduis.hooks")` |
| `src/arduis/spawn.py` | `build_worktree_spawn(runner, extra_env=None)` additive env seam | ✓ VERIFIED | `extra_env` parameter present; `envv = TERM_ENV + (extra_env or [])` — new list, TERM_ENV never mutated; argv unchanged regardless of extra_env |
| `src/arduis/attention.py` | Complete GTK-free policy brain | ✓ VERIFIED | All 18 required public symbols present (`AgentStatus`, `status_dir`, `state_file_path`, `clear_status_dir`, `read_state`, `effective_status`, `aggregate_task`, `HOOK_EVENTS`, `merged_settings`, `is_installed`, `hook_command`, `install_target_path`, `declined_marker_path`, `hook_script_source`, `should_notify`, `should_autosuspend`, `AttentionConfig`, `load_config`); no `import gi` |
| `src/arduis/session.py` | `TerminalRecord.status/.status_ts` + `Task.auto_suspended` + `AGENT_RESUME_FEED` | ✓ VERIFIED | `status`/`status_ts` are last two TerminalRecord fields; `auto_suspended` is last Task field; `AGENT_RESUME_FEED = b"claude --continue\n"` (bytes); positional construction verified for both; no `import gi` |
| `src/arduis/window.py` | Full attention wiring (consent + env injection + watcher + dots + notifications + cleanup) | ✓ VERIFIED | All key markers present: `_setup_attention`, `ARDUIS_STATE_FILE` (×2), `ARDUIS_SESSION_META` (×2), `monitor_directory`, `arduis-dot-waiting` (×3), `should_notify` (×2), `_clear_task_state_files` (×4), `arduis-backup`; Plan 04 markers: `_hibernate_task` (×6), `_auto_suspend` (×4), `should_autosuspend` (×4), `AGENT_RESUME_FEED` (×2), `"bell"`, `contents-changed`, `esperando?`, `status limitado`; AST parses clean |
| `tests/test_hook_script.py` | 21 subprocess round-trip tests | ✓ VERIFIED | 21 tests; covers env guard, full 7-event map, payload shape, Pitfall 2 idle_prompt guard, garbage stdin, unwritable dir, atomicity, stdlib-only assertion; all pass |
| `tests/test_attention.py` | 52 unit tests for attention policy surface | ✓ VERIFIED | 52 tests covering state machine, paths, reads, effective/aggregate status, settings merge (rich fixture), notify, suspend, config; all pass |
| `tests/test_session.py` | Extended with Phase 4 additions | ✓ VERIFIED | 5 new tests: AGENT_RESUME_FEED bytes, AGENT_FEED unchanged, auto_suspended trailing/serializable/untouched-by-hibernate; all pass |
| `tests/test_spawn_argv.py` | Extended with extra_env tests | ✓ VERIFIED | 4 new tests: append order, argv-unchanged, TERM_ENV immutability, ARDUIS_SESSION_META fixture; all pass |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/arduis/spawn.py` | `src/arduis/host_runner.py` | `runner.wrap_env(envv)` — list-literal posture unchanged | ✓ WIRED | `runner.wrap_argv(SHELL_ARGV), runner.wrap_env(envv)` confirmed in source; no shell-string join anywhere |
| `tests/test_hook_script.py` | `src/arduis/hooks/arduis_hook.py` | `subprocess.run([sys.executable, SCRIPT], env=..., input=json...)` | ✓ WIRED | Script invoked as subprocess exactly as claude would; 21 tests all confirm returncode == 0 |
| `src/arduis/attention.py` | `src/arduis/hooks/arduis_hook.py` | `hook_script_source()` reads packaged script content via `importlib.resources` | ✓ WIRED | `hook_script_source()` returns 2809-char content containing `ARDUIS_STATE_FILE`; skipif guard for parallel-worktree execution resolved |
| `src/arduis/attention.py` | `src/arduis/session.py:TerminalRecord` | `aggregate_task` consumes `record.kind`/`record.status` fields | ✓ WIRED | `getattr(rec, "kind", None)` and `getattr(rec, "status", None)` in `aggregate_task`; unit-tested with kind=="shell" exclusion |
| `src/arduis/window.py` | `src/arduis/attention.py` | All policy calls: `read_state`, `aggregate_task`, `merged_settings`, `should_notify`, `load_config`, `should_autosuspend`, `effective_status`, `state_file_path`, `clear_status_dir`, `hook_script_source`, `is_installed`, `install_target_path`, `declined_marker_path` | ✓ WIRED | `from arduis import attention` at line 72; `attention.` prefix calls confirmed throughout window.py |
| `src/arduis/window.py:_spawn_into` | `src/arduis/spawn.py:build_worktree_spawn` | `extra_env=[ARDUIS_STATE_FILE=..., ARDUIS_SESSION_META=...]` | ✓ WIRED | Lines 2120-2121 in window.py: `f"ARDUIS_STATE_FILE={state_file}"`, `f"ARDUIS_SESSION_META={term_id}"` passed as `extra_env`; agents-only (shells get none — Pitfall 8) |
| Status dir file events | Sidebar dot + pane header dot | `_on_status_event → _apply_state_file → record.status → _refresh_status_ui` | ✓ WIRED | `_on_status_event` does O(1) dict lookup in `_record_by_state_file` then calls `_apply_state_file`; `_refresh_status_ui` calls `_set_dot_class` on both `_dot_by_sid` and `_pane_dot_by_tid` |
| `src/arduis/window.py:_poll_ram` | `src/arduis/attention.py:should_autosuspend` | Calm-since tracking on the 2s tick | ✓ WIRED | `attention.should_autosuspend(agg, self._calm_since.get(...), now, auto_suspend_minutes)` at single call site; `to_suspend.append` then post-loop `_auto_suspend` (suspend-after-iterate pattern, never during iteration) |
| `src/arduis/window.py:_spawn_into agent feed` | `src/arduis/session.py:AGENT_RESUME_FEED` | `task.auto_suspended` selects the feed bytes | ✓ WIRED | `AGENT_RESUME_FEED if (task and task.auto_suspended) else AGENT_FEED` captured at closure-creation time; `task.auto_suspended = False` cleared after `_spawn_task_terminals` |
| `Vte.Terminal 'bell' signal` | `record.status waiting hint` | `terminal.connect("bell", self._make_bell_cb(task, record))` (0.76-floor API) | ✓ WIRED | Line 2138: `terminal.connect("bell", ...)` gated by `self._degraded`; `_make_bell_cb` sets status to "waiting", flips badge to "esperando?" |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `window.py` status dot rendering | `record.status` | `_apply_state_file` → `attention.read_state(path)` → `attention.effective_status(doc, ...)` | State file written by the real hook subprocess via atomic `os.replace` | ✓ FLOWING |
| `window.py` sidebar aggregate | `attention.aggregate_task(records)` | TerminalRecord.status fields populated by FileMonitor path | Real state files from hook events | ✓ FLOWING |
| `window.py` notification body | `doc.message` from StateDoc | Hook writes `payload.get("message", "")` from claude's stdin payload | Real claude message from hook stdin | ✓ FLOWING |
| `window.py` auto-suspend decision | `self._calm_since` | Set by `_poll_ram` from `aggregate_task` result; cleared on running/waiting | Real status aggregate from state files | ✓ FLOWING |
| `window.py` degraded bell status | `record.status` (sticky "waiting") | `_make_bell_cb` sets directly; `_make_activity_cb` clears; `_poll_ram` checks activity_ts | VTE bell signal (lower confidence, labeled "esperando?") | ✓ FLOWING (degraded path) |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Hook exits 0 on garbage stdin with no env | `subprocess.run(SCRIPT, input=b'not json{{', env={no STATE_FILE})` | returncode=0 | ✓ PASS |
| Hook writes state="waiting" for permission_prompt | `subprocess.run` with `ARDUIS_STATE_FILE` set, Notification/permission_prompt payload | state file written, doc.state=="waiting" | ✓ PASS |
| `effective_status` keeps WAITING at 24h age | `effective_status(StateDoc(state='waiting', ts=0), now=86400, pid_alive=True, ...)` | AgentStatus.WAITING | ✓ PASS |
| `should_autosuspend` never fires for RUNNING | `should_autosuspend(AgentStatus.RUNNING, calm_since=0, now=999999, minutes=1)` | False | ✓ PASS |
| `should_autosuspend` fires for READY past threshold | `should_autosuspend(AgentStatus.READY, calm_since=0, now=120, minutes=1)` | True | ✓ PASS |
| `merged_settings` is idempotent | double-merge on same settings+path | changed=False on second call | ✓ PASS |
| `merged_settings` preserves pre-existing hooks | notify-send Notification hook in input → present in output | True | ✓ PASS |
| `build_worktree_spawn` extra_env appended, argv unchanged | `build_worktree_spawn(runner, extra_env=[STATE_FILE, SESSION_META])` | argv=["zsh","-l","-i"], envv=[TERM=..., STATE_FILE=..., META=...], TERM_ENV len==1 | ✓ PASS |
| `hook_script_source` returns packaged content | `hook_script_source()` | 2809 chars, contains "ARDUIS_STATE_FILE" | ✓ PASS |
| Full test suite | `pytest tests/ -q` | 172 passed | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|---------------|-------------|--------|----------|
| STATUS-01 | 04-01, 04-02, 04-03, 04-04 | App detects "aguardando input" via Claude Code hooks (Notification/Stop → state file) | ✓ SATISFIED | Hook script (arduis_hook.py) maps 7 events to 5 states; ARDUIS_STATE_FILE injected per agent terminal via extra_env; FileMonitor drives record.status; 21 subprocess tests + 52 attention unit tests pass; degraded bell fallback (D-13) when hooks declined |
| STATUS-02 | 04-02, 04-03 | Per-worktree status indicator (running/waiting/idle/ready) in sidebar and pane header | ✓ SATISFIED | `_dot_by_sid` (task aggregate, sidebar) + `_pane_dot_by_tid` (per-terminal, pane header); 5 CSS classes (arduis-dot-waiting/ready/idle/active/hibernated); both update live from `_refresh_status_ui` on every state-file event; broadway smoke confirmed dot CSS class flips |
| STATUS-03 | 04-02, 04-03 | libnotify desktop notification + optional sound when agent enters waiting and window unfocused | ✓ SATISFIED (code) | `_maybe_notify` + `should_notify` gate (transition INTO waiting, unfocused only); replace-id per terminal (no stacking); `GLib.markup_escape_text` on body; optional sound GSound→beep→silence; live notification daemon confirmation is human-needed |
| RAM-04 | 04-02, 04-04 | Auto-suspend idle worktrees (linked to idle status) | ✓ SATISFIED | `should_autosuspend` (calm-only, never running/waiting, default OFF); `_auto_suspend` behind single call site in `_poll_ram`; reuses `_hibernate_task` no-orphan path; `AGENT_RESUME_FEED = b"claude --continue\n"` for resume; suspension always notifies; broadway smoke confirmed auto-suspend and the running-never-suspends guard |

No orphaned requirements — all 4 requirements for Phase 4 claimed by plans and verified with implementation evidence.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `window.py` | 1200, 1214, 2407 | "placeholder" mentions | ℹ️ Info | These are legitimate UI placeholder boxes for empty canvas states (hibernated task "Retomar" card, empty pane node) — not stub implementations. No feature is hidden behind a placeholder. |

No blocker or warning anti-patterns found. All Phase 4 source files have no TODO/FIXME/stub patterns.

### Human Verification Required

All 10 items from `04-HUMAN-UAT.md` await live confirmation on a real display with a real claude TUI. 5 are headless-proven (consent safety, pipeline dot flips, cleanup, auto-suspend gate); 5 require live interaction.

**The load-bearing gate** is criterion 3: "waiting survives a TUI redraw (no false orange) and fires for a real approval prompt (no missed orange)." This is the phase differentiator and is ONLY provable against a live claude TUI.

#### 1. Consent dialog + user hooks preserved

**Test:** Run `./run.sh` in a real project; first launch shows the pt-BR install dialog; accept; confirm `~/.claude/settings.json.arduis-backup` exists and your own hooks still fire in an outside-arduis claude session.
**Expected:** Dialog renders pt-BR text; backup created; arduis hook is a no-op outside arduis (env-guard: no ARDUIS_STATE_FILE set)
**Why human:** Real `~/.claude/settings.json` on a display; outside-arduis hook execution

#### 2. [UAT-D03] SessionStart dot color

**Test:** Create a task; observe the dot color the moment claude opens, before any prompt.
**Expected:** CIANO (ready), not VERDE (running) — the plan implemented `SessionStart → ready` over the CONTEXT's "→running" wording; if VERDE appears in practice, record as D-03 deviation.
**Why human:** Live claude hook firing at SessionStart

#### 3. Criterion 3 (THE GATE) — no false orange on TUI redraw

**Test:** While claude streams a long response (TUI repainting), confirm the dot NEVER goes orange without a real approval prompt. Then trigger an approval prompt — dot goes LARANJA in ≤1s.
**Expected:** Zero false-orange during streaming; real approval → orange within 1 second
**Why human:** Only provable against a real claude TUI; the phase differentiator

#### 4. [UAT-A1] Pending approval not downgraded after 60s

**Test:** Leave an approval pending more than 60 seconds.
**Expected:** Orange must NOT be downgraded to ready/idle by an idle_prompt notification (Pitfall 2 guard holds in production)
**Why human:** Requires 60+ real seconds with a pending approval

#### 5. [UAT-A2] Esc-interrupt mid-response

**Test:** Press Esc mid-response; observe dot behavior.
**Expected:** Dot returns to cyan within ~60s via Stop or idle_prompt self-heal
**Why human:** Live claude TUI interaction; Stop signal timing

#### 6. Criterion 4 — desktop notification unfocused

**Test:** Unfocus the window, provoke an approval prompt → notification arrives; focused window → no notification; bursts don't stack.
**Expected:** libnotify "branch aguarda você"; focus suppresses; replace-id prevents stacking
**Why human:** Real notification daemon + real window focus state

#### 7. Criterion 5 — auto-suspend + --continue resume (RAM-04)

**Test:** Create `~/.config/arduis/arduis.toml` with `[attention]\nauto_suspend_minutes = 1`; converse with an agent; leave it ready >1min → task auto-suspended (notification + "suspensa" subline). Resume via "Retomar" → conversation intact.
**Expected:** Conversation survives `claude --continue`; manual hibernate/resume still opens clean claude
**Why human:** Real claude conversation + RAM observation + toml read at startup

#### 8. Degraded bell mode

**Test:** Decline the dialog or touch `~/.local/share/arduis/hooks_declined`; drive a terminal bell; observe badge + hint.
**Expected:** "esperando?" badge; "status limitado — instalar hooks?" hint visible and clickable
**Why human:** Live VTE terminal BEL + GTK rendering

#### 9. No orphans on close

**Test:** Close the app with agents running → `ps -eo pgid,cmd | grep -i claude` shows no orphans; status dir clean on next launch.
**Expected:** Zero orphaned processes; status dir wiped by startup `clear_status_dir`
**Why human:** Process table inspection after real window close

#### 10. [UAT-D03 live observation]

**Test:** Observe whether VERDE (running) or CIANO (ready) appears at SessionStart in practice.
**Expected:** CIANO (per plan decision); VERDE → record as D-03 deviation and flip the hook map in a follow-up.
**Why human:** Live claude hook

### Gaps Summary

No gaps identified. All automated-verifiable must-haves pass. The 10 human verification items in `04-HUMAN-UAT.md` represent live confirmation of headless-proven behaviors (5 items) and behaviors that are only observable against a real claude TUI (5 items, including the load-bearing criterion 3). These are correctly classified as `human_needed`, not `gaps_found`.

The overall status is `human_needed` because of the 10 live verification items, with criterion 3 ("no false orange on TUI redraw") being the phase gate.

---

_Verified: 2026-06-13_
_Verifier: Claude (gsd-verifier)_
