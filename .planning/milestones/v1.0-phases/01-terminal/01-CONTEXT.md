# Phase 1: Terminal - Context

**Gathered:** 2026-06-08
**Status:** Ready for planning

<domain>
## Phase Boundary

A GTK4/libadwaita window with **one** real VTE terminal running the user's host `zsh` via a
**direct native PTY** (no sandbox). All host execution funnels through a thin `HostRunner`
seam that is a no-op for native builds. This phase retires the foundational risk (host shell
in an embedded terminal with correct signals/job-control/exit-status) before worktrees,
multiple panes, or agents are built on top. Covers **TERM-01**.

Out of scope for this phase: worktrees (Phase 2), multiple panes / sidebar (Phase 3), agent
status detection (Phase 4), theme-switching UI (Phase 5), `.arduis.toml` (Phase 6).

</domain>

<decisions>
## Implementation Decisions

### Distribution model (project-level pivot — affects this phase directly)
- **D-01:** Flatpak is **out of v1**. arduis ships as **native packages**: `.deb` (Ubuntu) +
  AUR (Arch), using the **system VTE** (Ubuntu 24.04 `gir1.2-vte-3.91` 0.76 in `main`,
  verified; Arch `vte4` 0.84). No VTE/simdutf/fast_float bundling.
- **D-02:** Because there is no sandbox, the terminal spawns the host `zsh` through a
  **direct native PTY** (like BridgeMind on Mac) — no `flatpak-spawn --host`.
- **D-03:** Code targets the **VTE 0.76 API floor** so the same code runs on Ubuntu (0.76)
  and Arch (0.84). (0.76 covers Phase 1 and the OSC 133 needed in Phase 4.)

### HostRunner seam
- **D-04:** A thin `HostRunner` abstraction centralizes all host execution. On native builds
  it is a **no-op** (spawns the command directly). The Flatpak path (prepend
  `flatpak-spawn --host`) is **stubbed but unused** — a single place to re-enable an optional
  Flatpak channel in v2 (DIST-01) without reshaping code.
- **D-05:** The terminal PTY spawn goes through `HostRunner`, even though it is a no-op now —
  the seam must exist from day one (it is the v2 reattach point).

### Terminal theme / colors
- **D-06:** **The app owns the terminal color palette**, not the shell. Phase 1 applies the
  app's palette (16 ANSI colors + fg/bg). Default = **Dracula** (matches the draft).
- **D-07:** The user's `zsh` provides behavior only — PATH, aliases, functions, prompt *text*.
  The prompt renders using the app's palette, never colors the shell tries to impose.
- **D-08:** Per-window/per-pane theme selection is the eventual goal, but the **theme-switching
  UI is Phase 5 (UI-02)**. Phase 1 just hardcodes the Dracula default; it must not depend on
  the shell's theme.

### Shell invocation
- **D-09:** Spawn `zsh` as **login + interactive** (`zsh -l -i`) so `.zprofile` + `.zshrc`
  both load and `claude` / `gh` / `docker` / version-manager shims (asdf/nvm/pyenv) resolve
  (Success Criterion #2).
- **D-10:** Force `TERM=xterm-256color` (as the draft does). Working directory = the user's
  home for Phase 1.

### Signals, job control, exit status (the acceptance bar)
- **D-11:** Ctrl+C must interrupt the running host subprocess; Ctrl+Z + `fg` job control must
  work. Native (no sandbox boundary), so this is expected to "just work" — but it is still a
  **mandatory acceptance check** for the phase.
- **D-12:** Exit codes and signals decoded correctly via `os.waitstatus_to_exitcode`.

### Window-close teardown (no orphans)
- **D-13:** On window close, send **SIGHUP to the child process group**, then **SIGKILL**
  after a short timeout if anything survives. Native `os.killpg` (no sandbox indirection).
  "No orphans" = no leftover host `zsh`/agent process after the window closes.

### Acceptance testing approach
- **D-14:** Interactive signal/job-control checks (Ctrl+C, Ctrl+Z/`fg`, no-orphans on close)
  are a **documented manual acceptance checklist**. Exit-code/signal decoding
  (`os.waitstatus_to_exitcode`) gets a **small automated unit test**. Pragmatic for solo dev;
  avoids heavy Wayland-GUI test harness in Phase 1.

### Draft disposition
- **D-15:** The uncommitted draft `src/main.py` is the **starting base**, but must be changed:
  remove `flatpak-spawn --host` from the spawn argv (direct `zsh -l -i`), and route the spawn
  through `HostRunner`. The Flatpak manifest (`io.github.thallys.Arduis.yml`) and `dev.sh`
  are **obsolete** — replace with a native run/build path. Keep `data/*.desktop` / metainfo.

### Claude's Discretion
- Exact `HostRunner` API shape/signature (as long as it's the single host-exec seam, no-op
  native, Flatpak-stub).
- Font choice/size beyond the draft's `monospace 11`, scrollback specifics.
- Native run/build tooling for dev (replacing `dev.sh`) — Meson vs plain script.
- File/module layout for the Phase-1 app.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope & requirements
- `.planning/ROADMAP.md` § "Phase 1: Terminal" — goal + 5 success criteria (the acceptance bar)
- `.planning/REQUIREMENTS.md` § TERM-01, § DIST (native pivot, DIST-01 deferred to v2)
- `.planning/PROJECT.md` § Key Decisions — distribution pivot + VTE-from-system rows

### Product background (rich prior docs)
- `docs/MOTIVATION.md` — base motivation document for arduis
- `docs/ROADMAP.md` — original degraus roadmap + `.arduis.toml` schema + swarm track (context
  for later phases; Phase 1 only needs the terminal/seam framing)

### Visual reference (approved mockups)
- `docs/mockup/interface-v1.html` / `interface-v1.png` — v1 Dracula layout
- `docs/mockup/interface-v2-bridgespace.html` / `interface-v2-bridgespace.png` — v2 BridgeSpace-style
  (Phase 1 is a single terminal; mockups inform the eventual shell, not this phase's UI)

### Draft to evolve
- `src/main.py` — Degrau-1 draft (GTK4 + Adw window + VTE Dracula terminal). Adopt as base,
  strip `flatpak-spawn`, route through `HostRunner`.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/main.py`: working `Adw.ApplicationWindow` + `Adw.ToolbarView`/`HeaderBar` + `Vte.Terminal`
  with Dracula palette, font, scrollback, and `child-exited` → close. Solid Phase-1 skeleton.
- `data/io.github.thallys.Arduis.desktop` + `.metainfo.xml`: keep for native packaging.

### Established Patterns
- `gi.require_version("Vte", "3.91")` + GTK4 + libadwaita is the confirmed stack.
- Dracula palette already defined as constants in the draft.

### Integration Points
- `HostRunner` is the new seam introduced here; the VTE spawn and (later) all git/gh/docker
  calls route through it. It is the first thing planned in Phase 1.

### Obsolete (remove/replace)
- `io.github.thallys.Arduis.yml` (Flatpak manifest) and `dev.sh` — no longer the build/run path.
- `flatpak-spawn --host` argv prefix in `_spawn_host_shell`.

</code_context>

<specifics>
## Specific Ideas

- "Igual BridgeMind" — on native Linux, the embedded terminal connects to the host shell the
  same way a normal terminal does: a direct PTY to a child process. The Flatpak sandbox was
  the only reason a bridge was ever needed; removing it removes the bridge.
- The app, not the shell, decides terminal colors (Dracula default), per the user.

</specifics>

<deferred>
## Deferred Ideas

- **Flatpak channel** → v2 (DIST-01). The `HostRunner` Flatpak-stub keeps this cheap to add
  later without reshaping code.
- **Reattach to live agents after closing/reopening the whole app** → v2 (PERSIST-01); needs a
  host-side tmux/abduco layer.
- **Same shell session mirrored across multiple panes/windows** (tmux-style multiplexing) →
  not in v1; raised during discussion, not adopted.
- **`CLAUDE.md` cleanup** → its tech-stack section still describes Flatpak/VTE-bundling/
  `flatpak-spawn` and contradicts this pivot; needs a separate cleanup pass (tracked in STATE.md).

</deferred>

---

*Phase: 01-terminal*
*Context gathered: 2026-06-08*
