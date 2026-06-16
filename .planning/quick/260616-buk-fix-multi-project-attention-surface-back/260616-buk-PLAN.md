---
quick_id: 260616-buk
description: Fix multi-project attention — surface background-project WAITING agents
date: 2026-06-16
source: .planning/CODE-REVIEW-2026-06-15.md (finding #4 High; also closes #6 Low)
decision: PO chose "Notify + keep RAM-polling/auto-suspend for background projects; dots reconcile on switch"
tasks: 1
---

# Quick Task 260616-buk — Plan

## Problem (Finding #4, High — breaks the core "who's waiting" value prop)

With two projects "both alive" (Phase 03.4), the status watcher and RAM poll are scoped to the
ACTIVE project's bundle only:
- `_on_status_event` (window.py:947) looks up only `self._record_by_state_file` (active bundle) →
  a BACKGROUND project's agent entering WAITING is dropped: no notification, no dot, no auto-suspend.
- `_poll_ram` (window.py:4167) iterates only `self._store.all()` (active project) and recomputes the
  status-file path via `_proj_term_id` using the ACTIVE root → background tasks are never RAM-polled,
  re-read, idle-aged, or auto-suspended.
- Same root cause as the already-fixed `_reconcile_orphans`/`_apply_theme`/`_on_close_request`.

Also closes **finding #6**: `_proj_term_id` always uses the active root, so status-file paths derived
for a BACKGROUND task (poll re-read, teardown clear) are wrong.

## Key facts (verified — do not re-derive)
- Records are registered at spawn (window.py:4038) into the THEN-active (= owning) project's bundle,
  keyed by a path namespaced with the OWNING project's root. After switching away the entry persists
  in the owning bundle under the owning-root path.
- `_rebuild_sidebar` (window.py:1429) calls `_refresh_status_ui(task)` per task (line 1478), and
  `_switch_project` calls `_rebuild_sidebar`. **Therefore dot reconcile-on-switch is AUTOMATIC** as long
  as `record.status`/`record.status_ts` are kept current in memory for background projects.
- `_refresh_status_ui(task)` reads dot/pane widgets via `.get(...)` on the ACTIVE bundle; for a
  background task those return `None`, so it is a harmless no-op on widgets — safe to call for any task.
- `_maybe_notify` uses libnotify (global, fires regardless of active project) but stores the dedup
  handle in `self._notif_by_tid` (active bundle).

## Decision (locked)
Background WAITING agents fire the desktop notification AND keep RAM-polling/auto-suspend. Sidebar/pane
dots for a background project reconcile automatically when the user switches to it (no per-frame
background widget updates needed). Minimal, faithful to the product promise.

## Task 1 — Route attention across all projects by owning bundle

**Files:** `src/arduis/window.py`, `tests/test_window_attention_multiproject.py` (new)

### 1a. Owning-project helpers
- Add `_project_for_task(self, task) -> Project | None`: return the project in `self._registry.all()`
  whose `store.get(task.task_id)` is `task` (identity/`task_id` match). `None` if not found.
- Add `_proj_term_id_for(self, root: str | None, term_id: str) -> str`: the existing `_proj_term_id`
  logic but parameterized on an explicit root (`return term_id` if `root` falsy, else
  `project_term_id(root, term_id)`). Reimplement `_proj_term_id` to call
  `_proj_term_id_for(self._project_root, term_id)` (behavior unchanged for active-path callers).

### 1b. `_on_status_event` — search all bundles
Replace the active-only lookup with a search across every registered project's bundle:
```python
path = gfile.get_path()
for proj in self._registry.all():
    bundle = self._bundle_for(proj)
    entry = bundle["record_by_state_file"].get(path)
    if entry is not None:
        task, record = entry
        self._apply_state_file(task, record, path)
        return
```
(Bootstrap fallback: if `registry.all()` is empty, keep the current `self._record_by_state_file` path.)

### 1c. `_apply_state_file` / `_maybe_notify` — use the owning bundle's notif store
- `_apply_state_file` keeps updating `record.status`/`status_ts` and calling `_refresh_status_ui(task)`
  (harmless no-op for background widgets) and `_maybe_notify(...)`.
- Parameterize the notif dedup store so a background task dedups in its OWN bundle. Simplest: in
  `_maybe_notify`, resolve the bundle via `proj = self._project_for_task(task)` and use
  `self._bundle_for(proj)["notif_by_tid"]` when `proj` is not None, else `self._notif_by_tid`.
  Do NOT change the notification gating (`attention.should_notify`) — the desktop notification must
  fire for background tasks exactly as for active ones (window unfocused → notify).

### 1d. `_poll_ram` — iterate all projects with the owning bundle + namespace
Refactor the body so it runs per project. For each `proj in self._registry.all()`:
- Use that project's bundle dicts: `bundle = self._bundle_for(proj)`; use
  `bundle["subline_by_sid"]`, `bundle["calm_since"]`, `bundle["record_by_state_file"]`,
  `bundle["activity_ts"]` instead of the `self._*` active-bundle properties.
- Recompute status-file paths with the OWNING root: `self._proj_term_id_for(proj.root, t.term_id)`.
- Iterate `proj.store.all()` instead of `self._store.all()`.
- Collect `to_suspend` across all projects, then suspend AFTER the loop. **Auto-suspend must target the
  correct project**: if `_suspend_task`/hibernate assumes the active project, either (i) only auto-suspend
  tasks of the ACTIVE project for now and leave background auto-suspend to the dot/notify path, OR
  (ii) make suspend project-aware. PREFER (i) if making hibernate project-aware is risky — but the PO
  chose to keep background auto-suspend, so implement (ii) if `_suspend_task` can take/derive the project
  cleanly; if not, document the limitation in the SUMMARY and auto-suspend active-only (still a net win:
  background NOTIFY + dot reconcile both work). Use judgment; do not break the active-project path.
- Keep `SOURCE_CONTINUE` return and the degraded-mode branch (apply the same per-project bundle scoping).

### 1e. `_clear_task_state_files` / `_clear_repo_state_files` — owning namespace (closes #6)
When clearing a task's state files, derive the path with the task's OWNING project root:
`self._proj_term_id_for((self._project_for_task(task).root if self._project_for_task(task) else self._project_root), record.term_id)`
and pop from the owning bundle's `record_by_state_file`. Keep behavior identical for active-project tasks.

### Tests — `tests/test_window_attention_multiproject.py` (GTK-free)
Use the existing seam: `win = ArduisWindow.__new__(ArduisWindow)` with `_display=None` and the minimal
attrs the methods touch (mirror `tests/test_window_projects.py` setup — registry with 2 projects, each a
Task with an agent TerminalRecord, per-project bundles via `_bundle_for`, `_att_config`, `_status_dir`,
`_degraded=False`, `props.is_active` stub False). Assert:
1. **Routing:** register a background project's record at its owning-root path in its bundle; call
   `_on_status_event` with a fake GFile for that path → the BACKGROUND record's `status` flips to the
   state-file value (stub `attention.read_state` to return a WAITING doc). Active-only code would not.
2. **Notify fires for background:** with `props.is_active=False` and a →waiting transition for a
   background task, `_maybe_notify` invokes the notification path (monkeypatch `Notify`/`_HAS_NOTIFY`
   or assert the owning bundle's `notif_by_tid` got a handle). Skip gracefully if `_HAS_NOTIFY` is False
   in the test env — assert no crash and record updated.
3. **Namespace (#6):** `_proj_term_id_for(projB.root, term_id) != _proj_term_id_for(projA.root, term_id)`
   and the poll/clear paths use the owning root (assert the path string contains projB's discriminator).
4. **Poll all projects:** seed a live pgid stub (monkeypatch `resource_monitor.group_rss_kb`) on a
   background task; run `_poll_ram`; assert the background task's terminal `rss_kb` was written and its
   `record_by_state_file` re-read ran (status updated) — proving the loop covered the background project.
5. **Reconcile-on-switch is automatic:** after a background record's status is WAITING, calling
   `_rebuild_sidebar`/`_refresh_status_ui` for that task (once it is active) colors the row dot waiting
   (assert `_dot_css_for(WAITING, True) == "arduis-dot-waiting"`; a light check that the path is wired).

Do NOT fabricate tests that don't exercise the change. If a specific assertion genuinely needs GTK,
note it as manual and keep the GTK-free ones real.

## Verification
- `/tmp/arduis-venv/bin/python -m pytest` → all green (≥443 + new). Report exact count.
- Active-project behavior byte-identical (existing attention/poll/close tests still pass).
- Update `.planning/CODE-REVIEW-2026-06-15.md`: mark #4 FIXED and #6 FIXED.
