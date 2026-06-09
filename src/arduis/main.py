"""Adw.Application entry point for arduis.

Presents a single ``ArduisWindow`` on activation. The GTK imports live in
``arduis.window``; this module only owns the application lifecycle.
"""
from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw  # noqa: E402

from arduis.window import ArduisWindow  # noqa: E402

APP_ID = "io.github.thallys.Arduis"


class ArduisApp(Adw.Application):
    """The arduis GTK4/libadwaita application."""

    def __init__(self, **kwargs):
        super().__init__(application_id=APP_ID, **kwargs)

    def do_activate(self):
        win = self.props.active_window or ArduisWindow(application=self)
        win.present()


def main() -> int:
    """Run the application. Returns the process exit code."""
    return ArduisApp().run(None)


if __name__ == "__main__":
    raise SystemExit(main())
