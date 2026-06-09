"""ArduisWindow — GTK4/libadwaita window wrapping one VTE terminal.

Wires the tested Plan-01 seams into a real GTK app:
- spawns host ``zsh -l -i`` through a direct native PTY via ``HostRunner``
  (no ``flatpak-spawn`` prefix — D-02/D-15),
- applies the app-owned Dracula palette (D-06/D-07 — the app owns colors,
  not the shell),
- tears the child process group down on ``close-request`` (SIGHUP -> SIGKILL,
  no orphans — D-13),
- decodes the raw ``child-exited`` wait status via ``decode_exit`` (D-12).

Targets the VTE 0.76 API floor (D-03) so one codebase runs on Ubuntu (0.76)
and Arch (0.84). This is the only module that imports ``gi``; the core seams
(spawn/theme/exit_status/host_runner) stay GTK-free and unit-tested.
"""
from __future__ import annotations

import os
import signal

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")  # GTK4 binding — needs gir1.2-vte-3.91 installed
from gi.repository import Adw, Gdk, GLib, Gtk, Pango, Vte  # noqa: E402

from arduis.host_runner import HostRunner  # noqa: E402
from arduis.spawn import build_spawn_command  # noqa: E402
from arduis.exit_status import decode_exit  # noqa: E402
from arduis.theme import (  # noqa: E402
    DRACULA_BG,
    DRACULA_CURSOR,
    DRACULA_FG,
    DRACULA_PALETTE,
)

_SIGKILL_GRACE_MS = 1500  # time between SIGHUP and the SIGKILL sweep (D-13)


def _rgba(spec: str) -> Gdk.RGBA:
    """Parse a hex color string into a ``Gdk.RGBA`` (GTK lives only here)."""
    color = Gdk.RGBA()
    color.parse(spec)
    return color


class ArduisWindow(Adw.ApplicationWindow):
    """A single-terminal window running the host ``zsh`` over a direct PTY."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._runner = HostRunner()
        self._child_pid: int | None = None
        self._last_exit: int | None = None

        self.set_title("arduis")
        self.set_default_size(960, 620)

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="arduis"))
        view.add_top_bar(header)

        self.terminal = Vte.Terminal()
        # D-06/D-07: the app owns the palette, never the shell.
        self.terminal.set_colors(
            _rgba(DRACULA_FG),
            _rgba(DRACULA_BG),
            [_rgba(c) for c in DRACULA_PALETTE],
        )
        self.terminal.set_color_cursor(_rgba(DRACULA_CURSOR))
        self.terminal.set_font(Pango.FontDescription.from_string("monospace 11"))
        self.terminal.set_scrollback_lines(10000)
        self.terminal.set_mouse_autohide(True)

        # Terminal copy/paste: VTE does NOT bind these itself — the app must
        # wire the shortcuts and call the clipboard methods (like GNOME
        # Terminal/Console do). Ctrl+Shift+C/V are the terminal convention
        # (plain Ctrl+C stays SIGINT). Middle-click primary paste is VTE's
        # built-in default and needs no wiring.
        self._install_clipboard_shortcuts()

        view.set_content(self.terminal)
        self.set_content(view)

        # GTK4 window-close signal (Pitfall 5: NOT GTK3 "delete-event").
        self.connect("close-request", self._on_close_request)
        # Raw wait-status decode + window close when the shell exits (D-12).
        self.terminal.connect("child-exited", self._on_child_exited)

        self._spawn_host_shell()

    def _install_clipboard_shortcuts(self) -> None:
        """Wire Ctrl+Shift+C/V to VTE's clipboard methods (GTK4 core API)."""
        controller = Gtk.ShortcutController()
        controller.set_scope(Gtk.ShortcutScope.LOCAL)
        controller.add_shortcut(
            Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string("<Control><Shift>c"),
                Gtk.CallbackAction.new(self._copy_selection),
            )
        )
        controller.add_shortcut(
            Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string("<Control><Shift>v"),
                Gtk.CallbackAction.new(self._paste_clipboard),
            )
        )
        self.terminal.add_controller(controller)

    def _copy_selection(self, *_) -> bool:
        """Copy the current selection to the CLIPBOARD (no-op if none)."""
        if self.terminal.get_has_selection():
            self.terminal.copy_clipboard_format(Vte.Format.TEXT)
        return True  # handled — don't propagate

    def _paste_clipboard(self, *_) -> bool:
        """Paste the CLIPBOARD selection into the terminal."""
        self.terminal.paste_clipboard()
        return True  # handled — don't propagate

    def _spawn_host_shell(self) -> None:
        """Spawn host ``zsh -l -i`` over a direct PTY through the seam."""
        argv, envv = build_spawn_command(self._runner)
        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            GLib.get_home_dir(),  # working_directory (D-10)
            argv,  # ["zsh", "-l", "-i"]
            envv,  # ["TERM=xterm-256color"]
            GLib.SpawnFlags.DEFAULT,
            None,  # child_setup
            None,  # child_setup_data
            -1,  # timeout (-1 = none)
            None,  # cancellable
            self._on_spawned,  # callback (terminal, pid, error) — Pitfall 2: final arg
        )
        self.terminal.grab_focus()

    def _on_spawned(self, terminal, pid, error):
        """Capture the child PID for teardown; ignore a failed spawn."""
        if error is not None or pid == -1:
            # Surface/log the failure; do not store a bad pid.
            return
        self._child_pid = pid

    def _on_child_exited(self, terminal, status):
        """Decode the RAW wait status (D-12), record it, then close."""
        self._last_exit = decode_exit(status)
        self.close()

    def _on_close_request(self, *_):
        """No-orphan teardown (D-13): SIGHUP the child PGID, then SIGKILL."""
        pid = self._child_pid
        if pid:
            try:
                pgid = os.getpgid(pid)  # A1: don't assume pgid == pid
                os.killpg(pgid, signal.SIGHUP)
                GLib.timeout_add(_SIGKILL_GRACE_MS, self._sigkill_if_alive, pgid)
            except ProcessLookupError:
                pass  # already gone
        return False  # allow the window to close

    def _sigkill_if_alive(self, pgid):
        """SIGKILL sweep after the grace period if anything survived."""
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return GLib.SOURCE_REMOVE
