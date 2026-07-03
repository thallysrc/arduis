"""Adw.Application entry point for arduis.

Presents a single ``ArduisWindow`` on activation. The GTK imports live in
``arduis.window``; this module only owns the application lifecycle.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk  # noqa: E402

from arduis.window import ArduisWindow  # noqa: E402

APP_ID = "io.github.thallys.Arduis"


class ArduisApp(Adw.Application):
    """The arduis GTK4/libadwaita application."""

    def __init__(self, **kwargs):
        super().__init__(application_id=APP_ID, **kwargs)

    def do_activate(self):
        # The GTK4 ibus IM module fails to clear the dead-key preedit, so the
        # ´ ` " glyph stays painted on the VTE cursor forever (upstream
        # https://gitlab.gnome.org/GNOME/vte/-/issues/2741, open as of 0.76).
        # Compose dead keys locally via the simple IM context instead. Set via
        # Gtk.Settings — NOT the GTK_IM_MODULE env var — so spawned shells and
        # agents don't inherit it. Trade-off: ibus engines (CJK) won't work
        # inside arduis while this is in place; remove when upstream fixes it.
        settings = Gtk.Settings.get_default()
        if settings is not None:
            settings.set_property("gtk-im-module", "gtk-im-context-simple")
        win = self.props.active_window or ArduisWindow(application=self)
        win.present()


def main() -> int:
    """Run the application. Returns the process exit code."""
    return ArduisApp().run(None)


if __name__ == "__main__":
    raise SystemExit(main())
