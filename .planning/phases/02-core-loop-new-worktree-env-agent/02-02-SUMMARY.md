---
phase: 02-core-loop-new-worktree-env-agent
plan: 02
subsystem: ui
tags: [gtk4, libadwaita, vte, adw-tabview, gio-subprocess, git-worktree, pygobject]

# Dependency graph
requires:
  - phase: 01-terminal
    provides: "HostRunner no-op seam, Dracula palette, spawn argv builder, no-orphan close-request teardown (SIGHUP→SIGKILL pgid)"
  - phase: 02-core-loop-new-worktree-env-agent (02-01)
    provides: "GTK-free domain: worktree.py git-argv/parse builders, serializable SessionStore + WorktreeSession, AGENT_FEED, hibernate_fields"
provides:
  - "Adw.TabView/TabBar core-loop UI replacing the single Phase-1 terminal (tab 0 = $HOME scratch shell, unchanged)"
  - "git_service.run_git_async — Gio.Subprocess async runner executing worktree.py argv off the GTK loop (the one new thin gi service module)"
  - "+New worktree dialog (type-or-pick branch), async create via `git worktree add` off the auto-detected default branch into a sibling dir"
  - "spawn+feed: each worktree tab spawns zsh -l -i in the worktree dir and feeds b'claude\\n' as bytes"
  - "Right-click Hibernate/Resume context menu killing/relaunching the agent process GROUP (RAM-01), keeping the directory"
  - "Generalized no-orphan window-close teardown across all active sessions"
affects: [phase-3-sidebar-ram, phase-4-attention-detection, phase-5-agent-swap-themes]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Presentation→Domain→Service: window.py orchestrates; worktree.py builds argv (pure); git_service.run_git_async executes async"
    - "async git via Gio.Subprocess + communicate_utf8_async (on_done fires on GLib main loop — safe to mutate widgets/SessionStore), no threading/asyncio"
    - "feed-after-spawn: terminal.feed_child(AGENT_FEED) inside the spawn_async callback once pid arrives"
    - "process-GROUP teardown (os.killpg SIGHUP → SIGKILL grace sweep) reused for hibernate AND window-close"

key-files:
  created:
    - src/arduis/git_service.py
    - docs/PHASE2-ACCEPTANCE.md
  modified:
    - src/arduis/spawn.py
    - src/arduis/window.py
    - tests/test_spawn_argv.py
    - run.sh

key-decisions:
  - "git_service.py is the ONE new thin gi-importing service module; window.py stays the only presentation gi module; worktree.py/session.py remain GTK-free"
  - "build_worktree_spawn reuses SHELL_ARGV/TERM_ENV (cwd is a spawn_async argument, not part of argv) — separate name documents intent + gives a unit-test handle"
  - "Resume is a cold relaunch (fresh spawn+feed), not a PTY reattach — reattach deferred to v2 (PERSIST-01)"
  - "run.sh must NOT cd into the repo — preserves the launch cwd so D-03 (+ disabled outside a git repo) resolves correctly"

patterns-established:
  - "argv funnel: every host argv routes through HostRunner.wrap_argv (single seam, no shell, no shell=True)"
  - "sibling-dir path computed only by worktree.py's tested sanitize/worktree_dir_for — window.py never builds the path from raw dialog input"
  - "--force is never emitted; porcelain pre-check (branch_checked_out_path) gates creation (focus existing / clear abort)"

requirements-completed: [WT-01, WT-02, WT-03, RAM-01]

# Metrics
duration: ~multi-session (executor + human-verify continuation)
completed: 2026-06-09
---

# Phase 2 Plan 02: GTK Core-Loop Wiring Summary

**Adw.TabView core loop wiring the Plan-01 domain into the live app: a "+New worktree" dialog creates a worktree via async `git worktree add` off the auto-detected default branch and opens a tab whose VTE terminal spawns `zsh -l -i` in the worktree dir and feeds `claude` as bytes, with right-click Hibernate/Resume process-group teardown (RAM-01) and a generalized no-orphan close.**

## Performance

- **Duration:** Multi-session (autonomous Tasks 1-3 + a blocking human-verify checkpoint resolved on the main worktree)
- **Completed:** 2026-06-09
- **Tasks:** 3 implementation tasks + 1 human-verify checkpoint (approved)
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments
- Replaced the single Phase-1 terminal with an `Adw.TabView` + `Adw.TabBar`; tab 0 remains the unchanged `$HOME` scratch shell (D-02, zero regression).
- "+New worktree" button (disabled with a hint outside a git repo, D-03) opens a type-or-pick branch dialog; new name = new branch, pick = existing.
- Async create flow: default-branch auto-detection (origin → local fallback), sibling-dir computation, porcelain pre-check that focuses an existing tab or aborts with a clear message — **never `--force`** (D-07).
- Each worktree tab spawns `zsh -l -i` in the worktree dir and feeds `b"claude\n"` after the pid arrives (WT-03); a missing `claude` leaves a usable shell (D-09).
- Right-click Hibernate kills the agent process **group** (SIGHUP→SIGKILL grace sweep), dims the tab, and KEEPS the directory; Resume cold-relaunches (RAM-01). Window-close teardown generalized across all active sessions (no orphans).
- New thin `git_service.run_git_async` (Gio.Subprocess + `communicate_utf8_async`, no threading/asyncio) keeps git off the GTK loop and routes argv through `HostRunner`.

## Task Commits

Each task was committed atomically:

1. **Task 1: git_service.py async git runner + spawn.py per-worktree cwd** - `f3ae6fb` (feat)
2. **Task 2: Adw.TabView core loop — +New worktree dialog, async create, feed claude** - `db3b4bd` (feat)
3. **Task 3: Phase 2 manual acceptance checklist (SC#2/#3/#4)** - `55f6534` (docs)

**Checkpoint fix (during human-verify):** `058af28` (fix) — `run.sh` must not `cd` into the repo, so D-03 correctly disables the "+New worktree" button outside a git repo. This resolved the single acceptance failure the user found.

## Files Created/Modified
- `src/arduis/git_service.py` - The one new thin gi service module: `run_git_async` runs worktree.py argv via Gio.Subprocess off the GTK loop, on_done on the main loop, routed through `HostRunner.wrap_argv`.
- `src/arduis/spawn.py` - Added `build_worktree_spawn(runner)` reusing SHELL_ARGV/TERM_ENV (cwd passed to spawn_async by the caller).
- `src/arduis/window.py` - Rewired `ArduisWindow` to host the `Adw.TabView`/`TabBar`, + button + new-worktree dialog, async create + spawn+feed, Hibernate/Resume context menu (`Gio.SimpleAction` + `set_menu_model`), `_teardown_pgid` helper, generalized `_on_close_request`.
- `tests/test_spawn_argv.py` - Added `test_build_worktree_spawn_matches_shell` (asserts the shell argv/env and that `flatpak-spawn` is absent).
- `docs/PHASE2-ACCEPTANCE.md` - Manual acceptance checklist (SC#2/#3/#4 + D-03 disabled-button + no-orphans-on-close), the manual half of D-14.
- `run.sh` - No longer `cd`s into the repo, preserving the launch cwd for D-03.

## Decisions Made
- `git_service.py` is the single new gi-importing **service** module; `window.py` stays the only **presentation** gi module; `worktree.py`/`session.py` remain GTK-free (verified by the import-boundary check in the plan's verification).
- `build_worktree_spawn` reuses the Phase-1 shell argv/env because cwd is a `spawn_async` argument, not part of argv — the separate name documents intent and provides a unit-test handle.
- Resume is a cold relaunch (fresh spawn + re-feed), not a PTY reattach; reattach is deferred to v2 (PERSIST-01).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `run.sh` changed the working directory into the repo, breaking D-03**
- **Found during:** Task 4 (human-verify checkpoint — acceptance step 6, the negative "+ disabled outside a git repo" case)
- **Issue:** `run.sh` `cd`'d into the repo before launching arduis, so the launch cwd was always inside a git repo — the "+New worktree" button never disabled when arduis was started from a non-git directory, failing SC D-03.
- **Fix:** Removed the `cd` so the launch cwd is preserved and `git rev-parse --show-toplevel` correctly reports no repo, disabling the + button with its hint tooltip.
- **Files modified:** run.sh
- **Verification:** User re-ran the acceptance checklist; the + button is now disabled with a hint when launched outside a git repo (D-03 PASS).
- **Committed in:** 058af28

---

**Total deviations:** 1 auto-fixed (1 bug, surfaced by manual acceptance).
**Impact on plan:** The fix was necessary for the D-03 success criterion. No scope creep.

## Issues Encountered
- None during planned implementation. The only acceptance failure (the `run.sh` cwd bug above) was caught by the manual human-verify checkpoint and fixed in `058af28`.

## Checkpoint: Human-Verify — APPROVED

Task 4 was a `checkpoint:human-verify` (gate: blocking) — the GUI/teardown behaviors are manual-acceptance per D-14 / VALIDATION.md (no Wayland GUI harness). The user manually executed `docs/PHASE2-ACCEPTANCE.md` and **approved**:

- SC#2 — new worktree tab opens with `claude` running (WT-01/02/03): **PASS**
- SC#3 — already-checked-out branch handled gracefully, never `--force` (D-07): **PASS**
- SC#4 — Hibernate frees RAM + keeps dir, Resume relaunches (RAM-01): **PASS**
- No orphans on window close (D-13): **PASS** (the orchestrator also proved the `os.killpg` group-teardown primitive via an automated test)
- "+" disabled outside a git repo (D-03): **PASS** (after the `run.sh` fix `058af28`)

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- The product's heart ("+New worktree → env → agent in seconds") is live end-to-end; WT-01/WT-02/WT-03/RAM-01 delivered.
- The GTK-free, serializable `SessionStore` is wired as the single source of truth for worktree tabs — ready for Phase 3's sidebar binding and ResourceMonitor/RSS visibility.
- The process-group teardown primitive (`_teardown_pgid`) is reusable for Phase 4's idle auto-suspend.

## Self-Check: PASSED

- Commits confirmed present: `f3ae6fb`, `db3b4bd`, `55f6534`, `058af28` (verified via `git log --oneline`).
- Files confirmed on disk: `src/arduis/git_service.py`, `src/arduis/spawn.py`, `src/arduis/window.py`, `tests/test_spawn_argv.py`, `docs/PHASE2-ACCEPTANCE.md`.
- Full test suite GREEN: `25 passed`.
- Human-verify checkpoint: approved by user.

---
*Phase: 02-core-loop-new-worktree-env-agent*
*Completed: 2026-06-09*
