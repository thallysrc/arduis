"""ArduisWindow — GTK4/libadwaita window hosting the core loop.

Phase 3 rewires the Phase-2 tab strip (the now-removed libadwaita tab view +
tab bar) into the real v1 shell:
a left **sidebar** (``Gtk.ListBox`` bound to the ``SessionStore`` plus a pinned
``main`` scratch-shell row) + a right **nested ``GtkPaned`` canvas** that
*reflects* the GTK-free ``LayoutModel`` (Plan 03-02). The tab strip is gone:
several worktrees stay open at once, each in its own pane (PAR-01); selecting a
sidebar row focuses its pane if visible, else swaps it into the focused pane
(PAR-02 / D-06); creating a worktree splits the focused pane so the new agent
appears beside it (D-03); the canvas is free split/drag with no visible tab bar
(LAYOUT-01 / D-01). Hibernate/Resume move to the sidebar row's right-click menu
(D-08), reusing the Phase-2 ``win.hibernate``/``win.resume`` actions verbatim.

ALL layout *logic* lives in the GTK-free ``arduis.layout.LayoutModel`` —
``window.py`` only reflects the model tree into ``Gtk.Paned``/``Vte.Terminal``
widgets. This is the only presentation module that imports ``gi``.

Decisions wired here:
- D-01: nested ``GtkPaned`` canvas replaces the tab strip (no visible tab bar).
- D-02: sidebar (all worktrees) and pane canvas (a subset) are decoupled.
- D-03: ``+New`` splits the focused pane before the spawn.
- D-04 (discretion): closing a pane HIDES the worktree (leaf removed from the
  layout, session stays ACTIVE in the store + sidebar) — no confirmation.
- D-06 (Phase 03.1): row select swaps the WHOLE workspace (worktree), not a pane.
- D-07: the ``$HOME`` scratch shell is a pinned ``main`` sidebar row (not a session).
- D-08: Hibernate/Resume live on the sidebar row context menu.
- D-10/D-11/D-12 (Phase-2): hibernate kills the group + keeps the dir; resume
  cold-relaunches; window-close tears down ALL sessions (no orphans).

Targets the VTE 0.76 API floor so one codebase runs on Ubuntu (0.76) and Arch
(0.84). Plan 03-05 adds, on top of this shell: a capture-phase ``C-Space`` prefix
state machine (PAR-03/D-09/D-10) dispatching via ``arduis.keymap``; a ~2s off-loop
``GLib`` RAM poll (RAM-03/D-12/D-14) writing process-group RSS onto each session;
and the active-agent cap prompt-to-hibernate gate on +New (RAM-02/D-15/D-16).
"""
from __future__ import annotations

import os
import signal
import subprocess

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")  # GTK4 binding — needs gir1.2-vte-3.91 installed
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango, Vte  # noqa: E402

from arduis.host_runner import HostRunner  # noqa: E402
from arduis.spawn import build_spawn_command, build_worktree_spawn  # noqa: E402
from arduis.exit_status import decode_exit  # noqa: E402
from arduis.git_service import run_git_async  # noqa: E402
from arduis import caps, keymap, resource_monitor  # noqa: E402
from arduis.layout import LayoutModel, LeafNode, SplitNode  # noqa: E402
from arduis.session import (  # noqa: E402
    AGENT_FEED,
    SessionState,
    SessionStore,
    TerminalRecord,
    WorktreeSession,
    default_terminals,
    hibernate_fields,
)
from arduis.worktree import (  # noqa: E402
    argv_default_branch_local,
    argv_default_branch_via_origin,
    argv_list_local_branches,
    argv_repo_has_commit,
    argv_worktree_add_existing,
    argv_worktree_add_new,
    argv_worktree_list_porcelain,
    branch_checked_out_path,
    infer_new_vs_existing,
    parse_default_branch,
    parse_local_branches,
    parse_worktrees,
    worktree_dir_for,
)
from arduis.theme import (  # noqa: E402
    DRACULA_BG,
    DRACULA_CURSOR,
    DRACULA_FG,
    DRACULA_PALETTE,
)

_SIGKILL_GRACE_MS = 1500  # time between SIGHUP and the SIGKILL sweep (D-13)
_NO_REPO_HINT = "Launch arduis inside a git repo to create worktrees"

# The pinned $HOME scratch shell is a layout leaf but NOT a store session (D-07).
_MAIN_SID = "main"

_SIDEBAR_WIDTH = 248   # UI-SPEC: fixed-ish sidebar width
_PANE_HEADER_H = 32    # UI-SPEC: pane-header height
_MIN_PANE_W = 240      # UI-SPEC: min usable terminal width
_MIN_PANE_H = 120      # UI-SPEC: min usable terminal height

# UI-SPEC Color (Dracula, mirrored from theme.py).
_DOT_ACTIVE = "#50fa7b"      # active agent dot (green)
_DOT_HIBERNATED = "#6272a4"  # hibernated dot (grey)
_BRANCH_PINK = "#ff79c6"     # pane-header branch label
_FOCUS_RING = "#bd93f9"      # focused-pane purple ring
_BG2 = "#21222c"             # sidebar / header / pane-header surface

# Loaded once into the display so the CSS classes below resolve everywhere.
_CSS = f"""
.arduis-sidebar {{
    background-color: {_BG2};
}}
.arduis-pane-header {{
    background-color: {_BG2};
    min-height: {_PANE_HEADER_H}px;
    padding: 0 16px;
}}
.arduis-branch {{
    color: {_BRANCH_PINK};
    font-weight: 600;
    font-size: 13px;
}}
.arduis-badge {{
    color: {_FOCUS_RING};
    font-size: 11px;
}}
.arduis-leaf.focus {{
    border: 1px solid {_FOCUS_RING};
}}
.arduis-dot-active {{
    color: {_DOT_ACTIVE};
}}
.arduis-dot-hibernated {{
    color: {_DOT_HIBERNATED};
}}
.arduis-row-branch {{
    font-weight: 600;
    font-size: 13px;
}}
.arduis-row-subline {{
    font-size: 11px;
    opacity: 0.7;
}}
.arduis-row-hibernated {{
    opacity: 0.5;
}}
.arduis-hintbar {{
    background-color: {_BG2};
    padding: 4px 16px;
    font-size: 11px;
}}
.arduis-hint-key {{
    color: {_FOCUS_RING};
    font-weight: 600;
}}
.arduis-footer-count {{
    color: {_DOT_ACTIVE};
    font-weight: 600;
}}
"""


def _rgba(spec: str) -> Gdk.RGBA:
    """Parse a hex color string into a ``Gdk.RGBA`` (GTK lives only here)."""
    color = Gdk.RGBA()
    color.parse(spec)
    return color


class ArduisWindow(Adw.ApplicationWindow):
    """Sidebar + nested-GtkPaned canvas: N worktree terminals, decoupled view."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._runner = HostRunner()
        self._store = SessionStore()
        # The $HOME scratch shell is the pinned "main" leaf (D-07), not a session.
        self._shell_pid: int | None = None
        self._last_exit: int | None = None
        self._repo_root: str | None = None
        self._repo_name: str | None = None

        # Phase 03.1 pivot (D-04): ONE LayoutModel PER worktree (keyed by worktree
        # sid) instead of one global tree. The canvas shows exactly ONE worktree's
        # terminals at a time; selecting a sidebar row swaps the whole workspace.
        self._layouts: dict[str, LayoutModel] = {}            # worktree sid -> its tree
        self._active_workspace_sid: str | None = None         # which worktree is visible

        # Widget maps are now keyed by TERMINAL id (e.g. "main:t0", "feat:t0",
        # "feat:t1"), NOT by worktree sid — a worktree owns N terminals (D-02/D-03).
        self._leaf_by_sid: dict[str, Gtk.Widget] = {}
        self._term_by_sid: dict[str, Vte.Terminal] = {}
        # sidebar row <-> session_id (the main row maps to the scratch shell).
        self._sid_by_row: dict[Gtk.ListBoxRow, str] = {}
        self._row_by_sid: dict[str, Gtk.ListBoxRow] = {}
        # the row a right-click context menu currently targets (D-08).
        self._menu_target_sid: str | None = None

        # C-Space prefix state machine (PAR-03/D-09/D-10): armed by Ctrl+Space.
        self._prefix_armed = False
        # ~2s off-loop RAM poll source id (RAM-03); removed on close.
        self._ram_source: int | None = None
        # The aggregate RAM footer + per-row RAM sub-line labels (Plan 03-05).
        self._footer_label: Gtk.Label | None = None
        self._subline_by_sid: dict[str, Gtk.Label] = {}

        self._install_css()

        self.set_title("arduis")
        self.set_default_size(960, 620)

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="arduis"))

        # The "+New worktree" button lives in the header (D-02/D-03). Disabled
        # until repo resolution succeeds.
        self._new_btn = Gtk.Button()
        self._new_btn.set_icon_name("list-add-symbolic")
        self._new_btn.set_tooltip_text("Nova worktree")
        self._new_btn.set_sensitive(False)  # enabled once _repo_root resolves
        self._new_btn.connect("clicked", self._on_new_worktree_clicked)
        header.pack_start(self._new_btn)

        # ⌥ Layout menu (LAYOUT-01/D-04): grid 2×2 / columns presets.
        header.pack_start(self._build_layout_button())
        view.add_top_bar(header)

        # Outer body: the sidebar+canvas row over a bottom tmux-hint bar.
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Row: horizontal split = sidebar (left, fixed-ish) + canvas slot (right).
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_vexpand(True)

        self._sidebar = self._build_sidebar()
        body.append(self._sidebar)

        # Canvas slot: a single-child frame whose child is the reflected pane tree.
        self._canvas_slot = Gtk.Frame()
        self._canvas_slot.set_hexpand(True)
        self._canvas_slot.set_vexpand(True)
        body.append(self._canvas_slot)

        outer.append(body)
        outer.append(self._build_hint_bar())

        view.set_content(outer)
        self.set_content(view)

        # C-Space prefix machine on a CAPTURE-phase controller (RESEARCH § Pattern
        # 3): it sees every key before the focused Vte.Terminal, swallowing ONLY
        # the prefix while disarmed and a recognized action while armed (Pitfall 6).
        kc = Gtk.EventControllerKey()
        kc.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        kc.connect("key-pressed", self._on_key)
        self.add_controller(kc)

        # Hibernate / Resume actions reused from Phase 2, now driven by the row
        # context menu (D-08).
        self._install_row_actions()
        # Layout preset actions (LAYOUT-01/D-04), driven by the ⌥ Layout menu.
        self._install_layout_actions()

        # GTK4 window-close signal (NOT GTK3 "delete-event").
        self.connect("close-request", self._on_close_request)

        # Resolve the launch repo FIRST (D-03) so the pinned main leaf can open
        # in the repo root rather than $HOME, and the sidebar can show its name.
        self._resolve_repo_root()

        # Seed the canvas with the main checkout scratch shell as the pinned leaf.
        self._open_shell_leaf()

        # ~2s off-loop RAM poll (RAM-03/D-14): writes live process-group RSS onto
        # each active session and refreshes the row sub-lines + aggregate footer.
        # Removed in _on_close_request so no poll outlives the window.
        self._ram_source = GLib.timeout_add_seconds(2, self._poll_ram)

    # --- CSS provider (UI-SPEC Color) ---------------------------------------

    def _install_css(self) -> None:
        """Load the sidebar/dot/pane-header/focus-ring colors once per display."""
        provider = Gtk.CssProvider()
        provider.load_from_data(_CSS.encode("utf-8"))
        display = Gdk.Display.get_default()
        if display is not None:
            Gtk.StyleContext.add_provider_for_display(
                display, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    # --- terminal factory (reused verbatim from Phase 2) --------------------

    def _make_terminal(self) -> Vte.Terminal:
        """Build a VTE terminal with the app-owned palette + clipboard shortcuts."""
        terminal = Vte.Terminal()
        # D-06/D-07 (Phase 1): the app owns the palette, never the shell.
        terminal.set_colors(
            _rgba(DRACULA_FG),
            _rgba(DRACULA_BG),
            [_rgba(c) for c in DRACULA_PALETTE],
        )
        terminal.set_color_cursor(_rgba(DRACULA_CURSOR))
        terminal.set_font(Pango.FontDescription.from_string("monospace 11"))
        terminal.set_scrollback_lines(10000)
        terminal.set_mouse_autohide(True)
        self._install_clipboard_shortcuts(terminal)
        return terminal

    def _install_clipboard_shortcuts(self, terminal: Vte.Terminal) -> None:
        """Wire Ctrl+Shift+C/V to VTE's clipboard methods (GTK4 core API)."""
        controller = Gtk.ShortcutController()
        controller.set_scope(Gtk.ShortcutScope.LOCAL)
        controller.add_shortcut(
            Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string("<Control><Shift>c"),
                Gtk.CallbackAction.new(self._make_copy_cb(terminal)),
            )
        )
        controller.add_shortcut(
            Gtk.Shortcut.new(
                Gtk.ShortcutTrigger.parse_string("<Control><Shift>v"),
                Gtk.CallbackAction.new(self._make_paste_cb(terminal)),
            )
        )
        terminal.add_controller(controller)

    def _make_copy_cb(self, terminal: Vte.Terminal):
        def _copy(*_) -> bool:
            if terminal.get_has_selection():
                terminal.copy_clipboard_format(Vte.Format.TEXT)
            return True  # handled — don't propagate
        return _copy

    def _make_paste_cb(self, terminal: Vte.Terminal):
        def _paste(*_) -> bool:
            terminal.paste_clipboard()
            return True  # handled — don't propagate
        return _paste

    # --- pane leaf factory (pane-header + terminal) -------------------------

    def _make_leaf(
        self,
        sid: str,
        branch_label: str,
        terminal: Vte.Terminal,
        badge_label: str = "claude",
    ) -> Gtk.Widget:
        """Build a leaf = 32px pane header (branch + badge + ⊟/⊞/✕) over a terminal.

        ``badge_label`` reflects what actually runs in the pane: ``zsh`` for the
        pinned main scratch shell, ``claude`` for worktree agents (the default).
        """
        leaf = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        leaf.add_css_class("arduis-leaf")
        leaf.set_size_request(_MIN_PANE_W, _MIN_PANE_H)  # UI-SPEC min usable pane

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("arduis-pane-header")

        # T-03-09: render the branch literally via set_text — never set_markup.
        branch = Gtk.Label()
        branch.set_text(branch_label)
        branch.add_css_class("arduis-branch")
        header.append(branch)

        badge = Gtk.Label()
        badge.set_text(badge_label)
        badge.add_css_class("arduis-badge")
        header.append(badge)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)

        split_btn = Gtk.Button(label="⊟")
        split_btn.set_tooltip_text("Dividir painel")
        split_btn.add_css_class("flat")
        split_btn.connect("clicked", self._make_split_pane_cb(sid))
        header.append(split_btn)

        zoom_btn = Gtk.Button(label="⊞")
        zoom_btn.set_tooltip_text("Zoom")
        zoom_btn.add_css_class("flat")
        zoom_btn.connect("clicked", self._make_zoom_pane_cb(sid))
        header.append(zoom_btn)

        close_btn = Gtk.Button(label="✕")
        close_btn.set_tooltip_text("Fechar painel")
        close_btn.add_css_class("flat")
        close_btn.connect("clicked", self._make_close_pane_cb(sid))
        header.append(close_btn)

        leaf.append(header)

        terminal.set_hexpand(True)
        terminal.set_vexpand(True)
        leaf.append(terminal)
        return leaf

    def _make_split_pane_cb(self, sid: str):
        def _split(_btn) -> None:
            # ⊟ splits the active workspace, adding a new agent terminal beside
            # this one (D-05). ``sid`` here is a TERMINAL id in the active tree.
            model = self._active_layout()
            if model is None:
                return
            model.focused_id = sid
            self._split_active_pane(sid)
        return _split

    def _make_zoom_pane_cb(self, sid: str):
        def _zoom(_btn) -> None:
            model = self._active_layout()
            if model is None:
                return
            if model.is_zoomed():
                model.unzoom()
            else:
                model.zoom(sid)
            self._reflect_layout()
        return _zoom

    def _make_close_pane_cb(self, sid: str):
        def _close(_btn) -> None:
            # D-04 default: HIDE — drop the terminal leaf from the active tree.
            model = self._active_layout()
            if model is None:
                return
            model.close_leaf(sid)
            self._reflect_layout()
        return _close

    # --- per-worktree layout lookup (D-04, rebuild-on-switch) ----------------

    def _workspace_layout(self, sid: str) -> LayoutModel:
        """Return the LayoutModel for worktree ``sid`` (created lazily, D-04)."""
        return self._layouts.setdefault(sid, LayoutModel())

    def _active_layout(self) -> LayoutModel | None:
        """The visible worktree's LayoutModel (None when no workspace is active)."""
        if self._active_workspace_sid is None:
            return None
        return self._layouts.get(self._active_workspace_sid)

    # --- the pinned main-checkout scratch shell as the "main" leaf (D-07) ----

    def _open_shell_leaf(self) -> None:
        """Seed the canvas with the zsh scratch shell as the pinned main leaf.

        D-07 (revised on UAT): the pinned leaf opens in the launch repo's root —
        its main checkout — so launching arduis from a repo lands you in it.
        Falls back to ``$HOME`` only when arduis was launched outside a repo.
        """
        terminal = self._make_terminal()
        terminal.connect("child-exited", self._on_shell_exited)

        # Label the pinned leaf with the repo name (its main checkout); fall back
        # to "main" when launched outside a repo. The badge is "zsh" (not claude).
        # D-07: the main row is a REGULAR 1-terminal workspace — its single terminal
        # id is "main:t0", keyed by terminal id like every other workspace.
        main_label = self._repo_name or "main"
        main_tid = f"{_MAIN_SID}:t0"
        leaf = self._make_leaf(main_tid, main_label, terminal, badge_label="zsh")
        self._leaf_by_sid[main_tid] = leaf
        self._term_by_sid[main_tid] = terminal

        # Build the main workspace's OWN LayoutModel (D-04/D-07) — no special-casing;
        # it goes through the same swap/reflect path as any worktree.
        model = self._workspace_layout(_MAIN_SID)
        model.root = LeafNode(main_tid)
        model.focused_id = main_tid
        model.touch(main_tid)
        self._active_workspace_sid = _MAIN_SID
        self._reflect_layout()

        main_cwd = self._repo_root or GLib.get_home_dir()
        argv, envv = build_spawn_command(self._runner)
        terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            main_cwd,             # working_directory: repo root, else $HOME
            argv,                 # ["zsh", "-l", "-i"]
            envv,                 # ["TERM=xterm-256color"]
            GLib.SpawnFlags.DEFAULT,
            None,                 # child_setup
            None,                 # child_setup_data
            -1,                   # timeout (-1 = none)
            None,                 # cancellable
            self._on_shell_spawned,  # callback (terminal, pid, error)
        )
        terminal.grab_focus()

    def _on_shell_spawned(self, terminal, pid, error):
        """Capture the scratch shell's PID for teardown; ignore a failed spawn."""
        if error is not None or pid == -1:
            return
        self._shell_pid = pid

    def _on_shell_exited(self, terminal, status):
        """The scratch shell exiting closes the window (the primary shell)."""
        self._last_exit = decode_exit(status)
        self.close()

    # --- sidebar (PAR-02, D-05/D-06/D-07/D-08) ------------------------------

    def _build_sidebar(self) -> Gtk.Widget:
        """The left sidebar: a ListBox of the pinned main row + worktree rows."""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("arduis-sidebar")
        box.set_size_request(_SIDEBAR_WIDTH, -1)

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._listbox.connect("row-activated", self._on_row_activated)
        box.append(self._listbox)

        self._rebuild_sidebar()
        return box

    def _rebuild_sidebar(self) -> None:
        """Rebuild rows from the store; pinned main row first, then each session."""
        # Clear existing rows via the GTK4 child API (first-child + next-sibling
        # walk — the GTK3 container-children accessor is gone in GTK4).
        child = self._listbox.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            self._listbox.remove(child)
            child = nxt
        self._sid_by_row.clear()
        self._row_by_sid.clear()
        self._subline_by_sid.clear()

        # Pinned main row (D-07 revised): the repo's main-checkout scratch shell,
        # not a session. Titled with the repo name so you see which repo you're in.
        main_title = self._repo_name or "main"
        self._listbox.append(
            self._make_row(_MAIN_SID, main_title, "main · zsh", active=True)
        )

        # One row per worktree session.
        for session in self._store.all():
            active = session.state == SessionState.ACTIVE
            self._listbox.append(
                self._make_row(session.session_id, session.branch, "claude · —", active=active)
            )

    def _make_row(self, sid: str, branch: str, subline: str, active: bool) -> Gtk.ListBoxRow:
        """One sidebar row: dot (8px) + branch (13/600) + RAM sub-line (11/400)."""
        row = Gtk.ListBoxRow()
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.set_margin_top(8)
        outer.set_margin_bottom(8)
        outer.set_margin_start(16)
        outer.set_margin_end(16)

        dot = Gtk.Label(label="●")
        dot.add_css_class("arduis-dot-active" if active else "arduis-dot-hibernated")
        dot.set_valign(Gtk.Align.CENTER)
        outer.append(dot)

        text = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        # T-03-09: branch name rendered literally via set_text (no markup injection).
        name = Gtk.Label(xalign=0)
        name.set_text(branch)
        name.add_css_class("arduis-row-branch")
        text.append(name)
        sub = Gtk.Label(xalign=0)
        sub.set_text(subline)
        sub.add_css_class("arduis-row-subline")
        text.append(sub)
        outer.append(text)
        # Keep a handle so the ~2s RAM poll can refresh the sub-line in place.
        self._subline_by_sid[sid] = sub

        if not active:
            row.add_css_class("arduis-row-hibernated")

        row.set_child(outer)

        # Track the row<->sid map (the main row is mappable so activation focuses
        # the scratch shell pane).
        self._sid_by_row[row] = sid
        self._row_by_sid[sid] = row

        # Right-click context menu targets this row's session (D-08).
        if sid != _MAIN_SID:
            gesture = Gtk.GestureClick()
            gesture.set_button(Gdk.BUTTON_SECONDARY)
            gesture.connect("pressed", self._make_row_menu_cb(sid, row))
            row.add_controller(gesture)

        return row

    def _make_row_menu_cb(self, sid: str, row: Gtk.ListBoxRow):
        def _on_secondary(_gesture, _n_press, x, y) -> None:
            self._menu_target_sid = sid
            session = self._store.get(sid)
            menu = Gio.Menu()
            if session is not None and session.state == SessionState.ACTIVE:
                menu.append("Hibernar", "win.hibernate")  # D-08
            else:
                menu.append("Retomar", "win.resume")
            popover = Gtk.PopoverMenu.new_from_model(menu)
            popover.set_parent(row)
            rect = Gdk.Rectangle()
            rect.x = int(x)
            rect.y = int(y)
            rect.width = 1
            rect.height = 1
            popover.set_pointing_to(rect)
            popover.popup()
        return _on_secondary

    def _swap_workspace(self, sid: str) -> None:
        """Swap the visible canvas to worktree ``sid``'s terminals (D-04/D-07).

        Phase 03.1: selecting a sidebar row swaps the WHOLE workspace (tmux:
        windows = worktrees), not a single pane. ``_reflect_layout`` unparents every
        mapped leaf before re-hanging the active subset, so the detached terminals
        (and their live PTY children) survive the swap intact (A1/Pitfall 2 — no
        respawn). The pinned ``main`` row goes through this same path — no branch.
        """
        self._active_workspace_sid = sid
        self._reflect_layout()
        # Focus the swapped-in workspace's focused terminal.
        model = self._workspace_layout(sid)
        term = self._term_by_sid.get(model.focused_id)
        if term is not None:
            term.grab_focus()

    def _on_row_activated(self, _listbox, row: Gtk.ListBoxRow) -> None:
        """Row activation swaps the entire workspace to that worktree (D-04/D-07)."""
        sid = self._sid_by_row.get(row)
        if sid is None:
            return
        self._swap_workspace(sid)

    # --- ⌥ Layout presets + zoom (LAYOUT-01/D-04) ---------------------------

    def _build_layout_button(self) -> Gtk.Widget:
        """Header menu button (``⌥ Layout``) with grid 2×2 / columns presets."""
        menu = Gio.Menu()
        menu.append("Grade 2×2", "win.preset_grid2x2")
        menu.append("Colunas", "win.preset_columns")

        button = Gtk.MenuButton()
        button.set_label("⌥ Layout")
        button.set_tooltip_text("Layout")
        button.set_menu_model(menu)
        return button

    def _install_layout_actions(self) -> None:
        """Register win.preset_grid2x2 / win.preset_columns (LAYOUT-01/D-04)."""
        grid = Gio.SimpleAction.new("preset_grid2x2", None)
        grid.connect("activate", lambda *_: self._apply_preset("grid2x2"))
        self.add_action(grid)

        columns = Gio.SimpleAction.new("preset_columns", None)
        columns.connect("activate", lambda *_: self._apply_preset("columns"))
        self.add_action(columns)

    def _apply_preset(self, kind: str) -> None:
        """Rebuild the active workspace with a preset over its terminals (D-04).

        Phase 03.1: presets now act WITHIN the visible worktree's terminals, not
        across worktrees — the more natural per-workspace arrangement.
        """
        model = self._active_layout()
        if model is None:
            return
        ids = self._mru_active_ids(model)
        if not ids:
            return
        model.preset(kind, ids)
        self._reflect_layout()

    def _mru_active_ids(self, model: LayoutModel) -> list[str]:
        """The active workspace's most-recently-focused visible terminal ids (D-04)."""
        visible = set(model.visible_ids())
        ordered = [sid for sid in model.mru_order() if sid in visible]
        # Include any visible ids the MRU hasn't seen yet (deterministic tail).
        for sid in model.visible_ids():
            if sid not in ordered:
                ordered.append(sid)
        return ordered

    # --- bottom tmux-hint bar (UI-SPEC Copywriting) -------------------------

    def _build_hint_bar(self) -> Gtk.Widget:
        """The literal tmux hint bar + the live ``N agentes ativos`` footer."""
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=16)
        bar.add_css_class("arduis-hintbar")

        # Literal contract copy with purple C-Space glyphs (UI-SPEC).
        hints = Gtk.Label()
        hints.set_xalign(0)
        hints.set_use_markup(True)
        key = _FOCUS_RING
        hints.set_markup(
            f'<span foreground="{key}" weight="bold">C-Space n</span> nova · '
            f'<span foreground="{key}" weight="bold">C-Space hjkl</span> mover · '
            f'<span foreground="{key}" weight="bold">C-Space z</span> zoom'
        )
        bar.append(hints)

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        bar.append(spacer)

        # Aggregate footer: "N agentes ativos · <total> RAM" (count in green).
        self._footer_label = Gtk.Label()
        self._footer_label.set_xalign(1)
        self._footer_label.set_use_markup(True)
        self._update_footer()
        bar.append(self._footer_label)
        return bar

    # --- C-Space prefix state machine (PAR-03/D-09/D-10) --------------------

    def _on_key(self, _ctrl, keyval, _code, state) -> bool:
        """Capture-phase prefix machine: arm on Ctrl+Space, dispatch the next key.

        Returns True ONLY for the prefix keystroke (while disarmed) and for a
        recognized action key (while armed); every other key returns False so the
        focused terminal receives all normal typing (T-03-12 / Pitfall 6).
        """
        name = Gdk.keyval_name(keyval) or ""
        if not self._prefix_armed:
            if (
                name == keymap.PREFIX_KEYVAL
                and (state & Gdk.ModifierType.CONTROL_MASK)
            ):
                self._prefix_armed = True
                return True  # swallow the prefix; do NOT leak it to the shell
            return False  # normal typing — let the terminal have it (Pitfall 6)

        # Armed: the next key is the action key. Disarm regardless of match.
        self._prefix_armed = False
        action = keymap.dispatch(name)
        if action is None:
            return False  # stray key after the prefix — don't eat it
        self._run_action(action)
        return True  # recognized action — swallow it

    def _run_action(self, action: tuple) -> None:
        """Map a keymap action tuple to focus/worktree/jump behavior (A2)."""
        kind = action[0]
        if kind == "focus_dir":
            self._focus_neighbor(action[1])
        elif kind == "worktree":
            self._cycle_worktree(action[1])
        elif kind == "jump":
            self._jump_to_row(action[1])

    def _focus_neighbor(self, direction: str) -> None:
        """Move focus to the neighbor TERMINAL in the active worktree (D-06, A2).

        Phase 03.1 re-target (D-06): h/j/k/l now moves between the terminals of the
        VISIBLE worktree (tmux: panes = terminals). Tree-order, not geometric: h/k
        step toward the previous visible terminal, j/l toward the next (A2).
        """
        model = self._active_layout()
        if model is None:
            return
        visible = model.visible_ids()
        if len(visible) < 2:
            return
        focused = model.focused_id
        try:
            idx = visible.index(focused)
        except ValueError:
            idx = 0
        step = -1 if direction in ("left", "up") else 1
        target = visible[(idx + step) % len(visible)]
        self._focus_leaf(target)

    def _focus_leaf(self, sid: str) -> None:
        """Focus a visible terminal in the active workspace: model, ring, grab."""
        model = self._active_layout()
        if model is None:
            return
        model.focused_id = sid
        model.touch(sid)
        self._reflect_layout()
        term = self._term_by_sid.get(sid)
        if term is not None:
            term.grab_focus()

    def _cycle_worktree(self, direction: str) -> None:
        """C-Space n/p: cycle the sidebar selection, swapping the WHOLE workspace (D-06/D-07).

        Phase 03.1 re-target: n/p step through EVERY sidebar row in order — the
        pinned ``main`` workspace included (D-07) — and activation swaps the whole
        workspace via ``_on_row_activated`` → ``_swap_workspace`` (not a pane).
        """
        rows = self._all_workspace_rows()
        if not rows:
            return
        current = self._listbox.get_selected_row()
        try:
            idx = rows.index(current)
        except ValueError:
            idx = -1
        step = 1 if direction == "next" else -1
        target = rows[(idx + step) % len(rows)]
        self._listbox.select_row(target)
        self._on_row_activated(self._listbox, target)

    def _jump_to_row(self, n: int) -> None:
        """C-Space <N>: select the Nth sidebar row (1-indexed) + swap the workspace.

        Sidebar order including the pinned ``main`` as row 1 (Discretion A3 / D-07);
        activation swaps the whole workspace via ``_on_row_activated``.
        """
        rows = self._all_workspace_rows()
        if not (1 <= n <= len(rows)):
            return
        target = rows[n - 1]
        self._listbox.select_row(target)
        self._on_row_activated(self._listbox, target)

    def _all_workspace_rows(self) -> list[Gtk.ListBoxRow]:
        """Every sidebar row in display order: the pinned main row, then worktrees.

        n/p and ``C-Space <number>`` cycle/jump across whole workspaces, and the
        pinned ``main`` workspace is a regular row in this order (D-07) so n/p reaches
        main and ``<number>`` is 1-indexed from main (A3).
        """
        rows: list[Gtk.ListBoxRow] = []
        main_row = self._row_by_sid.get(_MAIN_SID)
        if main_row is not None:
            rows.append(main_row)
        for session in self._store.all():
            row = self._row_by_sid.get(session.session_id)
            if row is not None:
                rows.append(row)
        return rows

    # --- repo resolution (D-03) ---------------------------------------------

    def _resolve_repo_root(self) -> None:
        """Resolve the launch repo's toplevel; enable + on success, else hint.

        Runs once at startup BEFORE the main leaf is seeded so the pinned ``main``
        leaf opens in the repo root (the repo's main checkout, D-07 revised) and
        the sidebar shows the repo name. A single ``git rev-parse`` is a short
        read-only host query — blocking briefly at startup is acceptable
        (CLAUDE.md) — and it still routes through the HostRunner seam.
        """
        cwd = os.getcwd()
        argv = self._runner.wrap_argv(["git", "-C", cwd, "rev-parse", "--show-toplevel"])
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=5)
            top = proc.stdout.strip() if proc.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            top = ""

        if top:
            self._repo_root = top
            self._repo_name = os.path.basename(top)
            self._new_btn.set_sensitive(True)
            self._new_btn.set_tooltip_text("Nova worktree")
        else:
            self._repo_root = None
            self._repo_name = None
            self._new_btn.set_sensitive(False)
            self._new_btn.set_tooltip_text(_NO_REPO_HINT)

    # --- + New-worktree dialog (D-06) ---------------------------------------

    def _on_new_worktree_clicked(self, _button) -> None:
        """Cap-gate (RAM-02/D-16), then fetch branches + present the dialog (D-06)."""
        if not self._repo_root:
            return  # button should be insensitive, but guard anyway

        # RAM-02/D-15/D-16: BLOCK at the active-agent cap and force a hibernate
        # BEFORE any worktree is added/spawned — never silent-allow, never
        # create-hibernated. Proceed only once a worktree is freed.
        if caps.at_cap(self._store.all()):
            self._prompt_hibernate_then(self._begin_new_worktree)
            return
        self._begin_new_worktree()

    def _begin_new_worktree(self) -> None:
        """Fetch local branches, then present the type-or-pick dialog (D-06)."""
        def _branches_done(status, out, _err):
            existing = parse_local_branches(out) if status == 0 else []
            self._present_new_worktree_dialog(existing)

        run_git_async(argv_list_local_branches(self._repo_root), _branches_done, self._runner)

    def _prompt_hibernate_then(self, proceed) -> None:
        """Cap-reached gate (D-16): pick an active worktree to hibernate, then run ``proceed``.

        Presents the UI-SPEC prompt with a chooser of active branches. On a pick we
        run the existing hibernate path on that session, THEN call ``proceed`` to
        resume the original creation. On cancel, creation is aborted.
        """
        active = [s for s in self._store.all() if s.state == SessionState.ACTIVE]
        if not active:
            # No active worktree to free (e.g. cap == 0) — just proceed.
            proceed()
            return

        n = caps.active_count(self._store.all())
        dialog = Adw.AlertDialog(
            heading=f"Você está com {n} agentes ativos",
            body="Hiberne uma worktree para liberar RAM antes de abrir outra.",
        )
        chooser = Gtk.DropDown.new_from_strings([s.branch for s in active])
        dialog.set_extra_child(chooser)
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("hibernate", "Hibernar e continuar")
        dialog.set_response_appearance("hibernate", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("hibernate")
        dialog.set_close_response("cancel")

        def _on_response(_dlg, response):
            if response != "hibernate":
                return  # cancel — abort creation, never silent-allow
            idx = chooser.get_selected()
            if idx < 0 or idx >= len(active):
                return
            session = active[idx]
            # Run the existing hibernate path on the chosen session (D-16). Kill
            # EVERY terminal group so RAM is actually freed (Pitfall 3).
            self._teardown_session_terminals(session)
            hibernate_fields(session)
            self._rebuild_sidebar()
            proceed()  # cap freed — resume the original creation

        dialog.connect("response", _on_response)
        dialog.present(self)

    def _present_new_worktree_dialog(self, existing: list[str]) -> None:
        """Type-or-pick branch dialog: typing a new name = new branch (D-06)."""
        dialog = Adw.AlertDialog(
            heading="Nova worktree",
            body="Digite o nome de uma nova branch ou escolha uma existente.",
        )
        combo = Gtk.ComboBoxText.new_with_entry()
        for name in existing:
            combo.append_text(name)
        dialog.set_extra_child(combo)
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("create", "Criar")
        dialog.set_response_appearance("create", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("create")
        dialog.set_close_response("cancel")

        def _on_response(_dlg, response):
            if response != "create":
                return
            branch = (combo.get_active_text() or "").strip()
            if not branch:
                return
            self._create_worktree(branch, existing)

        dialog.connect("response", _on_response)
        dialog.present(self)

    # --- create flow (WT-01/WT-02/WT-03, D-04/D-05/D-07) --------------------

    def _create_worktree(self, branch: str, existing: list[str]) -> None:
        """Born-HEAD guard, porcelain pre-check (D-07), then base chain + add."""
        kind = infer_new_vs_existing(branch, existing)

        def _has_commit_done(hstatus, _hout, _herr):
            if hstatus != 0:
                # UAT: a freshly init'd repo (unborn HEAD) cannot host a worktree.
                # Show a friendly message instead of git's "invalid reference: HEAD".
                self._show_error(
                    "Este repositório ainda não tem commits.",
                    "Faça um commit antes de criar worktrees.",
                )
                return
            self._continue_create_worktree(branch, kind)

        run_git_async(
            argv_repo_has_commit(self._repo_root), _has_commit_done, self._runner
        )

    def _continue_create_worktree(self, branch: str, kind: str) -> None:
        """Porcelain pre-check (D-07), then default-branch chain + add (async)."""

        def _porcelain_done(status, out, _err):
            parsed = parse_worktrees(out) if status == 0 else []
            path = branch_checked_out_path(branch, parsed)
            if path:
                # D-07: swap to the tracked worktree's workspace if arduis owns it...
                session = self._session_for_worktree_dir(path)
                if session is not None:
                    row = self._row_by_sid.get(session.session_id)
                    if row is not None:
                        self._listbox.select_row(row)
                    self._swap_workspace(session.session_id)
                    return
                # ...else it's the main checkout or an untracked worktree: abort.
                self._abort_already_checked_out(branch, path)
                return
            # Not checked out anywhere — resolve the base branch, then add.
            self._resolve_base_then_add(branch, kind)

        run_git_async(
            argv_worktree_list_porcelain(self._repo_root), _porcelain_done, self._runner
        )

    def _resolve_base_then_add(self, branch: str, kind: str) -> None:
        """Default-branch chain (D-04): origin/HEAD -> local HEAD fallback."""
        repo = self._repo_root

        def _origin_done(status, out, _err):
            if status == 0 and out.strip():
                base = parse_default_branch(out)
                self._open_and_add(branch, kind, base)
                return

            def _local_done(lstatus, lout, _lerr):
                base = lout.strip() if lstatus == 0 else "HEAD"
                self._open_and_add(branch, kind, base)

            run_git_async(argv_default_branch_local(repo), _local_done, self._runner)

        run_git_async(argv_default_branch_via_origin(repo), _origin_done, self._runner)

    def _open_and_add(self, branch: str, kind: str, base: str) -> None:
        """Born-with-2-terminals workspace (D-02/D-03), then worktree add + spawn.

        Phase 03.1: a new worktree owns its OWN LayoutModel with two terminals side
        by side — left agent (``claude`` fed) + right plain shell. After ``git
        worktree add`` succeeds, BOTH terminals spawn eagerly (D-03); only the agent
        is fed ``AGENT_FEED``.
        """
        repo = self._repo_root
        wt_dir = worktree_dir_for(repo, branch)

        agent_tid = f"{branch}:t0"
        shell_tid = f"{branch}:t1"

        # Build the worktree's own 2-terminal tree: left agent, right shell (D-02).
        model = self._workspace_layout(branch)
        model.root = LeafNode(agent_tid)
        model.focused_id = agent_tid
        model.touch(agent_tid)
        model.split(agent_tid, shell_tid, "h")  # left agent, right shell (horizontal)
        # split() sets focused to the new (shell) leaf — refocus the agent (left).
        model.focused_id = agent_tid
        model.touch(agent_tid)

        # Two terminals via the palette factory (T-04 — branch rendered with set_text).
        agent_terminal = self._make_terminal()
        agent_terminal.connect("child-exited", self._on_worktree_term_exited)
        agent_leaf = self._make_leaf(agent_tid, branch, agent_terminal, badge_label="claude")
        self._leaf_by_sid[agent_tid] = agent_leaf
        self._term_by_sid[agent_tid] = agent_terminal

        shell_terminal = self._make_terminal()
        shell_terminal.connect("child-exited", self._on_worktree_term_exited)
        shell_leaf = self._make_leaf(shell_tid, branch, shell_terminal, badge_label="zsh")
        self._leaf_by_sid[shell_tid] = shell_leaf
        self._term_by_sid[shell_tid] = shell_terminal

        # Make the new worktree the visible workspace (D-04).
        self._active_workspace_sid = branch
        self._reflect_layout()

        if kind == "new":
            argv = argv_worktree_add_new(repo, branch, wt_dir, base)
        else:
            argv = argv_worktree_add_existing(repo, wt_dir, branch)

        def _add_done(status, _out, err):
            if status != 0:
                # Creation failed — drop BOTH leaves; surface the git error.
                self._show_error("Não foi possível criar a worktree.", err)
                model.close_leaf(agent_tid)
                model.close_leaf(shell_tid)
                self._leaf_by_sid.pop(agent_tid, None)
                self._leaf_by_sid.pop(shell_tid, None)
                self._term_by_sid.pop(agent_tid, None)
                self._term_by_sid.pop(shell_tid, None)
                # Fall back to the main workspace so the canvas isn't empty.
                self._swap_workspace(_MAIN_SID)
                return
            session = WorktreeSession(
                session_id=branch,
                branch=branch,
                worktree_dir=wt_dir,
                repo_root=repo,
                terminals=default_terminals(branch),  # [agent t0, shell t1]
            )
            self._store.add(session)
            self._rebuild_sidebar()
            # D-03: spawn BOTH eagerly. Agent is fed claude; shell stays plain.
            self._spawn_into(agent_terminal, wt_dir, session, agent_tid, kind="agent")
            self._spawn_into(shell_terminal, wt_dir, session, shell_tid, kind="shell")

        run_git_async(argv, _add_done, self._runner)

    def _split_active_pane(self, focused_tid: str) -> None:
        """Split the active workspace, spawning a new agent terminal beside ``focused_tid`` (D-05).

        Every split is an agent terminal by default (D-05) — Ctrl+C drops to the
        shell. The new terminal id is ``f"{sid}:tN"`` where N is the next free index
        for the active worktree; it spawns into the worktree dir and is fed claude.
        """
        sid = self._active_workspace_sid
        if sid is None:
            return
        model = self._workspace_layout(sid)
        new_tid = self._next_term_id(sid)

        session = self._store.get(sid)
        cwd = session.worktree_dir if session is not None else (self._repo_root or GLib.get_home_dir())

        terminal = self._make_terminal()
        terminal.connect("child-exited", self._on_worktree_term_exited)
        label = session.branch if session is not None else (self._repo_name or "main")
        leaf = self._make_leaf(new_tid, label, terminal, badge_label="claude")
        self._leaf_by_sid[new_tid] = leaf
        self._term_by_sid[new_tid] = terminal

        model.split(focused_tid, new_tid, "h")
        self._reflect_layout()

        if session is not None:
            # Track the new split terminal on the session so RAM/teardown see it.
            session.terminals.append(TerminalRecord(new_tid, "agent"))
            self._spawn_into(terminal, cwd, session, new_tid, kind="agent")
        else:
            # main workspace has no store session — spawn plain via the agent path
            # but with no TerminalRecord to write (cwd is repo root / $HOME).
            self._spawn_into(terminal, cwd, None, new_tid, kind="agent")

    def _next_term_id(self, sid: str) -> str:
        """Return the next free ``{sid}:tN`` terminal id for worktree ``sid``."""
        n = 0
        while f"{sid}:t{n}" in self._term_by_sid:
            n += 1
        return f"{sid}:t{n}"

    # --- spawn + feed claude (WT-03, D-08) ----------------------------------

    def _spawn_into(
        self,
        terminal: Vte.Terminal,
        cwd: str,
        session: WorktreeSession | None,
        term_id: str,
        kind: str = "agent",
    ) -> None:
        """Spawn zsh -l -i in ``cwd``; feed AGENT_FEED only when ``kind == "agent"``.

        Writes the spawned ``pid``/``pgid`` onto the matching ``TerminalRecord`` in
        ``session.terminals`` (found by ``term_id``). A plain ``shell`` terminal
        (D-02 right pane) is NOT fed ``claude``.
        """
        argv, envv = build_worktree_spawn(self._runner)
        terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            cwd,                  # per-worktree working directory (WT-03)
            argv,                 # ["zsh", "-l", "-i"]
            envv,                 # ["TERM=xterm-256color"]
            GLib.SpawnFlags.DEFAULT,
            None,                 # child_setup
            None,                 # child_setup_data
            -1,                   # timeout (-1 = none)
            None,                 # cancellable
            self._make_wt_spawn_cb(session, term_id, kind),
        )
        terminal.grab_focus()

    def _make_wt_spawn_cb(self, session: WorktreeSession | None, term_id: str, kind: str):
        def _on_wt_spawned(terminal, pid, error):
            if error is not None or pid == -1:
                return  # D-09: no banner; the pane stays a usable shell
            # Write pid/pgid onto the matching TerminalRecord (N-terminal model).
            if session is not None:
                record = next(
                    (t for t in session.terminals if t.term_id == term_id), None
                )
                if record is not None:
                    record.pid = pid
                    try:
                        record.pgid = os.getpgid(pid)  # A1: don't assume pgid == pid
                    except ProcessLookupError:
                        record.pgid = None
            if kind == "agent":
                terminal.feed_child(AGENT_FEED)  # b"claude\n" — bytes (Pitfall 5)
        return _on_wt_spawned

    def _on_worktree_term_exited(self, terminal, status):
        """A worktree shell exiting is local — do not close the whole window."""
        # The pane's shell ended (e.g. user typed `exit`); leave the leaf/dir.
        return

    # --- ~2s off-loop RAM poll (RAM-03/D-12/D-14) ---------------------------

    def _poll_ram(self) -> bool:
        """Write live process-group RSS onto each active session; refresh the UI.

        Runs on the GLib main loop every ~2s (NOT a thread — CLAUDE.md). Bounded to
        the 5–12 active groups (sub-ms, Assumption A1); hibernated/pgid-None sessions
        are skipped (Pitfall 3) and per-pid errors are swallowed inside
        ``group_rss_kb``. Returns ``SOURCE_CONTINUE`` so the timeout keeps firing.
        """
        for session in self._store.all():
            if session.state != SessionState.ACTIVE:
                continue  # skip hibernated (Pitfall 3)
            # D-10: a worktree's RAM is the SUM of all its terminal process groups.
            total = 0
            for t in session.terminals:
                if t.pgid is None:
                    continue  # not-yet-spawned terminal
                t.rss_kb = resource_monitor.group_rss_kb(t.pgid)
                if t.rss_kb:
                    total += t.rss_kb
            label = self._subline_by_sid.get(session.session_id)
            if label is not None:
                label.set_text(
                    f"claude · {resource_monitor.format_ram_kb(total or None)}"
                )
        self._update_footer()
        return GLib.SOURCE_CONTINUE

    def _update_footer(self) -> None:
        """Render ``N agentes ativos · <total> RAM`` (active count in green)."""
        if self._footer_label is None:
            return
        sessions = self._store.all()
        n = caps.active_count(sessions)
        # D-10: aggregate sums every active worktree's terminal RAM.
        total = sum(
            t.rss_kb
            for s in sessions
            if s.state == SessionState.ACTIVE
            for t in s.terminals
            if t.rss_kb is not None
        )
        total_str = resource_monitor.format_ram_kb(total if total else None)
        self._footer_label.set_markup(
            f'<span foreground="{_DOT_ACTIVE}" weight="bold">{n} agentes ativos</span>'
            f" · {total_str} RAM"
        )

    # --- canvas reflection: model tree -> Gtk.Paned widgets (D-01) ----------

    def _reflect_layout(self) -> None:
        """Rebuild the canvas widget tree from the layout model (Pattern 1).

        Walks the GTK-free ``LayoutModel``: a ``SplitNode`` becomes a draggable
        ``Gtk.Paned``; a ``LeafNode`` becomes its mapped pane widget. Detaches
        every leaf from its previous parent FIRST (single-parent rule, Pitfall 1)
        so widgets can be re-hung without "already has a parent" crashes.
        """
        # Detach the old root + every mapped leaf so they are parent-free before
        # we re-hang them (GTK4 single-parent rule, Pitfall 1). VTE widgets + their
        # PTY children SURVIVE unparenting (A1/Pitfall 2) — a swap never respawns.
        if self._canvas_slot.get_child() is not None:
            self._canvas_slot.set_child(None)
        for leaf in self._leaf_by_sid.values():
            if leaf.get_parent() is not None:
                leaf.unparent()

        # Phase 03.1: read the ACTIVE worktree's tree, not a global tree (D-04).
        model = self._active_layout()
        if model is None or model.root is None:
            self._canvas_slot.set_child(self._build_widget(None))
            return
        self._canvas_slot.set_child(self._build_widget(model.root))

        # Apply the focused-pane purple ring to exactly one leaf (UI-SPEC).
        focused = model.focused_id
        for sid, leaf in self._leaf_by_sid.items():
            if sid == focused:
                leaf.add_css_class("focus")
            else:
                leaf.remove_css_class("focus")

    def _build_widget(self, node) -> Gtk.Widget:
        """Reflect one layout node into a widget (SplitNode->Paned, LeafNode->leaf)."""
        if node is None:
            # Empty canvas — a neutral placeholder box.
            return Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        if isinstance(node, LeafNode):
            if node.session_id is None:
                return Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            leaf = self._leaf_by_sid.get(node.session_id)
            if leaf is None:
                # A leaf id with no widget (shouldn't happen) — neutral filler.
                return Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            return leaf
        if isinstance(node, SplitNode):
            orient = (
                Gtk.Orientation.HORIZONTAL if node.orientation == "h"
                else Gtk.Orientation.VERTICAL
            )
            paned = Gtk.Paned(orientation=orient)
            paned.set_wide_handle(True)            # visible draggable gutter
            paned.set_shrink_start_child(False)    # honor each leaf's min size
            paned.set_shrink_end_child(False)
            paned.set_start_child(self._build_widget(node.start))
            paned.set_end_child(self._build_widget(node.end))
            return paned
        return Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    # --- helpers: session lookup + user messaging ---------------------------

    def _session_for_worktree_dir(self, path: str) -> WorktreeSession | None:
        """Return the tracked session whose worktree_dir matches ``path``."""
        norm = path.rstrip("/")
        for s in self._store.all():
            if s.worktree_dir.rstrip("/") == norm:
                return s
        return None

    def _abort_already_checked_out(self, branch: str, path: str) -> None:
        """D-07: clear abort message — NEVER --force."""
        self._show_error(
            f"A branch '{branch}' já está em uso",
            f"Ela está em uso em {path}. Escolha outra branch.",
        )

    def _show_error(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body or "")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.present(self)

    # --- row context menu: Hibernate / Resume (D-08) ------------------------

    def _install_row_actions(self) -> None:
        """Register win.hibernate / win.resume actions (reused from Phase 2)."""
        hibernate = Gio.SimpleAction.new("hibernate", None)
        hibernate.connect("activate", self._on_hibernate)
        self.add_action(hibernate)

        resume = Gio.SimpleAction.new("resume", None)
        resume.connect("activate", self._on_resume)
        self.add_action(resume)

    def _menu_session(self) -> WorktreeSession | None:
        """Resolve the right-clicked row back to its tracked session (D-08)."""
        if self._menu_target_sid is None:
            return None
        return self._store.get(self._menu_target_sid)

    def _on_hibernate(self, _action, _param) -> None:
        """D-08: kill ALL the worktree's terminal groups, keep the dir, dim the row.

        Full hibernate re-targeting (active-workspace fallback, layout clearing,
        D-09 resume) lands in plan 03; here it tears down every terminal group so RAM
        is actually freed under the N-terminal model (Pitfall 3).
        """
        session = self._menu_session()
        if session is None or session.state == SessionState.HIBERNATED:
            return
        self._teardown_session_terminals(session)  # kill every group (Pitfall 3/5)
        hibernate_fields(session)  # GTK-free: state=HIBERNATED, all pid/pgid=None
        self._rebuild_sidebar()    # dim/grey-dot the row (D-08, not a tab badge)

    def _on_resume(self, _action, _param) -> None:
        """D-09: cold relaunch the agent terminal (fresh zsh+claude), not a reattach.

        The full D-09 default-layout rebuild (re-spawn agent + shell, discard the
        saved tree) is plan 03's. Here we keep resume crash-free under the N-terminal
        model by re-spawning the agent terminal (keyed by ``{sid}:t0``).
        """
        session = self._menu_session()
        if session is None or session.state == SessionState.ACTIVE:
            return
        session.state = SessionState.ACTIVE
        self._rebuild_sidebar()
        agent_tid = f"{session.session_id}:t0"
        terminal = self._term_by_sid.get(agent_tid)
        if terminal is not None:
            self._spawn_into(
                terminal, session.worktree_dir, session, agent_tid, kind="agent"
            )

    # --- teardown (RAM-01, D-11/D-13) ---------------------------------------

    def _teardown_pgid(self, pid: int) -> None:
        """SIGHUP the child's process GROUP, then SIGKILL-sweep (no orphans)."""
        try:
            pgid = os.getpgid(pid)  # A1: don't assume pgid == pid
            os.killpg(pgid, signal.SIGHUP)
            GLib.timeout_add(_SIGKILL_GRACE_MS, self._sigkill_if_alive, pgid)
        except ProcessLookupError:
            pass  # already gone

    def _teardown_session_terminals(self, session: WorktreeSession) -> None:
        """Tear down EVERY terminal's process group for a worktree (Pitfall 3/4).

        The N-terminal model means a worktree owns a list of terminals (agent +
        shell + any splits); each carries its own pid. Killing only ``terminals[0]``
        would orphan the split agents and leak RAM (D-08). Plan 03 adds the rest of
        the hibernate/resume re-targeting; this iterates the groups so no terminal
        is forgotten by the existing hibernate/close call sites.
        """
        for t in session.terminals:
            if t.pid:
                self._teardown_pgid(t.pid)

    def _on_close_request(self, *_):
        """No-orphan teardown across ALL panes (D-13): scratch shell + sessions."""
        # Stop the ~2s RAM poll first so no source outlives the window (RAM-03).
        if self._ram_source is not None:
            GLib.source_remove(self._ram_source)
            self._ram_source = None
        if self._shell_pid:
            self._teardown_pgid(self._shell_pid)
        # D-13: tear down EVERY terminal group of EVERY session (N-terminal model);
        # iterating session.pid alone would orphan split agents (Pitfall 3/4).
        for session in self._store.all():
            self._teardown_session_terminals(session)
        return False  # allow the window to close

    def _sigkill_if_alive(self, pgid):
        """SIGKILL sweep after the grace period if anything survived."""
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return GLib.SOURCE_REMOVE
