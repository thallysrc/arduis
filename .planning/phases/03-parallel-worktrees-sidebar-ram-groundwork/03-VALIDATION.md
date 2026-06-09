---
phase: 3
slug: parallel-worktrees-sidebar-ram-groundwork
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-09
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
| 3-01-01 | 01 | 0 | LAYOUT-01 | — | N/A | unit | `python -m pytest tests/test_layout.py -q` | ❌ W0 | ⬜ pending |
| 3-01-02 | 01 | 0 | RAM-03 | — | N/A | unit | `python -m pytest tests/test_resource_monitor.py -q` | ❌ W0 | ⬜ pending |
| 3-01-03 | 01 | 0 | RAM-02 | — | N/A | unit | `python -m pytest tests/test_caps.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_layout.py` — binary split/leaf tree mutations (split focused, close+collapse parent, visible-leaf set) for LAYOUT-01, PAR-01
- [ ] `tests/test_resource_monitor.py` — `/proc/<pid>/smaps_rollup` + `statm` parsing, process-group enumeration via pgid, comm-with-parens parse trap fixture for RAM-03
- [ ] `tests/test_caps.py` — active-agent cap policy (at-cap detection, prompt-to-hibernate trigger) for RAM-02
- [ ] Existing `tests/` infrastructure (session, spawn argv, theme, host_runner) covers the reused seams

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
