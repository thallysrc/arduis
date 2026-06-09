---
phase: 01-terminal
plan: 01
subsystem: testing
tags: [pytest, hostrunner, vte, dracula, waitstatus, tdd, gtk-free]

# Dependency graph
requires: []
provides:
  - "HostRunner seam (no-op native wrap_argv/wrap_env, Flatpak v2 stub that raises)"
  - "Dracula palette constants (16 hex entries + fg/bg/cursor), GTK-free"
  - "decode_exit() raw-waitstatus decoder (exit code / -signum)"
  - "build_spawn_command() GTK-free (argv, env) builder routed through HostRunner"
  - "pytest infrastructure (pyproject.toml discovery, src on pythonpath)"
affects: [01-02 GTK wiring, phase-2 SessionStore, phase-5 themes, phase-9 packaging]

# Tech tracking
tech-stack:
  added: [pytest 9.0.3]
  patterns:
    - "HostRunner seam funnels all host execution; single v2 (DIST-01) re-enable point"
    - "GTK-free core modules (no gi import) so unit suite runs without GTK/Vte"
    - "argv as list literals, never shell strings (no shell=True) — injection-safe"
    - "TDD RED->GREEN per task with atomic test/feat commits"

key-files:
  created:
    - src/arduis/host_runner.py
    - src/arduis/exit_status.py
    - src/arduis/theme.py
    - src/arduis/spawn.py
    - src/arduis/__init__.py
    - tests/test_host_runner.py
    - tests/test_exit_decode.py
    - tests/test_theme.py
    - tests/test_spawn_argv.py
    - tests/__init__.py
    - pyproject.toml
    - .gitignore
  modified: []

key-decisions:
  - "_FLATPAK=False guards a NotImplementedError Flatpak branch — v2 path proven unreachable in v1"
  - "Palette stays GTK-free hex strings; Gdk.RGBA conversion deferred to Plan 02"
  - "pytest installed in a project .venv (--system-site-packages) because host sudo/apt unavailable and pip is PEP-668 externally-managed"

patterns-established:
  - "Seam pattern: HostRunner.wrap_argv/wrap_env is the single host-exec funnel"
  - "GTK-free testable core: zero gi imports in src/arduis/*.py for this plan"
  - "List-literal argv discipline (T-01-01 mitigation)"

requirements-completed: [TERM-01]

# Metrics
duration: ~12min
completed: 2026-06-09
---

# Phase 1 Plan 01: Testable Foundation (Seams + Palette + Spawn Builder) Summary

**Established the GTK-free, unit-tested Phase-1 foundation — HostRunner no-op/Flatpak-stub seam, Dracula palette, raw-waitstatus exit decode, and the spawn argv/env builder — with pytest infrastructure; 15 tests green, zero GTK imports.**

## Performance

- **Duration:** ~12 min
- **Tasks:** 3 completed (Task 0 scaffold + 2 TDD tasks)
- **Files created:** 12
- **Tests:** 15 passing (host_runner 4, exit_decode 3, theme 3, spawn_argv 5)

## Accomplishments
- Pytest infrastructure stood up on a host that lacked pytest (project `.venv` with system site-packages so Plan 02's `gi`/Vte stays importable).
- `HostRunner` seam implemented as a native no-op returning new lists; Flatpak branch raises `NotImplementedError` (threat T-01-03 mitigated, v2 DIST-01 re-enable point isolated).
- Dracula palette lifted verbatim from `src/main.py` into a GTK-free `theme.py` (16 entries + fg/bg/cursor), validated by regex + length.
- `decode_exit` wraps `os.waitstatus_to_exitcode`; verified 0->0, 42->42, SIGINT->-2 against real forked-child raw statuses.
- `build_spawn_command` produces `(["zsh","-l","-i"], ["TERM=xterm-256color"])` through the seam, with no `flatpak-spawn`/`--host` prefix and no `shell=True` (threats T-01-01/T-01-02 mitigated).

## Task Commits

1. **Task 0: pytest config + package/test scaffolding** - `df55843` (chore)
2. **Task 1 (RED): failing tests for HostRunner/exit/theme** - `2dfc75b` (test)
3. **Task 1 (GREEN): HostRunner seam, exit decode, Dracula palette** - `945d1a6` (feat, includes test-helper fix)
4. **Task 2 (RED): failing test for spawn builder** - `ae7e2e5` (test)
5. **Task 2 (GREEN): GTK-free spawn argv/env builder** - `74ce67f` (feat)

_TDD tasks split into test (RED) then feat (GREEN) commits. No standalone refactor commits needed — modules were minimal._

## Files Created/Modified
- `pyproject.toml` - pytest discovery (`testpaths=["tests"]`, `pythonpath=["src"]`, `-q`)
- `src/arduis/__init__.py` - package marker + docstring
- `src/arduis/host_runner.py` - HostRunner seam (no-op native / Flatpak stub)
- `src/arduis/exit_status.py` - `decode_exit` raw-waitstatus wrapper
- `src/arduis/theme.py` - GTK-free Dracula palette constants
- `src/arduis/spawn.py` - GTK-free `build_spawn_command` routed through HostRunner
- `tests/test_host_runner.py` / `test_exit_decode.py` / `test_theme.py` / `test_spawn_argv.py` - unit tests
- `tests/__init__.py` - test package marker
- `.gitignore` - venv/pycache/pytest_cache

## Decisions Made
- Installed pytest in a project `.venv` created with `--system-site-packages`. The host has no pytest, `sudo apt` requires an interactive password, and `pip --user` is blocked by PEP 668 (externally-managed). `--system-site-packages` keeps the distro `gi`/PyGObject visible so Plan 02's GTK/Vte imports still resolve from this venv.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pytest absent on host; installed via project .venv**
- **Found during:** Task 0
- **Issue:** `python3 -m pytest` failed (`No module named pytest`). The plan's `user_setup` expected `sudo apt install python3-pytest` or a venv, but non-interactive sudo is unavailable and `pip install --user` is blocked by PEP 668.
- **Fix:** Created `.venv` with `python3 -m venv --system-site-packages .venv` and installed pytest 9.0.3 into it. Ran the whole suite via `./.venv/bin/python -m pytest`. `.venv/` added to `.gitignore`.
- **Files modified:** `.gitignore` (new)
- **Verification:** `./.venv/bin/python -m pytest --version` -> 9.0.3; full suite green.
- **Committed in:** `df55843` (.gitignore; venv itself is gitignored)

**2. [Rule 1 - Bug] SIGINT test helper exited code 2 instead of dying by signal**
- **Found during:** Task 1 (GREEN run)
- **Issue:** The forked-child helper called `os.kill(pid, SIGINT)`, but Python's default SIGINT handler raised `KeyboardInterrupt`, so the child exited with code 2 (raw status 512) rather than being terminated by the signal — `decode_exit` correctly returned 2, but the test expected -2. The implementation was correct; the test fixture was wrong.
- **Fix:** Added `signal.signal(signum, signal.SIG_DFL)` in the child before `os.kill`, so the signal actually terminates the process and yields the negative-signum decode.
- **Files modified:** `tests/test_exit_decode.py`
- **Verification:** `test_sigint_decodes_to_negative_two` passes; full suite green.
- **Committed in:** `945d1a6` (part of Task 1 GREEN)

---

**Total deviations:** 2 auto-fixed (1x Rule 3 blocking, 1x Rule 1 bug)
**Impact on plan:** Both necessary for correctness/runnability. No scope creep — no new modules or features beyond the plan's interfaces.

## Issues Encountered
- `src/main.py` (source of the Dracula constants in `read_first`) is an untracked draft present only in the main checkout, not this worktree. Constants were read from the main project path and lifted verbatim; no functional impact.

## User Setup Required
- For Plan 02 (GTK wiring): the GTK4 VTE binding is still NOT installed on the host. Plan 02 will need `sudo apt install -y gir1.2-vte-3.91 libvte-2.91-gtk4-0` (or the Arch `vte4` equivalent). Verify with `python3 -c "import gi; gi.require_version('Vte','3.91')"`. This plan deliberately imports no `gi`, so it was not blocked by this.
- Running the test suite uses the project `.venv`: `./.venv/bin/python -m pytest tests/ -v` (or `sudo apt install python3-pytest` to use the system interpreter directly).

## Verification Results
- `./.venv/bin/python -m pytest tests/ -v` -> 15 passed.
- `grep -rL "import gi" src/arduis/*.py` lists all 5 modules (none import gi).
- `pyproject.toml` carries `[tool.pytest.ini_options]` with `pythonpath = ["src"]`.
- `spawn.py` contains no executable `flatpak-spawn`, `--host`, or `shell=True` (only docstring warnings); both `wrap_argv` and `wrap_env` are called.

## Self-Check: PASSED

All 12 created files verified present on disk. All 5 task commits (`df55843`, `2dfc75b`, `945d1a6`, `ae7e2e5`, `74ce67f`) verified in git history. No missing items.
