---
phase: 09
slug: packaging-aur-deb
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-06-15
validated: 2026-06-15
---

# Phase 09 — Validation Strategy

> Per-phase validation contract. Packaging is largely shell/lint-verifiable; the clean
> install + Wayland launch on real Ubuntu + Arch is the human hardware gate (DIST-04).
> Derived from 09-RESEARCH.md "## Validation Architecture".

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | shell/CLI lint + build checks + pytest (packaging + regression) |
| **Build tools (Wave 0 apt install)** | `meson`, `ninja-build`, `debhelper`, `lintian`, `desktop-file-utils`, `appstream` (Ubuntu); `namcap`/`makepkg` are Arch-only |
| **Quick run command** | `/tmp/arduis-venv/bin/python -m pytest tests/test_packaging_install_tree.py tests/test_packaging_native_noop.py tests/test_packaging_version.py -q` |
| **Build-gate command** | `dpkg-buildpackage -us -uc -b && lintian ../arduis_1.0.0_all.deb` |
| **Lint commands** | `desktop-file-validate data/*.desktop`; `appstreamcli validate --no-net data/*.metainfo.xml`; `bash -n PKGBUILD` |
| **Regression** | `/tmp/arduis-venv/bin/python -m pytest -q` (437 passed as of 2026-06-15) |
| **Estimated runtime** | build+lint ~30–60s; pytest packaging tests ~1s; full suite ~2s |

---

## Sampling Rate

- **After each packaging task:** run the relevant lint/build check for the file touched.
- **After the meson task:** `meson setup build` must configure clean; staged install tree correct.
- **Before UAT:** `.deb` builds + lintian clean; metainfo + desktop validate; pytest green; HostRunner-no-op grep passes.
- **Max feedback latency:** ~60s (build), ~1s (packaging pytest).

---

## Per-Task Verification Map

> Anchored to the 4 ROADMAP success criteria (SC-1 AUR, SC-2 .deb, SC-3 clean install Wayland both, SC-4 HostRunner no-op) + DIST-02/03/04.

| Decision/SC | What | Test Type | Automated Command | Count | Status |
|-------------|------|-----------|-------------------|-------|--------|
| D-01/D-02 (meson) | meson configures + stages install tree (bin/arduis, purelib arduis pkg incl. hooks data, desktop/metainfo/icon) | build + pytest | `pytest tests/test_packaging_install_tree.py -v` | 1 | ✅ green |
| D-03 (version/metainfo) | metainfo validates + has `<release version="1.0.0">` + homepage url | pytest + build-gate | `pytest tests/test_packaging_version.py -v` (3); `appstreamcli validate --no-net data/io.github.thallys.Arduis.metainfo.xml` | 3 | ✅ green |
| D-05 (icon) | scalable SVG installed at hicolor path; desktop validates | build-gate lint | `desktop-file-validate data/io.github.thallys.Arduis.desktop` (exit 0); staged tree check (covered by test_packaging_install_tree) | 1 (file exists in staged tree) | ✅ green |
| SC-2/DIST-03 (.deb) | `.deb` builds + lintian 0 errors; declares exact runtime deps; no maintainer scripts | build/lint | `dpkg-buildpackage -us -uc -b && lintian ../arduis_1.0.0_all.deb` — 0 errors, 1 warning (no-manual-page, acceptable) | build artifact | ✅ green |
| SC-1/DIST-02 (AUR) | PKGBUILD parses + srcinfo generates; deps match CLAUDE.md; no .install scriptlet | lint | `bash -n PKGBUILD` (exit 0); `makepkg --printsrcinfo` (Arch: `namcap` at UAT) | parse check | ✅ green |
| SC-4 | HostRunner is a native no-op (no live flatpak-spawn in argv) | pytest | `pytest tests/test_packaging_native_noop.py -v` — 5 tests: flatpak_disabled, wrap_argv_is_identity, wrap_argv_returns_copy, wrap_env_is_identity, no_live_flatpak_spawn_in_src | 5 | ✅ green |
| regression | packaging changes don't break the app | pytest | `/tmp/arduis-venv/bin/python -m pytest -q` — 437 passed | 437 | ✅ green |
| SC-3/DIST-04 | Clean install + Wayland launch on real Ubuntu 24.04 + Arch | MANUAL-ONLY | Hardware gate — PO-accepted without execution (see 09-HUMAN-UAT.md) | — | ✅ PO-accepted |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `apt install meson ninja-build debhelper lintian desktop-file-utils appstream` (Ubuntu build/lint tools — installed during execution)
- [x] Add `<url type="homepage">https://github.com/thallysrc/arduis</url>` + `<releases>` to the metainfo so `appstreamcli validate` passes (done in Plan 01/02)
- [x] `tests/test_packaging_install_tree.py` — DIST-02/03 meson install tree + importlib.resources smoke (1 test, created in Plan 01)
- [x] `tests/test_packaging_native_noop.py` — SC-4 HostRunner no-op + repo scan (5 tests, created in Plan 01)
- [x] `tests/test_packaging_version.py` — D-03 single-source version 1.0.0 (3 tests, created in Plan 01)

---

## Manual-Only Verifications (DIST-04 hardware gate)

> **PO-accepted without execution (2026-06-15)** — see `09-HUMAN-UAT.md` status: accepted.
> The build+lint automated half (commit 4fffd03) is verified green. Hardware items remain
> open for post-release confirmation; they do not block v1 closure.

| Behavior | SC | Why Manual | Test Instructions |
|----------|----|-----------|--------------------|
| Clean `.deb` install + launch on real Ubuntu 24.04 under Wayland | SC-2/SC-3/DIST-03/DIST-04 | Needs a clean Ubuntu box + Wayland session + GUI | `sudo apt install ./arduis_1.0.0_all.deb`; launch from app grid; confirm window + embedded VTE zsh works; `apt remove` clean |
| AUR `makepkg -si` install + launch on real Arch under Wayland | SC-1/SC-3/DIST-02/DIST-04 | Needs an Arch box (no pacman/makepkg on dev host) | `makepkg -si` from the PKGBUILD; launch; confirm VTE works; `pacman -R` clean |
| Icon shows in the app grid (both distros) | D-05 | Visual | App appears with the arduis icon, not a generic placeholder |

---

## Validation Sign-Off

- [x] meson configures + stages a correct install tree
- [x] `.deb` builds + lintian 0 errors; metainfo + desktop validate
- [x] PKGBUILD parses + srcinfo generates (namcap on Arch at UAT)
- [x] HostRunner no-op grep + existing tests green; full pytest 437 passed
- [x] Wave 0 build tools installed + metainfo homepage/release added
- [x] `nyquist_compliant: true` set in frontmatter
- [x] Hardware gate (DIST-04) items handed to PO for real-distro UAT — PO-accepted

**Approval:** validated 2026-06-15 (post-execution reconcile)

---

## Validation Audit 2026-06-15

| Metric | Count |
|--------|-------|
| Gaps found | 0 (all packaging tests created during execution; build-gate run green in Plan 05) |
| Resolved | 7 task rows reconciled to ✅ green |
| Escalated | 0 |

All DIST-02/03/SC-4 automatable behaviors are covered by green tests: meson install tree
+ importlib.resources hook load (1 test — `test_packaging_install_tree.py`), version single-source
+ metainfo release + homepage URL (3 tests — `test_packaging_version.py`), HostRunner native
no-op including tokenizer-based live-flatpak-spawn scan of all src/ (5 tests —
`test_packaging_native_noop.py`). Total packaging-specific pytest coverage: 9 tests, all green.

Build-gate evidence from Plan 05 (09-05-SUMMARY.md, commit 4fffd03): `dpkg-buildpackage -us -uc
-b` built `arduis_1.0.0_all.deb` (100K, Architecture: all) with correct declared deps
(`python3-gi`, `gir1.2-gtk-4.0`, `gir1.2-adw-1`, `gir1.2-vte-3.91 | libvte-2.91-gtk4-0`,
no maintainer scripts); `lintian` returned 0 errors (1 acceptable warning: `no-manual-page`);
`appstreamcli validate --no-net` clean; `desktop-file-validate` exit 0; `bash -n PKGBUILD`
exit 0. Full regression suite: 437 passed (3 pre-existing fork DeprecationWarnings only).

DIST-04 (SC-3) hardware install + Wayland launch on real Ubuntu 24.04 and Arch is the only
remaining manual gate. PO explicitly accepted closure without executing it on 2026-06-15
(09-HUMAN-UAT.md status: accepted). This is the same treatment as live-GTK items in Phase 1 —
irreducibly manual, not an automated gap, and does not block `nyquist_compliant: true`.
VALIDATION.md was a stale plan-time draft; reconciled to reflect the shipped green surface.
