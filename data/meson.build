# Install the data assets into their XDG locations (D-02 / D-05).
datadir = get_option('datadir')

# Desktop entry → $datadir/applications (Exec=arduis matches the launcher).
install_data(
  'io.github.thallys.Arduis.desktop',
  install_dir: datadir / 'applications',
)

# AppStream metainfo → $datadir/metainfo.
install_data(
  'io.github.thallys.Arduis.metainfo.xml',
  install_dir: datadir / 'metainfo',
)

# Scalable app icon → hicolor theme (the .desktop/.metainfo reference this id).
install_data(
  'icons/hicolor/scalable/apps/io.github.thallys.Arduis.svg',
  install_dir: datadir / 'icons' / 'hicolor' / 'scalable' / 'apps',
)

# DEV CONVENIENCE ONLY: refresh the icon/desktop caches after a bare
# `meson install` on a developer box. These scripts are SKIPPED when DESTDIR is
# set (RESEARCH Pitfall 2), so the .deb (dh triggers) and the AUR PKGBUILD
# (pacman hooks) refresh the caches for packaged installs — NOT this. No Arch
# `.install` scriptlet is shipped either (RESEARCH Pitfall 3).
gnome = import('gnome')
gnome.post_install(
  gtk_update_icon_cache: true,
  update_desktop_database: true,
)
