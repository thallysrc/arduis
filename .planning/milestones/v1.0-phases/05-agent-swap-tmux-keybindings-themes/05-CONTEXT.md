# Phase 05: Agent Swap + tmux Keybindings + Themes - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning
**Mode:** Autonomous — the user delegated decisions ("tome as decisões por você mesmo enquanto estarei AFK") and asked for Fable on planning (Fable is currently inaccessible to subagents in this Opus-4.8 session — research ran on the session model; the preference persists in config.json for when Fable is the session model). Every decision below adopts the recommended default from 05-RESEARCH.md (HIGH-confidence, VTE 0.76 API verified by runtime probe, mechanisms read from working code). Revisitable at UAT.

<domain>
## Phase Boundary

Wrap three ALREADY-WORKING seams in config/registry layers — no new mechanisms, zero new
dependencies:
- **AGENT-01:** the agent is a CONFIGURABLE command (default `claude`) fed into the durable
  `zsh -l -i` PTY; Ctrl+C drops to the live shell (native job control) and the user runs
  another agent in the SAME pane — the shell NEVER re-spawns.
- **UI-01:** the existing C-Space prefix state machine + `keymap.KEYMAP` get a config layer
  (`[keys]` in arduis.toml): a configurable prefix + a flat char→action bindings map.
- **UI-02:** a GTK-free theme registry (Dracula default + Nord + Solarized Dark + Gruvbox
  Dark), each defining BOTH the 16-color VTE palette (+fg/bg/cursor) AND the UI colors
  `window._CSS` hardcodes; runtime switch re-applies the CSS provider and re-colors every live
  VTE; switch persists; switch UI is a header primary-menu "Tema" submenu.

**Out of scope:** light themes (all 4 are dark — libadwaita FORCE_DARK stays consistent);
a GUI editor for agent command / keybindings (those are TOML-edited like `[attention]`);
multi-key chord sequences (prefix grammar stays C-Space+single-key); per-window (vs per-app)
theme (one active theme app-wide this phase); the `keyboard-shortcuts-inhibit` Wayland
protocol (not needed — the prefix is app-internal).
</domain>

<decisions>
## Implementation Decisions

### Agent as configurable command (AGENT-01)
- **D-01:** The fed agent command comes from `[agent] command` in `~/.config/arduis/arduis.toml`
  (default `"claude"`). Parsed with `shlex.split` so args work (`"claude --model opus"`,
  `"aider"`). Fed as bytes into the durable shell exactly as today (AGENT_FEED is built from
  the configured command, not a hardcoded literal).
- **D-02:** Ctrl+C behavior is UNCHANGED (native job control drops to zsh — Phase 1). Add a
  convenience "re-feed agent" action on `C-Space a` (D-08) that types the configured agent
  command into the focused pane's live shell. The shell is NEVER killed on swap (Pitfall 5).
- **D-03:** Auto-suspend resume (Phase 4 `AGENT_RESUME_FEED`) becomes the configured command
  + `--continue` ONLY when that command is claude-family; for a non-claude agent, resume feeds
  the plain configured command (no `--continue` — it's a claude flag). Keep it simple: if the
  configured command's argv[0] basename is `claude`, append `--continue` on auto-suspend
  resume; else feed the bare command.

### Configurable tmux keybindings (UI-01)
- **D-04:** A `[keys]` config layer over the GTK-free `keymap.KEYMAP`: a `prefix` string
  (default `"ctrl+space"`; `"ctrl+b"` to mimic tmux) + a flat `[keys.bindings]` char→action-name
  map (closed action set: `split_v`/`split_h`/`zoom`/`refeed_agent`/focus moves). Omitted keys
  keep defaults; unknown action names are ignored (safe). The working prefix state machine is
  NOT redesigned — only its table + prefix become config-driven.
- **D-05:** Parsing lives in a GTK-free helper (mirror `attention.load_config`): hostile/garbage
  values fall back to the default binding for that key. The capture-phase `EventControllerKey`
  stays exactly as is.

### Themes (UI-02)
- **D-06:** A frozen `Theme` dataclass in a NEW GTK-free `src/arduis/themes.py`, registered in a
  `THEMES` dict keyed by slug. Each theme supplies the 16-color VTE palette + fg/bg/cursor AND
  the UI colors (`_BG2` surface, focus ring, branch pink, the 5 status-dot colors).
  `get_theme(name)` returns Dracula for any unknown/missing name. Ship 4: `dracula` (default,
  values verbatim from theme.py), `nord`, `solarized-dark`, `gruvbox-dark` (hex tables in
  05-RESEARCH DESIGN — sanity-check the 3 non-Dracula palettes against their cited specs during
  planning; a wrong hex is cosmetic, Pitfall 6 guards the parse).
- **D-07:** Runtime switch: remove the old `CssProvider` from the display before adding the new
  one (Pitfall 1 — no stacking), and call `set_colors` on EVERY live `Vte.Terminal` (all tasks'
  task-level pair + splits + per-repo). `_make_terminal` reads `self._current_theme` so
  resumed/split/newly-spawned terminals are born in the active theme (Pitfall 2). VTE 0.76
  `set_colors`/`set_color_foreground`/`set_color_background`/`set_color_cursor` confirmed present.
- **D-08:** Switch UI: a `Gtk.MenuButton` (`open-menu-symbolic`) on the header `pack_end` with a
  "Tema" submenu of radio-style entries, one `win.set_theme(slug)` per theme. No preferences
  dialog this phase.
- **D-09:** Persistence: a tiny GTK-free atomic writer (`appconfig.write_theme(path, name)`)
  reads-parses-rewrites arduis.toml via tmp+`os.replace` (the project's existing atomic-write
  pattern), persisting `[theme] name`. NO `tomli-w` dependency. Accepts that inline TOML
  comments are lost on rewrite (documented). The theme loads from `[theme] name` at startup
  (Dracula fallback).

### Config consolidation
- **D-10:** All three sections (`[agent]`, `[keys]`, `[theme]`) live in the SAME
  `~/.config/arduis/arduis.toml` Phase 4 introduced. One consolidated loader (extend the
  attention config pattern or a sibling module) reads all sections with safe defaults; read is
  stdlib `tomllib`; the only write is the targeted theme writer (D-09).
</decisions>

<specifics>
## Specific Ideas
- TDD rhythm (Wave 0 RED → GREEN) as every prior phase: new `tests/test_themes.py`,
  `tests/test_keyconfig.py`, `tests/test_agentconfig.py` + extend `tests/test_keymap.py`.
- The VTE 16-color palettes ARE the tmux color contract (same ANSI indices) — no separate tmux
  config; tmux-in-a-pane inherits via `TERM=xterm-256color` + the VTE palette.
- Criterion 3 (Wayland app-scoped shortcuts) is ALREADY satisfied by the capture-phase
  controller — it's app-internal propagation, not a compositor grab. This is a UAT VERIFICATION
  (`echo $XDG_SESSION_TYPE` == wayland; confirm C-Space arms), not new code.
</specifics>

<deferred>
## Deferred Ideas
- Light themes / system-accent following → not this phase (all dark).
- GUI editors for agent command + keybindings → TOML-edited for now (consistent with [attention]).
- Multi-key chord sequences; per-window theme; tomli-w-based full config writer → later/if needed.
</deferred>

---

*Phase: 05-agent-swap-tmux-keybindings-themes*
*Decisions: 10 locked (autonomous, research-recommended defaults)*
*Ready for: planning (UI-SPEC-grade contract — UI hint: yes)*
