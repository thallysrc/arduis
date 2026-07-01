# Phase 2: Core Loop (new worktree → env → agent) - Research

**Researched:** 2026-06-09
**Domain:** GTK4/libadwaita tabbed UI + git worktree orchestration + VTE PTY feed + GTK-free serializable session model
**Confidence:** HIGH (every load-bearing API was introspected live on this host at the Ubuntu floor; git mechanics verified in scratch repos)

## Summary

Phase 2 is almost entirely **assembly of APIs that already exist on the Ubuntu 24.04 floor** plus a **new GTK-free domain/service layer**. Every uncertain API was verified live on this host, which happens to run the floor versions: **Vte 0.76.0, libadwaita 1.5.0, GTK 4.14.5, Python 3.12.3, git 2.43.0**. No API in this phase exceeds the floor: `Adw.TabView`/`TabBar`/`TabPage` (with `set_needs_attention`, `set_indicator_icon`, `set_loading`, `set_menu_model`) are all available **since libadwaita 1.0** [VERIFIED: live introspection + valadoc/gnome docs], and `Vte.Terminal.feed_child` / `spawn_async` are present at 0.76 [VERIFIED: live introspection].

The four mechanics that needed pinning down are now pinned: (1) **`feed_child` at 0.76 takes `bytes` (a list of ints), NOT `str`** — passing a `str` raises `TypeError: Must be number, not str` [VERIFIED: live]. (2) The **spawn callback delivers the pid**; feed only after it fires. (3) **`git worktree add` fails hard (exit 128) when a branch is already checked out** — never use `--force`; pre-check `git worktree list --porcelain` [VERIFIED: scratch repo]. (4) **Default-branch detection cannot assume `origin`** — this very repo has no remote and uses `master`; `git symbolic-ref refs/remotes/origin/HEAD` fails, so a fallback chain is mandatory [VERIFIED: this repo errored exactly this way].

**Primary recommendation:** Build a strict three-layer split — `window.py` (GTK, the only `gi` module) → `session_store.py` + `worktree.py` git-argv builders (GTK-free, pure) → `git_service.py` (the only async-IO module, `Gio.Subprocess`). Reuse Phase-1's `_on_close_request` teardown verbatim by extracting it into a per-worktree `_teardown_pgid(pid)` helper that hibernate and window-close both call. Keep `claude` fed as `b"claude\n"` from inside the `spawn_async` callback.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01 … D-14 — all LOCKED)

- **D-01:** Worktrees presented as a **tab strip** (`Adw.TabView` / `Adw.TabBar`). Each worktree is a tab. Phase 3 replaces this with the real sidebar **binding to the same `SessionStore`** (the tab UI is a stepping stone, not throwaway).
- **D-02:** **Tab 0 keeps the Phase-1 `$HOME` shell** unchanged (zero regression; scratch shell). The **`+` ("New worktree") button lives on the tab bar**; new worktrees add tabs alongside tab 0.
- **D-03:** Repo resolved from arduis's **launch working directory** (`git rev-parse --show-toplevel`), terminal-centric. Launched **outside a git repo** → "+New worktree" **disabled with a hint**.
- **D-04:** A **new** branch is created off the repo's **auto-detected default branch** (`origin/HEAD` → `main`/`master`) — **without hardcoding the literal `main`**.
- **D-05:** Worktree directory is a **sibling**: **`../<repo>-<branch>`**. Branch names with slashes/unsafe chars are **sanitized** for the directory name.
- **D-06:** "+New worktree" dialog uses a **single editable combo (type-or-pick)**: typing a new name creates the branch; picking from the dropdown (`git branch`) checks out an existing one. arduis **infers new-vs-existing** automatically.
- **D-07:** **Never `--force`.** If the chosen branch is already checked out in a worktree arduis tracks, **focus that worktree's existing tab**. If checked out somewhere arduis doesn't track (e.g. the main working copy), show a **clear message** and abort. (Satisfies Success Criterion #3.)
- **D-08:** Launch is **feed-into-PTY**: spawn **`zsh -l -i`** in the worktree directory (same spawn path as Phase 1, different `cwd`), then write **`claude\n`** via `Vte.Terminal.feed_child()`. The **shell is the durable PTY child**; `claude` is a child of that zsh.
- **D-09:** Agent runs *inside* zsh → **Ctrl+C / agent exit lands back at the worktree zsh prompt**. A **missing or failed `claude` needs no special handling** (normal shell, `command not found`); tab stays open. **No in-app error banner** in Phase 2.
- **D-10:** Hibernate triggered from the **worktree tab's context menu** (right-click → "Hibernate"). A hibernated tab **stays visible but dimmed/badged** as suspended; "Resume" (menu) brings it back. Phase-3 sidebar inherits the same `SessionStore` state + actions.
- **D-11:** Hibernate **kills the whole worktree PTY process group** (`zsh` + `claude` child) via the **Phase-1 teardown path (SIGHUP → SIGKILL grace)**, reclaiming RAM, while **keeping the worktree directory** on disk. (Phase 2 does **not** remove worktrees — that's Phase 8.)
- **D-12:** **Resume re-spawns** `zsh -l -i` in the worktree dir and **re-feeds `claude`** — identical to fresh creation (D-08). It is a **cold relaunch**, not a reattach (reattach = v2 / PERSIST-01).
- **D-13:** The `SessionStore` is **GTK-free and serializable** with **RAM fields on the model from day one**, but **in-memory only** in Phase 2 — **no disk persistence**. Serializable ≠ persisted.
- **D-14:** **OS suspend/resume** is a **non-feature**. Persisting/re-listing worktrees across an **arduis quit/restart** is **deferred to v2** (PERSIST-01). On quit→relaunch arduis returns to its initial state (tab 0 = `$HOME`).

### Claude's Discretion

- Exact `SessionStore` shape, model fields, and serialization format (must be GTK-free, serializable, with RAM fields).
- Concrete Presentation→Domain→Service module/file layout; git argv construction details.
- **Creation progress feedback** during `git worktree add → open terminal → launch claude` (spinner / disabled button vs. just opening the tab).
- **Worktree tab label format** (branch name vs repo/branch vs dir name) and long-name truncation.
- The empty named `swarm/` seam directory.

### Deferred Ideas (OUT OF SCOPE — do not plan)

- **Conclude / remove worktree + teardown ordering + diff/PR** → **Phase 8** (REVIEW-03). Phase 2 only hibernates (keeps the directory); never removes worktrees.
- **Persist `SessionStore` to disk / cold-reopen worktrees across quit-restart** → **v2** (PERSIST-01).
- **Reattach to a live agent after quitting the app** → **v2 (PERSIST-01)** — needs a host tmux/abduco layer.
- **Repo folder-picker / multiple-repo switching** → not Phase 2; launch-cwd is the v1 repo source.
- **`.arduis.toml` `[worktree] base/location/setup`** → **Phase 6**; Phase 2 uses hardcoded equivalents.
- **Agent = configurable command / Ctrl+C swaps agent** → **Phase 5** (AGENT-01); Phase 2 hardcodes `claude`.
- Sidebar + parallel panes + per-worktree RAM **visibility** + active **caps** → Phase 3 (RAM-02/03). Phase 2 carries RAM *fields* on the model but does not display them.
- Attention/status detection → Phase 4.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **WT-01** | User creates a new worktree from a branch (new or existing) via UI ("+New worktree") | `Adw.TabBar` `+` button (D-02) + editable-combo dialog (D-06); new-vs-existing inferred by checking branch presence via `git for-each-ref refs/heads`. See *Architecture / git worktree mechanics*. |
| **WT-02** | The worktree is created via `git worktree add` at configured location/base | `git worktree add -b <branch> <dir> <base>` (new) / `git worktree add <dir> <branch>` (existing); base = auto-detected default branch (D-04); dir = `../<repo>-<sanitized-branch>` (D-05). Verified argv in *Code Examples*. |
| **WT-03** | A terminal opens in the worktree dir with the default agent (`claude`) already running | Reuse Phase-1 `spawn_async` with worktree `cwd`, then `feed_child(b"claude\n")` from the spawn callback (D-08). *VTE feed_child timing*. |
| **RAM-01** | User hibernates a worktree (kills agent, keeps directory) and resumes later, freeing RAM | Reuse Phase-1 SIGHUP→SIGKILL pgid teardown factored into a reusable helper (D-11); resume = cold re-spawn + re-feed (D-12); RAM fields on the `SessionStore` model (D-13). *Hibernate/Resume*. |

**Success-criteria mapping:**
1. (SC#1 — create at location/base) → WT-01 + WT-02
2. (SC#2 — terminal with `claude` running) → WT-03
3. (SC#3 — already-checked-out handled gracefully, never `--force`) → D-07 + the porcelain pre-check
4. (SC#4 — hibernate/resume frees RAM) → RAM-01
</phase_requirements>

## Standard Stack

Phase 2 adds **zero new third-party dependencies**. Everything is stdlib + the already-confirmed system stack.

### Core
| Library | Version (verified on host) | Purpose | Why Standard |
|---------|---------|---------|--------------|
| libadwaita | **1.5.0** | `Adw.TabView` + `Adw.TabBar` + `Adw.TabPage` for the worktree tab strip | The GNOME-standard tab widget; carries built-in per-page state (`set_needs_attention`, `set_loading`, `set_indicator_icon`) [VERIFIED: live introspection 2026-06-09] |
| Vte (GTK4, Vte-3.91) | **0.76.0** | `feed_child` (launch `claude`), `spawn_async` per-worktree `cwd` | Same engine as Phase 1; `feed_child`/`spawn_async` present at 0.76 [VERIFIED: live] |
| GTK | 4.14.5 | `Gio.SimpleAction` + `Gio.Menu` for the tab context menu (Hibernate/Resume) | Standard GTK4 menu model wiring |
| Python stdlib | 3.12.3 | `dataclasses` (SessionStore), `re`/`pathlib` (dir sanitization), `os`/`signal` (teardown), `enum` (session state) | GTK-free serializable core requirement (D-13) |
| `Gio.Subprocess` (PyGObject) | system | Async non-blocking `git` queries (`branch`, default-branch, `worktree list`) | CLAUDE.md mandates this for short read-only git — never block the GTK loop |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `git worktree` CLI | 2.43.0 | `add` / `list --porcelain` | Shell-out via `HostRunner` argv list (CLAUDE.md: no Python git lib) |
| `dataclasses.asdict` | stdlib | Serialize `SessionStore` (D-13 "serializable ≠ persisted") | Proves serializability in a unit test without writing to disk |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `Adw.TabView` | `Gtk.Notebook` | Rejected — `Adw.TabView` is the libadwaita-native widget with built-in `needs-attention`/`loading`/`indicator` state that Phase 3/4 reuse; `Gtk.Notebook` lacks them and looks non-native. D-01 locks `Adw.TabView`. |
| `Gio.Subprocess` async | `subprocess.run` (blocking) | Blocking is acceptable only for sub-millisecond calls; `git worktree add` can take longer (object checkout) → must be async or it freezes the UI. CLAUDE.md forbids blocking the GTK loop for long jobs. |
| `dataclasses` | `pydantic` / `attrs` | Rejected — adds a dependency; stdlib `dataclasses` is GTK-free, serializable via `asdict`, and zero-cost. |

**Installation:** None. Confirm the floor (already satisfied on this host):
```bash
.venv/bin/python -c "import gi; gi.require_version('Vte','3.91'); gi.require_version('Adw','1'); \
from gi.repository import Vte, Adw; print('Vte', Vte.MINOR_VERSION, 'Adw', Adw.MINOR_VERSION)"
# → Vte 76 Adw 5  (on this host, 2026-06-09)
```

**Version verification (done):** `Vte 0.76.0`, `Adw 1.5.0`, `Gtk 4.14.5`, `PyGObject 3.48.2`, `git 2.43.0`, `Python 3.12.3` — all confirmed live on the dev host [VERIFIED: live introspection 2026-06-09]. Note the host is at the **Ubuntu floor**, which makes it an ideal floor-compliance check: anything that runs here runs on the target.

## Architecture Patterns

### Recommended Project Structure (Presentation → Domain → Service)

```
src/arduis/
├── main.py             # Adw.Application entry (unchanged)
├── window.py           # PRESENTATION: only gi-importing module; owns Adw.TabView, terminals, feed, teardown
├── host_runner.py      # SERVICE seam (unchanged) — argv funnel
├── spawn.py            # DOMAIN: extend build_spawn_command(runner, cwd=...) — still GTK-free
├── exit_status.py      # DOMAIN (unchanged)
├── theme.py            # DOMAIN (unchanged)
├── session.py          # DOMAIN (NEW): SessionStore + WorktreeSession dataclass + SessionState enum — GTK-free, serializable, RAM fields
├── worktree.py         # DOMAIN (NEW): pure git-argv builders + parsers (default-branch chain, add argv, porcelain parse, dir sanitize) — GTK-free
├── git_service.py      # SERVICE (NEW): Gio.Subprocess async runner that EXECUTES the argv from worktree.py off the GTK loop
└── swarm/              # SEAM (NEW): named empty dir (with __init__.py) — no code in v1 (roadmap swarm seam)
    └── __init__.py
```

**Layering rule (established Phase-1 pattern, extended):** `window.py` is the **only** module that imports `gi`. `session.py` and `worktree.py` are **pure** (stdlib only) and unit-tested. `git_service.py` is the one new place that touches `Gio.Subprocess` (it imports `gi`, so technically presentation-adjacent — keep its *logic* thin: it just runs argv built by `worktree.py` and hands parsed strings back). This keeps the swarm-seam promise: the *domain* (`session.py` + `worktree.py`) is serializable and GTK-free.

### Pattern 1: GTK-free serializable SessionStore with RAM fields (D-13)
**What:** A plain in-memory registry of `WorktreeSession` dataclasses. No `gi` import. Serializable via `asdict`. RAM fields present but unpopulated in Phase 2 (Phase 3 fills them).
**When to use:** Single source of truth for which worktrees exist, their dirs, branch, pid/pgid, and state — the UI (tabs now, sidebar in Phase 3) is a *view* of this.
**Example:**
```python
# Source: stdlib dataclasses; design verified against D-13 + roadmap swarm-seam note
# src/arduis/session.py  — GTK-FREE
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from enum import Enum

class SessionState(str, Enum):       # str-Enum → serializes cleanly
    ACTIVE = "active"
    HIBERNATED = "hibernated"

@dataclass
class WorktreeSession:
    session_id: str                  # stable key (e.g. branch name)
    branch: str
    worktree_dir: str                # absolute sibling path ../<repo>-<branch>
    repo_root: str
    state: SessionState = SessionState.ACTIVE
    pid: int | None = None           # shell pid from spawn callback (None when hibernated)
    pgid: int | None = None          # process-group id for teardown (None when hibernated)
    # --- RAM fields, present from day one (D-13); populated in Phase 3 (RAM-02/03) ---
    rss_kb: int | None = None        # resident set size; None until a ResourceMonitor lands
    def to_dict(self) -> dict:       # proves "serializable" without persisting (D-13)
        return asdict(self)

class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, WorktreeSession] = {}
    def add(self, s: WorktreeSession) -> None: self._sessions[s.session_id] = s
    def get(self, sid: str) -> WorktreeSession | None: return self._sessions.get(sid)
    def by_branch(self, branch: str) -> WorktreeSession | None:
        return next((s for s in self._sessions.values() if s.branch == branch), None)
    def all(self) -> list[WorktreeSession]: return list(self._sessions.values())
    def to_list(self) -> list[dict]: return [s.to_dict() for s in self._sessions.values()]
```
> RSS source (Phase 3, not now): read `/proc/<pid>/statm` field 2 (resident pages) × `os.sysconf("SC_PAGE_SIZE")` — **no psutil dependency needed**. Phase 2 only carries the field. [ASSUMED — `/proc/<pid>/statm` is the standard Linux RSS source; confirm exact field in Phase 3]

### Pattern 2: feed-into-PTY after spawn (D-08)
**What:** Spawn `zsh -l -i` with the worktree `cwd`; in the spawn callback (where the pid is delivered), capture pid/pgid into the session, then `feed_child(b"claude\n")`.
**When to use:** Both fresh creation (D-08) and resume (D-12) — identical path.
**Example:** see *Code Examples → feed claude after spawn*.

### Pattern 3: async git via Gio.Subprocess (never block the loop)
**What:** Build argv with the pure `worktree.py` builders; run them with `Gio.Subprocess` + `communicate_utf8_async`; parse stdout in the async callback; then mutate UI/SessionStore on the main loop.
**When to use:** default-branch detection, `git branch` list for the combo, `git worktree list --porcelain` pre-check, and `git worktree add` itself.
**Example:** see *Code Examples → async git runner*.

### Anti-Patterns to Avoid
- **`feed_child("claude\n")` with a `str`:** raises `TypeError: Must be number, not str` at the 0.76 binding. Always pass `bytes` ([VERIFIED: live]).
- **`git worktree add --force`:** explicitly forbidden (D-07). Pre-check, never force.
- **Assuming `origin/HEAD` exists:** breaks on remote-less repos (this very repo). Use the fallback chain.
- **Blocking `subprocess.run("git worktree add")` on the GTK loop:** freezes the UI during object checkout. Use `Gio.Subprocess` async.
- **Putting worktree logic in `window.py`:** violates the GTK-free-core pattern; logic goes in `worktree.py`/`session.py`, UI glue stays in `window.py`.
- **Killing only the shell pid on hibernate:** must kill the **process group** (`os.killpg(pgid, ...)`) or `claude` orphans — exactly the Phase-1 no-orphan lesson.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Tab strip + per-tab state/badge | Custom tab bar on top of `Gtk.Box` | `Adw.TabView`/`TabBar`/`TabPage` | Built-in `set_needs_attention` (badge), `set_loading` (spinner), `set_indicator_icon`, drag/close, `set_menu_model` for right-click — all at the 1.0 floor [VERIFIED] |
| Dimmed/badged hibernated tab | Manual CSS opacity tracking | `TabPage.set_needs_attention(True)` + `set_indicator_icon`/`set_icon` (suspend glyph) | Native libadwaita state, survives Phase-3 sidebar migration |
| Right-click tab menu | Custom popover + hit-testing | `Adw.TabView.set_menu_model(Gio.Menu)` + `Gio.SimpleAction` | `set_menu_model` present [VERIFIED]; standard GTK action wiring |
| PTY ownership / resize / scrollback | Hand-rolled `pty` layer | `Vte.Terminal.spawn_async` (Phase-1 path, new `cwd`) | CLAUDE.md: VTE owns the PTY |
| Default-branch detection | Hardcode `main` | `git symbolic-ref refs/remotes/origin/HEAD` → fallback `git symbolic-ref --short HEAD` | D-04 forbids hardcoding `main`; this repo proves `origin` may be absent |
| Async subprocess on GTK loop | Threads + `subprocess` | `Gio.Subprocess` + `communicate_utf8_async` | CLAUDE.md mandated; integrates with the GLib main loop, no thread juggling |
| Process-group teardown | New kill code | Extract Phase-1 `_on_close_request`/`_sigkill_if_alive` into `_teardown_pgid(pid)` | RAM-01 reuses the *exact* tested no-orphan path (D-11) |

**Key insight:** Phase 2 is glue, not invention. The only genuinely new *logic* is (a) the git-argv/parse builders and (b) the SessionStore dataclass — both pure and unit-testable. Everything UI-side is wiring stock libadwaita/VTE APIs that are already on the floor.

## Common Pitfalls

### Pitfall 1: `feed_child` rejects `str` at the 0.76 floor
**What goes wrong:** `feed_child("claude\n")` raises `TypeError: Must be number, not str`.
**Why it happens:** The 0.76 GTK4 binding signature is `feed_child(self, text:list=None)` — it expects a list of ints (a `bytes` object). [VERIFIED: live — `b"claude\n"` works, `"claude\n"` fails]
**How to avoid:** Always `feed_child(b"claude\n")` (or `"claude\n".encode()`).
**Warning signs:** TypeError mentioning "number, not str" the first time you launch the agent.

### Pitfall 2: Default-branch detection assumes `origin`
**What goes wrong:** `git symbolic-ref refs/remotes/origin/HEAD` → `fatal: ref refs/remotes/origin/HEAD is not a symbolic ref` (or exit 128) on a remote-less repo. arduis's own repo triggers this and uses `master`, not `main`.
**Why it happens:** Many local-only / freshly-init repos have no `origin`, and the default branch may be `master`.
**How to avoid:** Fallback chain (verified on this repo):
1. `git symbolic-ref refs/remotes/origin/HEAD` → strip `refs/remotes/origin/` (when a remote exists)
2. else `git symbolic-ref --short HEAD` (→ `master` here) or `git rev-parse --abbrev-ref HEAD`
[VERIFIED: this repo — step 1 errors, step 2 returns `master`]
**Warning signs:** New branches always forking from a nonexistent `main`, or a fatal on creation.

### Pitfall 3: `git worktree add` of an already-checked-out branch is a hard error
**What goes wrong:** `git worktree add ../dir main` → `fatal: 'main' is already used by worktree at '<path>'`, **exit 128**. [VERIFIED: scratch repo]
**Why it happens:** git refuses to check the same branch out twice without `--force`. D-07 forbids `--force`.
**How to avoid:** Before `add`, parse `git worktree list --porcelain` (each record has a `branch refs/heads/<name>` or `detached` line; locked ones add a `locked` line). If the chosen branch is already a worktree arduis tracks → focus that tab (D-07). If it's checked out somewhere arduis doesn't track (the main copy) → clear message + abort. [VERIFIED: porcelain format with `branch`/`detached`/`locked` lines]
**Warning signs:** Worktree creation fails with exit 128 and a "already used by worktree" message.

### Pitfall 4: Race between shell init and the fed `claude`
**What goes wrong:** Feeding `claude\n` before the shell is reading its PTY can lose or mis-order the input.
**Why it happens:** `spawn_async` is async; the pid only exists once the callback fires.
**How to avoid:** Feed **from inside the spawn callback** (after a valid pid). `zsh -l -i` drains its input buffer once interactive, so a feed right after the pid is delivered is the standard, reliable point. [VERIFIED: spawn callback is the documented completion point; Phase-1 `_on_spawned` already captures the pid there]
**Warning signs:** `claude` occasionally not launching, or the command appearing before the prompt.

### Pitfall 5: Hibernate killing only the shell, orphaning `claude`
**What goes wrong:** Killing `pid` (the shell) leaves `claude` running, defeating RAM-01.
**Why it happens:** `claude` is a *child* of zsh in its own/shared process group; you must signal the **group**.
**How to avoid:** Reuse Phase-1's `os.getpgid(pid)` → `os.killpg(pgid, SIGHUP)` → SIGKILL grace. Store `pgid` on the session at spawn time.
**Warning signs:** RAM not dropping after hibernate; a stray `claude`/`node` in `ps`.

### Pitfall 6: Directory-name collision / unsafe branch chars (D-05)
**What goes wrong:** `feature/foo` → `../repo-feature/foo` creates a nested dir, or two branches sanitize to the same dir.
**Why it happens:** Branch names allow `/` and other chars illegal/ambiguous in a flat sibling dir name.
**How to avoid:** Sanitize: replace `/` and unsafe chars with `-`; if the target dir already exists, append a short disambiguator or refuse with a message. Keep sanitization in `worktree.py` (pure, unit-tested). [ASSUMED — exact sanitization scheme is Claude's discretion per CONTEXT; just make it pure + tested]
**Warning signs:** `git worktree add` failing because the dir exists, or two worktrees pointing at one dir.

### Pitfall 7: `Gio.Subprocess` callback mutating GTK while not on the main loop
**What goes wrong:** Touching widgets from the wrong context.
**Why it happens:** Misunderstanding — `communicate_utf8_async`'s callback **does** run on the main loop, so this is usually fine, but spawning threads around it is not.
**How to avoid:** Stick to `Gio.Subprocess` + `*_async` + GLib main loop; do not introduce `threading`/`asyncio` (CLAUDE.md footgun warning).

## Code Examples

### Default-branch detection chain (pure argv builders)
```python
# Source: git 2.43 behavior verified on this host + a scratch repo (2026-06-09)
# src/arduis/worktree.py  — GTK-FREE pure functions returning argv lists
def argv_default_branch_via_origin() -> list[str]:
    return ["git", "-C", "{repo}", "symbolic-ref", "refs/remotes/origin/HEAD"]
    # stdout: "refs/remotes/origin/main" → strip prefix → "main"
    # FAILS (exit 128) when no origin — caller falls through to:
def argv_default_branch_local() -> list[str]:
    return ["git", "-C", "{repo}", "symbolic-ref", "--short", "HEAD"]
    # stdout: "master" on this repo  [VERIFIED]
```

### worktree add argv — new vs existing
```python
# Source: scratch-repo verification 2026-06-09
# NEW branch off the detected base:
["git", "-C", repo, "worktree", "add", "-b", branch, worktree_dir, base]
# EXISTING branch (checks it out):
["git", "-C", repo, "worktree", "add", worktree_dir, branch]
# NEVER add "--force" (D-07).  Existing-branch add fails exit 128 if the
# branch is already checked out elsewhere → pre-check porcelain first.
```

### Porcelain pre-check parse (D-07)
```python
# Source: `git worktree list --porcelain` output verified 2026-06-09
# Records are blank-line-separated; lines of interest per record:
#   worktree <abs-path>
#   branch refs/heads/<name>     (or)  detached
#   locked                       (optional)
def parse_worktrees(porcelain: str) -> list[dict]:
    out, cur = [], {}
    for line in porcelain.splitlines():
        if not line:
            if cur: out.append(cur); cur = {}
            continue
        key, _, val = line.partition(" ")
        if key == "worktree": cur["path"] = val
        elif key == "branch": cur["branch"] = val.removeprefix("refs/heads/")
        elif key == "detached": cur["branch"] = None
        elif key == "locked": cur["locked"] = True
    if cur: out.append(cur)
    return out   # → check if chosen branch already in this list before add (D-07)
```

### feed claude after spawn (D-08 / WT-03) — bytes, in the callback
```python
# Source: Phase-1 window.py _on_spawned + live feed_child type check (2026-06-09)
def _on_worktree_spawned(self, terminal, pid, error, session):
    if error is not None or pid == -1:
        return                       # D-09: no banner; tab stays as a shell
    session.pid = pid
    session.pgid = os.getpgid(pid)   # for hibernate teardown (RAM-01)
    terminal.feed_child(b"claude\n") # MUST be bytes at 0.76 [VERIFIED]
```

### async git runner (never blocks the GTK loop)
```python
# Source: CLAUDE.md mandated pattern; Gio.Subprocess + communicate_utf8_async
# src/arduis/git_service.py  (the one new gi-importing service module)
from gi.repository import Gio
def run_git_async(argv: list[str], on_done) -> None:
    proc = Gio.Subprocess.new(argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE)
    def _cb(p, res):
        ok, out, err = p.communicate_utf8_finish(res)
        on_done(p.get_exit_status(), out or "", err or "")   # runs on the main loop
    proc.communicate_utf8_async(None, None, _cb)
```

### Hibernate / Resume reusing Phase-1 teardown (RAM-01, D-11/D-12)
```python
# Source: refactor of window.py _on_close_request/_sigkill_if_alive (Phase 1)
def _teardown_pgid(self, pid: int) -> None:
    """Extracted verbatim from Phase-1 close path — SIGHUP then SIGKILL grace."""
    try:
        pgid = os.getpgid(pid)
        os.killpg(pgid, signal.SIGHUP)
        GLib.timeout_add(_SIGKILL_GRACE_MS, self._sigkill_if_alive, pgid)
    except ProcessLookupError:
        pass

def _hibernate(self, session):           # D-11: kill group, KEEP the directory
    if session.pid: self._teardown_pgid(session.pid)
    session.pid = session.pgid = None
    session.state = SessionState.HIBERNATED
    page = self._page_for(session)
    page.set_needs_attention(True)       # dim/badge as suspended (D-10)

def _resume(self, session):              # D-12: cold relaunch == fresh create
    session.state = SessionState.ACTIVE
    terminal = self._terminal_for(session)
    self._spawn_into(terminal, session.worktree_dir, session)  # then feed b"claude\n"
```
> The window-close path (`_on_close_request`) should iterate **all** active sessions and `_teardown_pgid` each, so closing the window leaves no orphans across N worktrees (the Phase-1 guarantee generalized).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `Gtk.Notebook` tabs | `Adw.TabView`/`TabBar` | libadwaita 1.0 (2022) | Native tab state (attention/loading/indicator) used directly for hibernate badge — no custom CSS |
| `feed_child` taking a string | list-of-bytes signature in GI | VTE GTK4 binding | Must encode to `bytes` (the GTK4/0.76 binding) |
| Blocking `subprocess` for git | `Gio.Subprocess` async | GLib-era standard | UI stays responsive during `worktree add` |

**Deprecated/outdated:** Nothing in this phase pulls a deprecated API. All APIs are at-or-above the libadwaita 1.0 / VTE 0.76 floor and confirmed present on the 1.5.0/0.76.0 host.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `/proc/<pid>/statm` (resident pages × page size) is the right Phase-3 RSS source | Pattern 1 note | LOW — Phase 2 only carries the field; exact source confirmed in Phase 3 (RAM-03). No Phase-2 impact. |
| A2 | Directory-name sanitization scheme (replace `/` and unsafe chars with `-`, disambiguate on collision) | Pitfall 6 | LOW — exact scheme is Claude's discretion (D-05/CONTEXT); just needs to be pure + unit-tested. |
| A3 | Feeding `b"claude\n"` immediately in the spawn callback is reliably consumed by `zsh -l -i` | Pitfall 4 | MEDIUM — verify in the manual acceptance checklist; if a rare race appears, gate the feed on the first VTE `contents-changed`/prompt signal (a Phase-4-adjacent fallback, not needed by default). |

## Open Questions

1. **Tab label format & truncation** (Claude's discretion, D-Discretion)
   - What we know: options are branch name / repo:branch / dir name.
   - What's unclear: long-name truncation behavior in `Adw.TabView`.
   - Recommendation: use the **branch name** as `TabPage.set_title`; libadwaita truncates tab titles natively (ellipsis) — no custom logic. Decide in planning, not blocking.

2. **Creation progress feedback** (Claude's discretion)
   - What we know: `TabPage.set_loading(True)` shows a native spinner.
   - Recommendation: open the tab immediately with `set_loading(True)`, run `git worktree add` async, then spawn + feed on success and `set_loading(False)`. Gives instant "in seconds" feedback without a separate dialog/spinner. Non-blocking.

3. **Untracked-but-checked-out branch message** (D-07 abort case)
   - What we know: porcelain lists *all* worktrees including the main copy; arduis can detect the branch is checked out somewhere it doesn't own.
   - Recommendation: surface an `Adw.AlertDialog`/toast "Branch X is already checked out at <path>" and abort. Wording is discretion.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | App | ✓ | 3.12.3 | — |
| git (`worktree` subcmd) | WT-01/WT-02, D-07 | ✓ | 2.43.0 | — |
| Vte (GTK4, 3.91) | WT-03 feed/spawn | ✓ | 0.76.0 | — |
| libadwaita (`Adw.TabView`) | WT-01 UI (D-01) | ✓ | 1.5.0 (floor 1.0 API) | — |
| GTK4 | UI | ✓ | 4.14.5 | — |
| PyGObject | bindings | ✓ | 3.48.2 | — |
| pytest | validation | ✓ (in `.venv`) | 9.0.3 | run via `.venv/bin/python -m pytest` |
| ruff | lint | ✓ | 0.15.9 | — |
| `claude` CLI | WT-03 runtime (fed into shell) | not probed | — | **D-09: none needed** — missing `claude` just yields `command not found`; tab stays a usable shell. No blocker. |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** `claude` is intentionally not a hard dependency (D-09). System `pytest`/`ruff` are absent on PATH but present in `.venv` — use `.venv/bin/python -m pytest` / `.venv/bin/ruff` (the existing suite runs 15 tests green there [VERIFIED]).

## Validation Architecture

> nyquist_validation is enabled (config.json `workflow.nyquist_validation: true`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 (in `.venv`) |
| Config file | `pyproject.toml` → `[tool.pytest.ini_options]` (`testpaths=["tests"]`, `pythonpath=["src"]`, `addopts="-q"`) |
| Quick run command | `.venv/bin/python -m pytest -q tests/test_worktree.py tests/test_session.py -x` |
| Full suite command | `.venv/bin/python -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WT-01 | new-vs-existing inferred from branch list parse | unit | `.venv/bin/python -m pytest tests/test_worktree.py::test_infer_new_vs_existing -x` | ❌ Wave 0 |
| WT-02 | `worktree add` argv (new `-b`, existing) built correctly | unit | `.venv/bin/python -m pytest tests/test_worktree.py::test_add_argv -x` | ❌ Wave 0 |
| WT-02 | default-branch chain: origin→local fallback parse | unit | `.venv/bin/python -m pytest tests/test_worktree.py::test_default_branch_fallback -x` | ❌ Wave 0 |
| WT-02 | sibling dir path + branch-name sanitization (D-05) | unit | `.venv/bin/python -m pytest tests/test_worktree.py::test_sanitize_dir -x` | ❌ Wave 0 |
| WT-03 | `claude` is fed as **bytes**, not str (0.76 floor) | unit | `.venv/bin/python -m pytest tests/test_session.py::test_agent_feed_is_bytes -x` | ❌ Wave 0 |
| WT-03 | terminal opens with `claude` running in worktree dir | manual | acceptance checklist (GUI/Wayland) | ❌ checklist |
| D-07 / SC#3 | porcelain parse detects already-checked-out branch | unit | `.venv/bin/python -m pytest tests/test_worktree.py::test_detect_checked_out -x` | ❌ Wave 0 |
| D-07 / SC#3 | already-checked-out → focus existing / abort (no `--force`) | manual | acceptance checklist | ❌ checklist |
| RAM-01 | SessionStore add/get/by_branch + serializable (`to_dict`/`to_list`) | unit | `.venv/bin/python -m pytest tests/test_session.py::test_store_serializable -x` | ❌ Wave 0 |
| RAM-01 | hibernate sets state=HIBERNATED, clears pid/pgid; RAM fields present | unit | `.venv/bin/python -m pytest tests/test_session.py::test_hibernate_model -x` | ❌ Wave 0 |
| RAM-01 | hibernate kills the **process group** (no orphan), keeps dir | manual | acceptance checklist (observe RAM drop, dir survives) | ❌ checklist |

> **Why manual for GUI/teardown:** consistent with Phase-1 D-14 — interactive signal/teardown checks are a documented manual acceptance checklist (no heavy Wayland GUI harness); pure logic (argv, parse, model, bytes) is automated unit tests. Keep the same split.

### Sampling Rate
- **Per task commit:** `.venv/bin/python -m pytest -q tests/test_worktree.py tests/test_session.py -x`
- **Per wave merge:** `.venv/bin/python -m pytest -q` (full suite — must stay green, includes Phase-1 tests)
- **Phase gate:** Full suite green + the manual acceptance checklist (SC#2/#3/#4) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_worktree.py` — covers WT-01/WT-02/D-07 (argv builders, default-branch fallback, sanitize, porcelain parse, infer new/existing)
- [ ] `tests/test_session.py` — covers WT-03/RAM-01 (bytes-feed constant, SessionStore CRUD + serialization, hibernate model transition)
- [ ] No new framework install needed — pytest 9.0.3 already in `.venv`
- [ ] Manual acceptance checklist doc — SC#2 (claude running), SC#3 (already-checked-out graceful), SC#4 (hibernate frees RAM + dir kept, resume relaunches)

## Security Domain

> `security_enforcement` not present in config.json → treat as enabled. Phase 2 surface is local (no network, no auth, no crypto). Most ASVS categories are N/A; the live one is command/argv construction.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — (no auth surface) |
| V3 Session Management | no | — (no web session; "SessionStore" is local process state) |
| V4 Access Control | no | — (local desktop app) |
| V5 Input Validation | **yes** | Branch name + dir sanitization (D-05) handled in pure `worktree.py`; argv built as **lists**, never shell strings (Phase-1 threat T-01-01/T-01-02 carried forward) |
| V6 Cryptography | no | — (no crypto) |

### Known Threat Patterns for {Python git shell-out + VTE PTY}
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Shell/argument injection via branch name | Tampering / EoP | Build argv as **lists** routed through `HostRunner`; never `shell=True`, never join into a shell string (continues Phase-1 `spawn.py` discipline). `git -C <repo> worktree add ...` with the branch as a discrete argv element. |
| Path traversal via crafted branch name (`../`, abs paths) into the sibling dir | Tampering | Sanitize branch → safe dir component (D-05); compute the sibling dir from `repo_root` + sanitized leaf, never from raw user input; reject/normalize `..`. |
| `claude\n` fed input treated as untrusted | (low) | Fed string is a fixed literal `b"claude\n"` (not user-supplied in Phase 2; AGENT-01 configurability is Phase 5). |

## Sources

### Primary (HIGH confidence)
- **Live host introspection (2026-06-09):** `Vte.MINOR_VERSION==76`, `feed_child` requires `bytes` (str → `TypeError: Must be number, not str`), `spawn_async` present; `Adw 1.5.0`, `TabView/TabBar/TabPage` + `append/close_page/set_selected_page/set_needs_attention/set_loading/set_indicator_icon/set_menu_model` all present; `Gtk 4.14.5`; pytest 9.0.3 in `.venv`, 15 existing tests green.
- **Scratch-repo git verification (2026-06-09):** `worktree add -b` (new) / `worktree add <dir> <branch>` (existing); duplicate branch add → `fatal: ... already used by worktree`, **exit 128**; `worktree list --porcelain` record format (`worktree`/`branch refs/heads/...`/`detached`/`locked`).
- **This repo (2026-06-09):** `git symbolic-ref refs/remotes/origin/HEAD` → `fatal: not a symbolic ref` (no origin); `git symbolic-ref --short HEAD` → `master` — proves the default-branch fallback is mandatory.
- `src/arduis/window.py`, `spawn.py`, `host_runner.py` — Phase-1 reusable teardown + spawn + seam.
- CLAUDE.md — subprocess/process-management patterns, GTK-free-core rule, VTE 0.76 floor, no-`--force` not stated there but in CONTEXT D-07.

### Secondary (MEDIUM confidence)
- [Adw.TabPage:indicator-activatable (libadwaita 1.0.0 docs)](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1.0.0/property.TabPage.indicator-activatable.html) — confirms TabPage indicator API at the 1.0 floor.
- [Adw.TabView class docs](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/1.0/class.TabView.html) — TabView available since 1.0; later methods (`add_shortcuts` 1.2, `invalidate_thumbnails` 1.3) flagged, base methods unflagged → 1.0.
- [Vte spawn_async method docs](https://gnome.pages.gitlab.gnome.org/vte/gtk4/method.Terminal.spawn_async.html) — callback-on-completion semantics.

### Tertiary (LOW confidence)
- `/proc/<pid>/statm` as the Phase-3 RSS source (A1) — standard Linux knowledge, deferred verification to Phase 3.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every version introspected live on the floor host.
- Architecture: HIGH — extends an established, tested Phase-1 layering; new domain modules are pure stdlib.
- git mechanics: HIGH — add/list/default-branch all verified in scratch repos and on this repo.
- VTE feed timing: MEDIUM-HIGH — bytes requirement VERIFIED; "feed in callback" reliable but manual-acceptance-confirmed (A3).
- Pitfalls: HIGH — each pitfall reproduced or introspected this session.

**Research date:** 2026-06-09
**Valid until:** 2026-07-09 (stable system stack; refresh if the host distro upgrades VTE/libadwaita)
