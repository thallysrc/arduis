# Pitfalls Research

**Domain:** Python/GTK4/VTE Flatpak desktop app orchestrating parallel AI agents in git worktrees + opt-in isolated docker-compose stacks, driving the host via `flatpak-spawn --host`
**Researched:** 2026-06-08
**Confidence:** HIGH for Flatpak/VTE/git/docker mechanics (verified against upstream issues, manpages, official docs); MEDIUM for Claude Code detection behavior (verified against upstream feature issues, evolving fast); MEDIUM for RAM thresholds (synthesized, not benchmarked).

> Scope note: these are stack-specific failure modes for THIS architecture, mapped to the Degraus in `docs/ROADMAP.md`. Generic "write tests" advice is omitted.

---

## Critical Pitfalls

### Pitfall 1: `flatpak-spawn --host bash -i` / `zsh -i` breaks job control and Ctrl+C (the tcsetpgrp trap)

**What goes wrong:**
You spawn an interactive shell on the host through the portal and the shell prints `cannot set terminal process group (-1): Inappropriate ioctl for device`, or job control silently fails. Worse for arduis: **Ctrl+C does not cleanly land where you expect.** The whole product loop ("`Ctrl+C` cai no shell → troca de agente") depends on signal/job-control semantics that the portal disturbs.

**Why it happens:**
`flatpak-session-helper` runs `child_setup` that calls `setsid()` + `setpgid()` and the host command does not own the controlling TTY of the VTE PTY. There are actually **two PTYs in the chain**: the VTE PTY (created in the sandbox) and the host process spawned by the portal. The signal you generate with Ctrl+C in VTE goes to the foreground process group of the *VTE* PTY (i.e. `flatpak-spawn` itself), and propagation to the host-side `claude`/`zsh` is not guaranteed — flatpak-spawn historically did not even forward signals or exit status correctly (see Pitfall 2). Job control (`fg`/`bg`/Ctrl+Z) inside the host shell is the part that breaks outright.

**How to avoid:**
- **Spawn the host process so the VTE PTY *is* its controlling terminal.** Use VTE's own pty: `Vte.Terminal.spawn_async` with `Vte.PtyFlags.DEFAULT` already allocates a PTY and sets it as ctty for the spawned child. The child here is `flatpak-spawn`; you need the *grandchild* (host `zsh`) to inherit that ctty. Verify Ctrl+C actually interrupts a `sleep 100` running under host `claude` early — this is a Degrau-1 acceptance test, not a Degrau-5 one.
- **Prefer launching the agent directly, not via an extra `-i` login shell wrapper**, to reduce the number of process-group hops. If a login shell is needed for the user's zsh config, test job control explicitly.
- Confirm `flatpak-spawn` version in the runtime forwards signals (recent versions do; the GNOME SDK 50 runtime should). If signals do not forward, you may need to translate VTE's "Ctrl+C" into an explicit SIGINT sent to the host PID via the portal rather than relying on PTY-level propagation.
- Keep `flatpak-spawn` as `--watch-bus` so the host child is killed if arduis dies (prevents orphaned `claude`/`zsh`).

**Warning signs:**
- `Inappropriate ioctl for device` in the terminal on first spawn.
- Ctrl+C does nothing, or kills the agent but not the running subprocess, or kills the wrong thing.
- Ctrl+Z / `fg` don't work inside the spawned shell.
- Closing the arduis window leaves `claude`/`node` processes alive on the host.

**Phase to address:** **Degrau 1** (the very first spawn must validate Ctrl+C + ctty + clean teardown — these are the foundation, not polish). Re-verified in **Degrau 5** when "Ctrl+C swaps agent" becomes a feature.

---

### Pitfall 2: Exit detection is wrong — `child-exited` reports success for a failed/killed host process

**What goes wrong:**
VTE's `child-exited` signal gives you the status of `flatpak-spawn`, not of the host `claude`/`zsh`. Historically `flatpak-spawn` mangled the exit status: a host process that returned `1` could surface as `256`, and `(256 & 0xff) == 0` made flatpak-spawn exit **0 (success)**. A host process killed by SIGTERM(15) surfaced as exit 15 with no indication it was a signal. So arduis's "agent finished / agent crashed / agent was killed" state machine reads garbage.

**Why it happens:**
The portal's `SpawnExited` signal carries the raw `waitpid()` status (which encodes exit-vs-signal in different bits), and naive code passes it straight to `exit()` instead of decoding with `WIFEXITED`/`WEXITSTATUS`/`WIFSIGNALED`. This was a real flatpak-xdg-utils bug (PR #10).

**How to avoid:**
- Treat VTE `child-exited` `status` as a `waitpid` status and decode it (`os.waitstatus_to_exitcode` in Python, or the `WIF*` macros' logic) — do **not** compare it to literal exit codes.
- Verify against a recent enough `flatpak-spawn` (the fix is upstream; GNOME SDK 50 should carry it). Add a smoke test: host command `exit 3`, host command `kill -TERM $$`, host command that exits 0 — assert arduis classifies each correctly.
- For the agent state machine, don't rely solely on exit code for "crashed vs finished": correlate with whether the user requested termination.

**Warning signs:**
- Sidebar shows a crashed agent as "pronto/done".
- Exit codes that are always 0 or always multiples of 256.
- Killed agents reported as clean exits.

**Phase to address:** **Degrau 1** (spawn + exit handling) and **Degrau 4** (status state machine consumes this).

---

### Pitfall 3: "Agent is waiting for input" detection by screen-scraping is fundamentally fragile — and there's a robust alternative you must use instead

**What goes wrong:**
The instinct (and Degrau 4's literal wording, "lendo a saída do VTE") is to scrape VTE output for prompt patterns like `>`, `Do you want to proceed?`, or spinner characters, then flip the sidebar dot to orange. This produces:
- **False positives:** Claude Code's TUI redraws constantly (spinners, token counters, animated "Thinking…"), so screen text matches "looks idle" momentarily mid-stream. Any TUI repaint can look like a prompt. Code blocks in the agent's output containing `>` or `?` trigger matches.
- **False negatives:** the prompt format changes between Claude Code releases, uses ANSI/cursor-positioning instead of literal newlines, or sits below the visible region. Reflow and alternate-screen mode (TUIs use the alt screen) mean the "last line" you read may not be where the prompt is.
- **Locale/ANSI breakage:** parsing requires stripping ANSI, handling cursor moves, and the strings are not stable contract — they are a moving target across every `claude` update.

This is the single highest-risk feature in the product because "always knowing which agent is waiting for you" is the **core value proposition** (PROJECT.md).

**Why it happens:**
TUI output is a rendering stream, not a structured status API. Screen content is a side effect, and Claude Code in particular owns the alternate screen and repaints aggressively. There is no documented stable text contract.

**How to avoid (concrete mitigations, in priority order):**
1. **Use Claude Code's hooks as the primary signal — not the screen.** Claude Code fires a `Notification` hook when it is waiting for input/approval and a `Stop` hook when a turn finishes. Configure these hooks (in the worktree's settings or a managed config arduis injects) to write a tiny status record (e.g. append a line / touch a file / emit on a fd/socket arduis watches per worktree). This is structured, language-independent, and survives TUI redesigns. **This is the recommended architecture for Degrau 4.** Caveat verified in upstream issues: the generic `Notification`/`idle_prompt` hook can over-fire (fires for non-approval notifications too), so filter on the hook event type, and treat `Stop` as "done/idle" vs `Notification` as "needs you".
2. **Fallback signal: terminal bell (BEL / `\a`).** Claude Code is moving toward ringing the bell when waiting for approval. VTE emits the `bell` signal — subscribe to it (`terminal.connect("bell", ...)`) and treat a bell as a strong "needs attention" hint. This works even when hooks aren't configured, and is trivial. Combine: bell → candidate "waiting"; hook → authoritative.
3. **Coarse activity heuristic, only as a tiebreaker:** "no new output bytes for N seconds AND the foreground host process is still alive" → likely idle/waiting. Use VTE's `contents-changed`/output activity, not pattern matching. This avoids parsing prompt strings entirely.
4. **Make the agent configurable's detection pluggable.** Since "agente = comando configurável" (claude/codex/aider/shell), don't hardcode Claude Code prompt regexes. Each agent type can declare how its waiting-state is detected (hook script, bell, or activity timeout). Default to bell+activity for unknown agents.
5. **Never claim certainty in the UI.** Use a confident state only from hooks/bell; show activity-timeout-derived state as a softer hint.

**Warning signs:**
- The orange dot flickers during long agent responses (false positive).
- The dot never turns orange for a real prompt after a `claude` update (false negative — your regex rotted).
- Detection logic accumulates special-cases per Claude Code version.

**Phase to address:** **Degrau 4.** This pitfall should reshape Degrau 4's scope: change "ler a saída do VTE" to "hook-driven + bell signal, with activity timeout as fallback." Flag Degrau 4 as needing its own deep-dive research spike.

---

### Pitfall 4: Environment / PATH not inherited by host commands → `claude`, `gh`, `docker`, user zsh config missing

**What goes wrong:**
The agent spawns but `claude` / `gh` / `docker` are "command not found", or the user's zsh theme/aliases/`asdf`/`nvm`/`mise`/Volta shims are absent, or `claude` can't find its API key from the environment. The current `main.py` passes `None` for envp ("herda o ambiente") — but what it inherits is the *sandbox* environment plus whatever the portal passes, **not** the user's interactive host environment.

**Why it happens:**
`flatpak-spawn --host` does **not** reliably inherit the environment of `flatpak run`; the host side starts from the session-helper's environment (systemd `--user`/dbus-daemon), with a minimal PATH (`/app/bin:/usr/bin` etc.). Version managers (asdf/mise/nvm) put `claude`/`node` under `~/.local/...` or `~/.asdf/shims`, which won't be on that PATH. The sandbox PATH also wrongly prioritizes system paths over user-writable ones in some setups.

**How to avoid:**
- **Run the agent inside a proper login+interactive host shell** so the user's `~/.zshrc`/`~/.zprofile` set up PATH and version-manager shims: spawn `flatpak-spawn --host zsh -l -c '<agent>'` (or let the user's default login shell resolve the agent), rather than execing the agent binary directly with a guessed path. This is the cleanest fix and matches the tmux-centric user's expectation that "it's just my shell."
- Balance against Pitfall 1: more shell wrappers = more process-group hops. Test job control with the chosen wrapper.
- Do **not** hardcode `/usr/bin/zsh` or assume a PATH; resolve via the host's `$SHELL` where possible.
- For non-interactive needs (setup commands, docker), explicitly source the environment or run through a login shell too, so `docker`, `npm`, etc. resolve identically on Ubuntu and Arch.

**Warning signs:**
- Works in a terminal you launched by hand, "command not found" inside arduis.
- User's prompt/theme/aliases missing in the embedded terminal.
- `claude` runs but behaves as if unconfigured (missing env-based settings).
- Differs between Ubuntu and Arch (different version-manager conventions).

**Phase to address:** **Degrau 1** (spawn the host shell correctly), reconfirmed in **Degrau 6** (setup commands must run in the same resolved environment) and **Degrau 7** (docker must be on PATH).

---

### Pitfall 5: Docker socket access from inside the sandbox is not covered by the current manifest

**What goes wrong:**
Degrau 7 needs `docker compose` to work. The current `finish-args` only has `--talk-name=org.freedesktop.Flatpak` and `--filesystem=home`. Because arduis runs `docker compose` **on the host via flatpak-spawn**, the docker CLI talks to `/run/docker.sock` *on the host* — so socket access is not actually arduis's problem **as long as docker commands always go through `--host`**. The trap is doing it the "in-sandbox" way: bundling a docker client and trying to reach the daemon from inside the sandbox, which then needs `--filesystem=/run/docker.sock` and the user being in the `docker` group — and on the user's setup docker is a **snap**, so the socket path and daemon are non-standard.

**Why it happens:**
Two valid architectures (run docker via `flatpak-spawn --host` vs. run a docker client inside the sandbox) have very different permission needs, and mixing them silently fails. The user's docker-via-snap means `/var/run/docker.sock` may be `/var/snap/docker/...` or require the snap's own socket, and group membership differs Ubuntu (snap docker) vs Arch (native docker).

**How to avoid:**
- **Decide explicitly: all docker/compose calls go through `flatpak-spawn --host docker compose ...`** (consistent with git/gh). Then arduis needs *no* docker-socket permission at all — the host docker CLI handles auth/socket. Keep the manifest minimal (matches the "minimal deps/permissions" value).
- Detect docker availability by running `flatpak-spawn --host docker compose version` at runtime, not by probing a socket path.
- Account for snap docker on Ubuntu: don't assume `/var/run/docker.sock`; rely on the host CLI's own resolution.

**Warning signs:**
- "Cannot connect to the Docker daemon" only inside arduis.
- Works on Arch (native docker), fails on Ubuntu (snap docker), or vice-versa.
- You added `--filesystem=/run/docker.sock` and it still fails (snap socket path).

**Phase to address:** **Degrau 7** (containers). Decide the "always via --host" rule at the start of Degrau 7.

---

### Pitfall 6: docker-compose isolation leaks — port collisions, orphaned containers, volumes that don't actually isolate, and teardown that never runs

**What goes wrong:**
The opt-in isolated stack per worktree (`COMPOSE_PROJECT_NAME` unique + port offset override) develops several leaks:
- **Port collisions:** two worktrees compute the same offset, or the offset lands on an already-used host port, or the user already has the base stack running (offset 0). `docker compose up` then fails or steals a port.
- **Orphaned containers:** `down` run with a different `COMPOSE_PROJECT_NAME` or from a different directory than `up` leaves containers Compose no longer tracks. Compose tracks by project name; if arduis's generated name drifts (e.g. derived from worktree dir name, which changes), the old containers become orphans consuming RAM and ports.
- **Volumes don't isolate the way you assume:** unique `COMPOSE_PROJECT_NAME` gives unique *named* volumes (good — empty isolated DB), but **bind mounts to absolute host paths are shared** across worktrees. A compose file that bind-mounts `./data` is fine (relative to worktree); one that mounts `/var/lib/myapp` is not isolated at all.
- **Teardown never runs on crash:** if arduis crashes or is force-killed, the per-worktree stacks keep running forever. There is no Compose-level "kill when parent dies."
- **compose-from-main when the branch diverged:** the design pulls the compose base from `main`, but the worktree's branch may add a service or change ports; running main's compose against the branch's code/migrations causes subtle "works on trunk, broken here" failures.

**Why it happens:**
Compose's identity model is `(project name, compose file, working dir)`; arduis generates all three and any inconsistency between `up` and `down`/`ps` orphans resources. Port offsets are arithmetic on a shared host port space with no global registry. Nothing ties container lifetime to the GUI process.

**How to avoid:**
- **Make `COMPOSE_PROJECT_NAME` a stable, content-independent ID** (e.g. `arduis-<short-hash-of-worktree-path-or-uuid>`), persisted in arduis state — never derived from a mutable dir name. Use the exact same project name for `up`, `ps`, `down`.
- **Always run `down --remove-orphans --volumes`(for isolated) on teardown**, and a reconciliation pass on startup: enumerate `arduis-*` compose projects, cross-check against known worktrees, and offer to clean orphans. This recovers from crashes.
- **Pick ports by probing, not blind offset:** compute candidate from offset, then check the host port is free (via host `ss`/bind attempt) before writing the override; retry next offset on collision. Surface the actual chosen port in the badge (the design already shows `db :5433`).
- **Persist a port registry** in arduis state so two worktrees never pick the same port, and so badges survive restart.
- **Track stack lifetime against the GUI:** on arduis startup, reconcile; on clean shutdown, optionally hibernate (stop, keep volumes) rather than leak.
- **Be explicit about compose-from-main risk:** document that isolated stacks use trunk's services; if a branch needs new services it must update its own compose. Detect when the branch's `docker-compose.yml` differs from main's and warn.
- For bind mounts, detect absolute-path bind mounts in the compose file and warn that they are not isolated.

**Warning signs:**
- `bind: address already in use` on `up`.
- `docker ps` shows `arduis-*` containers with no corresponding open worktree.
- Two worktrees' badges show the same port.
- RAM climbs across a day of use even after closing worktrees.
- Branch's app crashes connecting to a service that exists on main but not branch.

**Phase to address:** **Degrau 7** (build isolation correctly with stable project IDs, port probing, `--remove-orphans` teardown) and **Degrau 8** (cleanup on "concluir worktree" must guarantee teardown). Startup reconciliation is a Degrau 7 sub-task.

---

### Pitfall 7: RAM blow-up — N agents + N isolated stacks exhausts memory, and the GUI gets blamed

**What goes wrong:**
The user opens 6 worktrees, each auto-running `claude` (Node, ~100–300 MB each) and toggles isolated stacks (0.5–2 GB each). That's potentially 3–15 GB before any real work. The machine swaps, everything (including arduis) becomes sluggish, and the natural-but-wrong reaction is to blame Python/GTK4 and consider a Rust rewrite — which PROJECT.md explicitly rejects because the cost is the agents and containers, not the GUI.

**Why it happens:**
Each worktree spawns a real agent process tree and optionally a full app stack, with no global ceiling. Auto-running the default agent on every new worktree (Degrau 2) multiplies Node processes. Idle worktrees keep agents and containers resident.

**How to avoid:**
- **Treat RAM management as a first-class feature from the start, not a late add** (PROJECT.md/MOTIVATION already mandate this). Implement: configurable max simultaneous agents/containers; **hibernate** (kill agent + `docker compose stop`, keep directory + volumes) and resume; suspend idle worktrees; per-worktree RAM visibility in UI; guaranteed teardown.
- **Default isolated containers to `off`** (already decided) and shared by default — only the explicit opt-in pays the container RAM.
- **Don't auto-spawn the agent on every worktree unconditionally at scale:** consider auto-running the agent only on the focused/active worktree, or a soft cap with a prompt, once N grows. Lazy-start agents on focus is a strong mitigation.
- **Measure, don't guess:** read per-process RSS from host (`flatpak-spawn --host` + `/proc` or `ps`) and per-container stats (`docker stats --no-stream`) to drive the UI numbers and the cap decisions.
- **Bound VTE scrollback** (see Pitfall 8) — N terminals × huge scrollback is its own RAM line item.

**Warning signs:**
- System swap usage climbs with worktree count.
- arduis UI jank correlates with number of open worktrees (it's memory pressure, not GTK).
- OOM killer terminates agents/containers randomly.

**Phase to address:** RAM visibility and hibernate are their own concern but must be designed into **Degrau 3** (multiple worktrees) and become real by **Degrau 7** (containers). Lazy-start-on-focus is a Degrau 2/3 design decision. Do not defer all RAM work to "later."

---

### Pitfall 8: VTE scrollback × many terminals = quiet memory and perf cost; version/build drift in Flatpak

**What goes wrong:**
`main.py` sets `set_scrollback_lines(10000)` per terminal. With N agents producing verbose output (Claude Code logs a lot), each terminal's scrollback grows; across many terminals this is real memory, and reflow on resize/relayout of many VTEs can stutter. Separately, building VTE 0.84.0 in-manifest against GNOME SDK 50 (with pinned `fast_float` v8.2.8 + `simdutf` v7.7.1) is brittle: the VTE subproject expects specific dep versions, and a future VTE bump or SDK bump can break the build or cause ABI/`Vte-3.91` mismatches.

**Why it happens:**
Scrollback is per-terminal and unbounded-feeling at 10k×N; VTE compresses scrollback (LZ4 in recent versions) but it still costs. The hand-pinned C++ deps (`fast_float`, `simdutf`) are a maintenance liability for a solo dev: VTE chooses these versions in its meson subprojects, and drift between your pins and VTE's expectation breaks offline Flatpak builds.

**How to avoid:**
- **Keep scrollback modest and configurable**; consider lowering the default or making it per-agent. Don't set 100k+. VTE docs explicitly warn very large scrollback degrades performance/exhausts resources.
- **Reuse/destroy VTE widgets with worktree lifecycle:** when hibernating a worktree, free its terminal (don't keep N idle VTEs with full scrollback resident).
- **Pin the VTE build reproducibly and document the dep triplet** (VTE 0.84.0 ↔ fast_float v8.2.8 ↔ simdutf v7.7.1). When bumping VTE, read its `subprojects/*.wrap` to get the exact expected dep versions rather than guessing. Treat the manifest's VTE build as a thing that needs a deliberate re-test on every SDK bump.
- Test the Flatpak build offline (flatpak-builder with no network) to catch missing/incompatible pinned deps early — this is what the comments already aim for.
- Watch for `Vte-3.91` typelib/ABI mismatch (the gi.require_version) if SDK and bundled VTE disagree.

**Warning signs:**
- Memory grows with terminal output volume even when idle.
- Resize/relayout stutters with several terminals open.
- Flatpak build breaks after a VTE or SDK version bump with meson subproject errors.
- `Vte` import fails or behaves oddly after a runtime update.

**Phase to address:** **Degrau 1** (build + sane scrollback default), **Degrau 9** (packaging — pin/reproducibility), and revisited whenever the SDK/VTE version changes.

---

### Pitfall 9: git worktree lifecycle hazards — "already checked out", removing a worktree with live processes, shared `.git`, hooks/submodules

**What goes wrong:**
- **"branch already checked out at <path>":** the core loop offers "existing branch", but a branch can be checked out in only one worktree. Picking an already-checked-out branch fails hard.
- **Removing a worktree with a running agent/container:** `git worktree remove` refuses on a dirty tree, and even with `--force` you can `rm`-style delete a directory that still has `claude`/`docker` holding it, leaving git's `.git/worktrees/<name>` metadata stale and processes orphaned.
- **Manual `rm -rf` of a worktree** leaves dangling administrative files; `git worktree prune` is then needed. Editing `.git/worktrees/<name>/HEAD` by hand corrupts state.
- **Submodules & hooks:** worktrees share the common `.git`; submodule init per worktree and hook behavior can surprise (hooks run from the worktree but config/objects are shared).

**Why it happens:**
git worktrees deliberately share one object store and enforce single-checkout per branch; arduis is automating the exact operations (add/remove/reuse-branch) where these constraints bite, and it's layering process + container lifecycle on top of git's.

**How to avoid:**
- **Before `git worktree add`, run `git worktree list --porcelain`** and detect already-checked-out branches; for "existing branch", either focus the existing worktree or refuse with a clear message — never `--force` blindly.
- **Teardown order on "concluir worktree":** (1) kill the agent process, (2) `docker compose down` the stack, (3) verify the dir is clean / commit-or-warn, (4) `git worktree remove`, (5) `git worktree prune` to be safe. Never `rm -rf` first.
- **Always use `git worktree remove`, never filesystem delete**; run `prune` on startup to heal stale metadata.
- Guard removal when the tree is dirty: surface uncommitted changes rather than `--force`-deleting (the user could lose work).
- For submodules, run setup (`.arduis.toml` setup commands) that init submodules per worktree if the repo uses them.

**Warning signs:**
- "already checked out" errors when creating from an existing branch.
- Stale entries in `git worktree list` pointing at deleted dirs.
- "concluir worktree" leaves containers running or the directory locked.
- Lost uncommitted changes after a forced removal.

**Phase to address:** **Degrau 2** (create: handle already-checked-out), **Degrau 8** (review + cleanup: correct teardown order, no force-delete, prune). Startup prune is a small Degrau 2/3 task.

---

### Pitfall 10: Wayland/X11 and Ubuntu-vs-Arch divergence treated as an afterthought

**What goes wrong:**
"Must run on Ubuntu AND Arch, GNOME, Wayland" is non-negotiable, but divergences surface late: different docker (snap on Ubuntu vs native on Arch), different default shells/version managers, GNOME version skew affecting libadwaita/GTK4 behavior, and Wayland-specific input quirks for the tmux-style global keybindings (Wayland restricts global grabs; some key combos behave differently than X11). `fallback-x11` masks Wayland bugs during dev if you happen to run XWayland.

**Why it happens:**
Flatpak's one-build promise covers the *runtime*, not host integrations (docker, shell, version managers) or compositor behavior. Solo devs naturally test on one machine and discover the other distro's quirks at packaging time (Degrau 9), too late.

**How to avoid:**
- **Dogfood on both distros early and regularly** (the method already says dogfood early) — at least smoke-test on the secondary distro by Degrau 3, not Degrau 9.
- **Test under real Wayland**, not XWayland, for keybindings; verify the tmux-style chords (`C-Space`, `C-h/j/k/l`, splits) work as in-app shortcuts (they're app-local, not global grabs — keep them app-scoped to avoid Wayland global-shortcut limitations).
- **Never assume host paths/sockets/shells** (see Pitfalls 4, 5): resolve docker/shell/agent via the host shell at runtime.
- Keep `--socket=wayland` primary; treat `fallback-x11` as fallback only and don't let it hide Wayland issues.

**Warning signs:**
- Keybinding works on X11, not Wayland.
- docker/agent works on Arch, not Ubuntu (or vice-versa).
- libadwaita widgets render/behave differently across GNOME versions.

**Phase to address:** **Degrau 5** (keybindings under Wayland), continuous from **Degrau 3**, hard gate at **Degrau 9** (install on clean Ubuntu + Arch).

---

### Pitfall 11 (solo-maintainer): scope creep into swarm / over-engineering before v1 dogfoods

**What goes wrong:**
The swarm track (Coordinator/Builder/Reviewer + mailbox + MCP) is seductive and the temptation is to build coordination plumbing before the simple parallel loop is even dogfoodable. Or: over-abstracting the agent model, building a plugin system for agents, a theming engine, free-form draggable pane layout, etc., before Degrau 1–4 deliver daily value. Momentum dies; nothing ships.

**Why it happens:**
The interesting problem (multi-agent coordination) is more fun than the boring foundation (one terminal that doesn't break Ctrl+C). Solo devs with rich vision over-design abstractions for a single user.

**How to avoid:**
- **Honor the roadmap's own guardrail:** swarm is explicitly Fase 2 OPCIONAL; v1 is simple parallelism. Don't build swarm primitives (mailbox, MCP, roles) until v1 is dogfooded daily.
- **Ship each Degrau as installable + usable** (the Accelerate/DORA method already mandates this). Resist building configurability/plugins before the hardcoded happy path works (e.g. hardcode `claude` first; make "agente = comando" real only in Degrau 5).
- **Prefer shell-out over integration:** the design already shells out to git/gh/docker — keep it that way; don't write libraries where a subprocess call suffices.
- Treat "constant visible progress" as the success metric: if a Degrau isn't shippable in a small batch, it's too big.

**Warning signs:**
- Working on Coordinator/board logic while Ctrl+C still misbehaves.
- Abstraction layers with one implementation.
- A Degrau that's been "in progress" without an installable result.

**Phase to address:** Process-level, all phases. Hard rule: no swarm work until v1 (Degrau 1–9) is dogfooded.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Hardcode `claude` as the only agent | Fastest path to Degrau 1–4 value | Rework when "agente = comando" lands | Acceptable through Degrau 4; generalize in Degrau 5 |
| Screen-scrape VTE for "waiting" prompt regex | Quick visible demo of the orange dot | Rots on every Claude Code update; false +/- destroy trust in the core feature | **Never as the primary signal** — only as activity-timeout fallback (Pitfall 3) |
| Derive `COMPOSE_PROJECT_NAME` from worktree dir name | No state to persist | Orphaned containers when dirs change/move | Never — use a stable persisted ID (Pitfall 6) |
| `rm -rf` worktree dir on cleanup | Simple | Stale git metadata, orphaned processes, lost work | Never — use `git worktree remove` + prune (Pitfall 9) |
| Blind port offset without probing | Simple arithmetic | Port collisions, failed `up` | Acceptable only with a free-port probe + retry (Pitfall 6) |
| Pass `None` envp / exec agent binary directly | Works on dev machine | Breaks PATH/version-manager/shell config on others & other distro | Replace with login-shell spawn before sharing (Pitfall 4) |
| No teardown-on-crash reconciliation | Less startup code | Container/agent leaks accumulate, RAM creep | Acceptable in earliest prototype only; required by Degrau 7 |
| Auto-spawn agent on every worktree | Matches the "agent in seconds" promise | RAM blow-up at N worktrees | Acceptable at small N; add lazy-start/cap by Degrau 3 |

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `flatpak-spawn --host` (shell) | Exec agent directly / pass `None` env; assume host PATH | Spawn via host login shell so zsh config + version-manager shims resolve (Pitfall 4) |
| `flatpak-spawn --host` (signals) | Trust PTY Ctrl+C to reach host child; trust exit status literally | Ensure VTE PTY is ctty; decode `waitpid` status with `WIF*` logic; `--watch-bus` to kill on death (Pitfalls 1,2) |
| Claude Code state | Parse TUI output for prompts | Use `Notification`/`Stop` hooks + BEL signal; activity timeout as fallback (Pitfall 3) |
| docker / docker compose | Try to reach daemon from inside sandbox; assume `/run/docker.sock` | Always run `docker compose` via `flatpak-spawn --host`; detect via `docker compose version`; account for snap docker on Ubuntu (Pitfall 5) |
| docker compose isolation | Mismatched project name between up/down; blind ports | Stable persisted `COMPOSE_PROJECT_NAME`; probe free ports; `down --remove-orphans`; startup reconcile (Pitfall 6) |
| git worktree | `--force` past "already checked out"; `rm -rf` to remove | Check `worktree list --porcelain` first; kill procs + compose down before `worktree remove` + `prune` (Pitfall 9) |
| VTE in Flatpak | Bump VTE without re-pinning C++ deps | Read VTE's subproject wraps for exact fast_float/simdutf versions; re-test offline build on every bump (Pitfall 8) |

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-terminal scrollback × N | Memory creep with verbose agent output | Modest configurable scrollback; free VTE on hibernate | A handful of chatty terminals open all day |
| N agents + N isolated stacks | Swap thrash, OOM, UI jank | Caps, hibernate, lazy-start, shared-by-default containers | ~4–6 worktrees with isolated stacks on a 16 GB machine |
| Blaming GTK/Python for memory pressure | "Rewrite in Rust" urge | Measure per-process/per-container RSS; cost is agents+containers | As soon as parallelism is real (Degrau 3+) |
| VTE reflow on many resizes | Stutter on window resize/relayout | Limit live VTE count; bound scrollback | Many terminals + frequent layout changes |
| Polling host for status/RAM aggressively | CPU burn, flatpak-spawn overhead | Batch/throttle host queries; prefer hooks/events over polling | Tight polling loops across N worktrees |

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| Treating the Flatpak sandbox as a security boundary | It isn't — `--talk-name=org.freedesktop.Flatpak` + `--filesystem=home` + host spawn = arbitrary host code execution by design | Be honest in docs: arduis is a host-driving tool; the sandbox is for distribution/packaging, not isolation. Don't over-claim safety. |
| Over-broad portal permissions | Larger attack surface; Flathub review friction | Keep `finish-args` minimal; avoid docker-socket filesystem perms by routing docker through `--host` (Pitfall 5) |
| Injecting hook config / writing to user repos | Surprising writes to user's project (e.g. Claude Code hook config) | Be explicit/opt-in about any config arduis writes into a worktree; document it; prefer per-worktree managed settings over editing user's global config |
| Running setup commands from `.arduis.toml` automatically | A repo's `.arduis.toml` can run arbitrary host commands on worktree creation | Treat `.arduis.toml` setup as trusted-repo-only; consider confirmation on first run for an unfamiliar repo |

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Flickering/unreliable "waiting" indicator | Destroys trust in the core value ("always know who waits for you") | Hook/bell-driven authoritative state; soft hint for heuristic state (Pitfall 3) |
| Breaking tmux muscle-memory keybindings | The user's #1 stated requirement violated | App-scoped configurable chords tested under Wayland; default to the user's tmux scheme (Degrau 5) |
| Silent container/port state | User can't tell what's running where | Port/RAM/status badges per worktree (already in mockups); reflect real probed ports |
| Forced worktree removal losing uncommitted work | Data loss | Warn on dirty tree; never force-delete; offer to commit/stash (Pitfall 9) |
| Hidden orphaned containers eating RAM | "Why is my machine slow?" with no visibility | Startup reconciliation + per-worktree RAM/container visibility (Pitfalls 6,7) |

## "Looks Done But Isn't" Checklist

- [ ] **Terminal spawn (Degrau 1):** Often missing — verify Ctrl+C interrupts a host subprocess, Ctrl+Z/fg work, closing the window kills host `claude`/`zsh` (no orphans), and exit codes/signals are decoded correctly.
- [ ] **Agent environment (Degrau 1/4):** Often missing — verify `claude`, `gh`, `docker`, and the user's zsh theme/aliases all resolve inside the embedded terminal, on **both** Ubuntu and Arch.
- [ ] **Waiting detection (Degrau 4):** Often missing — verify it's hook/bell-driven, survives a Claude Code TUI redraw mid-response (no false orange), and fires for a real approval prompt (no missed orange). Test with a long streaming response and a real tool-approval prompt.
- [ ] **Worktree create (Degrau 2):** Often missing — verify "existing branch already checked out" is handled gracefully, not `--force`d.
- [ ] **Worktree cleanup (Degrau 8):** Often missing — verify teardown order (kill agent → compose down → check clean → worktree remove → prune); verify no orphaned containers/ports remain.
- [ ] **Container isolation (Degrau 7):** Often missing — verify stable project name across up/down, probed free ports, `--remove-orphans` on teardown, startup reconciliation after a crash, and that bind-mounted absolute paths are flagged as non-isolated.
- [ ] **RAM management (Degrau 3/7):** Often missing — verify hibernate actually frees agent RAM + stops containers, caps are enforced, and per-worktree RAM is shown.
- [ ] **Cross-distro (Degrau 9):** Often missing — verify a clean Ubuntu **and** clean Arch install both run, under real Wayland.
- [ ] **Flatpak offline build (Degrau 1/9):** Often missing — verify the VTE + fast_float + simdutf build reproducibly offline and `Vte-3.91` imports against SDK 50.

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Screen-scrape detection rotted | MEDIUM | Rip out regex; switch to Claude Code hooks + BEL signal; keep activity-timeout fallback |
| Orphaned containers leaking RAM | LOW | Startup reconcile: list `arduis-*` compose projects, `down --remove-orphans` those with no live worktree |
| Stale git worktree metadata | LOW | `git worktree prune`; re-list; never hand-edit `.git/worktrees` |
| Ctrl+C / job control broken | MEDIUM-HIGH | Re-architect spawn (ctty ownership, login-shell wrapper, explicit portal SIGINT); validate with subprocess interrupt test |
| Exit status misread | LOW | Decode `waitpid` status with `os.waitstatus_to_exitcode`; add smoke tests |
| Env/PATH missing on a user's machine | LOW-MEDIUM | Spawn via host login shell; stop assuming PATH/binary locations |
| Port collisions | LOW | Add free-port probe + retry; persist a port registry |
| RAM blow-up | MEDIUM | Enforce caps, lazy-start agents on focus, hibernate idle, default containers off |
| Wayland keybinding/distro divergence | MEDIUM | Keep chords app-scoped; dogfood both distros under real Wayland earlier |

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| 1. tcsetpgrp / Ctrl+C / job control | Degrau 1 (re-check 5) | Interrupt a host `sleep` under the agent; Ctrl+Z/fg work; no orphans on close |
| 2. Exit-status misdecode | Degrau 1 / 4 | Smoke test exit 0 / exit 3 / SIGTERM classified correctly |
| 3. Fragile waiting-detection | Degrau 4 (research spike) | Hook/bell fires for real prompt; no false orange during streaming |
| 4. Env/PATH not inherited | Degrau 1 (re-check 6,7) | `claude`/`gh`/`docker`/zsh config resolve on Ubuntu + Arch |
| 5. Docker socket / sandbox | Degrau 7 | `docker compose version` works via `--host`; snap-docker Ubuntu OK |
| 6. Compose isolation leaks | Degrau 7 / 8 | Stable project name; probed ports; `--remove-orphans`; startup reconcile |
| 7. RAM blow-up | Degrau 3 design → 7 real | Hibernate frees RAM; caps enforced; per-worktree RAM shown |
| 8. VTE scrollback / build drift | Degrau 1 / 9 | Sane scrollback; offline reproducible VTE build; `Vte-3.91` imports |
| 9. git worktree lifecycle | Degrau 2 / 8 | "already checked out" handled; correct teardown order; prune heals |
| 10. Wayland / Ubuntu-vs-Arch | Degrau 3 → 9 | Clean install both distros under real Wayland; chords work |
| 11. Scope creep / over-engineering | All phases (process) | No swarm work until v1 dogfooded; each Degrau installable+usable |

## Sources

- flatpak-spawn `tcsetpgrp` / job-control breakage in interactive host shells — https://github.com/flatpak/flatpak/issues/3697 (HIGH)
- flatpak-spawn exit-status mangling fix (`waitpid` decoding) — https://github.com/flatpak/flatpak-xdg-utils/pull/10 and https://blogs.gnome.org/wjjt/2018/06/08/ (HIGH)
- flatpak-spawn signal/exit semantics — https://man7.org/linux/man-pages/man1/flatpak-spawn.1.html (HIGH)
- Environment/PATH not inherited via flatpak-spawn --host — https://github.com/flatpak/flatpak/issues/5278, https://github.com/zed-industries/zed/issues/53238, https://github.com/flathub/com.vscodium.codium/issues/411 (HIGH)
- flatpak-spawn `--cwd`/working-dir translation — https://github.com/flatpak/flatpak/issues/2418, https://github.com/matthiasclasen/flatpak/commit/e53ad1ac02592fd97dae7a224ea7ca313b1291b8 (MEDIUM)
- Docker socket access from Flatpak — https://docs.flatpak.org/en/latest/sandbox-permissions.html, https://github.com/flathub/com.jetbrains.IntelliJ-IDEA-Ultimate/issues/22 (MEDIUM)
- VTE inside Flatpak / runtime notes — https://discourse.gnome.org/t/vte-terminal-inside-flatpak/580 (MEDIUM)
- VTE scrollback warning + perf/LZ4 work — https://gnome.pages.gitlab.gnome.org/vte/gtk4/method.Terminal.set_scrollback_lines.html, https://www.phoronix.com/news/GNOME-VTE-Goes-Faster, https://discourse.gnome.org/t/terminal-and-vte-news/20030 (HIGH)
- Claude Code Notification/Stop hooks + BEL for waiting/approval — https://code.claude.com/docs/en/hooks-guide, https://github.com/anthropics/claude-code/issues/36850, https://github.com/anthropics/claude-code/issues/13024, https://github.com/anthropics/claude-code/issues/12048 (MEDIUM)
- TUI screen-scraping fragility / PTY buffering — https://github.com/mstsirkin/interminai, https://github.com/pexpect/pexpect/blob/master/doc/FAQ.rst (MEDIUM)
- git worktree gotchas (already-checked-out, locks, prune, submodules) — https://git-scm.com/docs/git-worktree, https://fixdevs.com/blog/git-worktree-not-working/ (HIGH)
- docker compose project isolation / orphans / `--remove-orphans` — https://github.com/docker/compose/issues/9718, https://www.kubeblogs.com/how-to-avoid-issues-with-docker-compose-due-to-same-folder-names-project-isolation-best-practices/ (MEDIUM)
- Project context — `.planning/PROJECT.md`, `docs/MOTIVATION.md`, `docs/ROADMAP.md`, `io.github.thallys.Arduis.yml`, `src/main.py`

---
*Pitfalls research for: Flatpak GTK4/VTE multi-agent worktree orchestrator driving the host*
*Researched: 2026-06-08*
