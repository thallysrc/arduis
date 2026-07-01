---
phase: 09-packaging-aur-deb
plan: 02
subsystem: packaging
tags: [packaging, meson, purelib, launcher, xdg, importlib-resources]
requires:
  - "Validated AppStream metainfo (homepage url + 1.0.0 release) — 09-01"
  - "Scalable app icon at the hicolor path — 09-01"
  - "Packaging test files (install-tree, version) — 09-01"
provides:
  - "meson.build single build/install definition (D-01) both packages wrap"
  - "purelib install of the full arduis package (incl. hooks/arduis_hook.py) — import + importlib.resources work with no sys.path hack"
  - "generated bin/arduis launcher importing arduis.main:main directly"
  - ".desktop/.metainfo/SVG installed into XDG dirs; version single-sourced 1.0.0"
affects:
  - "meson.build"
  - "src/meson.build"
  - "data/meson.build"
  - "data/arduis.in"
tech-stack:
  added:
    - "meson + ninja (build/install definition; system 1.3.2 on Ubuntu host)"
  patterns:
    - "py.install_sources(..., pure:true, preserve_path:true) → whole package into purelib (no subdir double-nesting)"
    - "configure_file-generated launcher with @VERSION@ single-sourced from meson.project_version()"
    - "gnome.post_install for dev only — DESTDIR-skipped; packagers use dh triggers / pacman hooks"
    - "default_options: ['prefix=/usr'] so the launcher lands at /usr/bin/arduis (distro packaging prefix)"
key-files:
  created:
    - "meson.build"
    - "src/meson.build"
    - "data/meson.build"
    - "data/arduis.in"
  modified: []
decisions:
  - "Install via purelib install_sources with preserve_path (no subdir:'arduis') — the preserved path already carries the arduis/ package dir; adding subdir would double-nest"
  - "meson_version bumped to >= 0.63.0 (preserve_path requires it); placed BEFORE version: in project() so the version-equality test's greedy regex resolves to 1.0.0, not meson_version"
  - "default_options prefix=/usr (not meson default /usr/local) — matches the install-tree test's usr/bin/arduis assertion and the distro packaging convention both downstream packages expect"
metrics:
  duration: "~12m"
  completed: "2026-06-15"
  tasks: 2
  files: 4
---

# Phase 9 Plan 02: meson build/install definition Summary

Authored the single meson build/install definition (D-01) that the `.deb` (Plan 03) and AUR
PKGBUILD (Plan 04) wrap thinly. The whole `arduis` package — including `hooks/arduis_hook.py`
and `swarm/` — installs into the Python purelib via `py.install_sources(preserve_path:true)`, so
`import arduis` and `importlib.resources.files("arduis.hooks")` work on the installed copy with
ZERO `sys.path` hacking (RESEARCH Pitfall 1). A `configure_file`-generated `bin/arduis` launcher
imports `arduis.main:main` directly (no dev shim leak); the `.desktop`/`.metainfo`/SVG install into
their XDG dirs; the version is single-sourced 1.0.0 from `meson.build`.

## What Was Built

- **`meson.build` (root):** `project('arduis', version: '1.0.0', license: 'MIT')` (D-03 single
  source) with `default_options: ['prefix=/usr']` so the launcher lands at `/usr/bin/arduis` (the
  distro packaging prefix both downstream packages expect; meson's default `/usr/local` would put
  it at `/usr/local/bin`). `subdir('src')` + `subdir('data')`. No compiled targets (pure Python).
- **`src/meson.build`:** `py.install_sources(<34 explicit .py files>, pure: true,
  preserve_path: true)` — every module enumerated (meson has no recursive glob) INCLUDING
  `arduis/hooks/__init__.py`, `arduis/hooks/arduis_hook.py`, `arduis/swarm/__init__.py`.
  `preserve_path` keeps the `arduis/` + `hooks/` + `swarm/` nesting so the hook ships as package
  data. Plus the `configure_file`-generated launcher (`@VERSION@` from `meson.project_version()`,
  installed `rwxr-xr-x` to `bindir`).
- **`data/arduis.in`:** launcher template — `#!/usr/bin/env python3`, `from arduis.main import
  main; raise SystemExit(main())`, a minimal `--version` short-circuit, and NO `sys.path.insert`
  (the dev shim's hack must not leak into the installed launcher).
- **`data/meson.build`:** `install_data` of the `.desktop` → `datadir/applications`, the
  `.metainfo.xml` → `datadir/metainfo`, the SVG → `datadir/icons/hicolor/scalable/apps`; plus
  `gnome.post_install(gtk_update_icon_cache:true, update_desktop_database:true)` marked
  DEV-CONVENIENCE-ONLY (DESTDIR-skipped per Pitfall 2). No Arch `.install` (Pitfall 3).

## Verification Results

- `meson setup /tmp/arduis-mb .` → configures clean, "Project version: 1.0.0", no warnings.
- `meson install --destdir /tmp/arduis-stage` → stages `usr/bin/arduis` (executable), the full
  package at `usr/lib/python3/dist-packages/arduis/` (incl. `hooks/arduis_hook.py`,
  `swarm/__init__.py`), and the three data assets in their XDG dirs. The two `gnome.post_install`
  scripts correctly print "Skipping custom install script because DESTDIR is set" (Pitfall 2
  confirmed live).
- Launcher contains NO `sys.path.insert`; `@VERSION@` substituted to `1.0.0`; `--version` prints
  `arduis 1.0.0`.
- `PYTHONPATH=<stage>/usr/lib/python3/dist-packages python3 -c "import importlib.resources,
  arduis.hooks; ...read_text()[:1]"` → prints `#` (hook resolves via importlib.resources on the
  staged copy — Pitfall 1 mitigated).
- `pytest -q tests/test_packaging_install_tree.py tests/test_packaging_version.py` → 4 passed
  (both previously skip-guarded tests now un-skip and pass, including the meson↔metainfo version
  equality assertion).
- Full suite `pytest` → **436 passed** (only pre-existing `os.fork` DeprecationWarnings in
  `test_exit_decode.py`, unrelated to this plan).
- `run.sh` / `src/main.py` untouched (last modified Phase 02); dev import
  (`PYTHONPATH=src python -c "import arduis.main"`) still works — dev flow unaffected.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] meson_version bump + ordering to satisfy the version-equality test**
- **Found during:** Task 1
- **Issue:** (a) `preserve_path` in `python.install_sources` was introduced in meson 0.63.0;
  the initial `meson_version: '>= 0.59.0'` produced a feature-version warning. (b) After bumping
  to `>= 0.63.0`, `test_meson_version_matches_metainfo`'s greedy regex
  `project\([^)]*version\s*:` matched `meson_version: '>= 0.63.0'` (the later `version:`-suffixed
  key) instead of `version: '1.0.0'`, failing the equality assertion.
- **Fix:** Bumped `meson_version` to `>= 0.63.0` (both target distros far exceed it: Ubuntu 24.04
  ships 1.3.2, Arch newer) AND placed `meson_version:` BEFORE `version:` in `project()` so the
  greedy `[^)]*` lands on `version: '1.0.0'` as the test expects. The test (a Plan 01 contract)
  passes unchanged — no test edit.
- **Files modified:** meson.build
- **Commit:** 7e80cfb

### Discretion exercised (within plan bounds)

- **No `subdir: 'arduis'` on `install_sources`** — the plan's interface sketch showed
  `subdir:'arduis'` with files listed relative to `src/arduis/`. I instead list files relative to
  `src/` as `arduis/<module>.py` with `preserve_path: true` and NO `subdir` — the preserved path
  already carries the `arduis/` package dir, so adding `subdir:'arduis'` would double-nest to
  `arduis/arduis/...`. Verified the staged tree is `dist-packages/arduis/<module>.py` (correct).
- **`prefix=/usr`** added as a `default_option` so the install-tree test's `usr/bin/arduis`
  assertion holds (meson's default `/usr/local` would stage `usr/local/bin/arduis`); this is also
  the correct distro packaging prefix both Plan 03 (dh stages to `debian/arduis/usr`) and Plan 04
  (`--destdir "$pkgdir"`) expect.

## Commits

- `7e80cfb` feat(09-02): meson purelib install + generated launcher (no sys.path hack)
- `4be368f` feat(09-02): install .desktop/.metainfo/SVG into XDG dirs + dev-only gnome.post_install

## Self-Check: PASSED

- All 4 created files present on disk (`meson.build`, `src/meson.build`, `data/meson.build`,
  `data/arduis.in`).
- Both task commits present in git history (`7e80cfb`, `4be368f`).
- Key links verified live: launcher `from arduis.main import main` (no `sys.path.insert`);
  staged `arduis/hooks/arduis_hook.py` resolves via `importlib.resources`; meson
  `project(... version: '1.0.0')` equals the metainfo `<release>`.
