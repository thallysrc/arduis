# Phase 9: Packaging (AUR + .deb) - Context

**Gathered:** 2026-06-15 (--chain: interactive discuss, then auto plan+execute)
**Status:** Ready for planning

<domain>
## Phase Boundary

Make arduis **team-installable as native packages** on Ubuntu (`.deb`) and Arch (AUR), using the
**system VTE** (Ubuntu 0.76 / Arch 0.84) — no bundling, no sandbox, no Flatpak (deferred to v2).
The acceptance bar is a **clean install + launch under real Wayland on BOTH distros**: `apt install`
the built `.deb` on Ubuntu 24.04 and build/install the AUR `PKGBUILD` on Arch, then launch arduis
from the desktop entry and confirm the embedded VTE terminal works. This is the final phase of v1.

**Out of scope (this phase):** Flatpak (v2 / DIST-01); publishing to the AUR and hosting the `.deb`
in an apt repo / PPA (manual or v1.1 — this phase produces the packaging DEFINITIONS that build
locally, not the publish pipeline); Snap (rejected).
</domain>

<decisions>
## Implementation Decisions

### Build / install system
- **D-01:** Use **meson + ninja** as the single build/install definition (the GNOME-standard for a
  PyGObject app). Both downstream packages wrap it thinly: the `.deb` via debhelper with the meson
  build sequence, the AUR `PKGBUILD` via `meson setup`/`meson compile`/`meson install` with
  `DESTDIR`. Rejected: setuptools/pip (wrong execution model — the app uses DISTRO PyGObject, never
  `pip install PyGObject`, per CLAUDE.md) and a plain Makefile (reimplements what meson gives free:
  DESTDIR staging, XDG install dirs, desktop/metainfo validation hooks).
- **D-02:** meson installs: (a) the `arduis` Python package into a package-private libdir (e.g.
  `{prefix}/share/arduis/` or the meson python module install), (b) a launcher executable `arduis`
  on `PATH` (`{prefix}/bin/arduis`) that sets up `sys.path` and runs the app's entry point — this
  is what the existing `.desktop` `Exec=arduis` already expects, and (c) the data assets
  (`.desktop`, `.metainfo.xml`, icon) into their XDG locations. The launcher replaces the
  dev-only `run.sh` for installed use (`run.sh` stays for dev).

### Version + maintainer identity
- **D-03:** Version is **1.0.0** (the v1 milestone), declared ONCE in `meson.build`
  (`project('arduis', version: '1.0.0')`) and propagated to the app/`.metainfo.xml` release entry,
  the `PKGBUILD` `pkgver`, and the `debian/changelog` first entry — no second source of truth.
- **D-04:** Maintainer is **`thallys <thallys.costa@livon.io>`** (from `git config`) in
  `debian/control` (Maintainer:) and the `PKGBUILD` `# Maintainer:` comment. Upstream URL =
  `https://github.com/thallysrc/arduis`. (Noted: this is a work email going public in the package
  metadata — accepted by the PO.)

### App icon
- **D-05:** **Generate a simple scalable SVG icon** at
  `data/icons/hicolor/scalable/apps/io.github.thallys.Arduis.svg` (geometric, dracula palette,
  evoking the embedded-terminal / parallel-worktrees idea) so the package is complete and the
  launcher shows a real icon (the `.desktop`/`.metainfo` already reference `Icon=io.github.thallys.Arduis`).
  meson installs it to the hicolor theme dir; post-install runs `gtk-update-icon-cache` (the `.deb`
  via dh triggers, the AUR via a `.install` scriptlet). Replaceable later by a designed icon.

### Distribution + CI scope
- **D-06:** Ship the packaging **DEFINITIONS that build locally** only: `meson.build` (+
  `meson_options` if needed), `debian/` (control, rules, changelog, compat, install, the
  dh-meson sequence), and a `PKGBUILD` (Arch). Plus a packaging section in the README documenting
  how to build/install on each distro. Publishing to the AUR and hosting/serving the `.deb`
  (GitHub Releases / apt repo / PPA) is MANUAL / deferred to v1.1 — not built here. No CI pipeline
  in this phase.

### Claude's Discretion
- Exact meson layout (python.install_sources vs install_data + a generated launcher), the launcher
  shebang/entry mechanism, and whether a tiny `arduis` console entry imports `arduis.main:main`.
- Dependency lists per distro (must follow the CLAUDE.md Packaging table: Ubuntu →
  `gir1.2-vte-3.91`/`libvte-2.91-gtk4-0` 0.76, `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`,
  `python3` ≥3.12; Arch → `vte4`, `python-gobject`, `gtk4`, `libadwaita`, `python`).
- The SVG icon's exact artwork.
- desktop-file-validate / appstreamcli metainfo validation as build/CI-less local checks.
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Packaging policy (project-level, authoritative)
- `CLAUDE.md` §Packaging (Phase 9) — the per-channel approach + EXACT dependency lists (Ubuntu
  `gir1.2-vte-3.91`/`libvte-2.91-gtk4-0` 0.76 confirmed in `main`; Arch `vte4` 0.84 in `extra`),
  and "native only in v1, Flatpak v2".
- `CLAUDE.md` §"What NOT to Use" — no `pip install PyGObject`, no Snap, no VTE bundling, no
  `flatpak-spawn` in v1; code to the VTE 0.76 API floor.
- `CLAUDE.md` §Version Compatibility + §Sources — VTE pins + the verified apt/Arch package facts.

### Existing assets to wire (not re-create)
- `data/io.github.thallys.Arduis.desktop` — desktop entry (`Exec=arduis`, `Icon=io.github.thallys.Arduis`).
- `data/io.github.thallys.Arduis.metainfo.xml` — AppStream metainfo (needs a `<release version="1.0.0">`).
- `src/arduis/main.py` — `APP_ID = "io.github.thallys.Arduis"`, the `Adw.Application` entry point the launcher must invoke.
- `run.sh` — dev launcher (`python3 src/main.py`); the installed `arduis` launcher mirrors its sys.path setup.
- `.planning/PROJECT.md` — the running phase log + the "Phase 9 = hardware gate" framing.

### Roadmap
- `.planning/ROADMAP.md` §"Phase 9: Packaging (AUR + .deb)" — goal + success criteria.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `data/*.desktop` + `*.metainfo.xml` already exist with the correct app id — meson just installs +
  validates them; the metainfo needs a 1.0.0 `<release>` entry added.
- `src/arduis/main.py` exposes the `Adw.Application` (`APP_ID` set) — the installed launcher invokes
  this; today `run.sh` does `python3 src/main.py` with `src/` put on `sys.path` by `main.py` itself.
- `pyproject.toml` currently holds ONLY pytest config (`testpaths`/`pythonpath=src`) — NOT project
  metadata. Packaging metadata lives in meson/debian/PKGBUILD, not here (keep pyproject pytest-only).

### Established Patterns
- The app is pure system-PyGObject (no third-party Python deps) — packaging declares only DISTRO
  runtime deps (GTK4/libadwaita/VTE-3.91/python3-gi), never pip wheels.
- `src/main.py` is a thin shim; the real package is `src/arduis/`. meson must install the `arduis`
  package (not a loose `src/`) and a launcher that imports it.

### Integration Points
- New: `meson.build` at repo root (+ `data/meson.build`, maybe `src/meson.build`).
- New: `debian/` dir (control, rules using dh + meson, changelog 1.0.0, compat, install, source/format).
- New: `PKGBUILD` (+ optional `.install` for icon-cache/desktop-db post hooks).
- New: `data/icons/hicolor/scalable/apps/io.github.thallys.Arduis.svg`.
- New: launcher `bin/arduis` (or meson-generated) replacing `run.sh` for installed use.
- New: README packaging/install section for Ubuntu + Arch.
</code_context>

<specifics>
## Specific Ideas
- The whole point is "instalável facilmente por um time" — `apt install ./arduis_1.0.0_*.deb` on
  Ubuntu, `makepkg -si` (AUR) on Arch, then it shows up in the app grid with its icon and launches.
- Acceptance is a **hardware gate**: the PO verifies clean install + launch under real Wayland on
  BOTH Ubuntu 24.04 and Arch (like the live UATs of prior phases). The automated half is: the
  packages BUILD, lint clean (desktop-file-validate, appstream validate, lintian/namcap if present),
  and declare the right deps.
</specifics>

<deferred>
## Deferred Ideas
- Flatpak channel (re-enables the HostRunner Flatpak path + bundles VTE) — v2 / DIST-01.
- Publishing: pushing the `PKGBUILD` to aur.archlinux.org + hosting the `.deb` (GitHub Releases /
  apt repo / PPA) — manual or v1.1, not built here.
- CI (GitHub Actions building the `.deb` + namcap/lintian on every push) — considered, deferred to
  keep this phase lean; can be added in v1.1.
- A professionally-designed app icon — the v1 SVG is a clean placeholder.

### Reviewed Todos (not folded)
None — no pending todos matched this phase.
</deferred>

---

*Phase: 09-packaging-aur-deb*
*Context gathered: 2026-06-15*
