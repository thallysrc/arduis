---
phase: 06-per-worktree-setup-via-arduis-toml
plan: 02
subsystem: ui
tags: [gtk4, libadwaita, vte, trust-gate, setup, feed_child, adw-alertdialog, security, composition]

requires:
  - phase: 06-per-worktree-setup-via-arduis-toml
    provides: repoconfig.load_repo_setup + setup_feed_bytes + trust.setup_hash/is_trusted/record_trust (Plan 01 GTK-free domain)
  - phase: 05-agent-swap-and-themes
    provides: feed_child agent-feed path + agentconfig command resolution (cloned for the shell setup feed)
  - phase: 04-attention-detection
    provides: _present_hook_consent Adw.AlertDialog consent pattern (mirrored for the setup trust gate)
provides:
  - "window.py _run_repo_setups — CREATE-only per-repo [setup] gather; trusted repos feed silently, untrusted collected for the gate (ENV-02, criterion 4)"
  - "window.py _present_setup_trust — ONE consolidated Adw.AlertDialog showing exact commands per repo (Confiar e rodar / Pular), record_trust+feed on accept, nothing on skip (D-08)"
  - "window.py _feed_repo_setup — cd-guarded setup_feed_bytes fed into the task SHELL terminal {task}:t1 only, never the agent {task}:t0 (Pitfall 1/2, D-06 best-effort)"
affects: [Phase 6 Plan 03 headless broadway smoke + live UAT, Phase 7 containers (shares .arduis.toml)]

tech-stack:
  added: []
  patterns:
    - "Composition-layer wiring: window.py imports the GTK-free domain modules (repoconfig, trust) and threads them into the create chain — zero new mechanisms"
    - "Content-hash trust gate at the UI: untrusted (repo_realpath, hash) always routes through a verbatim-command disclosure dialog before any byte reaches the PTY"
    - "Best-effort setup feed: None-check the shell terminal + try/except the feed so a missing terminal or feed error never crashes task creation or blocks the agent (D-06)"

key-files:
  created: []
  modified:
    - src/arduis/window.py

key-decisions:
  - "Setup feed lands in {task}:t1 (plain login shell), never {task}:t0 (agent claude TUI) — the security+correctness boundary (T-06-08, Pitfall 2)"
  - "_run_repo_setups is called ONLY from _finalize_task_creation; _resume_task touches _build_task_workspace+_spawn_task_terminals but never finalize, so setup is structurally unreachable on resume (Pitfall 3)"
  - "repo_id = os.path.realpath(self._member_repo_path(repo.repo_name)) — the repo SOURCE dir on this machine (D-09), passed opaquely to trust.py; the worktree-copy .arduis.toml is what is READ for commands"
  - "Dialog responses are the literal strings 'trust' (Confiar e rodar, SUGGESTED+default) and 'skip' (Pular, close-response); only the 'trust' branch record_trusts + feeds"

patterns-established:
  - "UI trust gate mirrors _present_hook_consent verbatim: Adw.AlertDialog + add_response + set_response_appearance(SUGGESTED) + set_default_response + set_close_response + connect('response')"

requirements-completed: [ENV-02]

duration: 6 min
completed: 2026-06-13
---

# Phase 6 Plan 02: Trust-Gated Setup Feed Wired into Task Create Summary

**Wired the Wave-1 `repoconfig`/`trust` domain into `window.py`: on CREATE-finalize only, each succeeded repo's `[setup]` is read from its worktree, already-trusted (repo-realpath, content-hash) repos feed silently into the task's SHELL terminal (`{task}:t1`) with a `cd`-guard, and the rest gate behind ONE consolidated `Adw.AlertDialog` showing the exact commands per repo — completing ENV-02 and criterion 4.**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-06-13T15:42:00Z (approx)
- **Completed:** 2026-06-13T15:48:26Z
- **Tasks:** 2 (1 code task + 1 verification task)
- **Files modified:** 1 (`src/arduis/window.py`)

## Accomplishments

- Three new `window.py` methods + one call site complete the only `gi`-touching file of Phase 6 (the composition layer), introducing ZERO new mechanisms.
- The setup feed is content-hash trust-gated and lands in the SHELL terminal `{task}:t1` only — never the agent `{task}:t0` TUI (mitigates T-06-08).
- Full suite stays green at 274 passed (no regression); `arduis.window` imports cleanly under the venv with Gtk/Adw/Vte required.

## The Three New Methods + Call Site

- **Call site:** `_finalize_task_creation` (~line 2177) calls `self._run_repo_setups(task)` immediately after `self._spawn_task_terminals(task)` and before the `if repo_errors:` block. A comment asserts CREATE-only / never `_resume_task` (Pitfall 3).
- **`_run_repo_setups(task)`** — per `repo in task.repos`: `repoconfig.load_repo_setup(repo.worktree_dir)`; empty commands → skip (no gate, the dominant no-op path, criterion 1); else `h = trust.setup_hash(setup.commands)`, `repo_id = os.path.realpath(self._member_repo_path(repo.repo_name))`; if `trust.is_trusted(self._trusted_setups_path, repo_id, h)` → `_feed_repo_setup` silently, else collect `(repo, commands, repo_id, h)`. Non-empty collection → `_present_setup_trust`.
- **`_feed_repo_setup(task, repo, commands)`** — `shell = self._term_by_sid.get(f"{task.task_id}:t1")`; `None` → return; else `shell.feed_child(repoconfig.setup_feed_bytes(repo.worktree_dir, commands))` wrapped in `try/except Exception: pass`.
- **`_present_setup_trust(task, to_confirm)`** — builds a per-repo block (`<repo_name>:` then each command indented), `Adw.AlertDialog(heading="Rodar setup destes repositórios?", body=...)`; responses `"skip"` (Pular, close-response) and `"trust"` (Confiar e rodar, SUGGESTED + default). On `"trust"`: per entry `trust.record_trust(self._trusted_setups_path, repo_id, h)` then `_feed_repo_setup`. On skip/close: nothing (re-prompt next create). `dialog.present(self)`.

## Dialog Response Strings + Terminal Target (for Plan 03's smoke)

- **Response strings:** `"trust"` (label "Confiar e rodar", SUGGESTED, default response) and `"skip"` (label "Pular", close-response). The smoke must emit `dialog.response("trust")` / `dialog.response("skip")` (or activate the corresponding response) — NOT the labels.
- **Shell terminal target:** `self._term_by_sid[f"{task.task_id}:t1"]` (the plain `zsh -l -i`). The agent terminal `{task}:t0` is fed `claude` in `_make_wt_spawn_cb._on_wt_spawned` (kind=="agent") and is never touched by the setup path.
- **Trust file:** `self._trusted_setups_path = os.path.expanduser("~/.config/arduis/trusted_setups.toml")` resolved in `__init__`. The smoke MUST sandbox `HOME` before constructing the window (the `expanduser` runs at init under the sandbox HOME) so the real trust list is never written.
- **CREATE-only:** verified `_resume_task` calls `_build_task_workspace` + `_spawn_task_terminals` but NOT `_run_repo_setups`/`_finalize_task_creation` (grep-confirmed).

## Files Created/Modified

- `src/arduis/window.py` — added `from arduis import ... repoconfig, trust`; `self._trusted_setups_path` in `__init__`; `_run_repo_setups` call in `_finalize_task_creation`; new methods `_run_repo_setups`, `_feed_repo_setup`, `_present_setup_trust`.

## Decisions Made

None beyond the plan — wired exactly as `<plan_decisions>` specified. The plan's code snippets were used verbatim (with PEP8 line-wrapping for the two long method signatures).

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- ENV-02 + criterion 4 complete: a created task's trusted `[setup]` runs visibly in its shell pane; untrusted/changed setups gate behind one consolidated verbatim-command dialog.
- Wave 3 (Plan 03) can now write the headless broadway smoke + live UAT against the three methods. It must: sandbox `HOME` before window construction; drive the dialog via the `"trust"`/`"skip"` response strings; assert the feed targets `{task}:t1` and never `{task}:t0`; assert no setup on resume; assert a garbage `.arduis.toml` and a missing shell terminal never crash creation.
- No blockers. Full suite green (274 passed); window.py parses and imports cleanly.

## Self-Check: PASSED

- `src/arduis/window.py` exists on disk and contains `_run_repo_setups`, `_feed_repo_setup`, `_present_setup_trust` (grep-confirmed).
- Task 1 commit `3ddfe2f` present in git history.
- Full suite: 274 passed, zero regressions; `import arduis.window` succeeds under the venv.

---
*Phase: 06-per-worktree-setup-via-arduis-toml*
*Completed: 2026-06-13*
