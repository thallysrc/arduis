---
phase: 09-packaging-aur-deb
plan: 01
subsystem: packaging
tags: [packaging, appstream, metainfo, icon, tests, meson-prep]
requires: []
provides:
  - "Validated AppStream metainfo (homepage url + 1.0.0 release)"
  - "Scalable app icon at the hicolor path the .desktop/.metainfo reference"
  - "Three packaging test files (native no-op, version, install-tree) for Plans 02-04 gates"
affects:
  - "data/io.github.thallys.Arduis.metainfo.xml"
  - "data/io.github.thallys.Arduis.desktop"
  - "tests/"
tech-stack:
  added: []
  patterns:
    - "appstreamcli validate --no-net for structural metainfo validation (network reachability deferred with publish)"
    - "tokenize-based source scan to distinguish live code from docstring/comment mentions"
    - "skip-guarded forward-looking tests (skip until meson.build lands in Plan 02)"
key-files:
  created:
    - "data/icons/hicolor/scalable/apps/io.github.thallys.Arduis.svg"
    - "tests/test_packaging_native_noop.py"
    - "tests/test_packaging_version.py"
    - "tests/test_packaging_install_tree.py"
  modified:
    - "data/io.github.thallys.Arduis.metainfo.xml"
    - "data/io.github.thallys.Arduis.desktop"
decisions:
  - "Ship NO Arch .install scriptlet (RESEARCH Pitfall 3 overrides CONTEXT D-05) — pacman hooks/dh triggers refresh caches"
  - "Build toolchain (meson/ninja/lintian) install surfaced as an auth gate — passwordless sudo unavailable in this environment"
  - "appstreamcli url-not-reachable warning accepted: repo not yet published (D-06 defers publishing to v1.1); structural validation passes --no-net"
metrics:
  duration: "~15m"
  completed: "2026-06-15"
  tasks: 3
  files: 6
---

# Phase 9 Plan 01: Packaging Wave-0 Foundation Summary

Fixed the two AppStream metainfo defects that failed validation (added the homepage URL and a 1.0.0 release element), generated a static Dracula-palette SVG app icon at the hicolor scalable path, and wrote the three skip-guarded packaging test files (HostRunner native no-op, single-sourced version, meson DESTDIR install-tree) that the downstream meson/deb/PKGBUILD plans verify against. Build-toolchain install is the one outstanding item (auth gate — no passwordless sudo).

## What Was Built

- **App icon (D-05):** `data/icons/hicolor/scalable/apps/io.github.thallys.Arduis.svg` — hand-authored 256x256 static SVG (Dracula palette, stacked terminal panes + `>` prompt). No external refs, no `<script>`, no raster (threat T-09-03 mitigated).
- **Metainfo fix (D-03/D-04, Pitfall 4):** added `<url type="homepage">https://github.com/thallysrc/arduis</url>` and `<releases><release version="1.0.0" date="2026-06-15"/></releases>`. `appstreamcli validate --no-net` now passes (exit 0); `desktop-file-validate` exits 0.
- **Desktop cleanup (Pitfall 5):** reduced `Categories` to `Development;` to clear the duplicate-menu-entry hint.
- **Three test files:** `test_packaging_native_noop.py` (Criterion-4: `_FLATPAK is False`, identity `wrap_argv`/`wrap_env`, tokenize-based scan proving no LIVE `flatpak-spawn` in `src/`), `test_packaging_version.py` (metainfo has exactly one `<release version="1.0.0">` + homepage url; meson-equality half skip-guarded), `test_packaging_install_tree.py` (meson DESTDIR stage smoke — fully skip-guarded until Plan 02).

## Verification Results

- `appstreamcli validate --no-net data/io.github.thallys.Arduis.metainfo.xml` → exit 0 (only `url-not-reachable` remains online — repo unpublished, expected per D-06).
- `desktop-file-validate data/io.github.thallys.Arduis.desktop` → exit 0.
- SVG is valid XML (verified via `xml.dom.minidom.parse`).
- `pytest -q tests/test_packaging_*.py` → 7 passed, 2 skipped (install_tree + meson-version-half skip cleanly; meson.build lands in Plan 02).
- Full suite `pytest -q` → all green, no regression (pre-existing `os.fork` deprecation warnings in `test_exit_decode.py` only).

## Deviations from Plan

### Auth Gate (toolchain install — Task 1 step 1)

**Build/lint toolchain install deferred — passwordless sudo unavailable**
- **Found during:** Task 1
- **Issue:** `sudo apt install -y meson ninja-build debhelper lintian desktop-file-utils appstream` requires interactive sudo; `sudo -n true` confirmed no passwordless sudo in this worktree environment.
- **Action:** Completed everything in Task 1 that does NOT need the toolchain (the SVG icon). `desktop-file-validate` and `appstreamcli` were already present on the host, so Task 2 validation ran fully. `meson`/`ninja-build`/`lintian` remain absent — the install-tree test skip-guards on this. Surfaced the exact install command below (see Outstanding / Auth Gate).
- **Files modified:** none for this item (toolchain is host state, not repo)

### Auto-fixed Issues

**1. [Rule 1 - Bug] tokenize-based flatpak-spawn classifier**
- **Found during:** Task 3 (TDD RED)
- **Issue:** Initial substring heuristic for "is this line a comment/string?" misclassified docstring body lines containing `` ``flatpak-spawn`` `` (backtick-quoted in prose) as live code — the no-op grep test failed on three legitimate docstring mentions in `docker_service.py` and `spawn.py`.
- **Fix:** Replaced the heuristic with a `tokenize`-based scan that marks every line covered by a STRING or COMMENT token as non-code, so only genuinely reachable `flatpak-spawn` would fail the test.
- **Files modified:** tests/test_packaging_native_noop.py
- **Commit:** c90cf0a

### Plan-sanctioned override

- **No Arch `.install` scriptlet** — followed RESEARCH Pitfall 3 (overrides CONTEXT D-05's `.install` mention): pacman hooks + dh triggers refresh icon/desktop caches automatically. No scriptlet authored. (No file change this plan; informs Plan 04.)

## Outstanding / Auth Gate

The build/lint toolchain is not installed and could not be installed here (no passwordless sudo). Before Plans 02-04 build/lint gates and the install-tree test can run, the user must run:

```bash
sudo apt install -y meson ninja-build debhelper lintian desktop-file-utils appstream
```

`desktop-file-utils` (`desktop-file-validate`) and `appstream` (`appstreamcli`) are already present on this host — only `meson`, `ninja-build`, `debhelper`, and `lintian` are actually missing; re-listing them is idempotent. After install, the `test_packaging_install_tree.py` skip resolves into the real install-tree gate once Plan 02 adds `meson.build`.

## Commits

- `101ff67` feat(09-01): add scalable app icon at hicolor path (D-05)
- `2f20614` fix(09-01): metainfo homepage url + 1.0.0 release; single desktop category
- `c90cf0a` test(09-01): add packaging tests (native no-op, version, install-tree)

## Self-Check: PASSED

- All 6 created/modified files present on disk.
- All 3 task commits present in git history (101ff67, 2f20614, c90cf0a).
- Key links verified: metainfo `url type="homepage"`, test `wrap_argv` import assertion.
