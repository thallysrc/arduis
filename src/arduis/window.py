"""ArduisWindow — GTK4/libadwaita window hosting the core loop.

Phase 2 rewires the Phase-1 single-terminal window into an ``Adw.TabView`` /
``Adw.TabBar`` whose ``+`` button opens the "New worktree" dialog, creates a
worktree via ``git worktree add`` (async, off the GTK loop through
``git_service.run_git_async``), opens a tab whose VTE terminal spawns
``zsh -l -i`` in the worktree dir and feeds ``b"claude\\n"``, and adds a
right-click Hibernate/Resume menu that reuses the Phase-1 process-group
teardown — generalized so closing the window leaves no orphan across N tabs.

Layering: this is the ONLY presentation module that imports ``gi``. All
branch/dir/argv logic stays in the GTK-free ``worktree.py``; the session model
lives in ``session.py``; async git runs through ``git_service.py``. ``window.py``
only orchestrates.

Decisions wired here:
- D-02: tab 0 is the unchanged Phase-1 ``$HOME`` scratch shell (no session).
- D-03: ``+`` disabled with a hint when launched outside a git repo.
- D-04/D-05: default-branch chain (origin -> local), sibling dir from worktree.py.
- D-06: type-or-pick branch dialog.
- D-07: porcelain pre-check — focus existing tab / clear abort, NEVER --force.
- D-08: feed ``AGENT_FEED`` bytes after the spawn pid arrives (WT-03).
- D-09: a failed/absent ``claude`` needs no handling — the shell stays usable.
- D-10/D-11/D-12: hibernate kills the group + keeps the dir; resume cold-relaunches.
- D-13: window-close tears down ALL active sessions (no orphans).

Targets the VTE 0.76 API floor (D-03) so one codebase runs on Ubuntu (0.76)
and Arch (0.84).
"""
from __future__ import annotations

import os
import signal

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")  # GTK4 binding — needs gir1.2-vte-3.91 installed
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango, Vte  # noqa: E402

from arduis.host_runner import HostRunner  # noqa: E402
from arduis.spawn import build_spawn_command, build_worktree_spawn  # noqa: E402
from arduis.exit_status import decode_exit  # noqa: E402
from arduis.git_service import run_git_async  # noqa: E402
from arduis.session import (  # noqa: E402
    AGENT_FEED,
    SessionState,
    SessionStore,
    WorktreeSession,
    hibernate_fields,
)
from arduis.worktree import (  # noqa: E402
    argv_default_branch_local,
    argv_default_branch_via_origin,
    argv_list_local_branches,
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


def _rgba(spec: str) -> Gdk.RGBA:
    """Parse a hex color string into a ``Gdk.RGBA`` (GTK lives only here)."""
    color = Gdk.RGBA()
    color.parse(spec)
    return color


class ArduisWindow(Adw.ApplicationWindow):
    """A tabbed window: tab 0 = host scratch shell, +N worktree-agent tabs."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._runner = HostRunner()
        self._store = SessionStore()
        # tab 0 (the Phase-1 $HOME scratch shell) is NOT a session.
        self._shell_pid: int | None = None
        self._last_exit: int | None = None
        self._repo_root: str | None = None

        # per-session widget maps (session_id -> widget) + reverse page lookup.
        self._page_by_sid: dict[str, Adw.TabPage] = {}
        self._term_by_sid: dict[str, Vte.Terminal] = {}
        self._sid_by_page: dict[Adw.TabPage, str] = {}

        self.set_title("arduis")
        self.set_default_size(960, 620)

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title="arduis"))

        # The "+New worktree" button lives in the header (D-02/D-03). Disabled
        # until repo resolution succeeds.
        self._new_btn = Gtk.Button()
        self._new_btn.set_icon_name("list-add-symbolic")
        self._new_btn.set_tooltip_text("New worktree")
        self._new_btn.set_sensitive(False)  # enabled once _repo_root resolves
        self._new_btn.connect("clicked", self._on_new_worktree_clicked)
        header.pack_start(self._new_btn)
        view.add_top_bar(header)

        # Adw.TabView (the tab content stack) + Adw.TabBar (the visible strip).
        self._tabs = Adw.TabView()
        tabbar = Adw.TabBar(view=self._tabs)
        view.add_top_bar(tabbar)
        view.set_content(self._tabs)
        self.set_content(view)

        # Right-click tab menu: Hibernate / Resume (D-10).
        self._install_tab_menu()

        # GTK4 window-close signal (Pitfall 5: NOT GTK3 "delete-event").
        self.connect("close-request", self._on_close_request)

        # Tab 0: the unchanged Phase-1 $HOME scratch shell (D-02).
        self._open_shell_tab()

        # Resolve the launch repo asynchronously (D-03). Enables + on success.
        self._resolve_repo_root()

    # --- terminal factory (extracted Phase-1 setup) -------------------------

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

    # --- tab 0: Phase-1 $HOME scratch shell (D-02) --------------------------

    def _open_shell_tab(self) -> None:
        """Append tab 0 — the $HOME zsh scratch shell. Not a worktree session."""
        terminal = self._make_terminal()
        terminal.connect("child-exited", self._on_shell_exited)
        page = self._tabs.append(terminal)
        page.set_title("shell")

        argv, envv = build_spawn_command(self._runner)
        terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            GLib.get_home_dir(),  # working_directory (D-10)
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
        """Capture tab 0's PID for teardown; ignore a failed spawn."""
        if error is not None or pid == -1:
            return
        self._shell_pid = pid

    def _on_shell_exited(self, terminal, status):
        """Tab 0 exiting closes the window (D-12 — the scratch shell is primary)."""
        self._last_exit = decode_exit(status)
        self.close()

    # --- repo resolution (D-03) ---------------------------------------------

    def _resolve_repo_root(self) -> None:
        """Resolve the launch repo's toplevel; enable + on success, else hint."""
        cwd = os.getcwd()
        argv = ["git", "-C", cwd, "rev-parse", "--show-toplevel"]

        def _done(status, out, _err):
            if status == 0 and out.strip():
                self._repo_root = out.strip()
                self._new_btn.set_sensitive(True)
                self._new_btn.set_tooltip_text("New worktree")
            else:
                self._repo_root = None
                self._new_btn.set_sensitive(False)
                self._new_btn.set_tooltip_text(_NO_REPO_HINT)

        run_git_async(argv, _done, self._runner)

    # --- + New-worktree dialog (D-06) ---------------------------------------

    def _on_new_worktree_clicked(self, _button) -> None:
        """Fetch local branches, then present the type-or-pick dialog (D-06)."""
        if not self._repo_root:
            return  # button should be insensitive, but guard anyway

        def _branches_done(status, out, _err):
            existing = parse_local_branches(out) if status == 0 else []
            self._present_new_worktree_dialog(existing)

        run_git_async(argv_list_local_branches(self._repo_root), _branches_done, self._runner)

    def _present_new_worktree_dialog(self, existing: list[str]) -> None:
        """Type-or-pick branch dialog: typing a new name = new branch (D-06)."""
        dialog = Adw.AlertDialog(
            heading="New worktree",
            body="Type a new branch name or pick an existing branch.",
        )
        combo = Gtk.ComboBoxText.new_with_entry()
        for name in existing:
            combo.append_text(name)
        dialog.set_extra_child(combo)
        dialog.add_response("cancel", "Cancel")
        dialog.add_response("create", "Create")
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
        """Porcelain pre-check (D-07), then default-branch chain + add (async)."""
        kind = infer_new_vs_existing(branch, existing)

        def _porcelain_done(status, out, _err):
            parsed = parse_worktrees(out) if status == 0 else []
            path = branch_checked_out_path(branch, parsed)
            if path:
                # D-07: focus the tracked tab if arduis owns this worktree...
                session = self._session_for_worktree_dir(path)
                if session is not None:
                    self._tabs.set_selected_page(self._page_by_sid[session.session_id])
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
        """Open the tab immediately (loading spinner), then run worktree add."""
        repo = self._repo_root
        wt_dir = worktree_dir_for(repo, branch)

        # Instant "in seconds" feedback (Open Q2): open the tab loading.
        terminal = self._make_terminal()
        terminal.connect("child-exited", self._on_worktree_term_exited)
        page = self._tabs.append(terminal)
        page.set_title(branch)
        page.set_loading(True)
        self._tabs.set_selected_page(page)

        if kind == "new":
            argv = argv_worktree_add_new(repo, branch, wt_dir, base)
        else:
            argv = argv_worktree_add_existing(repo, wt_dir, branch)

        def _add_done(status, _out, err):
            page.set_loading(False)
            if status != 0:
                # Creation failed — abort the tab; surface the git error.
                self._show_error(f"Could not create worktree for '{branch}'", err)
                self._tabs.close_page(page)
                return
            session = WorktreeSession(
                session_id=branch,
                branch=branch,
                worktree_dir=wt_dir,
                repo_root=repo,
            )
            self._store.add(session)
            self._page_by_sid[branch] = page
            self._term_by_sid[branch] = terminal
            self._sid_by_page[page] = branch
            self._spawn_into(terminal, wt_dir, session)

        run_git_async(argv, _add_done, self._runner)

    # --- spawn + feed claude (WT-03, D-08) ----------------------------------

    def _spawn_into(self, terminal: Vte.Terminal, cwd: str, session: WorktreeSession) -> None:
        """Spawn zsh -l -i in the worktree dir; feed AGENT_FEED in the callback."""
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
            self._make_wt_spawn_cb(session),
        )
        terminal.grab_focus()

    def _make_wt_spawn_cb(self, session: WorktreeSession):
        def _on_wt_spawned(terminal, pid, error):
            if error is not None or pid == -1:
                return  # D-09: no banner; the tab stays a usable shell
            session.pid = pid
            try:
                session.pgid = os.getpgid(pid)  # A1: don't assume pgid == pid
            except ProcessLookupError:
                session.pgid = None
            terminal.feed_child(AGENT_FEED)  # b"claude\n" — bytes (Pitfall 1)
        return _on_wt_spawned

    def _on_worktree_term_exited(self, terminal, status):
        """A worktree shell exiting is local — do not close the whole window."""
        # The tab's shell ended (e.g. user typed `exit`); leave the tab/dir.
        return

    # --- helpers: session/page lookup + user messaging ----------------------

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
            f"Branch '{branch}' is already checked out",
            f"It is checked out at {path}. Pick a different branch.",
        )

    def _show_error(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body or "")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.present(self)

    # --- tab context menu: Hibernate / Resume (D-10) ------------------------

    def _install_tab_menu(self) -> None:
        """Right-click tab menu wired to win.hibernate / win.resume actions."""
        menu = Gio.Menu()
        menu.append("Hibernate", "win.hibernate")
        menu.append("Resume", "win.resume")
        self._tabs.set_menu_model(menu)

        hibernate = Gio.SimpleAction.new("hibernate", None)
        hibernate.connect("activate", self._on_hibernate)
        self.add_action(hibernate)

        resume = Gio.SimpleAction.new("resume", None)
        resume.connect("activate", self._on_resume)
        self.add_action(resume)

    def _selected_session(self) -> WorktreeSession | None:
        """Resolve the currently selected tab back to its tracked session."""
        page = self._tabs.get_selected_page()
        if page is None:
            return None
        sid = self._sid_by_page.get(page)
        if sid is None:
            return None  # tab 0 / untracked page — no session
        return self._store.get(sid)

    def _on_hibernate(self, _action, _param) -> None:
        """D-11: kill the worktree process GROUP, keep the dir, dim the tab."""
        session = self._selected_session()
        if session is None or session.state == SessionState.HIBERNATED:
            return
        if session.pid:
            self._teardown_pgid(session.pid)  # kills zsh + claude GROUP (Pitfall 5)
        hibernate_fields(session)  # GTK-free: state=HIBERNATED, pid/pgid=None
        page = self._page_by_sid[session.session_id]
        page.set_needs_attention(True)  # dim/badge as suspended (D-10)

    def _on_resume(self, _action, _param) -> None:
        """D-12: cold relaunch (fresh zsh+claude) — not a reattach (v2/PERSIST-01)."""
        session = self._selected_session()
        if session is None or session.state == SessionState.ACTIVE:
            return
        session.state = SessionState.ACTIVE
        page = self._page_by_sid[session.session_id]
        page.set_needs_attention(False)
        terminal = self._term_by_sid[session.session_id]
        self._spawn_into(terminal, session.worktree_dir, session)  # re-feeds AGENT_FEED

    # --- teardown (RAM-01, D-11/D-13) ---------------------------------------

    def _teardown_pgid(self, pid: int) -> None:
        """SIGHUP the child's process GROUP, then SIGKILL-sweep (no orphans)."""
        try:
            pgid = os.getpgid(pid)  # A1: don't assume pgid == pid
            os.killpg(pgid, signal.SIGHUP)
            GLib.timeout_add(_SIGKILL_GRACE_MS, self._sigkill_if_alive, pgid)
        except ProcessLookupError:
            pass  # already gone

    def _on_close_request(self, *_):
        """No-orphan teardown across ALL tabs (D-13): tab 0 + every session."""
        if self._shell_pid:
            self._teardown_pgid(self._shell_pid)
        for session in self._store.all():
            if session.pid:
                self._teardown_pgid(session.pid)
        return False  # allow the window to close

    def _sigkill_if_alive(self, pgid):
        """SIGKILL sweep after the grace period if anything survived."""
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return GLib.SOURCE_REMOVE
