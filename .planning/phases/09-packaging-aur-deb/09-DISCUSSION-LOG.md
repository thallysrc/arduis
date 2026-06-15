# Phase 9: Packaging (AUR + .deb) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-15
**Phase:** 09-packaging-aur-deb
**Mode:** --chain (interactive discuss → auto plan+execute)
**Areas discussed:** Build/install system, Version + maintainer, App icon, Distribution + CI

---

## Build / install system

| Option | Description | Selected |
|--------|-------------|----------|
| meson + ninja | GNOME-standard; .deb (dh+meson) + AUR (meson/ninja) wrap it thinly; one source of truth; launcher + python pkg + data install | ✓ |
| Script de install + Makefile | Simpler, less idiomatic; reimplements DESTDIR/XDG staging meson gives free | |
| setuptools/pip | Rejected by CLAUDE.md — wrong execution model (distro PyGObject, not pip) | |

**User's choice:** meson + ninja.

## Version + maintainer

| Option | Description | Selected |
|--------|-------------|----------|
| 1.0.0 + git identity | 1.0.0 single-sourced in meson.build; Maintainer thallys <thallys.costa@livon.io> from git | ✓ |
| 1.0.0 + outro email | Same version, different public/personal maintainer email | |

**User's choice:** 1.0.0 + git identity. Noted: work email goes public in package metadata (accepted).

## App icon

| Option | Description | Selected |
|--------|-------------|----------|
| Gerar SVG simples | Generate a geometric dracula-palette SVG at the hicolor path so the package is complete | ✓ |
| Sem ícone por enquanto | Ship iconless (generic launcher icon); strip the icon ref | |
| Fornecer depois | User provides a designed icon later | |

**User's choice:** generate a simple SVG now (replaceable later).

## Distribution + CI

| Option | Description | Selected |
|--------|-------------|----------|
| Só as definições + build local | PKGBUILD + debian/ + meson that build locally + README; publish/host manual (v1.1) | ✓ |
| + GitHub Actions | Add CI to build the .deb + lint PKGBUILD on push | |
| Pipeline completo de release | Publish to AUR + apt repo | |

**User's choice:** definitions + local build only; publish/CI deferred to v1.1.

## Claude's Discretion
- Exact meson layout + launcher entry mechanism; per-distro dependency lists (per CLAUDE.md table);
  the SVG artwork; local metainfo/desktop validation.

## Deferred Ideas
- Flatpak (v2 / DIST-01); AUR publish + .deb hosting (manual / v1.1); CI workflow (v1.1);
  a professionally-designed icon.
