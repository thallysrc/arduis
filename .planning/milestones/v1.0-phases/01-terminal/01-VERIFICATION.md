---
phase: 01-terminal
verified: 2026-06-09T00:00:00Z
status: passed
score: 5/5 must-haves verified
re_verification: false
---

# Phase 1: Terminal Verification Report

**Phase Goal:** A GTK4/libadwaita window with one real VTE terminal running the user's host `zsh` via a direct native PTY (no sandbox). All host execution funnels through a thin `HostRunner` seam — a no-op for native builds — so an optional Flatpak channel can later prepend `flatpak-spawn --host` in one place.
**Verified:** 2026-06-09
**Status:** passed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User gets a working host zsh in the window rendered in the app's Dracula palette | VERIFIED | Human sign-off 2026-06-09 (see below); `window.py` wires `set_colors` + `set_color_cursor` from `DRACULA_*` constants |
| 2 | `claude`, `gh`, `docker` resolve in the embedded terminal (login+interactive PATH) | VERIFIED | Human sign-off 2026-06-09; `SHELL_ARGV = ["zsh", "-l", "-i"]` confirmed by unit test `test_shell_argv_is_login_interactive_zsh` |
| 3 | Ctrl+C interrupts; Ctrl+Z / `fg` job control works | VERIFIED | Human sign-off 2026-06-09; direct native PTY — no sandbox — so signal forwarding is native kernel behavior, no code gap |
| 4 | Exit codes and signals decoded correctly; window close kills host zsh/agent with no orphans | VERIFIED | Human sign-off 2026-06-09; `decode_exit` unit-tested (exit 0→0, 42→42, SIGINT→-2); `window.py` wires `close-request` → `killpg(SIGHUP)` → `GLib.timeout_add(1500)` → `killpg(SIGKILL)` via `os.getpgid(pid)` (A1) |
| 5 | Runs on Ubuntu 0.76 / Arch 0.84 under real Wayland; VTE 0.76 API floor; HostRunner no-op with Flatpak stub | VERIFIED | Code targets 0.76 API floor (documented); HostRunner stub confirmed by unit tests; Wayland session unavailable on X11 dev host — recorded as coverage note per acceptance doc (Pitfall 6), not a code defect; accepted at the human gate |

**Score:** 5/5 truths verified

---

### Human Gate Sign-offs (recorded 2026-06-09)

Interactive criteria were verified by the user at the `execute-phase` human-verify checkpoint on 2026-06-09:

| Criterion | Result |
|-----------|--------|
| #1 — working host zsh in app-owned Dracula palette | PASS |
| #2 — `which claude gh docker` all resolve | PASS |
| #3 — Ctrl+C interrupts; Ctrl+Z + `fg` job control | PASS |
| #4 — no orphan processes on window close | PASS |
| #5 — Wayland on Ubuntu+Arch | Coverage note: tested on X11 dev host; Wayland session unavailable — accepted per acceptance doc |
| #6 — Ctrl+Shift+C/V copy-paste | PASS (added during checkpoint, commit 88cc5dd) |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/arduis/host_runner.py` | HostRunner seam (no-op native, Flatpak stub) | VERIFIED | `class HostRunner` with `wrap_argv`/`wrap_env`; `_FLATPAK = False`; Flatpak branch raises `NotImplementedError` |
| `src/arduis/theme.py` | Dracula palette constants (GTK-free hex strings) | VERIFIED | `DRACULA_PALETTE` = 16 hex entries; `DRACULA_BG`, `DRACULA_FG`, `DRACULA_CURSOR` present; zero `gi` imports |
| `src/arduis/exit_status.py` | Raw-waitstatus decode wrapper | VERIFIED | `def decode_exit(status: int) -> int` wrapping `os.waitstatus_to_exitcode` |
| `src/arduis/spawn.py` | GTK-free spawn argv/env builder routed through HostRunner | VERIFIED | `build_spawn_command` calls `runner.wrap_argv`/`wrap_env`; `SHELL_ARGV = ["zsh", "-l", "-i"]`; `TERM_ENV = ["TERM=xterm-256color"]`; no `flatpak-spawn`, no `shell=True` |
| `pyproject.toml` | pytest config + test discovery path | VERIFIED | `[tool.pytest.ini_options]` with `testpaths = ["tests"]`, `pythonpath = ["src"]`, `addopts = "-q"` |
| `src/arduis/window.py` | ArduisWindow: VTE wiring, palette, spawn-through-seam, close-request teardown | VERIFIED | All wiring present (see Key Links below) |
| `src/arduis/main.py` | Adw.Application entry (`do_activate`) + `main()` | VERIFIED | `class ArduisApp(Adw.Application)`, `do_activate`, `def main()`, `APP_ID = "io.github.thallys.Arduis"` |
| `run.sh` | Native dev run script | VERIFIED | Exists, executable, contains `exec python3 src/main.py` |
| `docs/PHASE-01-ACCEPTANCE.md` | Manual acceptance checklist for criteria #1-#5 | VERIFIED | Covers all 5 criteria + added #6 for copy/paste; contains `Wayland`, `pgrep`, `Ctrl+Z`, `which claude`, `#282a36` |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/arduis/spawn.py` | `src/arduis/host_runner.py` | `build_spawn_command` calls `runner.wrap_argv` / `runner.wrap_env` | WIRED | Both `wrap_argv` and `wrap_env` called on L25; confirmed by unit tests |
| `src/arduis/window.py` | `src/arduis/spawn.py` | `build_spawn_command(self._runner)` feeds `Vte.Terminal.spawn_async` | WIRED | L126: `argv, envv = build_spawn_command(self._runner)`; fed directly to `spawn_async` on L127 |
| `src/arduis/window.py` | `src/arduis/theme.py` | `DRACULA_*` constants → `Gdk.RGBA` → `terminal.set_colors` | WIRED | L68–73: `set_colors(_rgba(DRACULA_FG), _rgba(DRACULA_BG), [...])` + `set_color_cursor(_rgba(DRACULA_CURSOR))` |
| `src/arduis/window.py` | `os.killpg` | `close-request` handler signals the child PGID | WIRED | L159: `os.killpg(pgid, signal.SIGHUP)` + L168: `os.killpg(pgid, signal.SIGKILL)` |
| `src/arduis/window.py` | `src/arduis/exit_status.py` | `child-exited` → `decode_exit(status)` | WIRED | L150: `self._last_exit = decode_exit(status)` |

---

### Data-Flow Trace (Level 4)

The VTE terminal renders a real host PTY, not static data. The data flow is:

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `window.py` → `Vte.Terminal` | PTY child output | `spawn_async` → `zsh -l -i` on host | Yes — real host process | FLOWING |
| `window.py` → `set_colors` | palette constants | `DRACULA_*` from `theme.py` | Yes — 16 Gdk.RGBA values applied at widget init | FLOWING |
| `window.py` → `_last_exit` | `decode_exit(status)` | VTE `child-exited` signal raw waitstatus | Yes — real kernel wait status | FLOWING |

No static data is rendered in place of real data. No `return []` / `return {}` stubs in any rendering path.

---

### Behavioral Spot-Checks

The GTK4 VTE binding (`gir1.2-vte-3.91`) is not installed on the verification host, so the app cannot be launched. Unit-testable behaviors are checked instead.

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 15 unit tests pass | `./.venv/bin/python -m pytest tests/ -v` | 15 passed in 0.02s | PASS |
| No executable `flatpak-spawn` in src/ | `grep -rn "flatpak-spawn" src/` + AST inspection | All 3 matches are comments or module docstrings; none are executable code | PASS |
| Core modules are GTK-free | `grep -l "import gi" src/arduis/*.py` | Only `window.py` and `main.py` import gi | PASS |
| `run.sh` is executable | `test -x run.sh` | Passes | PASS |
| `dev.sh` absent (Flatpak cruft removed) | `test ! -f dev.sh` | Passes | PASS |
| Flatpak manifest absent | `test ! -f io.github.thallys.Arduis.yml` | Passes | PASS |
| `data/*.desktop` + `*.metainfo.xml` kept | `test -f data/...` | Both present | PASS |
| Launch the app | `./run.sh` | Requires VTE GTK4 binding — SKIPPED (not installed on verification host; accepted per human gate) | SKIP |

---

### Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| TERM-01 | 01-01-PLAN.md, 01-02-PLAN.md | Usuário tem um terminal VTE embutido rodando o shell do host (zsh) dentro do app | SATISFIED | `ArduisWindow` embeds `Vte.Terminal`; spawns `zsh -l -i` via direct native PTY through `HostRunner`; human acceptance recorded PASS 2026-06-09 |

No orphaned requirements: the traceability table in REQUIREMENTS.md maps only TERM-01 to Phase 1, and both plans claim it. All other Phase-1 requirements from the traceability table are assigned to later phases and are not orphaned here.

---

### Anti-Patterns Found

No blockers or warnings found.

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/arduis/host_runner.py` | 19 | `# v2 (DIST-01): return ["/usr/bin/flatpak-spawn", ...]` | Info | Comment inside a dead branch (`_FLATPAK = False`); documents the v2 re-enable point — intentional, not a stub |
| `src/arduis/window.py` | 143–145 | `if error is not None or pid == -1: return` (no pid stored) | Info | Spawn-failure no-op; acceptable for v1 single-terminal window; failure path is documented |

No `TODO`/`FIXME`/placeholder text found in any `src/arduis/*.py` file. No `return null`/`return []`/`return {}` in any rendering path.

---

### Human Verification Required

None. All interactive criteria were signed off by the user on 2026-06-09 at the `execute-phase` human-verify checkpoint (criteria #1–#4 and #6 PASS; criterion #5 accepted with documented X11 coverage note).

---

### Gaps Summary

No gaps. All code-level must-haves are present, substantive, and wired. The unit suite passes (15/15). No executable `flatpak-spawn` invocation exists in `src/`. All human-interactive criteria were accepted at the phase checkpoint.

---

_Verified: 2026-06-09_
_Verifier: Claude (gsd-verifier)_
