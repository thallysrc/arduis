# Phase 4: Attention Detection (who's waiting) - Research

**Researched:** 2026-06-12
**Domain:** Claude Code hooks → state files → GTK status surface (sidebar/pane dots, libnotify, idle auto-suspend)
**Confidence:** HIGH (hooks mechanics verified against current docs + this machine's real Claude Code 2.1.175 install; VTE floor verified; gi bindings probed locally)

## Summary

The hooks-first bet is **confirmed and stronger than expected**. Claude Code (verified 2.1.175 on this machine) ships a rich hook system: the `Notification` event now carries a `notification_type` field (`permission_prompt | idle_prompt | elicitation_dialog | ...`) that cleanly separates "real approval prompt" from "sat idle 60s" — exactly the disambiguation success criterion 3 needs. `Stop` carries `stop_reason`, `UserPromptSubmit`/`PostToolUse` bracket the running window, and `SessionStart`/`SessionEnd` bracket the agent's lifetime. Hooks from **all settings scopes MERGE (all run, deduplicated)** — so arduis can add its own hook entries without ever clobbering the user's existing hooks (this user's `~/.claude/settings.json` was inspected: it is dense with GSD hooks plus a `notify-send` Notification hook, and merge semantics mean they all coexist) [VERIFIED: code.claude.com/docs/en/hooks + local inspection].

The load-bearing design choice is the **injection channel**. Three options were evaluated; the winner is a **single env-guarded hook script registered once at user level (`~/.claude/settings.json`), additive-merge with consent**. The script exits 0 instantly unless `ARDUIS_STATE_FILE` is set in its environment — and arduis sets that variable per-terminal in the VTE spawn `envv`. This makes the hook a guaranteed no-op for the user's normal tmux/CLI claude sessions, survives `Ctrl+C` + manual relaunch of `claude` inside an arduis terminal (Phase 5 agent-swap compatible), works regardless of which subdirectory the user runs `claude` from, and avoids the workspace-trust dialog (user-level hooks are exempt; project-level hooks are not) [CITED: code.claude.com/docs/en/settings]. The two rejected options have concrete disqualifiers documented below — notably that `symlink_plan` symlinks the project root's `.claude/` into the task dir, so writing settings there would pollute the user's real project.

State files live in `$XDG_RUNTIME_DIR/arduis/status/` (tmpfs, 0700, auto-cleared at logout — verified present), written atomically (`mkstemp` + `os.replace`), watched with `Gio.FileMonitor` on the GLib main loop (no threads). VTE at the 0.76 floor has **no OSC 133/termprops access** (those are 0.78+) — the secondary signal is the ancient `bell` signal + `contents-changed` activity timestamps, used only as a degraded mode when the user declines hook installation. `libnotify` (gir `Notify 0.7`) is verified importable on this machine; `GSound` is NOT installed — sound stays optional with a graceful fallback.

**Primary recommendation:** One stdlib-only python3 hook script (env-guarded no-op), registered additively in `~/.claude/settings.json` with user consent, mapping 7 hook events to a 5-state model (running/waiting/ready/idle/ended); per-terminal state files in `XDG_RUNTIME_DIR` keyed by paths arduis itself composes; `Gio.FileMonitor` + the existing 2s poll drive the dots, libnotify drives unfocused notifications, and the READY+threshold timer drives opt-in auto-suspend with `claude --continue` on resume.

## Project Constraints (from CLAUDE.md)

- **GLib main loop only, no threads** — file watching must be `Gio.FileMonitor` / GLib timeouts, never a watcher thread.
- **VTE 0.76 API floor** (Ubuntu 24.04) — no termprops, no `shell-precmd/preexec` signals (0.78+); `bell` and `contents-changed` are within the floor.
- **Attention detection is HOOKS-FIRST**; text-scraping is explicitly NOT the primary signal (non-Claude agents = v2 / STATUS-04).
- **Distro packages, not pip** — any new dependency must exist as `gir1.2-*` (Ubuntu) / pacman (Arch) packages and be optional where possible.
- **`shlex`/argv lists, never shell strings**, when constructing host commands; all host execution through `HostRunner`.
- **Lightweight / first-class RAM management** — RAM-04 auto-suspend integrates with the existing hibernate machinery; hook overhead must be negligible.
- **pt-BR UI strings** (established convention: "Hibernar", "Retomar", "agentes ativos").
- **arduis NEVER deletes user data from disk** (D-10) — state files in `XDG_RUNTIME_DIR` are arduis-owned runtime data and exempt; `~/.claude/settings.json` edits must be additive-only with backup.
- **GSD workflow enforcement** — implementation goes through `/gsd-execute-phase`.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STATUS-01 | Detect "aguardando input" via Claude Code hooks (`Notification`/`Stop` → state file) | Hook events + payloads verified current (incl. `notification_type`); env-guarded script design; additive user-level settings merge; atomic state files in `XDG_RUNTIME_DIR`; `Gio.FileMonitor` watch |
| STATUS-02 | Status indicator (running/waiting/idle/ready) on sidebar + pane header | 5-state model + event→state map; task aggregation rule (waiting > running > ready > idle); existing `_DOT_*` CSS machinery + `_make_row`/`_make_leaf` extension points located in window.py |
| STATUS-03 | Desktop notification (libnotify) + optional sound when agent enters waiting and window unfocused | `Notify 0.7` gir verified importable locally; `Gtk.Window:is-active` property for focus; GSound absent → optional dep with `Gdk.Display.beep()`/no-sound fallback |
| RAM-04 | Auto-suspend idle worktrees (tied to detected idle status) | IDLE = READY + threshold (never from RUNNING — long tool calls safe); reuses `_on_hibernate` path; `claude --continue` (flag verified in 2.1.175 `--help`) restores the conversation on resume |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Claude Code hooks | 2.1.175 (verified on host) | Primary attention signal | Event-driven, immune to TUI repaints; `notification_type` disambiguates approval vs idle [VERIFIED: `claude --version` + docs] |
| Gio.FileMonitor (PyGObject) | system | Watch the status dir on the GLib main loop | inotify-backed, no threads, native GTK-loop integration [CITED: GNOME Gio docs] |
| libnotify via gir (`Notify` 0.7) | system | Desktop notification (STATUS-03) | Works without a `.desktop` file (unlike `Gio.Notification`, which silently drops on GNOME without a matching app-id desktop entry — arduis isn't packaged until Phase 9) [VERIFIED: local `gi.require_version("Notify","0.7")` OK] |
| python3 stdlib (`json`, `tempfile`, `os.replace`, `time`) | 3.12 | Hook script + atomic state writes | Zero new deps; the hook script must be dependency-free (`jq` not guaranteed) |
| `tomllib` (stdlib) | 3.11+ | Read optional `~/.config/arduis/arduis.toml` (auto-suspend opt-in) | Read-only is enough, consistent with existing decisions |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Vte.Terminal `bell` signal | ≤0.76 (ancient API) | Secondary attention hint | Degraded mode only (user declined hook install) [VERIFIED: VTE gtk4 docs list the signal; predates 0.76] |
| Vte.Terminal `contents-changed` | ≤0.76 | Activity timestamps for degraded-mode idle detection | Degraded mode only |
| GSound via gir (`GSound` 1.0) | system, OPTIONAL | Freedesktop event sound on waiting | Only if importable (`try/except`); **NOT installed on this machine** [VERIFIED: local probe MISSING] — fall back to `Gdk.Display.beep()` or silence |
| `Gtk.Window:is-active` property | GTK4 | "Window unfocused" gate for notifications | Read `self.props.is_active` at transition time |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| User-level hook merge | `claude --settings <file>` fed in `AGENT_FEED` | Flag verified to exist, but breaks when the user Ctrl+C's and relaunches `claude` manually (Phase 5 agent-swap explicitly enables this); hook-merge semantics for `--settings` not explicitly documented. Rejected as primary; viable emergency fallback |
| User-level hook merge | `.claude/settings.local.json` written into the TASK ROOT | `symlink_plan` symlinks every non-repo root entry — incl. the project's real `.claude/` — into the task dir, so writing there pollutes the user's project [VERIFIED: src/arduis/task_layout.py:50-67]; project-level hooks also require the workspace-trust dialog, and the hook is lost if the user runs `claude` inside a worktree subdir. Rejected |
| Gio.FileMonitor | Piggyback the existing 2s `_poll_ram` to read state files | Simpler but adds up to 2s dot latency; the poll is still used for IDLE/staleness sweeps. Use BOTH: monitor for instant flips, poll tick for time-based states |
| libnotify | `Gio.Notification` via `Adw.Application` | Portal-friendly and dep-free, but requires an installed `.desktop` matching the app-id — arduis is unpackaged until Phase 9, so notifications would silently vanish during dogfooding. Revisit at Phase 9 |

**Installation (dev machine + packaging deps for Phase 9):**
```bash
# Ubuntu: gir1.2-notify-0.7 (required), gir1.2-gsound-1.0 (optional sound)
# Arch:   libnotify (required), gsound (optional sound)
# This machine: Notify 0.7 already importable; GSound missing (optional path must degrade)
```

## Architecture Patterns

### Recommended Module Structure
```
src/arduis/
├── attention.py        # NEW, GTK-free: AgentStatus enum, event→state map, state-file
│                       #   path/parse, task aggregation, idle/auto-suspend policy,
│                       #   settings-merge builder (pure dict→dict), hook-script content
├── spawn.py            # MODIFIED: build_worktree_spawn grows per-terminal extra env
│                       #   (ARDUIS_STATE_FILE=..., ARDUIS_TERM_ID=...)
├── session.py          # MODIFIED: TerminalRecord += status fields (appended LAST,
│                       #   keeping positional construction working — house rule)
└── window.py           # MODIFIED: status dir init + hook-script install + consent
                        #   dialog + Gio.FileMonitor wiring + dot/badge updates +
                        #   libnotify + auto-suspend tick + state-file cleanup on
                        #   hibernate/teardown
```
All decision logic (which state, how to aggregate, when to suspend, how to merge settings JSON) lives in GTK-free `attention.py` → fully unit-testable, consistent with the established layout.py/caps.py pattern.

### Pattern 1: The 5-state model and the event→state map
**What:** `running / waiting / ready / idle / ended` per agent terminal; `idle` is **computed by arduis** (ready + N min), never written by a hook.

| Hook event | Payload discriminator | → state | Rationale |
|---|---|---|---|
| `SessionStart` | — | `ready` | claude is at its input prompt awaiting the first message |
| `UserPromptSubmit` | — | `running` | user sent a prompt; Claude is working |
| `Notification` | `notification_type == "permission_prompt"` or `"elicitation_dialog"` | `waiting` | the real approval prompt — THE orange dot |
| `Notification` | `notification_type == "idle_prompt"` | `ready` **only if current file state is `running`** | self-heals a missed Esc-interrupt; must NOT downgrade `waiting` (see Pitfall 2) |
| `PostToolUse` (matcher `*`) | — | `running` | clears `waiting` after the user approves (see Pitfall 3) |
| `PostToolUseFailure` (matcher `*`) | — | `running` | tool denied-with-feedback → Claude keeps going |
| `Stop` | — | `ready` | response finished; awaiting next prompt |
| `SessionEnd` | — | `ended` | claude exited; pane is a plain shell again |
| `SubagentStop` | — | (not subscribed) | main-agent `Stop` is the truth; subagent permission prompts still surface as top-level `Notification` |

All payload fields verified current: common fields `session_id`, `transcript_path`, `cwd`, `hook_event_name`; `Notification` adds `message` + `notification_type`; `Stop` adds `stop_reason` + `stop_hook_active` [VERIFIED: code.claude.com/docs/en/hooks].

**Task aggregation (03.2 model):** sidebar rows are TASKS. Precedence: any terminal `waiting` → task waiting; else any `running` → running; else any `ready` → ready; else idle/ended. Shell terminals (`kind == "shell"`) never have a state file and are excluded from aggregation (Pitfall 8). Iterate via the existing `_all_task_terminals` accessor (the 03.2 SUMMARY explicitly names it as the Phase-4 seam).

### Pattern 2: Env-guarded no-op hook script (the injection seam)
**What:** ONE stdlib-only python3 script at a stable path (`~/.local/share/arduis/hooks/arduis_status_hook.py`, content written/refreshed by arduis at startup — stable across repo moves and packaging). First line of logic:

```python
state_file = os.environ.get("ARDUIS_STATE_FILE")
if not state_file:
    sys.exit(0)   # not inside arduis → guaranteed no-op for the user's tmux claudes
```

**Why this wins:** hooks inherit the parent process environment [CITED: code.claude.com/docs/en/hooks env table — "All parent environment variables: inherited"]. arduis injects `ARDUIS_STATE_FILE` per terminal in the VTE spawn `envv` → `zsh` → `claude` → hook. Consequences:
- the user's own claude sessions outside arduis: hook exits in ~30ms doing nothing;
- `Ctrl+C` + manual `claude` relaunch inside an arduis pane: still tracked (env lives on the shell);
- user `cd`s into a worktree subdir and runs `claude` there: still tracked (mapping is by env, not cwd);
- Phase 5 agent-swap (agent = arbitrary command): any future claude invocation keeps working.

**VTE envv is additive, not a replacement:** the current spawn passes only `["TERM=xterm-256color"]` yet the children see `HOME`/`DISPLAY`/etc. (Phase 1 acceptance proved `.zshrc` loads) — VTE's `spawn_async` docs phrase `envv` as variables "added to the environment" [VERIFIED: empirical Phase-1 behavior + VTE docs]. Extend `build_worktree_spawn(runner, extra_env: list[str])` and keep the list-literal threat posture (T-01-01).

### Pattern 3: Additive consent-gated merge into `~/.claude/settings.json`
**What:** hooks from all scopes merge — "Hooks from all enabled sources are combined; multiple hooks for the same event/matcher all execute; identical handlers are deduplicated" [VERIFIED: code.claude.com/docs/en/hooks]. So arduis appends its own matcher groups; the user's existing GSD/notify-send hooks are untouched and keep firing.

Merge algorithm (pure function in `attention.py`, unit-tested):
1. Load `~/.claude/settings.json` (it is plain JSON — verified by reading this user's real file).
2. For each of the 7 events: if no existing hook entry whose `command` contains the arduis script path, append `{"hooks":[{"type":"command","command":"/usr/bin/env python3 /home/<u>/.local/share/arduis/hooks/arduis_status_hook.py","timeout":5}]}` (absolute expanded path — no `~`, see Pitfall 9; `matcher: "*"` for the tool events).
3. Write atomically (tmp + `os.replace`) after copying a backup `settings.json.arduis-backup`.
4. Idempotent: presence check by script path makes re-runs no-ops.

Claude Code's settings file watcher reloads hooks live — even already-running claude sessions pick the new hooks up [VERIFIED: hooks doc, "Direct edits to settings files are picked up automatically"]. **User-level hooks are exempt from the workspace-trust dialog** (project hooks are not) [CITED: code.claude.com/docs/en/settings].

Gate the write behind a first-run consent dialog (pt-BR, e.g. "arduis instala um hook do Claude Code para detectar quando um agente espera você. Fora do arduis o hook não faz nada."). Decline → degraded bell mode (Pattern 6) + a persistent "status limitado" hint.

### Pattern 4: Atomic per-terminal state files in XDG_RUNTIME_DIR
**What:** arduis composes the FULL path itself and hands it to the hook via env — the hook never derives names, so branch-name sanitization (slashes in `task_id`) lives in tested Python, not shell.

- Dir: `$XDG_RUNTIME_DIR/arduis/status/` (verified `/run/user/1000`, mode 0700, tmpfs — auto-cleaned at logout). Fallback when unset: `~/.cache/arduis/status/`.
- Name: `<sanitize(term_id)>.json` (e.g. `feat-x:t0.json`, `/`→`-`); arduis keeps `{path → (task_id, term_id)}` in memory — no reverse mapping ever needed.
- Write (in the hook): `tempfile.mkstemp(dir=same_dir)` → `json.dump` → `os.replace` (atomic on same fs). Readers never see partial JSON.
- Content: `{"state": "...", "ts": <epoch>, "event": "...", "session_id": "...", "cwd": "...", "message": "..."}` — `message` feeds the notification body.
- Lifecycle: arduis wipes the whole status dir at startup (stale from a previous arduis run) and deletes a task's files on hibernate/teardown (Pitfall 5).
- Concurrency: one claude per PTY foreground at a time; distinct terminals → distinct files → no contention. Last-writer-wins with `ts` recorded for staleness checks.

### Pattern 5: Watching + time-based states on the main loop
```python
self._status_monitor = Gio.File.new_for_path(status_dir).monitor_directory(
    Gio.FileMonitorFlags.NONE, None)
self._status_monitor.connect("changed", self._on_status_file_event)
```
- React to `CREATED`/`CHANGED`/`CHANGES_DONE_HINT`/`RENAMED` by re-reading the touched file (cheap; debouncing is unnecessary at this event rate — atomic rename yields ~2 events per write). inotify works on tmpfs.
- Time-based states ride the existing 2s `_poll_ram` tick (or a parallel 30s tick): compute IDLE (`ready` && `now-ts > threshold`), reconcile staleness (file says `running` but the terminal's pgid is dead → `ended` — catches SIGKILL'd claudes that never fired `SessionEnd`), and evaluate auto-suspend.
- UI updates: sidebar dot per task (extend `_make_row`'s existing dot + `_DOT_*` CSS classes), pane-header dot per terminal (extend `_make_leaf` badge). Suggested Dracula mapping: running `#50fa7b` (green, current active), waiting `#ffb86c` (orange), ready `#8be9fd` (cyan), idle/ended `#6272a4` (grey, current hibernated tone).

### Pattern 6: Degraded mode (hooks declined) — bell + activity timeout
- `terminal.connect("bell", ...)` → attention hint → mark the terminal `waiting` (coarse; any BEL triggers it). The user can additionally run `claude config set --global preferredNotifChannel terminal_bell` to make claude itself ring BEL on notifications [ASSUMED — flag/channel name not re-verified this session; degraded mode works without it, just coarser].
- `contents-changed` → bump an activity timestamp → `running` while recent, `idle` after timeout. No `ready` state in degraded mode.
- OSC 133 / termprops / `shell-precmd`/`shell-preexec` are **0.78+** and unavailable at the 0.76 floor [VERIFIED: VTE 0.78 release notes/termprop migration; Fedora carried these as downstream patches pre-0.78] — do not plan around them; do not use them conditionally on Arch (one codebase, 0.76 floor).

### Pattern 7: RAM-04 auto-suspend riding the existing hibernate machinery
- Trigger: task aggregate `ready`/`ended` continuously for `auto_suspend_minutes` (config; **default OFF**). NEVER from `running` or `waiting` — a 30-min tool call must not be killed (Pitfall 6).
- Action: the existing `_on_hibernate` path verbatim (SIGHUP→SIGKILL groups, keep dirs, clear pid/pgid) + delete the task's state files + a libnotify "task X suspensa por inatividade".
- Resume: feed `b"claude --continue\n"` instead of plain `AGENT_FEED` for auto-suspended tasks — `-c/--continue` resumes the most recent conversation in the cwd [VERIFIED: present in `claude --help` 2.1.175], so suspension stops costing the conversation. Keep manual hibernate/resume behavior unchanged (plain `claude`) unless the orchestrator opts in to `--continue` everywhere (Open Question 4).

### Anti-Patterns to Avoid
- **Scraping the VTE buffer for status** — explicitly v2/STATUS-04; the hooks make it unnecessary for claude.
- **A watcher thread or asyncio loop** — `Gio.FileMonitor` + GLib timeouts only (CLAUDE.md).
- **Marking hooks `async: true`** — tempting for latency, but async completion can land a stale `running` write AFTER the `Stop` write → permanently wrong dot. Keep hooks synchronous with `timeout: 5`; they're sub-50ms and the user already runs heavier synchronous node hooks per tool call.
- **Writing into `<task_dir>/.claude/`** — it may be a symlink into the user's real project (Pitfall 4).
- **Rewriting/normalizing the user's `~/.claude/settings.json`** — append-only, backup first, dedupe by script path; never touch existing keys.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Detecting "claude waits for approval" | PTY output parser / regex on the TUI | `Notification` hook + `notification_type` | TUI repaints constantly; the event is authoritative and repaint-immune (success criterion 3 by construction) |
| File-change detection | Custom inotify wrapper or poll loop | `Gio.FileMonitor` | Main-loop native, battle-tested, ~10 lines |
| Desktop notifications | Raw D-Bus `org.freedesktop.Notifications` calls | libnotify gir (`Notify 0.7`) | Handles server caps/fallbacks; verified present |
| Atomic file writes | flock/locking schemes | `mkstemp` + `os.replace` in the same dir | POSIX rename atomicity; readers never see partial JSON |
| Settings JSON edit | sed/regex on settings.json | `json.load` → pure merge fn → atomic write | The user's file is dense and load-bearing; structural merge is testable |
| Hook JSON parsing in shell | `jq` pipelines (not a declared dep) | stdlib python3 script | python3 is already a hard dependency of the app |

**Key insight:** every hard sub-problem here (event detection, watching, notification, atomicity) has a system-blessed primitive; Phase 4's real work is the *glue policy* (state machine, aggregation, consent UX), which is exactly what belongs in tested GTK-free code.

## Common Pitfalls

### Pitfall 1: Treating every `Notification` as "waiting"
**What goes wrong:** `idle_prompt` fires after ~60s of claude sitting at its input prompt — mapping it to `waiting` paints false oranges on every forgotten-but-finished agent.
**How to avoid:** branch on `notification_type`; only `permission_prompt`/`elicitation_dialog` → `waiting`.
**Warning signs:** dots flipping orange exactly 60s after a response completes.

### Pitfall 2: `idle_prompt` downgrading a real `waiting`
**What goes wrong:** if a permission dialog is pending long enough, an `idle_prompt` may also fire [ASSUMED — co-occurrence not documented]; naive mapping to `ready` would clear a true orange (missed approval = the cardinal sin of this phase).
**How to avoid:** in the hook script, `idle_prompt` upgrades **only** `running → ready` (read the existing state file first); it never touches `waiting`.

### Pitfall 3: `waiting` never clearing after the user approves
**What goes wrong:** with only `Notification`+`Stop` hooks, approving a permission resumes work but no event fires until `Stop` — the dot stays orange through minutes of work (false orange, criterion 3 violated in the other direction).
**How to avoid:** subscribe `PostToolUse` (matcher `*`) and `PostToolUseFailure` → `running`. This is why the event set is 7, not 2.

### Pitfall 4: Writing settings into the task folder
**What goes wrong:** `symlink_plan` symlinks every non-repo root entry into the task dir — if the project root has `.claude/`, `<task_dir>/.claude` IS the user's project `.claude` [VERIFIED: task_layout.py:60-67]. Writing `settings.local.json` "into the task" mutates the user's real project.
**How to avoid:** user-level injection (Pattern 3). If a task-local file is ever needed, check `os.path.islink` first — but don't go there in v1.

### Pitfall 5: Stale state files lying about dead claudes
**What goes wrong:** hibernate SIGKILLs the group → no `SessionEnd` hook → file forever says `running`; same after an arduis crash. Auto-suspend then never triggers; dots lie.
**How to avoid:** (a) wipe the status dir at arduis startup; (b) delete a task's files inside the hibernate/teardown path; (c) the periodic tick reconciles `running`-with-dead-pgid → `ended` (pgid liveness is already polled for RAM).

### Pitfall 6: Idle detection keyed off "no events" instead of "ready + time"
**What goes wrong:** a long `docker build` or 10-minute Bash tool call produces no hook events; an absence-of-events idle timer would auto-suspend (SIGKILL!) a working agent.
**How to avoid:** IDLE derives exclusively from `ready`/`ended` + threshold. `running`/`waiting` are exempt from auto-suspend no matter how old.

### Pitfall 7: Esc-interrupt leaving a phantom `running`
**What goes wrong:** `Stop`'s documented `stop_reason` values (`end_turn|max_tokens|tool_use|stop_sequence`) suggest a user Esc-interrupt may not fire `Stop` [ASSUMED]; the dot would stay green while claude sits at its prompt.
**How to avoid:** the `idle_prompt → ready` (only-from-running) rule self-heals this within ~60s; the staleness sweep is the backstop. Verify interrupt behavior live during UAT and adjust.

### Pitfall 8: Shell terminals polluting aggregation
**What goes wrong:** `t1` (plain zsh) never writes a state file; treating "no file" as `idle` would drag every task to idle and could auto-suspend a task whose agent is mid-run if aggregation is buggy.
**How to avoid:** aggregate ONLY over `kind == "agent"` records (and any terminal that has ever produced a state file); "no file ever" = no opinion.

### Pitfall 9: `~` and `$VARS` inside hook command strings
**What goes wrong:** the hook `command` runs through a shell, but relying on tilde/var expansion is fragile across shells and the documented exec-form (`args` present = no shell).
**How to avoid:** write the fully expanded absolute script path when generating the settings entry; use `/usr/bin/env python3` as the interpreter (works under pyenv/nvm-style shims since the script is stdlib-only).

### Pitfall 10: Double notifications on this user's machine
**What goes wrong:** the user's own `Notification` hook already fires `notify-send` for every claude (verified in their settings). arduis notifying on `waiting` will sometimes double up.
**How to avoid:** accept it (their config, merge semantics are by design); differentiate arduis notifications (app-name "arduis", body = task/branch name) and only notify when the window is unfocused. Mention in release notes that the personal hook is now redundant inside arduis.

### Pitfall 11: First-run trust dialog is invisible to hooks
**What goes wrong:** the very first `claude` in a fresh task folder shows the workspace-trust prompt BEFORE `SessionStart` fires — that initial "claude is asking you something" moment produces no hook event and no orange dot.
**How to avoid:** accept as a known gap in v1 (it happens once per task, seconds after the user deliberately created the task and is looking at it). The bell secondary signal may catch it later; do not contort the design for it.

## Code Examples

### The hook script (stdlib-only, env-guarded, atomic)
```python
#!/usr/bin/env python3
# Source: payload fields per code.claude.com/docs/en/hooks (verified 2026-06-12)
import json, os, sys, tempfile, time

state_file = os.environ.get("ARDUIS_STATE_FILE")
if not state_file:
    sys.exit(0)                     # outside arduis: guaranteed no-op

try:
    payload = json.load(sys.stdin)
except Exception:
    payload = {}

event = payload.get("hook_event_name", "")
SIMPLE = {"SessionStart": "ready", "UserPromptSubmit": "running",
          "PostToolUse": "running", "PostToolUseFailure": "running",
          "Stop": "ready", "SessionEnd": "ended"}
state = SIMPLE.get(event)
if event == "Notification":
    ntype = payload.get("notification_type", "")
    if ntype in ("permission_prompt", "elicitation_dialog"):
        state = "waiting"
    elif ntype == "idle_prompt":
        try:                        # Pitfall 2: only upgrade running -> ready
            with open(state_file) as f:
                if json.load(f).get("state") == "running":
                    state = "ready"
        except Exception:
            pass
if state is None:
    sys.exit(0)

doc = {"state": state, "ts": time.time(), "event": event,
       "session_id": payload.get("session_id"),
       "cwd": payload.get("cwd"), "message": payload.get("message", "")}
d = os.path.dirname(state_file)
os.makedirs(d, exist_ok=True)
fd, tmp = tempfile.mkstemp(dir=d, prefix=".arduis-")
with os.fdopen(fd, "w") as f:
    json.dump(doc, f)
os.replace(tmp, state_file)        # atomic — readers never see partial JSON
sys.exit(0)                        # NEVER block claude (exit 2 would)
```

### Settings entry arduis appends per event (Pattern 3)
```json
{
  "matcher": "*",
  "hooks": [
    { "type": "command",
      "command": "/usr/bin/env python3 /home/USER/.local/share/arduis/hooks/arduis_status_hook.py",
      "timeout": 5 }
  ]
}
```
(`matcher` only on `PreToolUse`-family events; `Notification`/`Stop`/`SessionStart`/`SessionEnd`/`UserPromptSubmit` groups omit it. Synchronous on purpose — see Anti-Patterns.)

### Spawn env injection (extends the existing seam)
```python
# spawn.py — keeps the list-literal/no-shell-string posture (T-01-01)
def build_worktree_spawn(runner, extra_env: list[str] | None = None):
    envv = TERM_ENV + (extra_env or [])
    return runner.wrap_argv(SHELL_ARGV), runner.wrap_env(envv)

# window.py — per agent terminal, before spawn_async:
extra = [f"ARDUIS_STATE_FILE={attention.state_file_path(status_dir, term_id)}",
         f"ARDUIS_TERM_ID={term_id}"]
# VTE envv is ADDED to the inherited environment (Phase-1 empirically proven:
# children see HOME/DISPLAY with only TERM passed) — not a replacement.
```

### Watch + notify (GLib main loop, no threads)
```python
# Source: GNOME Gio.FileMonitor docs; Notify gir verified importable locally
gi.require_version("Notify", "0.7")
from gi.repository import Notify
Notify.init("arduis")

mon = Gio.File.new_for_path(status_dir).monitor_directory(Gio.FileMonitorFlags.NONE, None)
mon.connect("changed", self._on_status_event)

def _on_status_event(self, _m, gfile, _other, event_type):
    path = gfile.get_path()
    rec = self._record_by_state_file.get(path)
    if rec is None:
        return
    new = attention.read_state(path)          # GTK-free parse, swallows partial/missing
    old = rec.status
    rec.status, rec.status_ts = new.state, new.ts
    self._refresh_status_ui(rec)              # sidebar dot (task aggregate) + pane badge
    if new.state == "waiting" and old != "waiting" and not self.props.is_active:
        n = Notify.Notification.new(
            f"{task.branch} aguarda você", new.message or "Aprovação pendente",
            "dialog-information")
        n.show()                               # + optional GSound/beep if enabled
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hooks limited to ~9 events, `Notification` payload = message only | 30+ events; `Notification` carries `notification_type` (`permission_prompt`/`idle_prompt`/`elicitation_dialog`/...); `Stop` carries `stop_reason` | Claude Code 2.x (current: 2.1.175) | Approval-vs-idle disambiguation is now first-class — the core risk of this phase evaporated |
| Hooks snapshot fixed at session start | Settings file watcher hot-reloads hook changes mid-session | Claude Code 2.x | Installing arduis hooks benefits already-running claudes immediately |
| Hook timeout default 60s | Default 600s (so set explicit `timeout: 5`) | Claude Code 2.x | Misbehaving hook would stall claude far longer — always pin timeouts |
| VTE: title/cwd getter functions; no shell-integration API | termprops + `shell-precmd`/`shell-preexec` signals | VTE 0.78 | All 0.78+ → unusable at the 0.76 floor; bell + contents-changed are the only in-floor secondary signals |
| `claude` docs at docs.claude.com/.../claude-code | Moved to code.claude.com/docs | 2026 | Update any doc links in plans |

**Deprecated/outdated:** planning around OSC 133 visibility inside VTE 0.76 (the ROADMAP's "OSC 133 secondary" wording predates this verification — at the floor it is bell/contents-changed only); `Vte.Terminal.get_window_title`-era APIs (deprecated 0.78, irrelevant here).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `idle_prompt` may fire while a permission dialog is pending | Pitfall 2 | None if wrong (the guard is conservative either way) |
| A2 | Esc-interrupt does not fire `Stop` | Pitfall 7 | Phantom `running` for ≤60s until idle_prompt self-heal — verify live in UAT |
| A3 | `SessionEnd` does not fire on SIGKILL (hibernate) | Pitfall 5 | Stale files — already mitigated by arduis-side cleanup regardless |
| A4 | `preferredNotifChannel terminal_bell` still exists for boosting degraded mode | Pattern 6 | Degraded mode stays coarser; primary path unaffected |
| A5 | `--settings <file-or-json>` hooks merge additively with user hooks | Alternatives | Moot (not the chosen path); only matters if the fallback channel is ever needed |
| A6 | Notification body `message` field is human-readable enough for the desktop notification | Code Examples | Cosmetic — fall back to a fixed pt-BR string |

## Open Questions

*(User is AFK — each has a recommended default for the orchestrator.)*

1. **Hook installation consent UX**
   - What we know: writing to `~/.claude/settings.json` is safe (additive merge, backup, idempotent, env-guarded no-op) but it IS the user's file; this user's file is heavily customized.
   - Recommendation (default): first-launch `Adw.AlertDialog` (pt-BR) with "Instalar" / "Agora não"; decline → degraded bell mode + persistent subtle hint. Never silently write.

2. **Notify on `ready` (response finished) as well as `waiting`?**
   - What we know: STATUS-03 only requires waiting; the user's own global hook already notifies on claude notifications.
   - Recommendation (default): notify on `waiting` only in v1; make `ready` notification a config flag default-off.

3. **Auto-suspend policy values**
   - What we know: RAM-04 says "can be auto-suspended"; killing claude loses nothing if resume uses `--continue`; no app-level config file exists yet.
   - Recommendation (default): opt-in via new `~/.config/arduis/arduis.toml` (`[attention] auto_suspend_minutes = 30`, absent/0 = off, read with stdlib `tomllib`). Default OFF.

4. **Resume feed: `claude --continue` for all resumes or only auto-suspended ones?**
   - What we know: `-c/--continue` (verified flag) resumes the most recent conversation in the cwd; current manual resume feeds plain `claude` (fresh conversation).
   - Recommendation (default): `--continue` for auto-suspend resume (mandatory for RAM-04 to be acceptable); keep manual resume as plain `claude` to avoid silently changing Phase-2 semantics — revisit in Phase 5 (agent = configurable command).

5. **Optional sound implementation given GSound is absent on the dev machine**
   - What we know: GSound gir not installed; `Gdk.Display.beep()` is dep-free but often muted under GNOME/Wayland.
   - Recommendation (default): config flag default-off; when on, try GSound (`try/except` import, play `"message-new-instant"`), else `Gdk.Display.beep()`. List `gir1.2-gsound-1.0`/`gsound` as optional package deps for Phase 9.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Claude Code CLI | hooks (STATUS-01) | ✓ | 2.1.175 | — |
| `claude --continue` / `--resume` / `--settings` flags | RAM-04 resume; alt injection | ✓ | verified in `--help` | — |
| `~/.claude/settings.json` (plain JSON, hooks-rich) | merge target | ✓ | inspected read-only | — |
| gir `Notify` 0.7 (libnotify) | STATUS-03 | ✓ | probe OK | — |
| gir `GSound` 1.0 | optional sound | ✗ | — | `Gdk.Display.beep()` or silence (default off) |
| `$XDG_RUNTIME_DIR` | state files | ✓ | `/run/user/1000` 0700 tmpfs | `~/.cache/arduis/status/` |
| python3 (hook script, stdlib only) | hook script | ✓ | 3.12 | — |
| VTE `bell` + `contents-changed` signals | degraded mode | ✓ | within 0.76 floor | — |
| VTE termprops / OSC 133 signals | (not used) | ✗ at floor | 0.78+ | bell/contents-changed |

**Missing dependencies with no fallback:** none.
**Missing dependencies with fallback:** GSound (optional sound → beep/silence).

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing; runs via /tmp venv `--system-site-packages` per dev-env convention) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths=tests, pythonpath=src) |
| Quick run command | `pytest tests/test_attention.py -x -q` |
| Full suite command | `pytest` (current baseline: 88 passing) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STATUS-01 | event→state map, incl. notification_type branches + idle_prompt guard | unit | `pytest tests/test_attention.py -x` | ❌ Wave 0 |
| STATUS-01 | hook script end-to-end: stdin JSON + env → atomic state file; no-op without env; never nonzero exit | integration (subprocess) | `pytest tests/test_hook_script.py -x` | ❌ Wave 0 |
| STATUS-01 | settings merge: additive, idempotent, preserves user hooks (fixture = anonymized copy of a real hooks-rich settings.json) | unit | `pytest tests/test_attention.py -k merge -x` | ❌ Wave 0 |
| STATUS-01 | spawn env injection (`ARDUIS_STATE_FILE` in envv, argv unchanged) | unit | `pytest tests/test_spawn_argv.py -x` | ✅ extend |
| STATUS-02 | task aggregation precedence; shell terminals excluded; TerminalRecord status fields | unit | `pytest tests/test_attention.py tests/test_session.py -x` | ✅/❌ Wave 0 |
| STATUS-02 | dots render in sidebar + pane header; flip live | manual-only (GTK) — gtk4-broadwayd headless harness + live UAT | — | checklist |
| STATUS-03 | notification fires only on →waiting transition and only when unfocused (policy fn unit-testable; display manual) | unit + manual | `pytest tests/test_attention.py -k notify_policy -x` | ❌ Wave 0 |
| RAM-04 | should_autosuspend: ready+threshold yes; running/waiting never; config parse | unit | `pytest tests/test_attention.py -k suspend -x` | ❌ Wave 0 |
| RAM-04 | suspended task resume feeds `claude --continue` | unit (feed constant/builder) + manual | `pytest tests/test_session.py -k continue -x` | ❌ Wave 0 |
| crit. 3 | real approval → orange; TUI redraw → no false orange; approve → clears | manual-only (live claude UAT — the phase gate) | — | checklist |

### Sampling Rate
- **Per task commit:** `pytest tests/test_attention.py tests/test_hook_script.py -x -q`
- **Per wave merge:** `pytest` (full suite, must stay ≥ baseline)
- **Phase gate:** full suite green + live UAT checklist (real claude in an arduis task: approval prompt → orange ≤1s; approve → green; finish → ready; 60s → no false orange; unfocused notification arrives; user's own hooks still fire)

### Wave 0 Gaps
- [ ] `tests/test_attention.py` — covers STATUS-01/02, RAM-04 policy (state map, aggregation, merge, suspend, notify policy)
- [ ] `tests/test_hook_script.py` — subprocess round-trip of the generated hook script (STATUS-01)
- [ ] extend `tests/test_session.py` — TerminalRecord status fields appended last (positional-construction invariant)
- [ ] extend `tests/test_spawn_argv.py` — extra_env injection (STATUS-01)

## Sources

### Primary (HIGH confidence)
- https://code.claude.com/docs/en/hooks — full event list, payloads (`notification_type`, `stop_reason`), env vars (`CLAUDE_PROJECT_DIR`, parent env inheritance), merge behavior across scopes, hot-reload, timeouts, exit-code semantics (fetched 2026-06-12)
- https://code.claude.com/docs/en/settings — scope precedence, `--settings` flag rank, workspace-trust applies to project (not user) hooks (fetched 2026-06-12)
- Local verification on the dev machine (2026-06-12): `claude --version` = 2.1.175; `claude --help` confirms `--continue`/`--resume`/`--settings <file-or-json>`; `~/.claude/settings.json` inspected read-only (hooks-rich, plain JSON); `settings.local.json` has permissions only (no hooks); `gi` probes: Notify 0.7 ✓, GSound ✗; `$XDG_RUNTIME_DIR=/run/user/1000` 0700
- Codebase: `src/arduis/window.py` (`_all_task_terminals`, `_poll_ram`, `_make_row`/`_make_leaf`, hibernate/teardown), `src/arduis/session.py` (TerminalRecord/Task, AGENT_FEED), `src/arduis/spawn.py` (TERM_ENV seam), `src/arduis/task_layout.py` (`symlink_plan` symlinks root `.claude/`)
- https://gnome.pages.gitlab.gnome.org/vte/gtk4/signal.Terminal.bell.html — bell signal exists in Vte 3.91 (pre-0.76 API)

### Secondary (MEDIUM confidence)
- VTE 0.78 termprop migration / `shell-precmd`/`shell-preexec` landing in 0.78 (web search cross-referencing release notes + Fedora downstream patch history) — grounds "no OSC 133 at the 0.76 floor"
- Phase-1 empirical evidence that VTE `spawn_async` envv is additive (children see full env with only TERM passed)

### Tertiary (LOW confidence)
- `preferredNotifChannel terminal_bell` for degraded mode (training knowledge, not re-verified — flagged A4)
- Esc-interrupt/Stop interaction (A2) — verify in UAT

## Metadata

**Confidence breakdown:**
- Hooks mechanics & payloads: HIGH — current official docs + the exact installed version probed
- Injection strategy (user-level env-guarded merge): HIGH — merge semantics documented, user's real file inspected, disqualifiers for alternatives verified in this codebase
- State machine edge cases (interrupt, idle_prompt co-occurrence): MEDIUM — guards designed conservative; UAT items listed
- VTE floor (no OSC 133, bell available): HIGH
- Notification/sound stack: HIGH for libnotify (probed), MEDIUM for sound (optional path)

**Research date:** 2026-06-12
**Valid until:** ~2026-07-12 (Claude Code hook surface moves fast; re-verify event payloads if the phase slips a month)
