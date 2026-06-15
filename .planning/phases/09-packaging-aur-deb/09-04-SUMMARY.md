---
phase: 09-packaging-aur-deb
plan: 04
subsystem: packaging
tags: [aur, arch, pkgbuild, meson, readme, dist-02, dist-04]
requires:
  - "meson.build (09-02): single build/install def the PKGBUILD wraps"
provides:
  - "PKGBUILD: Arch native package definition (DIST-02)"
  - "README.md: Ubuntu + Arch build/install docs (DIST-04, D-06)"
affects:
  - "Arch team-install story (makepkg -si) — real build is Plan-05 hardware UAT"
tech-stack:
  added: []
  patterns:
    - "arch-meson + meson compile + meson install --destdir (ArchWiki Meson guidelines)"
    - "arch=('any') for pure-Python package; no .install scriptlet (pacman hooks)"
    - "local git-archive source tarball, sha256sums=SKIP (D-06, publish deferred v1.1)"
key-files:
  created:
    - PKGBUILD
    - README.md
  modified: []
decisions:
  - "PKGBUILD ships NO .install scriptlet — pacman hooks refresh icon/desktop caches (RESEARCH Pitfall 3, overrides CONTEXT D-05)"
  - "source from local git archive tarball with sha256sums=SKIP until a published GitHub release exists (D-06 / Open Q1)"
metrics:
  duration: ~6m
  tasks: 2
  files: 2
  completed: 2026-06-15
---

# Phase 9 Plan 04: Arch PKGBUILD + README Packaging Section Summary

Authored the Arch `PKGBUILD` (DIST-02) — a thin `arch-meson`/`meson compile`/`meson install --destdir` wrapper over the Plan-02 meson definition, `arch=('any')`, the exact 5 CLAUDE.md Arch system deps, `pkgver=1.0.0`, maintainer comment, NO `.install` scriptlet — and a new `README.md` documenting team-install on both Ubuntu (`.deb`) and Arch (AUR) plus the dev `run.sh` flow.

## What Was Built

### Task 1 — PKGBUILD (commit 31952fb)
- `# Maintainer: thallys <thallys.costa@livon.io>` (D-04), `pkgname=arduis`, `pkgver=1.0.0` (D-03), `pkgrel=1`, pkgdesc, `arch=('any')` (pure Python), `url=https://github.com/thallysrc/arduis`, `license=('MIT')`.
- `depends=('python-gobject' 'gtk4' 'libadwaita' 'vte4' 'python')` — the exact CLAUDE.md §Packaging Arch list (system VTE 0.84, never pip). `makedepends=('meson')` (pulls ninja).
- `source=("$pkgname-$pkgver.tar.gz")` + `sha256sums=('SKIP')`, documented as produced locally via `git archive --prefix=arduis-1.0.0/` until a published GitHub release exists (D-06 / Open Q1).
- `build()` → `arch-meson "$pkgname-$pkgver" build; meson compile -C build`; `check()` → `meson test -C build --print-errorlogs`; `package()` → `meson install -C build --destdir "$pkgdir"`.
- **NO `.install` scriptlet** — pacman hooks refresh icon/desktop caches (RESEARCH Pitfall 3; overrides CONTEXT D-05's `.install` mention).

### Task 2 — README.md packaging section (commit eae91ef)
- New file (none existed): project intro (core value) + native-only/no-Flatpak/no-Snap note.
- **Ubuntu (.deb):** `sudo apt install meson ninja-build debhelper` → `dpkg-buildpackage -us -uc -b` → `../arduis_1.0.0_all.deb` → `sudo apt install`; runtime-deps note (system VTE 0.76, no pip/Flatpak).
- **Arch (AUR):** `git archive` tarball → `makepkg -si`; runtime-deps note + no-`.install` note.
- **Dev:** `./run.sh` / `python3 src/main.py` unchanged.
- Publishing (AUR push / apt repo) noted as deferred to v1.1 (D-06).

## Verification

| Check | Result |
|-------|--------|
| `bash -n PKGBUILD` | PASS (parses clean) |
| `grep arch=('any')` | PASS |
| `grep depends=(...5 exact...)` | PASS |
| `grep makedepends=('meson')` | PASS |
| `grep pkgver=1.0.0` | PASS |
| `grep thallys.costa@livon.io` | PASS |
| `grep arch-meson` / `meson install -C build --destdir` | PASS |
| `! grep ^install=` (no .install) | PASS |
| README has dpkg-buildpackage / makepkg / apt install / arch / ubuntu | PASS |
| Full pytest suite | 436 passed, 0 failed (3 pre-existing fork DeprecationWarnings) |

The real `makepkg -si` build + Wayland launch on Arch is the Plan-05 hardware UAT — `makepkg`/`pacman`/`namcap` do not exist on this Ubuntu dev host, so only the parse + static-dep assertions are automatable here (as the plan scopes).

## Threat Mitigations Applied

- **T-09-10 (Tampering, source):** `source` is a LOCAL git-archive tarball (no remote URL to swap); `sha256sums=('SKIP')` only because locally produced — documented; no network fetch in `build()`.
- **T-09-11 (EoP, build/package + no .install):** `build()`/`package()` are the canonical arch-meson/meson lines — no `curl|sh`, no `eval`; NO `.install` scriptlet runs as root at install.
- **T-09-12 (Tampering, depends):** `depends` lists ONLY the CLAUDE.md Arch system deps; no pip wheel; `arch=('any')` (no native objects).

## Deviations from Plan

None — plan executed exactly as written. (The "no `.install` scriptlet" choice is itself the plan's explicit override of CONTEXT D-05 per RESEARCH Pitfall 3, not a deviation introduced here.)

## Self-Check: PASSED
- FOUND: PKGBUILD
- FOUND: README.md
- FOUND commit: 31952fb (PKGBUILD)
- FOUND commit: eae91ef (README)
