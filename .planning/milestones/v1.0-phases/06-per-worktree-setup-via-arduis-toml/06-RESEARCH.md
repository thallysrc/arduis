# Phase 6: Per-Worktree Setup via `.arduis.toml` - Research

**Researched:** 2026-06-13
**Domain:** Repo-committed config parsing (stdlib `tomllib`) + visible setup-command execution through the existing VTE login shell + a trusted-repo security gate
**Confidence:** HIGH (entirely within the established arduis codebase + stdlib + already-proven VTE feed path; no new external dependency)

## Summary

Phase 6 makes a freshly created task "ready to work": each member repo may ship a committed `.arduis.toml` whose `[setup]` section lists shell commands (`npm install`, `cp .env.example .env`, migrate, seed) that arduis runs automatically in the new worktree, **visibly in a pane**, through the **same `zsh -l -i` login shell** the agent already uses — so `nvm`/`asdf`/`mise` shims and PATH resolve identically on Ubuntu and Arch. Because those commands come from a repo file, running them is arbitrary code execution; Phase 6's highest-care item is a **trusted-repo gate** that mirrors the Phase-4 consent dialog: an `Adw.AlertDialog` showing the exact commands, persisted as a per-repo trust record keyed by a **content hash of the setup commands** so a changed setup re-prompts.

The whole feature fits the existing seams with almost no new machinery. Reading is a tolerant stdlib `tomllib` reader in a new GTK-free `repoconfig.py` module — a near-clone of `agentconfig.load_agent_config` (missing/garbage file → empty setup → behaves exactly as today, satisfying criterion 1). Execution is **feeding the setup command bytes into the VTE shell terminal before the agent is fed** — this inherits the login-shell environment "for free" (criterion 3) and is naturally visible (criterion 2). The trust list is a new file under `~/.config/arduis/` written with the same atomic `tempfile.mkstemp` + `os.replace` pattern already used by `appconfig.write_theme` and the Phase-4 settings install.

**Primary recommendation:** Add a GTK-free `repoconfig.py` (`load_repo_setup(repo_dir) -> RepoSetup`) + a GTK-free `trust.py` (content-hash + tolerant trust-list read/write), then wire `window.py` to, **per repo that has a non-empty `[setup]`**, gate trust via an `Adw.AlertDialog`, and on accept feed the joined setup commands into that repo's **shell** terminal *before* feeding the agent. Setup runs on **CREATE only**, never on resume. No exit-code parsing in v1 — the live shell shows stdout/stderr/exit naturally.

## User Constraints

No `CONTEXT.md` exists for this phase (research spawned standalone / pre-discuss). The binding constraints come from `CLAUDE.md` (see Project Constraints below) and the phase goal. The orchestrator should treat the **Open Decisions** section as the discuss-phase surface; each carries a recommended default because the user is AFK.

## Project Constraints (from CLAUDE.md)

These are LOCKED — research must not contradict them; the planner must verify compliance:

- **Read-only TOML via stdlib `tomllib`** (Python 3.11+, verified 3.12.3 on host). `tomllib` cannot write — fine, `.arduis.toml` is hand-edited and committed in the repo, arduis only reads it. Do NOT add `tomli`/`tomlkit`/`tomli-w` as a dependency.
- **No `shell=True`, no joined shell strings as argv.** Build argv as lists; use `shlex` for any argv construction. (NOTE: setup commands are an explicit exception in spirit — see Pitfall "shell features" — they are *fed as text into a real interactive shell*, which is the user's intent, not built into a `subprocess` argv. They never touch `spawn_async` argv.)
- **All host execution funnels through the `HostRunner` seam.** Setup runs inside the VTE shell that `build_worktree_spawn(self._runner, …)` already spawns through the seam — no new spawn path, no `Gio.Subprocess`, no `flatpak-spawn`.
- **Login + interactive shell** (`zsh -l -i`, `SHELL_ARGV` in `spawn.py`) is mandatory so version-manager shims resolve. Setup MUST run through this same shell, not a fresh non-login `subprocess` (that would miss `.zprofile`/`.zshrc` and break `nvm`/`asdf`/`mise`).
- **Credentials / secrets are OUT OF SCOPE** (`PROJECT.md` Out of Scope; `CLAUDE.md` "credenciais/Jira fora"). A `[setup]` that needs secrets is the user's problem to solve in the repo (e.g. `cp .env.example .env` then hand-edit); arduis injects no secrets and stores none.
- **Never block the GTK main loop** — but setup runs *inside the VTE PTY child*, which is inherently async (VTE owns it), so there is no blocking concern here. No `subprocess.run` on the main loop.
- **VTE 0.76 API floor.** `feed_child` takes **bytes**, not str (the existing `AGENT_FEED = b"claude\n"` comment documents the `TypeError: Must be number, not str` at the floor). Setup feed bytes must be `.encode("utf-8")`.
- **Atomic best-effort writes** for any state file: `tempfile.mkstemp(dir=...)` + `os.replace`, swallow `OSError` (mirror `appconfig.write_theme` / `_install_hooks`).
- **Method: Accelerate/DORA** — small shippable degrau; `main` always working; the absent-file path must be a no-op so nothing regresses.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ENV-01 | `.arduis.toml` per repo is read with sensible defaults (works without the file) | `repoconfig.load_repo_setup` (tolerant `tomllib` reader, near-clone of `agentconfig.load_agent_config`). Missing/garbage/empty → `RepoSetup(commands=[])` → no setup runs → identical to today. (Standard Stack, Architecture Pattern 1) |
| ENV-02 | Setup commands run on worktree creation via the host login shell | Feed joined commands into the repo's **shell** VTE terminal (which is `zsh -l -i` via `build_worktree_spawn`/`HostRunner`) *before* feeding the agent. Runs in `_finalize_task_creation` / `_spawn_task_terminals`, CREATE path only. (Architecture Pattern 2; criteria 2 & 3) |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `tomllib` | stdlib (Python 3.12.3 verified on host) | Read `[setup]` from `.arduis.toml` | `[VERIFIED: python3 --version → 3.12.3]` Already the project's TOML reader (`agentconfig`, `appconfig`, `attention`); read-only is exactly the need. Zero new dependency. |
| `hashlib` | stdlib | Content hash of the setup commands for the trust key | `[VERIFIED: stdlib]` `hashlib.sha256` over the normalized command list → a stable trust key that *changes* when the repo's setup changes (re-prompt). No crypto-strength requirement; collision-resistance is plenty. |
| `shlex` | stdlib | (Display + safety only) escape commands shown in the trust dialog; NOT for building setup argv | `[VERIFIED: stdlib]` Already used by `agentconfig`. Setup is fed as raw shell text into the interactive shell (that is the user's intent), so `shlex` is used to *render* commands safely in the dialog, not to wrap them. |
| `tempfile` + `os.replace` | stdlib | Atomic best-effort write of the trust list | `[VERIFIED: codebase — appconfig.write_theme:104-109, window._install_hooks:653-658]` The established arduis atomic-write idiom. |
| `Vte.Terminal.feed_child` | system VTE 0.76 floor | Inject setup command bytes into the live login shell | `[VERIFIED: codebase — window.py:2379 feeds agent_feed; session.py:46 AGENT_FEED bytes]` Already the agent-launch mechanism; setup reuses it. Bytes only at the 0.76 floor. |
| `Adw.AlertDialog` | libadwaita 1.x | The trusted-repo confirmation gate | `[VERIFIED: codebase — window._present_hook_consent:605, _show_new_worktree dialogs:1860/1898]` The exact widget + response pattern Phase 4's consent gate uses; mirror it. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `Gio.Subprocess` | system | (NOT used for setup) | Listed only to reject it — see "Don't Hand-Roll". Setup must run in the VTE login shell, not a separate subprocess. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `tomllib` (read-only) | `tomlkit` (round-trip) | arduis only READS `.arduis.toml` — no round-trip need. `tomlkit` is a new dependency CLAUDE.md explicitly rejects for read-only config. Reject. |
| Feed into VTE shell | `Gio.Subprocess` running each command | Subprocess would be a non-login shell (misses `nvm`/`asdf`/`mise` shims — breaks criterion 3), NOT visible in a pane (breaks criterion 2), and Ctrl+C-uninterruptible. Feeding the VTE shell gives all three for free. Reject the subprocess path. |
| Content-hash trust key | Trust by repo path only | Path-only trust would silently run a *changed* setup the user never re-approved (a supply-chain hole: `git pull` brings a new malicious `[setup]`). Hash-keyed trust re-prompts on change — the secure choice. (See Trust-Gate Design.) |

**Installation:** None. Everything is stdlib + already-present system libs.

**Version verification:**
- `[VERIFIED: python3 --version]` → Python **3.12.3** on the host; `tomllib` present (3.11+).
- `[VERIFIED: codebase]` VTE feed/spawn path, `Adw.AlertDialog`, atomic-write idiom all already in `window.py`.

## Architecture Patterns

### Recommended Project Structure
```
src/arduis/
├── repoconfig.py     # NEW — GTK-free: load_repo_setup(repo_dir) -> RepoSetup (tomllib, tolerant)
├── trust.py          # NEW — GTK-free: setup_hash(commands) + load/save trust list (atomic)
├── session.py        # (unchanged model; setup is a transient action, not persisted state)
├── window.py         # WIRING: trust gate (Adw.AlertDialog) + feed setup into the shell on CREATE
└── spawn.py          # (unchanged — setup rides the existing zsh -l -i spawn)
tests/
├── test_repoconfig.py  # NEW — Wave 0 RED: schema parse + tolerant defaults + absent-file no-op
└── test_trust.py       # NEW — Wave 0 RED: hash stability/change + trust list round-trip + tolerant read
```

Keep ALL parsing/hashing/trust-list logic GTK-free (imports no `gi`) so it is unit-testable on the host without a display — the established arduis discipline (every `*config.py` is GTK-free; `window.py` is the only `gi`-touching wiring file). `[VERIFIED: codebase — agentconfig.py, appconfig.py, attention.py, project.py all import no gi]`

### Pattern 1: Tolerant stdlib config reader (clone `agentconfig.load_agent_config`)
**What:** A read-only `tomllib` loader that returns a safe default on ANY failure (missing file, `TOMLDecodeError`, wrong types, empty section).
**When to use:** Reading `[setup]` from each repo's `.arduis.toml`.
**Example:**
```python
# Source: codebase — src/arduis/agentconfig.py:23-40 (load_agent_config), adapted
# Tag: [VERIFIED: codebase pattern]
from dataclasses import dataclass, field
import os, tomllib

@dataclass
class RepoSetup:
    commands: list[str] = field(default_factory=list)   # ordered; [] = no setup

def load_repo_setup(repo_dir: str) -> RepoSetup:
    """Read [setup] commands from <repo_dir>/.arduis.toml (ENV-01).

    Missing file / invalid TOML / wrong types / empty list -> RepoSetup([])
    -> NO setup runs -> behaves exactly as today (criterion 1)."""
    path = os.path.join(repo_dir, ".arduis.toml")
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return RepoSetup()
    section = data.get("setup")
    if not isinstance(section, dict):
        return RepoSetup()
    raw = section.get("commands")
    if not isinstance(raw, list):
        return RepoSetup()
    # keep only non-empty strings, stripped, in order
    cmds = [c.strip() for c in raw if isinstance(c, str) and c.strip()]
    return RepoSetup(commands=cmds)
```

### Pattern 2: Feed setup into the live login shell BEFORE the agent (criteria 2 & 3)
**What:** After a repo's worktree exists and its shell terminal has spawned, `feed_child` the setup commands (joined with `&&` or newline-separated) as bytes into that shell; the agent feed happens after.
**When to use:** On the CREATE path only, per repo with a non-empty + trusted `[setup]`.
**Example:**
```python
# Source: codebase — window.py:2379 feed_child(agent_feed); session.py:46 bytes-only
# Tag: [VERIFIED: codebase pattern]
def setup_feed_bytes(commands: list[str]) -> bytes:
    """Join setup commands for the interactive shell. Newline-separated runs each
    sequentially and shows each + its output; the shell's own exit codes are
    visible (criterion 2). NO shlex-wrapping — these are raw shell lines the user
    authored (cd/&&/$VAR are intentional)."""
    return ("\n".join(commands) + "\n").encode("utf-8")  # bytes at 0.76 floor
# fed via: shell_terminal.feed_child(setup_feed_bytes(setup.commands))
```
**Ordering:** the existing flow is shell spawns → (Phase-4) agent spawns + `feed_child(agent_feed)`. Insert the setup feed into the **shell** terminal in its spawn callback, BEFORE the agent terminal is fed `claude`, so `npm install` is already scrolling when the agent comes up. The shell terminal (`{task}:t1`, `kind="shell"`) is the natural host: it is plain `zsh`, not running the agent, so feeding commands there does not collide with the agent TUI.

### Pattern 3: Trust gate mirroring the Phase-4 consent dialog
**What:** Before feeding any setup, if the repo's setup-hash is not in the trust list, present an `Adw.AlertDialog` listing the exact commands; on "Confiar e rodar" persist the hash + feed; on "Pular" skip feeding (the worktree still opens, just without setup).
**When to use:** Per repo with a non-empty `[setup]`, on CREATE.
**Example:** mirror `window._present_hook_consent` (`Adw.AlertDialog` + `add_response` + `set_response_appearance(SUGGESTED)` + `connect("response", ...)`). `[VERIFIED: codebase — window.py:601-635]`

### Anti-Patterns to Avoid
- **Running setup via `Gio.Subprocess` / `subprocess.run`:** loses the login shell (breaks shims/criterion 3), loses visibility (breaks criterion 2). Feed the VTE shell instead.
- **Re-running setup on RESUME:** a resumed task already has `node_modules`/`.env`; re-running wastes minutes and can clobber state. Setup is CREATE-only.
- **Trusting by repo path alone:** a `git pull` that adds a hostile `[setup]` would auto-run unapproved. Key trust by content hash.
- **`shlex`-wrapping each setup command:** these are shell *lines* (the user wants `cd x && npm i`, `cp a b`, `$VAR`); wrapping them as a single argv breaks intent. Feed raw.
- **Parsing exit codes / gating the agent on setup success in v1:** over-engineering; the live shell already shows failures. Keep v1 simple (see Open Decision OD-5).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TOML parsing | A hand regex/INI parser | `tomllib` (stdlib) | Already the project standard; handles arrays/types correctly. |
| Running commands in the login env | A custom PTY / `Gio.Subprocess` with a sourced rc | The existing VTE `zsh -l -i` shell terminal via `feed_child` | VTE already owns a login-interactive PTY with the user's full env, visible, Ctrl+C-able. `[CITED: CLAUDE.md "Hand-rolling a PTY layer → VTE already owns/forwards the PTY"]` |
| Trust-list / consent | A new bespoke prompt + storage scheme | Clone `_present_hook_consent` + the atomic-write idiom | Phase 4 already shipped + threat-modeled a consent gate; reuse the proven pattern. |
| Atomic config write | Plain `open(...).write()` | `tempfile.mkstemp(dir=...)` + `os.replace` | A torn write can't corrupt the trust list (matters: it is a security record). `[VERIFIED: codebase — appconfig.write_theme]` |

**Key insight:** Phase 6 introduces *zero* new runtime mechanisms. Every piece (tolerant TOML read, VTE feed, consent dialog, atomic write) already exists in the codebase — Phase 6 is composition + one security idea (hash-keyed trust).

## Trust-Gate Design (criterion 4 — the highest-care item)

**Threat:** `.arduis.toml` is committed in the repo. On `git worktree add`, arduis would otherwise run arbitrary commands the repo author chose — classic supply-chain RCE (a malicious or compromised repo, or a teammate's mistake). This is the security crux of the phase.

**Model (recommended):**
1. **Trust is per-repo, keyed by a content hash of the setup commands.** `setup_hash = sha256("\n".join(commands).encode()).hexdigest()`. Store a record `{repo_identity: setup_hash}` (or a set of trusted `(repo_identity, hash)` pairs). `[VERIFIED: stdlib hashlib]`
2. **Repo identity:** the repo's canonical path (`os.path.realpath` of the member repo's source dir, e.g. `<project_root>/<repo_name>`), NOT the worktree dir (worktrees are per-task and ephemeral; the trust decision is about the *repo*). See OD-3 for the path-vs-remote alternative.
3. **First run / changed setup → prompt.** If `(repo_identity, current_hash)` is not in the trust list, present the dialog showing the **exact commands** (one per line, `shlex.quote`-rendered for unambiguous display). "Confiar e rodar" → persist `(repo_identity, current_hash)` + feed. "Pular" → do not feed; do NOT persist (so next create re-prompts — a skip is not a permanent decline).
4. **Changed setup re-prompts automatically** because the hash changes — this is the whole reason to key by hash. A repo the user trusted yesterday that `git pull`s a new `[setup]` today re-prompts.
5. **Persist location:** a new file under `~/.config/arduis/` — recommend `~/.config/arduis/trusted_setups.toml` (TOML, consistent with the rest) or a JSON sidecar. Written atomically, read tolerantly (missing/garbage → empty trust list → everything re-prompts, the safe default). `[VERIFIED: codebase atomic-write idiom]`
6. **Empty `[setup]` → no gate, no dialog.** Only repos that actually want to run commands trigger the gate (most repos won't ship `.arduis.toml` at all → criterion 1 no-op path).

**Why hash, not path-only:** path-only trust means a changed setup runs unapproved — a real hole. Hash-keyed costs nothing and closes it. This mirrors how Phase 4's consent is a one-time *capability* grant, but setup needs a *content*-bound grant because the content is attacker-controlled.

**Multi-repo task:** a task can span N repos, each with its OWN `.arduis.toml`. The gate is **per repo**: gather all repos with non-empty setup, and either (a) present one dialog per repo, or (b) present one consolidated dialog grouping commands by repo (recommended — fewer interruptions; see OD-2). Each repo's setup feeds into a terminal rooted in *that repo's worktree dir* (criterion: `cd` semantics — see Pitfall), not the task root, so relative paths in the setup resolve.

## Common Pitfalls

### Pitfall 1: Setup needs the repo's own worktree dir, but the default terminal is at the task root
**What goes wrong:** Under the 03.2 UX pivot, the two default terminals open at `task.task_dir` (the task root mirror), not inside any one repo. A multi-repo task feeding `npm install` into the task-root shell runs it in the wrong directory.
**Why it happens:** The task model decoupled terminals from repos (`session.py` docstring: terminals are task-level, `repo_name=None`).
**How to avoid:** For each repo with setup, feed `cd <repo_worktree_dir> && <commands>` (or spawn a transient per-repo setup terminal at that worktree dir — OD-1). In the degenerate 1-repo task, `_task_root_cwd` already returns the sole repo's worktree dir (`window.py:2193-2195`), so a `cd` prefix is harmless there. Recommended default: prefix each repo's setup block with a `cd` to its `worktree_dir` (relative or absolute) so it works regardless of where the host shell sits.

### Pitfall 2: Feeding setup into the AGENT terminal collides with the claude TUI
**What goes wrong:** If setup is fed into the agent terminal (`t0`), the bytes land mid-`claude` startup and get eaten by the TUI or corrupt its input.
**How to avoid:** Feed setup into the **shell** terminal (`t1`, `kind="shell"`, plain zsh) — never the agent. Sequence: shell spawns → feed setup into shell → agent spawns → feed `claude` into agent. `[VERIFIED: codebase — kind distinction at window.py:2378, session.py default_task_terminals t0=agent/t1=shell]`

### Pitfall 3: Re-running setup on resume re-installs / clobbers
**What goes wrong:** A resumed (hibernated/auto-suspended) task already has `node_modules`, a `.env`, a seeded DB. Re-running setup wastes time and can overwrite the user's edited `.env`.
**How to avoid:** Setup runs ONLY on the CREATE path (`_finalize_task_creation`/initial `_spawn_task_terminals`), NEVER on `_resume_task`. The two paths already share `_build_task_workspace`/`_spawn_task_terminals` — gate the setup feed on a "this is a fresh create" flag, not on spawn alone. `[VERIFIED: codebase — _build_task_workspace shared by _create_task and _resume_task per docstring window.py:2006-2008]`

### Pitfall 4: A setup command hangs (interactive prompt, dev server, `npm install` waiting on a TTY)
**What goes wrong:** A command like a dev server or an interactive prompt never returns; the agent feed (which follows) queues behind it or the pane looks stuck.
**How to avoid:** It is a REAL interactive shell — the user can Ctrl+C (criterion of the VTE design). Feed setup into the SHELL terminal so the agent terminal is independent and usable regardless. Document that setup commands should be non-interactive/terminating (the user owns the `.arduis.toml`). No timeout machinery in v1.

### Pitfall 5: `feed_child` requires bytes (0.76 floor)
**What goes wrong:** Feeding a `str` raises `TypeError: Must be number, not str`.
**How to avoid:** `.encode("utf-8")` the joined commands (mirror `AGENT_FEED = b"claude\n"`). `[VERIFIED: codebase — session.py:46 comment]`

### Pitfall 6: Trust-by-path lets a changed setup auto-run
Covered in Trust-Gate Design — key by content hash.

### Pitfall 7: Garbage `.arduis.toml` must not crash task creation
**What goes wrong:** A malformed `.arduis.toml` raises `TOMLDecodeError` and aborts the create chain.
**How to avoid:** The tolerant reader swallows `TOMLDecodeError`/`OSError` → `RepoSetup([])` → no setup, worktree still opens (criterion 1). `[VERIFIED: codebase — agentconfig.py:32 swallows both]`

### Pitfall 8: Secrets in setup are out of scope
A `[setup]` that does `export TOKEN=...` or fetches secrets is the user's responsibility; arduis injects/stores nothing. `cp .env.example .env` is fine (no secret), but arduis does not populate the values. `[CITED: CLAUDE.md / PROJECT.md Out of Scope]`

## `.arduis.toml` Schema Proposal (ENV-01)

Minimal, forward-compatible (Phase 7 will add `[containers]`; Phase 5 already conceptually owns `[agent]` at the *user* level — keep per-repo overrides out of scope for v1 unless trivial):

```toml
# <repo-root>/.arduis.toml  — committed in the repo, hand-edited.
# DISTINCT from the user-level ~/.config/arduis/arduis.toml ([attention]/[agent]/[keys]/[theme]).

[setup]
# Ordered list of shell commands run, in order, in the new worktree on CREATE,
# inside the host login shell (zsh -l -i) so nvm/asdf/mise + PATH resolve.
# Runs ONLY on create (not resume). Trusted-repo gated on first run / on change.
commands = [
  "npm install",
  "cp .env.example .env",
  "npm run db:migrate",
  "npm run db:seed",
]
```

**Sensible default (criterion 1):** no file, or no `[setup]`, or `commands = []` → nothing runs → identical to today's behavior. This is the dominant path (most repos won't have the file).

**Forward-compat note for the planner:** keep the reader scoped to `[setup].commands` only; ignore unknown sections/keys silently so Phase 7's `[containers]` (and any future keys) can be added to the same file without breaking the Phase-6 reader. Do NOT validate-and-reject unknown keys.

## Code Examples

### Compute the trust hash (stable + change-sensitive)
```python
# Source: stdlib hashlib — [VERIFIED: stdlib]
import hashlib

def setup_hash(commands: list[str]) -> str:
    """Stable over identical command lists; changes when any command changes,
    is added, removed, or reordered (order is semantically meaningful for setup)."""
    payload = "\n".join(commands).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
```

### Tolerant trust-list read (safe default = empty = re-prompt everything)
```python
# Source: codebase pattern — appconfig.load_theme_name tolerance — [VERIFIED: codebase pattern]
import tomllib, os

def load_trusted(path: str) -> dict[str, str]:
    """Return {repo_identity: trusted_hash}. Missing/garbage -> {} (re-prompt all)."""
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    trusted = data.get("trusted")
    if not isinstance(trusted, dict):
        return {}
    return {k: v for k, v in trusted.items() if isinstance(v, str)}
```

(Atomic write mirrors `appconfig.write_theme`'s `_serialize` + `tempfile.mkstemp` + `os.replace`; reuse that serializer or a JSON one — see OD-4.)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| (n/a — greenfield phase) | Repo-committed setup with a trusted-repo gate | — | Comparable to VS Code "Workspace Trust", `direnv`'s `direnv allow` (hash-pinned approval), and `mise`/`asdf` trust prompts — all gate repo-supplied executable config behind explicit, content-pinned user consent. arduis's hash-keyed trust mirrors `direnv allow` exactly. `[CITED: direnv `direnv allow` content-hash model — well-known; ASSUMED parallel, not re-verified this session]` |

**Deprecated/outdated:** none.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `direnv`/VS-Code-Workspace-Trust use a content-hash/explicit-approval trust model that arduis's hash-keyed gate parallels | State of the Art | Low — the *design rationale* stands on its own (changed content must re-prompt); the analogy is illustrative, not load-bearing. |
| A2 | Feeding `cd <repo> && <cmds>` into the task-root shell is the cleanest multi-repo fit vs. a transient per-repo setup terminal | Pitfall 1 / OD-1 | Medium — if discuss-phase prefers a dedicated visible setup pane per repo, the wiring differs (still feeds VTE, just a different terminal). Both satisfy the criteria. |
| A3 | The user wants ONE consolidated trust dialog for a multi-repo task rather than N dialogs | OD-2 | Low — UX preference; either works. Defaulted to consolidated to minimize interruption. |
| A4 | No per-repo `[agent]`/`[theme]` override is wanted in v1 (per-repo file is setup-only for now) | Schema | Low — phase goal + ROADMAP scope `.arduis.toml` to setup for Phase 6; containers are Phase 7. Adding more is scope creep. |

## Open Decisions (each with a recommended default — orchestrator decides, user AFK)

**OD-1 — Where setup runs visibly (which terminal/pane):**
- Options: (a) feed `cd <repo> && <cmds>` into the existing default **shell** terminal (`t1`); (b) spawn a transient dedicated "setup" terminal per repo, rooted at that repo's worktree, that the user watches and which stays as a shell after.
- **Recommended default: (a)** — reuses the existing shell terminal, zero new layout machinery, setup scrolls in a pane the user already sees, and the shell remains usable after. Simplest shippable degrau. Prefix each repo's block with `cd <worktree_dir>` to fix Pitfall 1.

**OD-2 — One dialog or N for a multi-repo task:**
- **Recommended default: ONE consolidated `Adw.AlertDialog`** grouping commands under each repo name, with a single "Confiar e rodar" / "Pular". Persists a trust record per repo. Fewer interruptions; matches the "task is the unit" mental model. (If any repo's setup is already trusted, omit it from the dialog and run it silently.)

**OD-3 — Trust identity: repo path vs. git remote URL:**
- Options: (a) `os.path.realpath(<project_root>/<repo_name>)`; (b) the repo's `origin` remote URL.
- **Recommended default: (a) realpath of the repo source dir** — no extra git call, deterministic, matches "trust this checkout on this machine." Remote-URL identity is more portable but costs a `git remote get-url` and conflates forks/mirrors. Keep it simple for v1.

**OD-4 — Trust-list file format & path:**
- **Recommended default: `~/.config/arduis/trusted_setups.toml`** with a `[trusted]` table `{repo_path = sha256hex}`, written via the existing `appconfig._serialize` atomic idiom. Keeps everything TOML + reuses code. (JSON is equally fine; TOML is more consistent.)

**OD-5 — Surface setup failure?**
- Options: (a) do nothing (the shell shows stderr + non-zero exit naturally); (b) softly note "setup falhou" if the last command exited non-zero.
- **Recommended default: (a) do nothing in v1** — no exit-code parsing, no agent gating. The live shell is self-evident; failing setup must NOT block the agent or crash creation (phase criterion). Revisit soft surfacing in a later degrau if dogfooding demands it.

**OD-6 — Sequential `\n` vs. `&&` joining:**
- Options: newline-joined (each command runs and shows regardless of prior failure) vs. `&&`-joined (stop on first failure).
- **Recommended default: newline-joined per repo, but `cd <repo> &&` only as the directory guard.** Newline-joining shows every command + output even if an earlier one fails (more debuggable), and matches "the shell shows everything" (criterion 2). Do NOT `&&`-chain the whole list — one failure shouldn't silently swallow the rest from view.

## Open Questions

1. **Does the user ever want setup on a *manual* resume of a freshly-created-but-never-run task?**
   - What we know: setup is CREATE-only by design (Pitfall 3).
   - What's unclear: edge case where create's setup was "Pular"'d and the user later wants to run it.
   - Recommendation: out of scope for v1; the user can run the commands by hand in the shell pane. Defer.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python `tomllib` | ENV-01 read | ✓ | 3.12.3 (stdlib) | — |
| `hashlib`/`shlex`/`tempfile` | trust gate | ✓ | stdlib | — |
| System VTE (Vte-3.91) `feed_child` | ENV-02 run | ✓ | 0.76 floor (Ubuntu) / 0.84 (Arch) | — |
| libadwaita `Adw.AlertDialog` | trust dialog | ✓ | 1.x (already used) | — |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** none. (Note: the *setup commands themselves* — `npm`, `mise`, etc. — are the USER's repo's dependencies, resolved by their login shell; arduis does not probe them. A missing `npm` simply errors visibly in the pane, which is correct behavior.)

## Validation Architecture

`nyquist_validation` is enabled (config.json `workflow.nyquist_validation: true`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | none top-level detected — tests run from `tests/`; venv is `/tmp` `--system-site-packages` per MEMORY (arduis-dev-environment) |
| Quick run command | `python -m pytest tests/test_repoconfig.py tests/test_trust.py -x` |
| Full suite command | `python -m pytest tests/ -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ENV-01 | Missing/garbage/empty `.arduis.toml` → `RepoSetup([])` (no-op default) | unit | `pytest tests/test_repoconfig.py -x` | ❌ Wave 0 |
| ENV-01 | Valid `[setup].commands` parsed in order, non-str/blank entries dropped | unit | `pytest tests/test_repoconfig.py -x` | ❌ Wave 0 |
| ENV-02 | `setup_feed_bytes` returns bytes, newline-terminated, order preserved | unit | `pytest tests/test_repoconfig.py -x` (or a feed module) | ❌ Wave 0 |
| ENV-02/crit-4 | `setup_hash` stable for identical lists, changes on add/remove/reorder/edit | unit | `pytest tests/test_trust.py -x` | ❌ Wave 0 |
| crit-4 | Trust list tolerant read (missing/garbage → {}) + atomic round-trip | unit | `pytest tests/test_trust.py -x` | ❌ Wave 0 |
| crit-2/3 | Setup feeds into shell terminal, CREATE-only, login shell | manual UAT | headless broadway smoke + live (`06-HUMAN-UAT.md`) | manual |
| crit-4 | Trust dialog shows exact commands; accept persists hash, skip re-prompts | manual UAT | live | manual |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/test_repoconfig.py tests/test_trust.py -x`
- **Per wave merge:** `python -m pytest tests/ -q`
- **Phase gate:** full suite green + headless broadway smoke (mirror `tests/smoke/` Phase-4/5 pattern) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_repoconfig.py` — covers ENV-01 (tolerant parse + defaults) and `setup_feed_bytes`
- [ ] `tests/test_trust.py` — covers `setup_hash` stability/change + trust-list tolerant read + atomic write round-trip
- [ ] (Wiring/UI) `06-HUMAN-UAT.md` for the 4 success criteria (visible setup, login-shell shims, trust dialog, absent-file no-op) and a headless broadway smoke under `tests/smoke/`

## Security Domain

`security_enforcement` not set to false in config → enabled. This phase IS a security feature (criterion 4).

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V1 Architecture / Trust Boundaries | yes | Treat the repo-committed `.arduis.toml` as UNTRUSTED input crossing into code execution; gate with explicit, content-pinned consent. |
| V5 Input Validation | yes | Tolerant `tomllib` parse; only `[setup].commands` string entries accepted; never crash on malformed input. |
| V4 Access Control / Authorization | yes | The trust gate is the authorization decision: no setup runs without per-repo, per-content user approval. |
| V6 Cryptography | partial | `hashlib.sha256` used as a *content fingerprint* for the trust key (not a security secret) — collision resistance suffices; do not hand-roll a hash. |
| V2 Authentication | no | — |
| V3 Session Management | no | — |

### Known Threat Patterns for repo-supplied executable config
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious/compromised repo ships hostile `[setup]` → RCE on `worktree add` | Elevation of Privilege / Tampering | Trusted-repo gate; commands shown verbatim before running; no auto-run. |
| `git pull` swaps a trusted setup for a hostile one | Tampering | Content-hash trust key → changed setup re-prompts (the reason to hash, not path-trust). |
| Path traversal / dir-name injection via repo names in the feed | Tampering | Repo names already only land as discrete git-argv elements (`project.py` T-03.2-04); setup `cd` target is the resolved `worktree_dir`, not user text. |
| Trust-list corruption hides a prior decline / forges trust | Tampering | Atomic write (no torn file); tolerant read defaults to EMPTY (re-prompt) — fail-closed, never fail-open. |
| `feed_child` injection via crafted command bytes into the agent TUI | Tampering | Feed setup into the SHELL terminal, never the agent (Pitfall 2). |
| Setup exfiltrates secrets | Information Disclosure | Out of scope to *prevent* arbitrary user-approved commands, but arduis injects/stores NO secrets (scope boundary); the trust gate is the user's checkpoint. |

## Sources

### Primary (HIGH confidence)
- Codebase — `src/arduis/agentconfig.py`, `appconfig.py`, `attention.py`, `project.py`, `session.py`, `spawn.py`, `window.py` (consent dialog `:601-635`, task create chain `:1944-2183`, spawn/feed `:2280-2380`, config region `:285-344`) — the exact patterns Phase 6 composes.
- `[VERIFIED: python3 --version]` → Python 3.12.3 (tomllib present).
- `CLAUDE.md` — locked stack/constraints (tomllib read-only, HostRunner seam, login shell, secrets out, VTE 0.76 floor, atomic writes).
- `.planning/ROADMAP.md` Phase 6 / `.planning/REQUIREMENTS.md` ENV-01/ENV-02 — scope.

### Secondary (MEDIUM confidence)
- `MEMORY.md` (arduis-dev-environment) — pytest via `/tmp` venv `--system-site-packages`; headless GTK via broadway. Used for the Validation Architecture commands.

### Tertiary (LOW confidence)
- `direnv allow` / VS Code Workspace Trust content-hash analogy — ASSUMED (A1), illustrative only.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all stdlib + already-present system libs, verified in-repo.
- Architecture: HIGH — every mechanism (tolerant reader, VTE feed, consent dialog, atomic write) is an existing, tested codebase pattern; Phase 6 is composition.
- Trust gate: HIGH on mechanism (mirrors Phase 4), MEDIUM on the specific identity/format choices (captured as OD-3/OD-4 with defaults).
- Pitfalls: HIGH — derived from the actual task-creation/spawn code and the 03.2 UX pivot.

**Research date:** 2026-06-13
**Valid until:** ~30 days (stable — stdlib + in-repo patterns; no fast-moving external dependency).
