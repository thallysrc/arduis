<!-- GSD:project-start source:PROJECT.md -->
## Project

**arduis**

arduis é um app desktop GNOME **lightweight** (Linux: Ubuntu + Arch) que orquestra
**vários agentes de IA (Claude Code) em paralelo** — cada um na sua **git worktree**, com
**terminais reais embutidos (VTE)**. É a resposta Linux e terminal-cêntrica ao
BridgeMind/BridgeSpace (que só existe no Mac). Para devs que vivem no terminal/tmux e usam
agentes de IA intensamente; usável solo e **instalável facilmente por um time** (pacotes
nativos `.deb` + AUR).

**Core Value:** Tirar a ideia "quero começar uma branch nova" e ter um **agente de IA rodando numa worktree
isolada em segundos** — gerenciando N agentes em paralelo e **sempre sabendo qual deles te
espera**.

### Constraints

- **Plataforma**: Linux + GNOME, **Ubuntu E Arch** — regra inegociável
- **Tech stack**: Python + PyGObject + GTK4 + libadwaita + VTE (Vte-3.91); config TOML; shell-out para git/gh/docker compose
- **Distribuição**: **nativa** — `.deb` (Ubuntu) + AUR (Arch), usando o VTE do sistema; Flatpak fora do v1; Snap não
- **UX**: centrado no terminal; respeita keybindings estilo tmux
- **Performance/Memória**: lightweight, com **gestão de RAM de primeira classe**
- **Método**: Accelerate/DORA — degraus pequenos, instaláveis e usáveis; trunk-based; entrega contínua; `main` sempre funcionando; dogfooding cedo
- **Escopo**: credenciais/Jira fora; só leitura de git/gh
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

> **Distribution pivot (2026-06-08): native, not Flatpak.** arduis ships as native packages —
> `.deb` (Ubuntu) + AUR (Arch) — using the **system VTE**. There is **no Flatpak sandbox in
> v1**, therefore **no `flatpak-spawn --host`**: the embedded terminal spawns the host `zsh`
> through a **direct native PTY** (like BridgeMind on Mac). All host execution still funnels
> through a thin `HostRunner` seam that is a **no-op** on native builds and keeps a single
> stubbed place to re-add an optional Flatpak channel in v2 (DIST-01). Flatpak is deferred to
> v2; the bundled-VTE / simdutf / fast_float machinery is **not used**.

## Confirmed Decisions
| Decision | Verdict | Note |
|----------|---------|------|
| Python + PyGObject + GTK4 + libadwaita | **CONFIRMED — sound** | Standard GNOME app stack; available natively on Ubuntu + Arch |
| VTE for GTK4 (Vte-3.91), **from the system** | **CONFIRMED** | Ubuntu 24.04 `gir1.2-vte-3.91` **0.76** in `main` (verified); Arch `vte4` **0.84** in `extra`. **Code to the 0.76 API floor.** |
| **Native packaging (.deb + AUR), Flatpak out of v1** | **CONFIRMED — 2026-06-08** | Removes the sandbox and the entire `flatpak-spawn --host` risk class. One code path, two thin packages. |
| Direct PTY via `Vte.Terminal.spawn_async` (no bridge) | **CONFIRMED** | No sandbox → spawn host `zsh` directly. `HostRunner` is the seam (no-op native). |
| TOML via `tomllib` (stdlib) | **CONFIRMED — correct for read** | `tomllib` is read-only (Python 3.11+); you only read `.arduis.toml`, so stdlib is enough. |
| Shell-out to git/gh/docker compose | **CONFIRMED — correct** | No mature, maintained Python libs worth the dependency cost here |
| Snap | **REJECTED** | Confinement is hostile to a docker/git-driving tool |

## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Notes |
|------------|---------|---------|-------|
| Python | 3.12 | App language | Fast prototyping, minimal deps, first-class GNOME bindings; RAM bottleneck is agents/containers, not the GUI — confirms the "don't rewrite in Rust" decision |
| PyGObject | system (`python3-gi` / `python-gobject`) | GTK/GLib/Vte bindings | Use the **distro** PyGObject, not `pip install`. |
| GTK | 4.x | UI toolkit | Native GNOME on both Ubuntu and Arch |
| libadwaita | 1.x | Adaptive widgets/styling | `Adw.ApplicationWindow`, `Adw.ToolbarView`, `Adw.HeaderBar` already used in draft `main.py` |
| VTE (GTK4) | **system** (Ubuntu 0.76 / Arch 0.84), Vte-3.91 | Embedded real terminal | Same engine as GNOME Terminal; `gi.require_version("Vte", "3.91")` is correct. **From the system package — not compiled/bundled.** Target the 0.76 API floor. |
| TOML parsing | `tomllib` (stdlib, 3.11+) | Read `.arduis.toml` | Zero dependency; read-only is fine because the schema is hand-edited |

### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| GLib / Gio (via PyGObject) | system | Async subprocess, main-loop integration, signals | **Primary concurrency tool.** Use `Gio.Subprocess` + the GLib main loop for non-PTY child processes (`git`, `gh`, `docker compose`); never block the GTK main loop. |
| Vte.Pty / `Vte.Terminal.spawn_async` | system | PTY-backed long-lived processes (the shell/agents) | The terminals ARE the PTY-backed processes — VTE owns the PTY. No separate `pty`/`asyncio` PTY layer, and **no `flatpak-spawn` prefix** — spawn the host command directly. |
| `tomli-w` (optional) | 1.x | Writing TOML if you ever generate `.arduis.toml` | Only if arduis writes config back. `tomllib` cannot write. Keep optional. |
| Python `subprocess` (stdlib) | 3.12 | Simple synchronous/quick host queries | For short read-only calls (`git rev-parse`, `gh pr view --json`) where blocking briefly is acceptable; prefer `Gio.Subprocess` for anything longer. |
| `shlex` (stdlib) | 3.12 | Safe argv construction | Build argv **lists**, never shell strings, when constructing host commands. |

### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| meson + ninja (optional) | Packaging / install layout | Standard for a GNOME Python app; or a plain install script for v1 |
| pytest | Test runner | Unit tests run directly on the host (e.g. exit-code/signal decoding); no sandbox |
| pytest-xvfb / `dbus-run-session` / Mutter `--headless` | Headless GUI tests | Use when asserting on real GTK rendering/input; otherwise keep GUI checks as a manual acceptance checklist |
| ruff + mypy + PyGObject-stubs | Lint/type-check | `PyGObject-stubs` gives typing for `gi.repository.*` |

## The HostRunner Seam (load-bearing detail)
- **All host execution funnels through one `HostRunner` abstraction.** On native builds it is a
  **no-op** — it spawns the command directly (the host *is* the environment). It exists from day
  one so that (a) there is a single place to add the optional v2 Flatpak path (prepend
  `flatpak-spawn --host`), and (b) it is the future reattach point.
- **Terminal spawn:** `Vte.Terminal.spawn_async` with argv built by `HostRunner` → `zsh -l -i`
  (login + interactive, so `.zprofile`/`.zshrc` load and `claude`/`gh`/version-manager shims
  resolve). Force `TERM=xterm-256color`.
- **The app owns the terminal palette** (Dracula default), not the shell. The shell provides
  PATH/aliases/functions/prompt text; colors come from arduis. Per-window theme switching is
  Phase 5 (UI-02).
- **Signals / job control / exit status are native now.** Ctrl+C interrupts the child, Ctrl+Z +
  `fg` work, and `os.waitstatus_to_exitcode` decodes results — no sandbox boundary to cross.
  Still verify them (they are Phase 1 acceptance criteria).
- **Teardown on window close:** `os.killpg` SIGHUP to the child process group, then SIGKILL after
  a short timeout. No `flatpak-spawn` indirection — a normal kill. "No orphans" is the bar.

## Subprocess / Process-Management Patterns
| Need | Recommended approach | Why |
|------|---------------------|-----|
| Terminals (long-lived PTY) | `Vte.Terminal.spawn_async`, argv via `HostRunner` (direct `zsh -l -i`) | VTE owns the PTY, handles resize/scrollback/colors; you do not hand-roll a PTY layer |
| Short read-only host queries (`git`, `gh --json`) | `Gio.Subprocess` + `communicate_utf8_async` on the GLib main loop | Non-blocking, integrates with GTK loop, no threads needed |
| Many parallel long-running non-PTY jobs (setup commands, `docker compose up -d`) | `Gio.Subprocess` async, track by handle | Async-first; reserve Python `asyncio` only if genuinely needed (GLib loop already gives concurrency) |
| State detection ("who's waiting on me") | Claude Code hooks (Phase 4, primary) + VTE OSC 133 / `contents-changed` (secondary) | See below |

- **Attention detection is HOOKS-FIRST** (Phase 4): Claude Code `Notification`/`Stop` hooks write
  per-worktree state files arduis watches. VTE **OSC 133 semantic prompt** + `contents-changed`
  are the secondary signal; raw text-scraping is the fragile fallback (Claude Code's TUI repaints
  heavily) and is deferred to v2 for non-Claude agents (STATUS-04).
- VTE emits `contents-changed` (and cursor/notification signals) you can hook from Python.

## Docker Compose Orchestration (Phase 7)

> **Re-anchored 2026-06-10 (Phase 03.2):** the isolation unit is the **TASK** (a set of worktrees
> across the project's repos), not a single worktree. The compose base is **ONE
> `docker-compose.yml` at the project ROOT** (multi-repo meta-repo) covering all member services —
> one shared network (service discovery by name) and atomic whole-stack duplication. Per-repo
> compose files were explicitly rejected.

- Docker runs **on the host directly** (native build → no sandbox, no socket permission hole).
  Compose orchestration is "build argv → run `docker compose ...` via `HostRunner`".
- **Isolation via `COMPOSE_PROJECT_NAME`** — a unique project name per TASK gives separate
  container names, networks, and volumes (an isolated DB per task for free). Pass it as an env var.
- **Override files** — `docker compose -f docker-compose.yml -f docker-compose.override.yml ...`
  merges, override wins; arrays like `ports` are *combined* not replaced. To remap a port, override
  the **whole** service's `ports` list. Generate the override with the offset-applied port list.
- **Base from `main`** — read the root compose file from the meta-repo's `main`; generate the
  override into the **task folder** (which mirrors the root layout — worktrees keep the repo dir
  names — so relative build contexts/bind mounts resolve verbatim).
- **Port offset** — auto-assign with a per-task offset (config `port_offset = 1000`) but **probe
  for free ports** before committing; persist the chosen ports per task so badges/URLs stay stable.
- **Teardown** — `docker compose -p <name> down -v` on task conclude/hibernate; wire into both
  "conclude task" and app-exit handlers (first-class RAM requirement).
- **No Python docker library** — skip `docker` PyPI SDK / `python-on-whales`; shell `docker compose` via `HostRunner`.

## Packaging (Phase 9) — native only in v1
| Channel | Approach | Notes |
|---------|----------|-------|
| AUR (Arch) | `PKGBUILD` depending on system `vte4` (0.84, `extra`), `python-gobject`, `gtk4`, `libadwaita` | No sandbox, no `flatpak-spawn` — runs commands directly. Follow ArchWiki Meson/Python guidelines. |
| .deb (Ubuntu) | debhelper package depending on `gir1.2-vte-3.91`/`libvte-2.91-gtk4-0` (**0.76 in `main`, verified**), `python3-gi`, `gir1.2-gtk-4.0`, `libadwaita` | GTK4-VTE confirmed present on Ubuntu 24.04 — no PPA/backport needed. |
| Flatpak | **v2 / deferred (DIST-01)** | Would re-enable the `HostRunner` Flatpak path and bundle VTE; out of v1. |

## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Python + PyGObject | Vala / Rust (gtk-rs) | Only if RAM/perf became the GUI bottleneck — it won't (bottleneck is Node agents + containers). |
| System VTE (native) | Bundle/compile VTE (Flatpak) | Only relevant if a v2 Flatpak channel is added. |
| Direct PTY + `HostRunner` no-op | `flatpak-spawn --host` | Only inside a future Flatpak build; the seam already accommodates it. |
| Shell-out `docker compose` | `docker` Python SDK / `python-on-whales` | Never here — adds deps. |
| `Gio.Subprocess` + GLib loop | Python `asyncio` | Only if a future component is genuinely async-Python-shaped; mixing two event loops in a GTK app is a footgun. |
| `tomllib` (read) | `tomlkit` | Only if you need round-trip-preserving edits of user TOML; not needed for read-only config. |

## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `flatpak-spawn --host` (in v1) | No sandbox in v1 — unnecessary indirection | Direct spawn via `HostRunner` |
| Compiling/bundling VTE + simdutf + fast_float | Only needed for Flatpak, which is out of v1 | System `vte4` / `gir1.2-vte-3.91` |
| `pip install PyGObject` | Conflicts with distro bindings; wrong execution model | System `python3-gi` / `python-gobject` |
| Snap as a channel | Confinement blocks driving host docker/git/ssh cleanly | Native `.deb` + AUR |
| Hand-rolling a PTY layer | VTE already owns/forwards the PTY | `Vte.Terminal.spawn_async` |
| `docker` PyPI SDK / `python-on-whales` | Extra dep, two execution models | `docker compose` via `HostRunner` |
| Blocking `subprocess.run` on the GTK main loop for long jobs | Freezes the UI | `Gio.Subprocess` async |
| Text-scraping VTE buffer as primary state signal | Fragile against TUI repaints (Claude Code) | Claude Code hooks (Phase 4) + OSC 133, scrape only as fallback |
| VTE APIs newer than 0.76 without a guard | Breaks on Ubuntu 24.04 (ships 0.76) | Target the 0.76 API floor |

## Version Compatibility
| Component | Pin | Notes |
|-----------|-----|-------|
| VTE | system: Ubuntu **0.76** / Arch **0.84** (Vte-3.91) | Code to the 0.76 API floor so one codebase covers both |
| GTK / libadwaita / PyGObject | system (Ubuntu 24.04 / Arch) | Use distro packages, not pip |
| `tomllib` | stdlib (Python 3.11+) | Read-only; fine |

## Roadmap-Relevant Flags
- **Phase 1 (Terminal):** direct native PTY behind a no-op `HostRunner`; app owns the palette; verify Ctrl+C / Ctrl+Z+`fg` / exit-status / no-orphans. The old "get the Flatpak manifest build green" risk is gone.
- **Phase 4 (status detection):** HOOKS-FIRST (Claude Code `Notification`/`Stop` → state file); OSC 133 + `contents-changed` secondary; scraping deferred to v2. Highest-uncertainty piece.
- **Phase 5 (agent swap / themes):** shell is the durable PTY child; agents are ephemeral commands; theme-switching UI (Dracula default) lands here.
- **Phase 7 (containers):** docker on host directly; port auto-probe + persist; override regenerates the whole `ports` list; teardown wired to exit handlers.
- **Phase 9 (packaging):** Ubuntu 24.04 GTK4-VTE confirmed in `main` (0.76); AUR relies on system `vte4` 0.84. Flatpak is v2.

## Sources
- [Arch vte4 0.84.0-1](https://archlinux.org/packages/extra/x86_64/vte4/) — native GTK4 VTE 0.84 (HIGH)
- Ubuntu 24.04 `apt-cache policy gir1.2-vte-3.91` — **0.76.0-1ubuntu0.1 in `main`**, verified on host 2026-06-08 (HIGH)
- [Vte 3.91 reference docs](https://gnome.pages.gitlab.gnome.org/vte/gtk4/) — Vte-3.91 GTK4 binding (HIGH)
- [Docker Compose project name](https://docs.docker.com/compose/how-tos/project-name/) + [override merge](https://docs.docker.com/compose/intro/compose-application-model/) — COMPOSE_PROJECT_NAME isolation, override array-merge gotcha (HIGH)
- [Contour OSC 133 shell integration](https://contour-terminal.org/vt-extensions/osc-133-shell-integration/) — semantic prompt boundaries (MEDIUM)
- [ArchWiki Meson](https://wiki.archlinux.org/title/Meson_package_guidelines) / [Python package guidelines](https://wiki.archlinux.org/title/Python_package_guidelines) — AUR packaging (HIGH)
- [Debian libvte-2.91-gtk4-0](https://packages.debian.org/unstable/libs/libvte-2.91-gtk4-0) — GTK4 VTE in Debian (MEDIUM)
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
