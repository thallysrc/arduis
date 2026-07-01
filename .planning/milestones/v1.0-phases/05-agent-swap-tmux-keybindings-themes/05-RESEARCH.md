# Phase 5: Agent Swap + tmux Keybindings + Themes - Research

**Researched:** 2026-06-13
**Domain:** GTK4/libadwaita config-driven theming + VTE palette switching + GTK4 key routing on Wayland + agent-as-command seam
**Confidence:** HIGH

## Summary

Phase 5 is overwhelmingly a **wrap-existing-seams** phase, not a build-new-machinery phase. The three load-bearing mechanisms already exist and work: (1) the agent is fed as bytes into a durable `zsh -l -i` PTY child (`AGENT_FEED`/`session.py`, fed in `window._make_wt_spawn_cb`), so swapping agents is a parameterization of one constant plus a "re-feed" action — the shell never re-spawns; (2) the C-Space prefix state machine runs on a CAPTURE-phase `Gtk.EventControllerKey` on the toplevel window (`window._on_key`) dispatching through the GTK-free `keymap.py` table — making chords configurable is a config layer over that table, not a redesign; (3) the Dracula palette is applied to every VTE via `set_colors`/`set_color_cursor` (`window._make_terminal`) and to the UI via a single display-wide `Gtk.CssProvider` (`window._install_css`) — theme switching is a registry of palettes + a "re-apply provider, re-set every live terminal" runtime path.

The **highest-risk criterion (3, Wayland app-scoped shortcuts) is already satisfied by the current architecture and needs verification, not new code.** `[VERIFIED: docs.gtk.org/gtk4/input-handling]` A CAPTURE-phase key controller on the window is **app-internal event routing within arduis's own surface** — it is NOT a global keyboard grab and does NOT touch the compositor. Wayland's restriction is on *global* shortcut interception across surfaces (which needs the `keyboard-shortcuts-inhibit` protocol); routing a key to a non-focused child widget *inside your own focused window* is plain GTK event propagation and behaves identically on Wayland and XWayland. `C-Space` is not a default Mutter/GNOME global binding, so it reaches arduis's surface unimpeded. No portal, no inhibit protocol, no XWayland dependency.

**Primary recommendation:** Add a config layer (`[agent]`, `[keys]`, `[theme]`) reusing the exact `attention.load_config()` tomllib pattern; keep config **read-mostly with runtime-only theme switching + a tiny atomic TOML writer for persistence** (do NOT add the `tomli-w` dependency — hand-write the 3 lines arduis owns). Build a GTK-free `themes.py` registry (Dracula + Nord + Solarized Dark + Gruvbox Dark) mirroring `theme.py`'s shape, a GTK-free `keyconfig.py` that merges user chords over `keymap.KEYMAP`, and a GTK-free `agentconfig.py` for the agent command (shlex-split). Wire all three into `window.py` behind a header-bar primary menu (theme submenu) + a re-feed-agent action bound to a configurable chord.

## User Constraints

No `CONTEXT.md` exists for Phase 5 (standalone research, no discuss-phase ran — the user is AFK and the orchestrator decides). Constraints are therefore drawn from **CLAUDE.md** and the **ROADMAP/REQUIREMENTS** and are treated with locked-decision authority. See `## Project Constraints (from CLAUDE.md)` below. Every open decision in this document carries a **recommended default** so the orchestrator can proceed without the user.

## Project Constraints (from CLAUDE.md)

These are non-negotiable and the planner must not contradict them:

- **VTE 0.76 API floor.** Code only to APIs present in Vte-3.91 0.76 (Ubuntu 24.04). `[VERIFIED: runtime probe]` `set_colors`, `set_color_foreground`, `set_color_background`, `set_color_cursor` all exist at 0.76 on the dev host. Never use a VTE API newer than 0.76 without a guard.
- **The app owns the terminal palette, not the shell.** "Per-window theme switching is Phase 5 (UI-02)." The shell provides PATH/aliases/prompt; colors come from arduis.
- **Dracula is the default theme.** It is the user's tmux/nvim palette.
- **GLib main loop, no threads.** Theme re-apply and config reads happen on the main loop (cheap, startup/click-driven). No `asyncio`, no thread pool.
- **`tomllib` is read-only (stdlib).** `tomli-w` is OPTIONAL and only if arduis writes config. (This research recommends a 3-line hand-rolled atomic writer instead — see Don't Hand-Roll / Open Decisions.)
- **AgentSpec stays a plain command (swarm seam).** The agent abstraction must remain "a command string," GTK-free and serializable. No roles/mailbox/MCP.
- **`shlex` for argv construction; never shell strings.** An agent command with args is split with `shlex.split` into an argv list.
- **GTK-free domain modules.** All testable logic (theme registry, key-merge, agent-command parse, config read/write) lives in `gi`-free modules with unit tests; `window.py` is the only `gi` importer.
- **Native build, no Flatpak, no sandbox.** Irrelevant to this phase but confirms there is no portal indirection to worry about for keys.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AGENT-01 | Agent = configurable command (default `claude`); Ctrl+C drops to the shell, user runs another agent in the SAME pane | The durable PTY is `zsh -l -i`; `claude` is *fed* (`feed_child(AGENT_FEED)`), never spawned as the PTY. Ctrl+C is native job control (Phase 1) that returns control to the live zsh. Change: parameterize `AGENT_FEED` from `[agent] command` (shlex), add a "re-feed agent" action so the user can relaunch the configured agent without typing — nothing re-spawns. Findings: §Agent-as-command, §Pattern 1. |
| UI-01 | Configurable tmux keybindings (`C-Space` prefix, `C-h/j/k/l`, split `-`/`=`, zoom `z`) | The CAPTURE-phase prefix machine (`window._on_key`) + GTK-free `keymap.KEYMAP` table already dispatch h/j/k/l/n/p/digits. Change: add split/zoom chords to the action set (already TODO per keymap.py D-09/D-10), add a `[keys]` config layer that merges user overrides over the default table, keep the dispatcher untouched. Findings: §tmux keybindings, §Pattern 2. |
| UI-02 | App + terminal color themes (VTE palette + UI), Dracula default, swappable | `theme.py` holds the Dracula constants; `window._make_terminal` applies them via `set_colors`; `window._install_css` applies UI colors via a display CssProvider. Change: a GTK-free `themes.py` registry (≥2 themes), a runtime switch path (rebuild the CssProvider + `set_colors` on every live terminal), `[theme] name`, and a header-menu switch UI. Findings: §Theme switching, §DESIGN, §Pattern 3. |
</phase_requirements>

## Standard Stack

No new third-party libraries. Everything is stdlib + the already-present GNOME stack.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `tomllib` | stdlib (3.11+) | Read `[agent]`/`[keys]`/`[theme]` from `~/.config/arduis/arduis.toml` | `[VERIFIED: CLAUDE.md + attention.py]` Already the project's config reader; read-only is correct for config |
| `shlex` | stdlib | Split an agent command string (`"claude --model opus"`) into an argv list | `[VERIFIED: CLAUDE.md]` Mandated for safe argv construction; never join into a shell string |
| PyGObject / Vte-3.91 | system 0.76 | `Vte.Terminal.set_colors` / `set_color_cursor` to re-theme live terminals | `[VERIFIED: runtime probe]` Methods present at the 0.76 floor on the dev host |
| PyGObject / Gtk 4.0 | system | `Gtk.CssProvider`, `Gtk.StyleContext.add_provider_for_display`, `Gtk.EventControllerKey` (CAPTURE) | `[VERIFIED: existing window.py]` Already used for CSS + key routing |
| libadwaita | system 1.x | `Adw.HeaderBar` primary menu (`Gtk.MenuButton` + `Gio.Menu`) for the theme switcher | `[CITED: gnome.pages.gitlab.gnome.org/libadwaita/styles-and-appearance]` Standard place for an app menu |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `Gio.SimpleAction` | system | `win.set_theme(s)`, `win.refeed_agent` actions backing the menu + chord | Already the pattern for `win.hibernate`/`win.resume` |
| `os` + `tempfile` (atomic write) | stdlib | Persist `[theme] name` back to `arduis.toml` if persistence is chosen | `[VERIFIED: window._install_hooks]` Project already does tmp-file + `os.replace` atomic writes for `settings.json` |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled 3-line TOML writer | `tomli-w` 1.x | `tomli-w` adds a runtime dependency to write one `name = "..."` line; CLAUDE.md flags it "optional only if arduis writes config." A round-trip-preserving writer (`tomlkit`) would clobber comments unless careful. Recommend a minimal targeted writer (see Open Decisions). |
| `Adw.StyleManager` color-scheme | full custom CSS variables | `[CITED: libadwaita styles-and-appearance]` `Adw.StyleManager` only toggles light/dark + system accent; arduis needs *full named palettes* (Dracula/Nord/...), so a custom `CssProvider` with the theme's hex values is required regardless. Use `StyleManager.set_color_scheme(FORCE_DARK)` once so libadwaita widgets render dark under all our dark palettes. |
| Custom key config schema | GTK accelerators / `Gtk.ShortcutController` | The prefix model (C-Space then a bare key) is a tmux state machine, not a single accelerator. The existing CAPTURE controller already implements it correctly; `ShortcutController` is used only for the LOCAL clipboard shortcuts (Ctrl+Shift+C/V) and is the wrong tool for the prefix grammar. |

**Installation:** None — all stdlib + system packages already required.

**Version verification:**
- `gir1.2-vte-3.91`: `[VERIFIED: apt-cache policy on host 2026-06-13]` `0.76.0-1ubuntu0.1` in Ubuntu `main`.
- `Vte.Terminal.set_colors` / `set_color_foreground` / `set_color_background` / `set_color_cursor`: `[VERIFIED: python3 -c gi probe on host 2026-06-13]` all `hasattr` → True at runtime VTE 0.76.0.
- `tomli-w`: `[VERIFIED: pip3 show]` NOT installed (confirms adding it is a real new dependency).

## Architecture Patterns

### Recommended Project Structure (new/changed files)
```
src/arduis/
├── themes.py        # NEW: GTK-free theme registry (Dracula+Nord+Solarized+Gruvbox), each a Theme dataclass of hex strings
├── keyconfig.py     # NEW: GTK-free merge of user [keys] overrides onto keymap.KEYMAP + prefix override
├── agentconfig.py   # NEW: GTK-free [agent] reader → command string → shlex argv + feed-bytes builder
├── appconfig.py     # OPTIONAL NEW: tiny atomic TOML writer (persist [theme] name); or fold into themes/agent readers
├── theme.py         # KEEP: Dracula constants stay as the default Theme's source (themes.py imports them)
├── keymap.py        # EXTEND: add split/zoom/refeed action tuples to dispatch (the table Phase 5 wraps)
├── session.py       # EXTEND: AGENT_FEED stops being a hardcoded const consumed blindly — window builds the feed from agentconfig
└── window.py        # WIRE: load the 3 configs at startup, header theme menu, runtime re-theme, configurable chords, refeed action
```

### Pattern 1: Agent-as-command (durable shell, fed agent) — AGENT-01
**What:** The PTY child is the durable `zsh -l -i`. The agent is bytes written into that PTY with `feed_child`, so Ctrl+C kills only the agent and returns to the live shell. Swapping agents = feeding a different command; nothing re-spawns.
**When to use:** Default create, manual resume, auto-suspend resume, and the new "re-feed agent" action all funnel through the same feed.
**Example:**
```python
# Source: src/arduis/window.py _make_wt_spawn_cb (existing) + src/arduis/session.py (existing)
# CURRENT (hardcoded):
AGENT_FEED: bytes = b"claude\n"          # session.py
terminal.feed_child(agent_feed)          # window.py, after the shell PTY spawns

# PHASE 5 (parameterized, GTK-free agentconfig.py):
import shlex
def agent_argv(command: str) -> list[str]:
    """shlex-split the configured agent command (CLAUDE.md: never a shell string)."""
    return shlex.split(command)            # "claude --model opus" -> ["claude","--model","opus"]

def agent_feed_bytes(command: str) -> bytes:
    """The bytes fed into the durable zsh to launch the agent (feed_child needs bytes at 0.76)."""
    # Re-join the validated argv so the shell parses it, then newline. shlex.join quotes safely.
    return (shlex.join(shlex.split(command)) + "\n").encode("utf-8")
```
- **Critical invariant:** the agent command is fed to the **shell** (it is a shell command line), not passed to `spawn_async` argv. `spawn_async` still launches `zsh -l -i`. This is why Ctrl+C drops to the shell and a re-feed needs no re-spawn. `[VERIFIED: window.py _spawn_into spawns SHELL_ARGV, then feeds]`
- **Re-feed action:** add `win.refeed_agent` (a `Gio.SimpleAction`) that calls `term.feed_child(agent_feed_bytes(cfg.command))` on the focused terminal. Bind it to a configurable chord (suggest C-Space then `a`). The user can also just type at the shell — the action is a convenience, not a requirement.
- **Feed-bytes, not str:** `feed_child` rejects `str` at the 0.76 floor (`TypeError: Must be number, not str`) — keep encoding to bytes. `[VERIFIED: session.py D-08 comment + existing AGENT_FEED bytes literal]`

### Pattern 2: Configurable chords as a config layer over the GTK-free table — UI-01
**What:** `keymap.py` is already the single GTK-free key table + pure `dispatch`. Phase 5 adds a merge function that overlays user `[keys]` onto the defaults, and extends the action set with split/zoom/refeed. The CAPTURE controller and prefix machine are untouched.
**When to use:** Startup reads `[keys]`; `window._run_action` gains split/zoom/refeed branches.
**Example:**
```python
# Source: src/arduis/keymap.py (existing table) + NEW keyconfig.py
# keymap.py extends dispatch's action set (split/zoom/refeed are the Phase-5 TODO per D-09/D-10):
DEFAULT_KEYMAP = {
    "h": ("focus_dir","left"), "j": ("focus_dir","down"),
    "k": ("focus_dir","up"),   "l": ("focus_dir","right"),
    "n": ("worktree","next"),  "p": ("worktree","prev"),
    "-": ("split","v"),        "=": ("split","h"),     # NEW (tmux-style)
    "z": ("zoom", None),                               # NEW
    "a": ("refeed", None),                             # NEW (re-launch the configured agent)
}

# keyconfig.py (GTK-free, unit-tested) merges user overrides defensively:
def resolve_keymap(user_keys: dict | None) -> dict[str, tuple]:
    table = dict(DEFAULT_KEYMAP)
    for key, action in (user_keys or {}).items():
        parsed = _parse_user_action(action)   # validates against a CLOSED action set
        if parsed is not None and len(key) == 1:
            table[key] = parsed                # unknown/garbage actions are dropped (T-03-03 closed set)
    return table

def resolve_prefix(user_prefix: str | None) -> tuple[str, str]:
    # default ("space","ctrl"); allow override like "ctrl+b" -> ("b","ctrl"); reject garbage -> default
    ...
```
- **Closed action set (security):** never fabricate an action from untrusted config — only map to the known `focus_dir/worktree/jump/split/zoom/refeed` verbs. An unrecognized config value is dropped, mirroring `keymap.dispatch` returning `None` for unknown keys. `[VERIFIED: keymap.py T-03-03 comment]`
- **Config format (recommend):** `[keys] prefix = "ctrl+space"` and a `[keys.bindings]` table mapping a single action-key char to an action name: `"h" = "focus_left"`, `"-" = "split_v"`. Keep it a flat string→string map so the GTK-free parser is trivial and a malformed entry degrades to the default for that key.

### Pattern 3: Theme registry + runtime re-apply — UI-02
**What:** A GTK-free `Theme` dataclass (fg/bg/cursor + 16-color palette + UI accent/surface colors) and a registry. `window` converts a `Theme` to `Gdk.RGBA` + CSS at apply time (GTK stays in `window.py`).
**When to use:** Startup applies `[theme] name`; the header menu / chord triggers a runtime switch.
**Example:**
```python
# Source: src/arduis/theme.py (existing Dracula) generalized into themes.py
from dataclasses import dataclass
@dataclass(frozen=True)
class Theme:
    name: str
    bg: str; fg: str; cursor: str
    palette: tuple[str, ...]      # 16 hex colors (ANSI 0..15)
    # UI (GTK CSS) colors — the subset window._CSS currently hardcodes:
    surface: str; accent: str; focus_ring: str
    dot_active: str; dot_waiting: str; dot_ready: str; dot_idle: str; dot_hibernated: str; branch: str

THEMES: dict[str, Theme] = {"dracula": DRACULA, "nord": NORD, "solarized-dark": SOLARIZED_DARK, "gruvbox-dark": GRUVBOX_DARK}
def get_theme(name: str | None) -> Theme:
    return THEMES.get((name or "dracula").lower(), DRACULA)   # unknown name -> Dracula default
```
```python
# Source: window.py runtime switch (GTK lives here) — re-apply UI CSS + re-color every live terminal
def _apply_theme(self, theme):
    # 1) UI: rebuild the CssProvider from theme colors, REPLACING the old one (Pitfall: no leak).
    if self._css_provider is not None:
        Gtk.StyleContext.remove_provider_for_display(self._display, self._css_provider)
    self._css_provider = Gtk.CssProvider()
    self._css_provider.load_from_data(self._build_css(theme).encode("utf-8"))
    Gtk.StyleContext.add_provider_for_display(self._display, self._css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
    # 2) Terminals: re-color EVERY live VTE (set_colors at the 0.76 floor).
    for term in self._term_by_sid.values():
        term.set_colors(_rgba(theme.fg), _rgba(theme.bg), [_rgba(c) for c in theme.palette])
        term.set_color_cursor(_rgba(theme.cursor))
    self._current_theme = theme
```
- **Re-color includes resumed terminals:** terminals created *after* a switch must also get the current theme. Make `_make_terminal()` read `self._current_theme` instead of the `DRACULA_*` constants, so a hibernated-then-resumed task's fresh VTE is born in the active theme. `[VERIFIED: window._make_terminal currently hardcodes DRACULA_*]`

### Anti-Patterns to Avoid
- **Re-spawning the shell to swap agents.** Breaks the durable-PTY invariant, loses scrollback/cwd. Feed bytes into the existing PTY instead.
- **Adding a second `CssProvider` per switch without removing the old one.** Providers stack on the display → color drift + memory growth. Always `remove_provider_for_display` the previous one first.
- **Setting VTE colors from the shell (`PROMPT`/OSC).** CLAUDE.md: the app owns the palette. Keep `set_colors` authoritative.
- **Global keyboard grab / `keyboard-shortcuts-inhibit` for the prefix.** Unnecessary and wrong — the prefix is app-internal routing, not a compositor shortcut (see §Wayland).
- **Passing the agent command as `spawn_async` argv.** Then Ctrl+C would kill the PTY child (the agent IS the shell) and there'd be nothing to drop back to. Feed it to the shell.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Splitting `"claude --foo bar"` into argv | A custom space-splitter | `shlex.split` | Handles quotes/escapes; CLAUDE.md mandates it; avoids injection |
| Reading TOML config | A custom parser | `tomllib` (stdlib) | Already the project pattern (`attention.load_config`) |
| App-scoped key routing on Wayland | A compositor inhibitor / portal / `evdev` listener | `Gtk.EventControllerKey` CAPTURE phase (already in place) | App-internal propagation needs no special Wayland API |
| UI dark styling of libadwaita widgets | Restyling every Adw widget by hand | `Adw.StyleManager.set_color_scheme(FORCE_DARK)` once | Lets Adw widgets pick a dark base; your CssProvider only overrides accents/surfaces |
| Atomic config write | `open().write()` in place | tmp-file + `os.replace` (already used for settings.json) | Avoids torn writes on crash |

**Key insight:** Phase 5 adds **zero** external dependencies. The temptation is to reach for `tomli-w` (write), the shortcuts-inhibit protocol (keys), or `Adw.StyleManager` accent palettes (themes) — all three are unnecessary given the existing seams.

## Common Pitfalls

### Pitfall 1: Stacking CSS providers on theme switch
**What goes wrong:** Each switch adds a new provider; old colors bleed through at the same priority and providers accumulate.
**Why it happens:** `add_provider_for_display` is additive; there's no implicit replace.
**How to avoid:** Keep `self._css_provider` handle; `remove_provider_for_display` it before adding the new one. `_install_css` currently creates a provider without keeping a handle — refactor it to store the handle so it can be replaced.
**Warning signs:** Switching dracula→nord→dracula leaves wrong accent colors or rising memory.

### Pitfall 2: Newly-spawned terminals keep the old theme
**What goes wrong:** Switch theme, then resume a hibernated task — its fresh VTE is Dracula again.
**Why it happens:** `_make_terminal` reads the `DRACULA_*` module constants, not the active theme.
**How to avoid:** Route `_make_terminal` through `self._current_theme`; on every switch, re-color all *existing* terminals AND set `_current_theme` so future ones are born correct.
**Warning signs:** Mixed-theme panes after a resume/split following a switch.

### Pitfall 3: C-Space collides with the user's own zsh/claude binding
**What goes wrong:** The user has `bindkey` or a TUI binding on C-Space; arduis swallows it first (CAPTURE phase), so the inner program never sees it.
**Why it happens:** CAPTURE intercepts before the focused VTE — by design, but it means the prefix is *globally* unavailable inside panes.
**How to avoid:** Make the prefix configurable (`[keys] prefix`) so a colliding user can move it (e.g. `ctrl+b`, the tmux default). Document the tradeoff. The existing machine only swallows the prefix when *disarmed* and a recognized action when *armed*; everything else propagates, so the collision surface is exactly one chord. `[VERIFIED: window._on_key returns False for non-prefix/unrecognized]`
**Warning signs:** User reports C-Space "doesn't work" inside their TUI.

### Pitfall 4: Agent command with arguments fed unsafely
**What goes wrong:** A command like `claude --model "opus 4"` fed raw could mis-parse or (if ever joined into a shell string) inject.
**Why it happens:** Naive string concatenation.
**How to avoid:** `shlex.split` to validate, `shlex.join` to re-serialize for the feed, encode to bytes. Reject an empty/whitespace command → fall back to `claude`.
**Warning signs:** Agent launches with mangled args.

### Pitfall 5: Killing the zsh when swapping agents
**What goes wrong:** A "swap agent" implementation that tears down the terminal/pgid instead of feeding the shell.
**Why it happens:** Conflating "the agent" with "the terminal."
**How to avoid:** Swap = Ctrl+C (native) + feed new command. The durable shell's pid/pgid (the teardown handle on the `TerminalRecord`) must remain valid across swaps. Never call `_teardown_pgid` on a swap.
**Warning signs:** Pane goes dead / RAM accounting loses the terminal after a swap.

### Pitfall 6: `set_colors` palette length / RGBA parse
**What goes wrong:** A theme with !=16 palette entries or a malformed hex string makes `set_colors` raise.
**Why it happens:** Hand-edited theme registry or config typo.
**How to avoid:** The registry is in-code (not user TOML) so it's controlled; still, validate each `Theme` has exactly 16 palette colors in a unit test. `_rgba` should tolerate a bad parse (Gdk.RGBA.parse returns bool) — log + fall back to Dracula.
**Warning signs:** Crash on switch to a specific theme.

## Code Examples

### Reading the consolidated config (mirror attention.load_config)
```python
# Source: pattern from src/arduis/attention.py load_config (VERIFIED existing)
import tomllib
from dataclasses import dataclass

@dataclass
class AgentConfig:
    command: str = "claude"

def load_agent_config(path: str) -> AgentConfig:
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return AgentConfig()
    section = data.get("agent")
    if not isinstance(section, dict):
        return AgentConfig()
    cmd = section.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return AgentConfig()
    return AgentConfig(command=cmd.strip())
```

### Header-bar theme switcher (UI)
```python
# Source: libadwaita HeaderBar + Gio.Menu (standard); actions mirror win.hibernate
menu = Gio.Menu()
theme_menu = Gio.Menu()
for key, theme in THEMES.items():
    item = Gio.MenuItem.new(theme.display_name, None)
    item.set_action_and_target_value("win.set_theme", GLib.Variant.new_string(key))
    theme_menu.append_item(item)
menu.append_submenu("Tema", theme_menu)
menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
header.pack_end(menu_btn)
# action:
act = Gio.SimpleAction.new("set_theme", GLib.VariantType.new("s"))
act.connect("activate", lambda a, p: self._apply_theme(get_theme(p.get_string())))  # + persist
self.add_action(act)
```

## DESIGN (UI phase)

### Theme registry shape
A frozen `Theme` dataclass in GTK-free `themes.py`, registered in a `THEMES` dict keyed by a slug. Each theme supplies BOTH the 16-color VTE palette (+ fg/bg/cursor) AND the handful of UI colors `window._CSS` currently hardcodes (surface `_BG2`, focus ring, branch pink, and the five status-dot colors). `get_theme(name)` returns Dracula for any unknown/missing name.

Ship **4 themes** (Dracula default + 3 popular dark palettes the tmux/nvim crowd recognizes). All dark so libadwaita `FORCE_DARK` is consistent.

**Dracula (default — keep `theme.py` values verbatim):** `[VERIFIED: theme.py]`
- bg `#282a36` fg `#f8f8f2` cursor `#f8f8f2`; palette as in `theme.py` (16 colors). UI: surface `#21222c`, accent/focus `#bd93f9`, branch `#ff79c6`, dots: active `#50fa7b`, waiting `#ffb86c`, ready `#8be9fd`, idle `#7a9e7e`, hibernated `#6272a4`.

**Nord:** `[CITED: nordtheme.com/docs/colors-and-palette]`
- bg `#2e3440` fg `#d8dee9` cursor `#d8dee9`; palette (0..15): `#3b4252 #bf616a #a3be8c #ebcb8b #81a1c1 #b48ead #88c0d0 #e5e9f0 #4c566a #bf616a #a3be8c #ebcb8b #81a1c1 #b48ead #8fbcbb #eceff4`. UI: surface `#3b4252`, accent/focus `#88c0d0`, branch `#b48ead`, dots: active `#a3be8c`, waiting `#d08770`, ready `#88c0d0`, idle `#8fbcbb`, hibernated `#4c566a`.

**Solarized Dark:** `[CITED: ethanschoonover.com/solarized]`
- bg `#002b36` fg `#839496` cursor `#93a1a1`; palette: `#073642 #dc322f #859900 #b58900 #268bd2 #d33682 #2aa198 #eee8d5 #002b36 #cb4b16 #586e75 #657b83 #839496 #6c71c4 #93a1a1 #fdf6e3`. UI: surface `#073642`, accent/focus `#268bd2`, branch `#d33682`, dots: active `#859900`, waiting `#cb4b16`, ready `#2aa198`, idle `#586e75`, hibernated `#073642`.

**Gruvbox Dark:** `[CITED: github.com/morhetz/gruvbox color spec]`
- bg `#282828` fg `#ebdbb2` cursor `#ebdbb2`; palette: `#282828 #cc241d #98971a #d79921 #458588 #b16286 #689d6a #a89984 #928374 #fb4934 #b8bb26 #fabd2f #83a598 #d3869b #8ec07c #ebdbb2`. UI: surface `#3c3836`, accent/focus `#83a598`, branch `#d3869b`, dots: active `#98971a`, waiting `#fe8019`, ready `#8ec07c`, idle `#689d6a`, hibernated `#504945`.

> Confidence: Dracula HIGH (from code). The other three palettes are CITED from each project's published spec but values are training-recalled and should be sanity-checked against the linked source during planning (a wrong hex is cosmetic, not load-bearing — Pitfall 6 guards the parse).

### Switch UI placement
**Recommended: a primary menu (`Gtk.MenuButton` + `open-menu-symbolic`) on the header bar's `pack_end`, with a "Tema" submenu of radio-style entries** (one `win.set_theme(slug)` per theme). Rationale: zero new dialogs, discoverable, mirrors the existing `win.hibernate`/`win.resume` action style, and a `Adw.PreferencesDialog` is overkill for one setting in this phase. The agent command and keybindings are edited in `arduis.toml` (no GUI editor this phase — consistent with `[attention]`). A `C-Space` chord (suggest `t` then cycle, or a submenu) is optional; the menu is the primary affordance.

### tmux color tables
The VTE 16-color palettes above ARE the tmux color contract (same ANSI indices tmux/nvim use). No separate tmux config — arduis owns the palette; the user's tmux-inside-a-pane will inherit these via `TERM=xterm-256color` + the VTE palette.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `Adw.StyleManager` accent only | Custom `CssProvider` + named palettes | libadwaita 1.x | Full themes need a custom provider; StyleManager handles only dark/light + system accent |
| X11 global key grabs | Wayland: app-internal propagation only; global needs `keyboard-shortcuts-inhibit` | Wayland | arduis's prefix is app-internal → unaffected; no inhibit needed |

**Deprecated/outdated:** GTK3 `key-press-event` signal → GTK4 `EventControllerKey::key-pressed` (already migrated in `window.py`).

## Wayland App-Scoped Shortcuts (criterion 3 — the risk, resolved)

**Finding: the existing architecture already satisfies criterion 3; this is a verification, not new work.**

- `[VERIFIED: docs.gtk.org/gtk4/input-handling]` In GTK4, a key event goes to the toplevel window first (capture phase, top→down), then to the focused widget. A `Gtk.EventControllerKey` with `PropagationPhase.CAPTURE` on the window sees the key **before** the focused `Vte.Terminal`. This is the exact pattern in `window._on_key` (line ~347) and is pure intra-application event propagation.
- `[VERIFIED: wayland.app/protocols/keyboard-shortcuts-inhibit-unstable-v1]` Wayland's restriction is on intercepting the **compositor's own global shortcuts** across surfaces; the `keyboard-shortcuts-inhibit` protocol exists for apps that need to capture *compositor-reserved* combos. **arduis does not need it** — routing a key to a non-focused child *inside its own focused surface* never involves the compositor.
- `[VERIFIED: search — Mutter default shortcuts]` `C-Space` is **not** a default GNOME/Mutter global binding (those are mostly `Super`-based + `Alt-Tab`). So `C-Space` is delivered to arduis's focused surface normally on Wayland, identical to XWayland. No XWayland dependency.
- **Residual risk (LOW):** a user could have *manually* bound `Ctrl+Space` as a GNOME global shortcut (rare; the GNOME default for it is the input-source switcher on some locales). Mitigation = the configurable prefix (Pitfall 3) lets them rebind. The planner should include a manual UAT step "verify C-Space prefix arms under a native Wayland session (not XWayland)" — `echo $XDG_SESSION_TYPE` == `wayland`, `GDK_BACKEND` unset/wayland.

## Config Consolidation

Phase 4 established `~/.config/arduis/arduis.toml` with `[attention]`, read by `attention.load_config()` (tomllib, safe defaults, read-only). Phase 5 adds three sections to the SAME file:

```toml
[agent]
command = "claude"            # default; e.g. "claude --model opus" or "aider"

[keys]
prefix = "ctrl+space"         # default; "ctrl+b" to mimic tmux / avoid a collision
[keys.bindings]
# action-key char -> action name (closed set); omitted keys keep defaults
"-" = "split_v"
"=" = "split_h"
"z" = "zoom"
"a" = "refeed_agent"

[theme]
name = "dracula"              # dracula | nord | solarized-dark | gruvbox-dark
```

**Write question (theme persistence):** tomllib is read-only. Options:
1. **Runtime-only switch (no persistence)** — simplest; theme resets to `[theme] name` (or Dracula) on restart. Lightest.
2. **Targeted atomic writer** — a tiny GTK-free helper that reads the file, replaces/inserts the `[theme] name` line, and writes via tmp+`os.replace` (the project already does atomic writes for `settings.json`). No new dependency.
3. **`tomli-w`** — clean serialize, but a new runtime dependency and CLAUDE.md flags it optional.

See Open Decisions for the recommendation.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Nord/Solarized/Gruvbox hex palettes are accurate as listed | DESIGN | Cosmetic only — wrong shade; Pitfall 6 guards parse failures. Verify against cited specs in planning. |
| A2 | A configurable prefix is sufficient mitigation for C-Space collisions (no inhibit protocol needed) | Wayland, Pitfall 3 | If a user globally bound C-Space in GNOME, rebinding the prefix is the only fix — acceptable, documented. |
| A3 | `Adw.StyleManager.set_color_scheme(FORCE_DARK)` plays nicely with a custom CssProvider for all 4 dark themes | Stack/DESIGN | Adw widgets might show a wrong base under one palette; cosmetic, fixable in CSS. |
| A4 | Re-feeding the agent into the same shell (after Ctrl+C) is the desired "swap" UX vs. a kill+respawn | Pattern 1 | If product wants a hard restart, design changes — but ROADMAP explicitly says "zero re-spawn," so HIGH confidence. |

## Open Questions / Decisions (each with a recommended default — orchestrator decides)

1. **Theme persistence: runtime-only vs. atomic writer vs. tomli-w?**
   - What we know: tomllib can't write; project has an atomic-write pattern; CLAUDE.md discourages new deps.
   - **Recommended default:** **Option 2 — a tiny GTK-free atomic writer** (`appconfig.write_theme(path, name)`) that persists only `[theme] name`. It honors "switch persists" UX with zero new dependency, is unit-testable, and reuses the tmp+`os.replace` pattern. Keep it minimal (it writes one key; it need not preserve arbitrary comments — but should preserve other sections by reading-then-rewriting the parsed dict, accepting that inline comments are lost on the rewrite). If the planner wants to avoid even that, fall back to Option 1 (runtime-only) — but persistence is the better UX for a daily-driver app.

2. **Keybinding config schema: flat char→action map vs. richer chords?**
   - **Recommended default:** the **flat `[keys.bindings]` char→action-name map + a `prefix` string** shown above. It matches the existing single-char dispatch, keeps the GTK-free parser trivial, and degrades safely. Multi-key chord sequences are out of scope (the prefix grammar is already C-Space+key).

3. **Add split/zoom/refeed to `keymap.py` now, or in a Wave-0 RED test first?**
   - **Recommended default:** follow the project's TDD rhythm — a Wave-0 RED test (`tests/test_keymap.py` extension + new `tests/test_keyconfig.py`, `tests/test_themes.py`, `tests/test_agentconfig.py`) pinning the contracts, then GREEN. Matches every prior phase's wave structure.

4. **Switch UI: header primary menu vs. preferences dialog?**
   - **Recommended default:** **header primary menu with a "Tema" submenu** (Section DESIGN). No dialog this phase; agent/keys stay TOML-edited like `[attention]`.

5. **Re-feed-agent chord default key?**
   - **Recommended default:** `C-Space` then **`a`** (mnemonic: agent). Configurable via `[keys.bindings]`. The user can also just type the command at the live shell — the chord is convenience.

6. **Should `_make_terminal` read the active theme (vs. constants)?**
   - **Recommended default:** **Yes.** Route through `self._current_theme` so resumed/split terminals are born in the active theme (Pitfall 2). This is required for criterion 4 correctness.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `gir1.2-vte-3.91` (`set_colors`) | UI-02 runtime re-theme | ✓ | 0.76.0 | — (API floor confirmed) |
| GTK4 `EventControllerKey` CAPTURE | UI-01 prefix | ✓ | system | — |
| libadwaita `Adw.StyleManager`/`HeaderBar` | UI-02 menu | ✓ | system 1.x | header `Gtk.MenuButton` works without StyleManager |
| `tomllib` | config read | ✓ | stdlib 3.12 | — |
| `shlex` | AGENT-01 argv | ✓ | stdlib | — |
| `tomli-w` | (only if Option 3 persistence) | ✗ | — | hand-rolled atomic writer (Option 2) — recommended |
| Wayland session | criterion 3 UAT | (runtime) | — | XWayland equivalent; UAT must assert native Wayland |

**Missing dependencies with no fallback:** None.
**Missing dependencies with fallback:** `tomli-w` — use the hand-rolled atomic writer (no dependency).

## Validation Architecture

`nyquist_validation` is enabled (config.json `workflow.nyquist_validation: true`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `pythonpath=["src"]`, `testpaths=["tests"]`) |
| Quick run command | `pytest tests/test_themes.py tests/test_keyconfig.py tests/test_agentconfig.py -x` |
| Full suite command | `pytest` |

GTK-free modules are unit-testable directly on the host (the established pattern — `test_attention.py`, `test_keymap.py`, etc.). `window.py` (GTK) is covered by the manual UAT checklist + optional headless broadway smoke (per the dev-environment memory: `gtk4-broadwayd`).

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AGENT-01 | `agent_argv("claude --model opus")` → `["claude","--model","opus"]`; empty → `claude`; feed bytes end in `\n` | unit | `pytest tests/test_agentconfig.py -x` | ❌ Wave 0 |
| AGENT-01 | Ctrl+C → shell → re-feed re-launches without re-spawn | manual UAT | (live checklist) | ❌ Wave 0 |
| UI-01 | `resolve_keymap` merges user overrides, drops garbage (closed set); `dispatch` returns split/zoom/refeed tuples | unit | `pytest tests/test_keyconfig.py tests/test_keymap.py -x` | ⚠️ extend `test_keymap.py` + new `test_keyconfig.py` |
| UI-01 | C-Space prefix arms under native Wayland; configurable prefix rebinds | manual UAT | (live checklist, assert `$XDG_SESSION_TYPE=wayland`) | ❌ Wave 0 |
| UI-02 | `get_theme(name)` returns correct Theme / Dracula for unknown; every Theme has exactly 16 palette colors + valid hex | unit | `pytest tests/test_themes.py -x` | ❌ Wave 0 |
| UI-02 | Runtime switch re-colors all live terminals + replaces (not stacks) the CssProvider; new terminals born in active theme | manual UAT + headless smoke | (live checklist) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_themes.py tests/test_keyconfig.py tests/test_agentconfig.py -x`
- **Per wave merge:** `pytest`
- **Phase gate:** full suite green + manual UAT (live Wayland) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_themes.py` — registry shape, 16-color palette invariant, unknown→Dracula, valid-hex (UI-02)
- [ ] `tests/test_keyconfig.py` — prefix override parse, bindings merge over defaults, closed-action-set rejection (UI-01)
- [ ] `tests/test_agentconfig.py` — `[agent] command` read, shlex split, feed-bytes, empty→default (AGENT-01)
- [ ] extend `tests/test_keymap.py` — split/zoom/refeed action tuples in `dispatch`
- [ ] (if Option 2 persistence) `tests/test_appconfig.py` — atomic `[theme] name` write round-trips, preserves other sections

## Security Domain

`security_enforcement` not present in config.json (treat as enabled). This phase is local-only (no network, no auth, no crypto).

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | — |
| V5 Input Validation | yes | `shlex.split` for agent command; closed action set for `[keys]`; tolerant tomllib reads with safe defaults; theme name → `get_theme` whitelist |
| V6 Cryptography | no | — |

### Known Threat Patterns for this stack
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malicious `[agent] command` injects shell metachars | Tampering/EoP | `shlex.split` → argv list; fed as a single shell command line the user authored in their own config (trust boundary = the user's own `~/.config`), never joined from untrusted input |
| Garbage `[keys]` fabricates an unintended action | Tampering | Closed action set — unrecognized values dropped (mirrors `keymap.dispatch` → None) |
| Hostile theme name path-traversal | Tampering | `get_theme` is a dict whitelist; name is never used as a path |
| Config persistence torn write corrupts arduis.toml | DoS | Atomic tmp+`os.replace`; tolerant read with safe defaults on next launch |

Trust note: `arduis.toml` lives in the user's own `$HOME/.config` — the agent command is something the user types for themselves, so the threat model is "don't surprise the user / don't mangle args," not "untrusted remote input." `shlex` + closed sets satisfy this.

## Sources

### Primary (HIGH confidence)
- Local code: `src/arduis/session.py`, `keymap.py`, `theme.py`, `attention.py`, `spawn.py`, `window.py`, `main.py` — the existing seams
- Runtime probe (host 2026-06-13): `Vte.Terminal.set_colors/set_color_*` present at VTE 0.76.0; `tomli-w` not installed; `apt-cache policy gir1.2-vte-3.91` → 0.76.0-1ubuntu0.1
- [docs.gtk.org/gtk4/input-handling](https://docs.gtk.org/gtk4/input-handling.html) — capture-phase propagation, window-first key delivery
- [docs.gtk.org/gtk4/class.EventControllerKey](https://docs.gtk.org/gtk4/class.EventControllerKey.html) — CAPTURE phase semantics
- [wayland.app keyboard-shortcuts-inhibit-unstable-v1](https://wayland.app/protocols/keyboard-shortcuts-inhibit-unstable-v1) — confirms the protocol is for *compositor* shortcuts, not app-internal routing

### Secondary (MEDIUM confidence)
- [libadwaita Styles & Appearance](https://gnome.pages.gitlab.gnome.org/libadwaita/doc/main/styles-and-appearance.html) — StyleManager scope, CSS-variable theming
- CLAUDE.md (project) — VTE floor, app-owns-palette, shlex mandate, tomllib read-only

### Tertiary (LOW confidence — verify in planning)
- Nord / Solarized / Gruvbox palette hex values (training-recalled; cross-check against each project's published spec — A1)

## Metadata

**Confidence breakdown:**
- Agent-as-command (AGENT-01): HIGH — mechanism read directly from working code
- Configurable chords (UI-01): HIGH — table + dispatcher already GTK-free; config layer is additive
- Wayland app-scoped keys (criterion 3): HIGH — confirmed app-internal routing, not a compositor concern; verified GTK4 propagation + Wayland protocol scope
- Theme switching (UI-02): HIGH for mechanism (set_colors/CssProvider verified at 0.76), MEDIUM for non-Dracula palette hex (A1)
- Config writer choice: MEDIUM — a decision, not a fact; recommended default given

**Research date:** 2026-06-13
**Valid until:** 2026-07-13 (stable stack; VTE/GTK/libadwaita versions pinned to distro)
