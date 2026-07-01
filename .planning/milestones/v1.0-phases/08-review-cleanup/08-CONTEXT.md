# Phase 08: Review + Cleanup - Context

**Gathered:** 2026-06-14
**Status:** Ready for planning
**Mode:** Autonomous — user delegated, AFK. Decisions adopt the recommended defaults from
08-RESEARCH.md (HIGH-confidence; git 2.43 / gh 2.93 verified live on host). Revisitable at UAT.

<domain>
## Phase Boundary

Close the work loop and the resource loop: read-only DIFF of a worktree's changes, branch/PR
status via git/`gh` (read-only, THROTTLED), and a "Concluir" action with the correct SAFE teardown
order. The worktree-remove half ships on its own; container teardown reuses the Phase-7 channel.

**Out of scope:** any git/gh WRITE except `gh pr create` (opening a PR is the ONE allowed write —
roadmap-sanctioned); deleting branches (conclude keeps the branch — arduis stays read-only on
history); deleting source repos / symlink targets (D-10 from 03.2 holds); the mockup's "Review"
room tab (room tabs are out of v1); merge/rebase/push actions.
</domain>

<decisions>
## Implementation Decisions

### Domain modules (zero new deps)
- **D-01:** New GTK-free modules: `review.py` (git diff argv builders + any parsing), `gh.py` (gh
  argv builders + `--json` parse + auth/absence degrade), and a tiny TTL cache helper. All reuse
  `git_service.run_git_async` (argv-agnostic — `gh` calls go through it verbatim). No new service
  module, no new dependency.
- **D-07:** Add an optional `cwd=` param to `git_service.run_git_async` (backward-compatible) so
  git/gh run in the right repo/worktree dir.

### Read-only diff (REVIEW-01)
- **D-02:** Diff is shown in a READ-ONLY spawned VTE leaf running `git --no-pager diff`
  (`set_input_enabled(False)`), reusing the existing pane/spawn machinery (keeps color/scroll/copy
  for free; beats a GtkTextView). Per-repo on demand ("Ver diff ▸ <repo>"); a 1-repo task is the
  degenerate single entry.

### PR/branch status (REVIEW-02/GIT-01)
- **D-03:** Status (branch ahead/behind + PR state/number/url) rendered in the sidebar task-row
  subline (where RAM `claude · —` already renders) + a manual refresh action. THROTTLE = manual
  refresh + a TTL cache (defaults: git 30s, gh 120s) + in-flight debounce (mirror `_compose_busy`)
  — NOT a poll (gh is network/rate-limited).
- **D-05:** Opening a PR uses `gh pr create` (the ONE allowed write). Reading uses
  `gh pr view/status --json`. Branch ahead/behind via `git rev-list --count`.
- **D-06:** gh not installed / not authed (gh exit code 4 = needs auth) degrades GRACEFULLY —
  show "gh ausente" / "gh não autenticado" in the subline, never crash. git absence likewise.

### "Concluir" — the safe teardown order (REVIEW-03, criterion 4 — load-bearing safety)
- **D-04:** FIXED sequence, composing three already-built channels:
  1. `_teardown_session_terminals` — kill the task's agent/shell process groups (killpg).
  2. `_container_down` — Phase-7 compose-down channel, only if the task had isolation ON.
  3. **Clean-gate:** `git status --porcelain` per repo — if ANY repo is DIRTY, REFUSE to remove;
     surface a confirmation/refusal dialog (NEVER force-delete uncommitted work).
  4. `git worktree remove` (NEVER `--force` — the dirty/locked refusal IS the safety).
  5. `git worktree prune`.
  6. Unlink the task folder's RELATIVE symlinks (the links only — never the targets, D-10) and
     drop the task from the store + sidebar.
  D-10 holds throughout: arduis removes only the task's worktrees in `../<root>-tasks/`, never the
  source repos, symlink targets, or branches.

### Confirm dialog
- The "Concluir" confirm dialog states plainly: removes the task's worktrees, KEEPS the branch and
  the source repos. If any repo is dirty, it blocks with the dirty list (no force path in the UI).
</decisions>

<specifics>
## Specific Ideas
- TDD the GTK-free domain: `tests/test_review.py` (diff argv), `tests/test_gh.py` (gh argv + JSON
  parse + auth-exit-4 degrade), cache TTL/debounce test, and a conclude-order test (assert the
  sequence + the dirty-tree refusal, with mocked git status). window.py wiring (the diff leaf,
  subline status, "Concluir" menu + confirm) is headless-smoke + live UAT.
- The conclude clean-gate is the security-relevant piece (never destroy uncommitted work) — the
  auditor will check there is no `--force` worktree-remove anywhere.
</specifics>

<deferred>
## Deferred Ideas
- Whole-task single combined diff view → per-repo on demand for v1.
- A dedicated "Review" room tab (mockup) → out of v1.
- Merge/rebase/push/branch-delete → out of scope (read-only history).
- Auto-refresh polling of gh → manual refresh + TTL cache for v1.
</deferred>

---

*Phase: 08-review-cleanup*
*Decisions: 7 (autonomous, research-recommended defaults; the safe teardown order D-04 is load-bearing)*
*Ready for: planning (UI hint: yes)*
