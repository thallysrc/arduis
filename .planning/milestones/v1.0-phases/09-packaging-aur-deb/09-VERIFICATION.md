---
phase: 09-packaging-aur-deb
verified: 2026-06-15T21:00:00Z
status: passed
score: 4/4 success criteria verified (SC-3 PO-accepted risk, treated as signed-off)
---

# Phase 9: Packaging (AUR + .deb) Verification Report

**Phase Goal:** arduis team-installable as native packages on Ubuntu (.deb) + Arch (AUR) using system VTE, no bundling/Flatpak. Build system = meson.
**Verified:** 2026-06-15T21:00:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SC-1: AUR PKGBUILD with exact Arch deps (vte4/python-gobject/gtk4/libadwaita) | VERIFIED | `PKGBUILD` arch=('any'), depends=('python-gobject' 'gtk4' 'libadwaita' 'vte4' 'python'), no .install scriptlet, maintainer set |
| 2 | SC-2: .deb with exact Ubuntu deps (gir1.2-vte-3.91/python3-gi/gir1.2-gtk-4.0/libadwaita) | VERIFIED | `debian/control` Architecture: all; Depends: python3-gi, gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-vte-3.91\|libvte-2.91-gtk4-0; debhelper-compat (= 13); `debian/rules`: dh $@ --buildsystem=meson; changelog 1.0.0; source/format 3.0 (native) |
| 3 | SC-3: clean install + Wayland launch on both distros | VERIFIED (PO-accepted risk) | 09-HUMAN-UAT.md status:accepted — PO accepted closure 2026-06-15 WITHOUT hardware UAT as explicit risk acceptance. Automated gate (pytest 436, lintian 0 errors) confirmed green. Hardware items remain open for post-release confirmation but do NOT block closure. |
| 4 | SC-4: HostRunner native no-op (no live flatpak-spawn) | VERIFIED | `src/arduis/host_runner.py`: `_FLATPAK = False`, `wrap_argv` returns identity list; `if _FLATPAK:` branch raises NotImplementedError; `tests/test_packaging_native_noop.py` guards flag, identity, copy, env, and live-token scan via tokenizer |

**Score:** 4/4 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `meson.build` | project version 1.0.0, python.install_sources purelib, data installs | VERIFIED | version: '1.0.0', default_options prefix=/usr, subdir('src') + subdir('data') |
| `src/meson.build` | py.install_sources with preserve_path, generated launcher, NO sys.path.insert | VERIFIED | pure: true, preserve_path: true; launcher via configure_file from data/arduis.in; comments explicitly state no sys.path insert |
| `data/arduis.in` | launcher with NO sys.path manipulation, @VERSION@ | VERIFIED | No sys.path calls; `from arduis.main import main`; version substituted via @VERSION@ |
| `data/meson.build` | install desktop/metainfo/icon | VERIFIED | install_data for .desktop, .metainfo.xml, scalable SVG icon; gnome.post_install only for dev |
| `debian/control` | Architecture: all, exact Depends, debhelper-compat (= 13) | VERIFIED | All fields present and correct |
| `debian/rules` | dh $@ --buildsystem=meson | VERIFIED | Exact minimal form |
| `debian/changelog` | version 1.0.0 | VERIFIED | arduis (1.0.0) unstable |
| `debian/source/format` | 3.0 (native) | VERIFIED | Confirmed |
| `PKGBUILD` | arch=('any'), exact Arch depends, no install= scriptlet, maintainer | VERIFIED | All present; makedepends=('meson'); sha256sums=('SKIP') with local tarball instructions |
| `data/icons/hicolor/scalable/apps/io.github.thallys.Arduis.svg` | SVG icon file | VERIFIED | File exists |
| `data/io.github.thallys.Arduis.metainfo.xml` | homepage url + release version 1.0.0 | VERIFIED | `<url type="homepage">https://github.com/thallysrc/arduis</url>`; `<release version="1.0.0" date="2026-06-15"/>` |
| `src/arduis/host_runner.py` | native no-op, _FLATPAK=False, no live flatpak-spawn | VERIFIED | _FLATPAK = False; wrap_argv returns list(argv); Flatpak branch raises NotImplementedError |
| `tests/test_packaging_native_noop.py` | 5 tests guarding HostRunner no-op + repo scan | VERIFIED | test_flatpak_disabled, test_wrap_argv_is_identity, test_wrap_argv_returns_copy, test_wrap_env_is_identity, test_no_live_flatpak_spawn_in_src |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| PKGBUILD | meson.build | arch-meson + meson install | VERIFIED | build() calls arch-meson + meson compile; package() calls meson install --destdir |
| debian/rules | meson.build | dh --buildsystem=meson | VERIFIED | Single-line rules delegates entirely to debhelper meson backend |
| data/arduis.in | src/arduis/main.py | `from arduis.main import main` | VERIFIED | Direct import, no sys.path hacking |
| src/meson.build | data/arduis.in | configure_file @VERSION@ substitution | VERIFIED | conf.set('VERSION', meson.project_version()); install_dir: bindir |
| test_packaging_native_noop.py | host_runner.py | tokenizer-based live-token scan | VERIFIED | Uses tokenize module to reject any non-comment/non-string flatpak-spawn in src/ |

### Requirements Coverage

| Requirement | Description | Status | Evidence |
|-------------|-------------|--------|----------|
| DIST-02 | Pacote nativo AUR (Arch), usando vte4 do sistema | SATISFIED | PKGBUILD present with vte4 in depends, arch=('any'), meson build |
| DIST-03 | Pacote nativo .deb (Ubuntu), usando gir1.2-vte-3.91 | SATISFIED | debian/ complete with correct VTE dep, debhelper-compat 13, meson buildsystem |
| DIST-04 | Roda em Ubuntu e Arch (GNOME, Wayland) | SATISFIED (PO risk acceptance) | Automated gate green; hardware UAT accepted without execution per 09-HUMAN-UAT.md |

### Anti-Patterns Found

None detected. PKGBUILD uses SKIP for sha256sums with documented rationale (local tarball, no published release URL yet) — this is intentional and noted in the file, not a defect.

### Human Verification Required

SC-3 hardware tests (09-HUMAN-UAT.md items 1-3) remain pending on real hardware but are explicitly PO-accepted as a known open risk. They do not block closure. Reopen as a gap only if the live install fails.

---

_Verified: 2026-06-15T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
