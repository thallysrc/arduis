# Phase 9: Packaging (AUR + .deb) - Research

**Researched:** 2026-06-15
**Domain:** Native Linux packaging of a meson-built, pure-system-PyGObject GTK4/libadwaita/VTE app (.deb + AUR)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use **meson + ninja** as the single build/install definition. `.deb` wraps it via debhelper; AUR `PKGBUILD` wraps it via `meson setup`/`compile`/`install` with `DESTDIR`. Rejected: setuptools/pip (wrong execution model — distro PyGObject, never `pip install PyGObject`) and a plain Makefile.
- **D-02:** meson installs: (a) the `arduis` Python package, (b) a launcher executable `arduis` on `PATH` (`{prefix}/bin/arduis`) that the existing `.desktop` `Exec=arduis` expects, (c) data assets (`.desktop`, `.metainfo.xml`, icon) into XDG locations. The launcher replaces dev-only `run.sh` for installed use (`run.sh` stays for dev).
- **D-03:** Version is **1.0.0**, declared ONCE in `meson.build` (`project('arduis', version: '1.0.0')`) and propagated to the `.metainfo.xml` release entry, the `PKGBUILD` `pkgver`, and the `debian/changelog` first entry — no second source of truth.
- **D-04:** Maintainer is **`thallys <thallys.costa@livon.io>`** (from `git config`) in `debian/control` (Maintainer:) and the `PKGBUILD` `# Maintainer:` comment. Upstream URL = `https://github.com/thallysrc/arduis`. (Work email going public — accepted by PO.)
- **D-05:** **Generate a simple scalable SVG icon** at `data/icons/hicolor/scalable/apps/io.github.thallys.Arduis.svg` (geometric, dracula palette). meson installs it to the hicolor theme dir; post-install runs `gtk-update-icon-cache` (`.deb` via dh triggers; AUR — see CORRECTION below). Replaceable later.
- **D-06:** Ship the packaging **DEFINITIONS that build locally** only: `meson.build` (+ `meson_options` if needed), `debian/` (control, rules, changelog, compat, install, source/format), and a `PKGBUILD`. Plus a README packaging section. Publishing to AUR / hosting the `.deb` is MANUAL / v1.1. No CI pipeline this phase.

### Claude's Discretion
- Exact meson layout (`python.install_sources` vs `install_data` + generated launcher), launcher shebang/entry mechanism, whether a tiny `arduis` console entry imports `arduis.main:main`.
- Dependency lists per distro (must follow the CLAUDE.md Packaging table).
- The SVG icon's exact artwork.
- `desktop-file-validate` / `appstreamcli` metainfo validation as build/CI-less local checks.

### Deferred Ideas (OUT OF SCOPE)
- Flatpak channel (re-enables the HostRunner Flatpak path + bundles VTE) — v2 / DIST-01.
- Publishing: pushing the `PKGBUILD` to aur.archlinux.org + hosting the `.deb` (GitHub Releases / apt repo / PPA) — manual or v1.1.
- CI (GitHub Actions building the `.deb` + namcap/lintian on every push) — deferred to v1.1.
- A professionally-designed app icon — the v1 SVG is a clean placeholder.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DIST-02 | Pacote nativo **AUR** (Arch), usando `vte4` do sistema | PKGBUILD with `arch-meson` + `meson install --destdir`, `depends=(python-gobject gtk4 libadwaita vte4 python)`, `arch=('any')`, `makedepends=(meson)`. No `.install` needed (see §Pitfall 3). |
| DIST-03 | Pacote nativo **`.deb`** (Ubuntu), usando `gir1.2-vte-3.91` do sistema | `debian/` with `dh $@ --buildsystem=meson`, debhelper-compat 13, `Architecture: all`, runtime `Depends:` on `gir1.2-vte-3.91`/`libvte-2.91-gtk4-0`/`python3-gi`/`gir1.2-gtk-4.0`/`gir1.2-adw-1`/`python3 (>=3.12)`. |
| DIST-04 | Roda em Ubuntu e Arch (GNOME, Wayland) | Both packages declare correct system deps verified present (§Standard Stack). The launch-under-Wayland check is a **manual hardware gate** (§Validation Architecture / UAT). |
</phase_requirements>

## Summary

Phase 9 is pure packaging plumbing over an app that is **100% pure Python `.py` + three data files** — no compiled extensions, no C, no gresource/.ui/.css, no third-party Python deps (verified: `find src/arduis -type f -not -name '*.py'` returns nothing; 34 `.py` files across `arduis`, `arduis.hooks`, `arduis.swarm`). meson's `python` module installs the package; its `gnome` module handles desktop/metainfo conventions; debhelper and `PKGBUILD` each wrap the meson sequence thinly. Because the app is arch-independent, **both packages are `Architecture: all` / `arch=('any')`**.

The single load-bearing technical decision is **where the `arduis` package lands**. The codebase loads its Claude Code hook at runtime via `importlib.resources.files("arduis.hooks").joinpath("arduis_hook.py").read_text()` (`attention.py:324`). `importlib.resources` requires `arduis` to be a real importable package on `sys.path` with the hook shipped as package data. The cleanest correct answer is **install into the Python purelib (site-packages) via `python.install_sources(..., subdir:'arduis')`** — then `import arduis` and `importlib.resources` both "just work" with **zero `sys.path` hacking** in the launcher (the dev-only `run.sh`/`src/main.py` sys.path insert MUST NOT leak into the installed launcher). The generated `bin/arduis` launcher then reduces to `#!/usr/bin/env python3` + `from arduis.main import main; raise SystemExit(main())`.

**Primary recommendation:** meson `python.install_sources(preserve_path:true, subdir:'arduis')` for the whole package (including `hooks/arduis_hook.py` and `swarm/__init__.py` as data); `configure_file()`-generated `bin/arduis` launcher (no sys.path hack); `install_data` for `.desktop`/`.metainfo`/SVG into XDG dirs; `gnome.post_install(gtk_update_icon_cache:true, update_desktop_database:true)` for dev installs only (it is **skipped under DESTDIR**, so `.deb`+AUR must trigger caches themselves — dh triggers / pacman hooks). `.deb` = `dh $@ --buildsystem=meson` + compat 13 + `Architecture: all`. AUR = `arch-meson`/`meson compile`/`meson install --destdir` + `arch=('any')`, **no `.install` scriptlet** (pacman hooks auto-refresh both caches). Single-source the version from `meson.build` via `configure_file` into the metainfo `<release>` and an `arduis --version`.

## Standard Stack

### Build / packaging tools
| Tool | Version (verified) | Purpose | Why Standard |
|------|--------------------|---------|--------------|
| meson | apt candidate **1.3.2-1ubuntu1** (not yet installed on dev host) | Build/install definition | `[VERIFIED: apt-cache policy meson]` GNOME-standard; gives DESTDIR staging, XDG dirs, python module, GNOME hooks for free |
| ninja (`ninja-build`) | system | meson backend | `[CITED: mesonbuild.com]` meson's default backend |
| debhelper | apt candidate **13.14.1ubuntu5** (compat 13 available) | `.deb` build sequencer | `[VERIFIED: apt-cache policy debhelper]` `dh --buildsystem=meson` is the canonical thin wrapper |
| `arch-meson` (from `meson` pkg) | Arch `meson` | PKGBUILD meson wrapper | `[CITED: wiki.archlinux.org/Meson_package_guidelines]` sets Arch's standard buildtype/prefix/flags |

### Runtime dependencies — Ubuntu (.deb `Depends:`)  [all VERIFIED on host 2026-06-15]
| Package | Installed version | Provides |
|---------|-------------------|----------|
| `gir1.2-vte-3.91` | **0.76.0-1ubuntu0.1** | VTE-3.91 GTK4 GI typelib (the 0.76 API floor) |
| `libvte-2.91-gtk4-0` | **0.76.0-1ubuntu0.1** | VTE GTK4 shared lib (pulled by the typelib; safe to list) |
| `python3-gi` | **3.48.2-1** | PyGObject (distro, never pip) |
| `gir1.2-gtk-4.0` | **4.14.5+ds-0ubuntu0.7** | GTK4 GI typelib |
| `gir1.2-adw-1` | **1.5.0-1ubuntu2** | libadwaita GI typelib |
| `python3` (`>= 3.12`) | system | interpreter (host is 3.12.3) |
| `${misc:Depends}` | dh-substituted | debhelper-required deps |

`[VERIFIED: apt-cache policy ... on Ubuntu 24.04.3 LTS host]` — every CLAUDE.md package fact reconfirmed this session.

### Runtime dependencies — Arch (PKGBUILD `depends`)
| Package | Version (cited) | Provides |
|---------|-----------------|----------|
| `python-gobject` | system | PyGObject |
| `gtk4` | system | GTK4 + its GI typelib |
| `libadwaita` | system | libadwaita + GI typelib |
| `vte4` | **0.84** | VTE-3.91 GTK4 (`extra`) |
| `python` | system | interpreter |

`[CITED: CLAUDE.md §Packaging + archlinux.org/packages/extra/x86_64/vte4]` — not re-verifiable on this Ubuntu host (no pacman); marked accordingly.

### Build dependencies
| .deb `Build-Depends:` | AUR `makedepends` |
|-----------------------|-------------------|
| `meson`, `ninja-build`, `debhelper-compat (= 13)`, `python3` | `meson` (pulls ninja) |

**Why no third-party Python deps:** `[VERIFIED: codebase scan]` `pyproject.toml` is pytest-only; no `install_requires`; no imports outside stdlib + `gi.repository`. Packaging declares ONLY distro runtime deps.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `python.install_sources` to purelib | `install_data` into `{datadir}/arduis` + launcher `sys.path` insert | Works but forces the launcher to hack `sys.path` AND keeps `importlib.resources` working only because the dir is on the path — strictly more fragile. Purelib is the simplest correct layout for a pure-Python package. |
| `dh --buildsystem=meson` | hand-written `debian/rules` calling meson/ninja | dh auto-detects and runs configure/build/test/install correctly; hand-rolling reimplements it. |
| `arch=('any')` | `arch=('x86_64')` | Pure Python → no native objects → `any` is correct and lets one PKGBUILD serve all arches. |
| native `debian/source/format` (`3.0 (native)`) | `3.0 (quilt)` | App is built from its OWN repo (no separate upstream tarball) → native is simpler and correct for v1. |

**Installation (dev / building locally — D-06 scope):**
```bash
# Ubuntu build deps (NOT currently installed on dev host — Wave-0 gap)
sudo apt install meson ninja-build debhelper devscripts dpkg-dev lintian
# build the .deb from repo root:
dpkg-buildpackage -us -uc -b      # → ../arduis_1.0.0_all.deb
# Arch (on an Arch box):
makepkg -si                        # uses the PKGBUILD
# distro-agnostic meson smoke (any machine):
meson setup builddir && meson install -C builddir --destdir /tmp/stage
```

**Version verification (done this session):** apt `meson` 1.3.2, `debhelper` 13.14.1, `gir1.2-vte-3.91` 0.76.0, `gir1.2-adw-1` 1.5.0, `gir1.2-gtk-4.0` 4.14.5, `python3-gi` 3.48.2, `python3` 3.12.3 — all `[VERIFIED]`.

## Architecture Patterns

### Recommended Project Structure (new files this phase)
```
meson.build                 # project('arduis', version:'1.0.0'); subdirs; python module
src/meson.build             # python.install_sources(arduis/**, subdir:'arduis', preserve_path:true)
                            # + configure_file() → bin/arduis launcher
data/meson.build            # install_data .desktop/.metainfo/SVG; gnome.post_install(...)
data/arduis.in              # launcher template (configure_file source)  [or inline]
data/icons/hicolor/scalable/apps/io.github.thallys.Arduis.svg   # D-05 generated icon
debian/control              # Architecture: all; Build-Depends + Depends (lists above)
debian/rules                # %:\n\tdh $@ --buildsystem=meson
debian/changelog            # arduis (1.0.0) ...; first entry; maintainer D-04
debian/compat               # 13   (OR debhelper-compat (=13) in control — pick one)
debian/source/format        # 3.0 (native)
debian/copyright            # MIT (matches metainfo project_license)
PKGBUILD                    # arch=('any'); meson build()/package(); NO .install
README.md                   # NEW — packaging/install section (no README exists yet)
```

### Pattern 1: meson python package install (purelib)
**What:** Install the whole `arduis` package tree into site-packages so `import arduis` and `importlib.resources` work with no path hacks.
**When to use:** Pure-Python app with package-data files (our case — the hook script).
```meson
# src/meson.build  — Source: mesonbuild.com/Python-module.html [CITED]
py = import('python').find_installation('python3')
py.install_sources(
  # list every .py incl. arduis/hooks/arduis_hook.py and arduis/swarm/__init__.py
  files_glob_or_explicit_list,
  subdir: 'arduis',
  preserve_path: true,        # keeps hooks/ and swarm/ nesting
)
```
> NOTE: meson has no native recursive glob; enumerate files (34 today) or use `run_command('find'...)` guarded. Enumerating explicitly is the meson-blessed approach.

### Pattern 2: generated launcher (no sys.path hack)
**What:** A `configure_file`-generated `bin/arduis` that imports the installed package directly.
```python
#!/usr/bin/env python3
# data/arduis.in  → configure_file substitutes @VERSION@ if you want --version
import sys
from arduis.main import main
raise SystemExit(main())
```
```meson
conf = configuration_data()
conf.set('VERSION', meson.project_version())     # single-source D-03
configure_file(input: 'arduis.in', output: 'arduis',
  configuration: conf, install: true,
  install_dir: get_option('bindir'), install_mode: 'rwxr-xr-x')
```
**Why:** `src/main.py`'s `sys.path.insert(0, ...)` is a DEV shim for `python3 src/main.py`. The installed launcher imports the *installed* `arduis` from site-packages — it must NOT carry the sys.path hack (Discretion item; Criterion-adjacent).

### Pattern 3: GNOME post-install (dev only — DESTDIR-skipped)
```meson
# data/meson.build  — Source: mesonbuild.com/Gnome-module.html [CITED]
gnome = import('gnome')
gnome.post_install(gtk_update_icon_cache: true, update_desktop_database: true)
```
**CRITICAL:** `gnome.post_install` scripts are **SKIPPED when `DESTDIR` is set** `[CITED: mesonbuild.com/Gnome-module.html]`. Both `.deb` (debhelper stages into `debian/arduis/`) and AUR (`--destdir "$pkgdir"`) set DESTDIR → the caches are refreshed by the **package manager**, not meson (see §Pitfalls 2 & 3). post_install only helps a bare `meson install` on a dev box.

### Pattern 4: `.deb` rules (canonical minimal)
```makefile
#!/usr/bin/make -f
%:
	dh $@ --buildsystem=meson
```
`[CITED: man7.org/.../debhelper.7]` dh auto-runs `dh_auto_configure` (meson setup), `dh_auto_build` (ninja), `dh_auto_test` (meson test), `dh_auto_install` (meson install into the staging dir). Modern debhelper registers the `gtk-update-icon-cache` and `update-desktop-database` triggers automatically when a `hicolor` icon / `.desktop` file is installed — no manual maintainer scripts needed.

### Pattern 5: PKGBUILD (canonical meson)
```bash
# Maintainer: thallys <thallys.costa@livon.io>     # D-04
pkgname=arduis
pkgver=1.0.0
pkgrel=1
pkgdesc="Orquestra agentes de IA em paralelo sobre git worktrees"
arch=('any')
url="https://github.com/thallysrc/arduis"
license=('MIT')
depends=('python-gobject' 'gtk4' 'libadwaita' 'vte4' 'python')
makedepends=('meson')
source=(...)            # local tarball or git tag for D-06 "builds locally"
build()   { arch-meson "$pkgname-$pkgver" build; meson compile -C build; }
check()   { meson test -C build --print-errorlogs; }   # optional
package() { meson install -C build --destdir "$pkgdir"; }
# NO .install scriptlet — pacman hooks refresh icon/desktop caches (Pitfall 3)
```
`[CITED: wiki.archlinux.org/Meson_package_guidelines]`

### Anti-Patterns to Avoid
- **Leaking the dev `sys.path` hack into the installed launcher** — the installed `arduis` imports from site-packages; no path manipulation.
- **Relying on `gnome.post_install` to refresh caches in the packages** — it is DESTDIR-skipped; packages must use dh triggers / pacman hooks.
- **Adding an Arch `.install` scriptlet that calls `gtk-update-icon-cache`/`update-desktop-database`** — explicitly discouraged; pacman hooks already do it (Pitfall 3).
- **`Architecture: any` / arch-specific PKGBUILD** — wrong; this is pure-Python → `all` / `any`.
- **Putting packaging metadata in `pyproject.toml`** — keep it pytest-only (CONTEXT); metadata lives in meson/debian/PKGBUILD.
- **`pip install`-style entry_points / console_scripts** — not used; the launcher is a meson-installed wrapper (the app uses distro PyGObject, never a pip install).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| XDG install dirs (bindir/datadir/applications/metainfo/icons) | A Makefile with hardcoded paths | meson `get_option('bindir')` / `gnome` module conventions | meson + GNOME guidelines already encode them; portable across distros |
| DESTDIR staging for the packagers | Custom install script | meson `install` (honors DESTDIR) | both dh and makepkg expect this; meson does it natively |
| `.deb` build orchestration | Hand-written `debian/rules` targets | `dh $@ --buildsystem=meson` | dh auto-sequences configure/build/test/install for meson |
| Icon/desktop cache refresh | `.install` scriptlet (Arch) / postinst (deb) | pacman hooks (Arch) + dh triggers (deb) | both are automatic since modern tooling; manual calls are discouraged and namcap-flagged |
| Version threading | Editing the version in 3+ files | `meson.project_version()` → `configure_file` into launcher + metainfo | one source of truth (D-03) |

**Key insight:** Native packaging is a *thin* layer over meson for a pure-Python GNOME app. Almost every "I'll just script this" instinct is already a meson/dh/pacman feature; the work is wiring + correct dependency declarations, not logic.

## Common Pitfalls

### Pitfall 1: `importlib.resources` breaks if the package isn't installed as a real package
**What goes wrong:** `attention.py:324` does `files("arduis.hooks").joinpath("arduis_hook.py").read_text()`. If `arduis_hook.py` isn't installed as package data under an importable `arduis.hooks`, the hook-injection feature (STATUS-01) silently breaks at runtime — invisible to build-time validation.
**Why it happens:** Treating the install as "copy `.py` files somewhere on PATH" instead of installing a real package.
**How to avoid:** `python.install_sources(preserve_path:true, subdir:'arduis')` over the full tree INCLUDING `hooks/arduis_hook.py` and `hooks/__init__.py`. Add a smoke test: after `meson install --destdir`, run `python3 -c "import importlib.resources, sys; sys.path.insert(0,STAGE); import arduis.hooks; print(importlib.resources.files('arduis.hooks').joinpath('arduis_hook.py').read_text()[:1])"`.
**Warning signs:** Hook feature dead on an installed copy though it works from the repo.

### Pitfall 2: `gnome.post_install` is skipped under DESTDIR
**What goes wrong:** Relying on meson's post_install to update icon/desktop caches in the package → caches never refresh because both packagers set DESTDIR. Icon won't appear in the app grid.
**Why it happens:** `[CITED: mesonbuild.com/Gnome-module.html]` "scripts are skipped if DESTDIR is specified."
**How to avoid:** Keep `gnome.post_install` for dev installs, but let dh triggers (deb) and pacman hooks (Arch) handle the packaged case.
**Warning signs:** Fresh install shows generic icon until a manual `gtk-update-icon-cache`.

### Pitfall 3: Adding an Arch `.install` scriptlet for caches (CONTEXT D-05 over-specifies this)
**What goes wrong:** CONTEXT D-05 says "the AUR via a `.install` scriptlet" for `gtk-update-icon-cache`. Per current Arch guidelines this is **discouraged and namcap-flagged**.
**Why it happens:** Stale convention from pre-hook Arch.
**How to avoid:** `[CITED: wiki.archlinux.org/GNOME_Package_Guidelines]` "Do not call gtk-update-icon-cache in the .install file (updated via pacman hooks since gtk-update-icon-cache 3.20.3-2). Do not call update-desktop-database in the .install file (since desktop-file-utils 0.22-2)." → **ship NO `.install` scriptlet**; the hicolor SVG + `.desktop` install trigger the hooks automatically. Recommend the planner override D-05's `.install` detail.
**Warning signs:** namcap warns about unnecessary scriptlet calls.

### Pitfall 4: Existing metainfo FAILS appstream validation as-is
**What goes wrong:** `appstreamcli validate data/io.github.thallys.Arduis.metainfo.xml` → `✘ Validation failed: warnings: 1` — `url-homepage-missing`, plus it lacks the required `<release version="1.0.0">` (D-03).
**Why it happens:** The metainfo was authored in Phase 1 as a stub.
**How to avoid:** This phase MUST add `<url type="homepage">https://github.com/thallysrc/arduis</url>` AND a `<releases><release version="1.0.0" date="..."/></releases>` block before validation goes green. `[VERIFIED: appstreamcli 1.0.2 run this session]`
**Warning signs:** appstream validate non-zero in the build/lint gate.

### Pitfall 5: `.desktop` Categories hint
**What goes wrong:** `desktop-file-validate` emits a **hint** (not error): `Categories=Development;Utility;` has >1 main category → app may appear twice in the menu.
**How to avoid:** Optional cleanup — keep a single main category (e.g. `Development;`) or accept the hint (it passes validation). `[VERIFIED: desktop-file-validate 0.27 this session]`
**Warning signs:** Duplicate menu entries.

### Pitfall 6: VTE 0.76 API floor (cross-distro)
**What goes wrong:** Code using VTE APIs newer than 0.76 builds/runs on Arch (0.84) but crashes on Ubuntu (0.76).
**How to avoid:** Already a project constraint; packaging just declares `gir1.2-vte-3.91` (0.76). No new code here, but the UAT must run on real Ubuntu 24.04. `[CITED: CLAUDE.md §Version Compatibility]`

## Code Examples

### Single-source version → metainfo `<release>` and `--version`
```meson
# top meson.build
project('arduis', version: '1.0.0', license: 'MIT')   # D-03 single source
# data/meson.build — substitute into metainfo if you template it, OR add the
# <release> by hand and assert it matches meson.project_version() in a test.
metainfo = i18n_or_configure_file(...)   # configure_file with @VERSION@ optional
```
```python
# optional: arduis --version (single source via the generated launcher)
# launcher gets @VERSION@ from configure_file; print on --version.
```
`[CITED: mesonbuild.com — project()/configure_file()]`

### Criterion-4 grep test (HostRunner native no-op)
```python
# tests/test_packaging_native_noop.py
from arduis import host_runner
def test_flatpak_disabled():
    assert host_runner._FLATPAK is False
def test_wrap_argv_is_identity():
    r = host_runner.HostRunner()
    assert r.wrap_argv(["zsh", "-l", "-i"]) == ["zsh", "-l", "-i"]
```
`[VERIFIED: src/arduis/host_runner.py — _FLATPAK=False, wrap_argv returns list(argv)]` Confirmed no live `flatpak-spawn` in argv anywhere in `src/` (only docstring/comment mentions + the guarded `NotImplementedError` branch).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Arch `.install` calling `gtk-update-icon-cache`/`update-desktop-database` | pacman hooks auto-run them | gtk-update-icon-cache 3.20.3-2 / desktop-file-utils 0.22-2 | Drop the `.install` (overrides CONTEXT D-05) |
| `python-distutils` debhelper buildsystem | `pybuild` (irrelevant here — we use `meson`) | recent debhelper | N/A; we use `--buildsystem=meson` |
| Flatpak + bundled VTE/simdutf/fast_float | native `.deb`+AUR, system VTE | 2026-06-08 pivot | This whole phase; no bundling |

**Deprecated/outdated:**
- `flatpak-spawn --host` path: deferred to v2; `_FLATPAK=False` guard keeps it dead.
- `build-dir/` + `.flatpak-builder/` at repo root: stale Flatpak artifacts (gitignored). Harmless but the planner may note they exist.

## Runtime State Inventory

> This is a packaging phase (adds build files; installs an existing pure-Python app). No data migration / rename. Inventory included for completeness.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no datastores keyed on a renamed string; this phase renames nothing. | None |
| Live service config | None — no external service config changes. The Claude Code hook (`~/.claude/settings.json`) is registered at runtime by the app, not by the package. | None |
| OS-registered state | The package REGISTERS new OS state: `.desktop` in `/usr/share/applications`, metainfo in `/usr/share/metainfo`, hicolor icon, `arduis` on PATH. Caches (icon/desktop) refreshed by dh triggers (deb) / pacman hooks (Arch). | Ensure cache-refresh hooks fire (see Pitfalls 2,3) |
| Secrets/env vars | None. (App injects `ARDUIS_STATE_FILE` per terminal at runtime — not a packaging concern.) | None |
| Build artifacts | `build-dir/`, `.flatpak-builder/` (stale Flatpak, gitignored); `src/arduis/**/__pycache__` (gitignored). meson installs from `src/`, not these. | None (verify `.deb`/PKGBUILD don't pick up `__pycache__`) |

## Environment Availability

> Probed on the Ubuntu 24.04.3 LTS dev host this session.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| meson | build (both) | ✗ | apt candidate 1.3.2 | `apt install meson` (Wave-0 / build step) |
| ninja-build | meson backend | ✗ | — | `apt install ninja-build` |
| debhelper | `.deb` build | ✗ | apt candidate 13.14.1 | `apt install debhelper` |
| dpkg-buildpackage | `.deb` build | ✓ | (dpkg-dev present) | — |
| lintian | `.deb` lint | ✗ | — | `apt install lintian` (lint gate) |
| desktop-file-validate | desktop lint | ✓ | 0.27 | — |
| appstreamcli | metainfo lint | ✓ | 1.0.2 | — |
| appstream-util | metainfo lint (alt) | ✗ | — | use `appstreamcli validate` (present) |
| gtk-update-icon-cache | icon cache | ✓ | (gtk4) | — |
| python3 | runtime/build | ✓ | 3.12.3 | — |
| VTE-3.91 GI | runtime import check | ✓ | 0.76 (gir1.2-vte-3.91) | — |
| namcap | PKGBUILD lint (Arch) | ✗ (Arch-only) | — | manual on Arch box / skip |
| makepkg | AUR build (Arch) | ✗ (Arch-only) | — | **manual hardware gate on real Arch** |

**Missing dependencies with no fallback (Arch side):** `makepkg`/`namcap`/`pacman` don't exist on the Ubuntu dev host → the **AUR build + install + Wayland launch is a genuine human hardware gate on a real Arch machine**. Same for the `.deb` clean-`apt install` + Wayland launch on real Ubuntu 24.04.

**Missing dependencies with fallback (Ubuntu side, all `apt install`-able):** meson, ninja-build, debhelper, lintian — install these to make the `.deb` build + lint gate runnable in this environment.

## Validation Architecture

> nyquist_validation is enabled (config). VALIDATION.md can be derived from the maps below.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing; `pyproject.toml` `testpaths=["tests"]`, `pythonpath=["src"]`) |
| Config file | `/home/thallysrc/Projects/arduis/pyproject.toml` (pytest-only — keep it) |
| Quick run command | `python3 -m pytest -q tests/test_packaging_*.py` |
| Full suite command | `python3 -m pytest -q` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DIST-03 | `.deb` BUILDS from repo | build/integration | `dpkg-buildpackage -us -uc -b` (after `apt install meson ninja-build debhelper`) | ❌ Wave 0 (needs `debian/`) |
| DIST-03 | `.deb` lints clean | lint | `lintian ../arduis_1.0.0_all.deb` | ❌ needs lintian + the .deb |
| DIST-03 | `.deb` declares correct Depends | static | grep `debian/control` for the 6 runtime deps + `${misc:Depends}`; assert `Architecture: all` | ❌ Wave 0 |
| DIST-02 | PKGBUILD parses + declares deps | static | `bash -n PKGBUILD`; grep `arch=('any')`, the 5 `depends`, `makedepends=(meson)`; (real build = manual on Arch) | ❌ Wave 0 |
| DIST-02/03 | meson installs a correct file tree | integration | `meson setup b && meson install -C b --destdir /tmp/st && test -x /tmp/st/usr/bin/arduis && test -f /tmp/st/usr/.../io.github.thallys.Arduis.svg` | ❌ Wave 0 |
| DIST-02/03 | installed pkg is importable (importlib.resources hook) | integration | `PYTHONPATH=/tmp/st/usr/lib/python3*/site-packages python3 -c "import arduis.hooks, importlib.resources; importlib.resources.files('arduis.hooks').joinpath('arduis_hook.py').read_text()"` | ❌ Wave 0 |
| DIST-02/03 | desktop entry valid | lint | `desktop-file-validate data/io.github.thallys.Arduis.desktop` | ✅ (passes w/ hint) |
| DIST-02/03 | metainfo valid (homepage + 1.0.0 release) | lint | `appstreamcli validate data/io.github.thallys.Arduis.metainfo.xml` | ❌ currently FAILS (Pitfall 4) |
| DIST-03 (Crit 4) | HostRunner native no-op, no live flatpak-spawn | unit | `python3 -m pytest tests/test_packaging_native_noop.py` + `! grep -rn 'flatpak-spawn' src/ \| grep -v '#'` | ❌ Wave 0 (test file) |
| DIST-03 (Crit 3) | version single-sourced | unit | assert metainfo `<release version>` == meson project_version | ❌ Wave 0 |
| DIST-04 | clean `apt install ./arduis_1.0.0_all.deb` + Wayland launch + VTE works on real Ubuntu 24.04 | **manual UAT** | human hardware gate | n/a |
| DIST-04 | `makepkg -si` + Wayland launch + VTE works on real Arch | **manual UAT** | human hardware gate (no makepkg on dev host) | n/a |

### Sampling Rate
- **Per task commit:** `python3 -m pytest -q tests/test_packaging_*.py` + the relevant lint (`desktop-file-validate` / `appstreamcli validate`).
- **Per wave merge:** meson DESTDIR install smoke + importlib.resources import check + (if deps installed) `dpkg-buildpackage` + `lintian`.
- **Phase gate:** full pytest green; meson install tree correct; `.deb` builds+lints; PKGBUILD parses+declares; THEN `/gsd-verify-work`. Real-hardware install/launch is the separate live UAT (matches prior phases' "UAT pending").

### Wave 0 Gaps
- [ ] `tests/test_packaging_native_noop.py` — Criterion 4 (`_FLATPAK is False`, identity wrap, no live flatpak-spawn).
- [ ] `tests/test_packaging_version.py` — metainfo `<release>` == `meson.project_version()`.
- [ ] `tests/test_packaging_install_tree.py` — meson `--destdir` stage produces `bin/arduis`, the SVG, the package, and an importable `arduis.hooks`.
- [ ] Build-dep install step: `apt install meson ninja-build debhelper lintian` (not present on dev host).
- [ ] Fix metainfo (homepage + 1.0.0 release) so `appstreamcli validate` passes — itself a phase task, also a Wave-0 prerequisite for the lint gate.
- [ ] No conftest changes needed (existing pytest config covers `tests/`).

## Project Constraints (from CLAUDE.md)

- **Native only in v1; Flatpak is v2.** No `flatpak-spawn`, no VTE bundling, no simdutf/fast_float pins.
- **System PyGObject only** — never `pip install PyGObject`; declare distro deps.
- **Snap REJECTED** — do not add a Snap channel.
- **VTE from the system**, code to the **0.76 API floor** (Ubuntu) so one codebase covers Arch 0.84.
- **Exact dep lists** per CLAUDE.md §Packaging (reproduced in §Standard Stack) — Ubuntu `gir1.2-vte-3.91`/`libvte-2.91-gtk4-0` 0.76, `python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`, `python3` ≥3.12; Arch `vte4`, `python-gobject`, `gtk4`, `libadwaita`, `python`.
- **Shell-out, no docker/python libs** (not touched here).
- **GSD workflow enforcement** — packaging files are created through the GSD execution flow.
- **Method = Accelerate/DORA** — small shippable degraus; this is the final v1 degrau (team-installable).

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Arch `vte4` is 0.84 and `python-gobject`/`gtk4`/`libadwaita` cover the GI typelibs | Standard Stack (Arch) | Could not verify on this Ubuntu host (no pacman). Cited from CLAUDE.md + archlinux.org. Low risk — these are core Arch packages. |
| A2 | Modern debhelper auto-registers icon-cache/desktop-db triggers when a hicolor icon/.desktop is installed via meson | Pattern 4 / Pitfall 2 | If not auto-triggered, the `.deb` needs an explicit `dh_installdeb`/trigger or `postinst`. Verify in the build UAT (icon appears after `apt install`). |
| A3 | `Architecture: all` is accepted by lintian for a meson-built pure-Python pkg (meson sometimes implies arch-any) | Standard Stack / DIST-03 | If lintian/dpkg complain about arch-any artifacts, may need `Architecture: any` or a meson tweak. Caught by the lint gate. |
| A4 | `python.install_sources` lands in a path the system `python3` imports by default (purelib) | Pattern 1 | If meson installs to a versioned path not on the default sys.path, the launcher needs a path addition. Caught by the importlib.resources import test (Wave 0). |

## Open Questions

1. **Source format for `debian/` — native vs quilt, and the `source=()` for PKGBUILD under D-06 ("builds locally").**
   - What we know: app is built from its own repo; native (`3.0 (native)`) is simplest. PKGBUILD `source=()` can point at a local tarball or a git tag.
   - What's unclear: whether the PO wants the PKGBUILD `source` to reference a not-yet-published GitHub release tarball (publishing is deferred) or a local path for now.
   - Recommendation: native `debian/source/format`; PKGBUILD `source=("$pkgname-$pkgver.tar.gz")` documented as "produced from `git archive` locally" until a GitHub release exists (v1.1 publish). Keeps D-06 "builds locally" honest.

2. **Override CONTEXT D-05's Arch `.install` scriptlet?**
   - What we know: current Arch guidelines say do NOT call the cache tools in `.install` (pacman hooks do it).
   - Recommendation: **ship NO `.install`**; note the override in the plan. (Already flagged in Pitfall 3.)

3. **`compat` location:** `debian/compat` file vs `debhelper-compat (= 13)` in `Build-Depends`.
   - Recommendation: use `debhelper-compat (= 13)` in control (modern style); skip the `debian/compat` file. Either works.

## Sources

### Primary (HIGH confidence)
- `[VERIFIED]` Host probes (Ubuntu 24.04.3 LTS, this session): `apt-cache policy` for gir1.2-vte-3.91 0.76.0, libvte-2.91-gtk4-0 0.76.0, gir1.2-adw-1 1.5.0, gir1.2-gtk-4.0 4.14.5, python3-gi 3.48.2, meson 1.3.2 (candidate), debhelper 13.14.1 (candidate); `python3 --version` 3.12.3; `desktop-file-validate` 0.27 (passes w/ hint); `appstreamcli validate` 1.0.2 (FAILS — homepage+release missing); `Vte 3.91` import OK.
- `[VERIFIED]` Codebase scan: 34 `.py` files, zero non-`.py` files in `src/arduis`, `importlib.resources` hook load at `attention.py:324`, `host_runner._FLATPAK=False`, no live `flatpak-spawn` in argv.
- [mesonbuild.com/Python-module.html](https://mesonbuild.com/Python-module.html) — `install_sources`, `pure`, `subdir`, `preserve_path`.
- [mesonbuild.com/Gnome-module.html](https://mesonbuild.com/Gnome-module.html) — `gnome.post_install` (DESTDIR-skipped).
- [wiki.archlinux.org/Meson_package_guidelines](https://wiki.archlinux.org/title/Meson_package_guidelines) — `arch-meson`/`meson compile`/`meson install --destdir`.
- [wiki.archlinux.org/GNOME_Package_Guidelines](https://wiki.archlinux.org/index.php/GNOME_Package_Guidelines) — no `.install` icon/desktop cache calls (pacman hooks).
- [man7.org/.../debhelper.7](https://www.man7.org/linux/man-pages/man7/debhelper.7.html) — `dh $@ --buildsystem=meson`.
- `[CITED]` CLAUDE.md §Packaging / §Version Compatibility / §What NOT to Use — authoritative dep lists + pins.

### Secondary (MEDIUM confidence)
- [archlinux.org/packages/extra/x86_64/vte4](https://archlinux.org/packages/extra/x86_64/vte4/) — vte4 0.84 (cited via CLAUDE.md; not host-verifiable).

## Metadata

**Confidence breakdown:**
- Standard stack (Ubuntu): HIGH — every package version verified on the actual target host this session.
- Standard stack (Arch): MEDIUM — cited from CLAUDE.md + ArchWiki; no pacman on dev host (A1).
- Architecture / meson patterns: HIGH — official meson + ArchWiki + debhelper docs.
- Pitfalls: HIGH — Pitfalls 2,4,5 reproduced live this session; 3 from official ArchWiki.

**Research date:** 2026-06-15
**Valid until:** ~2026-07-15 (stable distro tooling; re-check Arch vte4 if a v2 Flatpak channel is reconsidered).
