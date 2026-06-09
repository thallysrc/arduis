# Phase 2: Core Loop (new worktree → env → agent) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-09
**Phase:** 02-core-loop-new-worktree-env-agent
**Areas discussed:** Worktree UI shape (interim), Repo + branch + location, Agent launch & Ctrl+C, Hibernate / resume (RAM-01), SessionStore persistence (clarified → v2)

---

## Worktree UI shape (interim)

| Option | Description | Selected |
|--------|-------------|----------|
| Tab strip | Each worktree = a tab (Adw.TabView/TabBar); $HOME terminal is tab 0; Phase-3 sidebar binds to same SessionStore | ✓ |
| Replace the terminal | One worktree at a time; creation swaps the current terminal | |
| New window per worktree | Each worktree opens its own top-level window | |

**User's choice:** Tab strip.

| Option | Description | Selected |
|--------|-------------|----------|
| Keep the $HOME shell | Phase-1 behavior unchanged; tab 0 = $HOME zsh; `+` on tab bar | ✓ |
| Open in the current repo | Tab 0 is a shell in the launch repo root | |
| No tab until you create one | Empty window + CTA; first worktree creates first tab | |

**User's choice:** Keep the $HOME shell as tab 0.

---

## Repo + branch + location

| Option | Description | Selected |
|--------|-------------|----------|
| Launch directory | Repo = `git rev-parse --show-toplevel` of arduis's cwd; button disabled outside a repo | ✓ |
| Folder picker | GTK folder chooser to pick repo | |
| Both: cwd default + picker override | cwd default plus a menu to pick another repo | |

**User's choice:** Launch directory.

| Option | Description | Selected |
|--------|-------------|----------|
| Default branch, auto-detected | Branch off origin/HEAD → main/master, detected via git | ✓ |
| Current HEAD | Branch off whatever is checked out in the main copy | |
| Ask each time | Prompt for base branch in the dialog | |

**User's choice:** Default branch, auto-detected.

| Option | Description | Selected |
|--------|-------------|----------|
| Sibling dir, named by branch | `../<repo>-<branch>` (matches docs location='../'), names sanitized | ✓ |
| Hidden dir inside repo | `.arduis/worktrees/<branch>` | |
| Central location under $HOME | `~/.local/share/arduis/worktrees/<repo>/<branch>` | |

**User's choice:** Sibling dir `../<repo>-<branch>`.

| Option | Description | Selected |
|--------|-------------|----------|
| Single combo: type-or-pick | One editable combo; type=new, pick=existing; infer automatically | ✓ |
| Explicit mode toggle | New/Existing segmented toggle switching entry vs list | |
| Text entry only | Type a name; exists→checkout else create; no list shown | |

**User's choice:** Single type-or-pick combo.

| Option | Description | Selected |
|--------|-------------|----------|
| Focus the existing tab | If branch already checked out in a tracked worktree, switch to its tab; clear message otherwise | ✓ |
| Clear message only | Always show an info/error dialog and abort | |

**User's choice:** Focus the existing tab (clear message when untracked).

---

## Agent launch & Ctrl+C

| Option | Description | Selected |
|--------|-------------|----------|
| Feed command into the PTY | Spawn `zsh -l -i` then `feed_child("claude\n")`; shell durable, claude is its child | ✓ |
| `zsh -ic 'claude; exec zsh'` | Run claude then drop to interactive shell | |
| Spawn claude as PTY child directly | No shell fallback — contradicts durable-shell rule | |

**User's choice:** Feed `claude\n` into the durable worktree shell.

| Option | Description | Selected |
|--------|-------------|----------|
| Land in the worktree shell | Missing/failed/exited claude leaves you at worktree zsh; no special handling | ✓ |
| Show an arduis error banner | Detect failure + surface in-app banner/toast | |

**User's choice:** Land in the worktree shell (no banner in Phase 2).

---

## Hibernate / resume (RAM-01)

| Option | Description | Selected |
|--------|-------------|----------|
| Tab context menu | Right-click tab → Hibernate; dimmed/badged; Resume from menu | ✓ |
| Header-bar button for active tab | Hibernate/resume button acting on focused tab | |
| Hibernate-on-tab-close prompt | Closing a tab asks Hibernate vs Conclude (pulls Phase-8 scope forward) | |

**User's choice:** Tab context menu.

| Option | Description | Selected |
|--------|-------------|----------|
| Kill whole PTY child; resume relaunches claude | SIGHUP→SIGKILL the zsh+claude group, keep dir; resume re-spawns + re-feeds claude | ✓ |
| Kill whole PTY child; resume = shell only | Same kill; resume drops to shell without auto-claude | |
| Kill only the agent, keep zsh alive | SIGINT just the claude child; weaker RAM win, fragile bookkeeping | |

**User's choice:** Kill whole PTY group; resume cold-relaunches claude.

---

## SessionStore persistence (clarified by user question)

**User question:** "What happens if I suspend my computer and reopen the app?"

Clarified the distinction:
- **OS suspend/resume** → all processes (arduis, worktree shells, agents) are frozen/restored
  by the OS and survive intact; nothing to build.
- **arduis quit/restart** → processes die; the open question was whether to persist + re-list
  worktrees.

**User's decision:** Defer persistence to v2 — "acho que isso fica para v2 né? foi o que foi
acordado." Aligns with PERSIST-01 (reattach to live agents = v2). Phase 2: SessionStore stays
**in-memory, GTK-free, serializable** (the seam) but is **not** persisted to disk.

---

## Claude's Discretion

- SessionStore shape / serialization format (GTK-free, serializable, RAM fields).
- Presentation→Domain→Service module layout; git argv construction.
- Creation progress feedback during worktree creation (user: "deixar pro Claude").
- Worktree tab label format + truncation (user: "deixar pro Claude").
- The empty named `swarm/` seam directory.

## Deferred Ideas

- Conclude/remove worktree + teardown ordering → Phase 8.
- Persist SessionStore / cold-reopen worktrees across app restart → v2.
- Reattach to a live agent after app quit → v2 (PERSIST-01).
- Repo folder-picker / multi-repo switching → not Phase 2.
- `.arduis.toml` worktree config → Phase 6 (Phase 2 hardcodes equivalents).
- Agent = configurable command / Ctrl+C swaps → Phase 5 (AGENT-01).
