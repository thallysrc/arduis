---
phase: 2
slug: core-loop-new-worktree-env-agent
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-09
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x (in `.venv`, not on PATH) |
| **Config file** | none — invoke via `.venv/bin/python -m pytest` |
| **Quick run command** | `.venv/bin/python -m pytest -q` |
| **Full suite command** | `.venv/bin/python -m pytest` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `.venv/bin/python -m pytest -q`
- **After every plan wave:** Run `.venv/bin/python -m pytest`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

> Filled by the planner as tasks are defined. Every GTK-free seam (git argv builders,
> default-branch fallback, sanitize, porcelain parse, SessionStore CRUD/serialization,
> bytes-feed constant, hibernate model) MUST have an automated unit test. GUI/teardown
> behaviors are manual-acceptance (see below), consistent with Phase-1 D-14.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 2-00-01 | 00 | 0 | WT-01/02/03, RAM-01 | — | N/A | unit | `.venv/bin/python -m pytest tests/test_worktree.py tests/test_session.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_worktree.py` — git argv builders, default-branch fallback (no `origin`), directory-name sanitize, `git worktree list --porcelain` parse, infer new-vs-existing (WT-01, WT-02, WT-03)
- [ ] `tests/test_session.py` — bytes-feed constant (`b"claude\n"`), `SessionStore` CRUD + serialization (GTK-free, RAM fields), hibernate model state (RAM-01)
- [ ] pytest already installed in `.venv` — no framework install needed

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| New worktree tab opens with `claude` running | WT-01, WT-02 | Requires live GTK/VTE rendering + agent install | Launch arduis inside the repo, click `+`, type a new branch name, confirm a tab opens in `../<repo>-<branch>` with `claude` running |
| Already-checked-out branch handled gracefully | WT-03 | Live UI focus/abort message | Pick a branch already in a tracked worktree → existing tab focused; pick the main checkout's branch → clear abort message, no `--force` |
| Hibernate frees RAM, keeps directory; resume relaunches | RAM-01 | Live process-group teardown + RAM observation | Right-click tab → Hibernate; confirm pgid killed (no orphan), tab dimmed/badged, directory still on disk; Resume → fresh `zsh`+`claude` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
