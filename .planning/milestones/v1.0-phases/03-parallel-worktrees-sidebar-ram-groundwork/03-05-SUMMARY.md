---
phase: 03-parallel-worktrees-sidebar-ram-groundwork
plan: 05
subsystem: window-presentation
tags: [gtk4, vte, tmux-prefix, event-controller-capture, ram-poll, proc-rss, active-cap, dracula]
requires:
  - "arduis.keymap.dispatch + PREFIX_KEYVAL/PREFIX_MODS (Plan 03-02 — C-Space prefix dispatch contract)"
  - "arduis.resource_monitor.group_rss_kb + format_ram_kb (Plan 03-03 — /proc RSS + pt-BR RAM)"
  - "arduis.caps.at_cap + ACTIVE_CAP_DEFAULT (Plan 03-03 — active-agent cap policy)"
  - "arduis.window sidebar + nested Gtk.Paned canvas (Plan 03-04 — the shell this builds on)"
provides:
  - "src/arduis/window.py — capture-phase C-Space prefix state machine wired to keymap.dispatch (h/j/k/l focus, n/p worktree cycle, digit jump)"
  - "~2s GLib.timeout_add_seconds RAM poll writing group RSS onto each active session; row sub-lines + 'N agentes ativos · <total> RAM' footer"
  - "Active-agent cap gate on +New: blocks at ACTIVE_CAP_DEFAULT with a pt-BR prompt-to-hibernate chooser, then proceeds"
  - "⌥ Layout presets (grid 2×2 / columns) + ⊞ zoom toggle"
  - "UAT fixes: main leaf opens in launch repo root (D-07 revised); repo name in sidebar; per-pane badge (zsh/claude); friendly empty-repo guard on +New"
affects:
  - "A future 'worktree = workspace of terminals' phase will redesign the sidebar/canvas interaction model (see .planning/notes / backlog) — much of the focus-or-swap + split-creates-worktree behavior here is slated for rework"
tech-stack:
  added: []
  patterns:
    - "Window-level Gtk.EventControllerKey at PropagationPhase.CAPTURE: returns True ONLY for the prefix keystroke (disarmed) and recognized action keys (armed); every other key returns False so the focused Vte.Terminal gets all normal typing (T-03-12)"
    - "~2s RAM poll via GLib.timeout_add_seconds (NOT a thread — CLAUDE.md); source removed on window close so no poll outlives the window (T-03-13)"
    - "+New routes through caps.at_cap BEFORE add/spawn — no path creates an agent past the cap (T-03-14)"
    - "Synchronous one-shot git rev-parse at startup (via HostRunner seam) to resolve the launch repo before seeding the main leaf"
    - "Born-HEAD pre-check (git rev-parse --verify -q HEAD) gates +New so an empty repo gets a friendly message, not git's raw error"
key-files:
  created:
    - .planning/phases/03-parallel-worktrees-sidebar-ram-groundwork/03-05-SUMMARY.md
  modified:
    - src/arduis/window.py
    - src/arduis/worktree.py
    - tests/test_worktree.py
decisions:
  - "D-07 REVISED on UAT: the pinned 'main' leaf opens in the launch repo's root (its main checkout), not $HOME; falls back to $HOME only when launched outside a repo. The sidebar 'main' row is titled with the repo name."
  - "Pane-header badge reflects the real command: 'zsh' for the main scratch shell, 'claude' for worktree agents (was hardcoded 'claude')."
  - "Empty/unborn-HEAD repos cannot host a worktree; +New shows a friendly pt-BR message instead of git's 'invalid reference: HEAD'."
  - "Directional h/j/k/l focus resolves in tree order (Assumption A2) — geometry-accurate directional focus is a later refinement."
patterns-established:
  - "Capture-phase prefix controller that never steals normal terminal typing"
  - "Off-main-loop-safe ~2s GLib RAM poll bounded to active process groups"
  - "Cap-gate-before-create flow with a prompt-to-hibernate chooser"
requirements-completed: [PAR-03, RAM-02, RAM-03, LAYOUT-01]
duration: ~30min
completed: 2026-06-09
---

# Phase 3 / Plan 05: tmux C-Space prefix + live RAM poll + active-agent cap

**The Phase-3 window is complete: a capture-phase C-Space prefix state machine, a ~2s process-group RAM poll feeding the sidebar + footer, and an active-agent cap that gates +New — plus four UAT-driven fixes that root the main shell in the launched repo and surface the repo name.**

## Performance

- **Duration:** ~30 min (Tasks 1–2) + UAT iteration (3 follow-up fixes)
- **Completed:** 2026-06-09
- **Tasks:** 2/2 code tasks; Task 3 (manual GTK acceptance) accepted by the user (see Verification)
- **Files modified:** 3 (window.py, worktree.py, test_worktree.py)

## Accomplishments

### Task 1 — C-Space prefix state machine + Layout presets + zoom (commit `b144799`)
- Window-level `Gtk.EventControllerKey` at `PropagationPhase.CAPTURE`. `C-Space` arms the prefix; the next key dispatches via `arduis.keymap.dispatch` to `h/j/k/l` (tree-order directional focus), `n/p` (worktree cycle), or digit-jump. Swallows only the prefix + recognized action keys; all other keys pass through to the focused `Vte.Terminal` (T-03-12).
- `⌥ Layout` menu: grid 2×2 / columns presets over the MRU active subset; the existing `⊞` zoom toggle; bottom tmux-hint bar.

### Task 2 — ~2s RAM poll + cap prompt-to-hibernate (commit `c8a32a4`)
- `GLib.timeout_add_seconds(~2, …)` writes `resource_monitor.group_rss_kb` onto each active session, rendering each row's `claude · <RAM>` sub-line and the green-count footer `N agentes ativos · <total> RAM`. Poll source removed on window close (T-03-13).
- `+New` routes through `caps.at_cap(store.all())` BEFORE add/spawn; at the cap it blocks with the pt-BR prompt (`Você está com N agentes ativos` / `Hiberne uma worktree para liberar RAM antes de abrir outra.`) + a `Gtk.DropDown` chooser; the pick is hibernated, then creation proceeds; cancel aborts (T-03-14/D-16).

### UAT-driven fixes (commits `4a5b11f`, `0b28cb9`)
- **D-07 revised:** the pinned `main` leaf now opens in the launch repo root (its main checkout) instead of `$HOME`; falls back to `$HOME` only outside a repo. `_resolve_repo_root` is now a synchronous one-shot at startup (via the HostRunner seam) so the cwd/label are ready before the main leaf is seeded.
- **Repo name in the sidebar:** the `main` row is titled with the repo name (e.g. `caramelo`), sub-line `main · zsh`.
- **Per-pane badge:** `_make_leaf` takes a `badge_label` — `zsh` for the main scratch shell, `claude` for worktree agents (was hardcoded `claude`).
- **Empty-repo guard:** new `worktree.argv_repo_has_commit` + a born-HEAD pre-check at the top of the create flow; an unborn-HEAD repo gets a friendly message instead of git's `fatal: invalid reference: HEAD`.

## Verification

- **Automated:** full suite **51 passed** (50 prior + 1 new `test_repo_has_commit_argv`). `window.py` compiles; all Task 1/2 acceptance greps pass (`PropagationPhase.CAPTURE`, `at_cap`, `agentes ativos`, `Hiberne uma worktree`, `timeout_add_seconds`); `threading`/`asyncio` absent (CLAUDE.md); `Adw.TabView`/`TabBar` absent.
- **Manual (Task 3 human-verify):** the live GTK/keyboard/RAM/cap surface is manual-only per 03-VALIDATION.md. The user confirmed: ✓ main terminal opens in the launched repo (`/tmp/caramelo`), ✓ repo name shows in the sidebar, ✓ empty-repo `+New` now shows the friendly guard. The user **accepted the phase** without exhaustively walking all 8 checks because they are redirecting the interaction model: a follow-up phase will redesign "worktree = a workspace of up to 2 terminals" (sidebar switches workspaces) — which supersedes the current focus-or-swap + split-creates-worktree behavior. Re-testing behavior slated for rework was deemed low-value.

## Notes / follow-ups

- **NEW PHASE PENDING — "worktree = workspace of terminals":** clicking a sidebar row should switch the whole canvas to that worktree's own set of terminals (up to 2), tmux-session style, rather than swapping a single terminal into a shared grid. This contradicts locked Phase-3 decisions PAR-01 (several worktrees visible at once), D-01/D-02 (single shared canvas), D-06 (focus-or-swap), and D-03 (split = new worktree). To be designed via discuss→plan as a dedicated phase.
- Directional `h/j/k/l` uses tree-order (A2); geometry-accurate directional focus is a later refinement.
