---
phase: 01-terminal
plan: 02
subsystem: gtk-app
tags: [gtk4, libadwaita, vte, pty, dracula, teardown, acceptance]

# Dependency graph
requires:
  - "HostRunner seam (01-01)"
  - "build_spawn_command (01-01)"
  - "decode_exit (01-01)"
  - "Dracula palette constants (01-01)"
provides:
  - "ArduisWindow: GTK4/Adw window with one VTE terminal on a direct native PTY"
  - "ArduisApp(Adw.Application) entry + main(); src/main.py thin shim"
  - "No-orphan teardown (close-request -> killpg SIGHUP -> GLib.timeout SIGKILL)"
  - "child-exited raw-status decode wired to decode_exit"
  - "Native run.sh dev launch path"
  - "Manual Phase-1 acceptance checklist (criteria #1-#5)"
affects: [phase-2 core-loop terminal embedding, phase-3 panes, phase-5 themes, phase-9 packaging]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "GTK imports isolated to window.py/main.py; core seams stay GTK-free"
    - "VTE 0.76 API floor: spawn_async (11-arg PyGObject shape), set_colors, child-exited"
    - "Direct native PTY: zsh -l -i, no flatpak-spawn (HostRunner no-op)"
    - "Teardown signals the child PGID via os.getpgid (A1), never assumes pgid==pid"

key-files:
  created:
    - src/arduis/window.py
    - src/arduis/main.py
    - src/main.py
    - run.sh
    - data/io.github.thallys.Arduis.desktop
    - data/io.github.thallys.Arduis.metainfo.xml
    - docs/PHASE-01-ACCEPTANCE.md
  modified: []

key-decisions:
  - "Built window.py/main.py fresh from plan spec + RESEARCH patterns: the draft src/main.py the plan names as base does not exist in this worktree (untracked draft, main checkout only)"
  - "data/*.desktop + *.metainfo.xml brought into the branch verbatim from the draft (D-15 'keep data/*'); they were untracked in main only"
  - "dev.sh + Flatpak manifest required no git rm — never committed on this branch (native pivot)"

requirements-completed: [TERM-01]

# Metrics
duration: ~6min
completed: 2026-06-09
---

# Phase 1 Plan 02: GTK Wiring — Embedded VTE Terminal Summary

**Wired the GTK4/libadwaita arduis window with one VTE terminal running host `zsh -l -i` over a direct native PTY through Plan-01's tested seams — app-owned Dracula palette, no-orphan SIGHUP->SIGKILL teardown on the child PGID, raw child-exit decode, a native `run.sh`, and the manual Phase-1 acceptance checklist. 15 unit tests still green; runtime/interactive acceptance is a human gate (D-14).**

## Performance

- **Duration:** ~6 min
- **Tasks:** 3 auto tasks complete; Task 4 is a blocking human-verify checkpoint (not yet run)
- **Files created:** 7
- **Tests:** 15 passing (Plan-01 suite untouched in behavior)

## Accomplishments
- `ArduisWindow(Adw.ApplicationWindow)`: `Adw.ToolbarView`/`HeaderBar`/`WindowTitle` chrome (960x620, "arduis"), one `Vte.Terminal`, monospace 11, scrollback 10000, mouse-autohide.
- Spawn through the seam: `build_spawn_command(self._runner)` -> `Vte.Terminal.spawn_async` in the exact 11-arg PyGObject shape (Pitfall 2 — callback is the final positional arg, no `child_setup_data_destroy`/`user_data`). No `flatpak-spawn` prefix (D-02).
- App owns the palette (D-06/D-07): `set_colors(fg, bg, [16 RGBA])` + `set_color_cursor`; `_rgba()` is the only place `Gdk` is touched.
- No-orphan teardown (D-13): `close-request` -> `os.getpgid(pid)` (A1) -> `killpg(SIGHUP)` -> `GLib.timeout_add(1500, ...)` -> `killpg(SIGKILL)`; returns `False` to allow close.
- `child-exited` -> `decode_exit(status)` stored on `self._last_exit`, then `self.close()` (D-12).
- `ArduisApp(Adw.Application)` with `application_id="io.github.thallys.Arduis"`, `do_activate`, `main()`; `src/main.py` is a thin shim re-exporting `arduis.main.main` so `python3 src/main.py` still works (D-15).
- `run.sh` native launch path; `data/*.desktop`/`*.metainfo.xml` kept for Phase 9.
- `docs/PHASE-01-ACCEPTANCE.md`: per-criterion manual checklist (#1-#5) with exact commands, Dracula `#282a36` check, `which claude gh docker`, Ctrl+C / Ctrl+Z+`fg`, `pgrep` no-orphan, exit/signal decode notes, and the X11->Wayland caveat (Pitfall 6) with PASS/FAIL sign-off lines.

## Task Commits

1. **Task 1: GTK4/Adw window + VTE spawn through seams** — `547efaa` (feat)
2. **Task 2: native run.sh + kept desktop/metainfo** — `61bc618` (feat)
3. **Task 3: manual acceptance checklist (#1-#5)** — `048b815` (docs)

_window.py was authored complete in Task 1's file write (it includes the teardown + child-exit wiring that the plan attributes to Task 2); Task 2 therefore committed only `run.sh` + the kept `data/` artifacts. Functionally identical to the plan; the split is the same code, committed once._

## Files Created/Modified
- `src/arduis/window.py` — ArduisWindow: VTE wiring, Dracula palette, spawn-through-seam, no-orphan teardown, child-exit decode (only module importing `gi`)
- `src/arduis/main.py` — ArduisApp(Adw.Application) + `main()`
- `src/main.py` — thin shim: puts `src/` on `sys.path`, delegates to `arduis.main.main`
- `run.sh` — `exec python3 src/main.py` (replaces obsolete Flatpak dev.sh)
- `data/io.github.thallys.Arduis.desktop` / `*.metainfo.xml` — kept for native packaging (Phase 9)
- `docs/PHASE-01-ACCEPTANCE.md` — manual acceptance checklist (D-14)

## Decisions Made
- Authored `window.py`/`main.py` fresh from the plan spec, `<vte_call_shape>`, and RESEARCH Patterns 2-5 because the draft `src/main.py` the plan names as the evolution base does not exist in this worktree (it was an untracked draft present only in the main checkout — see Plan-01 SUMMARY "Issues Encountered"). Output is identical to evolving the draft would have produced.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Draft base files (`src/main.py`, `data/`, `dev.sh`, manifest) absent in worktree**
- **Found during:** Task 1 / Task 2
- **Issue:** The plan treats `src/main.py` as the base to refactor and tells Task 2 to `git rm dev.sh io.github.thallys.Arduis.yml` and verify `test -f data/io.github.thallys.Arduis.desktop`. None of these existed in this worktree — they were untracked drafts in the main checkout only and were never committed to the branch.
- **Fix:** (a) Built `window.py`/`main.py`/`src/main.py` directly from the plan spec + RESEARCH patterns rather than refactoring a non-existent file. (b) Skipped the `git rm` — `dev.sh`/manifest are already absent on the branch. (c) Brought the `data/*.desktop` + `*.metainfo.xml` files in verbatim from the main-checkout draft so the kept-artifact requirement (D-15) and Task 2's `test -f data/...` verify are satisfied.
- **Files modified:** created `data/io.github.thallys.Arduis.desktop`, `data/io.github.thallys.Arduis.metainfo.xml`
- **Verification:** Task 2 automated checks pass (`test -f data/...`, `test ! -f dev.sh`, `test ! -f io.github.thallys.Arduis.yml`); full suite green.
- **Committed in:** `61bc618`

**2. [Rule 3 - Blocking] pytest absent in this worktree (no shared .venv)**
- **Found during:** Setup
- **Issue:** `python3 -m pytest` -> `No module named pytest`; the project `.venv` (gitignored, created in Plan 01) lives in the main checkout, not this parallel worktree.
- **Fix:** Recreated `.venv` with `python3 -m venv --system-site-packages .venv` + `pip install pytest`; ran the suite via `./.venv/bin/python -m pytest`. `.venv/` is already gitignored.
- **Files modified:** none (venv is gitignored)
- **Verification:** `./.venv/bin/python -m pytest tests/ -q` -> 15 passed.
- **Committed in:** n/a (gitignored)

---

**Total deviations:** 2 auto-fixed (both Rule 3 blocking). No scope creep — same modules/artifacts the plan specifies.
**Impact on plan:** Outcome matches the plan's intended end state; only the "evolve an existing draft" mechanic changed (draft absent, so authored from spec).

## Verification Results
- `./.venv/bin/python -m pytest tests/ -v` -> 15 passed (Plan-01 seams unchanged).
- No EXECUTABLE `flatpak-spawn` in `src/`; the only matches are docstrings/comments (window.py docstring "no flatpak-spawn prefix", host_runner.py v2 stub comment) — matches Plan-01's accepted state.
- `window.py` wires `close-request` -> `killpg(SIGHUP)` -> `GLib.timeout_add` -> `killpg(SIGKILL)` and `child-exited` -> `decode_exit`; uses `os.getpgid(pid)` (A1).
- Import graph validated with a mocked `gi` (VTE binding absent on host, expected): `arduis.main.main` callable, `ArduisWindow` defined, `src/main.py` shim re-exports `arduis.main.main`, `APP_ID == io.github.thallys.Arduis`.
- `run.sh` executable, execs `python3 src/main.py`; `dev.sh` + manifest absent; `data/*.desktop`/`*.metainfo.xml` present.
- `docs/PHASE-01-ACCEPTANCE.md` covers criteria #1-#5 with `Wayland`/`pgrep`/`Ctrl+Z`/`which claude`/`#282a36` and 5 sign-off lines.

## Known Stubs
None. No empty/placeholder data flows to UI; the VTE terminal is fully wired to the host PTY.

## Pending Human Verification (Task 4 — blocking checkpoint)
Runtime/interactive acceptance (real GTK/VTE rendering, Ctrl+C, Ctrl+Z+`fg`, no-orphan close, Wayland) cannot be asserted by an automated command on this X11 host with the VTE GTK4 binding absent. Per D-14 this is a human gate: install `gir1.2-vte-3.91 libvte-2.91-gtk4-0`, run `./run.sh`, and walk `docs/PHASE-01-ACCEPTANCE.md` (criteria #1-#4 must PASS; #5 recorded with session type).

## Self-Check: PASSED

All 7 created files verified present on disk. All 3 task commits (`547efaa`, `61bc618`, `048b815`) verified in git history. No missing items.
