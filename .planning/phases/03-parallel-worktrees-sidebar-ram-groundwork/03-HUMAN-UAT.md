---
status: partial
phase: 03-parallel-worktrees-sidebar-ram-groundwork
source: [03-VERIFICATION.md]
started: 2026-06-09T20:43:12Z
updated: 2026-06-09T20:43:12Z
---

## Current Test

[user accepted the phase to close it; a "worktree = workspace of terminals" redesign is planned as a future phase]

## Tests

### 1. PAR-01 — parallelism
expected: Creating 3+ worktrees via `＋` opens each new agent BESIDE the previous (focused pane splits, D-03); all terminals stay live.
result: pending — not exhaustively walked (behavior slated for rework by the workspace redesign)

### 2. PAR-02 / D-05 / D-07 — sidebar
expected: Sidebar lists every worktree (green dot) + the pinned `main` row; right-click → Hibernar greys the dot (#6272a4) and dims the row; Retomar restores.
result: pending — main row + repo name confirmed; hibernate/resume visual not exhaustively walked

### 3. D-06 — focus-or-swap
expected: Clicking a visible row focuses its terminal (purple ring); closing a pane then clicking that row swaps it into the focused pane (close = hide, not destroy).
result: pending — behavior slated for rework by the workspace redesign

### 4. LAYOUT-01 / D-04 — free layout
expected: Drag a GtkPaned divider (panes resize, min ~240×120); ⌥ Layout grid 2×2 / columns presets; ⊞ zoom toggle.
result: pending — not exhaustively walked

### 5. PAR-03 / D-09 — prefix keys
expected: Normal typing not eaten; C-Space then h/j/k/l moves pane focus; C-Space n/p cycles worktrees; C-Space 2 jumps to the 2nd row.
result: pending — not exhaustively walked

### 6. RAM-03 / D-14 — live RAM
expected: Each active row shows `claude · <RAM>` updating ~2s; footer `N agentes ativos · <total> RAM` (count green); no ~2s hitching.
result: pending — not exhaustively walked

### 7. RAM-02 / D-15 / D-16 — active cap
expected: At 6 active, `＋` blocks with the `Você está com N agentes ativos` prompt + chooser; picking one hibernates it then creation proceeds; cancel → no new worktree.
result: pending — not exhaustively walked

### 8. teardown — no orphans
expected: Closing the window leaves no arduis-spawned `zsh`/`claude` (pgrep clean).
result: pending — not exhaustively walked

### 9. UAT fix — main shell cwd + repo name
expected: Launched from a repo, the pinned `main` terminal opens in the repo root (not $HOME) and the sidebar shows the repo name.
result: passed — confirmed by user (launched from /tmp/caramelo, terminal opened there; sidebar shows repo name)

### 10. UAT fix — empty-repo guard
expected: `＋` in a repo with no commits shows "Este repositório ainda não tem commits. Faça um commit antes de criar worktrees." instead of git's raw error.
result: passed — confirmed (reproduced `fatal: invalid reference: HEAD` on an empty repo; guard added + tested)

## Summary

total: 10
passed: 2
issues: 0
pending: 8
skipped: 0
blocked: 0

## Gaps

(none blocking — the user accepted the phase to close it; checks 1–8 cover an interaction model that the planned "worktree = workspace of terminals" phase will redesign, so exhaustive sign-off here was deferred by decision, not by failure)
