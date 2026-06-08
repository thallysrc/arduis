<!-- GSD:project-start source:PROJECT.md -->
## Project

**arduis**

arduis é um app desktop GNOME **lightweight** (Linux: Ubuntu + Arch) que orquestra
**vários agentes de IA (Claude Code) em paralelo** — cada um na sua **git worktree**, com
**terminais reais embutidos (VTE)**. É a resposta Linux e terminal-cêntrica ao
BridgeMind/BridgeSpace (que só existe no Mac). Para devs que vivem no terminal/tmux e usam
agentes de IA intensamente; usável solo e **instalável facilmente por um time** (Flatpak).

**Core Value:** Tirar a ideia "quero começar uma branch nova" e ter um **agente de IA rodando numa worktree
isolada em segundos** — gerenciando N agentes em paralelo e **sempre sabendo qual deles te
espera**.

### Constraints

- **Plataforma**: Linux + GNOME, **Ubuntu E Arch** — regra inegociável
- **Tech stack**: Python + PyGObject + GTK4 + libadwaita + VTE (Vte-3.91); config TOML; shell-out para git/gh/docker compose
- **Distribuição**: Flatpak principal (instalação fácil pro time); AUR + .deb nativos; Snap não
- **UX**: centrado no terminal; respeita keybindings estilo tmux
- **Performance/Memória**: lightweight, com **gestão de RAM de primeira classe**
- **Método**: Accelerate/DORA — degraus pequenos, instaláveis e usáveis; trunk-based; entrega contínua; `main` sempre funcionando; dogfooding cedo
- **Escopo**: credenciais/Jira fora; só leitura de git/gh
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Verdict on the User's Pinned Decisions
| Decision | Verdict | Note |
|----------|---------|------|
| Python + PyGObject + GTK4 + libadwaita | **CONFIRMED — sound** | Standard GNOME app stack; PyGObject 3.56.0 (Feb 2026) current; bundled in GNOME SDK 50 |
| VTE for GTK4 (Vte-3.91), pinned 0.84.0 | **CONFIRMED — current stable** | 0.84.0 released 2026-03-14; Arch `vte4` is already 0.84.0-1 |
| GNOME SDK/Platform 50 | **CONFIRMED — current** | GNOME 50 released March 2026; supported until GNOME 52 (~April 2027) |
| simdutf pinned v7.7.1 | **CONFIRMED — matches VTE wrap** | VTE 0.84.0 `subprojects/simdutf.wrap` pins exactly `v7.7.1` |
| fast_float pinned v8.2.8 | **CHALLENGE — mismatch** | VTE 0.84.0 `subprojects/fast_float.wrap` pins **v8.1.0**, not v8.2.8. See Pitfall below. |
| TOML via `tomllib` (stdlib) | **CONFIRMED — correct for read** | `tomllib` is read-only (Python 3.11+); you only read `.arduis.toml`, so stdlib is enough. See note on writing. |
| Flatpak primary + AUR + .deb; no Snap | **CONFIRMED — sound** | Snap confinement is genuinely hostile to a docker/git-driving tool; instinct correct |
| Shell-out to git/gh/docker compose | **CONFIRMED — correct** | No mature, maintained Python libs worth the dependency cost here |
## Recommended Stack
### Core Technologies
| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 (host) / 3.12.x in SDK 50 | App language | Fast prototyping, minimal deps, first-class GNOME bindings; RAM bottleneck is agents/containers, not the GUI — confirms the "don't rewrite in Rust" decision |
| PyGObject | 3.56.0 (in GNOME SDK 50) | GTK/GLib/Vte bindings | Latest (2026-02-27); improved GObject lifecycle (`do_constructed`, `do_dispose`). **In Flatpak you use the SDK's copy — do not `pip install` it.** |
| GTK | 4.x (GNOME 50 series) | UI toolkit | Native GNOME on both Ubuntu and Arch; comes in the runtime |
| libadwaita | 1.x (GNOME 50 series) | Adaptive widgets/styling | `Adw.ApplicationWindow`, `Adw.ToolbarView`, `Adw.HeaderBar` already used correctly in draft `main.py` |
| VTE (GTK4) | 0.84.0 (Vte-3.91) | Embedded real terminal | Same engine as GNOME Terminal; `gi.require_version("Vte", "3.91")` is correct. NOT in the GNOME runtime — must be compiled in the manifest (see below) |
| Flatpak runtime | `org.gnome.Platform` / `org.gnome.Sdk` 50 | Dev env == distribution | One build covers Ubuntu + Arch; dogfood-friendly |
| TOML parsing | `tomllib` (stdlib, 3.11+) | Read `.arduis.toml` | Zero dependency; read-only is fine because the schema is hand-edited |
### Supporting Libraries
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| GLib / Gio (via PyGObject) | with SDK 50 | Async subprocess, main-loop integration, signals | **Primary concurrency tool.** Use `Gio.Subprocess` + the GLib main loop for non-PTY child processes (`git`, `gh`, `docker compose`); never block the GTK main loop. |
| Vte.Pty / `Vte.Terminal.spawn_async` | 0.84.0 | PTY-backed long-lived processes (the agents) | The agent terminals ARE the PTY-backed processes — VTE owns the PTY. You do not need a separate `pty`/`asyncio` PTY layer for those. |
| `tomli-w` (optional) | 1.x | Writing TOML if you ever generate `.arduis.toml` | Only if arduis writes config back. `tomllib` cannot write. Keep optional. |
| Python `subprocess` (stdlib) | 3.12 | Simple synchronous/quick host queries | For short read-only calls (`git rev-parse`, `gh pr view --json`) where blocking briefly is acceptable; prefer `Gio.Subprocess` for anything longer. |
| `shlex` (stdlib) | 3.12 | Safe argv construction for `flatpak-spawn --host` | Build argv lists, never shell strings, when forwarding to the host |
### Development Tools
| Tool | Purpose | Notes |
|------|---------|-------|
| flatpak-builder 1.4.2 | Build the app + VTE from manifest | Already installed; builds VTE, simdutf, fast_float as modules |
| meson + ninja (in SDK) | VTE build system | VTE module is `buildsystem: meson` — correct in draft manifest |
| cmake + ninja (in SDK) | simdutf / fast_float build | Both `cmake-ninja` — correct |
| pytest + pytest-xvfb | Test runner + headless display | `xvfb-run python -m pytest` or the `pytest-xvfb` plugin in CI |
| dbus-run-session | Session bus for GTK tests | Modern replacement for `dbus-launch`; what PyGObject's own suite uses |
| Mutter `--headless` (optional) | Wayland-native headless GUI tests | More faithful than Xvfb if you assert on real rendering/input |
| ruff + mypy + PyGObject-stubs | Lint/type-check | `PyGObject-stubs` gives typing for `gi.repository.*` |
## Installation
# --- Dev environment (host) ---
# Build + run the app from the manifest (dev == distribution path)
# --- Test deps (host venv, only for CI/unit tests outside the sandbox) ---
# system: xvfb (or mutter), dbus, gobject-introspection, gir1.2-vte-3.91 if testing outside flatpak
## VTE Bundling in Flatpak (the load-bearing detail)
- **fast_float: use `v8.1.0`, not `v8.2.8`.** VTE 0.84.0's own `subprojects/fast_float.wrap` pins `revision = v8.1.0`. Pinning v8.2.8 means you ship a different fast_float than upstream VTE was tested against. It will *probably* compile (header-only, stable API), but you lose the "matches upstream" guarantee. Either pin `v8.1.0` to match, or accept the drift deliberately and document why. (Confidence: HIGH that the wrap says v8.1.0.)
- **simdutf v7.7.1 is correct** — matches VTE 0.84.0's `subprojects/simdutf.wrap` exactly. Keep it. (Confidence: HIGH.)
- Consider extracting the exact pins by reading VTE's wrap files at the tagged commit rather than tracking them by hand, so a VTE bump auto-surfaces the right dep versions.
- Pin VTE by tag `0.84.0` (draft does) and ideally add `commit:` for reproducibility; tags on GNOME GitLab are protected but a commit hash is strictly safer for a redistributable build.
## flatpak-spawn --host: Reliability & Permissions (must shape architecture)
- `flatpak-spawn --host` runs the command **unsandboxed on the host** and requires access to the `org.freedesktop.Flatpak` D-Bus interface — hence `--talk-name=org.freedesktop.Flatpak` in `finish-args` (correct in the draft). (Confidence: HIGH.)
- Without `--host`, `flatpak-spawn` goes through the portal and creates a sandbox copy; **with** `--host` it uses the `org.freedesktop.Flatpak` Development interface to escape. (Confidence: HIGH.)
- **Environment is NOT inherited the way it looks.** The host process gets the host's environment, but PATH, locale, and shell-init differences between sandbox and host bite constantly. The draft sets `--env=TERM=xterm-256color` explicitly — good pattern; do the same for anything the agent needs. Running `zsh` (login/interactive) so the user's `.zshrc`/PATH loads is the right call for finding `claude`/`gh`.
- **`flatpak-spawn --host` PTY handling is the supported path for terminals** — VTE owns the PTY and `flatpak-spawn` forwards it. This works (it is how Flatpak'd terminal/IDE apps shell out), but signal propagation (e.g. `Ctrl+C` reaching the host child, the Degrau 5 "Ctrl+C drops to shell" requirement) needs explicit testing — signals cross the sandbox boundary and edge cases exist.
- **Each `flatpak-spawn --host` is a separate host process tree.** Managing N long-lived agents means tracking N host PIDs you cannot directly `kill()` from inside the sandbox — you send signals through the spawned process / VTE, or run a small host-side helper. Hibernate/teardown (RAM management, a first-class requirement) must be designed around this, not assumed to be a normal `os.kill`.
- **`--filesystem=home` is required** (draft has it) so the sandbox sees the worktrees; but the host commands run on the *real* paths. Keep arduis reasoning in host paths, not sandbox-mapped paths, when constructing `git worktree add` arguments.
- **Docker/docker compose run on the host**, so all compose orchestration is "build argv → `flatpak-spawn --host docker compose ...`". The sandbox never talks to the Docker socket directly — good, avoids a `--filesystem` hole for `/run/docker.sock`.
## Subprocess / Process-Management Patterns
| Need | Recommended approach | Why |
|------|---------------------|-----|
| Agent terminals (long-lived PTY) | `Vte.Terminal.spawn_async` with argv = `flatpak-spawn --host ... zsh` | VTE owns the PTY, handles resize/scrollback/colors; you do not hand-roll a PTY layer |
| Short read-only host queries (`git`, `gh --json`) | `Gio.Subprocess` + `communicate_utf8_async` on the GLib main loop | Non-blocking, integrates with GTK loop, no threads needed |
| Many parallel long-running non-PTY jobs (setup commands, `docker compose up -d`) | `Gio.Subprocess` async, track by `Gio.Subprocess` handle | Async-first; reserve Python `asyncio` only if you genuinely need it (GLib loop already gives you concurrency) |
| State detection ("who's waiting on me") | VTE `contents-changed` signal + OSC 133 shell integration; fallback to output heuristics | See below |
- VTE supports **OSC 133 semantic prompt** shell integration. On modern distros the shell sources a `vte.sh` that emits OSC 133 at prompt boundaries, letting VTE distinguish prompt / input / command-output phases. This is the *correct, robust* signal for "agent finished and is back at a prompt / waiting" rather than scraping bytes.
- VTE emits `contents-changed` (and cursor/notification signals) you can hook from Python. Combine: OSC 133 markers for prompt boundaries + a short idle timer on `contents-changed` to classify running / waiting-for-input / idle.
- Pure text-scraping of the last lines is the fragile fallback (Claude Code's TUI repaints heavily). Prefer the semantic-prompt path; flag Degrau 4 as needing a focused spike.
## Docker Compose Orchestration Patterns (Degrau 7)
- **Isolation via `COMPOSE_PROJECT_NAME`** — setting a unique project name per worktree gives separate container names, networks, and volumes (so each worktree gets an empty, isolated DB for free). This is exactly the documented mechanism for "a stable copy per feature branch." Pass it as an env var to the `flatpak-spawn --host docker compose` call.
- **Override files** — `docker compose -f docker-compose.yml -f docker-compose.override.yml ...` merges, override wins; arrays like `ports` are *combined* not replaced, which is the classic gotcha. To remap a port you must override the whole service's `ports` list, not append. Generate the override with the offset-applied port list, don't try to "patch" individual ports.
- **Base from `main`** — read the compose file from the `main` worktree/checkout, not the feature branch, per the user's decision; generate the override into the worktree dir.
- **Port offset** — auto-assign with a per-worktree offset (config `port_offset = 1000`) but **probe for free ports** before committing, because fixed offsets collide once you have several worktrees + restarts. Show resolved ports in the UI badge (`db :5433`). Open question (fixed vs. auto) resolves toward: auto-probe, then persist the chosen ports per worktree so badges/URLs stay stable.
- **Teardown** — `docker compose -p <name> down -v` on worktree removal/hibernate; `-v` to drop the isolated volumes. Guaranteed teardown is a first-class RAM requirement — wire it into both "conclude worktree" and app-exit handlers.
- **No Python docker library.** Skip `docker` PyPI SDK and `python-on-whales`: they add a dependency, and you'd still need host access. Shelling `docker compose` via `flatpak-spawn --host` keeps one consistent execution model and matches the "shell-out, don't reinvent" decision.
## Packaging (Degrau 9)
| Channel | Approach | Notes |
|---------|----------|-------|
| Flatpak (primary) | The existing manifest, submitted to Flathub | One build, Ubuntu+Arch. The VTE+deps modules already make it self-contained. This is the only channel where VTE-bundling matters. |
| AUR (native) | `PKGBUILD` depending on system `vte4` (0.84.0-1 already in Arch extra), `python-gobject`, `gtk4`, `libadwaita` | Arch ships VTE 0.84 GTK4 in `extra` — no need to vendor it natively. Use Meson packaging or a simple `install`; follow ArchWiki Meson/Python guidelines. No sandbox = `flatpak-spawn` indirection drops away (runs commands directly). |
| .deb (native) | Standard debhelper package; depends on `gir1.2-vte-3.91`/`libvte-2.91-gtk4-0`, `python3-gi`, `gir1.2-gtk-4.0`, `libadwaita` | Debian sid has `libvte-2.91-gtk4-0`; on Ubuntu 24.04 the GTK4 VTE may be too old/absent — verify per target release, may need a backport or PPA. Flag as a per-release check. |
## Alternatives Considered
| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| Python + PyGObject | Vala / Rust (gtk-rs) | Only if RAM/perf became the GUI bottleneck — it won't (bottleneck is Node agents + containers). Decision to stay Python is correct. |
| VTE compiled in manifest | Bundle a prebuilt VTE / use a BaseApp | No maintained GTK4-VTE BaseApp; compiling 3 small modules is the standard, reliable path. |
| `flatpak-spawn --host` | `--filesystem=host` + direct exec; or a host D-Bus helper service | A separate host helper service is worth considering ONLY if `flatpak-spawn` signal/PTY edge cases prove unworkable in Degrau 1–5 testing. Start with `flatpak-spawn`. |
| Shell-out `docker compose` | `docker` Python SDK / `python-on-whales` | Never here — adds deps and still needs host access. |
| `Gio.Subprocess` + GLib loop | Python `asyncio` | Use `asyncio` only if a future component is genuinely async-Python-shaped; mixing two event loops in a GTK app is a known footgun. |
| `tomllib` (read) | `tomlkit` | Only if you need round-trip-preserving edits of user TOML; not needed for read-only config. |
## What NOT to Use
| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `pip install PyGObject` inside the Flatpak | Conflicts with SDK's bindings; wrong execution model | Use the GNOME SDK 50 copy |
| fast_float `v8.2.8` (current draft) | Does not match VTE 0.84.0's pinned `v8.1.0`; loses upstream-tested guarantee | Pin `v8.1.0` (or document the deliberate drift) |
| Snap as a channel | Confinement blocks driving host docker/git/ssh cleanly | Flatpak + AUR + .deb (already the plan) |
| Hand-rolling a PTY layer for agents | VTE already owns/forwards the PTY | `Vte.Terminal.spawn_async` |
| `docker` PyPI SDK / `python-on-whales` | Extra dep, still needs host access, two execution models | `flatpak-spawn --host docker compose ...` |
| Blocking `subprocess.run` on the GTK main loop for long jobs | Freezes the UI | `Gio.Subprocess` async |
| Text-scraping VTE buffer as primary state signal | Fragile against TUI repaints (Claude Code) | OSC 133 semantic prompt + `contents-changed`, scrape only as fallback |
| `--filesystem=host` blanket hole | Over-broad sandbox break | `--filesystem=home` (draft) + `flatpak-spawn --host` |
## Version Compatibility
| Component | Pin | Compatible With | Notes |
|-----------|-----|-----------------|-------|
| GNOME SDK/Platform | 50 | GTK4, libadwaita 1.x, PyGObject 3.56 | Supported until ~GNOME 52 (Apr 2027) |
| VTE | 0.84.0 (Vte-3.91) | GTK 4 in SDK 50 | Released 2026-03-14; Arch `vte4` already 0.84.0-1 |
| simdutf | v7.7.1 | VTE 0.84.0 | Matches VTE's `simdutf.wrap` exactly — KEEP |
| fast_float | **v8.1.0** (correct VTE pin) | VTE 0.84.0 | Draft's v8.2.8 is a mismatch — change to v8.1.0 |
| `tomllib` | stdlib (Python 3.11+) | Python 3.12 in SDK | Read-only; fine |
## Roadmap-Relevant Flags
- **Degrau 1 (VTE in a window):** stack is proven; the only real work is getting the manifest build green. Fix fast_float pin first.
- **Degrau 4 (status detection):** flag for a focused spike — OSC 133 + `contents-changed`, not byte-scraping. Highest-uncertainty piece.
- **Degrau 5 (Ctrl+C / agent swap):** explicitly test signal propagation across the `flatpak-spawn --host` boundary; this is the known reliability edge.
- **Degrau 7 (containers):** port auto-probe + persist; override file regenerates whole `ports` list; teardown wired to exit handlers.
- **Degrau 9 (packaging):** verify Ubuntu 24.04 GTK4-VTE availability for .deb (may need backport); AUR can rely on system `vte4` 0.84.
## Sources
- [VTE GitLab tags](https://gitlab.gnome.org/GNOME/vte/-/tags) — confirmed 0.84.0 released 2026-03-14 (HIGH)
- [VTE 0.84.0 fast_float.wrap](https://gitlab.gnome.org/GNOME/vte/-/raw/0.84.0/subprojects/fast_float.wrap) — pins v8.1.0 (HIGH)
- [VTE 0.84.0 simdutf.wrap](https://gitlab.gnome.org/GNOME/vte/-/raw/0.84.0/subprojects/simdutf.wrap) — pins v7.7.1 (HIGH)
- [Arch vte4 0.84.0-1](https://archlinux.org/packages/extra/x86_64/vte4/) — native GTK4 VTE 0.84 available (HIGH)
- [Vte 3.91 reference docs](https://gnome.pages.gitlab.gnome.org/vte/gtk4/) — Vte-3.91 GTK4 binding (HIGH)
- [Flathub org.gnome.Platform 50](https://flathub.org/en/apps/org.gnome.Platform) / [org.gnome.Sdk 50](https://flathub.org/en/apps/org.gnome.Sdk) — runtime 50 available (HIGH)
- [GNOME Foundation update 2026-03-20](https://blogs.gnome.org/aday/2026/03/20/gnome-foundation-update-2026-03-20/) — GNOME 50 released March 2026 (HIGH)
- [PyGObject 3.56.0 release notes](https://pygobject.gnome.org/news/pygobject-3-56.html) — latest 2026-02-27 (HIGH)
- [Flatpak sandbox permissions](https://docs.flatpak.org/en/latest/sandbox-permissions.html) + [flatpak-spawn(1)](https://man7.org/linux/man-pages/man1/flatpak-spawn.1.html) — --host requires org.freedesktop.Flatpak (HIGH)
- [Docker Compose project name](https://docs.docker.com/compose/how-tos/project-name/) + [override merge](https://docs.docker.com/compose/intro/compose-application-model/) — COMPOSE_PROJECT_NAME isolation, override array-merge gotcha (HIGH)
- [PyGObject testing & CI guide](https://pygobject.gnome.org/guide/testing.html) — pytest-xvfb, dbus-run-session, mutter --headless (HIGH)
- [Contour OSC 133 shell integration](https://contour-terminal.org/vt-extensions/osc-133-shell-integration/) + [PyGObject threading](https://pygobject.gnome.org/guide/threading.html) — semantic prompt + GLib idle_add (MEDIUM)
- [ArchWiki Meson](https://wiki.archlinux.org/title/Meson_package_guidelines) / [Python package guidelines](https://wiki.archlinux.org/title/Python_package_guidelines) — AUR packaging (HIGH)
- [Debian libvte-2.91-gtk4-0 (sid)](https://packages.debian.org/unstable/libs/libvte-2.91-gtk4-0) — GTK4 VTE in Debian; verify Ubuntu 24.04 (MEDIUM)
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
