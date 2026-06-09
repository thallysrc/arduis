---
phase: 1
slug: terminal
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-08
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
| TBD | TBD | 0 | TERM-01 | — | Test infra present | infra | `python3 -m pytest --version` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | TERM-01 | — | `os.waitstatus_to_exitcode` decodes exit 0 / 42 / SIGINT → 0 / 42 / -2 | unit | `pytest tests/test_exit_decode.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | TERM-01 | — | `HostRunner.wrap_argv`/`wrap_env` identity on native | unit | `pytest tests/test_host_runner.py::test_native_noop -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | TERM-01 | — | `HostRunner` Flatpak branch stubbed/unreachable in v1 | unit | `pytest tests/test_host_runner.py::test_flatpak_stub -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | TERM-01 | — | Spawn argv = `["zsh","-l","-i"]` + `TERM=xterm-256color` | unit | `pytest tests/test_spawn_argv.py -x` | ❌ W0 | ⬜ pending |
| TBD | TBD | — | TERM-01 | — | Dracula palette → 16 `Gdk.RGBA` entries (valid `set_colors` size) | unit | `pytest tests/test_theme.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Install GTK4 VTE binding: `sudo apt install gir1.2-vte-3.91 libvte-2.91-gtk4-0` (also unblocks running the app at all — currently only GTK3 `Vte-2.91` typelib present)
- [ ] Install pytest: `apt install python3-pytest` or venv `pip install pytest`
- [ ] `pyproject.toml` / `pytest.ini` — pytest config + test discovery path
- [ ] `tests/test_exit_decode.py` — TERM-01 exit/signal decode
- [ ] `tests/test_host_runner.py` — native no-op + Flatpak-stub
- [ ] `tests/test_spawn_argv.py` — argv/env assembly (requires GTK-free argv helper)
- [ ] `tests/test_theme.py` — Dracula palette → 16 RGBA

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
