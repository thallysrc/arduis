# arduis — native build/install definition (D-01).
#
# This is the SINGLE build/install definition both downstream packages wrap
# thinly: the .deb via `dh $@ --buildsystem=meson` (Plan 03) and the AUR
# PKGBUILD via `arch-meson`/`meson install --destdir` (Plan 04).
#
# The app is 100% pure Python + three data files — no compiled targets.
# The version is single-sourced HERE (D-03) and propagated into the generated
# launcher (and asserted equal to the metainfo <release> by the test suite).
project(
  'arduis',
  meson_version: '>= 0.63.0',  # preserve_path in python.install_sources
  version: '1.0.0',
  license: 'MIT',
  # Distro packaging installs under /usr (not the meson default /usr/local);
  # both debhelper and the AUR PKGBUILD expect the launcher at /usr/bin/arduis.
  default_options: ['prefix=/usr'],
)

subdir('src')
subdir('data')
