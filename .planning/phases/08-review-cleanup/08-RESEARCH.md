# Phase 8: Review + Cleanup - Research

**Researched:** 2026-06-14
**Domain:** git/`gh` read-only introspection (diff, branch/PR status), safe multi-repo worktree teardown, GTK4/VTE display, throttle/cache
**Confidence:** HIGH (the stack is the project's OWN proven code — git_service async, killpg teardown, container-down channel, sidebar/menu; git/gh verified live on host)

## Summary

Phase 8 is almost entirely a **composition phase**: every primitive it needs already
exists in the codebase and was proven in earlier phases. The "read-only" constraint
(`só leitura de git/gh`, with the ONE allowed write being `gh pr create`) maps cleanly
onto the existing `git_service.run_git_async` async runner — the SAME `Gio.Subprocess` +
`HostRunner` + GLib-loop pattern, with NO new service module needed (gh argv is just
another argv list). The "conclude" safety is the load-bearing piece: it is a strict,
ORDERED composition of three already-built teardown channels — `_teardown_session_terminals`
(killpg agents, Phase 2/3.1), `_container_down` (compose down, Phase 7), and a NEW
`git worktree remove` step gated by a `git status --porcelain` clean-check — finishing with
`git worktree prune`. The never-force, never-delete-source rules (D-10 from 03.2) constrain
this hard: arduis removes the TASK's worktrees, NEVER the source repos, and NEVER `--force`s
a dirty tree.

Three new GTK-free domain modules carry the new logic (`review.py` for diff/status argv +
parsing, plus a `gh.py` argv builder and a tiny `throttle.py`/cache), mirroring the
`worktree.py` / `compose.py` GTK-free-builder + thin-service split that the project already
enforces. The display surfaces fit the existing sidebar+workspace model: the diff is a
**read-only spawned VTE leaf** running `git --no-pager diff` (reuses the spawn machinery and
the user's pager-free muscle memory), and the branch/PR status lives in the **sidebar row
subline** (where RAM and `claude · —` already render) plus a manual refresh action.

**Primary recommendation:** Add `review.py` (GTK-free diff/status/gh argv + parse), reuse
`run_git_async` verbatim for gh (rename-agnostic — it is just argv), show the diff in a
read-only spawned VTE leaf, surface branch/PR status in the row subline behind a
**manual-refresh + TTL-cache** throttle (NOT a poll), and implement "Concluir" as a strict
ordered chain `kill agents → compose down → porcelain clean-check (refuse if dirty) →
git worktree remove → git worktree prune`, NEVER `--force`, NEVER touching source repos.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REVIEW-01 | Usuário vê o diff (read-only) das mudanças de uma worktree | §1 read-only diff; spawn a `git --no-pager diff` VTE leaf (reuses `_spawn_into`/`_make_leaf`); per-repo argv via `argv_diff` in new `review.py`; `[VERIFIED: git 2.43 on host]` |
| REVIEW-02 | Usuário abre PR via `gh` (shell-out); o app lê o status do PR | §2 `gh pr create` (the ONE allowed write) opened in a spawned VTE leaf (interactive) OR `gh pr create --web`; then `gh pr view --json state,number,title,url,...` read-only via `run_git_async`. `[VERIFIED: gh 2.93.0, authed on host]` |
| REVIEW-03 | "Concluir worktree" → remove a worktree (+ teardown de containers) | §3 strict ordered teardown: `_teardown_session_terminals` → `_container_down` → porcelain clean-check → `git worktree remove` (no `--force`) → `git worktree prune`. Multi-repo: per-repo loop; task folder + symlinks cleaned, source repos UNTOUCHED (D-10). |
| GIT-01 | App lê e exibe branch + status de PR via git/`gh` (somente leitura) | §2 + §4: `git rev-parse --abbrev-ref HEAD`, ahead/behind via `git rev-list --left-right --count`, `gh pr view --json`; THROTTLED via manual-refresh + TTL cache (§4); degrade gracefully when gh absent/unauthed (exit 4). |
</phase_requirements>

## Standard Stack

This phase introduces **zero new third-party dependencies** — it is built entirely from
the host CLIs (`git`, `gh`) the project already shells out to, plus the project's own
proven modules. CLAUDE.md is explicit: "Shell-out to git/gh/docker compose — CONFIRMED
correct; no mature, maintained Python libs worth the dependency cost here."

### Core (reuse — already in the codebase)
| Module / Tool | Version | Purpose | Why Standard |
|---------------|---------|---------|--------------|
| `git` (host) | 2.43.0 `[VERIFIED: git --version on host]` | diff, status, worktree remove/prune, rev-list ahead/behind | Already the worktree engine; `só leitura` for review, plus the one `worktree remove` write |
| `gh` (host) | 2.93.0 `[VERIFIED: gh --version on host]` | `pr view --json` / `pr status --json` (read), `pr create` (the ONE allowed write) | The roadmap explicitly allows opening a PR; everything else is read-only |
| `arduis.git_service.run_git_async` | in-repo | Async argv runner on the GLib loop via `Gio.Subprocess`+`HostRunner` | EXISTING. Works for ANY argv — gh is just another argv list; no new service module |
| `Vte.Terminal.spawn_async` (via `_spawn_into`/`_make_leaf`) | system 0.76 floor | Display the diff as a real read-only terminal leaf | Reuses the pane/spawn machinery; pager-free `git --no-pager diff` renders with color |
| `_teardown_session_terminals` / `_teardown_pgid` | in-repo (Phase 2/3.1) | Kill the task's agent/shell process groups (step a of conclude) | EXISTING, proven no-orphan SIGHUP→SIGKILL |
| `_container_down` / `compose.down_argv` | in-repo (Phase 7) | `docker compose down --remove-orphans --volumes` (step b of conclude) | EXISTING separate channel (T-07-13); reused verbatim |

### Supporting (new GTK-free modules to ADD)
| Module | Purpose | When to Use | Mirrors |
|--------|---------|-------------|---------|
| `arduis/review.py` | GTK-free argv builders + parsers: `argv_diff`, `argv_diff_stat`, `argv_status_porcelain`, `argv_current_branch`, `argv_ahead_behind`, `parse_porcelain_clean`, `parse_ahead_behind` | All git read introspection + the dirty-tree guard | `worktree.py` (argv builders + parsers, GTK-free, no `gi`) |
| `arduis/gh.py` | GTK-free gh argv builders + JSON-shape parsers: `argv_pr_view`, `argv_pr_create`, `parse_pr_view`, `gh_available()` | PR read + the create write | `compose.py` (argv + json-shape parsing, GTK-free) |
| `arduis/review_cache.py` (or fold into `review.py`) | TTL cache keyed by task_id; `is_fresh(ts, now, ttl)`, store/get | Throttle gh/git reads (§4) | small pure helper, fully unit-testable |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Read-only spawned VTE for the diff | `Gtk.TextView` monospace fed `run_git_async` output | TextView gives easy programmatic copy/scroll and no PTY, BUT loses ANSI color, re-implements scrollback, and needs ANSI→Pango parsing. VTE reuses everything and matches the terminal-centric UX. **Recommend VTE.** A TextView is the fallback only if a non-terminal "summary card" is wanted. |
| Reuse `run_git_async` for gh | A new `gh_service.py` clone (like `docker_service.py`) | A clone adds a module for no behavior difference — gh is argv on the same loop. `run_git_async` is already argv-agnostic. **Reuse it.** (Optional cosmetic alias `run_gh_async = run_git_async` if naming clarity is wanted — zero new logic.) |
| Manual-refresh + TTL cache | Coarse interval poll (like the 2s RAM tick) | git/gh are heavier and network-bound (gh hits GitHub → rate limits, GIT-01 "throttled"). A poll spams the API. **Recommend manual refresh + a short on-create/on-focus auto-read behind a TTL.** |
| `git worktree remove` then `prune` | `git worktree remove --force` | `--force` deletes uncommitted work — the explicit criterion-4 prohibition. **Never `--force`.** The non-force refusal on a dirty/locked tree IS the safety; surface it. |

**Installation:** None. `git` and `gh` are host CLIs already required; no Python packages.

**Version verification (host, 2026-06-14):**
- `git version 2.43.0` `[VERIFIED]`
- `gh version 2.93.0 (2026-05-27)` `[VERIFIED]`, authed (`gh auth status` → ✓ Logged in to github.com as thallysrc, ssh) `[VERIFIED]`

## Architecture Patterns

### Recommended structure (extends the existing GTK-free-domain / thin-service / window split)
```
src/arduis/
├── review.py          # NEW: GTK-free git read argv + porcelain/ahead-behind parsers (no gi)
├── gh.py              # NEW: GTK-free gh argv + PR-JSON parsers (no gi)
├── review_cache.py    # NEW (or fold into review.py): pure TTL-cache helper (no gi)
├── git_service.py     # REUSE verbatim: run_git_async runs git AND gh argv
├── worktree.py        # REUSE: argv_worktree_list_porcelain, parse_worktrees, sanitize_*
├── task_layout.py     # REUSE: task_dir_for, repo_worktree_dir (locate worktrees to remove)
├── session.py         # REUSE/extend: Task/RepoCheckout; maybe a CONCLUDED state or just remove() from store
└── window.py          # WIRE: "Concluir" menu action, diff leaf, status subline, refresh action, throttle
```

### Pattern 1: gh/git read = argv builder (GTK-free) + `run_git_async` (existing service)
**What:** Build the argv as a pure list in `review.py`/`gh.py`; run it via the existing
`run_git_async`; parse the JSON/porcelain in the `on_done` callback (which fires on the
GLib loop, so it may mutate widgets/store directly).
**When to use:** EVERY git/gh read in this phase.
**Example:**
```python
# review.py (GTK-free, no gi) — Source: project's worktree.py builder convention
def argv_current_branch(repo: str) -> list[str]:
    return ["git", "-C", repo, "rev-parse", "--abbrev-ref", "HEAD"]

def argv_ahead_behind(repo: str, branch: str) -> list[str]:
    # left-right count vs the upstream; @{u} resolves the tracking branch
    return ["git", "-C", repo, "rev-list", "--left-right", "--count",
            f"{branch}...{branch}@{{u}}"]

def parse_ahead_behind(stdout: str) -> tuple[int, int]:
    # "3\t2" => (ahead=3, behind=2); empty/garbage => (0, 0)
    parts = stdout.split()
    if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
        return int(parts[0]), int(parts[1])
    return (0, 0)
```
```python
# gh.py (GTK-free, no gi)
PR_VIEW_FIELDS = "state,number,title,url,isDraft,reviewDecision,mergeable,headRefName"
def argv_pr_view(repo: str, branch: str) -> list[str]:
    # --json forces machine output; scope to the branch's head ref
    return ["gh", "pr", "view", branch, "--repo-relative-noop-placeholder",
            "--json", PR_VIEW_FIELDS]  # NOTE: run with cwd=worktree, see below
```
```python
# window.py (the wiring) — Source: existing _enable_isolation on_done convention
def _refresh_pr_status(self, task, repo):
    def _on_done(rc, out, err):
        if rc == 4:               # gh: needs authentication (verified exit-code table)
            self._set_status_subline(task, "gh: não autenticado"); return
        if rc != 0 or not out.strip():
            self._set_status_subline(task, "sem PR"); return
        try:
            pr = gh.parse_pr_view(out)         # json.loads + shape guard
        except (ValueError, TypeError):
            return                              # never crash the loop on garbage
        self._review_cache.put(task.task_id, pr, now=time.monotonic())
        self._set_status_subline(task, gh.format_pr_subline(pr))
    run_git_async(gh.argv_pr_view(repo.worktree_dir, repo.branch), _on_done,
                  runner=self._runner)
```
> **gh cwd note:** `gh` infers the repo from the working directory / git remote. Since
> `run_git_async`/`Gio.Subprocess` does not currently set `cwd`, the cleanest path is to
> pass `git -C`-style context to git, and for gh either (a) add an optional `cwd=` to
> `run_git_async` (small, backward-compatible: `Gio.Subprocess` → use
> `Gio.SubprocessLauncher().set_cwd(...)`), or (b) wrap as
> `["gh", "-R", "<owner/repo>", ...]` after resolving the remote once. **Recommend (a):
> add an optional `cwd` to `run_git_async`** — minimal, lets gh resolve the remote
> naturally, and helps git diff too. `[ASSUMED]` that adding `cwd` is preferable; flag A3.

### Pattern 2: The diff as a read-only spawned VTE leaf
**What:** Open a new pane (reusing `_make_leaf` + `_spawn_into`) whose command is
`git --no-pager diff` (or `diff --stat` first, then full), rendered with VTE color, and
set the terminal **input-disabled** so it is genuinely read-only.
**When to use:** REVIEW-01 (diff display).
**Example approach:**
```python
# Reuse the spawn machinery but spawn git directly (not zsh+claude). Two options:
#   (i) spawn ["zsh","-l","-i","-c","git --no-pager diff; exec zsh -i"]  (stays interactive)
#   (ii) spawn ["git","--no-pager","diff"] directly and set the VTE read-only.
# Recommend (i)-style via the existing login-shell so PATH/pager config resolve, OR a
# dedicated _spawn_diff that runs `git -C <wt> --no-pager diff` then drops to a shell.
terminal.set_input_enabled(False)   # VTE 0.76: read-only display (no keystrokes to child)
```
> `Vte.Terminal.set_input_enabled(False)` exists at the 0.76 floor and makes the pane a
> true read-only viewer (scroll/copy still work). `[CITED: gnome.pages.gitlab.gnome.org/vte/gtk4/]`
> For a whole-TASK diff (multiple repos), spawn one leaf per repo OR a single shell that
> loops `for d in <repos>; do git -C "$d" --no-pager diff; done`. **Recommend per-repo
> on demand** (a "Ver diff" entry per repo, like "Fechar repositório"); single-repo is the
> degenerate one-entry case.

### Pattern 3: "Concluir" = strict ordered teardown chain (the load-bearing safety)
**What:** A single action that composes existing channels in a FIXED order, with a
hard dirty-tree gate before any removal. See §3 for the full spec.
**When to use:** REVIEW-03 / criterion 4.

### Pattern 4: Throttle = manual refresh + TTL cache, NOT a poll
**What:** A refresh button/menu-item triggers the read; results cache per task with a TTL;
auto-reads happen only on create and on row-activation (focus), gated by the TTL so rapid
switching does not spam gh. See §4.

### Anti-Patterns to Avoid
- **Polling gh on the 2s RAM tick:** hammers the GitHub API → rate limits. Use manual
  refresh + TTL (GIT-01 "throttled").
- **`git worktree remove --force`:** deletes uncommitted work. NEVER. The non-force
  refusal is the feature.
- **Removing the source repo or the meta-repo `.git`:** D-10 — arduis only removes the
  TASK's worktrees in `../<root>-tasks/`, never the user's source.
- **Calling `_container_down` from inside `_teardown_session_terminals`:** the two channels
  stay SEPARATE (T-07-13). The conclude orchestrator calls them in sequence, not nested.
- **Blocking `subprocess.run` for git/gh on the GTK loop:** freezes the UI; use
  `run_git_async` (the app-exit synchronous-with-timeout exception in `_on_close_request`
  does NOT apply to the interactive conclude path).
- **Parsing diff output to "understand" changes:** read-only display only; no inline
  comments / PR UI (explicitly Out of Scope).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Diff rendering w/ color, scrollback, copy | A `Gtk.TextView` + ANSI parser | A read-only spawned VTE leaf (`set_input_enabled(False)`) | VTE already does color/scroll/copy; reuses `_make_leaf`/`_spawn_into` |
| Async git/gh execution | A new thread / asyncio / `gh_service.py` clone | `git_service.run_git_async` (argv-agnostic) | Exists, proven, on the GLib loop, routes through HostRunner |
| Dirty-tree detection | Parsing `git diff` byte counts | `git status --porcelain` empty-check | Porcelain is the canonical, stable clean-signal `[VERIFIED on host]` |
| Ahead/behind counts | Manual log walking | `git rev-list --left-right --count A...A@{u}` | One command, stable plumbing |
| Worktree removal + cleanup | `shutil.rmtree` of the worktree dir | `git worktree remove` (no `--force`) + `prune` | rmtree corrupts git's worktree registry and bypasses the dirty guard |
| PR data shape | Scraping `gh pr view` text | `gh pr view --json <fields>` + `json.loads` | `--json` is the stable contract; text format changes `[VERIFIED: gh 2.93 JSON FIELDS list]` |

**Key insight:** This phase's value is in ORDER and REFUSAL, not in new mechanism. Every
moving part is a project primitive; the work is composing them safely and surfacing the
refusals (dirty tree, gh absent, locked worktree) as clear pt-BR messages instead of raw
git/gh stderr.

## The Safe Teardown Order (REVIEW-03, criterion 4) — load-bearing spec

The "Concluir task" action MUST execute these steps in EXACTLY this order. The dirty-tree
gate (step c) sits BEFORE any removal and refuses rather than forces.

```
CONCLUDE(task):
  (a) KILL AGENTS  — self._teardown_session_terminals(task)
        SIGHUP→SIGKILL every terminal process group across every repo + task-level
        pair (EXISTING, no-orphan). Also _clear_task_state_files(task) (runtime data,
        D-10-exempt). This frees the worktrees from running processes so git can remove
        them (a process with cwd inside the worktree can make remove fail / a lock linger).

  (b) COMPOSE DOWN — self._container_down(task)  [only if isolation enabled]
        SEPARATE channel (T-07-13): docker compose down --remove-orphans --volumes,
        scoped to arduis-<branch>. Containers are daemon-owned, not in arduis's pgroup,
        so killpg in (a) does nothing for them. Skipped if state is None/disabled.
        NOTE: this is async fire-and-forget today; for CONCLUDE the remove in (d) should
        not depend on compose being fully down (the container dir is the task folder, but
        the worktree dirs are independent). Sequence (b) before (d) so a stack bound to
        bind-mounts in the worktree is released first. [ASSUMED ordering benefit; flag A1.]

  (c) VERIFY CLEAN — for EACH repo in task.repos:
        run `git -C <worktree_dir> status --porcelain`
        if stdout is non-empty (dirty) OR a repo is locked → REFUSE:
          do NOT remove ANY repo's worktree; surface an Adw.AlertDialog/toast in pt-BR
          ("A worktree <repo> tem mudanças não commitadas — conclua ou descarte antes.")
          and STOP. NEVER pass --force. (criterion 4)
        Decision: check ALL repos first; refuse the WHOLE conclude if ANY is dirty
          (all-or-nothing keeps the task folder consistent — no half-removed task).
          [ASSUMED all-or-nothing > per-repo partial; flag A2 — recommended default below.]

  (d) REMOVE WORKTREES — for EACH repo in task.repos:
        run `git -C <SOURCE_REPO> worktree remove <worktree_dir>`   (NO --force)
        The SOURCE repo path is the project member repo (where the worktree was added
        from), NOT the worktree itself. arduis NEVER deletes the source repo (D-10) —
        `git worktree remove` only removes the linked worktree + its admin entry.
        If git itself refuses (e.g. became dirty/locked between (c) and (d)), surface the
        stderr in pt-BR and stop — the refusal is the safety, do not escalate to --force.

  (e) PRUNE — for EACH source repo touched:
        run `git -C <SOURCE_REPO> worktree prune`
        Cleans stale admin entries for any worktree whose dir is already gone.

  (f) CLEAN THE TASK FOLDER (symlinks + now-empty dir):
        The task folder ../<root>-tasks/<branch>/ holds the removed worktree dirs (git
        removed them in (d)) + RELATIVE SYMLINKS to root files (D-09/D-10). UNLINK the
        symlinks (os.unlink on the LINK, never the target — D-10) and rmdir the task
        folder if empty. The source repos and the linked root files are UNTOUCHED.
        [ASSUMED arduis should also clean the symlink-only task folder on conclude;
        flag A4 — recommended default: yes, clean it, since the task is concluded.]

  (g) DROP FROM STORE — self._store.remove(task.task_id); rebuild sidebar; if it was the
        active workspace, swap to pinned main (mirrors _on_close_repo's blank-canvas guard).
```

**Command verification (host, git 2.43.0):**
- `git status --porcelain` → empty stdout when clean, `?? a.txt` / ` M file` lines when dirty `[VERIFIED]`
- `git worktree remove <wt>` → refuses a dirty/locked tree without `-f` (usage confirms `-f` is the only force) `[VERIFIED: git worktree remove -h]`
- `git worktree prune` → removes stale admin entries `[VERIFIED: git worktree prune -h]`

**What "conclude" removes vs keeps (D-10, explicit):**
| Removed | Kept (NEVER touched) |
|---------|----------------------|
| The task's worktree dirs (`../<root>-tasks/<branch>/<repo>/`) via `git worktree remove` | The source member repos (e.g. `backend/`, `frontend/` under the project root) |
| The relative symlinks in the task folder (`os.unlink` the link) | The symlink TARGETS (root `CLAUDE.md`, `docker-compose.yml`, ...) |
| The (now-empty) task folder itself | The meta-repo `.git` and all project source |
| The task's container stack (`down -v`) + runtime state files | The user's git history / branches (remove ≠ delete branch) |

> **Note on the branch:** `git worktree remove` does NOT delete the branch — the user's
> commits/branch survive (they may already be in a PR). arduis stays read-only on history;
> deleting branches is out of scope. Surface this if a user expects "conclude" to also drop
> the branch — it does not.

## Throttle + Cache Design (GIT-01)

GIT-01 says reads must be **throttled**. git is cheap (local); gh is network-bound and
rate-limited (GitHub primary-rate limits authenticated requests). The design:

- **Trigger model: manual refresh + event-gated auto-read, NOT a poll.**
  - Auto-read branch+ahead/behind+PR status ONCE on task create and ONCE on row-activation
    (focus), each gated by the TTL cache.
  - A "Atualizar status" menu item / a small refresh button forces a re-read (bypasses TTL).
- **Cache:** `review_cache.py` — a pure dict keyed by `task_id` → `(payload, monotonic_ts)`.
  `is_fresh(ts, now, ttl)` decides reuse. Use `time.monotonic()` (no wall-clock jumps).
- **Recommended TTLs (defaults; AFK-safe):**
  - git branch/ahead-behind (local, cheap): TTL **30 s**.
  - gh PR status (network): TTL **120 s**, and additionally **debounce in-flight** (a
    `_pr_busy: set[task_id]` like `_compose_busy` so a second request while one is pending
    is dropped, not queued — mirrors the Phase-7 busy guard).
- **Why not the 2s RAM tick:** that tick is local `/proc` reads (sub-ms); gh over the
  network on a 2s loop across 5–12 tasks would burn the rate limit fast. `[ASSUMED]` exact
  TTL values; flag A5 — recommended defaults above, tune after dogfooding.
- **Degrade gracefully:** if `gh` is not on PATH → never call it; show "gh ausente" in the
  subline. If `gh` returns exit **4** (needs auth) → show "gh: não autenticado". Both are
  static states (no retry storm). `[VERIFIED: gh exit-code table — 4 = requires authentication]`

```python
# review_cache.py (GTK-free, pure)
def is_fresh(ts: float | None, now: float, ttl: float) -> bool:
    return ts is not None and (now - ts) < ttl
```

## DESIGN — where the diff, status, and "Concluir" live

A v1-pragmatic placement that fits the EXISTING sidebar + workspace model (the mockup's
"Review" room tab is out of v1 — room tabs are explicitly v2). Three surfaces:

1. **Branch + PR status → the sidebar row SUBLINE (+ a refresh action).**
   The subline already renders `claude · <RAM>` / `claude · —` (hibernated) /
   `claude · suspensa`. Extend it (or add a second status line) to show e.g.
   `feat/x · ↑3 ↓0 · PR #42 open` or `feat/x · ↑3 · sem PR` or `gh ausente`. The status
   text is rendered by the same `_subline_by_sid` label machinery. A "Atualizar status"
   item goes in the row context menu (next to Hibernar/Retomar). **Recommend the subline**
   — it is glanceable, matches the "always know your tasks" core value, and needs no new
   widget. For multi-repo tasks, show the aggregate (e.g. the task branch + a per-repo PR
   count) and the per-repo detail on demand. `[ASSUMED]` aggregate-in-subline is enough;
   flag A6 (recommended default: yes).

2. **Diff → a read-only spawned VTE leaf, opened on demand from the row/pane menu.**
   Add "Ver diff" to the row context menu (and/or a pane action). It opens a new leaf in
   the active workspace running `git --no-pager diff` for the repo (per-repo entry for
   multi-repo, like "Fechar repositório"), with `set_input_enabled(False)`. This reuses the
   split/leaf machinery and the terminal-centric UX (the user already reads diffs in a
   terminal). **Recommend the spawned read-only VTE leaf.** No new room tab.

3. **"Concluir" → the row context menu, with a confirmation dialog.**
   Add "Concluir task" to the row context menu (below Hibernar). It runs an `Adw.AlertDialog`
   confirmation ("Concluir <branch>? Remove as worktrees da task; o código-fonte e o
   histórico ficam intactos."), then executes the §3 chain. If the dirty-gate refuses,
   surface a SECOND dialog/toast naming the dirty repo(s) and STOP. **Recommend the context
   menu + confirm dialog** — mirrors Hibernar/Retomar exactly; no new top-level UI.

**Menu shape (row context menu after Phase 8):**
```
[ACTIVE task]                  [HIBERNATED task]
  Hibernar                       Retomar
  Ver diff ▸ (per repo)          Concluir task
  Atualizar status               Isolar/Desligar containers (if avail)
  Fechar repositório ▸           Ver diff ▸ (optional, on disk)
  Concluir task
  Isolar/Desligar containers (if avail)
```
> `[ASSUMED]` "Concluir" is offered for both ACTIVE and HIBERNATED tasks (a hibernated task
> still has worktrees on disk to remove). Recommended default: offer it in both states; for
> an ACTIVE task, step (a) kills the live agents first. Flag A7.

## Common Pitfalls

### Pitfall 1: Force-removing a dirty tree (the cardinal sin)
**What goes wrong:** `git worktree remove --force` silently deletes uncommitted work.
**Why it happens:** git refuses a dirty tree without `-f`; the lazy fix is to add `-f`.
**How to avoid:** NEVER emit `--force`. Gate on `git status --porcelain` empty BEFORE
removing; if dirty, refuse and surface a pt-BR message. The refusal IS the feature.
**Warning signs:** any `--force`/`-f` token in a worktree-remove argv builder; a test that
removes a dirty tree "successfully."

### Pitfall 2: gh not installed / not authenticated
**What goes wrong:** calling `gh` crashes or hangs when gh is absent or unauthed.
**Why it happens:** assuming gh is always present + logged in.
**How to avoid:** probe `shutil.which("gh")` (GTK-free `gh.gh_available()`) before any gh
call; treat exit code **4** as "needs auth" `[VERIFIED]`. Show "gh ausente"/"gh: não
autenticado" in the subline; never retry-storm. (PR create simply unavailable when gh absent.)
**Warning signs:** a hang on a machine without gh; an uncaught exception in the on_done.

### Pitfall 3: A running process holds the worktree (order matters)
**What goes wrong:** `git worktree remove` fails or leaves a lock because an agent/shell has
its cwd inside the worktree, or a container bind-mount pins files.
**Why it happens:** removing before killing the agents / bringing the stack down.
**How to avoid:** the §3 ORDER — kill agents (a) and compose down (b) BEFORE remove (d).
**Warning signs:** intermittent "fatal: ... is dirty/locked" right after clicking conclude.

### Pitfall 4: Concluding with isolation still up
**What goes wrong:** orphaned containers/volumes after the worktree is gone (RAM leak — the
first-class constraint).
**How to avoid:** step (b) `_container_down` BEFORE remove; it is the Phase-7 channel, scoped
to `arduis-<branch>`, `--remove-orphans --volumes`. Skipped cleanly if isolation was off.
**Warning signs:** `docker compose ls` shows an `arduis-*` stack with no live task (the
existing `_reconcile_orphans` startup pass would later flag it).

### Pitfall 5: Deleting symlink TARGETS instead of the links (D-10)
**What goes wrong:** cleaning the task folder removes the root's real `CLAUDE.md` /
`docker-compose.yml`.
**Why it happens:** `shutil.rmtree(task_dir)` follows or a naive walk deletes targets.
**How to avoid:** `os.unlink` the LINK path only (never resolve+delete the target); the
symlinks are RELATIVE (per `task_layout.symlink_plan`). rmdir the task folder only when
empty. arduis NEVER deletes source (D-10). `[VERIFIED: task_layout.py symlink_plan is relative-target]`

### Pitfall 6: `git worktree remove` run from the wrong repo / on a locked tree
**What goes wrong:** running remove with `-C <worktree>` instead of `-C <source repo>`, or
on a tree git has locked.
**How to avoid:** run `git -C <SOURCE member repo> worktree remove <worktree_dir>`; surface
git's refusal on a locked tree (do not unlock+force). The source repo path is the project
member repo, derivable from the project root + repo_name.
**Warning signs:** "not a working tree" errors; removes that need a manual unlock.

### Pitfall 7: gh rate limits / spamming reads
**What goes wrong:** polling gh per task per tick exhausts the GitHub rate limit.
**How to avoid:** §4 — manual refresh + TTL cache + in-flight debounce; no interval poll.
**Warning signs:** gh returning rate-limit errors; sluggish status updates.

### Pitfall 8: Blocking the GTK loop on a slow git/gh call
**What goes wrong:** a network-slow `gh pr view` or a big `git diff` freezes the UI.
**How to avoid:** always `run_git_async` (GLib loop). The ONLY sanctioned synchronous call
is the app-exit `down` in `_on_close_request` (timeout-capped) — does NOT apply to the
interactive conclude/diff/status paths.

## Code Examples

### Read-only diff leaf (REVIEW-01)
```python
# review.py (GTK-free) — Source: project worktree.py builder convention
def argv_diff(repo: str) -> list[str]:
    return ["git", "-C", repo, "--no-pager", "diff"]
def argv_diff_stat(repo: str) -> list[str]:
    return ["git", "-C", repo, "--no-pager", "diff", "--stat"]
```
```python
# window.py wiring: spawn a read-only leaf (reuses _make_leaf/_spawn machinery)
terminal = self._make_terminal()
terminal.set_input_enabled(False)   # VTE 0.76 — true read-only viewer  [CITED: vte gtk4 docs]
# spawn `git -C <wt> --no-pager diff` via the login shell so color/pager config resolve
```

### Dirty-tree guard (REVIEW-03, criterion 4)
```python
# review.py (GTK-free)
def argv_status_porcelain(repo: str) -> list[str]:
    return ["git", "-C", repo, "status", "--porcelain"]
def parse_porcelain_clean(stdout: str) -> bool:
    return stdout.strip() == ""     # empty => clean => safe to remove   [VERIFIED on host]
```

### Worktree remove + prune (REVIEW-03) — NEVER --force
```python
# review.py (GTK-free)
def argv_worktree_remove(source_repo: str, worktree_dir: str) -> list[str]:
    return ["git", "-C", source_repo, "worktree", "remove", worktree_dir]  # NO --force
def argv_worktree_prune(source_repo: str) -> list[str]:
    return ["git", "-C", source_repo, "worktree", "prune"]
```

### PR read + create (REVIEW-02 / GIT-01)
```python
# gh.py (GTK-free)
PR_VIEW_FIELDS = "state,number,title,url,isDraft,reviewDecision,mergeable,headRefName"
def argv_pr_view(branch: str) -> list[str]:        # run with cwd=worktree (gh infers repo)
    return ["gh", "pr", "view", branch, "--json", PR_VIEW_FIELDS]
def argv_pr_create_web() -> list[str]:             # the ONE allowed write; --web is safest
    return ["gh", "pr", "create", "--web"]
def gh_available() -> bool:
    import shutil
    return shutil.which("gh") is not None
def parse_pr_view(stdout: str) -> dict:
    import json
    data = json.loads(stdout)                       # caller catches ValueError/TypeError
    if not isinstance(data, dict):
        raise TypeError("unexpected gh pr view shape")
    return data
```
> **`gh pr create` placement:** opening a PR is interactive (title/body/base). Two clean
> options: (i) `gh pr create --web` opens the browser form (zero in-app prompt UI, fully
> read-only-in-app afterward) — **recommend as the default**; (ii) `gh pr create` in a
> spawned VTE leaf for the terminal-native flow. Both shell out via the existing machinery.
> `[ASSUMED]` `--web` is the AFK-safe default; flag A8.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `gh pr view` text scraping | `gh pr view --json <fields>` + `json.loads` | gh has had `--json` for years | Stable machine contract; never scrape `[VERIFIED: gh 2.93 JSON FIELDS]` |
| `git worktree remove --force` for convenience | non-force + porcelain gate | project rule (criterion 4 / D-10) | Safety: never lose uncommitted work |
| Poll for status | manual refresh + TTL cache | GIT-01 "throttled" | Avoids gh rate limits |

**Deprecated/outdated:** none relevant — git/gh CLIs on host are current (2.43.0 / 2.93.0).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Sequencing compose-down (b) before worktree-remove (d) avoids bind-mount pin issues | §3 step b | Low — order is safe regardless; if no bind-mounts, ordering is neutral |
| A2 | Conclude is all-or-nothing if ANY repo is dirty (refuse whole task) vs per-repo partial | §3 step c | Medium — per-repo partial could leave a half-removed task folder; all-or-nothing is safer/cleaner. Recommended default: all-or-nothing |
| A3 | Adding an optional `cwd=` to `run_git_async` is preferable to `gh -R owner/repo` resolution | Pattern 1 | Low — both work; `cwd` is smaller and lets gh resolve the remote naturally |
| A4 | Conclude should also clean the symlink-only task folder (unlink links, rmdir) | §3 step f | Low — leaving an empty symlink folder is harmless but messy; cleaning matches "concluded". D-10 respected either way (links only) |
| A5 | TTLs: git 30 s, gh 120 s + in-flight debounce | §4 | Low — tunable after dogfooding; conservative defaults |
| A6 | Multi-repo status shows aggregate in subline, per-repo detail on demand | DESIGN §1 | Low — UI polish; aggregate is the glanceable default |
| A7 | "Concluir" offered for both ACTIVE and HIBERNATED tasks | DESIGN | Low — a hibernated task still has worktrees to remove; offering in both is correct |
| A8 | `gh pr create --web` is the AFK-safe default for opening a PR | Code Examples | Low — `--web` avoids in-app prompt UI; a VTE-leaf `gh pr create` is the terminal-native alternative |

## Open Questions

1. **Whole-task diff vs per-repo diff (REVIEW-01).**
   - What we know: a task spans N repos; each is a worktree dir.
   - What's unclear: one combined diff view or per-repo.
   - Recommendation: **per-repo on demand** ("Ver diff ▸ <repo>"), single-repo degenerate
     to one entry. Cleanest fit with the existing per-repo menu (Fechar repositório).

2. **Does "Concluir" delete the branch too?**
   - What we know: `git worktree remove` does NOT delete the branch; arduis is read-only on history.
   - Recommendation: **No** — never delete branches (out of scope); the branch/PR survive.
     Optionally note this in the confirm dialog so the user is not surprised.

3. **`cwd` for gh (Pattern 1 note / A3).**
   - Recommendation: add an optional `cwd=` to `run_git_async` (via
     `Gio.SubprocessLauncher.set_cwd`) — backward-compatible, smallest change.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| git | diff, status, worktree remove/prune, ahead/behind | ✓ | 2.43.0 | — (hard requirement; already used) |
| gh | PR view/create, GIT-01 status | ✓ (authed) | 2.93.0 | Degrade: show "gh ausente"/"gh: não autenticado"; PR features hidden; diff/branch status still work via git |
| docker compose | conclude step (b) container down | ✓ (Phase 7) | per-host | `_container_down` no-ops if isolation disabled / docker absent (`_isolation_available()` guard) |

**Missing dependencies with no fallback:** none (git is already a hard requirement).
**Missing dependencies with fallback:** gh — every PR-dependent feature degrades to a
static "ausente/não autenticado" state; diff + branch + ahead/behind (pure git) keep working.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (per `MEMORY.md`: `/tmp` venv `--system-site-packages`) |
| Config file | project pytest setup (existing — 344 tests at Phase 7) |
| Quick run command | `python -m pytest tests/test_review.py tests/test_gh.py -x` |
| Full suite command | `python -m pytest` |
| Headless GUI | broadway: `gtk4-broadwayd` (per `MEMORY.md` arduis-dev-environment) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REVIEW-01 | `argv_diff`/`argv_diff_stat` shape | unit | `pytest tests/test_review.py::test_argv_diff -x` | ❌ Wave 0 |
| REVIEW-03 | `parse_porcelain_clean` true/false on clean/dirty | unit | `pytest tests/test_review.py::test_porcelain_clean -x` | ❌ Wave 0 |
| REVIEW-03 | `argv_worktree_remove` NEVER contains `--force`/`-f` | unit (guard) | `pytest tests/test_review.py::test_remove_never_force -x` | ❌ Wave 0 |
| REVIEW-03 | conclude order: kill → down → check → remove → prune (orchestration) | unit (sequence recorder) | `pytest tests/test_window_conclude.py -x` (mock run_git_async/teardown, assert call order + refusal on dirty) | ❌ Wave 0 |
| REVIEW-02 | `parse_pr_view` json shape + garbage guard | unit | `pytest tests/test_gh.py::test_parse_pr_view -x` | ❌ Wave 0 |
| REVIEW-02/GIT-01 | gh exit-4 → "não autenticado"; absent → "ausente" | unit | `pytest tests/test_gh.py::test_degrade -x` | ❌ Wave 0 |
| GIT-01 | `parse_ahead_behind` parses `"3\t2"`/garbage | unit | `pytest tests/test_review.py::test_ahead_behind -x` | ❌ Wave 0 |
| GIT-01 | `review_cache.is_fresh` TTL logic | unit | `pytest tests/test_review_cache.py -x` | ❌ Wave 0 |
| REVIEW-01/03 | live: diff leaf read-only; conclude removes worktrees, keeps source | manual UAT (live git repo + gh) | 08-HUMAN-UAT.md | manual |

**Headless vs live split:**
- **Headless/automated:** all GTK-free argv builders + parsers + cache TTL + the conclude
  ORDER (mock the channels and assert call sequence + dirty-refusal). The dirty guard can be
  tested with a real temp git repo + worktree on disk (porcelain empty/dirty, remove
  refuses dirty) — no GUI needed. Broadway smoke for the menu wiring (Ver diff / Concluir
  entries appear; refusal dialog shows).
- **Live (UAT):** the read-only diff renders with color in a real VTE; `gh pr create` opens
  a real PR and `gh pr view` shows its status; concluding a real multi-repo task removes the
  worktrees + container stack and leaves the source repos + branch + PR intact; dirty-tree
  conclude is REFUSED with a clear message.

### Wave 0 Gaps
- [ ] `tests/test_review.py` — argv builders, porcelain clean, never-force guard, ahead/behind
- [ ] `tests/test_gh.py` — pr-view parse, degrade (absent/exit-4)
- [ ] `tests/test_review_cache.py` — TTL `is_fresh`
- [ ] `tests/test_window_conclude.py` — conclude order + dirty refusal (mock channels)
- [ ] Real-temp-repo fixture for the porcelain/remove dirty-guard test (conftest helper)

## Security Domain

> `security_enforcement` not set to false in config → included. Phase 8 shells out to
> git/gh and removes worktrees, so the relevant categories are injection (argv), and the
> destructive-action guard (force/source deletion).

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | gh auth is GitHub's; arduis only reads exit code 4 |
| V3 Session Management | no | — |
| V4 Access Control | yes | D-10: arduis may remove ONLY task worktrees/symlink-links, NEVER source repos/targets/branches; `--force` forbidden |
| V5 Input Validation | yes | branch names already sanitized (`sanitize_branch_for_dir`); argv are LISTS, never shell strings (no `shell=True`); diff/PR output is DISPLAY-only, never eval'd |
| V6 Cryptography | no | — |
| V12 File Resources | yes | symlink cleanup unlinks the LINK only (relative target), never resolves+deletes the target (Pitfall 5) |

### Known Threat Patterns for git/gh shell-out + worktree removal
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Command/argv injection via branch name | Tampering/EoP | argv LISTS via `Gio.Subprocess` (no shell); branch is a discrete element; reuse the tested `worktree.py` posture (T-02-01) |
| Force-deleting uncommitted work | Tampering (data loss) | NEVER `--force`; porcelain clean-gate before remove (criterion 4) |
| Deleting source repos / symlink targets | Tampering (data loss) | D-10: remove only task worktrees via `git worktree remove`; `os.unlink` links only; never `rmtree` the task folder following symlinks |
| gh output treated as code/path | Injection | PR JSON is `json.loads`'d and DISPLAYED only; never used to build a path or command |
| gh rate-limit / DoS-self | DoS | throttle: manual refresh + TTL + in-flight debounce (§4) |
| Diff leaf accepting input to the child | EoP | `Vte.set_input_enabled(False)` — read-only viewer |

## Sources

### Primary (HIGH confidence)
- Host `git version 2.43.0` — `git status --porcelain`, `git worktree remove -h` (only `-f` forces), `git worktree prune -h`, `git rev-list --left-right --count` `[VERIFIED on host 2026-06-14]`
- Host `gh version 2.93.0` — `gh pr view --json` FIELDS list (state, number, title, url, isDraft, reviewDecision, mergeable, headRefName, ...), `gh help exit-codes` (0 ok, 1 fail, 2 cancelled, 4 needs auth) `[VERIFIED on host 2026-06-14]`
- `gh auth status` — authenticated as thallysrc (ssh) `[VERIFIED on host]`
- Project source: `git_service.run_git_async`, `docker_service.run_compose_async`, `window.py` (`_teardown_session_terminals`, `_teardown_pgid`, `_container_down`, `_on_close_repo`, `_make_row_menu_cb`, subline `_subline_by_sid`, `_spawn_into`), `session.py` (Task/RepoCheckout/hibernate_fields), `task_layout.py` (symlink_plan relative target, D-10), `worktree.py` (argv builders + parsers) `[VERIFIED: read in this session]`
- CLAUDE.md — shell-out to git/gh; `só leitura de git/gh`; HostRunner seam; Gio.Subprocess async, no threads; VTE 0.76 API floor `[CITED]`

### Secondary (MEDIUM confidence)
- Vte 3.91 GTK4 reference (`set_input_enabled` available at 0.76 floor) `[CITED: gnome.pages.gitlab.gnome.org/vte/gtk4/]`

### Tertiary (LOW confidence)
- TTL values (§4) and the exact subline wording are recommendations to tune during dogfooding — none block planning.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all reused project code + host git/gh verified live
- Architecture (compose existing channels): HIGH — every channel exists and was proven in Phases 2/3.1/7
- Teardown order / dirty guard: HIGH — git behavior verified on host; D-10 constraints read from source
- Throttle/cache: MEDIUM — pattern is sound (mirrors `_compose_busy`); exact TTLs are tunable
- DESIGN placement: MEDIUM — fits the existing sidebar/menu model; subline-vs-second-line and a few UX choices flagged as assumptions

**Research date:** 2026-06-14
**Valid until:** 2026-07-14 (stable — host CLIs + own code; revisit if gh JSON fields change or VTE floor moves)
