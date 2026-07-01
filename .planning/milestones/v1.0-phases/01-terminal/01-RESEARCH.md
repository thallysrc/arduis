# Phase 1: Terminal - Research

**Researched:** 2026-06-08
**Domain:** GTK4 / libadwaita desktop app + embedded VTE terminal (direct native PTY) in Python/PyGObject
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Flatpak out of v1. Native packages: `.deb` (Ubuntu) + AUR (Arch), system VTE (Ubuntu 24.04 `gir1.2-vte-3.91` 0.76; Arch `vte4` 0.84). No VTE/simdutf/fast_float bundling.
- **D-02:** No sandbox → terminal spawns host `zsh` through a **direct native PTY** (no `flatpak-spawn --host`).
- **D-03:** Code targets the **VTE 0.76 API floor** so one codebase runs on Ubuntu (0.76) and Arch (0.84).
- **D-04:** A thin `HostRunner` abstraction centralizes all host execution. Native = no-op (spawns directly). Flatpak path (`flatpak-spawn --host` prefix) is **stubbed but unused** — single re-enable point for v2 (DIST-01).
- **D-05:** The terminal PTY spawn goes through `HostRunner` even though it is a no-op now — the seam must exist day one.
- **D-06:** **The app owns the terminal color palette**, not the shell. Phase 1 applies the app's palette (16 ANSI + fg/bg). Default = **Dracula**.
- **D-07:** The user's `zsh` provides behavior only (PATH, aliases, functions, prompt *text*). Prompt renders in the app's palette.
- **D-08:** Per-window/per-pane theme selection is the goal, but theme-switching UI is **Phase 5 (UI-02)**. Phase 1 hardcodes Dracula; must not depend on the shell's theme.
- **D-09:** Spawn `zsh` as **login + interactive** (`zsh -l -i`) so `.zprofile` + `.zshrc` load and `claude`/`gh`/`docker`/version-manager shims resolve.
- **D-10:** Force `TERM=xterm-256color`. Working directory = user's home for Phase 1.
- **D-11:** Ctrl+C must interrupt the running host subprocess; Ctrl+Z + `fg` job control must work. Mandatory acceptance check.
- **D-12:** Exit codes and signals decoded correctly via `os.waitstatus_to_exitcode`.
- **D-13:** On window close, send **SIGHUP to the child process group**, then **SIGKILL** after a short timeout. Native `os.killpg`. "No orphans" = no leftover host `zsh`/agent after window closes.
- **D-14:** Interactive signal/job-control/no-orphan checks = **documented manual acceptance checklist**. Exit-code/signal decoding gets a **small automated unit test**.
- **D-15:** Uncommitted draft `src/main.py` is the **starting base**, but: remove `flatpak-spawn --host` (direct `zsh -l -i`), route spawn through `HostRunner`. Flatpak manifest (`io.github.thallys.Arduis.yml`) and `dev.sh` are **obsolete** — replace with a native run/build path. Keep `data/*.desktop` / metainfo.

### Claude's Discretion
- Exact `HostRunner` API shape/signature (as long as it's the single host-exec seam, no-op native, Flatpak-stub).
- Font choice/size beyond the draft's `monospace 11`, scrollback specifics.
- Native run/build tooling for dev (replacing `dev.sh`) — Meson vs plain script.
- File/module layout for the Phase-1 app.

### Deferred Ideas (OUT OF SCOPE)
- **Flatpak channel** → v2 (DIST-01). `HostRunner` Flatpak-stub keeps this cheap to add.
- **Reattach to live agents after closing/reopening the whole app** → v2 (PERSIST-01); needs host-side tmux/abduco.
- **Same shell session mirrored across multiple panes/windows** (tmux-style multiplexing) → not in v1.
- **`CLAUDE.md` cleanup** → separate pass (tracked in STATE.md). *(NOTE: CLAUDE.md was already rewritten native-first on 2026-06-08 per recent commit 193cbdb — this deferred item is now largely resolved.)*
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TERM-01 | Usuário tem um terminal VTE embutido rodando o shell do host (zsh) dentro do app | `Vte.Terminal.spawn_async` (since 0.48, far below 0.76 floor) drives a direct native PTY; argv built by `HostRunner` → `zsh -l -i` with `TERM=xterm-256color`; `set_colors` applies the Dracula palette; `child-exited` + `os.waitstatus_to_exitcode` decodes exit; `os.killpg(SIGHUP→SIGKILL)` on window-close gives no-orphan teardown. All APIs verified present in the 0.76 floor. |
</phase_requirements>

## Summary

This phase is well-bounded and low-risk: the entire stack is standard GNOME (GTK4 + libadwaita + VTE 3.91 via PyGObject), and the previous highest-risk element — the Flatpak sandbox bridge — has been removed by the native pivot. The draft `src/main.py` is already 90% of the structure; the substantive work is (1) routing the spawn through a new `HostRunner` seam, (2) dropping the `flatpak-spawn --host` argv prefix in favor of direct `zsh -l -i`, (3) implementing no-orphan teardown on window close, and (4) decoding child exit status. [VERIFIED: local host probe + VTE GTK4 docs]

Every VTE API the phase needs exists at the **0.76 API floor** and is unchanged through 0.84, so there is no real divergence to guard against between Ubuntu and Arch for Phase 1. `spawn_async` was introduced in VTE 0.48 and is not deprecated; `set_colors`, `set_color_foreground/background/cursor`, `get_pty`, and the `child-exited` signal are all stable. [CITED: gnome.pages.gitlab.gnome.org/vte/gtk4] The one genuine environment gap: on this dev host, `gir1.2-vte-3.91` (the **GTK4** binding) is *not installed* — only the GTK3 `Vte-2.91` typelib is present. It is the apt candidate (`0.76.0-1ubuntu0.1` in `noble/main`) and must be installed before the app will import. [VERIFIED: apt-cache policy on host]

The signal/job-control/teardown behaviors that were the historical worry are now native PTY semantics: VTE allocates a real PTY and the child shell becomes the session/process-group leader on that PTY, so Ctrl+C, Ctrl+Z/`fg`, and `os.killpg` to the child's PGID all work the same as in any native terminal. These remain mandatory acceptance checks (D-11/D-13) but are no longer a research risk.

**Primary recommendation:** Evolve the existing `src/main.py` — introduce a `HostRunner` class (no-op `wrap_argv`/`wrap_env` returning input unchanged, with a stubbed `_FLATPAK` branch), drive `spawn_async` through it with `["zsh", "-l", "-i"]` and `["TERM=xterm-256color"]`, capture the child PID in the spawn callback, and wire `close-request` to `os.killpg(pgid, SIGHUP)` then `SIGKILL` on a GLib timeout. Target the VTE 0.76 API floor exactly.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | 3.12.3 (host) | App language | [VERIFIED: host probe] First-class GNOME bindings; `os.waitstatus_to_exitcode` available (3.9+) |
| PyGObject (`python3-gi`) | distro | GTK/GLib/Vte bindings | [VERIFIED: CLAUDE.md + host] Use distro package, never `pip install PyGObject` |
| GTK | 4.14.5 (host) | UI toolkit | [VERIFIED: host probe `Gtk.get_major/minor/micro` = 4.14.5] |
| libadwaita (Adw) | 1.5.0 (host) | Adaptive widgets | [VERIFIED: host probe `Adw.*_VERSION` = 1.5.0] `Adw.Application/ApplicationWindow/ToolbarView/HeaderBar` |
| VTE (GTK4, Vte-3.91) | system: Ubuntu **0.76** / Arch **0.84** | Embedded real terminal | [VERIFIED: apt-cache] Code to the 0.76 floor. **Not yet installed on dev host — see Environment Availability.** |
| `tomllib` | stdlib (3.11+) | (later phases) read `.arduis.toml` | [CITED: CLAUDE.md] Not needed in Phase 1 |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| GLib / Gio (via PyGObject) | system | Main-loop, timeouts (`GLib.timeout_add`), signals | SIGKILL-after-timeout in teardown; main-loop integration |
| `os` (stdlib) | 3.12 | `os.killpg`, `os.getpgid`, `os.waitstatus_to_exitcode`, `os.get_home_dir` equiv | Teardown + exit decode |
| `signal` (stdlib) | 3.12 | `signal.SIGHUP`, `signal.SIGKILL` | Teardown |
| `Pango` (via PyGObject) | system | `Pango.FontDescription.from_string("monospace 11")` | Terminal font (draft already uses) |
| `Gdk` (via PyGObject) | system | `Gdk.RGBA` for palette colors | Dracula palette |

### Dev / Build Tooling (Claude's discretion — D-15 replaces `dev.sh`)
| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| ruff | 0.15.9 (host) | Lint/format | [VERIFIED: host] Already installed |
| pytest | **not installed** | Unit tests (D-14) | [VERIFIED: host] `python3 -m pytest` missing — must `pip install pytest` (in a venv) or `apt install python3-pytest`. Wave 0 gap. |
| mypy + PyGObject-stubs | **not installed** | Type-check | [VERIFIED: host] Optional for Phase 1; install if typing the seam |
| meson + ninja | **not installed** | Packaging layout | [VERIFIED: host] Optional; a plain `run.sh` is sufficient for Phase 1 dev loop. Recommend a 1-line wrapper (`exec python3 -m arduis` or `python3 src/main.py`) over Meson for this phase. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `spawn_async` | `spawn_with_fds_async` | [CITED: vte/gtk4 docs] Only needed to pass extra FDs to the child; Phase 1 needs none → use the simpler `spawn_async`. |
| direct `zsh -l -i` argv | `Vte.Pty.new_sync` + manual fork | Hand-rolling the PTY; VTE already owns it. Never do this (CLAUDE.md "What NOT to Use"). |
| plain `run.sh` | meson + ninja | Meson pays off at packaging (Phase 9), not Phase 1. [ASSUMED] |

**Installation (dev host — blocking for this phase):**
```bash
sudo apt install gir1.2-vte-3.91 libvte-2.91-gtk4-0   # GTK4 VTE binding + runtime (0.76)
pip install pytest                                      # for the unit test (D-14); use a venv
```

**Version verification (done this session):**
- `gir1.2-vte-3.91`: candidate `0.76.0-1ubuntu0.1` in `noble/main`, **Installed: (none)** [VERIFIED: apt-cache policy]
- Arch `vte4`: `0.84.0-1` in `extra` [CITED: archlinux.org/packages/extra/x86_64/vte4]
- GTK 4.14.5, Adw 1.5.0, Python 3.12.3, zsh 5.9 [VERIFIED: host probe]

## Architecture Patterns

### Recommended Project Structure (Claude's discretion — D-15)
```
src/
└── arduis/
    ├── __init__.py
    ├── main.py          # Adw.Application entry (do_activate), main()
    ├── window.py        # ArduisWindow (Adw.ApplicationWindow) + VTE wiring + teardown
    ├── host_runner.py   # HostRunner seam (no-op native, Flatpak stub)
    └── theme.py         # Dracula palette constants + Gdk.RGBA helpers
tests/
    ├── test_host_runner.py   # no-op wrap_argv/wrap_env identity
    └── test_exit_decode.py   # os.waitstatus_to_exitcode mapping
run.sh                         # replaces dev.sh: exec python3 src/main.py (or -m arduis)
```
*(A single-file `src/main.py` evolution is also acceptable for this small phase; the split above isolates the testable seams from GTK code so unit tests don't import GTK.)* [ASSUMED — layout is discretion per D-15]

### Pattern 1: HostRunner seam (no-op native, Flatpak stub) — D-04/D-05
**What:** One abstraction every host-exec call funnels through. Native build returns argv/env unchanged; the Flatpak branch (prepend `flatpak-spawn --host`) exists but is unreachable in v1.
**When to use:** For the VTE spawn now; for all git/gh/docker shell-outs later.
**Example:**
```python
# src/arduis/host_runner.py
# Native build: wrap_argv/wrap_env are identity. The Flatpak path is stubbed for v2 (DIST-01).
from __future__ import annotations

_FLATPAK = False  # v1 is native-only. Flipping this is the single v2 re-enable point.

class HostRunner:
    """Single seam for executing host commands. No-op on native builds."""

    def wrap_argv(self, argv: list[str]) -> list[str]:
        if _FLATPAK:
            # v2 (DIST-01): return ["/usr/bin/flatpak-spawn", "--host", *argv]
            raise NotImplementedError("Flatpak channel is v2 (DIST-01)")
        return list(argv)

    def wrap_env(self, env: list[str]) -> list[str]:
        if _FLATPAK:
            # v2: prepend --env=K=V flags before the command instead
            raise NotImplementedError("Flatpak channel is v2 (DIST-01)")
        return list(env)
```
*(`env` is a list of `"KEY=VALUE"` strings to match VTE's `envv` parameter convention.)*

### Pattern 2: VTE spawn through the seam — D-02/D-09/D-10
**What:** Direct native PTY to `zsh -l -i`, argv built by `HostRunner`, `TERM` forced, working dir = home.
**Example (PyGObject 0.76-floor call shape):**
```python
# Source: api.pygobject.gnome.org/Vte-3.91 + gnome.pages.gitlab.gnome.org/vte/gtk4
# PyGObject DROPS the C trailing args child_setup_data_destroy + user_data.
runner = HostRunner()
argv = runner.wrap_argv(["zsh", "-l", "-i"])          # login + interactive
envv = runner.wrap_env(["TERM=xterm-256color"])        # merged onto inherited env

self.terminal.spawn_async(
    Vte.PtyFlags.DEFAULT,
    GLib.get_home_dir(),        # working_directory
    argv,                       # argv (list[str], null-term handled by binding)
    envv,                       # envv (list[str] of KEY=VALUE; merged with parent env)
    GLib.SpawnFlags.DEFAULT,
    None,                       # child_setup (callable | None)
    None,                       # child_setup_data
    -1,                         # timeout (-1 = no timeout)
    None,                       # cancellable (Gio.Cancellable | None)
    self._on_spawned,           # callback: (terminal, pid, error) -> None
)

def _on_spawned(self, terminal, pid, error):
    if error is not None or pid == -1:
        # surface error; do not store a bad pid
        return
    self._child_pid = pid       # captured for no-orphan teardown
```
**0.76-floor notes:**
- `spawn_async` exists since VTE **0.48** — safely below the floor; not deprecated. [CITED: vte/gtk4 method.Terminal.spawn_async]
- The callback gets `(terminal, pid, error)` — `pid == -1` and non-NULL `error` on failure. [VERIFIED: gtkd/valadoc cross-ref of `VteTerminalSpawnAsyncCallback`]
- `GLib.get_home_dir()` is correct for working dir (D-10).

### Pattern 3: App owns the palette — D-06/D-07
**What:** Apply 16 ANSI + fg/bg via `set_colors` before/after spawn; never let the shell choose colors.
**Example (already in draft, confirmed correct for 0.76):**
```python
# Source: api.pygobject.gnome.org/Vte-3.91 class-Terminal
# Python set_colors signature (binding): set_colors(foreground=None, background=None, palette=None)
self.terminal.set_colors(
    _rgba(DRACULA_FG),
    _rgba(DRACULA_BG),
    [_rgba(c) for c in DRACULA_PALETTE],   # len must be 0, 8, 16, 232, or 256 — Dracula = 16
)
# Optional refinements available at the 0.76 floor:
self.terminal.set_color_cursor(_rgba("#f8f8f2"))   # set_color_cursor(cursor_background=None)
```
**Palette-size constraint:** `palette_size` must be one of `0, 8, 16, 232, 256`. The Dracula list in the draft is exactly 16 → valid. [CITED: vte/gtk4 set_colors]

### Pattern 4: No-orphan teardown — D-13
**What:** On `close-request`, SIGHUP the child's process group, then SIGKILL after a short GLib timeout.
**Why a process group:** VTE allocates a real PTY and the child shell becomes its own session leader (new session + process group via the PTY's `login_tty` semantics), so the shell's PID *is* the PGID, and signalling the group reaches the shell **and** any agent/jobs it launched. [ASSUMED — standard PTY/`login_tty` session semantics; verify the PGID at runtime with `os.getpgid(pid)` rather than assuming `pgid == pid`]
**Example:**
```python
import os, signal
from gi.repository import GLib

def _on_close_request(self, *_):
    pid = getattr(self, "_child_pid", None)
    if pid:
        try:
            pgid = os.getpgid(pid)          # robust: don't assume pgid == pid
            os.killpg(pgid, signal.SIGHUP)
            GLib.timeout_add(1500, self._sigkill_if_alive, pgid)
        except ProcessLookupError:
            pass                            # already gone
    return False                            # allow the window to close

def _sigkill_if_alive(self, pgid):
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return GLib.SOURCE_REMOVE
```
*(Connect via `self.connect("close-request", self._on_close_request)`. In GTK4 the window signal is `close-request`, not GTK3's `delete-event`.)* [ASSUMED — GTK4 signal name; HIGH confidence, standard GTK4]

### Pattern 5: Child-exit decode — D-12
```python
import os
def _on_child_exited(self, terminal, status):
    # VTE passes the RAW wait status (as from waitpid), not a pre-decoded exit code.
    code = os.waitstatus_to_exitcode(status)
    # code >= 0  -> normal exit code
    # code < 0   -> killed by signal (-signum)
    self.close()   # draft behaviour: close window when shell exits
```
[CITED: vte/gtk4 signal child-exited "the child's exit status"; the value is the raw waitpid status — decode with `os.waitstatus_to_exitcode`, added Python 3.9]

### Anti-Patterns to Avoid
- **`flatpak-spawn --host` argv prefix:** No sandbox in v1 — remove it (D-02/D-15). Use `HostRunner`.
- **Calling VTE APIs newer than 0.76:** breaks Ubuntu 24.04. Target the 0.76 floor (D-03). (For Phase 1, none of the needed APIs are post-0.76.)
- **Assuming `pgid == pid`:** call `os.getpgid(pid)` instead of signalling `pid` directly.
- **Hand-rolling a PTY layer:** VTE owns the PTY. Never `pty.fork`/`Vte.Pty.new` + manual setup.
- **`pip install PyGObject`:** conflicts with distro bindings. Use system `python3-gi`.
- **Blocking the GTK main loop:** Phase 1 has no long shell-outs, but keep the habit — use `GLib.timeout_add`, not `time.sleep`.
- **Letting the shell own colors:** apply `set_colors` and don't pass color env that overrides the palette (D-06/D-07).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| PTY allocation + master/slave wiring | `pty.openpty` + fork + `login_tty` | `Vte.Terminal.spawn_async` | VTE allocates the PTY, handles resize/scrollback/colors/cursor; reimplementing is the whole "don't build a terminal emulator" out-of-scope item |
| Terminal rendering / escape parsing | custom widget | `Vte.Terminal` | VTE is the GNOME Terminal engine |
| Exit-status decoding | manual `WIFEXITED`/`WEXITSTATUS` bit math | `os.waitstatus_to_exitcode` | One stdlib call covers normal + signal cases (3.9+) |
| Process-group teardown | tracking every child PID | `os.killpg` on the shell's PGID | The PTY session groups the shell + its jobs; one group signal reaches all |
| TOML (later) | regex parsing | `tomllib` | stdlib, read-only is enough |

**Key insight:** Phase 1's job is to *wire up* VTE correctly, not to build any terminal machinery. Almost everything is a stdlib or VTE one-liner; the only bespoke code is the tiny `HostRunner` seam and the teardown timer.

## Common Pitfalls

### Pitfall 1: GTK4 VTE binding not installed (only GTK3 present)
**What goes wrong:** `gi.require_version("Vte", "3.91")` raises `ValueError: Namespace Vte not available for version 3.91` — the host has only `Vte-2.91.typelib` (GTK3). [VERIFIED: host import failed exactly this way]
**Why:** `gir1.2-vte-3.91` (GTK4) is the apt *candidate* but not installed; `gir1.2-vte-2.91` (GTK3) is.
**How to avoid:** `sudo apt install gir1.2-vte-3.91 libvte-2.91-gtk4-0` as a documented prerequisite (and a packaging dependency for Phase 9).
**Warning signs:** Import error on `require_version`; `ls /usr/lib/x86_64-linux-gnu/girepository-1.0/ | grep -i vte` shows only `Vte-2.91`.

### Pitfall 2: PyGObject `spawn_async` arg count differs from C docs
**What goes wrong:** Copying the 13-arg C signature into Python (including `child_setup_data_destroy` and `user_data`) raises a `TypeError`.
**Why:** PyGObject drops the destroy-notify and trailing `user_data`; the callback is `(terminal, pid, error)`. There is even a known Debian doc bug about the wrong argument list. [CITED: Debian bug #996084; api.pygobject.gnome.org]
**How to avoid:** Use the exact Python call shape in Pattern 2 (11 positional args ending at the callback).
**Warning signs:** `TypeError: ... takes N arguments` at spawn.

### Pitfall 3: `child-exited` status is raw, not a clean exit code
**What goes wrong:** Treating `status` as an exit code reports wrong values for signal-killed children (e.g. Ctrl+C exit looks like 130 only after decode).
**Why:** VTE forwards the raw `waitpid` status. [CITED: vte/gtk4 child-exited]
**How to avoid:** Always `os.waitstatus_to_exitcode(status)` (D-12). Negative result = `-signum`.

### Pitfall 4: Login+interactive zsh needed for shims
**What goes wrong:** Spawning bare `zsh` (no `-l -i`) skips `.zprofile`/`.zshrc`, so `claude`/`gh`/`docker`/asdf/nvm/pyenv shims don't resolve → Success Criterion #2 fails.
**Why:** PATH and version-manager shims are installed by login + interactive rc files.
**How to avoid:** argv `["zsh", "-l", "-i"]` (D-09). [CITED: CLAUDE.md HostRunner seam section]
**Warning signs:** `command not found: claude` inside the embedded terminal but it works in a normal terminal.

### Pitfall 5: GTK4 window-close signal name
**What goes wrong:** Connecting `delete-event` (GTK3) silently never fires → teardown never runs → orphans.
**Why:** GTK4 renamed it to `close-request`. [ASSUMED — standard GTK4 migration; HIGH confidence]
**How to avoid:** `self.connect("close-request", ...)` and return `False` to allow close.

### Pitfall 6: Dev session is X11, acceptance bar says Wayland
**What goes wrong:** Manual acceptance "runs under real Wayland" can't be checked in the current dev session (`XDG_SESSION_TYPE=x11`). [VERIFIED: host env]
**Why:** Dev box is logged into X11.
**How to avoid:** Note in the acceptance checklist that the Wayland check (Success Criterion #5) requires a Wayland login session (or `GDK_BACKEND=wayland` under a nested compositor). Functionally VTE/GTK4 behave the same; this is a checklist-coverage caveat, not a code issue.

## Code Examples

### Minimal GTK4 + libadwaita + VTE skeleton (0.76-floor)
```python
# Source: api.pygobject.gnome.org/Vte-3.91 + existing src/main.py (draft)
import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")          # GTK4 binding — needs gir1.2-vte-3.91 installed
from gi.repository import Adw, Gdk, GLib, Gtk, Pango, Vte

class ArduisWindow(Adw.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="arduis"))
        view.add_top_bar(header)
        self.terminal = Vte.Terminal()
        # ... set_colors / set_font / spawn via HostRunner ...
        view.set_content(self.terminal)
        self.set_content(view)
        self.connect("close-request", self._on_close_request)

class ArduisApp(Adw.Application):
    def do_activate(self):
        win = self.props.active_window or ArduisWindow(application=self)
        win.present()
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flatpak + `flatpak-spawn --host` bridge | Native `.deb`/AUR + direct PTY | 2026-06-08 pivot | Removes sandbox risk class; one code path |
| Bundle/compile VTE (+ simdutf, fast_float) | System `vte4`/`gir1.2-vte-3.91` | 2026-06-08 | No build of VTE; fast_float/simdutf pins irrelevant |
| `spawn_sync` (GTK3 era) | `spawn_async` (since 0.48) | long ago | Use async; `spawn_sync` is the old path |

**Deprecated/outdated:**
- The draft's `_spawn_host_shell` `flatpak-spawn --host` prefix — remove (D-15).
- `dev.sh` (flatpak-builder loop) and `io.github.thallys.Arduis.yml` (Flatpak manifest) — obsolete; replace with a native run path.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | VTE spawns the child as its own session/process-group leader so `pgid == pid` (mitigated by calling `os.getpgid`) | Pattern 4 / Don't Hand-Roll | Low — code uses `os.getpgid(pid)` so it's correct regardless; only the "one killpg reaches all jobs" reasoning depends on it. Verify in acceptance test. |
| A2 | GTK4 window close signal is `close-request` (not `delete-event`) | Pattern 4 / Pitfall 5 | Medium if wrong — teardown never fires → orphans. HIGH confidence it's correct (standard GTK4). Verify by observing teardown runs on close. |
| A3 | Project module layout (split files) | Architecture Patterns | None — explicitly Claude's discretion (D-15). |
| A4 | Plain `run.sh` over Meson for Phase 1 dev loop | Standard Stack / Architecture | None — discretion (D-15); Meson can be added at Phase 9. |
| A5 | `child-exited` carries raw waitpid status | Pattern 5 / Pitfall 3 | Low — VTE docs say "child's exit status"; raw-status behaviour is long-standing. `os.waitstatus_to_exitcode` is the right decoder either way for raw status. Confirm in unit test with a known signal. |

## Open Questions

1. **Does VTE pass a raw waitpid status or pre-decoded code to `child-exited`?**
   - What we know: docs say "the child's exit status"; VTE historically forwards the raw status.
   - What's unclear: docs don't state the encoding explicitly.
   - Recommendation: write the unit test (D-14) to spawn a process that exits 0, exits 42, and is killed by SIGINT, and assert `os.waitstatus_to_exitcode` returns `0`, `42`, `-2`. If VTE ever pre-decodes, the test catches it immediately. (Note: the unit test can decode statuses produced by `os.system`/`subprocess` directly without GTK — see Validation Architecture.)

2. **Exact PGID relationship of the VTE child.**
   - What we know: VTE uses a PTY; the child becomes a session leader.
   - What's unclear: whether any intermediate process changes the group.
   - Recommendation: use `os.getpgid(pid)` (already in Pattern 4) — correct regardless. Acceptance checklist verifies "no orphans" empirically (`pgrep -P` / `ps` after close).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.12 | App runtime | ✓ | 3.12.3 | — |
| GTK 4 | UI | ✓ | 4.14.5 | — |
| libadwaita (Adw 1) | UI | ✓ | 1.5.0 | — |
| PyGObject (`python3-gi`) | bindings | ✓ | distro | — |
| **VTE GTK4 (`gir1.2-vte-3.91`)** | embedded terminal | **✗** | candidate 0.76.0-1ubuntu0.1 | none — must install |
| `libvte-2.91-gtk4-0` (runtime lib) | VTE GTK4 | **✗** | candidate 0.76.0-1ubuntu0.1 | none — must install |
| zsh | host shell to spawn | ✓ | 5.9 | — |
| ruff | lint | ✓ | 0.15.9 | — |
| **pytest** | unit tests (D-14) | **✗** | — | `apt install python3-pytest` or venv `pip install pytest` |
| mypy + PyGObject-stubs | type-check | ✗ | — | optional for Phase 1; skip |
| meson / ninja | packaging | ✗ | — | plain `run.sh` (discretion D-15) |
| Wayland session | acceptance criterion #5 | ✗ (X11 now) | — | log into Wayland session / nested compositor for the check |

**Missing dependencies with no fallback (BLOCKING — planner must include install steps):**
- `gir1.2-vte-3.91` + `libvte-2.91-gtk4-0` — the app cannot import VTE without these. `sudo apt install gir1.2-vte-3.91 libvte-2.91-gtk4-0`.

**Missing dependencies with fallback:**
- `pytest` — install via apt or venv before running the unit test.
- Wayland session — switch session (or accept the X11 functional check + a note) for criterion #5.
- meson/ninja — not needed; use a plain run script.

## Validation Architecture

> nyquist_validation = true in config → section included.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (NOT YET INSTALLED — Wave 0) |
| Config file | none — add `pyproject.toml [tool.pytest.ini_options]` or `pytest.ini` in Wave 0 |
| Quick run command | `python3 -m pytest tests/ -x -q` |
| Full suite command | `python3 -m pytest tests/ -v` |

**Design constraint:** keep `HostRunner`, the Dracula palette mapping, and exit-decode logic in **GTK-free modules** so unit tests import them without `gi`/GTK. Anything that touches `Vte.Terminal`/`Adw.*` directly is manual-acceptance only (rendering, Wayland, interactive signals).

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TERM-01 | `os.waitstatus_to_exitcode` decodes exit 0 / exit 42 / SIGINT correctly (D-12) | unit | `pytest tests/test_exit_decode.py -x` | ❌ Wave 0 |
| TERM-01 | `HostRunner.wrap_argv`/`wrap_env` are identity on native (D-04) | unit | `pytest tests/test_host_runner.py::test_native_noop -x` | ❌ Wave 0 |
| TERM-01 | `HostRunner` Flatpak branch is stubbed/unreachable in v1 (D-04) | unit | `pytest tests/test_host_runner.py::test_flatpak_stub -x` | ❌ Wave 0 |
| TERM-01 | Spawn argv assembled as `["zsh","-l","-i"]` + `TERM=xterm-256color` (D-09/D-10) | unit | `pytest tests/test_spawn_argv.py -x` | ❌ Wave 0 |
| TERM-01 | Dracula palette maps to 16 `Gdk.RGBA` entries (valid `set_colors` size) (D-06) | unit | `pytest tests/test_theme.py -x` | ❌ Wave 0 |
| TERM-01 | Working shell renders host zsh w/ user prompt in Dracula (criterion #1) | manual | acceptance checklist | n/a |
| TERM-01 | `claude`/`gh`/`docker` resolve in embedded terminal (criterion #2) | manual | acceptance checklist | n/a |
| TERM-01 | Ctrl+C interrupts; Ctrl+Z + `fg` job control (criterion #3, D-11) | manual | acceptance checklist | n/a |
| TERM-01 | Closing window kills shell, no orphans (criterion #4, D-13) | manual | acceptance checklist (`ps`/`pgrep` after close) | n/a |
| TERM-01 | Runs under real Wayland on Ubuntu 0.76 + Arch 0.84 (criterion #5) | manual | acceptance checklist | n/a |

### Sampling Rate
- **Per task commit:** `python3 -m pytest tests/ -x -q`
- **Per wave merge:** `python3 -m pytest tests/ -v`
- **Phase gate:** full suite green AND the manual acceptance checklist completed (D-14) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] Install pytest: `apt install python3-pytest` or venv `pip install pytest`
- [ ] Install GTK4 VTE: `sudo apt install gir1.2-vte-3.91 libvte-2.91-gtk4-0` (also unblocks running the app at all)
- [ ] `tests/test_exit_decode.py` — covers TERM-01 exit/signal decode
- [ ] `tests/test_host_runner.py` — native no-op + Flatpak-stub
- [ ] `tests/test_spawn_argv.py` — argv/env assembly (requires extracting argv building into a GTK-free helper)
- [ ] `tests/test_theme.py` — Dracula palette → 16 RGBA
- [ ] `pyproject.toml`/`pytest.ini` — pytest config + test discovery path
- [ ] A written **manual acceptance checklist** doc (D-14) for criteria #1–#5

## Sources

### Primary (HIGH confidence)
- Local host probe (2026-06-08): Python 3.12.3, GTK 4.14.5, Adw 1.5.0, zsh 5.9, ruff 0.15.9; `Vte-3.91` import fails (only `Vte-2.91` typelib); `apt-cache policy gir1.2-vte-3.91` → candidate 0.76.0-1ubuntu0.1, not installed; `XDG_SESSION_TYPE=x11`.
- [VTE GTK4 Terminal.spawn_async](https://gnome.pages.gitlab.gnome.org/vte/gtk4/method.Terminal.spawn_async.html) — signature, since 0.48, not deprecated
- [VTE GTK4 Terminal.set_colors](https://gnome.pages.gitlab.gnome.org/vte/gtk4/method.Terminal.set_colors.html) — signature, palette_size {0,8,16,232,256}
- [VTE GTK4 child-exited signal](https://gnome.pages.gitlab.gnome.org/vte/gtk4/signal.Terminal.child-exited.html) — "child's exit status"
- [PyGObject Vte-3.91 Terminal](https://api.pygobject.gnome.org/Vte-3.91/class-Terminal.html) — Python signatures: `set_colors(foreground, background, palette)`, `set_color_cursor`, `do_child_exited(self, status: int)`, `get_pty`
- [Arch vte4 0.84.0-1](https://archlinux.org/packages/extra/x86_64/vte4/) — Arch system VTE version
- CLAUDE.md (project) — locked stack, HostRunner seam, packaging, "What NOT to Use"

### Secondary (MEDIUM confidence)
- [Debian bug #996084 — spawn_async wrong arg list in docs](https://www.mail-archive.com/debian-bugs-dist@lists.debian.org/msg1823456.html) — confirms doc/binding arg mismatch
- [gtkd VteTerminalSpawnAsyncCallback](https://api.gtkd.org/vte.Terminal.Terminal.spawnAsync.html) — callback `(terminal, pid, error, user_data)`; pid -1 on failure

### Tertiary (LOW confidence — verify in acceptance/unit tests)
- PTY session-leader / PGID reasoning (A1): standard `login_tty` semantics, mitigated by `os.getpgid` in code

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified on host + apt + Arch package page
- Architecture (spawn/colors/exit/teardown): HIGH — APIs verified against VTE GTK4 + PyGObject docs; all at/below 0.76 floor
- HostRunner seam shape: HIGH (design) — straightforward; exact API is Claude's discretion
- Pitfalls: HIGH — Pitfall 1 reproduced live on host; others cited
- PGID/session-leader detail (A1): MEDIUM — mitigated by `os.getpgid`, confirmed empirically in acceptance

**Research date:** 2026-06-08
**Valid until:** ~2026-07-08 (stable system stack; VTE 0.76/0.84 are released)
