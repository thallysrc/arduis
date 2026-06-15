---
status: accepted
phase: 09-packaging-aur-deb
source: [09-05-PLAN.md]
started: 2026-06-15
updated: 2026-06-15
---

## Current Test

[PO accepted closure 2026-06-15 WITHOUT running the hardware UAT — explicit risk acceptance.
The build+lint half is verified green (commit 4fffd03); the real-distro clean-install +
Wayland launch on Ubuntu 24.04 + Arch was NOT executed. Items 1-3 remain to confirm on hardware
whenever a real install is done; reopen as gap closure if any fails.]

## Tests

### 1. Ubuntu 24.04 — clean .deb install + Wayland launch (SC-2/SC-3/DIST-03)
expected: `sudo apt install ./arduis_1.0.0_all.deb` installs with no dep errors; app grid shows the arduis icon; launching gives a GTK4 window with embedded VTE running host zsh (`ls` works, Ctrl+C interrupts); `sudo apt remove arduis` clean. (`echo $XDG_SESSION_TYPE` → wayland)
result: [pending]

### 2. Arch — AUR makepkg install + Wayland launch (SC-1/SC-3/DIST-02)
expected: `git archive --format=tar.gz --prefix=arduis-1.0.0/ -o arduis-1.0.0.tar.gz HEAD` then `makepkg -si` builds + installs; launch under Wayland → window + embedded VTE works; icon in grid; `sudo pacman -R arduis` clean. (optional `namcap PKGBUILD` → no errors)
result: [pending]

### 3. HostRunner native no-op confirmed in the installed build (SC-4)
expected: the installed app spawns the host shell directly (no flatpak-spawn); already green in automated tests, confirmed live by the terminal working.
result: [pending — implied by tests 1 & 2 launching]

## Summary

total: 3
passed: 0
issues: 0
pending: 3
skipped: 0
blocked: 0

## Gaps

> Automated half (Wave 4 gate, commit 4fffd03) all green on the Ubuntu dev host: pytest 436, `.deb` builds + lintian 0 errors, metainfo/desktop validate, PKGBUILD parses, HostRunner no-op. Only the real-distro clean-install + Wayland launch remains (hardware gate, DIST-04).
