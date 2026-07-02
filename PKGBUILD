# Maintainer: thallys <thallys.costa@livon.io>
#
# Arch native package definition (DIST-02). Thin wrapper over the single
# meson build/install definition (meson.build, D-01): arch-meson sets Arch's
# standard buildtype/prefix/flags, `meson compile` builds, and `meson install
# --destdir "$pkgdir"` stages into the package root.
#
# The app is 100% pure Python + data files, so arch=('any'). Runtime deps are
# the EXACT CLAUDE.md §Packaging Arch list (system VTE 0.84, never a pip wheel).
#
# NO .install scriptlet: pacman hooks already refresh the icon and desktop-entry
# caches (gtk-update-icon-cache 3.20.3-2, desktop-file-utils 0.22-2), so a
# scriptlet would be redundant and namcap-flagged (RESEARCH Pitfall 3).
#
# The real `makepkg -si` build + Wayland launch is the Arch hardware UAT
# (Plan 05) — makepkg/pacman/namcap do not exist on the dev host.

pkgname=arduis
pkgver=1.0.0
pkgrel=1
pkgdesc="Orquestra agentes de IA em paralelo sobre git worktrees"
arch=('any')
url="https://github.com/thallysrc/arduis"
license=('MIT')
depends=('python-gobject' 'gtk4' 'libadwaita' 'vte4' 'python')
optdepends=('gst-plugins-good: captura de microfone para o agente de voz'
            'whisper.cpp: transcrição local (whisper-cli) do agente de voz')
makedepends=('meson')
# Local source tarball (D-06: "builds locally"). Until a published GitHub
# release tarball exists (publish deferred to v1.1, RESEARCH Open Q1), produce
# it from the repo with:
#   git archive --format=tar.gz --prefix=arduis-1.0.0/ -o arduis-1.0.0.tar.gz HEAD
# sha256sums=('SKIP') because the tarball is produced locally (no remote URL to
# pin); when a release is published, replace SKIP with the real checksum.
source=("$pkgname-$pkgver.tar.gz")
sha256sums=('SKIP')

build() {
  arch-meson "$pkgname-$pkgver" build
  meson compile -C build
}

check() {
  meson test -C build --print-errorlogs
}

package() {
  meson install -C build --destdir "$pkgdir"
}
