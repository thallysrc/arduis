---
phase: 09-packaging-aur-deb
plan: 03
subsystem: packaging
tags: [packaging, debian, deb, debhelper, dh-meson, lintian, ubuntu]
requires:
  - "meson.build single build/install definition + /usr-prefix launcher — 09-02"
  - "Validated .desktop/.metainfo/SVG installed into XDG dirs — 09-02"
provides:
  - "debian/ set wrapping the meson def via dh --buildsystem=meson (DIST-03)"
  - "locally-buildable arduis_1.0.0_all.deb (Architecture: all) that lints clean"
  - "exact CLAUDE.md Ubuntu runtime Depends declaration (single trusted dep set)"
affects:
  - "debian/control"
  - "debian/rules"
  - "debian/changelog"
  - "debian/source/format"
  - "debian/copyright"
  - ".gitignore"
tech-stack:
  added:
    - "debhelper-compat 13 + dh --buildsystem=meson (Ubuntu .deb build sequencer)"
  patterns:
    - "debian/rules = canonical 3-line dh meson wrapper (no custom shell, Rules-Requires-Root: no)"
    - "debhelper-compat (= 13) declared in control Build-Depends — NO debian/compat file (Open Q3)"
    - "debian/source/format = 3.0 (native) — built from own repo, no separate upstream tarball"
    - "pure-Python arch:all → only ${misc:Depends} + distro GIR deps; NO ${python3:Depends}/${shlibs:Depends}"
    - "version single-sourced from meson.build (1.0.0) → debian/changelog first entry"
key-files:
  created:
    - "debian/control"
    - "debian/rules"
    - "debian/changelog"
    - "debian/source/format"
    - "debian/copyright"
  modified:
    - ".gitignore"
decisions:
  - "debhelper-compat (= 13) lives in control Build-Depends, not a debian/compat file (RESEARCH Open Q3 — pick one)"
  - "Depends omits ${python3:Depends}/${shlibs:Depends}: pure-Python arch:all package needs neither; only ${misc:Depends} + the 5 CLAUDE.md GIR/python3 deps"
  - "Build artifacts (debian/arduis/, .debhelper, substvars, build-stamp, files, obj-*-linux-gnu) gitignored — generated, never committed"
metrics:
  duration: "~6m"
  completed: "2026-06-15"
  tasks: 2
  files: 6
---

# Phase 9 Plan 03: Ubuntu .deb packaging definition Summary

Authored the `debian/` set (DIST-03) that wraps the Plan-02 meson definition via the canonical
`dh $@ --buildsystem=meson` sequencer, and proved it builds a clean `arduis_1.0.0_all.deb`
locally. The package is `Architecture: all` (pure Python), declares EXACTLY the CLAUDE.md Ubuntu
runtime dependency set plus `${misc:Depends}`, single-sources version 1.0.0 from the changelog,
and carries the D-04 maintainer `thallys <thallys.costa@livon.io>`. `lintian` returns exit 0
(one benign `no-manual-page` warning), and the full pytest suite stays green at 436 passed. This
is the Ubuntu half of the team-install story: `apt install ./arduis_1.0.0_all.deb`.

## What Was Built

- **`debian/control`** — Source stanza: `Source: arduis`, `Section: devel`, `Priority: optional`,
  `Maintainer: thallys <thallys.costa@livon.io>` (D-04),
  `Build-Depends: meson, ninja-build, debhelper-compat (= 13), python3`,
  `Standards-Version: 4.6.2`, `Homepage: https://github.com/thallysrc/arduis`,
  `Rules-Requires-Root: no` (T-09-07 mitigation). Binary stanza: `Package: arduis`,
  `Architecture: all`, `Depends: ${misc:Depends}, python3 (>= 3.12), python3-gi, gir1.2-gtk-4.0,
  gir1.2-adw-1, gir1.2-vte-3.91 | libvte-2.91-gtk4-0` (the exact CLAUDE.md §Packaging list,
  T-09-08 mitigation — only distro packages, no pip wheel), plus a synopsis + extended Description.
- **`debian/rules`** — exactly the RESEARCH Pattern 4 three lines (`#!/usr/bin/make -f`, `%:`,
  TAB `dh $@ --buildsystem=meson`), executable (`0755`). No custom shell, no network fetch
  (T-09-07/T-09-09 mitigations).
- **`debian/changelog`** — `arduis (1.0.0) unstable; urgency=medium`, `Initial native packaging
  (v1 milestone).`, signed-off with the D-04 maintainer + a valid RFC-2822 date
  (`Mon, 15 Jun 2026 20:17:06 -0300`). Version 1.0.0 single-sourced (D-03).
- **`debian/source/format`** — `3.0 (native)` (RESEARCH Open Q1 — built from own repo, no
  separate upstream tarball).
- **`debian/copyright`** — machine-readable DEP-5 stanza, `License: MIT` (matches the metainfo
  `<project_license>MIT</project_license>`).
- **`.gitignore`** — appended the generated `dpkg-buildpackage` artifacts (`debian/.debhelper/`,
  `debian/arduis/`, `debian/arduis.substvars`, `debian/debhelper-build-stamp`, `debian/files`,
  `obj-*-linux-gnu/`) so build output is never committed.

No `debian/compat` (control's `debhelper-compat (= 13)` is the single source — Open Q3); no
`postinst`/`postrm` (modern dh auto-registers icon-cache/desktop-db triggers — A2; T-09-09:
nothing custom runs as root at install); no Snap, no pip.

## Verification Results

- **Task 1 (debian/ set):** all files present with the exact maintainer, `Architecture: all`, the
  5 runtime deps + `${misc:Depends}`, the `dh $@ --buildsystem=meson` rules (verified via
  `grep -F` — the plan's verify regex anchors `$` so a literal `cat -A` + fixed-string grep
  confirmed the line), `arduis (1.0.0` changelog, `3.0 (native)` source format, `MIT` copyright.
- **Task 2 (build + lint):** `dpkg-buildpackage -us -uc -b` produced
  `arduis_1.0.0_all.deb`. The meson `dh_auto_test` step ran `meson test` as a no-op (no meson
  tests defined) — confirmed a skip, not a failure; no packaging metadata added to pyproject.toml.
  The two `gnome.post_install` scripts correctly printed "Skipping custom install script because
  DESTDIR is set" (Pitfall 2 confirmed again under dpkg's DESTDIR).
- `lintian arduis_1.0.0_all.deb` → exit 0, single tag `W: arduis: no-manual-page [usr/bin/arduis]`
  (known-acceptable for a v1 GUI app — see Accepted Lint below). NO error tags (well under exit 2).
- `dpkg-deb -f` confirms: `Architecture: all`; `Depends: python3 (>= 3.12), python3-gi,
  gir1.2-gtk-4.0, gir1.2-adw-1, gir1.2-vte-3.91 | libvte-2.91-gtk4-0`; `Version: 1.0.0`;
  `Maintainer: thallys <thallys.costa@livon.io>`. (`${misc:Depends}` resolved to empty — correct,
  the package ships no maintainer scripts.)
- Full suite `pytest` → **436 passed** (only the pre-existing `os.fork` DeprecationWarnings in
  `test_exit_decode.py`, unrelated to this plan — identical to the Plan 02 baseline).
- `run.sh` / `src/main.py` / meson def untouched — dev flow unaffected.

## Accepted Lint

| Tag | Severity | Why accepted |
|-----|----------|--------------|
| `no-manual-page [usr/bin/arduis]` | W (warning) | v1 GUI desktop app launched from the app grid; a man page is out of scope for the v1 milestone (D-06 = definitions that build/lint locally). No error-level tags. |

## Deviations from Plan

None functional — plan executed as written. One verification nuance worth recording:

- **Verify-command regex quirk (not a deviation in output):** the Task 1 `<automated>` block uses
  `grep -q "dh \$@ --buildsystem=meson"`; under the shell, `\$@` becomes literal `$@` and grep
  treats the `$` as an end-of-line anchor, so that single sub-check reports no match even though
  the file content is exactly correct. Confirmed the literal line with `cat -A debian/rules`
  (`^Idh $@ --buildsystem=meson$`) and `grep -F`. The shipped `debian/rules` matches the plan's
  Pattern 4 verbatim; dpkg-buildpackage's successful meson-sequenced build is the authoritative
  proof the rules line is correct.

## Threat Surface

All three plan threats are addressed as planned — no new surface introduced:
- **T-09-07** (rules executes as root at build): canonical 3-line dh rules, no custom shell / no
  network, `Rules-Requires-Root: no`.
- **T-09-08** (declared Depends supply chain): only the CLAUDE.md distro packages; no pip wheel.
- **T-09-09** (maintainer scripts as root at install): no `postinst`/`postrm` shipped — dh
  triggers refresh caches; nothing custom runs as root.

## Known Stubs

None — the debian/ set is complete and produces a real installable, lint-clean `.deb`.

## Commits

- `ce28be9` feat(09-03): debian/ set (control, rules, changelog, source/format, copyright)
- `7f92da4` chore(09-03): ignore debian/meson build artifacts (.deb build)

## Self-Check: PASSED

- All 5 created debian/ files present on disk (`control`, `rules`, `changelog`, `source/format`,
  `copyright`).
- Both task commits present in git history (`ce28be9`, `7f92da4`).
- Key links verified live: `debian/rules` → `meson.build` via `dh --buildsystem=meson`
  (dpkg-buildpackage auto-sequenced configure/build/test/install and built the .deb);
  `debian/control` Depends → system GIR/python3-gi deps (confirmed on the built .deb via
  `dpkg-deb -f`).
