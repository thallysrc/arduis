---
quick_id: 260616-buk
description: Fix multi-project attention — surface background-project WAITING agents
date: 2026-06-16
status: complete
source: .planning/CODE-REVIEW-2026-06-15.md (finding #4 High; also closes #6 Low)
decision: PO chose "notify + keep background RAM-poll; dots reconcile on switch"
commits:
  - a6ff97f fix(260616-buk): route attention across all projects by owning bundle
tests: 448 passed (443 prior + 5 new)
---

# Quick Task 260616-buk — Summary

## Problem (Finding #4, High — broke the core "who's waiting" value prop)

With two projects "both alive" (Phase 03.4), the status watcher (`_on_status_event`) and RAM poll
(`_poll_ram`) were scoped to the ACTIVE project's bundle only. A BACKGROUND project's agent entering
WAITING was silently dropped — no notification, no dot, no RAM poll, no time-degrade. Same root-cause
class as the already-fixed `_reconcile_orphans` / `_apply_theme` / `_on_close_request`. Also closed
finding #6 (status-file paths for background tasks used the active root, not the owning root).

## Fix (`src/arduis/window.py`)

- **`_on_status_event`** now searches EVERY registered project's `record_by_state_file` bundle for the
  touched path (not just the active bundle) → a background WAITING agent is routed to its owning record.
- **`_poll_ram`** iterates all projects, using each project's own bundle dicts (`subline_by_sid`,
  `calm_since`, `record_by_state_file`, `activity_ts`) and the OWNING-root status-file namespace, so
  background tasks are RAM-polled, re-read, and idle/staleness-degraded.
- **`_maybe_notify`** dedups the libnotify handle in the task's OWNING bundle, so a background WAITING
  fires the desktop notification with the correct one-per-terminal handle.
- New helpers: **`_proj_term_id_for(root, term_id)`** (parameterized namespace; `_proj_term_id` now
  delegates with the active root — unchanged for active callers) and **`_project_for_task(task)`**.
- **`_clear_task_state_files` / `_clear_repo_state_files`** derive the path with the task's OWNING-root
  namespace (closes finding #6).

## Reconcile-on-switch (automatic)
`_switch_project` → `_rebuild_sidebar` → `_refresh_status_ui(task)` already colors each row/pane dot
from the live `record.status`. Because records are now kept current in memory for background projects,
switching to a background project reconciles its dots automatically — no per-frame background widget
updates needed.

## Decision 1d — auto-suspend stays ACTIVE-project-only
`_hibernate_task` is deeply bound to the active bundle's layout/workspace/sidebar maps, so making
background auto-suspend project-aware was judged too risky for a quick task. Background NOTIFY + dot
reconcile-on-switch + background RAM polling all work regardless; background calm-tracking advances
every tick, so a switched-to task auto-suspends promptly. **Follow-up (clean):** project-aware
`_hibernate_task` to enable true background auto-suspend.

## Tests — `tests/test_window_attention_multiproject.py` (5, GTK-free)
Routing (background record flips on status event), notify-fires-for-background (owning-bundle handle),
owning-root namespace (#6), poll-covers-all-projects (background `rss_kb` written + re-read), and
reconcile-on-switch wiring. Existing attention/poll/close/conclude/projects tests pass unchanged.

## Verification
- `/tmp/arduis-venv/bin/python -m pytest` → **448 passed**, ruff clean, 4 pre-existing warnings.
- Active-project behavior byte-identical.
- `.planning/CODE-REVIEW-2026-06-15.md` updated: #4 and #6 → FIXED (committed with the code).
