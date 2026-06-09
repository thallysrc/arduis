# Phase 2 — Manual Acceptance Checklist (core loop)

> The GTK/VTE GUI and process-group teardown are **manual acceptance** (D-14 /
> `02-VALIDATION.md` § Manual-Only Verifications) — there is no Wayland GUI
> harness, so these are verified by a human running the app. The GTK-free
> domain layer (argv builders, SessionStore, hibernate model) is covered by the
> automated pytest suite.

## How to run

From a checkout of this repo:

```sh
./run.sh        # native run (no Flatpak in v1 — spawns the host zsh directly)
```

Launch arduis **from inside this git repo** so the `+New worktree` button
resolves the repo and enables. For the negative test (step 6) launch from a
non-git directory (e.g. `cd /tmp && /path/to/run.sh`).

---

## Acceptance behaviors

### SC#2 — New worktree tab opens with `claude` running (WT-01, WT-02, WT-03)

1. Launch arduis from inside this repo. Confirm **tab 0** is the `$HOME` scratch
   shell and the **`+New worktree`** button is **ENABLED**.
2. Click `+`, type a **NEW** branch name (e.g. `try-phase2`), confirm.
   - Expect: a new tab opens titled `try-phase2`.
   - A sibling dir `../arduis-try-phase2` is created — confirm with `ls ..`.
   - `claude` is running in that tab's terminal (or `command not found` if
     `claude` is not installed — the shell stays usable, **D-09**).

**PASS when:** the worktree tab opens in `../<repo>-<branch>` with `claude` fed.

---

### SC#3 — Already-checked-out branch handled gracefully, NEVER `--force` (WT-03, D-07)

3. Click `+` again and **pick an EXISTING branch already open as a worktree
   tab** → expect the existing tab is focused (no duplicate tab).
   Then click `+` and pick **the branch checked out in the MAIN repo** (e.g.
   `master`) → expect a clear **"Branch '<branch>' is already checked out at
   <path>"** message, **NO new tab**, and **NO `--force`**.

**PASS when:** a tracked branch focuses its tab; the main checkout's branch
aborts with a clear message and no worktree is force-created.

---

### SC#4 — Hibernate frees RAM + keeps the dir; Resume relaunches (RAM-01, D-10/D-11/D-12)

4. **Right-click a worktree tab → Hibernate.**
   - Confirm the worktree's process group is gone (RAM reclaimed):
     `ps aux | grep -E "zsh|claude|node"` shows none for that worktree.
   - The tab is **dimmed/badged** (needs-attention).
   - The sibling dir **STILL exists** — confirm with `ls ..` (Phase 2 never
     removes the directory; that is Phase 8).
   - **Right-click → Resume** → a fresh `zsh` + `claude` relaunches in the tab.

**PASS when:** Hibernate kills the group + keeps the dir + dims the tab, and
Resume cold-relaunches the shell+agent.

---

### No-orphans on window close (D-13)

5. Close the window. Confirm `ps aux` shows **NO orphan** `zsh`/`claude`/`node`
   left by arduis — across **all** tabs (tab 0 + every worktree session).

**PASS when:** closing the window leaves no orphan processes.

---

### `+` disabled outside a git repo (D-03)

6. (Negative) Launch arduis from a **NON-git** directory
   (e.g. `cd /tmp && /path/to/run.sh`) → the `+New worktree` button is
   **DISABLED** with the tooltip hint
   *"Launch arduis inside a git repo to create worktrees"*.

**PASS when:** the `+` button is disabled with the hint outside a repo.

---

## Sign-off

| SC / behavior | Requirement | Result |
|---------------|-------------|--------|
| SC#2 — worktree tab opens with `claude` | WT-01, WT-02, WT-03 | ⬜ |
| SC#3 — already-checked-out graceful, no `--force` | WT-03, D-07 | ⬜ |
| SC#4 — hibernate frees RAM + keeps dir, resume relaunches | RAM-01 | ⬜ |
| No orphans on window close | D-13 | ⬜ |
| `+` disabled outside a git repo | D-03 | ⬜ |

**Approval:** pending — type "approved" if SC#2/#3/#4 all pass, or describe what
failed (e.g. claude not fed, orphan left, dir removed on hibernate).
