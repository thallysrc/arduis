---
phase: 09
slug: packaging-aur-deb
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-06-15
---

# Phase 09 — Validation Strategy

> Per-phase validation contract. Packaging is largely shell/lint-verifiable; the clean
> install + Wayland launch on real Ubuntu + Arch is the human hardware gate (DIST-04).
> Derived from 09-RESEARCH.md "## Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | shell/CLI lint + build checks (no pytest assertions for packaging) + existing pytest suite (regression) |
| **Build tools (Wave 0 apt install)** | `meson`, `ninja-build`, `debhelper`, `lintian`, `desktop-file-utils`, `appstream` (Ubuntu); `namcap`/`makepkg` are Arch-only |
| **Quick run command** | `meson setup build && meson install --destdir /tmp/arduis-stage -C build` (verify file tree) |
| **Lint commands** | `desktop-file-validate data/*.desktop`; `appstreamcli validate data/*.metainfo.xml`; `lintian ../arduis_1.0.0_all.deb` |
| **Regression** | `/tmp/arduis-venv/bin/python -m pytest -q` (must stay green — packaging adds files, no src behavior change) |
| **Estimated runtime** | build+lint ~30–60s; pytest ~30s |

---

## Sampling Rate

- **After each packaging task:** run the relevant lint/build check for the file touched.
- **After the meson task:** `meson setup build` must configure clean; staged install tree correct.
- **Before UAT:** `.deb` builds + lintian clean (or only known-acceptable tags); metainfo + desktop validate; pytest green; HostRunner-no-op grep passes.
- **Max feedback latency:** ~60s (build), ~30s (lint).

---

## Per-Task Verification Map

> Anchored to the 4 ROADMAP success criteria (SC-1 AUR, SC-2 .deb, SC-3 clean install Wayland both, SC-4 HostRunner no-op) + DIST-02/03/04. Planner populates Task IDs.

| Decision/SC | What | Test Type | Automated Command | Status |
|-------------|------|-----------|-------------------|--------|
| D-01/D-02 (meson) | meson configures + stages install tree (bin/arduis, purelib arduis pkg incl. hooks data, desktop/metainfo/icon) | build | `meson setup build && meson install --destdir /tmp/arduis-stage -C build && find /tmp/arduis-stage` | ⬜ |
| D-03 (version/metainfo) | metainfo validates + has `<release version="1.0.0">` + homepage url | lint | `appstreamcli validate data/io.github.thallys.Arduis.metainfo.xml` | ⬜ |
| D-05 (icon) | scalable SVG installed at hicolor path; desktop validates | lint | `desktop-file-validate data/io.github.thallys.Arduis.desktop` + `test -f data/icons/hicolor/scalable/apps/io.github.thallys.Arduis.svg` | ⬜ |
| SC-2/DIST-03 (.deb) | `.deb` builds + lintian clean; declares exact runtime deps | build/lint | `dpkg-buildpackage -b -us -uc` (or `debuild`) then `lintian ../arduis_1.0.0_all.deb` | ⬜ |
| SC-1/DIST-02 (AUR) | PKGBUILD parses + (Arch only) `namcap PKGBUILD` clean; deps match CLAUDE.md | lint | `bash -n PKGBUILD` + `makepkg --printsrcinfo` (Arch: `namcap`) | ⬜ (Arch parts = UAT) |
| SC-4 | HostRunner is a native no-op (no live flatpak-spawn in argv) | grep/unit | grep `host_runner` for identity `wrap_argv`; existing hostrunner test green | ⬜ |
| regression | packaging changes don't break the app | unit | `python -m pytest -q` (expect 427 passed) | ⬜ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `apt install meson ninja-build debhelper lintian desktop-file-utils appstream` (Ubuntu build/lint tools — absent on host)
- [ ] Add `<url type="homepage">https://github.com/thallysrc/arduis</url>` + `<releases>` to the metainfo so `appstreamcli validate` passes (currently FAILS — research finding)

*No new pytest files — packaging is validated by build+lint, not unit assertions. The existing suite is the regression guard.*

---

## Manual-Only Verifications (DIST-04 hardware gate)

| Behavior | SC | Why Manual | Test Instructions |
|----------|----|-----------|--------------------|
| Clean `.deb` install + launch on real Ubuntu 24.04 under Wayland | SC-2/SC-3/DIST-03/DIST-04 | Needs a clean Ubuntu box + Wayland session + GUI | `sudo apt install ./arduis_1.0.0_all.deb`; launch from app grid; confirm window + embedded VTE zsh works; `apt remove` clean |
| AUR `makepkg -si` install + launch on real Arch under Wayland | SC-1/SC-3/DIST-02/DIST-04 | Needs an Arch box (no pacman/makepkg on dev host) | `makepkg -si` from the PKGBUILD; launch; confirm VTE works; `pacman -R` clean |
| Icon shows in the app grid (both distros) | D-05 | Visual | App appears with the arduis icon, not a generic placeholder |

---

## Validation Sign-Off

- [ ] meson configures + stages a correct install tree
- [ ] `.deb` builds + lintian acceptable; metainfo + desktop validate
- [ ] PKGBUILD parses + srcinfo generates (namcap on Arch at UAT)
- [ ] HostRunner no-op grep + existing tests green; pytest 427 passed
- [ ] Wave 0 build tools installed + metainfo homepage/release added
- [ ] `nyquist_compliant: true` set in frontmatter
- [ ] Hardware gate (DIST-04) items handed to PO for real-distro UAT

**Approval:** pending
