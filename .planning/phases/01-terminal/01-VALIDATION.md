---
phase: 1
slug: terminal
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-08
validated: 2026-06-15
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (NOT YET INSTALLED — Wave 0) |
| **Config file** | none — add `pyproject.toml [tool.pytest.ini_options]` or `pytest.ini` in Wave 0 |
| **Quick run command** | `python3 -m pytest tests/ -x -q` |
| **Full suite command** | `python3 -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds (pure-Python unit tests, no GTK import) |

**Design constraint:** keep `HostRunner`, the Dracula palette mapping, and exit-decode logic in **GTK-free modules** so unit tests import them without `gi`/GTK. Anything touching `Vte.Terminal`/`Adw.*` directly is manual-acceptance only (rendering, Wayland, interactive signals).

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/ -x -q`
- **After every plan wave:** Run `python3 -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite green AND manual acceptance checklist completed
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

> Seeded from RESEARCH.md Validation Architecture. Planner refines Task IDs/plan/wave columns.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 1-infra | 01 | 0 | TERM-01 | — | Test infra present | infra | `python3 -m pytest --version` | ✅ | ✅ green |
| 1-exit | 01 | — | TERM-01 | — | `os.waitstatus_to_exitcode` decodes exit 0 / 42 / SIGINT → 0 / 42 / -2 | unit | `pytest tests/test_exit_decode.py` (3) | ✅ | ✅ green |
| 1-hr-noop | 01 | — | TERM-01 | — | `HostRunner.wrap_argv`/`wrap_env` identity on native | unit | `pytest tests/test_host_runner.py -k native_noop` (2) | ✅ | ✅ green |
| 1-hr-stub | 01 | — | TERM-01 | — | `HostRunner` Flatpak branch stubbed/unreachable in v1 | unit | `pytest tests/test_host_runner.py -k flatpak_stub` (2) | ✅ | ✅ green |
| 1-argv | 01 | — | TERM-01 | — | Spawn argv = `["zsh","-l","-i"]` + `TERM=xterm-256color` | unit | `pytest tests/test_spawn_argv.py` + `test_host_runner.py` argv tests | ✅ | ✅ green |
| 1-theme | 01 | — | TERM-01 | — | Dracula palette → 16 `Gdk.RGBA` entries (valid `set_colors` size) | unit | `pytest tests/test_theme.py` (3) | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] Install GTK4 VTE binding (dev env: `/tmp/arduis-venv` with `--system-site-packages`)
- [x] Install pytest (venv `/tmp/arduis-venv/bin/python -m pytest`)
- [x] pytest config + test discovery path
- [x] `tests/test_exit_decode.py` — TERM-01 exit/signal decode
- [x] `tests/test_host_runner.py` — native no-op + Flatpak-stub
- [x] `tests/test_spawn_argv.py` — argv/env assembly (requires GTK-free argv helper)
- [x] `tests/test_theme.py` — Dracula palette → 16 RGBA

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Working shell renders host zsh w/ user prompt in Dracula palette | TERM-01 (criterion #1) | Real GTK/VTE rendering | Launch app; confirm prompt + colors |
| `claude` / `gh` / `docker` resolve in embedded terminal | TERM-01 (criterion #2) | Depends on host login-shell PATH + shims | Type `which claude gh docker` in terminal |
| Ctrl+C interrupts; Ctrl+Z + `fg` job control | TERM-01 (criterion #3) | Interactive PTY signals | Run `sleep 100`, Ctrl+C; run again, Ctrl+Z then `fg` |
| Closing window kills shell, no orphans | TERM-01 (criterion #4) | Process-group teardown timing | Close window; `pgrep -af zsh` shows no leftover child |
| Runs under real Wayland on Ubuntu 0.76 + Arch 0.84 | TERM-01 (criterion #5) | Dev session is X11; needs Wayland login | Launch under Wayland on both distros |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 10s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-06-15 (post-execution reconcile)

---

## Validation Audit 2026-06-15

| Metric | Count |
|--------|-------|
| Gaps found | 0 (all referenced tests created during execution) |
| Resolved | 6 task rows reconciled to ✅ green |
| Escalated | 0 |

All TERM-01 automatable behaviors are covered by green tests: exit/signal decode (3),
HostRunner native no-op + Flatpak-stub (4), spawn argv `zsh -l -i` + `TERM` (multiple in
`test_spawn_argv.py`/`test_host_runner.py`), Dracula palette 16-entry/hex (3). The five
manual-only items (live VTE rendering, PATH/shim resolution, interactive Ctrl+C/Ctrl+Z+fg,
no-orphan window-close teardown, real-Wayland launch on Ubuntu 0.76 + Arch 0.84) remain
genuine human/hardware acceptance — tracked in 01-HUMAN-UAT.md. VALIDATION.md was a stale
plan-time draft; reconciled to reflect the shipped green surface.
