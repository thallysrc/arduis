---
phase: 3
slug: parallel-worktrees-sidebar-ram-groundwork
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-09
validated: 2026-06-15
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | none — existing `tests/` directory, run via `python -m pytest` |
| **Quick run command** | `python -m pytest tests/ -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

> Planner fills this with concrete task IDs. The GTK-free seams (layout tree, /proc RSS
> parsing, cap logic) carry all logic and are pytest-testable; the live-GTK surface
> (Paned rendering, prefix-key capture under Wayland) is manual acceptance.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 3-01-01 | 01 | 0 | LAYOUT-01, PAR-01, PAR-02 | — | N/A | unit | `python -m pytest tests/test_layout.py -q` (9 tests) | ✅ | ✅ green |
| 3-01-02 | 01 | 0 | RAM-03 | — | N/A | unit | `python -m pytest tests/test_resource_monitor.py -q` (6 tests) | ✅ | ✅ green |
| 3-01-03 | 01 | 0 | RAM-02 | — | N/A | unit | `python -m pytest tests/test_caps.py -q` (9 tests) | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

> **Post-execution reconcile (2026-06-15):** All three Wave-0 test files were created during
> execution and pass green (24 tests total). `tests/test_layout.py::test_focus_or_swap`
> additionally covers **PAR-02** (sidebar focus-or-swap), which was originally scoped as
> manual-only — automatable coverage exceeded the plan. The GTK-free seams (layout tree,
> /proc RSS parsing including the comm-with-parens parse trap, cap union across projects) are
> fully sampled. Only true live-GTK/display/keyboard behaviors remain manual (below).

---

## Wave 0 Requirements

- [x] `tests/test_layout.py` — binary split/leaf tree mutations (split focused, close+collapse parent, visible-leaf set) for LAYOUT-01, PAR-01, PAR-02
- [x] `tests/test_resource_monitor.py` — `/proc/<pid>/smaps_rollup` + `statm` parsing, process-group enumeration via pgid, comm-with-parens parse trap fixture for RAM-03
- [x] `tests/test_caps.py` — active-agent cap policy (at-cap detection, prompt-to-hibernate trigger, union across projects) for RAM-02
- [x] Existing `tests/` infrastructure (session, spawn argv, theme, host_runner) covers the reused seams

*The GTK-free seams are the Nyquist sampling surface; the planner must create these Wave 0 test files before the implementation tasks that depend on them.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Splitting/dragging/closing panes renders correctly in nested `Gtk.Paned` | LAYOUT-01, PAR-01 | Live GTK rendering — needs a display | Launch app, create 3+ worktrees, split/drag dividers, close a pane, confirm tree collapses |
| Sidebar row select focuses-or-swaps the worktree into a pane | PAR-02 | Live GTK widget focus | Select sidebar rows for visible and hidden worktrees; confirm D-06 focus-or-swap |
| `C-Space` prefix + `h/j/k/l` / next-prev / jump-by-number switching | PAR-03 | Live keyboard input capture | Arm prefix, test directional focus move, worktree cycling, jump-by-number |
| Per-worktree RSS sub-line + aggregate footer update ~2s | RAM-03 | Live UI render of polled value | Open worktrees with running agents; confirm RSS numbers populate and footer aggregates |
| At-cap prompt-to-hibernate when opening a new worktree | RAM-02 | Live dialog interaction | Reach the cap, attempt `+New worktree`, confirm hibernate-one prompt blocks until resolved |

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
| Gaps found | 0 (all Wave-0 tests created during execution) |
| Resolved | 3 task rows reconciled to ✅ green (24 tests) |
| Escalated | 0 |

No MISSING automated gaps — the auditor was not needed. The VALIDATION.md was stale (drafted
at plan-time, never reconciled after execution shipped the Wave-0 tests). Reconciled the
per-task map, Wave-0 checklist, and sign-off to reflect the green automated surface. PAR-02
coverage (`test_focus_or_swap`) promoted from manual-only to automated.
