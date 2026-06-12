---
phase: 04
slug: attention-detection-who-s-waiting
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-12
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Source: 04-RESEARCH.md §"Validation Architecture" (2026-06-12).

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing; /tmp venv `--system-site-packages` per dev-env convention) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths=tests, pythonpath=src) |
| **Quick run command** | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_attention.py tests/test_hook_script.py -x -q` |
| **Full suite command** | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/ -q` |
| **Estimated runtime** | ~5–10 seconds (current baseline: 88 passing) |

---

## Sampling Rate

- **After every task commit:** Run `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_attention.py tests/test_hook_script.py -x -q` (plus the task's own `<automated>` command)
- **After every plan wave:** Run `/tmp/arduis-venv-ab12/bin/python -m pytest tests/ -q` (must stay ≥ the 88-test baseline)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Phase gate:** full suite green + the 04-05 broadway smoke + live UAT checklist (04-05 Task 2)
- **Max feedback latency:** ~10 seconds

---

## Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STATUS-01 | event→state map, incl. notification_type branches + idle_prompt never-downgrade guard | unit | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_attention.py -x -q` | ❌ Wave 0 (created RED-first in 04-02 Task 1) |
| STATUS-01 | hook script end-to-end: stdin JSON + env → atomic state file; no-op without env; never nonzero exit | integration (subprocess) | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_hook_script.py -x -q` | ❌ Wave 0 (created RED-first in 04-01 Task 1) |
| STATUS-01 | settings merge: additive, idempotent, preserves user hooks (hooks-rich fixture) | unit | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_attention.py -k "merge or install or hook_command or marker" -x -q` | ❌ Wave 0 (04-02 Task 2) |
| STATUS-01 | spawn env injection (`ARDUIS_STATE_FILE` in envv, argv unchanged) | unit | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_spawn_argv.py -x -q` | ✅ extend (04-01 Task 2) |
| STATUS-02 | task aggregation precedence; shell terminals excluded; TerminalRecord status fields | unit | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_attention.py tests/test_session.py -x -q` | ❌ Wave 0 / ✅ extend (04-02 Tasks 1+3) |
| STATUS-02 | dots render in sidebar + pane header; flip live | broadway smoke + manual | 04-05 Task 1 harness; live UAT item 2 | checklist |
| STATUS-03 | notification fires only on →waiting transition and only when unfocused (policy fn) | unit + manual | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_attention.py -k notify -x -q` | ❌ Wave 0 (04-02 Task 3) |
| RAM-04 | should_autosuspend: ready+threshold yes; running/waiting NEVER; config parse defaults | unit | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_attention.py -k suspend -x -q` | ❌ Wave 0 (04-02 Task 3) |
| RAM-04 | suspended-task resume feeds `claude --continue` (AGENT_RESUME_FEED bytes constant) | unit + manual | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_session.py -x -q` | ✅ extend (04-04 Task 1) |
| crit. 3 | real approval → orange ≤1s; TUI redraw → no false orange; approve → clears | manual-only (live claude UAT — the phase gate) | — | checklist (04-05 Task 2 item 3) |

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | STATUS-01 | T-04-01/02/03/04 | hook never blocks claude (exit 0 always); atomic write; env-guard no-op | integration (subprocess) | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_hook_script.py -x -q` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 1 | STATUS-01 | T-04-05 | extra_env never leaks into argv; TERM_ENV immutable | unit | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_spawn_argv.py -x -q` | ✅ extend | ⬜ pending |
| 04-02-01 | 02 | 1 | STATUS-01, STATUS-02 | T-04-06/07/11 | hostile term_id → flat leaf; tolerant reads; symlink-safe wipe | unit | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_attention.py -x -q` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | STATUS-01 | T-04-08 | additive idempotent merge; user hooks byte-identical | unit | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_attention.py -k "merge or install or hook_command or marker" -x -q` | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 1 | STATUS-03, RAM-04 | T-04-09/10 | running/waiting never suspend; safe config defaults (suspend OFF) | unit | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_attention.py tests/test_session.py -x -q` | ❌ W0 / ✅ extend | ⬜ pending |
| 04-03-01 | 03 | 2 | STATUS-01 | T-04-12/13 | consent gate; backup + atomic settings write; unparseable → never write | smoke (parse + suite + greps) | `python -c "ast.parse(...)"` + full suite | ✅ (suite) | ⬜ pending |
| 04-03-02 | 03 | 2 | STATUS-01, STATUS-02 | T-04-15 | env injection agents-only; O(1) tolerant monitor handler | smoke (parse + suite + greps) | same + greps (`ARDUIS_STATE_FILE`, `arduis-dot-waiting`) | ✅ (suite) | ⬜ pending |
| 04-03-03 | 03 | 2 | STATUS-03 | T-04-14/16 | escaped notification body; deletions ONLY via `_clear_task_state_files` | smoke (parse + suite + greps) | same + D-10 deletion grep | ✅ (suite) | ⬜ pending |
| 04-04-01 | 04 | 3 | RAM-04 | T-04-20 | resume feed is a bytes LITERAL (no interpolation) | unit | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_session.py -x -q` | ✅ extend | ⬜ pending |
| 04-04-02 | 04 | 3 | RAM-04 | T-04-18/22 | suspend only calm aggregates via tested gate; suspension never silent | smoke (parse + suite + greps) | ast.parse + full suite + single-call-site grep | ✅ (suite) | ⬜ pending |
| 04-04-03 | 04 | 3 | STATUS-01 (degraded, D-13) | T-04-19/21 | bell hint lower-confidence ("esperando?"); 1s throttle; no auto-suspend in degraded | smoke (parse + suite + greps) | ast.parse + full suite + greps | ✅ (suite) | ⬜ pending |
| 04-05-01 | 05 | 4 | all | T-04-23/24 | sandbox HOME (real settings.json untouched, mtime asserted); broadwayd killed in finally | integration (broadway harness, /tmp) | full suite + harness pass/fail log | ✅ (suite) | ⬜ pending |
| 04-05-02 | 05 | 4 | all | — | live UAT of the five phase criteria + A1/A2/D-03 flags | manual checkpoint | — | — | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

The "Wave 0" test gaps land INSIDE the wave-1 TDD plans' RED steps (both wave-1 plans are
`type: tdd` — tests are written failing-first, no separate Wave 0 plan needed):

- [ ] `tests/test_hook_script.py` — subprocess round-trip of the hook script (STATUS-01) — created RED-first in **04-01 Task 1**
- [ ] `tests/test_attention.py` — state map, aggregation, merge, notify/suspend policy, config (STATUS-01/02/03, RAM-04) — created RED-first in **04-02 Tasks 1–3**
- [ ] extend `tests/test_spawn_argv.py` — extra_env injection, argv unchanged (STATUS-01) — **04-01 Task 2**
- [ ] extend `tests/test_session.py` — TerminalRecord status fields appended last (04-02 Task 3); AGENT_RESUME_FEED + Task.auto_suspended (04-04 Task 1)

---

## Manual-Only Verifications

All items below are exercised in 04-05 (Task 1 = headless broadway smoke; Task 2 = blocking
human-verify checkpoint on a real display):

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dots render in sidebar + pane header and flip live | STATUS-02 | real GTK rendering | 04-05 Task 1 check (b) headless; live UAT item 2 |
| Real approval → orange ≤1s; TUI redraw → NO false orange; approve → clears (phase gate) | STATUS-01/02 (crit. 3) | only provable against a real claude TUI | 04-05 Task 2 item 3 (+ A1: pending approval >60s never downgraded by idle_prompt) |
| SessionStart dot color — expected CIANO (ready), not VERDE | STATUS-01 (D-03) | live claude behavior; research-vs-CONTEXT wording conflict | 04-05 Task 2 item 2 [UAT-D03]; VERDE-correct → record as D-03 deviation in SUMMARY |
| Esc-interrupt behavior (Stop firing / idle_prompt self-heal) | STATUS-01 (A2) | live claude TUI interaction | 04-05 Task 2 item 2 [UAT-A2] |
| Desktop notification arrives unfocused, suppressed focused, replace-id no stacking | STATUS-03 | needs a real notification daemon + window focus | 04-05 Task 2 item 4 |
| Auto-suspend live + `--continue` resume restores the conversation | RAM-04 | needs a real claude conversation + RAM observation | 04-05 Task 2 item 5 |
| Degraded bell mode ("esperando?" badge + "status limitado" hint) | STATUS-01 (D-13) | live terminal BEL + GTK | 04-05 Task 2 item 6 |
| User's own hooks (GSD, notify-send) still fire; arduis hook no-op outside arduis | STATUS-01 (D-01/D-02) | requires the user's real settings + an outside-arduis claude session | 04-05 Task 2 item 1 |
| No orphan zsh/claude on app close; status dir clean next launch | RAM-04 / Pitfall 5 | process-table inspection | 04-05 Task 2 item 7 |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (every auto task carries an `<automated>` command; the only manual item is the 04-05 checkpoint)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test_hook_script.py + test_attention.py created RED-first in the wave-1 TDD plans)
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
