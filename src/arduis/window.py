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
- D-04 (discretion): closing a pane HIDES the worktree (leaf dropped from the
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
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import tomllib

import json

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")  # GTK4 binding — needs gir1.2-vte-3.91 installed
from gi.repository import Adw, Gdk, Gio, GLib, Gtk, Pango, Vte  # noqa: E402

# Phase 4 (STATUS-03): libnotify is OPTIONAL — guarded at import so a box without
# gir1.2-notify-0.7 silently disables notifications rather than crashing the app
# (Notify 0.7 is probed-present on the dev machine; the guard is for other boxes).
try:
    gi.require_version("Notify", "0.7")
    from gi.repository import Notify  # noqa: E402

    _HAS_NOTIFY = True
except (ValueError, ImportError):  # pragma: no cover - depends on host gir set
    Notify = None  # type: ignore[assignment]
    _HAS_NOTIFY = False

from arduis.host_runner import HostRunner  # noqa: E402
from arduis.spawn import build_spawn_command, build_worktree_spawn  # noqa: E402
from arduis.exit_status import decode_exit  # noqa: E402
from arduis.git_service import run_git_async  # noqa: E402
from arduis import compose, containerstate, docker_service  # noqa: E402
from arduis import gh, review  # noqa: E402  (Phase 8: read-only diff/PR surfaces)
from arduis.review_cache import ReviewCache, GH_TTL_S  # noqa: E402
from arduis import attention, caps, resource_monitor  # noqa: E402
from arduis.attention import AgentStatus  # noqa: E402
from arduis.layout import LayoutModel, LeafNode, SplitNode  # noqa: E402
from arduis.project import (  # noqa: E402
    Project,
    ProjectRegistry,
    detect_member_repos,
    ensure_project,
    project_term_id,
)
from arduis import projects_store  # noqa: E402
from arduis import layout_store  # noqa: E402
from arduis.session import (  # noqa: E402
    RepoCheckout,
    SessionState,
    SessionStore,
    Workspace,
    TerminalRecord,
    default_workspace_terminals,
    hibernate_fields,
)
from arduis import agentconfig, appconfig, claude_trust, keyconfig, repoconfig, trust  # noqa: E402
from arduis import voice, voice_store, voiceconfig  # noqa: E402  (voice agent)
from arduis.voice_controller import VoiceController  # noqa: E402  (Gst is lazy inside)
from arduis.themes import THEMES, Theme, get_theme  # noqa: E402
from arduis.workspace_layout import (  # noqa: E402
    repo_worktree_dir,
    resolve_repo_add,
    symlink_plan,
    workspace_dir_for,
)
from arduis.worktree import (  # noqa: E402
    argv_default_branch_local,
    argv_default_branch_via_origin,
    argv_list_local_branches,
    argv_repo_has_commit,
    argv_worktree_list_porcelain,
    parse_default_branch,
    parse_local_branches,
    parse_worktrees,
)
_SIGKILL_GRACE_MS = 1500  # time between SIGHUP and the SIGKILL sweep (D-13)
_NO_REPO_HINT = "Launch arduis inside a git repo to create worktrees"

# The pinned $HOME scratch shell is a layout leaf but NOT a store session (D-07).
_MAIN_SID = "main"

_SIDEBAR_WIDTH = 264   # fixed-ish sidebar width (sectioned parallel-code layout)
_PANE_HEADER_H = 32    # UI-SPEC: pane-header height
_MIN_PANE_W = 240      # UI-SPEC: min usable terminal width
_MIN_PANE_H = 120      # UI-SPEC: min usable terminal height

# UI-SPEC Color (Dracula, mirrored from theme.py).
#
# Phase 5 (UI-02): these 8 module constants are NO LONGER the color source — every
# CSS/set_colors path now reads the active ``Theme`` (``self._current_theme``). They
# remain only as documented DEAD Dracula fallbacks (the values match
# ``themes.DRACULA``); ``_build_css`` and ``_make_terminal`` substitute the Theme
# fields instead (Pitfall 2). Do not reintroduce them as the live source.
_DOT_ACTIVE = "#50fa7b"      # active agent dot (green) — also RUNNING (D-06)
_DOT_HIBERNATED = "#6272a4"  # hibernated dot (grey) — also ENDED (D-06)
# Phase 4 attention dot colors (D-06): waiting orange, ready cyan, idle muted
# grey-green. running reuses _DOT_ACTIVE; ended + hibernated stay _DOT_HIBERNATED.
_DOT_WAITING = "#ffb86c"     # waiting (orange) — THE attention dot
_DOT_READY = "#8be9fd"       # ready (cyan)
_DOT_IDLE = "#7a9e7e"        # idle (muted grey-green, D-06)
_BRANCH_PINK = "#ff79c6"     # pane-header branch label
_FOCUS_RING = "#bd93f9"      # focused-pane purple ring
_BG2 = "#21222c"             # sidebar / header / pane-header surface


def _build_css(theme: Theme) -> str:
    """Build the display CSS for ``theme`` (UI-02, D-07/Pitfall 1/2).

    Every class/selector is identical to the pre-Phase-5 ``_CSS`` f-string — only the
    color VALUES become per-theme: ``theme.surface`` (was ``_BG2``), ``theme.accent``
    (was ``_FOCUS_RING`` — the focus ring + badge + hint-key), ``theme.branch`` (was
    ``_BRANCH_PINK``), and the 5 status-dot colors. The footer-count reuses
    ``theme.dot_active`` (it reused ``_DOT_ACTIVE`` before).

    Card-style restyle (parallel-code look): every leaf is a rounded "island" with
    a subtle 1px border that is ALWAYS present — focus only changes the border
    COLOR, so focusing never reflows the layout. The optional Theme fields fall
    back so the 4 legacy themes keep working: card→surface, border→surface,
    canvas→bg.
    """
    card = theme.card or theme.surface
    border = theme.border or theme.surface
    canvas = theme.canvas or theme.bg
    return f"""
headerbar {{
    background-color: {theme.surface};
    box-shadow: none;
}}
.arduis-sidebar {{
    background-color: {theme.surface};
    border-right: 1px solid {border};
}}
.arduis-sidebar list {{
    background: none;
    background-color: transparent;
}}
.arduis-sidebar row {{
    border-radius: 6px;
}}
.arduis-sidebar row:selected {{
    background-color: alpha({theme.accent}, 0.20);
    box-shadow: inset 3px 0 0 0 {theme.accent};
}}
.arduis-pane-header {{
    background-color: transparent;
    min-height: {_PANE_HEADER_H}px;
    padding: 0 12px;
    border-bottom: 1px solid {border};
}}
.arduis-pane-header button {{
    opacity: 0.55;
    min-height: 22px;
    min-width: 22px;
    padding: 0 4px;
}}
.arduis-pane-header button:hover {{
    opacity: 1;
}}
.arduis-branch {{
    color: {theme.branch};
    font-weight: 600;
    font-size: 13px;
}}
.arduis-badge {{
    color: {theme.accent};
    font-size: 11px;
}}
.arduis-leaf {{
    background-color: {card};
    border: 1px solid {border};
    border-radius: 10px;
}}
.arduis-leaf vte-terminal {{
    padding: 4px 8px;
}}
.arduis-row-close {{
    opacity: 0.35;
    font-size: 11px;
    min-height: 20px;
    min-width: 20px;
    padding: 0 4px;
}}
.arduis-row-close:hover {{
    opacity: 1;
}}
.arduis-degraded-hint {{
    font-size: 11px;
    opacity: 0.7;
}}
/* Adw.AlertDialog (libadwaita 1.5 floating sheet) themed like a card: the
   visible surface is the `sheet` node; buttons live in `.response-area`
   (`suggested`/`destructive` appearance classes); `dimming` is the backdrop. */
dialog.alert sheet {{
    background-color: {card};
    color: {theme.fg};
    border: 1px solid {border};
    border-radius: 12px;
}}
dialog.alert sheet separator {{
    background-color: {border};
}}
dialog.alert .response-area button {{
    color: {theme.fg};
    font-weight: 600;
}}
dialog.alert .response-area button.suggested {{
    color: {theme.accent};
}}
dialog.alert .response-area button.destructive {{
    color: {theme.palette[9]};
}}
dialog.alert dimming {{
    background-color: alpha({canvas}, 0.55);
}}
.arduis-leaf.focus {{
    border-color: {theme.accent};
    box-shadow: inset 0 0 0 1px {theme.accent};
}}
/* Attention beats focus (declared later, same specificity): a WAITING agent's
   whole card rings in the attention color — visible from across the canvas. */
.arduis-leaf.attention {{
    border-color: {theme.dot_waiting};
    box-shadow: inset 0 0 0 1px {theme.dot_waiting};
}}
.arduis-row-attention {{
    background-color: alpha({theme.dot_waiting}, 0.14);
}}
.arduis-row-attention .arduis-row-branch {{
    color: {theme.dot_waiting};
}}
/* End-of-turn: the agent finished and sits at its prompt. Signaled by the blue
   status DOT alone (.arduis-dot-ready) — the card is intentionally NOT ringed.
   The loud full-card ring stays exclusive to WAITING (orange approvals). The
   `.arduis-leaf.attention-ready` class is still applied by the status logic but
   carries no card border/shadow. */
.arduis-row-attention-ready {{
    background-color: alpha({theme.dot_ready}, 0.14);
}}
.arduis-row-attention-ready .arduis-row-branch {{
    color: {theme.dot_ready};
}}
.arduis-canvas {{
    border: none;
    background-color: {canvas};
    padding: 12px;
}}
.arduis-split > separator {{
    background: none;
    background-color: transparent;
    border: none;
    min-width: 12px;
    min-height: 12px;
}}
.arduis-section-title {{
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    opacity: 0.55;
}}
.arduis-new-workspace-btn {{
    background-color: {card};
    border: 1px solid {border};
    border-radius: 8px;
    padding: 6px 12px;
    font-weight: 600;
}}
.arduis-project-row {{
    border-radius: 6px;
    font-size: 13px;
}}
.arduis-project-active {{
    background-color: {card};
    font-weight: 600;
}}
.arduis-dot-active {{
    color: {theme.dot_active};
}}
.arduis-dot-hibernated {{
    color: {theme.dot_hibernated};
}}
.arduis-dot-waiting {{
    color: {theme.dot_waiting};
}}
.arduis-dot-ready {{
    color: {theme.dot_ready};
}}
.arduis-dot-idle {{
    color: {theme.dot_idle};
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
.arduis-sidebar-footer {{
    font-size: 11px;
    border-top: 1px solid {border};
}}
.arduis-hint-key {{
    color: {theme.accent};
    font-weight: 600;
    font-size: 11px;
}}
.arduis-footer-count {{
    color: {theme.dot_active};
    font-weight: 600;
}}
/* Voice agent: pulsing mic while recording, steady accent while transcribing. */
.voice-recording {{
    color: {theme.dot_waiting};
    animation: arduis-voice-pulse 1.2s ease-in-out infinite;
}}
@keyframes arduis-voice-pulse {{
    0%   {{ opacity: 1.0; }}
    50%  {{ opacity: 0.35; }}
    100% {{ opacity: 1.0; }}
}}
.voice-transcribing {{
    color: {theme.accent};
}}
"""


def _rgba(spec: str) -> Gdk.RGBA:
    """Parse a hex color string into a ``Gdk.RGBA`` (GTK lives only here)."""
    color = Gdk.RGBA()
    color.parse(spec)
    return color


def _read_keys_section(path: str) -> dict:
    """Tolerantly read ``[keys]`` (UI-01, D-04/D-05) -> ``{"prefix", "bindings"}``.

    ``keyconfig.resolve_prefix``/``resolve_keymap`` take the RAW values (not the
    file), so the tomllib read lives here next to the other config reads in
    ``__init__``. Any failure (missing file, invalid TOML, no ``[keys]`` table) or a
    wrong-typed sub-value degrades to ``{}`` — the resolvers then fall back to the
    defaults. Mirrors ``attention.load_config``'s tolerant pattern.
    """
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    section = data.get("keys")
    if not isinstance(section, dict):
        return {}
    out: dict = {}
    prefix = section.get("prefix")
    if isinstance(prefix, str):
        out["prefix"] = prefix
    bindings = section.get("bindings")
    if isinstance(bindings, dict):
        out["bindings"] = bindings
    return out


def _learned_ratio(
    position: int, max_position: int, last_set: int, settled: bool
) -> float | None:
    """Ratio to learn from a ``Gtk.Paned`` position change, or ``None`` to ignore.

    Guards ``_init_paned_position``'s drag-learning against transient/spurious
    ``notify::position`` emissions (split-black-pane-hole). We only learn a user
    drag; everything else must be rejected so a bad ratio never gets persisted to
    ``layouts.json`` (which would produce a resize-RESISTANT black hole):

    - ``max_position <= 1``  → the paned has no real allocation yet; the read is
      meaningless. Ignore.
    - ``not settled``        → we have not applied our own proportional position
      yet; any position change is layout noise, not a user drag. Ignore.
    - ``position == last_set``→ this is the echo of our own ``set_position``
      (robust to GTK4 deferring ``notify::position`` to a later size-allocate,
      which the old synchronous ``applying`` flag missed). Ignore.
    - degenerate ratio (``<= 0.02`` or ``>= 0.98``) → a transient collapse to a
      sliver, never a deliberate drag. Ignore so we never persist a ~0 ratio.
    """
    if max_position <= 1:
        return None
    if not settled:
        return None
    if position == last_set:
        return None
    ratio = position / max_position
    if ratio <= 0.02 or ratio >= 0.98:
        return None
    return ratio


class ArduisWindow(Adw.ApplicationWindow):
    """Sidebar + nested-GtkPaned canvas: N worktree terminals, decoupled view."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._runner = HostRunner()

        # --- 03.4 multi-project registry (D-01/D-02) -------------------------
        # The window no longer bakes "one arduis = one project" as singletons.
        # A GTK-free ProjectRegistry holds the open projects + the active pointer;
        # the singleton-named accessors below (`_store`, `_project_root`,
        # `_member_repos`, `_compose_path`, `_container_state`, the GTK widget
        # maps) are now @property delegations to `registry.active()`. A per-window
        # BOOTSTRAP Project keeps the app launchable while no project is selected
        # yet (and backs the bare-__new__ conclude test that assigns `_store`
        # directly): the property setters write to the active Project if one is
        # selected, else onto this bootstrap fallback.
        self._registry = ProjectRegistry()
        self._bootstrap = Project(root="")  # fallback target before a project is active
        # The remembered-projects app-state file (D-05): XDG config dir; the GLib
        # lookup lives here (window.py) so projects_store stays gi-free.
        self._projects_json = os.path.join(
            GLib.get_user_config_dir(), "arduis", "projects.json"
        )
        # The persisted pane-layouts app-state file (companion to projects.json):
        # the split tree + per-pane kind/cwd + ratios per workspace, so the grid
        # returns identical after a restart. Loaded once before _open_shell_leaf.
        self._layouts_json = os.path.join(
            GLib.get_user_config_dir(), "arduis", "layouts.json"
        )
        # Spoken-prompt history (voice agent): same app-state dir, same atomic-JSON
        # discipline (voice_store mirrors projects_store; path resolved here so the
        # store stays gi-free).
        self._voice_history_path = os.path.join(
            GLib.get_user_config_dir(), "arduis", "voice_history.json"
        )
        # Debounced structural-change save source (crash-resilience); removed on close.
        self._layout_save_source = None
        # Docker-on-PATH is a MACHINE fact, not per-project — kept a plain field.
        self._docker_available = False
        # workspace_ids with an in-flight compose op (toggle disabled + spinner shown).
        self._compose_busy: set[str] = set()

        # --- Phase 8 (REVIEW-02/GIT-01, D-03): branch+PR status throttle --------
        # The TTL cache (gh payload keyed by workspace_id) + an in-flight debounce set
        # mirroring _compose_busy. Reads are manual-refresh + auto-on-create/activate
        # + TTL + debounce — NEVER a poll (gh is network/rate-limited, T-08-10).
        self._review_cache = ReviewCache()
        self._pr_busy: set[str] = set()
        # Pending enable data (project + port_map) stashed between the async
        # config-step and the up-step, keyed by workspace_id.
        self._compose_pending: dict[str, dict] = {}

        # The $HOME scratch shell is the pinned "main" leaf (D-07), not a session.
        self._shell_pid: int | None = None
        self._last_exit: int | None = None
        # 03.2 pivot: a PROJECT is a root with N member repos; a 1-repo project is
        # the degenerate case. `_project_root`/`_project_name`/`_member_repos`/
        # `_compose_path`/`_container_state` and the alias `_repo_root`/`_repo_name`
        # are now @property delegations onto the active Project (see below);
        # nothing to initialize here — the bootstrap Project holds the defaults.

        # Phase 03.1 pivot (D-04): ONE LayoutModel PER worktree (keyed by worktree
        # sid) instead of one global tree. The canvas shows exactly ONE worktree's
        # terminals at a time; selecting a sidebar row swaps the whole workspace.
        #
        # 03.4 D-08 ("both alive"): the per-project GTK widget maps below
        # (_layouts / _active_workspace_sid / _leaf_by_sid / _term_by_sid and the
        # Phase-4/5 dot/notif/subline/record/calm/activity/badge maps) are
        # PARTITIONED per project — each Project carries its own bundle so
        # switching never destroys the background project's leaves/terminals (they
        # sit unparented but ALIVE). They are now @property delegations onto the
        # active Project's lazily-created map bundle (see `_m`). Nothing to
        # initialize here — the bundle is created on first access per project.
        #
        # sidebar row <-> session_id (the main row maps to the scratch shell).
        # These stay window-global: the sidebar renders ONLY the active project, so
        # they always describe the currently-rendered rows (rebuilt on switch).
        self._sid_by_row: dict[Gtk.ListBoxRow, str] = {}
        self._row_by_sid: dict[str, Gtk.ListBoxRow] = {}
        # the row a right-click context menu currently targets (D-08).
        self._menu_target_sid: str | None = None

        # C-Space prefix state machine (PAR-03/D-09/D-10): armed by Ctrl+Space.
        self._prefix_armed = False
        # ~2s off-loop RAM poll source id (RAM-03); removed on close.
        self._ram_source: int | None = None
        # The aggregate RAM footer label (window-global chrome). The per-row RAM
        # sub-line labels (_subline_by_sid) are PER-PROJECT (D-08) — see `_m`.
        self._footer_label: Gtk.Label | None = None

        # --- Phase 4 attention/status (STATUS-01/02/03, RAM-04) --------------
        # The optional [attention] config (auto-suspend / idle / notify / sound).
        # Read once at startup with stdlib tomllib; safe defaults (every powerful
        # feature OFF) when the file is missing/garbage (D-11).
        self._att_config = attention.load_config(
            os.path.expanduser("~/.config/arduis/arduis.toml")
        )
        # The per-terminal state-file directory (XDG_RUNTIME_DIR, ~/.cache fallback)
        # wiped at startup so stale files from a previous arduis run never lie
        # (Pitfall 5a). clear_status_dir also makes the dir.
        self._status_dir = attention.status_dir()
        attention.clear_status_dir(self._status_dir)
        # The status-dir Gio.FileMonitor; cancelled in _on_close_request
        # (window-global — one watcher covers every project's status files, which
        # are project-namespaced on disk via project_term_id in Workspace 1c).
        self._status_monitor: Gio.FileMonitor | None = None
        # Main-workspace agent splits (workspace=None) have no TerminalRecord; their
        # attention state is tracked window-globally: state-file path → a small
        # info dict {root, tid, dot, leaf, status}. Widget refs survive project
        # switches (leaves are unparented, never destroyed); ``root`` scopes the
        # sidebar main-row highlight to the OWNING project. Keys are
        # project-namespaced state-file paths (_proj_term_id).
        self._main_split_info: dict[str, dict] = {}
        # State-file paths whose terminal CURRENTLY shows a blocking dialog
        # (maintained by the prompt scanner). Window-global — state-file paths are
        # project-namespaced and therefore unique. The degraded-mode activity
        # handler consults it so dialog repaints never clear a live waiting.
        self._dialog_on_screen: set[str] = set()
        # True in degraded mode (consent declined or settings unparseable) — Plan 04
        # surfaces the hint; here it is only the flag + marker logic. Window-global.
        self._degraded = False
        #
        # PER-PROJECT (D-08) maps now live on each Project's lazy bundle (see `_m`):
        #   _record_by_state_file, _dot_by_sid, _pane_dot_by_tid, _notif_by_tid,
        #   _calm_since, _activity_ts, _activity_last_handled, _badge_by_tid,
        #   _subline_by_sid, _leaf_by_sid, _term_by_sid, _layouts,
        #   _active_workspace_sid.
        # They are exposed via @property delegations and are NOT initialized here.

        # --- Phase 5 config region (AGENT-01/UI-01/UI-02) --------------------
        # One shared config path (the file Phase 4 introduced for [attention]).
        # The three new readers + write_theme all use it; load order is BEFORE
        # _install_css so the first paint already knows the active theme.
        self._config_path = os.path.expanduser("~/.config/arduis/arduis.toml")
        self._trusted_setups_path = os.path.expanduser(
            "~/.config/arduis/trusted_setups.toml"
        )
        # AGENT-01 (D-01/D-03): the fed agent command (default "claude"); drives
        # create/split/resume/refeed feeds via agentconfig.*_feed_bytes.
        self._agent_config = agentconfig.load_agent_config(self._config_path)
        # Voice agent: [voice] section (whisper command/model, silence tuning,
        # history cap). Tolerant load — every key optional (voiceconfig defaults).
        self._voice_config = voiceconfig.load_voice_config(self._config_path)
        # UI-01 (D-04/D-05): the configurable prefix tuple + the resolved keymap
        # merged over the defaults through a closed action set. Their USE is wired
        # in _on_key/_run_action (Workspace 2); loaded here so __init__ has one region.
        _keys = _read_keys_section(self._config_path)
        self._prefix = keyconfig.resolve_prefix(_keys.get("prefix"))
        self._keymap = keyconfig.resolve_keymap(_keys.get("bindings"))
        # UI-02 (D-06/D-09): the active theme loaded from [theme] name (Dracula
        # fallback via get_theme). _build_css/_make_terminal/_apply_theme read this.
        self._current_theme = get_theme(appconfig.load_theme_name(self._config_path))
        # The replaceable display CssProvider handle (Pitfall 1) + the display.
        self._css_provider: Gtk.CssProvider | None = None
        self._display = Gdk.Display.get_default()

        # App-bundled symbolic icons (the split-pane glyphs Adwaita lacks) live in
        # data/icons/hicolor/symbolic/actions. Installed builds get them via the
        # hicolor theme in XDG_DATA_DIRS automatically; for a dev run (run.sh) add
        # the repo's data/icons to the theme search path so they resolve too.
        if self._display is not None:
            _repo_icons = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "data", "icons",
            )
            if os.path.isdir(_repo_icons):
                Gtk.IconTheme.get_for_display(self._display).add_search_path(_repo_icons)

        # libadwaita dark base (A3): force dark so Adw widgets render correctly
        # under all 4 dark palettes. Set once here (main.py does not force it).
        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        self._install_css()

        self.set_title("arduis")
        self.set_default_size(960, 620)

        view = Adw.ToolbarView()
        header = Adw.HeaderBar()
        # D-06 (name-only, NO switcher): the topbar shows the PROJECT name once
        # resolution succeeds. Keep a reference so `_resolve_project` can update it.
        self._title_widget = Adw.WindowTitle(title="arduis")
        header.set_title_widget(self._title_widget)

        # Restyle (parallel-code layout): projects live in the sidebar PROJECTS
        # section (see _build_sidebar/_build_project_tabs) — the headerbar keeps
        # only the window title + the primary menu.

        # UI-02 (D-08): a primary menu (open-menu-symbolic) on pack_end with a "Tema"
        # submenu of one win.set_theme(slug) item per registered theme. The action is
        # registered in _install_row_actions (mirrors win.hibernate). Agent command +
        # keybindings stay TOML-edited (no GUI editor this phase).
        theme_menu = Gio.Menu()
        for slug, theme in THEMES.items():
            item = Gio.MenuItem.new(theme.display_name, None)
            item.set_action_and_target_value(
                "win.set_theme", GLib.Variant.new_string(slug)
            )
            theme_menu.append_item(item)
        menu = Gio.Menu()
        menu.append_submenu("Tema", theme_menu)
        menu_btn = Gtk.MenuButton(icon_name="open-menu-symbolic", menu_model=menu)
        menu_btn.set_tooltip_text("Menu")
        header.pack_end(menu_btn)

        # Voice agent (headerbar pair): history popover + mic toggle. The mic is a
        # placeholder until the capture controller lands (step 5) — insensitive so
        # the affordance is visible but inert. The history popover is live already:
        # any persisted spoken prompt can be re-run into a fresh agent pane.
        self._voice_history_list = Gtk.ListBox()
        self._voice_history_list.set_selection_mode(Gtk.SelectionMode.NONE)
        self._voice_history_list.add_css_class("boxed-list")
        _hist_scroll = Gtk.ScrolledWindow()
        _hist_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        _hist_scroll.set_max_content_height(360)
        _hist_scroll.set_propagate_natural_height(True)
        _hist_scroll.set_propagate_natural_width(True)
        _hist_scroll.set_child(self._voice_history_list)
        self._voice_history_popover = Gtk.Popover()
        self._voice_history_popover.set_child(_hist_scroll)
        self._voice_history_popover.connect(
            "show", lambda *_: self._refresh_voice_history()
        )
        self._voice_history_btn = Gtk.MenuButton(
            icon_name="document-open-recent-symbolic",
            popover=self._voice_history_popover,
        )
        self._voice_history_btn.set_tooltip_text("Prompts falados")
        header.pack_end(self._voice_history_btn)

        self._voice_btn = Gtk.ToggleButton()
        self._voice_btn.set_icon_name("audio-input-microphone-symbolic")
        self._voice_btn.set_tooltip_text(
            "Falar um prompt — roda num pane novo (C-Space v)"
        )
        # Programmatic set_active (state sync) must not re-trigger the toggle.
        self._voice_btn_guard = False
        self._voice_btn.connect("toggled", self._on_voice_btn_toggled)
        header.pack_end(self._voice_btn)
        # Capture/transcription controller: created lazily on first use so Gst is
        # only initialized when the mic is actually touched.
        self._voice_controller: VoiceController | None = None

        # NOTE: the old "⌥ Layout" preset menu (grid 2×2 / columns) was a leftover
        # of the pre-pivot GLOBAL-layout model — it arranged worktrees-as-panes. Under
        # the per-worktree workspace model (plan 02) a workspace is one worktree's
        # terminals with a default 2-terminal split, so a global layout preset has no
        # sensible meaning. The dead button is removed (UAT Failure 4).
        view.add_top_bar(header)

        # Outer body: the sidebar+canvas row over a bottom tmux-hint bar.
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        # Row: horizontal split = sidebar (left, fixed-ish) + canvas slot (right).
        body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        body.set_vexpand(True)

        self._sidebar = self._build_sidebar()
        body.append(self._sidebar)

        # Canvas slot: a single-child frame whose child is the reflected pane tree.
        # Styled as the card canvas: near-black background + 12px padding so the
        # rounded cards float with a gap all around (parallel-code look).
        self._canvas_slot = Gtk.Frame()
        self._canvas_slot.add_css_class("arduis-canvas")
        self._canvas_slot.set_hexpand(True)
        self._canvas_slot.set_vexpand(True)
        body.append(self._canvas_slot)

        outer.append(body)

        view.set_content(outer)
        # D-10: wrap the whole ToolbarView in an Adw.ToastOverlay so container
        # progress/result feedback (enable/disable/teardown/reconcile) surfaces as
        # transient toasts over the canvas. The overlay is the window's single
        # content child; `view` becomes its child. `self._toast(msg)` is the entry.
        self._toast_overlay = Adw.ToastOverlay()
        self._toast_overlay.set_child(view)
        self.set_content(self._toast_overlay)

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

        # GTK4 window-close signal (NOT GTK3 "delete-event").
        self.connect("close-request", self._on_close_request)

        # 03.4 (D-05/D-06/D-07): restore the remembered projects, auto-register the
        # launch cwd, select the active project, and rediscover EACH project's workspaces
        # (D-11: disk is the source of truth; workspaces are HIBERNATED and DO NOT spawn —
        # resume relaunches on demand, Pitfall 6). This replaces the single
        # _resolve_project + _scan_workspaces startup pair; it renders the active
        # project's sidebar + project tabs and persists the (possibly newly-added)
        # cwd root. Runs before the attention watcher + the RAM-poll seed.
        self._init_projects()

        # Phase 4 attention infra (STATUS-01): refresh the installed hook script,
        # offer the consent dialog once, and start the status-dir watcher. Runs
        # after the workspace scan (records exist) and before the shell leaf so the
        # monitor is live before any terminal can spawn (D-02/D-05).
        self._setup_attention()
        # Reveal the degraded-mode re-invite hint iff consent was declined/unparseable
        # (the hint button was built hidden before _setup_attention set _degraded).
        self._refresh_degraded_hint()

        # Load the persisted pane layouts once (used by _open_shell_leaf +
        # _resume_workspace to restore grids). Tolerant: missing/corrupt -> empty.
        self._saved_layouts = layout_store.load_layouts(self._layouts_json)

        # Seed the canvas with the main checkout scratch shell as the pinned leaf.
        self._open_shell_leaf()

        # ~2s off-loop RAM poll (RAM-03/D-14): writes live process-group RSS onto
        # each active session and refreshes the row sub-lines + aggregate footer.
        # Removed in _on_close_request so no poll outlives the window.
        self._ram_source = GLib.timeout_add_seconds(2, self._poll_ram)

    # --- active-project accessors (03.4 D-01: singletons → registry.active()) ---
    # Every site that used to read a project singleton now reads the ACTIVE
    # Project through these properties. When no project is selected yet (startup
    # before _init_projects, or the bare-__new__ conclude test) they fall back to
    # the per-window BOOTSTRAP Project, so behavior with exactly one project is
    # unchanged and `main` stays launchable. The setters write onto the active
    # Project if one exists, else the bootstrap — preserving direct assignment
    # (e.g. the conclude test's `win._store = <stub>` and _resolve_project's
    # transitional writes before the registry is seeded in Workspace 2).

    def _active_or_bootstrap(self) -> Project:
        """The active Project, or the bootstrap fallback when none is selected."""
        registry = getattr(self, "_registry", None)
        active = registry.active() if registry is not None else None
        if active is not None:
            return active
        # The bare-__new__ test path may have no _bootstrap; build one lazily.
        boot = getattr(self, "_bootstrap", None)
        if boot is None:
            boot = Project(root="")
            self._bootstrap = boot
        return boot

    @property
    def _store(self) -> SessionStore:
        return self._active_or_bootstrap().store

    @_store.setter
    def _store(self, value: SessionStore) -> None:
        self._active_or_bootstrap().store = value

    @property
    def _project_root(self) -> str | None:
        root = self._active_or_bootstrap().root
        return root or None  # empty bootstrap root → None (no project)

    @_project_root.setter
    def _project_root(self, value: str | None) -> None:
        self._active_or_bootstrap().root = value or ""

    @property
    def _project_name(self) -> str | None:
        return self._project_root and self._active_or_bootstrap().name or None

    @_project_name.setter
    def _project_name(self, _value: str | None) -> None:
        # name is derived from root (basename) — assignment is a no-op kept for the
        # transitional _resolve_project writes; the getter always reflects the root.
        pass

    @property
    def _member_repos(self) -> list[str]:
        return self._active_or_bootstrap().member_repos

    @_member_repos.setter
    def _member_repos(self, value: list[str]) -> None:
        self._active_or_bootstrap().member_repos = list(value)

    @property
    def _compose_path(self) -> str | None:
        return self._active_or_bootstrap().compose_path

    @_compose_path.setter
    def _compose_path(self, value: str | None) -> None:
        self._active_or_bootstrap().compose_path = value

    @property
    def _container_state(self) -> dict:
        return self._active_or_bootstrap().container_state

    @_container_state.setter
    def _container_state(self, value: dict) -> None:
        self._active_or_bootstrap().container_state = value

    # `_repo_root`/`_repo_name` are aliases of the active project root/name used by
    # the pinned-main-leaf code; they delegate to the same active Project.
    @property
    def _repo_root(self) -> str | None:
        return self._project_root

    @_repo_root.setter
    def _repo_root(self, _value: str | None) -> None:
        pass  # alias; the project root is the single source of truth

    @property
    def _repo_name(self) -> str | None:
        return self._project_name

    @_repo_name.setter
    def _repo_name(self, _value: str | None) -> None:
        pass  # alias

    # --- per-project GTK widget map bundle (03.4 D-08 "both alive") ----------
    # The leaf/term/layout + Phase-4/5 status maps are partitioned per project so a
    # background project's terminals stay alive (unparented but never destroyed)
    # while another project is on screen. Each Project gets one lazily-created
    # bundle of plain dicts (holding GTK values window.py created — the dicts keep
    # `project.py` gi-free). `_m()` returns the ACTIVE project's bundle; the named
    # @property accessors below read/write the corresponding entry so every
    # existing call site (`self._leaf_by_sid`, `_reflect_layout`'s unparent loop,
    # …) operates on the active project alone — verbatim, no call-site churn.

    _MAP_NAMES = (
        "leaf_by_sid", "term_by_sid", "layouts", "dot_by_sid", "pane_dot_by_tid",
        "notif_by_tid", "subline_by_sid", "record_by_state_file", "calm_since",
        "activity_ts", "activity_last_handled", "badge_by_tid",
    )

    def _bundle_for(self, proj: Project) -> dict:
        """The project's lazily-created map bundle (dicts + the visible sid scalar)."""
        bundle = getattr(proj, "_gtk_maps", None)
        if bundle is None:
            bundle = {name: {} for name in self._MAP_NAMES}
            bundle["active_workspace_sid"] = None
            proj._gtk_maps = bundle  # plain attr on the dataclass; gi-free dicts
        return bundle

    def _m(self) -> dict:
        """The ACTIVE project's (or bootstrap's) GTK map bundle."""
        return self._bundle_for(self._active_or_bootstrap())

    @property
    def _layouts(self) -> dict:
        return self._m()["layouts"]

    @property
    def _leaf_by_sid(self) -> dict:
        return self._m()["leaf_by_sid"]

    @property
    def _term_by_sid(self) -> dict:
        return self._m()["term_by_sid"]

    @property
    def _dot_by_sid(self) -> dict:
        return self._m()["dot_by_sid"]

    @property
    def _pane_dot_by_tid(self) -> dict:
        return self._m()["pane_dot_by_tid"]

    @property
    def _notif_by_tid(self) -> dict:
        return self._m()["notif_by_tid"]

    @property
    def _subline_by_sid(self) -> dict:
        return self._m()["subline_by_sid"]

    @property
    def _record_by_state_file(self) -> dict:
        return self._m()["record_by_state_file"]

    @property
    def _calm_since(self) -> dict:
        return self._m()["calm_since"]

    @property
    def _activity_ts(self) -> dict:
        return self._m()["activity_ts"]

    @property
    def _activity_last_handled(self) -> dict:
        return self._m()["activity_last_handled"]

    @property
    def _badge_by_tid(self) -> dict:
        return self._m()["badge_by_tid"]

    @property
    def _active_workspace_sid(self) -> str | None:
        return self._m()["active_workspace_sid"]

    @_active_workspace_sid.setter
    def _active_workspace_sid(self, value: str | None) -> None:
        self._m()["active_workspace_sid"] = value

    # --- per-project status-file namespacing (03.4 A3 / Pitfall 1) ----------
    def _proj_term_id(self, term_id: str) -> str:
        """Namespace ``term_id`` with the ACTIVE project's root discriminator (A3).

        ``term_id`` is branch-derived (``feat:t0``) so two projects with a
        same-named workspace would otherwise collide on the GLOBAL attention status-file
        path. Prefixing the active project's ``project_term_id`` discriminator makes
        every status-file path project-unique. CRITICAL CONSISTENCY: this is applied
        at ALL status-file derive sites (the env path the hook writes to, the
        ``_record_by_state_file`` write key, the watcher-tick re-read, and the
        teardown unlink) so the path WRITTEN is identical to the path READ — the
        watcher always matches the record it registered. A status terminal is
        spawned/read/cleared within its OWNING project; at spawn time the owning
        project is the active one (switching never tears down — D-08), so the active
        root is the right and stable discriminator for the write key. The read/clear
        sites that touch BACKGROUND workspaces (260616-buk, finding #6) pass the owning
        root explicitly via :meth:`_proj_term_id_for`. Falls back to the bare
        ``term_id`` only when no project is active (degenerate launch — single
        status namespace, unchanged).
        """
        return self._proj_term_id_for(self._project_root, term_id)

    def _proj_term_id_for(self, root: str | None, term_id: str) -> str:
        """``_proj_term_id`` logic parameterized on an EXPLICIT owning root (260616-buk).

        Multi-project attention surfacing (finding #4) and the teardown clear path
        (finding #6) must derive a BACKGROUND workspace's status-file path with ITS OWN
        project's root, not the active one — otherwise the path read/cleared differs
        from the path the hook writes to (registered at spawn under the owning root).
        Falsy ``root`` → the bare ``term_id`` (degenerate launch, unchanged).
        """
        if not root:
            return term_id
        return project_term_id(root, term_id)

    def _project_for_workspace(self, workspace: "Workspace") -> "Project | None":
        """The registered Project that OWNS ``workspace`` (its store holds it), else None.

        Used by the cross-project attention path (260616-buk): a status event or RAM
        tick for a BACKGROUND workspace must resolve that workspace's owning project so the
        correct bundle (notif dedup store, ``record_by_state_file``) and the correct
        root-namespaced status-file path are used. Identity is ``store.get(workspace_id)``
        being the SAME object (records are kept per-project, keyed by workspace_id).
        """
        registry = getattr(self, "_registry", None)
        if registry is None:
            return None
        for proj in registry.all():
            if proj.store.get(workspace.workspace_id) is workspace:
                return proj
        return None

    # --- CSS provider (UI-SPEC Color) ---------------------------------------

    def _install_css(self) -> None:
        """Load the active theme's colors once per display, KEEPING the handle.

        Builds the CSS from ``self._current_theme`` via ``_build_css`` and stores the
        provider on ``self._css_provider`` so ``_apply_theme`` can remove it before
        adding a replacement (Pitfall 1 — providers must be replaced, not stacked).
        """
        self._css_provider = Gtk.CssProvider()
        self._css_provider.load_from_data(
            _build_css(self._current_theme).encode("utf-8")
        )
        if self._display is not None:
            Gtk.StyleContext.add_provider_for_display(
                self._display,
                self._css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )

    # --- runtime theme switch (UI-02, D-07/D-08, Pitfall 1/2) ---------------

    def _apply_theme(self, theme: Theme) -> None:
        """Switch to ``theme`` at runtime: replace the provider, re-color every VTE.

        Pitfall 1: REMOVE the stored provider from the display before adding a fresh
        one (never stack — providers accumulate at the same priority otherwise).
        Pitfall 2: re-color EVERY live terminal (``_term_by_sid``) and set
        ``self._current_theme`` so new/resumed/split terminals are born in the active
        theme via ``_make_terminal``.
        """
        if self._css_provider is not None and self._display is not None:
            Gtk.StyleContext.remove_provider_for_display(
                self._display, self._css_provider
            )
        self._css_provider = Gtk.CssProvider()
        self._css_provider.load_from_data(_build_css(theme).encode("utf-8"))
        if self._display is not None:
            Gtk.StyleContext.add_provider_for_display(
                self._display,
                self._css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
            )
        # Re-color EVERY live terminal across ALL projects, not just the active
        # bundle (Finding #3): a background project's unparented terminals would
        # otherwise keep the old palette until switch-back. Same bug class as the
        # active-only scoping fixed in _reconcile_orphans (quick workspace 260615-t37).
        for proj in self._registry.all():
            bundle = self._bundle_for(proj)
            for term in bundle["term_by_sid"].values():
                term.set_colors(
                    _rgba(theme.fg),
                    _rgba(theme.bg),
                    [_rgba(c) for c in theme.palette],
                )
                term.set_color_cursor(_rgba(theme.cursor))
        self._current_theme = theme
        # The footer count color is Pango markup (not CSS) — re-render it so the
        # theme switch takes effect immediately, not on the next RAM poll.
        self._update_footer()

    def _on_set_theme(self, _action, param) -> None:
        """win.set_theme(slug): switch the theme + persist the CANONICAL name (D-08/D-09).

        ``get_theme`` re-whitelists the slug to a registered Theme (Dracula fallback),
        so an unknown target falls back safely; persistence writes ``theme.name`` (the
        canonical slug) — an unknown slug that fell back persists "dracula", never the
        raw target (T-05-03). ``write_theme`` is atomic + best-effort (T-05-04).
        """
        theme = get_theme(param.get_string())
        self._apply_theme(theme)
        appconfig.write_theme(self._config_path, theme.name)

    # --- Phase 4 attention startup infra (STATUS-01, D-01/D-02/D-05) --------

    def _setup_attention(self) -> None:
        """Install/refresh the hook, gate consent (D-02), and start the watcher.

        Five branches after refreshing the script copy + reading the user's
        settings:
        1. settings UNPARSEABLE → degraded, no write (never clobber a file we
           cannot parse — T-04-12); start the monitor anyway.
        2. already installed → no dialog (idempotent re-runs are silent — D-02).
        3. script referenced but registration OUTDATED → silent re-merge (consent
           was already given for exactly this script; no second dialog).
        4. declined marker present → degraded; start the monitor anyway (files may
           appear if hooks were installed manually).
        5. otherwise → first-run consent Adw.AlertDialog (pt-BR). The monitor
           starts REGARDLESS, before the async dialog response (so a same-session
           accept is watched immediately).
        """
        if _HAS_NOTIFY:
            Notify.init("arduis")

        home = os.path.expanduser("~")
        target = attention.install_target_path(home)

        # Refresh the installed script every launch so upgrades propagate
        # (Pattern 2). Atomic tmp + os.replace into the install dir; best-effort —
        # a write failure just means the previously-installed copy stays.
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            source = attention.hook_script_source()
            fd, tmp = tempfile.mkstemp(
                dir=os.path.dirname(target), prefix=".arduis-hook-"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(source)
            os.replace(tmp, target)
        except OSError as exc:  # pragma: no cover - filesystem-dependent
            print(f"arduis: could not refresh hook script: {exc}", file=sys.stderr)

        # Read ~/.claude/settings.json: missing → {}; UNPARSEABLE → degraded + never
        # write (T-04-12). Start the monitor in every branch before returning.
        settings_path = os.path.join(home, ".claude", "settings.json")
        settings: dict = {}
        unparseable = False
        if os.path.exists(settings_path):
            try:
                with open(settings_path, encoding="utf-8") as fh:
                    loaded = json.load(fh)
                settings = loaded if isinstance(loaded, dict) else {}
            except (OSError, ValueError) as exc:
                print(
                    f"arduis: ~/.claude/settings.json unreadable, attention "
                    f"hooks NOT installed: {exc}",
                    file=sys.stderr,
                )
                unparseable = True
                self._degraded = True

        if unparseable:
            self._start_status_monitor()
            return

        if attention.is_installed(settings, target):
            self._start_status_monitor()
            return

        if attention.references_script(settings, target):
            # An OUTDATED arduis registration (e.g. the pre-matcher Notification
            # shape): consent was already given for exactly this script, so
            # re-merge silently — no second dialog.
            self._install_hooks(settings, settings_path, target)
            self._start_status_monitor()
            return

        if os.path.exists(attention.declined_marker_path(home)):
            self._degraded = True
            self._start_status_monitor()
            return

        # First run, parseable, not installed, not declined → offer consent.
        self._present_hook_consent(settings, settings_path, target, home)
        self._start_status_monitor()

    def _present_hook_consent(
        self, settings: dict, settings_path: str, target: str, home: str
    ) -> None:
        """First-launch consent dialog (D-02). Install on accept, mark on decline."""
        dialog = Adw.AlertDialog(
            heading="Detectar agentes esperando você",
            body=(
                "arduis instala um hook do Claude Code para detectar quando um "
                "agente espera sua aprovação. Fora do arduis o hook não faz nada."
            ),
        )
        dialog.add_response("later", "Agora não")
        dialog.add_response("install", "Instalar")
        dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("install")
        dialog.set_close_response("later")

        def _on_response(_dlg, response):
            if response == "install":
                self._install_hooks(settings, settings_path, target)
            else:
                # Touch the declined marker → no dialog on future runs (D-02).
                marker = attention.declined_marker_path(home)
                try:
                    os.makedirs(os.path.dirname(marker), exist_ok=True)
                    with open(marker, "a", encoding="utf-8"):
                        os.utime(marker, None)
                except OSError as exc:  # pragma: no cover - filesystem-dependent
                    print(f"arduis: could not write declined marker: {exc}",
                          file=sys.stderr)
                self._degraded = True
                self._refresh_degraded_hint()

        dialog.connect("response", _on_response)
        dialog.present(self)

    def _install_hooks(self, settings: dict, settings_path: str, target: str) -> None:
        """Backup + atomic additive merge into ~/.claude/settings.json (T-04-12).

        Backup copy ONLY when a settings file already exists; missing settings →
        treated as {} and created. The merge is the Plan-02 tested additive builder
        (deepcopy, dedupe-by-path, idempotent). Atomic write (tmp + os.replace in
        the settings dir). Settings I/O is small and startup-only — synchronous
        stdlib I/O is acceptable here.
        """
        try:
            new_settings, changed = attention.merged_settings(settings, target)
            if not changed:
                return  # nothing to write (already present) — silent no-op
            os.makedirs(os.path.dirname(settings_path), exist_ok=True)
            if os.path.exists(settings_path):
                shutil.copyfile(settings_path, settings_path + ".arduis-backup")
            fd, tmp = tempfile.mkstemp(
                dir=os.path.dirname(settings_path), prefix=".arduis-settings-"
            )
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(new_settings, fh, indent=2)
            os.replace(tmp, settings_path)
            # Install succeeded → leave degraded mode and hide the re-invite hint
            # (a re-invite via _show_consent_dialog flips this back on; the next
            # claude relaunch picks up the freshly-installed hooks — primary mode).
            self._degraded = False
            self._refresh_degraded_hint()
        except OSError as exc:  # pragma: no cover - filesystem-dependent
            print(f"arduis: could not install attention hooks: {exc}",
                  file=sys.stderr)
            self._degraded = True
            self._refresh_degraded_hint()

    def _start_status_monitor(self) -> None:
        """Start the Gio.FileMonitor on the status dir (D-05, main loop, no threads)."""
        try:
            self._status_monitor = Gio.File.new_for_path(
                self._status_dir
            ).monitor_directory(Gio.FileMonitorFlags.NONE, None)
            self._status_monitor.connect("changed", self._on_status_event)
        except GLib.Error as exc:  # pragma: no cover - environment-dependent
            print(f"arduis: could not watch status dir: {exc}", file=sys.stderr)
            self._status_monitor = None

    def _on_status_event(self, _monitor, gfile, _other, _event_type) -> None:
        """A status file changed → flip the matching record's status (D-05).

        O(1) dict lookup from the touched path back to (workspace, record); unknown
        files (mkstemp leftovers, foreign files) are ignored (T-04-15).

        260616-buk (finding #4): the watcher is GLOBAL (one status dir for ALL
        projects), so a BACKGROUND project's agent entering WAITING fires here too —
        but its (workspace, record) lives in the OWNING project's bundle, not the active
        one. Search every registered project's ``record_by_state_file`` for the
        touched path so a background project's WAITING agent is surfaced (notify +
        status flip) exactly like the active project's. Falls back to the active
        bundle in the bootstrap/registry-empty case (degenerate launch, unchanged).
        """
        path = gfile.get_path()
        # Main-workspace agent splits map straight to their widgets (no record).
        # getattr guard: partially-constructed windows in unit tests route
        # events without running __init__.
        main_map = getattr(self, "_main_split_info", None)
        if main_map is not None and path in main_map:
            self._apply_main_state_file(path)
            return
        registry = getattr(self, "_registry", None)
        projects = registry.all() if registry is not None else []
        if not projects:
            # Bootstrap / no registered project: keep the original active-bundle path.
            entry = self._record_by_state_file.get(path)
            if entry is None:
                return
            workspace, record = entry
            self._apply_state_file(workspace, record, path)
            return
        for proj in projects:
            bundle = self._bundle_for(proj)
            entry = bundle["record_by_state_file"].get(path)
            if entry is not None:
                workspace, record = entry
                self._apply_state_file(workspace, record, path)
                return

    def _apply_state_file(self, workspace: Workspace, record: TerminalRecord, path: str) -> None:
        """Read one state file → recompute the record's effective status (D-05).

        Reads the (tolerant) parsed doc; computes pid liveness (hook pid first,
        pane pgid fallback — ``_pid_alive``); runs ``attention.effective_status``
        (time + pid based) and writes ``record.status``/``record.status_ts``; then
        refreshes the dots and evaluates the notification gate. A missing/partial
        file (read_state → None) is ignored — readers never crash (T-04-07/T-04-15).
        A scanner-escalated WAITING survives re-reads of a doc that is not NEWER
        than the escalation (``attention.preserve_scan_waiting``) — otherwise the
        ~2s poll tick would stomp the orange back to the file's stale opinion.
        """
        doc = attention.read_state(path)
        if doc is None:
            return
        old = record.status
        pid_alive = self._pid_alive(record, doc)
        new = attention.effective_status(
            doc,
            time.time(),
            pid_alive,
            self._att_config.idle_minutes * 60,
        )
        if attention.preserve_scan_status(
            record.status, record.status_ts, doc.ts, new, pid_alive
        ):
            return
        record.status = new.value
        record.status_ts = doc.ts
        self._refresh_status_ui(workspace)
        self._maybe_notify(workspace, record, old, new.value, doc)

    def _apply_main_state_file(self, path: str) -> None:
        """Flip a MAIN-workspace agent split's widgets from its state file.

        These agents have no TerminalRecord (the main workspace has no store
        Workspace), so liveness comes from the hook-written pid only. The status
        drives the pane dot, the card's attention ring, and — via
        ``_refresh_main_row_attention`` — the pinned main row in the sidebar
        (the user-visible alert while working inside another workspace).
        """
        info = self._main_split_info.get(path)
        if info is None:
            return
        doc = attention.read_state(path)
        if doc is None:
            return
        alive = self._hook_pid_alive(doc)
        if alive is None:
            alive = True  # no pid in the doc — never wrongly retire it
        status = attention.effective_status(
            doc, time.time(), alive, self._att_config.idle_minutes * 60
        )
        # Same guard as _apply_state_file: a scanner-set status (waiting dialog /
        # busy banner) outlives a doc that is not NEWER than the flip. Without it
        # the batched FileMonitor delivery of an OLDER Stop(ready) lands AFTER
        # the scanner's green and paints a static pane blue for good (the race
        # only bites main splits — the record path re-reads on the poll tick).
        if attention.preserve_scan_status(
            info.get("status"), info.get("status_ts"), doc.ts, status, alive
        ):
            return
        info["status"] = status.value
        info["status_ts"] = doc.ts
        dot = info.get("dot")
        if dot is not None:
            self._set_dot_class(dot, self._dot_css_for(status, True))
            dot.set_visible(True)
        leaf = info.get("leaf")
        if leaf is not None:
            if status == AgentStatus.WAITING:
                leaf.add_css_class("attention")
            else:
                leaf.remove_css_class("attention")
            if status == AgentStatus.READY:
                leaf.add_css_class("attention-ready")
            else:
                leaf.remove_css_class("attention-ready")
        self._refresh_main_row_attention()

    def _refresh_main_row_attention(self) -> None:
        """Light the pinned main row iff any ACTIVE-project main split WAITS.

        The main workspace is not a store Workspace, so `_refresh_status_ui` never
        touches its row — aggregate over `_main_split_info` instead, scoped to
        the active project's root (a background project's waiting split must
        not light the visible project's main row).
        """
        infos = getattr(self, "_main_split_info", None)
        if infos is None:
            return
        root = self._project_root
        statuses = {
            info.get("status")
            for info in infos.values()
            if info.get("root") == root
        }
        waiting = "waiting" in statuses
        ready = not waiting and "ready" in statuses
        row = getattr(self, "_row_by_sid", {}).get(_MAIN_SID)
        if row is not None:
            if waiting:
                row.add_css_class("arduis-row-attention")
            else:
                row.remove_css_class("arduis-row-attention")
            if ready:
                row.add_css_class("arduis-row-attention-ready")
            else:
                row.remove_css_class("arduis-row-attention-ready")
        dot = self._dot_by_sid.get(_MAIN_SID)
        if dot is not None:
            if waiting:
                self._set_dot_class(dot, "arduis-dot-waiting")
            elif ready:
                self._set_dot_class(dot, "arduis-dot-ready")
            else:
                self._set_dot_class(dot, "arduis-dot-active")

    # --- instant-waiting accelerator (terminal-text scan, RESEARCH Pattern 5) --
    # Claude Code fires the Notification event only seconds after a dialog
    # renders (~6s permission, 3-4s option-select; no bell, not configurable).
    # The terminal text is the only instant signal: on (debounced)
    # contents-changed, scan the tail for a blocking dialog (approval OR
    # option-select — attention.looks_like_pending_dialog) and ESCALATE-ONLY to
    # waiting — every hook event that follows stays authoritative and
    # overwrites this opinion. The same scan drives the background-busy banner
    # ("Waiting for N background agents to finish"): a turn that ends with
    # background agents still running fires Stop (hook says READY) while work
    # continues — the banner keeps the dot green (attention.next_busy_action).

    # Allowed FROM-sets for the scanner transitions (see _scan_set_status).
    _SCAN_FROM_ANY_BUT_WAITING = (
        None,
        AgentStatus.RUNNING.value,
        AgentStatus.READY.value,
        AgentStatus.IDLE.value,
        AgentStatus.ENDED.value,
    )
    _SCAN_FROM_CALM = (None, AgentStatus.READY.value, AgentStatus.IDLE.value)

    def _terminal_tail_text(self, terminal) -> str:
        """~20 rows ABOVE and BELOW the cursor of ``terminal`` (best-effort).

        Both directions matter: Claude Code's TUI parks the terminal cursor on
        the FOCUSED option row of the select dialog, so the footer key-hint row
        (the option-select marker) sits ~10 rows BELOW the cursor (verified
        empirically 2026-07-02 in a headless VTE — a cursor-terminated window
        never sees it). Rows past the end of content are clamped by VTE.

        Uses ``get_text_range_format`` (VTE 0.72+, within the 0.76 floor) — the
        legacy ``get_text_range``/``get_text`` return empty on this VTE build
        (verified empirically on the system 0.76/0.84 packages).
        """
        try:
            _col, row = terminal.get_cursor_position()
            start = max(0, row - 20)
            res = terminal.get_text_range_format(Vte.Format.TEXT, start, 0, row + 21, 0)
            text = res[0] if isinstance(res, tuple) else res
            return text or ""
        except Exception:  # noqa: BLE001 — scan is best-effort, never crash UI
            return ""

    def _scan_set_status(
        self,
        workspace: Workspace | None,
        term_id: str,
        state_file: str,
        new: str,
        only_from: tuple,
    ):
        """The ONE scanner-driven status mutator (the SECONDARY channel).

        Sets ``new`` iff the terminal's current status is in ``only_from`` and
        differs, then reconciles every widget the hook path reconciles (dot,
        waiting/ready rings, sidebar row). Returns ``(old_status, record)`` when
        a flip happened (``record`` is None for a main split), else None — the
        caller uses it for the notify gate.
        """
        if workspace is not None:
            record = next(
                (t for t in self._all_workspace_terminals(workspace) if t.term_id == term_id),
                None,
            )
            if record is None or record.status not in only_from or record.status == new:
                return None
            old = record.status
            record.status = new
            record.status_ts = time.time()
            self._refresh_status_ui(workspace)
            return old, record
        info = getattr(self, "_main_split_info", {}).get(state_file)
        if info is None or info.get("status") not in only_from or info.get("status") == new:
            return None
        old = info.get("status")
        info["status"] = new
        # Scanner flips stamp NOW (always newer than the doc they outran) so
        # _apply_main_state_file's preserve guard can tell them from hook writes.
        info["status_ts"] = time.time()
        status = next((s for s in AgentStatus if s.value == new), None)
        dot = info.get("dot")
        if dot is not None:
            self._set_dot_class(dot, self._dot_css_for(status, True))
            dot.set_visible(True)
        leaf = info.get("leaf")
        if leaf is not None:
            if status == AgentStatus.WAITING:
                leaf.add_css_class("attention")
            else:
                leaf.remove_css_class("attention")
            if status == AgentStatus.READY:
                leaf.add_css_class("attention-ready")
            else:
                leaf.remove_css_class("attention-ready")
        self._refresh_main_row_attention()
        return old, None

    def _escalate_waiting(self, workspace: Workspace | None, term_id: str, state_file: str) -> None:
        """Flip ``term_id`` to WAITING now (escalate-only; hooks overwrite later).

        Routes through ``_maybe_notify`` with the PRE-flip status: the scanner
        usually beats the hook's Notification event, and without this the later
        hook write would see old == waiting and the D-08 desktop notification
        would never fire.
        """
        flip = self._scan_set_status(
            workspace, term_id, state_file,
            AgentStatus.WAITING.value, self._SCAN_FROM_ANY_BUT_WAITING,
        )
        if flip is not None and workspace is not None:
            old, record = flip
            self._maybe_notify(workspace, record, old, AgentStatus.WAITING.value, None)

    def _current_scan_status(self, workspace: Workspace | None, term_id: str, state_file: str) -> str | None:
        """The terminal's current status string as the scanner sees it."""
        if workspace is not None:
            record = next(
                (t for t in self._all_workspace_terminals(workspace) if t.term_id == term_id),
                None,
            )
            return record.status if record is not None else None
        info = getattr(self, "_main_split_info", {}).get(state_file)
        return info.get("status") if info is not None else None

    def _deescalate_running(self, workspace: Workspace | None, term_id: str, state_file: str) -> None:
        """Flip a WAITING terminal back to RUNNING (dialog answered).

        Symmetric counterpart of ``_escalate_waiting`` — only ever leaves
        ``waiting`` (never touches ready/idle/ended), so the authoritative hook
        events that follow are never fought, just anticipated.
        """
        self._scan_set_status(
            workspace, term_id, state_file,
            AgentStatus.RUNNING.value, (AgentStatus.WAITING.value,),
        )

    def _make_prompt_scan_cb(self, terminal, workspace: Workspace | None, term_id: str, state_file: str):
        """A leading-edge-debounced contents-changed handler scanning for the
        blocking dialog AND the background-busy banner (300ms coalesce — the
        signal fires on every repaint).

        Tracks whether THIS terminal showed the dialog/banner (``saw_dialog`` /
        ``saw_busy``) so the vanish-side transitions (dialog answered → running;
        banner gone with no work spinner → ready) never clear a state the
        scanner did not witness (attention.next_scan_action/next_busy_action).
        """
        pending = [False]
        saw_dialog = [False]
        saw_busy = [False]

        def _scan() -> bool:
            pending[0] = False
            text = self._terminal_tail_text(terminal)
            has_dialog = attention.looks_like_pending_dialog(text)
            if has_dialog:
                self._dialog_on_screen.add(state_file)
            else:
                self._dialog_on_screen.discard(state_file)
            status = self._current_scan_status(workspace, term_id, state_file)
            action = attention.next_scan_action(saw_dialog[0], has_dialog, status)
            if has_dialog:
                saw_dialog[0] = True
            if action == "escalate":
                self._escalate_waiting(workspace, term_id, state_file)
            elif action == "deescalate":
                saw_dialog[0] = False
                self._deescalate_running(workspace, term_id, state_file)

            # Background-busy banner (re-read the status — the dialog action
            # above may have just flipped it).
            has_busy = attention.looks_like_background_busy(text)
            working = attention.looks_like_agent_working(text)
            busy_action = attention.next_busy_action(
                saw_busy[0], has_busy, working,
                self._current_scan_status(workspace, term_id, state_file),
            )
            if has_busy:
                saw_busy[0] = True
            elif working:
                # claude resumed on its own — hooks own the status again.
                saw_busy[0] = False
            if busy_action == "busy":
                self._scan_set_status(
                    workspace, term_id, state_file,
                    AgentStatus.RUNNING.value, self._SCAN_FROM_CALM,
                )
            elif busy_action == "unbusy":
                saw_busy[0] = False
                self._scan_set_status(
                    workspace, term_id, state_file,
                    AgentStatus.READY.value, (AgentStatus.RUNNING.value,),
                )
            return GLib.SOURCE_REMOVE

        def _on_changed(_term) -> None:
            if pending[0]:
                return
            pending[0] = True
            GLib.timeout_add(300, _scan)

        return _on_changed

    def _hook_pid_alive(self, doc) -> bool | None:
        """Liveness of the hook-written pid — claude itself (the hook's parent).

        ``None`` when the doc carries no usable pid (the caller picks a fallback);
        signal 0 sends nothing, EPERM still means "exists".
        """
        pid = getattr(doc, "pid", None)
        if not isinstance(pid, int):
            return None
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except OSError:
            return True  # EPERM etc. — process exists, just not ours to signal

    def _pid_alive(self, record: TerminalRecord, doc) -> bool:
        """Liveness probe for the staleness sweep (Pitfall 5, T-04-17).

        Prefer the HOOK-written pid — that IS claude (the hook's parent). The
        record's pgid is the PANE SHELL's process group: an interactive zsh puts
        claude in its own foreground group, so ``killpg(record.pgid, 0)`` only
        proves the pane is open and would keep a SIGKILL'd claude 'running'/
        'waiting' forever. The pgid is the fallback when the doc has no pid;
        with neither, assume alive (a fresh record — never wrongly retire it).
        """
        alive = self._hook_pid_alive(doc)
        if alive is not None:
            return alive
        if record.pgid is not None:
            try:
                os.killpg(record.pgid, 0)
                return True
            except ProcessLookupError:
                return False
            except OSError:
                return True  # EPERM etc. — process exists, just not ours to signal
        return True

    def _refresh_status_ui(self, workspace: Workspace) -> None:
        """Flip the sidebar aggregate dot + each agent's pane dot in place (D-06/D-07).

        Sidebar row dot = the workspace AGGREGATE over its agent terminals (the
        Plan-02 ``aggregate_workspace``); per-terminal pane dots reflect each agent
        record's own status. Active state gates the row: a hibernated/ended workspace
        keeps the grey dot regardless of any opinion.
        """
        active = workspace.state == SessionState.ACTIVE
        aggregate = attention.aggregate_workspace(self._all_workspace_terminals(workspace))
        row_dot = self._dot_by_sid.get(workspace.workspace_id)
        if row_dot is not None:
            self._set_dot_class(row_dot, self._dot_css_for(aggregate, active))
        # LOUD alert (user feedback 2026-07-01): a waiting OR ready aggregate
        # highlights the whole sidebar row, not just the 8px dot — both mean
        # "the agent waits for YOU" (approval vs end-of-turn). getattr guard:
        # bare unit windows may not build a sidebar.
        row = getattr(self, "_row_by_sid", {}).get(workspace.workspace_id)
        if row is not None:
            waiting = active and aggregate == AgentStatus.WAITING
            ready = active and aggregate == AgentStatus.READY
            if waiting:
                row.add_css_class("arduis-row-attention")
            else:
                row.remove_css_class("arduis-row-attention")
            if ready:
                row.add_css_class("arduis-row-attention-ready")
            else:
                row.remove_css_class("arduis-row-attention-ready")

        # Each agent terminal's own pane-header dot reflects its individual
        # status; a WAITING agent additionally rings its whole card.
        for record in self._all_workspace_terminals(workspace):
            if record.kind != "agent":
                continue
            status = None
            if record.status is not None:
                status = next(
                    (s for s in AgentStatus if s.value == record.status), None
                )
            pane_dot = self._pane_dot_by_tid.get(record.term_id)
            if pane_dot is not None:
                self._set_dot_class(pane_dot, self._dot_css_for(status, active))
            leaf = self._leaf_by_sid.get(record.term_id)
            if leaf is not None:
                if active and status == AgentStatus.WAITING:
                    leaf.add_css_class("attention")
                else:
                    leaf.remove_css_class("attention")
                if active and status == AgentStatus.READY:
                    leaf.add_css_class("attention-ready")
                else:
                    leaf.remove_css_class("attention-ready")

    def _dot_css_for(self, status, active: bool) -> str:
        """Map (status, active) → the dot CSS class (plan_decisions D-06).

        Not active → hibernated grey. Else by status: WAITING orange, RUNNING green
        (reuses active), READY cyan, IDLE muted grey-green, ENDED grey. A None
        status (no opinion yet) keeps the current active-green behavior.
        """
        if not active:
            return "arduis-dot-hibernated"
        if status == AgentStatus.WAITING:
            return "arduis-dot-waiting"
        if status == AgentStatus.RUNNING:
            return "arduis-dot-active"
        if status == AgentStatus.READY:
            return "arduis-dot-ready"
        if status == AgentStatus.IDLE:
            return "arduis-dot-idle"
        if status == AgentStatus.ENDED:
            return "arduis-dot-hibernated"
        return "arduis-dot-active"  # None — opinion-less active workspace

    def _set_dot_class(self, label: Gtk.Label, css_class: str) -> None:
        """Apply exactly one ``arduis-dot-*`` class to ``label`` (remove the rest)."""
        for klass in (
            "arduis-dot-active",
            "arduis-dot-hibernated",
            "arduis-dot-waiting",
            "arduis-dot-ready",
            "arduis-dot-idle",
        ):
            if klass != css_class:
                label.remove_css_class(klass)
        label.add_css_class(css_class)

    def _maybe_notify(self, workspace, record, old, new, doc) -> None:
        """Fire a libnotify notification on a →waiting transition while unfocused (D-08/D-09).

        Gated by the Plan-02 ``should_notify`` (transition INTO waiting, window
        UNFOCUSED, ``ready`` only behind the default-off flag). ONE Notification per
        terminal (D-09): subsequent waitings ``.update`` + ``.show`` the SAME object
        so a TUI burst is replaced server-side, never stacked. The body is the
        state-file message run through ``GLib.markup_escape_text`` (some servers
        parse body markup — T-04-14). ``.show()`` is wrapped so a dead notification
        daemon never crashes the app. Optional sound (D-10) is default-off.
        """
        if not _HAS_NOTIFY:
            return
        if not attention.should_notify(
            old, new, self.props.is_active, self._att_config.notify_ready
        ):
            return

        title = f"{workspace.branch} aguarda você"
        body = GLib.markup_escape_text(
            getattr(doc, "message", "") or "Aprovação pendente"
        )
        icon = "dialog-information"
        # 260616-buk (finding #4): dedup the ONE Notification per terminal (D-09) in
        # the workspace's OWNING bundle, so a BACKGROUND project's WAITING agent reuses its
        # OWN handle (the active bundle's notif store is the wrong one for it). The
        # gating (should_notify) is unchanged — background workspaces notify exactly like
        # active ones (window unfocused → notify).
        proj = self._project_for_workspace(workspace)
        notif_by_tid = (
            self._bundle_for(proj)["notif_by_tid"] if proj is not None
            else self._notif_by_tid
        )
        try:
            notif = notif_by_tid.get(record.term_id)
            if notif is None:
                notif = Notify.Notification.new(title, body, icon)
                notif_by_tid[record.term_id] = notif
            else:
                notif.update(title, body, icon)
            notif.show()
        except Exception as exc:  # noqa: BLE001 - never let a dead daemon crash us
            print(f"arduis: notification failed: {exc}", file=sys.stderr)

        if self._att_config.sound:
            self._play_attention_sound()

    def _play_attention_sound(self) -> None:
        """Optional waiting sound (D-10, default OFF): GSound → beep → silence.

        Try GSound's freedesktop ``message-new-instant`` event; on ANY failure
        (GSound absent on the dev machine) fall back to a beep. ``Gdk.Display.beep``
        may not be exposed as an instance method at the 0.76 floor, so prefer the
        floor-safe ``Gtk.Widget.error_bell``. Never raises.
        """
        try:
            gi.require_version("GSound", "1.0")
            from gi.repository import GSound

            ctx = getattr(self, "_gsound_ctx", None)
            if ctx is None:
                ctx = GSound.Context()
                ctx.init()
                self._gsound_ctx = ctx
            ctx.play_simple({GSound.ATTR_EVENT_ID: "message-new-instant"})
            return
        except Exception:  # noqa: BLE001 - GSound missing/failed → fall back to a beep
            pass
        try:
            self.error_bell()
        except Exception:  # noqa: BLE001 - never raise from the sound path
            pass

    # --- terminal factory (reused verbatim from Phase 2) --------------------

    def _make_terminal(self) -> Vte.Terminal:
        """Build a VTE terminal with the app-owned palette + clipboard shortcuts."""
        terminal = Vte.Terminal()
        # D-06/D-07 (Phase 1): the app owns the palette, never the shell.
        # Phase 5 (UI-02, Pitfall 2): color from the ACTIVE theme so resumed/split/
        # newly-spawned terminals are born in the current theme, not always Dracula.
        theme = self._current_theme
        terminal.set_colors(
            _rgba(theme.fg),
            _rgba(theme.bg),
            [_rgba(c) for c in theme.palette],
        )
        terminal.set_color_cursor(_rgba(theme.cursor))
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
        # Card look: clip children to the CSS border-radius, otherwise the
        # Vte.Terminal paints square corners over the rounded card.
        leaf.set_overflow(Gtk.Overflow.HIDDEN)

        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.add_css_class("arduis-pane-header")

        # Phase 4 (D-07): per-terminal status dot, FIRST in the header (card
        # order: dot · title · badge · spacer · actions). Hidden by default;
        # _spawn_into makes it visible for workspace AGENT terminals only (shells /
        # pinned main never write a state file).
        pane_dot = Gtk.Label(label="●")
        pane_dot.add_css_class("arduis-dot-active")
        pane_dot.set_valign(Gtk.Align.CENTER)
        pane_dot.set_visible(False)
        header.append(pane_dot)
        self._pane_dot_by_tid[sid] = pane_dot

        # T-03-09: render the branch literally via set_text — never set_markup.
        branch = Gtk.Label()
        branch.set_text(branch_label)
        branch.add_css_class("arduis-branch")
        header.append(branch)

        badge = Gtk.Label()
        badge.set_text(badge_label)
        badge.add_css_class("arduis-badge")
        header.append(badge)
        # Keep a handle so degraded mode can flip the label to "esperando?" on a
        # bell and back to "claude" on activity (D-13) without rebuilding the leaf.
        self._badge_by_tid[sid] = badge

        spacer = Gtk.Box()
        spacer.set_hexpand(True)
        header.append(spacer)

        # Two split buttons so BOTH orientations are reachable from the UI
        # (the C-Space -/= chords already do both). Adwaita has no split glyph, so
        # these use app-bundled symbolics that literally draw the result: two rows
        # stacked = top/bottom ("v"); two columns = side-by-side ("h").
        split_v_btn = Gtk.Button(icon_name="arduis-split-v-symbolic")
        split_v_btn.set_tooltip_text("Dividir em cima/embaixo")
        split_v_btn.add_css_class("flat")
        split_v_btn.connect("clicked", self._make_split_pane_cb(sid, "v"))
        header.append(split_v_btn)

        split_h_btn = Gtk.Button(icon_name="arduis-split-h-symbolic")
        split_h_btn.set_tooltip_text("Dividir lado a lado")
        split_h_btn.add_css_class("flat")
        split_h_btn.connect("clicked", self._make_split_pane_cb(sid, "h"))
        header.append(split_h_btn)

        # Expand/focus: the pane grows to fill the whole canvas. Uses the system
        # Adwaita symbolic (diagonal arrows to the corners) — the freedesktop
        # standard for "fullscreen", no extra icon dependency (CLAUDE.md: system libs).
        zoom_btn = Gtk.Button(icon_name="view-fullscreen-symbolic")
        zoom_btn.set_tooltip_text("Expandir painel")
        zoom_btn.add_css_class("flat")
        zoom_btn.connect("clicked", self._make_zoom_pane_cb(sid))
        header.append(zoom_btn)

        close_btn = Gtk.Button(icon_name="window-close-symbolic")
        close_btn.set_tooltip_text("Fechar painel")
        close_btn.add_css_class("flat")
        close_btn.connect("clicked", self._make_close_pane_cb(sid))
        header.append(close_btn)

        leaf.append(header)

        terminal.set_hexpand(True)
        terminal.set_vexpand(True)
        # Focus ring follows REAL keyboard focus: a mouse click on a terminal
        # grabs GTK focus without going through the C-Space keymap, so sync the
        # layout model + CSS ring from the widget's focus-enter event.
        focus_ctrl = Gtk.EventControllerFocus()
        focus_ctrl.connect("enter", self._make_focus_sync_cb(sid))
        terminal.add_controller(focus_ctrl)
        leaf.append(terminal)
        return leaf

    def _make_focus_sync_cb(self, sid: str):
        """Sync model.focused_id + the focus ring when ``sid`` gains GTK focus."""
        def _on_enter(_ctrl) -> None:
            model = self._active_layout()
            if model is None or model.focused_id == sid:
                return
            if not model.is_visible(sid):
                return  # stale event for a leaf outside the active workspace
            model.focused_id = sid
            model.touch(sid)
            self._refresh_focus_ring(sid)
        return _on_enter

    def _make_split_pane_cb(self, sid: str, orientation: str = "v"):
        def _split(_btn) -> None:
            # Split the active workspace, adding a new agent terminal beside this
            # one. ``orientation`` "v" stacks top/bottom (consistent with the default
            # agent-over-shell pair), "h" places side-by-side columns. ``sid`` here
            # is a TERMINAL id in the active tree.
            model = self._active_layout()
            if model is None:
                return
            model.focused_id = sid
            self._split_active_pane(sid, orientation)
        return _split

    def _make_zoom_pane_cb(self, sid: str):
        def _zoom(_btn) -> None:
            # Expand button and C-Space z share _zoom_pane — one place for the toggle logic.
            self._zoom_pane(sid)
        return _zoom

    def _make_close_pane_cb(self, tid: str):
        def _close(_btn) -> None:
            # D-04: closing a pane drops the terminal leaf from the active tree AND
            # tears down its process group + widget maps so the canvas re-reflects
            # cleanly (Failure 2: a stale leaf/empty root used to leave a blank
            # canvas until the sidebar row was clicked to force a rebuild).
            self._close_terminal(tid)
        return _close

    def _close_terminal(self, tid: str) -> None:
        """Close one terminal of the active workspace: kill it, drop it, re-reflect.

        Tears down the terminal's process group (no orphan), removes it from the
        active LayoutModel and the widget/session maps, then re-reflects. If that
        was the workspace's LAST terminal, STAY in the workspace and render the
        recoverable empty state (quick 260702-kzo) — the never-blank-canvas
        guarantee (Failure 2) is now the empty state, not a swap to main.
        """
        sid = self._active_workspace_sid
        if sid is None:
            return
        model = self._workspace_layout(sid)

        # Kill the closed terminal's process group (no orphan) and forget its
        # TerminalRecord so RAM/teardown no longer track it. Under the UX pivot the
        # record lives in workspace.terminals (default pair + splits); a per-repo split
        # could also exist — search both.
        workspace = self._store.get(sid)
        if workspace is not None:
            record = next(
                (t for t in workspace.terminals if t.term_id == tid), None
            )
            if record is not None:
                if record.pid:
                    self._teardown_pgid(record.pid)
                workspace.terminals.remove(record)
            else:
                for repo in workspace.repos:
                    record = next(
                        (t for t in repo.terminals if t.term_id == tid), None
                    )
                    if record is not None:
                        if record.pid:
                            self._teardown_pgid(record.pid)
                        repo.terminals.remove(record)
                        break

        # Drop the terminal from the layout tree + widget maps.
        model.close_leaf(tid)
        self._leaf_by_sid.pop(tid, None)
        self._term_by_sid.pop(tid, None)
        # Main-split attention tracking (no record): forget its info entry and
        # re-aggregate the main row (a closed waiting split must stop alerting).
        stale = [
            p for p, info in self._main_split_info.items() if info.get("tid") == tid
        ]
        for p in stale:
            self._main_split_info.pop(p, None)
            self._dialog_on_screen.discard(p)
        if stale:
            self._refresh_main_row_attention()

        # Empty workspace -> STAY in the workspace and show the recoverable empty
        # state (quick 260702-kzo). The empty state IS the never-blank-canvas
        # guarantee now, so closing the last pane no longer forces a swap to main
        # (which stranded the user on a black main canvas if main was empty too).
        if not model.visible_ids():
            self._reflect_layout()
            self._schedule_layout_save()
            return

        self._reflect_layout()
        # Re-grab the now-focused terminal so typing keeps working after a close.
        term = self._term_by_sid.get(model.focused_id)
        if term is not None:
            term.grab_focus()
        self._schedule_layout_save()
        return

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

        # Build the main workspace's OWN LayoutModel (D-04/D-07). If a saved grid
        # exists, restore it (main:t0 stays the pinned primary shell, spawned below);
        # otherwise seed the single pinned leaf as before.
        model = self._workspace_layout(_MAIN_SID)
        saved = self._saved_layout_for(_MAIN_SID)
        restored = False
        if saved is not None:
            restored = self._restore_layout(
                self._active_or_bootstrap(), _MAIN_SID, saved, primary_tid=main_tid
            )
        if not restored:
            model.root = LeafNode(main_tid)
            model.focused_id = main_tid
            model.touch(main_tid)
            self._active_workspace_sid = _MAIN_SID
            self._reflect_layout()

        # Boot does NOT go through _swap_workspace: both branches above set
        # _active_workspace_sid via _reflect_layout, and the only _rebuild_sidebar
        # so far ran (in _init_projects) while _active_workspace_sid was still None.
        # Sync the highlight now so the pinned main row boots selected (else a stale
        # row stays visually "active" — the sidebar-highlight-wrong-item bug).
        self._sync_sidebar_selection()

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

    # --- layout restore: layouts.json -> live panes -------------------------

    def _saved_layout_for(self, sid: str) -> dict | None:
        """The saved layout dict for the ACTIVE project's workspace ``sid``, or None."""
        proj = self._active_or_bootstrap()
        saved = getattr(self, "_saved_layouts", None) or {}
        return (
            saved.get("projects", {})
            .get(proj.root, {})
            .get("workspaces", {})
            .get(sid)
        )

    def _restore_layout(self, proj, sid: str, saved: dict, primary_tid: str | None = None) -> bool:
        """Rebuild ``sid``'s pane tree from ``saved``; spawn every non-primary leaf.

        Returns False (caller falls back to the default layout) if the tree is
        unusable: not deserializable, missing the primary leaf, or any non-primary
        leaf lacks a descriptor / points at a vanished cwd (D-06 tolerance).
        The primary leaf (``primary_tid``, the pre-built pinned main shell) is left
        for the caller to spawn. Ordering mirrors create/resume: build every
        non-primary leaf widget, reflect (parents them), then spawn (agents resume).
        """
        tree = layout_store.tree_from_dict(saved.get("tree"))
        if tree is None:
            return False
        ids = layout_store.leaf_ids(tree)
        if not ids:
            return False
        if primary_tid is not None and primary_tid not in ids:
            return False
        leaves = saved.get("leaves") or {}
        for tid in ids:
            if tid == primary_tid:
                continue
            desc = leaves.get(tid)
            if not isinstance(desc, dict) or not os.path.isdir(desc.get("cwd", "")):
                return False

        workspace = proj.store.get(sid)
        model = self._bundle_for(proj)["layouts"].setdefault(sid, LayoutModel())
        model.root = tree
        focused = saved.get("focused_id")
        model.focused_id = focused if focused in ids else (primary_tid or ids[0])
        model.touch(model.focused_id)
        self._active_workspace_sid = sid
        pending = []
        for tid in ids:
            if tid == primary_tid:
                continue
            desc = leaves[tid]
            label = workspace.branch if workspace is not None else (self._repo_name or "main")
            terminal = self._make_terminal()
            terminal.connect("child-exited", self._on_worktree_term_exited)
            badge = "zsh" if desc["kind"] == "shell" else "claude"
            leaf = self._make_leaf(tid, label, terminal, badge_label=badge)
            self._leaf_by_sid[tid] = leaf
            self._term_by_sid[tid] = terminal
            if workspace is not None:
                workspace.terminals.append(TerminalRecord(tid, desc["kind"]))
            pending.append((terminal, tid, desc))
        self._reflect_layout()
        # Called by both the boot main-restore and worktree-resume paths, neither of
        # which goes through _swap_workspace — sync the highlight directly rather
        # than relying on a caller's later _rebuild_sidebar() call.
        self._sync_sidebar_selection()
        for terminal, tid, desc in pending:
            self._spawn_into(
                terminal, desc["cwd"], workspace, tid,
                kind=desc["kind"], resume=(desc["kind"] == "agent"),
            )
        return True

    # --- sidebar (PAR-02, D-05/D-06/D-07/D-08) ------------------------------

    @staticmethod
    def _section_title(text: str) -> Gtk.Label:
        """A small all-caps section header label (parallel-code sidebar style)."""
        label = Gtk.Label(xalign=0)
        label.set_text(text)
        label.add_css_class("arduis-section-title")
        label.set_margin_start(16)
        label.set_margin_end(16)
        label.set_margin_top(12)
        label.set_margin_bottom(4)
        return label

    def _build_sidebar(self) -> Gtk.Widget:
        """The left sidebar, sectioned parallel-code style (top to bottom):
        "+ Novo workspace" button, WORKSPACES section title, then the scrollable ListBox of
        the pinned main row + worktree rows.
        """
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.add_css_class("arduis-sidebar")
        box.set_size_request(_SIDEBAR_WIDTH, -1)
        # hexpand PROPAGATES up from descendants in GTK4 (row labels use it for
        # ✕ right-alignment); explicitly pin the sidebar to non-expanding so the
        # canvas takes ALL the extra width (set_hexpand also sets hexpand-set,
        # which stops the child propagation).
        box.set_hexpand(False)

        # PROJECTS section (03.4 D-03 relocated): header row = title + a small
        # "+" opener (same folder-picker handler), then one row per project in
        # a short scrollable ListBox rendered by _build_project_tabs.
        projects_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        title = self._section_title("PROJETOS")
        title.set_hexpand(True)
        projects_header.append(title)
        open_btn = Gtk.Button()
        open_btn.set_icon_name("list-add-symbolic")
        open_btn.add_css_class("flat")
        open_btn.set_tooltip_text("Abrir projeto")
        open_btn.set_margin_end(8)
        open_btn.set_valign(Gtk.Align.CENTER)
        open_btn.connect("clicked", self._on_open_project_clicked)
        projects_header.append(open_btn)
        self._open_project_btn = open_btn  # exposed for smoke introspection
        box.append(projects_header)

        self._projects_box = Gtk.ListBox()
        self._projects_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._projects_box.add_css_class("arduis-projects")
        self._projects_box.set_margin_start(8)
        self._projects_box.set_margin_end(8)
        projects_scroll = Gtk.ScrolledWindow()
        projects_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        projects_scroll.set_propagate_natural_height(True)
        projects_scroll.set_max_content_height(220)
        projects_scroll.set_child(self._projects_box)
        box.append(projects_scroll)

        # The "+ Novo workspace" button (D-02/D-03) — moved from the headerbar into
        # the sidebar (parallel-code layout). Same attribute + handler, so
        # _refresh_project_chrome keeps driving its sensitivity/tooltip.
        self._new_btn = Gtk.Button(label="+ Novo workspace")
        self._new_btn.add_css_class("arduis-new-workspace-btn")
        self._new_btn.set_tooltip_text("Novo workspace")
        self._new_btn.set_sensitive(False)  # enabled once the project resolves
        self._new_btn.connect("clicked", self._on_new_worktree_clicked)
        self._new_btn.set_margin_start(12)
        self._new_btn.set_margin_end(12)
        self._new_btn.set_margin_top(12)
        box.append(self._new_btn)

        box.append(self._section_title("WORKSPACES"))

        self._listbox = Gtk.ListBox()
        self._listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self._listbox.connect("row-activated", self._on_row_activated)
        self._listbox.set_margin_start(8)
        self._listbox.set_margin_end(8)

        workspaces_scroll = Gtk.ScrolledWindow()
        workspaces_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        workspaces_scroll.set_vexpand(True)
        workspaces_scroll.set_child(self._listbox)
        box.append(workspaces_scroll)

        box.append(self._build_sidebar_footer())

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
        # Dots are recreated by _make_row below; drop stale handles first so the
        # post-rebuild status refresh re-binds to the fresh labels (D-06).
        self._dot_by_sid.clear()

        # Pinned project row (D-12): ONE terminal at the project root, not a workspace.
        # Title = the project name; subline = "<project> · zsh".
        main_title = self._project_name or "main"
        self._listbox.append(
            self._make_row(
                _MAIN_SID, main_title, f"{main_title} · zsh", active=True
            )
        )

        # One row per Workspace (a branch across N repos). The row sid is the workspace_id.
        # D-12: an AUTO-suspended workspace is visually distinct — subline "claude ·
        # suspenso" (vs the normal "claude · —" hibernated subline) so the user can
        # tell arduis suspended it for inactivity (not a manual hibernate).
        for workspace in self._store.all():
            active = workspace.state == SessionState.ACTIVE
            if not active and workspace.auto_suspended:
                subline = "claude · suspenso"
            else:
                subline = "claude · —"
            self._listbox.append(
                self._make_row(workspace.workspace_id, workspace.branch, subline, active=active)
            )

        # Rebuilding discards the old selection; restore it to the visible
        # workspace so C-Space n/p/number stay anchored to what's on screen.
        self._sync_sidebar_selection()

        # The dots were just recreated as plain active/hibernated — re-apply each
        # workspace's live aggregate status so dots survive a rebuild (D-06), and the
        # main row's split-aggregate attention state likewise.
        for workspace in self._store.all():
            self._refresh_status_ui(workspace)
        self._refresh_main_row_attention()

    def _sync_sidebar_selection(self) -> None:
        """Highlight the sidebar row for ``_active_workspace_sid`` (the highlight's
        single source of truth).

        The ListBox SINGLE-selection background (``.arduis-sidebar row:selected``)
        IS the "active workspace" highlight. Any path that sets
        ``_active_workspace_sid`` WITHOUT going through ``_swap_workspace`` — the
        boot ``_open_shell_leaf`` and layout restore — must call this, or the
        highlight drifts off the actually-active workspace (boot bug: the pinned
        main row was set active via ``_reflect_layout`` while the only prior
        ``_rebuild_sidebar`` ran with ``_active_workspace_sid`` still None, so the
        row was never selected and a stale row stayed prominent).
        """
        sid = self._active_workspace_sid
        row = self._row_by_sid.get(sid) if sid is not None else None
        if row is not None:
            if self._listbox.get_selected_row() is not row:
                self._listbox.select_row(row)
        else:
            self._listbox.unselect_all()

    def _make_row(self, sid: str, branch: str, subline: str, active: bool) -> Gtk.ListBoxRow:
        """One sidebar row: dot (8px) + branch (13/600) + RAM sub-line (11/400)."""
        row = Gtk.ListBoxRow()
        outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        outer.set_margin_top(8)
        outer.set_margin_bottom(8)
        outer.set_margin_start(8)
        outer.set_margin_end(8)

        dot = Gtk.Label(label="●")
        dot.add_css_class("arduis-dot-active" if active else "arduis-dot-hibernated")
        dot.set_valign(Gtk.Align.CENTER)
        outer.append(dot)
        # Keep a handle so state-file events can flip the workspace-aggregate dot in
        # place (D-06) without rebuilding the row.
        self._dot_by_sid[sid] = dot

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

        # Phase 7 (CONT-04, D-10): while a compose op is in flight show a spinner
        # at the row's TRAILING edge, vertically centered (UX 2026-07-03 — it used
        # to sit under the sub-line, visually floating). The resolved host ports
        # are NOT rendered in the sidebar anymore (same UX pass: the badge line
        # cluttered the row); they still reach the user via the "Containers no
        # ar" toast and the persisted arduis.container.toml.
        if sid != _MAIN_SID and sid in self._compose_busy:
            spinner = Gtk.Spinner()
            spinner.start()
            spinner.set_hexpand(True)
            spinner.set_halign(Gtk.Align.END)
            spinner.set_valign(Gtk.Align.CENTER)
            outer.append(spinner)

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
            # Phase 7 (CONT-01, D-11): the per-workspace isolation toggle is appended
            # ONLY when the feature is available (root compose + docker on PATH).
            # Default OFF; the label flips with the persisted ContainerState. While
            # a compose op is in flight for this workspace the entry is omitted (busy).
            self._append_isolation_menu_item(menu, sid)
            # Phase 8 (D-02/D-03/D-05): Ver diff ▸ / Atualizar status / Abrir PR.
            # Appended for BOTH active and hibernated workspaces — a hibernated workspace
            # still has worktrees on disk (diff) and an on-disk branch/PR (status).
            if session is not None:
                self._append_review_menu_items(menu, session)
            # Phase 8 (REVIEW-03, D-04): the LOAD-BEARING "Concluir workspace" — the safe
            # ordered teardown. Appended for BOTH ACTIVE and HIBERNATED workspaces (a
            # hibernated workspace still has worktrees on disk; an ACTIVE workspace's step (a)
            # kills the live agents first). No target — uses _menu_target_sid.
            if session is not None:
                menu.append("Concluir workspace", "win.conclude")
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

    def _append_review_menu_items(self, menu: Gio.Menu, session: Workspace) -> None:
        """Append the Phase 8 review entries to a workspace's row menu (D-02/D-03/D-05).

        - "Ver diff ▸ <repo>" (REVIEW-01, D-02): a submenu with one item per repo
          for a multi-repo workspace; a single "Ver diff" item for a 1-repo workspace. String
          target = repo_name.
        - "Atualizar status" (D-03): forces a TTL-bypassing status re-read.
        - "Abrir PR (web)" (D-05/REVIEW-02): the ONE allowed write, appended ONLY
          when gh is available.
        """
        repos = session.repos
        if repos:
            if len(repos) > 1:
                diff_menu = Gio.Menu()
                for repo in repos:
                    item = Gio.MenuItem.new(repo.repo_name, None)
                    item.set_action_and_target_value(
                        "win.ver_diff", GLib.Variant.new_string(repo.repo_name)
                    )
                    diff_menu.append_item(item)
                menu.append_submenu("Ver diff", diff_menu)
            else:
                item = Gio.MenuItem.new("Ver diff", None)
                item.set_action_and_target_value(
                    "win.ver_diff", GLib.Variant.new_string(repos[0].repo_name)
                )
                menu.append_item(item)

        # D-03: manual status refresh (forces a re-read, bypasses TTL).
        menu.append("Atualizar status", "win.refresh_status")

        # D-05/REVIEW-02: the ONE allowed write — offered only when gh is present.
        if gh.gh_available():
            menu.append("Abrir PR (web)", "win.open_pr")

    # --- Phase 7: per-workspace container isolation (CONT-01..05) -----------------

    def _isolation_available(self) -> bool:
        """True iff the project has a root compose AND docker is on PATH (CONT-01)."""
        return self._compose_path is not None and self._docker_available

    def _append_isolation_menu_item(self, menu: Gio.Menu, sid: str) -> None:
        """Append the "Isolar/Desligar containers" entry to a workspace's row menu (D-11).

        Gio.Menu has no native checkbox; we mirror the existing label-flip pattern —
        "Isolar containers" when OFF, "Desligar containers" when ON. Omitted entirely
        when the feature is unavailable (no root compose / no docker) or while a
        compose op is in flight for this workspace (busy → an insensitive informational
        line so the user sees WHY it is unavailable rather than a silent gap).
        """
        if not self._isolation_available():
            return
        if sid in self._compose_busy:
            # No way to make a Gio.Menu item insensitive declaratively; surface a
            # disabled-looking informational entry bound to a no-op-ish target.
            menu.append("Containers… (em andamento)", None)
            return
        state = self._container_state.get(sid)
        enabled = bool(state and state.enabled)
        label = "Desligar containers" if enabled else "Isolar containers"
        item = Gio.MenuItem.new(label, None)
        item.set_action_and_target_value(
            "win.toggle_isolation", GLib.Variant.new_string(sid)
        )
        menu.append_item(item)

    def _on_toggle_isolation_action(self, _action, param) -> None:
        """win.toggle_isolation(workspace_id) → dispatch enable vs disable (D-11)."""
        if param is None:
            return
        self._on_toggle_isolation(param.get_string())

    def _on_toggle_isolation(self, workspace_id: str) -> None:
        """Resolve the workspace and flip its isolation based on the persisted state.

        OFF (or no state) → enable; ON → disable. Guards live in the enable/disable
        bodies (feature available, not busy). Implemented fully in Workspace 2.
        """
        if not self._isolation_available():
            return
        workspace = self._store.get(workspace_id)
        if workspace is None:
            return
        state = self._container_state.get(workspace_id)
        if state is not None and state.enabled:
            self._disable_isolation(workspace)
        else:
            self._enable_isolation(workspace)

    def _enable_isolation(self, workspace: Workspace) -> None:
        """Async opt-in chain: config → assign → write override → up → persist.

        CONT-02/03, criterion 2/3 (Pitfall 3/5). Every docker call routes through
        ``docker_service.run_compose_async`` so the GTK loop never blocks on slow
        image pulls. The override is ALWAYS written (even with no published ports →
        an empty-services override) because ``up_argv`` always passes ``-f override``
        (D-05). On a non-zero ``up`` exit we fire ``down`` to clean the partial stack
        (Pitfall 5), leave the toggle OFF, and persist enabled=False. The on_done
        callbacks fire on the GLib main loop → safe to mutate widgets + the store.
        """
        workspace_id = workspace.workspace_id
        if not self._isolation_available():
            return
        if workspace_id in self._compose_busy:
            return
        state = self._container_state.get(workspace_id)
        if state is not None and state.enabled:
            return  # already isolated

        self._compose_busy.add(workspace_id)
        self._rebuild_sidebar()  # spinner shows; toggle entry omitted while busy

        project = compose.sanitize_project_name(workspace.branch)
        offset = containerstate.read_port_offset(self._config_path)
        workspace_dir = workspace.workspace_dir

        def _on_config(rc: int, out: str, err: str) -> None:
            if rc != 0:
                self._finish_isolation_error(workspace, "config falhou", err)
                return
            try:
                model = json.loads(out)
            except (ValueError, TypeError) as exc:  # T-07-11: never crash the loop
                self._finish_isolation_error(workspace, "config inválido", str(exc))
                return
            published = compose.parse_published_ports(model)
            try:
                port_map = compose.assign_ports(published, offset)
            except compose.PortAssignmentError as exc:
                self._finish_isolation_error(workspace, "sem portas livres", str(exc))
                return
            # ALWAYS write an override (D-05): override_bytes({}) emits a minimal
            # empty-services override so the `-f override` path always resolves.
            # CONT-07: fixed-name resources (container_name / network name /
            # volume name) bypass COMPOSE_PROJECT_NAME and collide with the root
            # stack — rename them with the project prefix in the same override.
            try:
                with open(
                    os.path.join(workspace_dir, "docker-compose.yml"),
                    "r", encoding="utf-8",
                ) as fh:
                    base_text = fh.read()
            except OSError:
                base_text = ""
            names = compose.fixed_name_overrides(base_text, project)
            # CONT-08: bind-mounting services run as the HOST user so the
            # artifacts they write into the worktrees (__pycache__, node_modules)
            # stay user-owned and conclude's `git worktree remove` never EACCESes.
            users = compose.user_overrides(model, os.getuid(), os.getgid())
            for svc, extra in users["services"].items():
                names["services"].setdefault(svc, {}).update(extra)
            # CONT-09: a CONT-08 service that also mounts a volume (anonymous
            # node_modules shadow) EACCESes on the fresh root-owned volume —
            # chown it via a one-shot init service gating the app service.
            inits = compose.volume_init_overrides(
                model, users, os.getuid(), os.getgid()
            )
            for svc, extra in inits["services"].items():
                names["services"].setdefault(svc, {}).update(extra)
            names["volumes"].update(inits["volumes"])
            override_path = os.path.join(workspace_dir, "docker-compose.override.yml")
            try:
                self._write_override(
                    override_path, compose.override_bytes(port_map, names)
                )
            except OSError as exc:
                self._finish_isolation_error(workspace, "override falhou", str(exc))
                return
            self._compose_pending[workspace_id] = {
                "project": project,
                "port_map": port_map,
            }

            # CONT-10: clone the root stack's volume DATA into the workspace
            # volumes BEFORE `up` — duplicating the stack duplicates the
            # databases, not just the containers. Best-effort per volume: dest
            # already exists → keep it (re-isolation preserves data); source
            # missing / any step failing → fall back to the empty volume
            # compose would have created anyway. A failed copy removes the
            # half-written dest so postgres never adopts partial data.
            clone_plan = compose.volume_clone_plan(model, project)

            def _start_up() -> None:
                docker_service.run_compose_async(
                    compose.up_argv(project, workspace_dir), _on_up,
                    runner=self._runner,
                )

            def _clone_next(idx: int) -> None:
                if idx >= len(clone_plan):
                    _start_up()
                    return
                item = clone_plan[idx]

                def _after_source(rc: int, _o: str, _e: str) -> None:
                    if rc != 0:  # no root data to clone
                        _clone_next(idx + 1)
                        return
                    docker_service.run_compose_async(
                        compose.volume_create_argv(
                            item["dest"], project, item["key"]
                        ),
                        _after_create, runner=self._runner,
                    )

                def _after_create(rc: int, _o: str, _e: str) -> None:
                    if rc != 0:
                        _clone_next(idx + 1)
                        return
                    docker_service.run_compose_async(
                        compose.volume_clone_argv(item["source"], item["dest"]),
                        _after_clone, runner=self._runner,
                    )

                def _after_clone(rc: int, _o: str, _e: str) -> None:
                    if rc != 0:
                        docker_service.run_compose_async(
                            compose.volume_remove_argv(item["dest"]),
                            lambda *_a: _clone_next(idx + 1),
                            runner=self._runner,
                        )
                        return
                    _clone_next(idx + 1)

                def _after_dest(rc: int, _o: str, _e: str) -> None:
                    if rc == 0:  # dest exists — re-isolation keeps its data
                        _clone_next(idx + 1)
                        return
                    docker_service.run_compose_async(
                        compose.volume_exists_argv(item["source"]),
                        _after_source, runner=self._runner,
                    )

                docker_service.run_compose_async(
                    compose.volume_exists_argv(item["dest"]), _after_dest,
                    runner=self._runner,
                )

            _clone_next(0)

        def _on_up(rc: int, out: str, err: str) -> None:
            pending = self._compose_pending.pop(workspace_id, None)
            port_map = pending["port_map"] if pending else {}
            if rc != 0:
                # Clean the partial stack best-effort (Pitfall 5), then surface.
                docker_service.run_compose_async(
                    compose.down_argv(project, workspace_dir),
                    lambda _rc, _o, _e: None,
                    runner=self._runner,
                )
                self._finish_isolation_error(workspace, "up falhou", err)
                return
            new_state = containerstate.ContainerState(
                project_name=project, enabled=True, ports=port_map
            )
            containerstate.write_container_state(workspace_dir, new_state)
            self._container_state[workspace_id] = new_state
            self._compose_busy.discard(workspace_id)
            self._toast(f"Containers no ar: {self._ports_summary(port_map)}")
            self._rebuild_sidebar()  # badges show

        # CONT-06 (root cause 2026-07-03): fresh worktrees carry no gitignored
        # files, so the env files the base compose points into member repos
        # (env_file: ./backend/app/.env) don't exist yet and `config` exits 1
        # before the chain starts. Materialize them from the root checkout first.
        self._sync_env_files(workspace_dir)

        docker_service.run_compose_async(
            compose.config_argv(workspace_dir), _on_config, runner=self._runner
        )

    def _sync_env_files(self, workspace_dir: str) -> None:
        """Copy root-only ``env_file`` files into the workspace (CONT-06).

        COPY, never symlink — a per-workspace edit must not leak back to the
        root checkout. Best-effort: any failure just falls through to the
        compose call, whose stderr already reaches the user via toast.
        """
        base = os.path.join(workspace_dir, "docker-compose.yml")
        try:
            with open(base, "r", encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return
        root = os.path.dirname(os.path.realpath(base))
        plan = compose.env_copy_plan(root, workspace_dir, compose.env_file_paths(text))
        for src, dst in plan:
            try:
                os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
                shutil.copy2(src, dst)
            except OSError:
                continue

    def _disable_isolation(self, workspace: Workspace) -> None:
        """Async opt-out: ``down --remove-orphans --volumes``, KEEP the port map.

        CONT-04, criterion 3. Flips enabled=False but PRESERVES ``state.ports`` so a
        later re-enable reuses the same stable host ports (badges/URLs unchanged).
        Down failures are surfaced but the state still flips OFF (the user asked to
        stop; a stuck stack should not pin the toggle ON).
        """
        workspace_id = workspace.workspace_id
        if not self._isolation_available():
            return
        if workspace_id in self._compose_busy:
            return

        state = self._container_state.get(workspace_id)
        project = (
            state.project_name
            if state and state.project_name
            else compose.sanitize_project_name(workspace.branch)
        )
        workspace_dir = workspace.workspace_dir

        self._compose_busy.add(workspace_id)
        self._rebuild_sidebar()  # spinner shows

        def _on_down(rc: int, out: str, err: str) -> None:
            cur = self._container_state.get(workspace_id) or containerstate.ContainerState(
                project_name=project
            )
            cur.enabled = False  # KEEP cur.ports (stable re-enable, criterion 3)
            containerstate.write_container_state(workspace_dir, cur)
            self._container_state[workspace_id] = cur
            self._compose_busy.discard(workspace_id)
            if rc == 0:
                self._toast("Containers desligados")
            else:
                self._toast(f"down retornou erro: {err.strip() or rc}")
            self._rebuild_sidebar()  # badges clear (enabled=False)

        docker_service.run_compose_async(
            compose.down_argv(project, workspace_dir), _on_down, runner=self._runner
        )

    def _finish_isolation_error(self, workspace: Workspace, summary: str, detail: str) -> None:
        """Common failure tail: clear busy, persist enabled=False, surface, rebuild.

        Never raises (called from on_done on the GLib loop). The detailed stderr
        goes to a toast; the port map (if any was persisted) is kept for stability.
        """
        workspace_id = workspace.workspace_id
        self._compose_pending.pop(workspace_id, None)
        self._compose_busy.discard(workspace_id)
        cur = self._container_state.get(workspace_id)
        if cur is None:
            cur = containerstate.ContainerState(
                project_name=compose.sanitize_project_name(workspace.branch)
            )
        cur.enabled = False
        try:
            containerstate.write_container_state(workspace.workspace_dir, cur)
        except OSError:
            pass  # best-effort; the in-memory flip below still holds
        self._container_state[workspace_id] = cur
        self._rebuild_sidebar()
        body = (detail or "").strip()
        self._toast(f"Isolamento: {summary}" + (f" — {body}" if body else ""))

    def _write_override(self, path: str, data: bytes) -> None:
        """Atomic-ish write of the generated override (tmp + os.replace).

        The override is regenerated on every enable; a tmp+replace keeps a half-
        written file from ever being read by ``up``.
        """
        directory = os.path.dirname(path) or "."
        fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def _ports_summary(self, port_map: dict) -> str:
        """`<service>:<host>` summary for the success toast (matches the badges)."""
        parts: list[str] = []
        for service, entries in port_map.items():
            for entry in entries:
                host = entry.get("host")
                if host is not None:
                    parts.append(f"{service}:{host}")
        return " ".join(parts) if parts else "sem portas publicadas"

    def _container_down(self, workspace: Workspace) -> None:
        """Async container teardown — a SEPARATE channel from killpg (Pitfall 7, D-12).

        Containers are docker-DAEMON-owned, NOT members of arduis's process group, so
        ``_teardown_session_terminals`` (the killpg path) does nothing for them. This
        runs ``docker compose down --remove-orphans --volumes`` for a workspace whose
        ContainerState is enabled, fire-and-forget on the GLib loop. NEVER call this
        from inside ``_teardown_session_terminals`` — the two channels stay separate
        (T-07-13). Used by the hibernate path (async, non-blocking).
        """
        if not self._isolation_available():
            return
        state = self._container_state.get(workspace.workspace_id)
        if state is None or not state.enabled:
            return
        project = state.project_name or compose.sanitize_project_name(workspace.branch)
        docker_service.run_compose_async(
            compose.down_argv(project, workspace.workspace_dir),
            lambda _rc, _o, _e: None,  # fire-and-forget; orphan-free is the bar
            runner=self._runner,
        )

    def _reconcile_orphans(self) -> None:
        """Startup reconcile: surface orphaned ``arduis-*`` stacks (D-13, criterion 4).

        Conservative — runs ``docker compose ls --all --filter name=arduis`` and
        TOASTS any ``arduis-*`` project with no matching live workspace. Does NOT auto
        ``down -v`` (volume deletion is destructive; a running stack the user wants
        might match). Malformed JSON is swallowed (T-07-11). Only runs when docker
        is on PATH.
        """
        if not self._docker_available:
            return

        def _on_ls(rc: int, out: str, err: str) -> None:
            if rc != 0:
                return
            try:
                projects = json.loads(out)
            except (ValueError, TypeError):
                return  # never crash the loop on garbage ls output
            if not isinstance(projects, list):
                return
            live = {
                compose.sanitize_project_name(t.branch)
                for p in self._registry.all()
                for t in p.store.all()
            }
            orphans = [
                p.get("Name", "")
                for p in projects
                if isinstance(p, dict)
                and p.get("Name", "").startswith("arduis-")
                and p.get("Name", "") not in live
            ]
            if orphans:
                self._toast(
                    f"{len(orphans)} stack(s) órfão(s) encontrado(s): "
                    + ", ".join(orphans)
                )

        docker_service.run_compose_async(
            compose.ls_argv(), _on_ls, runner=self._runner
        )

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
        # Keep the sidebar selection in sync with the visible workspace so the
        # C-Space n/p/number cycle always steps relative to what is on screen
        # (Failure 3: a stale selection made the prefix jumps unpredictable).
        self._sync_sidebar_selection()
        # Focus the swapped-in workspace's focused terminal.
        model = self._workspace_layout(sid)
        term = self._term_by_sid.get(model.focused_id)
        if term is not None:
            term.grab_focus()

    def _on_row_activated(self, _listbox, row: Gtk.ListBoxRow) -> None:
        """Row activation swaps the entire workspace to that worktree (D-04/D-07).

        A HIBERNATED workspace has no layout/terminals — swapping to it would show a
        blank canvas. Activating its row therefore NAVIGATES to a placeholder
        with an explicit "Retomar workspace" button (user decision: browsing the
        sidebar must never spawn agents; only a deliberate resume activates).
        The pinned main row and active workspaces swap directly as before.
        """
        sid = self._sid_by_row.get(row)
        if sid is None:
            return
        workspace = self._store.get(sid)
        if workspace is not None and workspace.state == SessionState.HIBERNATED:
            self._show_hibernated_placeholder(workspace)
            return
        self._swap_workspace(sid)
        # Phase 8 (D-03): auto-read status ONCE on activation of an ACTIVE workspace. The
        # TTL cache makes rapid row-switching a no-op for gh (no spam, no poll).
        if workspace is not None and workspace.state == SessionState.ACTIVE:
            self._refresh_workspace_status(workspace)

    def _show_hibernated_placeholder(self, workspace: Workspace) -> None:
        """Show a HIBERNATED workspace's workspace as a centered explicit-resume card.

        Pure navigation: nothing is spawned and no LayoutModel is created (so
        ``_layouts`` is not polluted with empty models). Detaches the current
        leaves exactly like ``_reflect_layout`` (GTK4 single-parent rule,
        Pitfall 1) before hanging the placeholder.
        """
        self._active_workspace_sid = workspace.workspace_id
        if self._canvas_slot.get_child() is not None:
            self._canvas_slot.set_child(None)
        for leaf in self._leaf_by_sid.values():
            if leaf.get_parent() is not None:
                leaf.unparent()

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        box.set_valign(Gtk.Align.CENTER)
        box.set_halign(Gtk.Align.CENTER)
        label = Gtk.Label(label=f"{workspace.branch} está hibernado")
        label.add_css_class("dim-label")
        button = Gtk.Button(label="Retomar workspace")
        button.add_css_class("suggested-action")
        button.add_css_class("pill")
        button.connect("clicked", lambda *_: self._resume_gated(workspace))
        box.append(label)
        box.append(button)
        self._canvas_slot.set_child(box)

        # Keep the sidebar selection in sync, same as _swap_workspace.
        self._sync_sidebar_selection()

    def _all_workspaces(self) -> list[Workspace]:
        """The UNION of every OPEN project's workspaces (D-09 global cap).

        RAM is a machine-global resource, so the active-agent cap must count agents
        across ALL open projects, not just the active store (RESEARCH Pitfall 4).
        Feed this list to ``caps.at_cap`` / ``caps.active_count`` at every gate so a
        second project can't silently push the live-agent count past the cap.
        """
        return [t for p in self._registry.all() for t in p.store.all()]

    def _resume_gated(self, workspace: Workspace) -> None:
        """Resume ``workspace`` through the active-workspace cap gate (RAM-02/D-14)."""
        if caps.at_cap(self._all_workspaces()):
            self._prompt_hibernate_then(lambda: self._resume_workspace(workspace))
            return
        self._resume_workspace(workspace)

    # --- bottom tmux-hint bar (UI-SPEC Copywriting) -------------------------

    def _build_sidebar_footer(self) -> Gtk.Widget:
        """The sidebar footer: DICAS (tmux hints) + degraded re-invite + the live
        ``N agentes ativos`` footer. Replaces the old full-width bottom hint bar
        (parallel-code puts tips/stats at the sidebar's bottom).
        """
        bar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        bar.add_css_class("arduis-sidebar-footer")

        bar.append(self._section_title("DICAS"))

        # Only advertise keys that the keymap actually dispatches: hjkl move focus
        # between the workspace's terminals; n/p (and a number) switch worktree.
        # ``z`` zoom stays a per-pane button (not in the keymap), so it is not shown
        # here as a C-Space chord (UAT: the hint must match real behavior).
        # Key glyphs use the theme-sourced .arduis-hint-key CSS class (the old bar
        # hardcoded the Dracula _FOCUS_RING hex in Pango markup — a theme-switch bug).
        for key_text, desc in (
            ("C-Space hjkl", "mover painel"),
            ("C-Space n/p", "trocar worktree"),
            ("C-Space 1-9", "ir para"),
        ):
            line = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            line.set_margin_start(16)
            line.set_margin_end(16)
            key_label = Gtk.Label(xalign=0)
            key_label.set_text(key_text)
            key_label.add_css_class("arduis-hint-key")
            line.append(key_label)
            desc_label = Gtk.Label(xalign=0)
            desc_label.set_text(desc)
            desc_label.add_css_class("arduis-row-subline")
            line.append(desc_label)
            bar.append(line)

        # Degraded-mode re-invite (D-02/D-13): a subtle flat button shown ONLY when
        # hooks were declined/unavailable. Clicking re-presents the consent dialog
        # (NOT the full _setup_attention — that would create a duplicate FileMonitor).
        # Built hidden here (this runs before _setup_attention sets _degraded);
        # revealed by _refresh_degraded_hint after setup.
        self._degraded_hint_btn = Gtk.Button(label="status limitado — instalar hooks?")
        self._degraded_hint_btn.add_css_class("flat")
        self._degraded_hint_btn.add_css_class("arduis-degraded-hint")
        self._degraded_hint_btn.set_visible(False)
        self._degraded_hint_btn.connect("clicked", lambda *_: self._show_consent_dialog())
        bar.append(self._degraded_hint_btn)

        # Aggregate footer: "N agentes ativos · <total> RAM" (count in green).
        self._footer_label = Gtk.Label(xalign=0)
        self._footer_label.set_use_markup(True)
        self._footer_label.set_margin_start(16)
        self._footer_label.set_margin_end(16)
        self._footer_label.set_margin_top(6)
        self._footer_label.set_margin_bottom(10)
        self._update_footer()
        bar.append(self._footer_label)
        return bar

    def _refresh_degraded_hint(self) -> None:
        """Show the 'status limitado' re-invite iff degraded (called after setup)."""
        btn = getattr(self, "_degraded_hint_btn", None)
        if btn is not None:
            btn.set_visible(self._degraded)

    def _show_consent_dialog(self) -> None:
        """Re-present ONLY the hook-consent dialog (D-13 re-invite, no monitor dup).

        Recomputes the same paths/settings ``_setup_attention`` uses and calls
        ``_present_hook_consent`` directly — it does NOT re-run ``_setup_attention``
        (which would create a SECOND Gio.FileMonitor on the status dir; the existing
        monitor keeps running). If settings are now unparseable we keep degraded mode
        and do nothing (never clobber a file we cannot parse — T-04-12). On a
        successful install ``_present_hook_consent`` clears degraded indirectly via
        ``_install_hooks``; we refresh the hint visibility after presenting.
        """
        home = os.path.expanduser("~")
        target = attention.install_target_path(home)
        settings_path = os.path.join(home, ".claude", "settings.json")
        settings: dict = {}
        if os.path.exists(settings_path):
            try:
                with open(settings_path, encoding="utf-8") as fh:
                    loaded = json.load(fh)
                settings = loaded if isinstance(loaded, dict) else {}
            except (OSError, ValueError):
                # Still unparseable — stay degraded, never write (T-04-12).
                return
        if attention.is_installed(settings, target):
            # Already installed (e.g. user fixed it manually) — leave degraded mode.
            self._degraded = False
            self._refresh_degraded_hint()
            return
        self._present_hook_consent(settings, settings_path, target, home)

    # --- C-Space prefix state machine (PAR-03/D-09/D-10) --------------------

    def _on_key(self, _ctrl, keyval, _code, state) -> bool:
        """Capture-phase prefix machine: arm on Ctrl+Space, dispatch the next key.

        Returns True ONLY for the prefix keystroke (while disarmed) and for a
        recognized action key (while armed); every other key returns False so the
        focused terminal receives all normal typing (T-03-12 / Pitfall 6).
        """
        name = Gdk.keyval_name(keyval) or ""
        if not self._prefix_armed:
            # UI-01 (D-05): the prefix is the CONFIGURED keyval (default "space")
            # with CONTROL_MASK (the only supported mod, matching keyconfig). The
            # capture-phase controller registration is untouched.
            if (
                name == self._prefix[0]
                and (state & Gdk.ModifierType.CONTROL_MASK)
            ):
                self._prefix_armed = True
                return True  # swallow the prefix; do NOT leak it to the shell
            return False  # normal typing — let the terminal have it (Pitfall 6)

        # Armed: the next key is the action key. Disarm regardless of match.
        self._prefix_armed = False
        # UI-01 (D-05): dispatch via the RESOLVED keymap (user [keys.bindings] merged
        # over the defaults through a closed action set). Keep the digit->jump rule,
        # which is not part of the configurable char map.
        action = self._keymap.get(name)
        if action is None and len(name) == 1 and "1" <= name <= "9":
            action = ("jump", int(name))
        if action is None:
            return False  # stray key after the prefix — don't eat it
        self._run_action(action)
        return True  # recognized action — swallow it

    def _run_action(self, action: tuple) -> None:
        """Map a keymap action tuple to focus/worktree/jump/split/zoom/refeed behavior.

        Phase 5 (UI-01) adds the split/zoom/refeed verbs on top of the Phase-3
        focus/worktree/jump set; all resolve the focused terminal via
        ``_active_layout`` and reuse the existing pane helpers (no duplicated logic).
        """
        kind = action[0]
        if kind == "focus_dir":
            self._focus_neighbor(action[1])
        elif kind == "worktree":
            self._cycle_worktree(action[1])
        elif kind == "jump":
            self._jump_to_row(action[1])
        elif kind == "split":
            model = self._active_layout()
            if model is not None:
                self._split_active_pane(model.focused_id, action[1])
        elif kind == "zoom":
            model = self._active_layout()
            if model is not None:
                self._zoom_pane(model.focused_id)
        elif kind == "refeed":
            self._refeed_focused_agent()
        elif kind == "voice":
            self._toggle_voice()

    def _zoom_pane(self, sid: str) -> None:
        """Toggle zoom on terminal ``sid`` in the active workspace (UI-01).

        Shared by the expand pane-header button and the ``C-Space z`` action so the toggle
        logic lives in ONE place. Zooms ``sid`` if nothing is zoomed, else unzooms.
        """
        model = self._active_layout()
        if model is None:
            return
        if model.is_zoomed():
            model.unzoom()
        else:
            model.zoom(sid)
        self._reflect_layout()

    def _refeed_focused_agent(self) -> None:
        """``C-Space a`` (AGENT-01, D-02/Pitfall 5): type the configured agent into the focused pane.

        Feeds ``agent_feed_bytes(self._agent_config.command)`` into the focused live
        terminal's PTY — it types the command into the durable zsh exactly as if the
        user typed it. NOTHING is killed or respawned. On the pinned main scratch
        shell it still just types the command (harmless).
        """
        model = self._active_layout()
        if model is None:
            return
        term = self._term_by_sid.get(model.focused_id)
        if term is not None:
            term.feed_child(
                agentconfig.agent_feed_bytes(self._agent_config.command)
            )

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
        """Focus a visible terminal in the active workspace: model, ring, grab.

        Focus movement must NOT rebuild the canvas: a full ``_reflect_layout`` here
        tore down and recreated every Gtk.Paned on each h/j/k/l press, resetting the
        split handles (Failure 1's collapse) and re-mapping the VTE widgets — the
        "undescribable" prefix behavior (Failure 3). Instead we update only the
        focus ring in place and grab the target terminal.
        """
        model = self._active_layout()
        if model is None:
            return
        model.focused_id = sid
        model.touch(sid)
        self._refresh_focus_ring(model.focused_id)
        term = self._term_by_sid.get(sid)
        if term is not None:
            term.grab_focus()

    def _refresh_focus_ring(self, focused_id: str | None) -> None:
        """Apply the purple focus ring to exactly one leaf without rebuilding."""
        for tid, leaf in self._leaf_by_sid.items():
            if tid == focused_id:
                leaf.add_css_class("focus")
            else:
                leaf.remove_css_class("focus")

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
        for workspace in self._store.all():
            row = self._row_by_sid.get(workspace.workspace_id)
            if row is not None:
                rows.append(row)
        return rows

    # --- project resolution (D-05/D-06/D-07) --------------------------------

    def _resolve_cwd_project(self) -> tuple[str | None, list[str]]:
        """Resolve the launch cwd → ``(root, member_repos)`` (D-05/D-07). Pure.

        D-05: a project root is a folder whose DIRECT subdirs carry a ``.git``.
        D-07: no walk-up — if the cwd has no member subdirs but is itself a git
        repo, it is the degenerate 1-repo project (preserving 03.1 behavior). The
        ``git rev-parse`` fallback is a short read-only host query — blocking
        briefly at startup is acceptable (CLAUDE.md) — routed through the
        HostRunner seam. Returns ``(None, [])`` when the cwd is not a project.
        Does NOT mutate any state (the seeding is ``_init_projects``'s job).

        ``$HOME`` is never a project: launched from the desktop icon the cwd is
        the home dir, and dotfile setups can make it LOOK like one (hidden
        tooling clones, or home itself being a git repo). Auto-registering it
        creates a phantom project named after the user on every start.
        """
        cwd = os.getcwd()
        if os.path.realpath(cwd) == os.path.realpath(os.path.expanduser("~")):
            return None, []
        members = detect_member_repos(cwd)          # D-05 direct-subdir .git scan
        if members:
            return cwd, members
        # D-07: cwd itself a git repo → degenerate 1-repo project (03.1 behavior)
        argv = self._runner.wrap_argv(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"]
        )
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=5)
            top = proc.stdout.strip() if proc.returncode == 0 else ""
        except (OSError, subprocess.SubprocessError):
            top = ""
        if top:
            # The sole member IS the repo itself; `_member_repo_path` maps it back
            # to `project_root` (not a subdir) in the degenerate case.
            return top, [os.path.basename(top)]
        return None, []

    def _resolve_members(self, root: str) -> list[str]:
        """Member repos of ``root`` WITH the D-07 degenerate fallback.

        ``detect_member_repos`` only finds DIRECT subdirs whose ``.git`` is a dir.
        A root that is ITSELF a git repo (no member subdirs — the degenerate
        1-repo project, e.g. a plain ``~/Projects/foo`` checkout) has no such
        subdir, so report its own basename as the sole member. This mirrors
        ``_resolve_cwd_project`` so a project OPENED via the picker behaves like a
        LAUNCHED one: its New-workspace dialog lists the repo (D-12) and its pinned main
        scratch shell can seed. ``_open_project``/``_init_projects`` route every
        root through here so remembered single-repo projects survive a relaunch.
        """
        members = detect_member_repos(root)
        if members:
            return members
        argv = self._runner.wrap_argv(
            ["git", "-C", root, "rev-parse", "--is-inside-work-tree"]
        )
        try:
            proc = subprocess.run(argv, capture_output=True, text=True, timeout=5)
            inside = proc.returncode == 0 and proc.stdout.strip() == "true"
        except (OSError, subprocess.SubprocessError):
            inside = False
        return [os.path.basename(os.path.normpath(root))] if inside else []

    def _detect_compose_path(self, root: str | None) -> str | None:
        """Root ``docker-compose.yml``/``compose.yaml`` path, or None (CONT-01, D-11)."""
        if not root:
            return None
        for name in ("docker-compose.yml", "compose.yaml"):
            cand = os.path.join(root, name)
            if os.path.isfile(cand):
                return cand
        return None

    def _refresh_project_chrome(self) -> None:
        """Sync the +New button + window title to the ACTIVE project (D-03/D-06)."""
        enabled = self._project_root is not None
        self._new_btn.set_sensitive(enabled)
        self._new_btn.set_tooltip_text("Novo workspace" if enabled else _NO_REPO_HINT)
        if getattr(self, "_title_widget", None) is not None:
            self._title_widget.set_title(self._project_name or "arduis")

    # --- project-tab switcher (03.4 D-03, UI-SPEC) --------------------------

    def _build_project_tabs(self) -> None:
        """Render one row per open project in the sidebar PROJECTS section.

        (Name kept from the 03.4 topbar-chips era — tests monkeypatch it by name.)
        Each project is a ``Gtk.ListBoxRow`` in ``self._projects_box``: status dot +
        name label set via ``set_text`` ONLY (never ``set_markup`` — T-03.4-07
        path-injection guard) + an inline ✕ that triggers the same
        ``_remove_project`` flow as the context menu; the tooltip is the full root
        path. The ACTIVE project's row gets ``.arduis-project-active`` (card fill +
        semibold). Clicking a row switches via ``win.switch_project`` semantics
        (no-op when already active). The list scrolls — no ``+N`` overflow needed.
        The "+" opener next to the PROJETOS title triggers the folder picker.
        """
        projects_box = getattr(self, "_projects_box", None)
        if projects_box is None:
            return  # sidebar not built yet (partial construction in unit tests)

        # Clear the section.
        child = projects_box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            projects_box.remove(child)
            child = nxt

        projects = self._registry.all()
        active = self._registry.active()
        active_root = active.root if active is not None else None

        for proj in projects:
            row = Gtk.ListBoxRow()
            row.add_css_class("arduis-project-row")
            outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            outer.set_margin_top(4)
            outer.set_margin_bottom(4)
            outer.set_margin_start(8)
            outer.set_margin_end(4)

            is_active = proj.root == active_root

            dot = Gtk.Label(label="●")
            # idle (not hibernated) for inactive projects — hibernated grey is
            # near-invisible on the surface; idle reads like pc's muted dots.
            dot.add_css_class(
                "arduis-dot-active" if is_active else "arduis-dot-idle"
            )
            dot.set_valign(Gtk.Align.CENTER)
            outer.append(dot)

            label = Gtk.Label(xalign=0)
            label.set_text(proj.name)  # set_text ONLY (T-03.4-07)
            label.set_hexpand(True)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            outer.append(label)

            # Inline close (parallel-code style) → the SAME remove flow as the
            # context menu (teardown + confirm live in _remove_project).
            close = Gtk.Button(icon_name="window-close-symbolic")
            close.add_css_class("flat")
            close.add_css_class("arduis-row-close")
            close.set_tooltip_text("Remover projeto")
            close.set_valign(Gtk.Align.CENTER)
            close.connect(
                "clicked", lambda _b, root=proj.root: self._remove_project(root)
            )
            outer.append(close)

            row.set_child(outer)
            row.set_tooltip_text(proj.root)
            if is_active:
                row.add_css_class("arduis-project-active")

            # Primary click on the row switches project (ignore clicks that land
            # on the ✕ button — the button consumes them).
            gesture = Gtk.GestureClick()
            gesture.set_button(Gdk.BUTTON_PRIMARY)
            gesture.connect("released", self._make_project_row_cb(proj.root))
            row.add_controller(gesture)

            # D-10: right-click context menu → "Remover projeto" (kept).
            menu_gesture = Gtk.GestureClick()
            menu_gesture.set_button(Gdk.BUTTON_SECONDARY)
            menu_gesture.connect("pressed", self._make_tab_menu_cb(proj.root, row))
            row.add_controller(menu_gesture)

            projects_box.append(row)

    def _make_project_row_cb(self, root: str):
        """A primary-click handler that switches to ``root`` unless already active."""
        def _cb(_gesture, _n_press, _x, _y) -> None:
            active = self._registry.active()
            if active is not None and active.root == root:
                return  # already active — no-op (avoids re-entrant swap)
            self._switch_project(root)
        return _cb

    def _on_open_project_clicked(self, _btn) -> None:
        """"+ Abrir projeto" → a native folder picker (Gtk.FileDialog, 4.10+)."""
        dialog = Gtk.FileDialog()
        dialog.set_title("Abrir projeto")
        dialog.select_folder(self, None, self._on_project_folder_chosen)

    def _on_project_folder_chosen(self, dialog, result) -> None:
        """FileDialog callback: register + switch to the chosen folder (D-03)."""
        try:
            folder = dialog.select_folder_finish(result)
        except GLib.Error:
            return  # user cancelled
        if folder is None:
            return
        root = folder.get_path()
        if root:
            self._open_project(root)

    def _open_project(self, root: str) -> None:
        """Register ``root`` (detect members + compose + scan), persist, switch (D-03).

        Picker validation that the dir is a plausible project root is skipped per
        CONTEXT discretion — a no-git dir registers as a degenerate project (its
        own ``_resolve``/scan simply finds no members/workspaces). Never tears anything
        down (D-08). Idempotent: re-opening an already-open project just switches.
        """
        existing = self._registry.get(root)
        if existing is None:
            proj = ensure_project(self._registry, root, self._resolve_members(root))
            proj.compose_path = self._detect_compose_path(root)
            self._scan_workspaces(project=proj)
            projects_store.save_projects(
                self._projects_json,
                [p.root for p in self._registry.all()],
                root,
            )
        self._switch_project(root)

    def _switch_project(self, root: str) -> None:
        """Make ``root`` the active project: swap sidebar + workspace, NEVER teardown.

        The project switch is the workspace-swap one level up (RESEARCH Pattern 3):
        remember the OUTGOING project's visible workspace into its
        ``last_active_workspace`` (so switch-back restores it), re-point ``set_active``,
        rebuild the sidebar from the NEW active project's store, run the existing
        ``_swap_workspace`` (which re-grabs terminal focus — Pitfall 2), restyle the
        tabs, and persist ``last_active_project``. CRITICAL (D-08): NO teardown — the
        previous project's leaf/term maps stay alive + unparented in its own bundle.
        """
        if self._registry.get(root) is None:
            return
        # Remember the outgoing project's current workspace for switch-back.
        outgoing = self._registry.active()
        if outgoing is not None:
            cur_sid = self._active_workspace_sid
            if cur_sid is not None:
                outgoing.last_active_workspace = cur_sid

        self._registry.set_active(root)
        active = self._registry.active()

        # 03.4 UAT fix: a project shown for the FIRST time (just opened via the
        # picker, or a remembered project never yet selected) has no spawned main
        # scratch shell in its per-project bundle — only __init__ seeds the LAUNCH
        # project. Without this, switching to it shows a blank canvas (the reported
        # "opened a repo, no terminal"). Seed it now so its workspace shows a shell
        # (D-07). `_open_shell_leaf` spawns into the NOW-active project's bundle and
        # reflects _MAIN_SID; the `_swap_workspace` below is then idempotent.
        if active is not None and f"{_MAIN_SID}:t0" not in self._leaf_by_sid:
            self._open_shell_leaf()

        # Render the new active project: chrome + sidebar + workspace.
        self._refresh_project_chrome()
        self._rebuild_sidebar()
        target = (active.last_active_workspace if active is not None else None) or _MAIN_SID
        # If the remembered workspace no longer exists in this project, fall back to
        # the pinned main leaf (always present, D-07).
        if target != _MAIN_SID and active is not None and active.store.get(target) is None:
            target = _MAIN_SID
        self._swap_workspace(target)
        self._build_project_tabs()

        # Persist the new last_active_project.
        projects_store.save_projects(
            self._projects_json,
            [p.root for p in self._registry.all()],
            root,
        )

    def _on_switch_project_action(self, _action, param) -> None:
        """win.switch_project(root) — backs the +N overflow menu items (D-03)."""
        if param is not None:
            self._switch_project(param.get_string())

    # --- project removal + teardown (D-10) ----------------------------------

    def _make_tab_menu_cb(self, root: str, btn: Gtk.Widget):
        """A secondary-click handler popping a 'Remover projeto' menu for ``root``.

        ``btn`` is the popover anchor — a sidebar PROJECTS row since the restyle
        (it was a headerbar chip ToggleButton before).
        """
        def _on_secondary(_gesture, _n_press, x, y) -> None:
            menu = Gio.Menu()
            item = Gio.MenuItem.new("Remover projeto", None)
            item.set_action_and_target_value(
                "win.remove_project", GLib.Variant.new_string(root)
            )
            menu.append_item(item)
            popover = Gtk.PopoverMenu.new_from_model(menu)
            popover.set_parent(btn)
            rect = Gdk.Rectangle()
            rect.x = int(x)
            rect.y = int(y)
            rect.width = 1
            rect.height = 1
            popover.set_pointing_to(rect)
            popover.popup()
        return _on_secondary

    def _on_remove_project_action(self, _action, param) -> None:
        """win.remove_project(root) — backs the tab context-menu item (D-10)."""
        if param is not None:
            self._remove_project(param.get_string())

    def _project_isolation_available(self, proj) -> bool:
        """True iff THIS project has a root compose AND docker is on PATH (CONT-01).

        Per-project variant of ``_isolation_available`` (which reads the ACTIVE
        project). Remove/exit teardown must consult the REMOVED/iterated project's
        OWN ``compose_path`` — never the active project's — so the per-project
        compose identity is correct (D-10/D-11).
        """
        return proj.compose_path is not None and self._docker_available

    def _teardown_project_containers(self, proj) -> None:
        """DETACHED ``compose down -v`` for each enabled workspace of ``proj`` (D-10/D-11).

        Uses THIS project's OWN compose identity (``proj.container_state`` +
        per-workspace ``project_name``/``workspace_dir``) — never the active project's — so two
        projects produce two DISTINCT compose-down argv. argv is built as a LIST via
        ``compose.down_argv`` + ``HostRunner.wrap_argv`` (never a shell string), so a
        crafted project/branch name cannot inject (T-03.4-11).

        Fire-and-forget (2026-07-03; the old brief-sync ``subprocess.run(timeout=10)``
        froze the close ~10s PER workspace — a 14-service stack eats the whole
        timeout). The CLI only *asks* the daemon to tear down; nothing needs to
        wait on it. ``start_new_session`` detaches it from the app's process
        groups (the killpg sweep must not reap it; it must outlive the window)
        and DEVNULL stdio means no pipe to a dead parent → no SIGPIPE mid-down.
        """
        if not self._project_isolation_available(proj):
            return
        for workspace in proj.store.all():
            state = proj.container_state.get(workspace.workspace_id)
            if state is None or not state.enabled:
                continue
            project_name = state.project_name or compose.sanitize_project_name(
                workspace.branch
            )
            argv = self._runner.wrap_argv(
                compose.down_argv(project_name, workspace.workspace_dir)
            )
            try:
                subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError:
                pass  # best-effort; the daemon outlives the app regardless

    def _drop_project(self, root: str) -> None:
        """Drop ``root`` from the registry + projects.json; reselect active if needed.

        NEVER deletes worktrees/workspace dirs on disk (D-10 hard rule). Only mutates the
        in-memory registry + the persisted roots list. If the removed project was the
        active one, pick the first remaining project (or None) and switch to it so the
        sidebar/workspace never points at the dropped project.
        """
        was_active = self._registry.active() is not None and (
            self._registry.active().root == root
        )
        self._registry.remove(root)
        remaining = self._registry.all()
        if was_active:
            new_active = remaining[0].root if remaining else None
            if new_active is not None:
                # _switch_project rebuilds tabs + sidebar + persists last_active.
                self._switch_project(new_active)
                return
            # No project left: clear the active pointer + persist; rebuild chrome.
            self._refresh_project_chrome()
            self._rebuild_sidebar()
        self._build_project_tabs()
        active = self._registry.active()
        projects_store.save_projects(
            self._projects_json,
            [p.root for p in remaining],
            active.root if active is not None else None,
        )

    def _remove_project(self, root: str) -> None:
        """Remove a project from the topbar, tearing down its live workspaces (D-10).

        If the project has NO live (ACTIVE) workspaces: drop silently (no dialog) — there
        is nothing to tear down. If it has live workspaces: present a DESTRUCTIVE
        ``Adw.AlertDialog`` (UI-SPEC copy); on confirm, tear down each live workspace
        (kill agent pgids via ``_teardown_session_terminals`` + clear its state files)
        and ``compose down -v`` for each isolated workspace using THIS project's OWN compose
        identity, THEN drop it from the registry + projects.json. The teardown is kill
        pgids + compose down -v ONLY — arduis NEVER deletes worktrees/workspace dirs on
        disk (D-10 hard rule; no ``git worktree remove`` / ``rm`` anywhere here).
        """
        proj = self._registry.get(root)
        if proj is None:
            return
        live = [t for t in proj.store.all() if t.state == SessionState.ACTIVE]
        if not live:
            # Nothing running — drop without a dialog (UI-SPEC silent path).
            self._drop_project(root)
            return

        dialog = Adw.AlertDialog(
            heading=f"Remover {proj.name} e encerrar seus workspaces?",
            body=(
                "Isto encerra os agentes e containers dos workspaces ativos deste "
                "projeto. As worktrees e pastas no disco são preservadas."
            ),
        )
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("remove", "Remover")
        dialog.set_response_appearance(
            "remove", Adw.ResponseAppearance.DESTRUCTIVE
        )
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def _on_response(_dlg, response):
            if response != "remove":
                return  # cancel — leave the project running, never silent-remove
            # Kill every live workspace's terminal groups (agent + shell + splits) +
            # clear its state files. Containers are a SEPARATE channel (daemon-owned,
            # not in our pgid) — torn down ALONGSIDE via the per-project compose loop.
            for workspace in live:
                self._teardown_session_terminals(workspace)
                self._clear_workspace_state_files(workspace)
            self._teardown_project_containers(proj)
            # NEVER delete worktrees/workspace dirs on disk — drop from list + JSON only.
            self._drop_project(root)

        dialog.connect("response", _on_response)
        dialog.present(self)

    def _resolve_project(self) -> None:
        """Seed the ACTIVE project from the launch cwd (legacy single-project path).

        Retained for any caller that wants the degenerate "cwd is the one project"
        behavior without the full ``projects.json`` machinery. Resolves the cwd,
        ensures it in the registry, selects it active, then syncs chrome. Startup
        uses ``_init_projects`` instead (which also restores remembered projects).
        """
        root, members = self._resolve_cwd_project()
        self._docker_available = shutil.which("docker") is not None
        if root:
            proj = ensure_project(self._registry, root, members)
            proj.compose_path = self._detect_compose_path(root)
            self._registry.set_active(root)
        self._refresh_project_chrome()

    def _init_projects(self) -> None:
        """Seed the registry from projects.json + auto-register the cwd (D-05/D-07).

        The full launch sequence (RESEARCH Pitfall 7 ordering):
          a. ``load_projects`` the remembered roots (+ last_active); missing roots
             are already skipped (D-06).
          b. For EACH remembered root: detect its members, ``ensure_project`` it,
             compute its compose_path, and ``_scan_workspaces(project=...)`` so its workspaces
             are rediscovered into ITS own store (D-02) — a background project is
             fully populated even before it is ever selected.
          c. Resolve the cwd project; if its root is not already registered,
             auto-register it (D-07) so launching inside a project always shows it.
          d. Choose active: ``last`` if still registered, else the cwd root, else
             None (no projects — the truly-empty fallback).
          e. Persist the possibly-newly-added cwd root + the chosen last_active.
        Then drive the initial render through the active project's store.
        """
        self._docker_available = shutil.which("docker") is not None

        # a + b: restore remembered projects (each into its own store).
        roots, last = projects_store.load_projects(self._projects_json)
        for r in roots:
            proj = ensure_project(self._registry, r, self._resolve_members(r))
            proj.compose_path = self._detect_compose_path(r)
            self._scan_workspaces(project=proj)

        # c: auto-register the cwd project (D-07) if absent.
        cwd_root, cwd_members = self._resolve_cwd_project()
        if cwd_root and self._registry.get(cwd_root) is None:
            proj = ensure_project(self._registry, cwd_root, cwd_members)
            proj.compose_path = self._detect_compose_path(cwd_root)
            self._scan_workspaces(project=proj)

        # d: choose the active project (D-07). Launching INSIDE a project always
        # lands you in it — the cwd project wins when it resolved (whether it was
        # just auto-registered or was already remembered). Only when the cwd is NOT
        # a project (launched from a neutral dir) does the remembered last_active
        # take over; otherwise (no projects at all) active stays None.
        registered = {p.root for p in self._registry.all()}
        if cwd_root in registered:
            chosen = cwd_root
        elif last in registered:
            chosen = last
        else:
            chosen = None
        if chosen is not None:
            self._registry.set_active(chosen)

        # e: persist (the cwd root may be newly added; last_active may have moved).
        projects_store.save_projects(
            self._projects_json,
            [p.root for p in self._registry.all()],
            chosen,
        )

        # Initial render: chrome + sidebar + workspace from the active project.
        self._refresh_project_chrome()
        self._rebuild_sidebar()
        # The project-tab switcher is rendered by Workspace 3; tolerate its absence so
        # this workspace alone keeps `main` launchable.
        build_tabs = getattr(self, "_build_project_tabs", None)
        if build_tabs is not None:
            build_tabs()
        # Phase 7 (D-13): conservative startup reconcile of orphaned `arduis-*`
        # compose projects (was the tail of the legacy single-project _scan_workspaces).
        # Async + surface-only; no-op without docker.
        self._reconcile_orphans()

    def _member_repo_path(self, name: str) -> str:
        """Absolute path of member repo ``name`` (D-07 degenerate-case aware).

        In the degenerate 1-repo project the sole member's NAME equals the project
        name but its PATH is the project root itself (there is no
        ``<root>/<name>`` subdir). Otherwise a member maps to ``<root>/<name>``.
        """
        root = self._project_root or ""
        if (
            name == self._project_name
            and len(self._member_repos) == 1
            and not os.path.isdir(os.path.join(root, name))
        ):
            return root
        return os.path.join(root, name)

    # --- startup workspace scan (D-11: disk is the source of truth) ---------------

    def _scan_workspaces(self, project: Project | None = None) -> None:
        """Rediscover past workspaces from ``../<root>-tasks/`` as HIBERNATED (D-11).

        Disk is the source of truth — there is NO persisted app-state file. At
        startup we scan the grouped sibling workspaces root and, for each direct subdir
        that is a VALID workspace (``_dir_is_workspace`` — ≥1 child whose ``.git`` is a FILE,
        a real worktree pointer; A5), build a HIBERNATED ``Workspace`` whose repos are
        inferred from its worktree subdirs. CRITICAL (Pitfall 6): this NEVER spawns
        a terminal — every terminal's pid/pgid stays ``None`` and rows render
        dimmed; ``_on_resume`` (Workspace 1) spawns the default layout on demand.

        03.4 (D-02): when ``project`` is given, scan THAT project's root and write
        into ITS store / container_state (used by ``_init_projects`` to seed each
        remembered project at startup), skipping the active-project-only sidebar
        rebuild + orphan reconcile. When called with no argument the disk-scan logic
        is unchanged — it operates on the ACTIVE project's store and finishes with
        the sidebar rebuild + reconcile (the legacy single-project path).
        """
        if project is not None:
            root = project.root or None
            store = project.store
            container_state = project.container_state
        else:
            root = self._project_root
            store = self._store
            container_state = self._container_state
        if not root:
            return  # no project resolved → nothing to scan

        # The workspaces root is the parent of any workspace_dir: derive it from a throwaway
        # branch so the convention (``<parent>/<base>-tasks``) lives in one place.
        workspaces_root = os.path.dirname(workspace_dir_for(root, "x"))
        if not os.path.isdir(workspaces_root):
            return  # no workspaces ever created → nothing to rediscover

        try:
            entries = sorted(os.scandir(workspaces_root), key=lambda e: e.name)
        except OSError:
            return

        for entry in entries:
            if not entry.is_dir(follow_symlinks=False):
                continue
            if not self._dir_is_workspace(entry.path):
                continue  # stray / symlink-only dir → not a workspace (A5/T-03.2-13)
            workspace_id = entry.name
            repos: list[RepoCheckout] = []
            try:
                children = sorted(os.scandir(entry.path), key=lambda e: e.name)
            except OSError:
                continue
            for child in children:
                if not child.is_dir(follow_symlinks=False):
                    continue
                # A child is a repo worktree iff its `.git` is a FILE (pointer).
                if not os.path.isfile(os.path.join(child.path, ".git")):
                    continue
                # UX pivot: a RepoCheckout is worktree METADATA only — terminals
                # live at workspace level, NOT per repo.
                repos.append(
                    RepoCheckout(
                        repo_name=child.name,
                        worktree_dir=child.path,
                        branch=workspace_id,
                    )
                )
            if not repos:
                continue  # validated but no worktree children → skip
            store.add(
                Workspace(
                    workspace_id=workspace_id,
                    branch=workspace_id,
                    workspace_dir=entry.path,
                    repos=repos,
                    state=SessionState.HIBERNATED,
                    # HIBERNATED: the default workspace-level pair's records exist but
                    # carry NO pid/pgid (Pitfall 6 — do NOT spawn). Resume re-spawns.
                    terminals=default_workspace_terminals(workspace_id),
                )
            )
            # Phase 7 (CONT-04, D-07/D-13): load the durable container state so port
            # badges render at startup for workspaces isolated before this restart. A
            # workspace with no arduis.container.toml yields the no-op default (OFF).
            container_state[workspace_id] = containerstate.load_container_state(
                entry.path
            )

        if project is not None:
            return  # seeding a background project: no active-project UI work here

        # The sidebar was built (from an empty store) before this scan runs, so
        # reflect the rediscovered workspaces now — otherwise they only appear after
        # the next unrelated _rebuild_sidebar (e.g. creating a new workspace).
        self._rebuild_sidebar()

        # Phase 7 (D-13, criterion 4): conservative startup reconcile — surface any
        # orphaned `arduis-*` compose projects with no live workspace (e.g. after a
        # crash). Async + surface-only (never auto down -v). No-op without docker.
        self._reconcile_orphans()

    def _dir_is_workspace(self, path: str) -> bool:
        """True iff ``path`` holds ≥1 real git worktree (a child with a ``.git`` FILE).

        A git worktree stores ``.git`` as a POINTER FILE (``gitdir: ...``), not a
        dir; a symlink-only / plain dir is NOT a worktree. Requiring a real pointer
        file means a stray or symlink-only dir under ``<root>-tasks/`` is never
        listed as a workspace (A5 / T-03.2-13 spoofing mitigation).
        """
        try:
            with os.scandir(path) as it:
                for child in it:
                    if child.is_dir(follow_symlinks=False) and os.path.isfile(
                        os.path.join(child.path, ".git")
                    ):
                        return True
        except OSError:
            return False
        return False

    # --- + New-workspace dialog (D-06) -------------------------------------------

    def _on_new_worktree_clicked(self, _button) -> None:
        """Cap-gate (RAM-02/D-16), then fetch branches + present the dialog (D-06)."""
        if not self._project_root:
            return  # button should be insensitive, but guard anyway

        # RAM-02/D-15/D-16: BLOCK at the active-agent cap and force a hibernate
        # BEFORE any workspace is created/spawned — never silent-allow, never
        # create-hibernated. Proceed only once a workspace is freed.
        if caps.at_cap(self._all_workspaces()):
            self._prompt_hibernate_then(self._begin_new_workspace)
            return
        self._begin_new_workspace()

    def _begin_new_workspace(self) -> None:
        """Fetch local branches from the project's PRIMARY repo, then show dialog.

        The type-or-pick branch list is read from the first member repo's path
        (via ``_member_repo_path``) — in a multi-repo project the primary repo
        seeds the suggestions; per-repo branch resolution still happens per repo
        during creation (D-13).
        """
        if not self._member_repos:
            return
        primary_path = self._member_repo_path(self._member_repos[0])

        def _branches_done(status, out, _err):
            existing = parse_local_branches(out) if status == 0 else []
            self._present_new_workspace_dialog(existing)

        run_git_async(argv_list_local_branches(primary_path), _branches_done, self._runner)

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

        # D-09: the COUNT in the heading is the GLOBAL union across all open
        # projects (RAM is machine-wide). The chooser LIST stays scoped to the
        # ACTIVE project's active workspaces — cross-project hibernation in the chooser
        # is a documented deferral (RESEARCH Open Q2), not a D-09 correctness gap.
        n = caps.active_count(self._all_workspaces())
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

    def _present_new_workspace_dialog(self, existing: list[str]) -> None:
        """New-workspace dialog: branch type-or-pick + a per-member-repo multi-pick (D-06).

        A workspace is one branch across 1+ chosen member repos. The branch
        ``Gtk.ComboBoxText`` is type-or-pick (typing a new name = a new branch).
        Each member repo gets a ``Gtk.CheckButton`` (checked by default). A
        degenerate 1-repo project still renders its single check (no
        ``len == 1`` special-case in the materialization path — criterion 5).
        """
        dialog = Adw.AlertDialog(
            heading="Novo workspace",
            body="Digite o nome de uma nova branch ou escolha uma existente, "
            "e selecione as repos.",
        )

        # Extra child: a vertical box with the branch combo over the repo checks.
        extra = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)

        combo = Gtk.ComboBoxText.new_with_entry()
        for name in existing:
            combo.append_text(name)
        extra.append(combo)

        # 03.4 (D-12): every member repo is checked by default. Chips are gone, so
        # the dialog seeds straight from the active project's member set — all on,
        # still user-overridable per workspace. (Pre-03.3 behavior, restored.)
        default = set(self._member_repos)
        repo_checks: dict[str, Gtk.CheckButton] = {}
        repos_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for repo in self._member_repos:
            check = Gtk.CheckButton(label=repo)
            check.set_active(repo in default)  # all member repos checked (D-12)
            repos_box.append(check)
            repo_checks[repo] = check
        extra.append(repos_box)

        dialog.set_extra_child(extra)
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
            chosen = [name for name, c in repo_checks.items() if c.get_active()]
            if not chosen:
                return  # require at least one repo
            isolate = isolate_check.get_active() if isolate_check is not None else True
            self._create_workspace(branch, chosen, existing, isolate=isolate)

        dialog.connect("response", _on_response)
        dialog.present(self)

    # --- create flow: per-repo chained sequence (D-01/D-02/D-08/D-09/D-13) --

    def _create_workspace(
        self,
        branch: str,
        chosen_repos: list[str],
        existing_in_primary: list[str],
        isolate: bool = True,
    ) -> None:
        """Materialize the workspace folder, kick the per-repo chain, then open the PAIR.

        D-08/D-09: a workspace is one branch across N chosen member repos. We FIRST
        create the workspace folder and materialize the relative symlinks (so relative
        compose build-contexts/bind-mounts resolve before any worktree add —
        Pitfall 4), then run a per-repo CHAINED ``run_git_async`` sequence (RESEARCH
        Pattern 2 — never threads/asyncio). Best-effort: a repo that aborts is
        skipped and surfaced; succeeded repos are kept (D-10/OQ2).

        UX pivot (2026-06-11, supersedes D-01/D-02): the workspace is NOT a column
        per repo. It is the DEFAULT 2-terminal pair (agent over shell) rooted at the
        workspace folder, built+spawned ONCE in ``_finalize_workspace_creation`` after the
        chain finishes with ≥1 success — terminals must NOT spawn before the workspace
        folder + worktrees are materialized.
        """
        root = self._project_root
        if not root:
            return
        workspace_dir = workspace_dir_for(root, branch)
        os.makedirs(workspace_dir, exist_ok=True)

        # Materialize the mirror symlinks FIRST (D-09, before worktree add so
        # relative build contexts resolve — Pitfall 4). Best-effort: collect
        # failures and surface them at the end; one bad symlink never aborts the
        # whole workspace (D-10/OQ2). Targets are RELATIVE (relocatable, T-03.2-05).
        symlink_errors: list[str] = []
        for src, dst in symlink_plan(root, workspace_dir, set(chosen_repos)):
            if os.path.lexists(dst):
                continue
            try:
                os.symlink(os.path.relpath(src, workspace_dir), dst)
            except OSError as exc:
                symlink_errors.append(f"{os.path.basename(dst)}: {exc}")

        # Register the Workspace NOW (so the sidebar row appears); repos get appended as
        # each succeeds (best-effort partial creation, OQ2). Its DEFAULT workspace is
        # the workspace-level 2-terminal pair (agent+shell), built+spawned once the chain
        # finishes — NOT before the folder is materialized (UX pivot).
        workspace = Workspace(
            workspace_id=branch,
            branch=branch,
            workspace_dir=workspace_dir,
            repos=[],
            terminals=default_workspace_terminals(branch),
        )
        self._store.add(workspace)
        self._rebuild_sidebar()  # show the row immediately; workspace opens on finalize

        # Per-repo errors accumulate across the chain; surfaced once at the end.
        repo_errors: list[str] = list(symlink_errors)

        # Kick the per-repo chain (one repo at a time, fully async — Pattern 2).
        self._add_repo(workspace, chosen_repos, 0, branch, repo_errors, isolate)

    def _build_workspace_terminals(self, workspace: Workspace, repos: list[str]) -> LayoutModel:
        """Build the DEFAULT 2-terminal workspace for ``workspace`` (UX pivot 2026-06-11).

        SUPERSEDES the one-column-per-repo 2×N layout of D-01/D-02 (a real 6-repo
        project produced an unusable 2×6 grid of tiny panes). Shared by
        ``_create_workspace`` and ``_resume_workspace``: build a fresh ``LayoutModel`` with
        EXACTLY TWO workspace-level leaves — agent ``{workspace}:t0`` over shell ``{workspace}:t1``
        (vertical split, the 03.1 default) — regardless of how many repos the workspace
        spans. Both terminals open at ``workspace.workspace_dir`` (the workspace folder mirrors the
        project root) so one agent works across all the workspace's repos; the user grows
        the workspace via the split machinery (no auto per-repo columns). ``repos``
        is accepted for signature compatibility but no longer drives the layout.
        The caller spawns the terminals afterwards.
        """
        branch = workspace.branch
        agent_tid = f"{workspace.workspace_id}:t0"
        shell_tid = f"{workspace.workspace_id}:t1"

        model = LayoutModel()
        model.root = LeafNode(agent_tid)
        model.focused_id = agent_tid
        model.touch(agent_tid)
        # Shell below the agent (vertical split) — the 03.1 default pair.
        model.split(agent_tid, shell_tid, "v")
        model.focused_id = agent_tid
        model.touch(agent_tid)

        # Build both VTE leaves (badge "claude" agent / "zsh" shell).
        self._make_workspace_leaf(agent_tid, branch, "claude")
        self._make_workspace_leaf(shell_tid, branch, "zsh")

        self._layouts[workspace.workspace_id] = model
        self._active_workspace_sid = workspace.workspace_id
        self._reflect_layout()
        # This helper (shared by _create_workspace's finalize and _resume_workspace)
        # switches the canvas WITHOUT going through _swap_workspace — sync the
        # highlight here directly rather than relying on the caller's later
        # _rebuild_sidebar() call (a caller that skips/reorders that call would
        # silently reintroduce the sidebar-highlight-wrong-item bug).
        self._sync_sidebar_selection()
        return model

    def _make_workspace_leaf(self, tid: str, branch: str, badge: str) -> None:
        """Build + register one workspace terminal's VTE leaf (palette factory, T-04)."""
        terminal = self._make_terminal()
        terminal.connect("child-exited", self._on_worktree_term_exited)
        leaf = self._make_leaf(tid, branch, terminal, badge_label=badge)
        self._leaf_by_sid[tid] = leaf
        self._term_by_sid[tid] = terminal

    def _add_repo(
        self,
        workspace: Workspace,
        repos: list[str],
        i: int,
        branch: str,
        repo_errors: list[str],
        isolate: bool = True,
    ) -> None:
        """Resolve + add ONE repo's worktree, then advance to repo ``i+1`` (D-13).

        Per-repo chained async (RESEARCH Pattern 2): born-HEAD guard → porcelain
        pre-check → branch list → base detection → ``resolve_repo_add`` → ``git
        worktree add``. Each repo resolves INDEPENDENTLY (best-effort, OQ2); an
        ``("abort", reason)`` (branch checked out elsewhere — NEVER ``--force``,
        D-13) is collected and the chain advances. After the last repo any
        accumulated per-repo errors are surfaced once (D-10).
        """
        if i >= len(repos):
            # Chain done — finalize. Succeeded repos are exactly those appended to
            # workspace.repos in _add_done; everything else aborted/failed. A failed repo
            # must NOT leave a dead empty column (zombie pane) in the workspace, and
            # a workspace where EVERY repo failed must NOT linger as a sidebar row that
            # counts toward the cap. Prune accordingly (NEVER deletes from disk —
            # D-10; the symlink-only folder may remain, startup scan rejects it).
            self._finalize_workspace_creation(workspace, repos, repo_errors, isolate)
            return

        name = repos[i]
        repo_path = self._member_repo_path(name)
        wt_dir = repo_worktree_dir(workspace.workspace_dir, name)

        def _advance() -> None:
            self._add_repo(workspace, repos, i + 1, branch, repo_errors, isolate)

        def _has_commit_done(hstatus, _hout, _herr):
            if hstatus != 0:
                # Unborn HEAD: this repo cannot host a worktree — skip it.
                repo_errors.append(
                    f"{name}: o repositório ainda não tem commits."
                )
                _advance()
                return
            run_git_async(
                argv_worktree_list_porcelain(repo_path), _porcelain_done, self._runner
            )

        def _porcelain_done(status, out, _err):
            parsed = parse_worktrees(out) if status == 0 else []

            def _branches_done(bstatus, bout, _berr):
                existing = parse_local_branches(bout) if bstatus == 0 else []

                def _resolve_with_base(base: str) -> None:
                    kind, payload = resolve_repo_add(
                        repo_path, branch, existing, parsed, base, wt_dir
                    )
                    if kind == "abort":
                        repo_errors.append(f"{name}: {payload}")
                        _advance()
                        return

                    def _add_done(astatus, _aout, aerr):
                        if astatus != 0:
                            repo_errors.append(f"{name}: {aerr}")
                            _advance()
                            return
                        # UX pivot: a RepoCheckout is now worktree METADATA only —
                        # the workspace's terminals live at workspace level (built once in
                        # finalize), so no per-repo terminal list / spawn here.
                        workspace.repos.append(
                            RepoCheckout(
                                repo_name=name,
                                worktree_dir=wt_dir,
                                branch=branch,
                            )
                        )
                        _advance()

                    run_git_async(payload, _add_done, self._runner)

                # Base detection (origin/HEAD → local HEAD fallback) only matters
                # for the "new" case, but resolve_repo_add ignores it otherwise.
                def _origin_done(ostatus, oout, _oerr):
                    if ostatus == 0 and oout.strip():
                        _resolve_with_base(parse_default_branch(oout))
                        return

                    def _local_done(lstatus, lout, _lerr):
                        _resolve_with_base(lout.strip() if lstatus == 0 else "HEAD")

                    run_git_async(
                        argv_default_branch_local(repo_path), _local_done, self._runner
                    )

                run_git_async(
                    argv_default_branch_via_origin(repo_path), _origin_done, self._runner
                )

            run_git_async(
                argv_list_local_branches(repo_path), _branches_done, self._runner
            )

        run_git_async(argv_repo_has_commit(repo_path), _has_commit_done, self._runner)

    def _finalize_workspace_creation(
        self,
        workspace: Workspace,
        chosen_repos: list[str],
        repo_errors: list[str],
        isolate: bool = True,
    ) -> None:
        """Finalize the create chain: drop zombie workspaces, else open the workspace PAIR.

        UX pivot (2026-06-11): there are no per-repo columns to prune anymore — the
        workspace is the single workspace-level 2-terminal pair, built+spawned HERE (once
        the workspace folder + worktrees are materialized). Partial failure just means
        fewer worktrees in the workspace folder; the 2-terminal workspace opens
        regardless. If ZERO repos succeeded the whole workspace is a zombie (symlink-only
        folder, no worktree): remove it from the store so it never appears in the
        sidebar or counts toward the active cap. NEVER deletes from disk (D-10).
        """
        succeeded = {r.repo_name for r in workspace.repos}

        if not succeeded:
            # Zero repos created — tear the workspace down completely (no zombie row).
            self._store.remove(workspace.workspace_id)
            self._layouts.pop(workspace.workspace_id, None)
            if self._active_workspace_sid == workspace.workspace_id:
                self._swap_workspace(_MAIN_SID)
            self._rebuild_sidebar()
            if repo_errors:
                self._show_error("Não foi possível criar o workspace", "\n".join(repo_errors))
            return

        # ≥1 repo succeeded → open the DEFAULT 2-terminal workspace at the workspace
        # folder root and spawn the agent+shell pair (now that the worktrees exist).
        self._build_workspace_terminals(workspace, list(succeeded))
        self._spawn_workspace_terminals(workspace)

        # Phase 7 (CONT-04): seed the in-memory container state for the fresh workspace
        # (no file yet → ContainerState() default, toggle OFF).
        self._container_state[workspace.workspace_id] = containerstate.load_container_state(
            workspace.workspace_dir
        )

        # Pivot 2026-07-03 (supersedes CONT-04's "never auto-enable"): creating a
        # workspace in a project with a root compose + docker brings its isolated
        # stack up — gated by the dialog's "Isolar containers" check (default ON;
        # ``isolate`` threads the choice through the create chain), same
        # availability gate as the menu item, and AFTER the terminals spawn so
        # the agent pair never waits on a slow image pull. _enable_isolation
        # keeps its own guards (busy / already enabled) and its failure path
        # only toasts + persists enabled=False — creation never breaks.
        if isolate and self._isolation_available():
            self._enable_isolation(workspace)

        # ENV-02 / criterion 4: run each succeeded repo's trusted [setup] in its shell
        # pane. CREATE path ONLY — _resume_workspace never reaches here (Pitfall 3). Failure
        # never blocks the agent or crashes creation (D-06).
        self._run_repo_setups(workspace)

        if repo_errors:
            self._show_error("Algumas repos não foram criadas", "\n".join(repo_errors))
        self._rebuild_sidebar()

        # Phase 8 (D-03): auto-read branch+PR status ONCE on create (after the workspace
        # is fully in the store with its repos). force=False so the TTL cache gates
        # rapid re-creates; gh is gated on availability + TTL + debounce — no poll.
        self._refresh_workspace_status(workspace)

    def _workspace_root_cwd(self, workspace: Workspace) -> str:
        """Working dir for the workspace's terminals (UX pivot): the workspace folder root.

        Both workspace-level terminals open at ``workspace.workspace_dir`` (it mirrors the project
        root — chosen repos as worktree dirs + relative symlinks for everything
        else) so one agent sees and works across ALL the workspace's repos. Degenerate
        1-repo workspace: open at that sole repo's worktree dir so the visible result
        equals today's 1-repo behavior (the agent lands inside the repo).
        """
        if len(workspace.repos) == 1:
            return workspace.repos[0].worktree_dir
        return workspace.workspace_dir

    def _spawn_workspace_terminals(self, workspace: Workspace) -> None:
        """Spawn the workspace's agent (fed claude) + shell (plain) pair (UX pivot).

        Both root at ``_workspace_root_cwd(workspace)`` (the workspace folder, or the sole repo's
        worktree in the degenerate 1-repo case). pid/pgid land on ``workspace.terminals``.

        Before spawning, propagate the project root's claude trust to the workspace
        paths (claude_trust): the agent pane runs ``claude`` immediately, and without
        a ``hasTrustDialogAccepted`` entry for the fresh folder it drops the repo's
        ``settings.local.json`` permissions until the user re-accepts the dialog.
        Shared create+resume hook point, so pre-fix workspaces heal on reopen.
        """
        proj = self._project_for_workspace(workspace)
        if proj is not None:
            claude_trust.pretrust_paths(
                claude_trust.default_claude_json_path(),
                proj.root,
                [workspace.workspace_dir, *(r.worktree_dir for r in workspace.repos)],
            )
        cwd = self._workspace_root_cwd(workspace)
        agent_tid = f"{workspace.workspace_id}:t0"
        shell_tid = f"{workspace.workspace_id}:t1"
        agent = self._term_by_sid.get(agent_tid)
        shell = self._term_by_sid.get(shell_tid)
        if agent is not None:
            self._spawn_into(agent, cwd, workspace, agent_tid, kind="agent")
        if shell is not None:
            self._spawn_into(shell, cwd, workspace, shell_tid, kind="shell")

    # --- per-worktree [setup] feed (ENV-02, criterion 4) --------------------

    def _run_repo_setups(self, workspace: Workspace) -> None:
        """ENV-02: gather each repo's [setup], run trusted ones silently, gate the rest.

        CREATE-only (called from _finalize_workspace_creation). For every succeeded repo
        with a non-empty [setup] (read from its worktree's .arduis.toml): already-
        trusted (repo_realpath, hash) repos feed silently; the rest are collected and
        confirmed via ONE consolidated Adw.AlertDialog (D-08). 'Pular' leaves the
        worktree un-setup and persists nothing (re-prompt next create). A garbage file
        -> RepoSetup([]) -> no gate (criterion 1).
        """
        to_confirm: list[tuple[RepoCheckout, list[str], str, str]] = []
        for repo in workspace.repos:
            setup = repoconfig.load_repo_setup(repo.worktree_dir)
            if not setup.commands:
                continue  # no [setup] -> no gate, no dialog (the dominant no-op path)
            h = trust.setup_hash(setup.commands)
            repo_id = os.path.realpath(self._member_repo_path(repo.repo_name))
            if trust.is_trusted(self._trusted_setups_path, repo_id, h):
                self._feed_repo_setup(workspace, repo, setup.commands)  # silent (trusted)
            else:
                to_confirm.append((repo, setup.commands, repo_id, h))
        if to_confirm:
            self._present_setup_trust(workspace, to_confirm)

    def _feed_repo_setup(
        self, workspace: Workspace, repo: RepoCheckout, commands: list[str]
    ) -> None:
        """Feed ``cd <worktree> &&`` + the commands into the workspace's SHELL terminal (t1).

        NEVER the agent terminal (t0) — feeding the claude TUI corrupts its input
        (Pitfall 2). The cd-guard re-roots into the repo's own worktree so multi-repo
        setups resolve relative paths (Pitfall 1). Best-effort: a missing terminal or a
        feed error must not crash creation (D-06).
        """
        shell = self._term_by_sid.get(f"{workspace.workspace_id}:t1")
        if shell is None:
            return
        try:
            shell.feed_child(repoconfig.setup_feed_bytes(repo.worktree_dir, commands))
        except Exception:  # noqa: BLE001 - a feed failure must never break creation
            pass

    def _present_setup_trust(
        self, workspace: Workspace, to_confirm: list[tuple[RepoCheckout, list[str], str, str]]
    ) -> None:
        """Consolidated trust gate (D-08), mirroring _present_hook_consent.

        Shows the EXACT commands grouped per repo (the security disclosure). 'Confiar e
        rodar' record_trusts each + feeds; 'Pular' persists nothing and feeds nothing
        (the worktree still opened; the user can run setup by hand).
        """
        blocks = []
        for repo, commands, _rid, _h in to_confirm:
            blocks.append(f"{repo.repo_name}:\n  " + "\n  ".join(commands))
        body = (
            "Estes repositórios pedem para rodar comandos de setup na nova worktree. "
            "Os comandos vêm do .arduis.toml do repositório — rode-os só se confiar nele.\n\n"
            + "\n\n".join(blocks)
        )
        dialog = Adw.AlertDialog(heading="Rodar setup destes repositórios?", body=body)
        dialog.add_response("skip", "Pular")
        dialog.add_response("trust", "Confiar e rodar")
        dialog.set_response_appearance("trust", Adw.ResponseAppearance.SUGGESTED)
        dialog.set_default_response("trust")
        dialog.set_close_response("skip")

        def _on_response(_dlg, response):
            if response != "trust":
                return  # 'Pular'/close: persist nothing, feed nothing (re-prompt)
            for repo, commands, repo_id, h in to_confirm:
                trust.record_trust(self._trusted_setups_path, repo_id, h)
                self._feed_repo_setup(workspace, repo, commands)

        dialog.connect("response", _on_response)
        dialog.present(self)

    def _split_active_pane(
        self,
        focused_tid: str | None,
        orientation: str = "h",
        feed: bytes | None = None,
    ) -> None:
        """Split the active workspace, spawning a new agent terminal beside ``focused_tid`` (D-05).

        Every split is an agent terminal by default (D-05) — Ctrl+C drops to the
        shell. UX pivot (2026-06-11): a workspace split is a WORKSPACE-level terminal — id
        ``{workspace}:tN`` rooted at the workspace folder (``_workspace_root_cwd``), tracked on
        ``workspace.terminals`` so RAM/teardown see it — coherent with the default pair
        opening at the workspace root. On the pinned main workspace there is no Workspace —
        spawn into the project root, untracked.

        ``orientation`` ("h"/"v") threads through to ``LayoutModel.split`` (UI-01):
        the top/bottom split button passes "v" (stacked); ``C-Space -``/``=`` pass "v"/"h"
        from the keymap tuple's second element.

        Empty-state recovery (quick 260702-kzo): ``focused_tid`` may be ``None`` (empty-state
        button, or the ``C-Space =``/``-`` keybinding on a workspace whose panes were all
        closed). When the model has no visible pane to split beside, ROOT the new leaf instead
        of no-oping — same degenerate path ``_open_diff_leaf`` already uses — so a blank canvas
        always has a keyboard/click path back to a live agent.
        """
        sid = self._active_workspace_sid
        if sid is None:
            return
        model = self._workspace_layout(sid)

        workspace = self._store.get(sid)
        if workspace is not None:
            cwd = self._workspace_root_cwd(workspace)
            new_tid = self._next_term_id(sid)
            label = workspace.branch
        else:
            cwd = self._repo_root or GLib.get_home_dir()
            new_tid = self._next_term_id(sid)
            label = self._repo_name or "main"

        terminal = self._make_terminal()
        terminal.connect("child-exited", self._on_worktree_term_exited)
        leaf = self._make_leaf(new_tid, label, terminal, badge_label="claude")
        self._leaf_by_sid[new_tid] = leaf
        self._term_by_sid[new_tid] = terminal

        if model.root is None or focused_tid is None or not model.is_visible(focused_tid):
            # Empty canvas (all panes closed / restored empty): root the new leaf
            # instead of no-oping — same degenerate pattern as _open_diff_leaf. This
            # is the empty-state recovery path (quick 260702-kzo).
            model.root = LeafNode(new_tid)
            model.focused_id = new_tid
            model.touch(new_tid)
        else:
            model.split(focused_tid, new_tid, orientation)
        self._reflect_layout()

        if workspace is not None:
            # Track the split as a workspace-level terminal so RAM/teardown see it.
            workspace.terminals.append(TerminalRecord(new_tid, "agent"))
            self._spawn_into(
                terminal, cwd, workspace, new_tid, kind="agent", feed_override=feed
            )
        else:
            # main workspace has no store workspace — spawn plain, no record to write.
            self._spawn_into(
                terminal, cwd, None, new_tid, kind="agent", feed_override=feed
            )
        self._schedule_layout_save()

    # --- voice agent: spoken prompt → new agent pane --------------------------

    def _run_voice_prompt(self, prompt: str) -> None:
        """Run a dictated ``prompt`` in a NEW agent pane of the active workspace.

        Handsfree flow (voice design): normalize the transcript, build the feed
        line ``<agent argv> '<prompt>'`` (shlex-quoted — quotes/metachars in the
        prompt stay literal), split the focused pane exactly like ``+`` does, and
        persist the prompt at the top of the history so it can be re-run later.
        A blank transcript is a strict no-op (toast, no pane, no history entry).
        """
        normalized = voice.normalize_transcript(prompt)
        if not normalized:
            self._toast("Nada reconhecido — tente de novo")
            return
        feed = agentconfig.prompt_feed_bytes(self._agent_config.command, normalized)
        model = self._active_layout()
        self._split_active_pane(
            model.focused_id if model is not None else None, "h", feed=feed
        )
        voice_store.append_entry(
            self._voice_history_path,
            normalized,
            time.strftime("%Y-%m-%dT%H:%M:%S"),
            cap=self._voice_config.history_max,
        )

    def _toggle_voice(self) -> None:
        """Mic button / ``C-Space v``: start listening, or stop-and-transcribe.

        Handsfree loop: recording ends on 1.5s of silence (or the manual toggle /
        max cap), whisper transcribes, and the prompt runs straight into a new
        agent pane via ``_run_voice_prompt``. Errors (Gst missing, whisper/model
        missing, nothing recognized) surface as toasts and reset to idle.
        """
        if self._voice_controller is None:
            self._voice_controller = VoiceController(
                self._voice_config,
                self._runner,
                on_state=self._on_voice_state,
                on_transcript=self._run_voice_prompt,
                on_error=self._toast,
            )
        self._voice_controller.toggle()

    def _on_voice_btn_toggled(self, _btn) -> None:
        if self._voice_btn_guard:
            return  # programmatic sync from _on_voice_state, not a user click
        self._toggle_voice()

    def _on_voice_state(self, state: str) -> None:
        """Reflect the voice machine state on the mic button (active + CSS)."""
        self._voice_btn_guard = True
        try:
            self._voice_btn.set_active(state == "recording")
        finally:
            self._voice_btn_guard = False
        for css, on in (
            ("voice-recording", state == "recording"),
            ("voice-transcribing", state == "transcribing"),
        ):
            if on:
                self._voice_btn.add_css_class(css)
            else:
                self._voice_btn.remove_css_class(css)

    def _refresh_voice_history(self) -> None:
        """Rebuild the history popover rows from ``voice_history.json`` (newest first)."""
        listbox = self._voice_history_list
        while (child := listbox.get_first_child()) is not None:
            listbox.remove(child)
        entries = voice_store.load_history(self._voice_history_path)
        if not entries:
            empty = Gtk.Label(label="Nenhum prompt falado ainda")
            empty.add_css_class("dim-label")
            empty.set_margin_top(12)
            empty.set_margin_bottom(12)
            empty.set_margin_start(12)
            empty.set_margin_end(12)
            listbox.append(empty)
            return
        for entry in entries:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.set_margin_top(4)
            row.set_margin_bottom(4)
            row.set_margin_start(8)
            row.set_margin_end(8)
            label = Gtk.Label(label=entry["text"], xalign=0)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(48)
            label.set_hexpand(True)
            label.set_tooltip_text(entry["text"])
            row.append(label)
            run_btn = Gtk.Button(icon_name="media-playback-start-symbolic")
            run_btn.add_css_class("flat")
            run_btn.set_tooltip_text("Rodar de novo")
            run_btn.connect(
                "clicked",
                (lambda text: lambda *_: (
                    self._voice_history_popover.popdown(),
                    self._run_voice_prompt(text),
                ))(entry["text"]),
            )
            row.append(run_btn)
            listbox.append(row)

    def _all_workspace_terminals(self, workspace: Workspace) -> list[TerminalRecord]:
        """Every TerminalRecord owned by ``workspace``: workspace-level pair + any per-repo splits.

        Under the UX pivot the default workspace lives in ``workspace.terminals``; a user
        could still attach a split to a specific repo (``workspace.repos[*].terminals``).
        RAM accounting + teardown must cover BOTH so no process group is missed.
        """
        records: list[TerminalRecord] = list(workspace.terminals)
        for repo in workspace.repos:
            records.extend(repo.terminals)
        return records

    # --- Phase 8: read-only diff leaf (REVIEW-01, D-02) ----------------------

    def _open_diff_leaf(self, workspace: Workspace, repo: RepoCheckout) -> None:
        """Open a READ-ONLY VTE leaf running ``git --no-pager diff`` for ``repo`` (D-02).

        REVIEW-01: spawn a NEW leaf in the ACTIVE workspace, reusing the same
        leaf-insertion path a split uses (``_make_terminal`` → ``_make_leaf`` →
        register in the widget maps → ``LayoutModel.split`` → ``_reflect_layout``).
        ``terminal.set_input_enabled(False)`` (VTE 0.76, confirmed present) makes
        the pane a read-only viewer — scroll/copy still work, but no keystroke
        reaches the child (T-08-08). The login shell resolves PATH/pager/color, runs
        the diff, then drops to ``exec zsh -i`` so the buffer stays alive for
        scroll/copy. argv is a LIST with ``cwd=worktree_dir`` — the branch is never
        interpolated into the command string (T-08-09).

        Teardown (PINNED): the diff leaf is NOT tracked as a TerminalRecord (it is
        not an agent and never writes a state file). ``_close_terminal`` cleans it up
        via the layout/widget-map path alone — the ``record is None`` branch there
        simply drops the leaf without a pgid kill, and the leaf's own ``✕`` runs
        ``_close_terminal``. The diff child dies with its PTY when the pane closes.
        """
        sid = self._active_workspace_sid
        if sid is None:
            return  # no active workspace to host the diff leaf
        model = self._workspace_layout(sid)

        diff_tid = f"{sid}:diff:{repo.repo_name}"
        # If a diff leaf for this repo is already open, just re-reflect (focus it)
        # rather than stacking duplicates.
        if diff_tid in self._term_by_sid:
            model.focused_id = diff_tid
            self._reflect_layout()
            return

        terminal = self._make_terminal()
        # Read-only viewer: disable input BEFORE spawning so no keystroke ever
        # reaches the child (REVIEW-01 / T-08-08). 0.76 floor: confirmed present.
        terminal.set_input_enabled(False)
        leaf = self._make_leaf(
            diff_tid, f"diff {repo.repo_name}", terminal, badge_label="diff"
        )
        self._leaf_by_sid[diff_tid] = leaf
        self._term_by_sid[diff_tid] = terminal

        # Insert beside the focused pane exactly like a split. If the workspace has
        # no focused leaf yet (degenerate), root it.
        if model.focused_id is not None and model.focused_id in self._term_by_sid:
            model.split(model.focused_id, diff_tid, "h")
        else:
            model.root = LeafNode(diff_tid)
            model.focused_id = diff_tid
            model.touch(diff_tid)
        self._reflect_layout()

        terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            repo.worktree_dir,
            ["zsh", "-l", "-i", "-c", "git --no-pager diff; exec zsh -i"],
            ["TERM=xterm-256color"],
            GLib.SpawnFlags.DEFAULT,
            None,                 # child_setup
            None,                 # child_setup_data
            -1,                   # timeout (-1 = none)
            None,                 # cancellable
            self._make_diff_spawn_cb(diff_tid),
        )

    def _make_diff_spawn_cb(self, diff_tid: str):
        """Benign spawn callback for the read-only diff leaf (no record to write).

        The diff leaf is not tracked as a TerminalRecord; on spawn failure the pane
        just stays a usable read-only shell (no banner). No pid is stored — the
        child dies with its PTY when the leaf is closed via ``_close_terminal``.
        """

        def _on_diff_spawned(_terminal, _pid, _error) -> None:
            return  # nothing to track; layout/widget cleanup handles teardown

        return _on_diff_spawned

    def _on_ver_diff(self, _action, param) -> None:
        """Row-menu ``win.ver_diff(repo_name)``: open the read-only diff for that repo.

        Resolves the right-clicked workspace + the repo by the string target. A
        hibernated workspace still has worktrees on disk, so the diff is
        available there too.
        """
        if self._menu_target_sid is None:
            return
        workspace = self._store.get(self._menu_target_sid)
        if workspace is None:
            return
        repo_name = param.get_string()
        repo = next((r for r in workspace.repos if r.repo_name == repo_name), None)
        if repo is None:
            return
        self._open_diff_leaf(workspace, repo)

    # --- Phase 8: branch + PR status subline (GIT-01/REVIEW-02, D-03) --------

    def _set_status_subline(self, sid: str, text: str) -> None:
        """Update a workspace row's subline label in place (guard a rebuilt/missing row).

        Reuses the EXISTING ``_subline_by_sid`` label set in ``_make_row`` — no row
        rebuild. The row may have been rebuilt between the async read kick and the
        callback, so a missing label is a silent no-op (never crash the GLib loop).
        """
        label = self._subline_by_sid.get(sid)
        if label is not None:
            label.set_text(text)

    def _refresh_workspace_status(self, workspace: Workspace, *, force: bool = False) -> None:
        """Read branch + ahead/behind (git) + PR (gh) and render the row subline (D-03).

        THROTTLE (T-08-10): branch/ahead-behind are cheap local git reads; the PR
        read is gated on ``gh.gh_available()`` FIRST (absent → ``GH_ABSENT_MSG``,
        never call gh), then on the TTL cache (``fresh_payload`` within ``GH_TTL_S``)
        unless ``force``, then on the ``_pr_busy`` in-flight debounce (DROP, never
        queue). All reads go through ``run_git_async`` with ``cwd=worktree`` on the
        GLib loop. NEVER a poll. Uses the workspace's PRIMARY repo (``workspace.repos[0]``) —
        aggregate-in-subline per the plan.
        """
        if not workspace.repos:
            return
        repo = workspace.repos[0]
        sid = workspace.workspace_id
        now = time.monotonic()

        # State threaded through the async branch/ahead-behind chain so the PR
        # render can prefix the branch subline.
        branch_sub = {"text": gh.format_branch_subline(repo.branch, 0, 0)}

        def _kick_pr() -> None:
            # PR read: gate availability → TTL cache → debounce.
            if not gh.gh_available():
                self._set_status_subline(sid, gh.GH_ABSENT_MSG)
                return
            if not force:
                cached = self._review_cache.fresh_payload(sid, now, GH_TTL_S)
                if cached is not None:
                    self._set_status_subline(
                        sid, f"{branch_sub['text']} · {gh.format_pr_subline(cached)}"
                    )
                    return
            if sid in self._pr_busy:
                return  # in-flight — DROP (debounce, never queue)
            self._pr_busy.add(sid)
            run_git_async(
                gh.argv_pr_view(repo.branch),
                _on_pr,
                runner=self._runner,
                cwd=repo.worktree_dir,
            )

        def _on_pr(rc: int, out: str, err: str) -> None:
            self._pr_busy.discard(sid)  # ALWAYS clear the in-flight guard
            if rc == gh.GH_EXIT_NEEDS_AUTH:
                self._set_status_subline(sid, gh.GH_UNAUTH_MSG)
                return
            if rc != 0 or not out.strip():
                self._set_status_subline(sid, f"{branch_sub['text']} · sem PR")
                return
            try:
                pr = gh.parse_pr_view(out)
            except (ValueError, TypeError):
                return  # garbage — never crash the GLib loop (T-08-05)
            self._review_cache.put(sid, pr, time.monotonic())
            self._set_status_subline(
                sid, f"{branch_sub['text']} · {gh.format_pr_subline(pr)}"
            )

        def _on_ahead_behind(rc: int, out: str, _err: str) -> None:
            if rc == 0:
                ahead, behind = review.parse_ahead_behind(out)
                branch_sub["text"] = gh.format_branch_subline(
                    repo.branch, ahead, behind
                )
            self._set_status_subline(sid, branch_sub["text"])
            _kick_pr()

        def _on_branch(rc: int, out: str, _err: str) -> None:
            name = out.strip() if rc == 0 and out.strip() else repo.branch
            branch_sub["text"] = gh.format_branch_subline(name, 0, 0)
            self._set_status_subline(sid, branch_sub["text"])
            run_git_async(
                review.argv_ahead_behind(repo.worktree_dir, name),
                _on_ahead_behind,
                runner=self._runner,
                cwd=repo.worktree_dir,
            )

        run_git_async(
            review.argv_current_branch(repo.worktree_dir),
            _on_branch,
            runner=self._runner,
            cwd=repo.worktree_dir,
        )

    def _on_refresh_status(self, _action, _param) -> None:
        """Row-menu ``win.refresh_status``: force a TTL-bypassing status re-read (D-03)."""
        workspace = self._menu_session()
        if workspace is None:
            return
        self._refresh_workspace_status(workspace, force=True)

    def _on_open_pr(self, _action, _param) -> None:
        """Row-menu ``win.open_pr``: run ``gh pr create --web`` — the ONE allowed write.

        D-05/REVIEW-02: the only write arduis performs. Runs for the workspace's PRIMARY
        repo via ``run_git_async(cwd=worktree)``; ``--web`` keeps it browser-driven
        (AFK-safe). Toasts the result and, on success, force-refreshes the status so
        the new PR shows. The menu item is offered ONLY when gh is available.
        """
        workspace = self._menu_session()
        if workspace is None or not workspace.repos:
            return
        repo = workspace.repos[0]

        def _on_create(rc: int, _out: str, err: str) -> None:
            if rc == 0:
                self._toast("PR aberto no navegador")
                self._refresh_workspace_status(workspace, force=True)
            elif rc == gh.GH_EXIT_NEEDS_AUTH:
                self._toast(gh.GH_UNAUTH_MSG)
            else:
                first = (err or "").strip().splitlines()
                detail = first[0] if first else f"código {rc}"
                self._toast(f"Falha ao abrir PR: {detail}")

        run_git_async(
            gh.argv_pr_create_web(),
            _on_create,
            runner=self._runner,
            cwd=repo.worktree_dir,
        )

    # --- Phase 8: "Concluir workspace" — the SAFE ordered teardown (REVIEW-03, D-04) ---

    def _on_conclude_action(self, _action, _param) -> None:
        """Row-menu ``win.conclude``: confirm, then run the D-04 safe teardown.

        Resolves the right-clicked workspace via ``_menu_session`` and presents a
        DESTRUCTIVE-styled Adw.AlertDialog that states plainly what conclude does:
        it removes the workspace's WORKTREES while KEEPING the branch and the source
        repos (D-10 / criterion 4). Declining aborts (nothing is touched). On "ok"
        the FIXED ordered chain ``_conclude_workspace`` runs.
        """
        workspace = self._menu_session()
        if workspace is None:
            return
        dialog = Adw.AlertDialog(
            heading=f"Concluir {workspace.branch}?",
            body=(
                "Remove as worktrees do workspace. O código-fonte, o histórico e a "
                "branch ficam intactos. Se alguma worktree tiver mudanças não "
                "commitadas, a conclusão é bloqueada (nada é removido)."
            ),
        )
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("ok", "Concluir")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def _on_response(_dlg, response):
            if response == "ok":
                self._conclude_workspace(workspace)

        dialog.connect("response", _on_response)
        dialog.present(self)

    def _conclude_workspace(self, workspace: Workspace) -> None:
        """The FIXED D-04 safe teardown order (REVIEW-03 criterion 4 — load-bearing).

        Composes three already-built channels in an INVARIANT order, structured as a
        small async state machine driven by ``run_git_async`` callbacks because the
        git reads/removes are async. The ORDER is the security of this phase:

          (a) CLEAN-GATE FIRST: per-repo ``git status --porcelain`` — ALL-OR-NOTHING,
              READ-ONLY. If ANY repo is dirty the WHOLE conclude REFUSES **before
              anything is touched**: agents keep running, containers stay up, state
              files stay. NEVER ``--force`` (the cardinal-sin guard). The gate used
              to run AFTER the kill — a refused conclude then left the workspace with
              dead PTYs behind live VTE widgets (frozen, input-less terminals).
          (a2) UNMERGED-COMMITS GATE, still READ-ONLY: per-repo default-branch
              detection + ``git log <base>..HEAD``. Commits on the workspace
              branch missing from the default branch surface a WARNING dialog
              listing them; only an explicit "Concluir mesmo assim" proceeds,
              and cancelling leaves the workspace fully alive (nothing was
              touched yet).
          (b) ``_teardown_session_terminals`` (kill the workspace's agent/shell process
              groups, killpg) then ``_clear_workspace_state_files`` (delete RUNTIME state
              files — D-10-exempt arduis-owned data) then ``_container_down`` (Phase-7
              compose-down channel; no-op via its own guards if isolation was OFF — a
              SEPARATE channel from killpg, T-07-13). Runs ONLY once the gate passed.
          (c) ``git worktree remove`` (NO ``--force``) per repo, run with cwd=SOURCE
              member repo (D-10), removing only the WORKTREE dir. If git refuses here
              (tree dirtied in the gate→remove race window) the workspace is
              HIBERNATED — its terminals are already dead, so a resumable hibernated
              row is the coherent state, never a zombie ACTIVE row.
          (d) ``git worktree prune`` per source repo.
          (e) unlink the workspace folder's RELATIVE symlinks (``os.path.islink`` guard —
              the LINK only, never the target/source/branch — D-10), rmdir if empty.
          (f) drop the workspace from the store, rebuild the sidebar, fall back to main if
              it was the active workspace, and drop the ``{sid}:`` widget/handle maps
              the way ``_hibernate_workspace`` does.
        """
        # (a) READ-ONLY clean-gate → only on ALL-CLEAN does anything destructive run.
        self._conclude_clean_gate(workspace)

    def _conclude_teardown(self, workspace: Workspace) -> None:
        """(b) The destructive teardown channels — ONLY after the gate passed.

        Kills the workspace's agent/shell process groups, deletes its runtime state
        files, and composes the container stack down. Must NEVER run before the
        clean-gate: a refused conclude has to leave the workspace fully alive.
        """
        self._teardown_session_terminals(workspace)
        self._clear_workspace_state_files(workspace)
        self._container_down(workspace)

    def _conclude_clean_gate(self, workspace: Workspace) -> None:
        """(a) Per-repo porcelain clean-gate — ALL-OR-NOTHING refusal (D-04, A2).

        Reads ``git status --porcelain`` for EVERY repo (cwd=worktree). Collects all
        results, then if ANY repo is dirty (or any read failed rc!=0) REFUSES the
        WHOLE conclude — ZERO worktree-remove argv is ever issued, NOTHING was
        touched (the gate runs BEFORE any teardown, so agents/containers survive a
        refusal) — and surfaces a pt-BR dialog naming the dirty repo(s). Only when
        EVERY repo is clean does it tear down (``_conclude_teardown``) and proceed to
        ``_conclude_remove_worktrees`` (T-08-12).
        """
        repos = list(workspace.repos)
        if not repos:
            # No worktrees to gate/remove — still tear down terminals + containers
            # before the store cleanup (e)+(f).
            self._conclude_teardown(workspace)
            self._conclude_clean_workspace_folder(workspace)
            self._conclude_finalize(workspace)
            return

        pending = {"n": len(repos)}
        dirty: list[str] = []

        def _make_on_status(repo):
            def _on_status(rc: int, out: str, _err: str) -> None:
                if rc != 0 or not review.parse_porcelain_clean(out):
                    dirty.append(repo.repo_name)
                pending["n"] -= 1
                if pending["n"] == 0:
                    if dirty:
                        names = ", ".join(sorted(dirty))
                        self._toast(
                            f"Conclusão bloqueada: worktree(s) com mudanças não "
                            f"commitadas — {names}. Conclua ou descarte antes."
                        )
                        self._conclude_refuse_dialog(names)
                        return  # REFUSE — nothing touched (all-or-nothing)
                    # ALL clean → next READ-ONLY gate: unmerged-commits warning.
                    self._conclude_unmerged_gate(workspace)
            return _on_status

        for repo in repos:
            run_git_async(
                review.argv_status_porcelain(repo.worktree_dir),
                _make_on_status(repo),
                runner=self._runner,
                cwd=repo.worktree_dir,
            )

    def _conclude_refuse_dialog(self, dirty_names: str) -> None:
        """Surface the all-or-nothing dirty refusal as a pt-BR dialog (no force path).

        Names the dirty repo(s) and makes plain that NOTHING was removed — there is
        no "force" affordance in the UI (the cardinal-sin guard, criterion 4).
        """
        dialog = Adw.AlertDialog(
            heading="Conclusão bloqueada",
            body=(
                f"As worktrees a seguir têm mudanças não commitadas: {dirty_names}. "
                "Conclua ou descarte essas mudanças antes de concluir o workspace. "
                "Nenhuma worktree foi removida."
            ),
        )
        dialog.add_response("ok", "Entendi")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.present(self)

    def _conclude_unmerged_gate(self, workspace: Workspace) -> None:
        """(a2) READ-ONLY unmerged-commits gate — warn BEFORE anything destructive.

        Runs only after the porcelain gate passed. For EVERY repo it resolves the
        source repo's default branch (origin/HEAD → local HEAD fallback — the same
        detection workspace creation uses) and lists the commits on the workspace
        branch that are NOT on that default branch (``git log <base>..HEAD`` in
        the worktree). All reads, nothing touched yet — so cancelling the warning
        leaves the workspace fully alive (agents running, containers up).

        - ANY repo with unmerged commits → ``_conclude_unmerged_dialog`` lists
          them and asks explicit confirmation before ``_conclude_proceed``.
        - None anywhere → ``_conclude_proceed`` directly (no extra click).
        - Detection failures (no default branch, log rc!=0) degrade to "nothing
          unmerged" for that repo: the warning is ADVISORY — conclude KEEPS the
          branch and its commits either way (D-10); only the worktrees go.
        """
        repos = list(workspace.repos)
        if not repos:
            self._conclude_proceed(workspace)
            return
        pending = {"n": len(repos)}
        findings: list[tuple[str, list[str]]] = []

        def _done_one() -> None:
            pending["n"] -= 1
            if pending["n"] == 0:
                if findings:
                    findings.sort()
                    self._conclude_unmerged_dialog(workspace, findings)
                    return  # wait for the user's explicit "mesmo assim"
                self._conclude_proceed(workspace)

        def _check_repo(repo) -> None:
            source = self._member_repo_path(repo.repo_name)

            def _with_base(base: str) -> None:
                if not base or base == repo.branch:
                    # No usable base / workspace IS the default branch — nothing
                    # to compare against; advisory gate passes for this repo.
                    _done_one()
                    return

                def _on_log(rc: int, out: str, _err: str) -> None:
                    commits = review.parse_unmerged_commits(out) if rc == 0 else []
                    if commits:
                        findings.append((repo.repo_name, commits))
                    _done_one()

                run_git_async(
                    review.argv_log_unmerged(repo.worktree_dir, base),
                    _on_log,
                    runner=self._runner,
                    cwd=repo.worktree_dir,
                )

            def _origin_done(rc: int, out: str, _err: str) -> None:
                if rc == 0 and out.strip():
                    _with_base(parse_default_branch(out))
                    return

                def _local_done(lrc: int, lout: str, _lerr: str) -> None:
                    _with_base(lout.strip() if lrc == 0 else "")

                run_git_async(
                    argv_default_branch_local(source), _local_done, self._runner
                )

            run_git_async(
                argv_default_branch_via_origin(source), _origin_done, self._runner
            )

        for repo in repos:
            _check_repo(repo)

    def _conclude_unmerged_dialog(
        self, workspace: Workspace, findings: list[tuple[str, list[str]]]
    ) -> None:
        """Warn that the branch has commits missing from the default branch.

        Lists the unmerged commits per repo (capped at 10 per repo so the dialog
        stays readable) and asks for EXPLICIT confirmation. "Cancelar" is the
        default/close response and aborts with the workspace fully alive — the
        gate ran before any destructive channel. Only "Concluir mesmo assim"
        (DESTRUCTIVE-styled) runs ``_conclude_proceed``.
        """
        lines: list[str] = []
        for repo_name, commits in findings:
            lines.append(f"{repo_name}:")
            lines.extend(f"  • {c}" for c in commits[:10])
            if len(commits) > 10:
                lines.append(f"  … e mais {len(commits) - 10} commit(s)")
        dialog = Adw.AlertDialog(
            heading="Commits não integrados",
            body=(
                f"A branch “{workspace.branch}” tem commits que ainda não estão "
                "na branch principal:\n\n" + "\n".join(lines) + "\n\n"
                "A branch e os commits são mantidos no repositório fonte, mas as "
                "worktrees serão removidas. Concluir mesmo assim?"
            ),
        )
        dialog.add_response("cancel", "Cancelar")
        dialog.add_response("ok", "Concluir mesmo assim")
        dialog.set_response_appearance("ok", Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.set_default_response("cancel")
        dialog.set_close_response("cancel")

        def _on_response(_dlg, response):
            if response == "ok":
                self._conclude_proceed(workspace)

        dialog.connect("response", _on_response)
        dialog.present(self)

    def _conclude_proceed(self, workspace: Workspace) -> None:
        """Run the destructive channels — ONLY after every read-only gate passed.

        The single entry point into (b)+(c): both the no-findings path of the
        unmerged gate and the dialog's "Concluir mesmo assim" land here, so the
        teardown→remove pairing can never diverge between the two paths.
        """
        self._conclude_teardown(workspace)
        self._conclude_remove_worktrees(workspace)

    def _conclude_remove_worktrees(self, workspace: Workspace) -> None:
        """(d) Per-repo ``git worktree remove`` (NO ``--force``), cwd=SOURCE repo (D-10).

        Runs ``review.argv_worktree_remove(source_repo, worktree_dir)`` for EACH repo
        with cwd=the SOURCE member repo (never the worktree). The remove TARGET is
        always the worktree dir; the source repo and the branch are never touched. If
        git itself refuses (rc!=0 — e.g. the tree went dirty/locked in the gate→remove
        race window) the chain STOPS, surfaces the stderr in pt-BR, and HIBERNATES the
        workspace — its terminals were already killed by ``_conclude_teardown``, so
        leaving the row ACTIVE would show live VTE widgets over dead PTYs (the
        frozen-terminal bug). It does NOT escalate to ``--force`` (T-08-14, Pitfall
        3/6). When every remove succeeds → prune (d).
        """
        repos = list(workspace.repos)
        pending = {"n": len(repos)}
        failed: list[str] = []

        def _make_on_remove(repo):
            def _on_remove(rc: int, _out: str, err: str) -> None:
                if rc != 0:
                    detail = (err or "").strip().splitlines()
                    msg = detail[0] if detail else f"código {rc}"
                    failed.append(f"{repo.repo_name}: {msg}")
                pending["n"] -= 1
                if pending["n"] == 0:
                    if failed:
                        self._toast(
                            "Falha ao remover worktree(s): " + "; ".join(failed)
                            + ". O workspace foi hibernado — retome para continuar."
                        )
                        # Terminals are already dead (teardown ran pre-remove) —
                        # hibernate so the row is resumable, never a zombie.
                        self._hibernate_workspace(workspace)
                        return  # STOP — no --force escalation
                    self._conclude_prune(workspace)
            return _on_remove

        for repo in repos:
            source = self._member_repo_path(repo.repo_name)
            run_git_async(
                review.argv_worktree_remove(source, repo.worktree_dir),
                _make_on_remove(repo),
                runner=self._runner,
                cwd=source,
            )

    def _conclude_prune(self, workspace: Workspace) -> None:
        """(e) Per-source-repo ``git worktree prune`` (clean stale admin entries).

        Fire-and-forget per source repo; when all prunes return, proceeds to the
        symlink cleanup (f) + store drop (g). A prune failure is non-fatal (the
        worktree is already gone) — it never blocks the store cleanup.
        """
        repos = list(workspace.repos)
        pending = {"n": len(repos)}

        def _on_prune(_rc: int, _out: str, _err: str) -> None:
            pending["n"] -= 1
            if pending["n"] == 0:
                self._conclude_clean_workspace_folder(workspace)
                self._conclude_finalize(workspace)

        for repo in repos:
            source = self._member_repo_path(repo.repo_name)
            run_git_async(
                review.argv_worktree_prune(source),
                _on_prune,
                runner=self._runner,
                cwd=source,
            )

    def _conclude_clean_workspace_folder(self, workspace: Workspace) -> None:
        """(f) Unlink the workspace folder's RELATIVE symlinks — the LINK only (D-10).

        Recomputes the symlink dst set via ``symlink_plan`` and ``os.unlink``s ONLY
        the dsts that are ``os.path.islink`` (the LINK, never ``realpath`` + delete,
        never ``shutil.rmtree`` — that would follow/strip the targets, Pitfall 5).
        Then ``os.rmdir`` the workspace folder ONLY if it is now empty (swallow OSError if
        not — never recursively remove). The source repos, symlink TARGETS, branches
        and the meta-repo ``.git`` are NEVER touched (T-08-13).
        """
        root = self._project_root
        if root is None:
            return
        chosen = {r.repo_name for r in workspace.repos}
        try:
            plan = symlink_plan(root, workspace.workspace_dir, chosen)
        except OSError:
            plan = []
        for _src, dst in plan:
            try:
                if os.path.islink(dst):  # the LINK only — never the target (D-10)
                    os.unlink(dst)
            except OSError:
                pass  # best-effort; never crash the GLib loop on cleanup
        try:
            os.rmdir(workspace.workspace_dir)  # only succeeds if empty — never rmtree
        except OSError:
            pass  # not empty / already gone — leave it (D-10: never force-delete)

    def _conclude_finalize(self, workspace: Workspace) -> None:
        """(g) Drop the workspace from the store + rebuild sidebar + main fallback (D-04).

        Mirrors the ``_hibernate_workspace`` store/widget-map drop: removes the workspace from
        the SessionStore, drops its saved layout + every ``{sid}:``-prefixed
        widget/handle map entry, falls back to the always-present main workspace if
        the concluded workspace was the visible one, and rebuilds the sidebar so the row
        disappears. The branch + source repos remain on disk (D-10).
        """
        sid = workspace.workspace_id
        self._store.remove(sid)
        self._calm_since.pop(sid, None)
        self._layouts.pop(sid, None)
        prefix = f"{sid}:"
        for tid in [t for t in self._leaf_by_sid if t.startswith(prefix)]:
            self._leaf_by_sid.pop(tid, None)
        for tid in [t for t in self._term_by_sid if t.startswith(prefix)]:
            self._term_by_sid.pop(tid, None)
        for tid in [t for t in self._pane_dot_by_tid if t.startswith(prefix)]:
            self._pane_dot_by_tid.pop(tid, None)
        for tid in [t for t in self._notif_by_tid if t.startswith(prefix)]:
            self._notif_by_tid.pop(tid, None)
        for tid in [t for t in self._badge_by_tid if t.startswith(prefix)]:
            self._badge_by_tid.pop(tid, None)
        for tid in [t for t in self._activity_ts if t.startswith(prefix)]:
            self._activity_ts.pop(tid, None)
        for tid in [t for t in self._activity_last_handled if t.startswith(prefix)]:
            self._activity_last_handled.pop(tid, None)
        if self._active_workspace_sid == sid:
            self._swap_workspace(_MAIN_SID)
        self._rebuild_sidebar()

    def _next_term_id(self, sid: str) -> str:
        """Return the next free ``{sid}:tN`` terminal id for workspace ``sid``."""
        n = 0
        while f"{sid}:t{n}" in self._term_by_sid:
            n += 1
        return f"{sid}:t{n}"

    # --- spawn + feed claude (WT-03, D-08) ----------------------------------

    def _spawn_into(
        self,
        terminal: Vte.Terminal,
        cwd: str,
        workspace: Workspace | None,
        term_id: str,
        kind: str = "agent",
        resume: bool = False,
        feed_override: bytes | None = None,
    ) -> None:
        """Spawn zsh -l -i in ``cwd``; feed the configured agent only when ``kind == "agent"``.

        ``feed_override`` (voice agent) replaces the default agent feed bytes with a
        caller-built line (e.g. ``claude '<spoken prompt>'``); ``None`` keeps the
        legacy behavior byte-identical.

        Writes the spawned ``pid``/``pgid`` onto the matching ``TerminalRecord``
        found across the workspace's terminals (workspace-level ``workspace.terminals`` first, then
        any per-repo ``workspace.repos[*].terminals``) by ``term_id``. A plain ``shell``
        terminal is NOT fed ``claude``.

        Phase 4 (STATUS-01): EVERY agent terminal gets the per-terminal env pair
        ``ARDUIS_STATE_FILE`` (where the hook writes) + ``ARDUIS_SESSION_META``
        (the term id) injected through the additive ``extra_env`` seam. A real
        workspace's agent registers in ``_record_by_state_file`` so the watcher flips
        the record's status; a MAIN-workspace agent split (workspace=None — D-05 made
        every split an agent) has no TerminalRecord, so its state file maps
        straight to its pane dot via ``_main_dot_by_state_file``. Plain shell
        terminals get NO extra env — the hook is then a no-op (Pitfall 8).
        """
        extra_env: list[str] | None = None
        if kind == "agent":
            # A3: namespace the status-file path per project so two projects with a
            # same-named branch never share a status file. The hook writes to this
            # exact path and the watcher key below is the SAME path → consistent.
            state_file = attention.state_file_path(
                self._status_dir, self._proj_term_id(term_id)
            )
            extra_env = [
                f"ARDUIS_STATE_FILE={state_file}",
                f"ARDUIS_SESSION_META={term_id}",
            ]
            # Reveal the pane-header status dot for this agent terminal (D-07).
            pane_dot = self._pane_dot_by_tid.get(term_id)
            if pane_dot is not None:
                pane_dot.set_visible(True)
            record = None
            if workspace is not None:
                record = next(
                    (
                        t
                        for t in self._all_workspace_terminals(workspace)
                        if t.term_id == term_id
                    ),
                    None,
                )
                if record is not None:
                    self._record_by_state_file[state_file] = (workspace, record)
            elif pane_dot is not None:
                # Main-workspace agent split: no record — track the widgets
                # directly, scoped to the owning (active-at-spawn) project.
                self._main_split_info[state_file] = {
                    "root": self._project_root,
                    "tid": term_id,
                    "dot": pane_dot,
                    "leaf": self._leaf_by_sid.get(term_id),
                    "status": None,
                    "status_ts": None,
                }
            # Degraded mode (D-13, hooks declined): the bell + contents-changed
            # signals are the ONLY status signal. Both are pre-0.76 (floor-safe). Do
            # NOT connect in primary mode — hooks are authoritative there and a BEL
            # would fight them. Reveal the dot regardless (it shows the coarse signal).
            if self._degraded and record is not None:
                terminal.connect("bell", self._make_bell_cb(workspace, record))
                terminal.connect(
                    "contents-changed",
                    self._make_activity_cb(workspace, record, state_file),
                )
            # Instant-waiting accelerator (ALL modes): scan the terminal tail for
            # a blocking dialog on contents-changed — escalate-only, so it never
            # fights the authoritative hook events (they overwrite it).
            terminal.connect(
                "contents-changed",
                self._make_prompt_scan_cb(terminal, workspace, term_id, state_file),
            )
        argv, envv = build_worktree_spawn(self._runner, extra_env)
        terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            cwd,                  # per-repo worktree working directory (WT-03)
            argv,                 # ["zsh", "-l", "-i"]
            envv,                 # ["TERM=xterm-256color"]
            GLib.SpawnFlags.DEFAULT,
            None,                 # child_setup
            None,                 # child_setup_data
            -1,                   # timeout (-1 = none)
            None,                 # cancellable
            self._make_wt_spawn_cb(workspace, term_id, kind, resume, feed_override),
        )
        terminal.grab_focus()

    def _make_wt_spawn_cb(
        self,
        workspace: Workspace | None,
        term_id: str,
        kind: str,
        resume: bool = False,
        feed_override: bytes | None = None,
    ):
        # AGENT-01 (D-01/D-03): the fed agent is the CONFIGURED command (default
        # "claude"), built from agentconfig — not a hardcoded literal. An AUTO-
        # suspended workspace OR an explicit ``resume`` (layout restore) resumes with
        # resume_feed_bytes (appends ``--continue`` ONLY for a claude-family command,
        # D-03) so the conversation survives; a normal create / split feeds the bare
        # configured command. Capture the decision HERE (at callback-creation time) so
        # ``_resume_workspace`` can clear ``workspace.auto_suspended`` immediately after
        # spawning without leaking the flag.
        cmd = self._agent_config.command
        use_resume = resume or (workspace is not None and workspace.auto_suspended)
        if feed_override is not None:
            agent_feed = feed_override  # voice agent: pre-built `claude '<prompt>'` line
        else:
            agent_feed = (
                agentconfig.resume_feed_bytes(cmd)
                if use_resume
                else agentconfig.agent_feed_bytes(cmd)
            )

        def _on_wt_spawned(terminal, pid, error):
            if error is not None or pid == -1:
                return  # D-09: no banner; the pane stays a usable shell
            # Write pid/pgid onto the matching TerminalRecord across ALL of the
            # workspace's terminals (workspace-level + any per-repo splits).
            if workspace is not None:
                record = next(
                    (
                        t
                        for t in self._all_workspace_terminals(workspace)
                        if t.term_id == term_id
                    ),
                    None,
                )
                if record is not None:
                    record.pid = pid
                    try:
                        record.pgid = os.getpgid(pid)  # A1: don't assume pgid == pid
                    except ProcessLookupError:
                        record.pgid = None
            if kind == "agent":
                terminal.feed_child(agent_feed)  # claude [--continue] — bytes (Pitfall 5)
        return _on_wt_spawned

    def _on_worktree_term_exited(self, terminal, status):
        """A worktree shell exiting is local — do not close the whole window."""
        # The pane's shell ended (e.g. user typed `exit`); leave the leaf/dir.
        return

    # --- degraded-mode signals (D-13): bell → waiting, activity → running/idle ---

    def _make_bell_cb(self, workspace: Workspace, record: TerminalRecord):
        """Degraded mode (D-13): a VTE bell is a coarse 'waiting' hint.

        Any program in the PTY can ring BEL (T-04-19 spoofing — accepted: degraded
        mode is explicitly lower-confidence and never auto-suspends, so the worst case
        is a false hint, never a kill). On a bell, mark the record 'waiting' (sticky
        until the next activity burst clears it), route through ``_maybe_notify`` so
        an unfocused waiting still notifies in degraded mode, flip this terminal's
        pane badge to the down-labeled "esperando?" (with the question mark — D-13),
        and refresh the dots. ``returns`` nothing — VTE 'bell' takes no return.
        """
        def _on_bell(_terminal) -> None:
            old = record.status
            record.status = AgentStatus.WAITING.value
            record.status_ts = time.time()
            self._refresh_status_ui(workspace)
            # Down-labeled badge (D-13 lower confidence): "esperando?" not the dot-only
            # treatment of the primary path.
            badge = self._badge_by_tid.get(record.term_id)
            if badge is not None:
                badge.set_text("esperando?")
            # Notification gate uses the PRE-flip status as `old` so a →waiting
            # transition (unfocused) fires once, even in degraded mode.
            self._maybe_notify(workspace, record, old, record.status, None)
        return _on_bell

    def _make_activity_cb(
        self, workspace: Workspace, record: TerminalRecord, state_file: str
    ):
        """Degraded mode (D-13): contents-changed activity → running, clears the bell.

        Throttled to once per second per terminal (T-04-21: a TUI repaint storm must
        not flood the loop — the handler is a dict-write + an occasional label flip).
        Activity bumps ``_activity_ts``; if the record is 'waiting' (a bell hint) or
        has no opinion yet, it becomes 'running' (activity clears the hint) and the
        badge is restored to "claude". 'running'/'idle' staleness vs idle is handled
        on the poll tick. NO 'ready' state in degraded mode (plan_decisions).

        While the prompt scanner sees a blocking dialog on THIS terminal
        (``_dialog_on_screen``), repaints are not progress: do NOT clear the
        waiting — the scanner's deescalate handles the answered case instantly.
        """
        def _on_activity(_terminal) -> None:
            now = time.time()
            last = self._activity_last_handled.get(record.term_id, 0.0)
            if now - last < 1.0:
                return  # throttle: ignore bursts within 1s (T-04-21)
            self._activity_last_handled[record.term_id] = now
            if state_file in self._dialog_on_screen:
                return  # a visible dialog repaints without being progress
            self._activity_ts[record.term_id] = now
            if record.status in (AgentStatus.WAITING.value, None):
                record.status = AgentStatus.RUNNING.value
                record.status_ts = now
                badge = self._badge_by_tid.get(record.term_id)
                if badge is not None:
                    badge.set_text("claude")
                self._refresh_status_ui(workspace)
        return _on_activity

    # --- ~2s off-loop RAM poll (RAM-03/D-12/D-14) ---------------------------

    def _poll_ram(self) -> bool:
        """Write live process-group RSS onto each active session; refresh the UI.

        Runs on the GLib main loop every ~2s (NOT a thread — CLAUDE.md). Bounded to
        the 5–12 active groups (sub-ms, Assumption A1); hibernated/pgid-None sessions
        are skipped (Pitfall 3) and per-pid errors are swallowed inside
        ``group_rss_kb``. Returns ``SOURCE_CONTINUE`` so the timeout keeps firing.

        260616-buk (finding #4): the poll runs across EVERY registered project, not
        just the active one. A BACKGROUND project's agent must still be RAM-polled,
        re-read (so a WAITING transition the FileMonitor missed is surfaced — notify +
        status flip), and time-degraded. Per project we use ITS OWN bundle dicts
        (subline labels, ``calm_since``, ``record_by_state_file``, ``activity_ts``)
        and recompute status-file paths with the OWNING root (``_proj_term_id_for``,
        also closes finding #6), iterating ``proj.store.all()``. The subline
        ``set_text`` is a no-op for background workspaces (their label widget lives in the
        inactive bundle → ``None``), and the dot refresh in ``_apply_state_file`` /
        ``_refresh_status_ui`` is likewise a harmless widget no-op for background
        workspaces (dots reconcile on switch — D-08); the VALUE is the background
        notification + the in-memory ``record.status`` kept fresh.

        Phase 4 / RAM-04 (D-12): this tick also drives idle auto-suspend. Calm-state
        tracking and the ``should_autosuspend`` gate are evaluated per ACTIVE workspace and
        the matching workspaces are suspended AFTER the whole loop (suspend mutates
        layouts/widgets — never during iteration). AUTO-SUSPEND IS RESTRICTED TO THE
        ACTIVE PROJECT (260616-buk decision (i)): ``_hibernate_workspace`` (the shared
        teardown body) is wired to the active bundle's layout/workspace/sidebar maps,
        so auto-suspending a BACKGROUND workspace would tear down its groups while leaving
        the active bundle's widgets/layout stale. Background NOTIFY + dot
        reconcile-on-switch + background RAM polling/re-read all work regardless; only
        the unattended kill is deferred to when the project is active. Degraded mode is
        excluded entirely (no ``ready`` state → never auto-suspend; T-04-18).
        """
        to_suspend: list[Workspace] = []
        now = time.time()
        registry = getattr(self, "_registry", None)
        projects = registry.all() if registry is not None else []
        if not projects:
            # Bootstrap / no registered project: poll the single active store.
            projects = [self._active_or_bootstrap()]
        active_proj = registry.active() if registry is not None else None
        for proj in projects:
            bundle = self._bundle_for(proj)
            subline_by_sid = bundle["subline_by_sid"]
            calm_since = bundle["calm_since"]
            record_by_state_file = bundle["record_by_state_file"]
            activity_ts = bundle["activity_ts"]
            is_active_proj = proj is active_proj
            for workspace in proj.store.all():
                if workspace.state != SessionState.ACTIVE:
                    # Not active → drop any stale calm tracking (Pitfall 8 chain).
                    calm_since.pop(workspace.workspace_id, None)
                    continue  # skip hibernated (Pitfall 3)
                # D-10/D-14 (UX pivot): a workspace's RAM is the SUM of every terminal's
                # process group — the workspace-level pair + any user splits + any per-repo
                # split. Poll each live group (pgid not None — skip the not-yet-spawned),
                # writing each terminal's rss_kb back, then sum for the row subline.
                terms = self._all_workspace_terminals(workspace)
                for t in (t for t in terms if t.pgid is not None):
                    t.rss_kb = resource_monitor.group_rss_kb(t.pgid)
                total = sum(t.rss_kb for t in terms if t.rss_kb)
                label = subline_by_sid.get(workspace.workspace_id)
                if label is not None:
                    label.set_text(
                        f"claude · {resource_monitor.format_ram_kb(total or None)}"
                    )
                # Phase 4 (D-05): ride this tick for the TIME-BASED transitions the
                # FileMonitor never sees — IDLE (ready + threshold) and staleness
                # (running with a dead pgid → ended). Cheap: re-read only the agent
                # records that already have a registered state file (~a few tiny JSON
                # reads). _apply_state_file re-aggregates + refreshes the dots.
                for t in terms:
                    if t.kind != "agent" or t.status is None:
                        continue
                    # A3: re-read the SAME project-namespaced path registered at
                    # spawn, using the OWNING project's root (finding #6).
                    path = attention.state_file_path(
                        self._status_dir,
                        self._proj_term_id_for(proj.root, t.term_id),
                    )
                    if path in record_by_state_file:
                        self._apply_state_file(workspace, t, path)

                # Phase 4 / D-13 (degraded mode): with hooks declined there are no
                # state files — the ONLY status signal is the bell (→waiting) and the
                # contents-changed activity timestamp. On this tick, an agent terminal
                # with NO activity for idle_minutes degrades to 'idle' (never 'ready'
                # — D-13 has no ready state, and degraded mode never auto-suspends so
                # 'idle' here is purely cosmetic). A 'waiting' bell hint is sticky and
                # is NOT idle-aged.
                if self._degraded:
                    idle_after = self._att_config.idle_minutes * 60
                    changed = False
                    for t in terms:
                        if t.kind != "agent" or t.status is None:
                            continue
                        if t.status == AgentStatus.WAITING.value:
                            continue  # sticky bell hint — only activity clears it
                        last = activity_ts.get(t.term_id)
                        if (
                            last is not None
                            and idle_after > 0
                            and (now - last) >= idle_after
                            and t.status != AgentStatus.IDLE.value
                        ):
                            t.status = AgentStatus.IDLE.value
                            t.status_ts = now
                            changed = True
                    if changed:
                        self._refresh_status_ui(workspace)

                # Phase 4 / RAM-04 (D-12, Pitfall 6): track when this workspace ENTERED a
                # calm aggregate (ready/idle/ended) and evaluate auto-suspend. The
                # aggregate is recomputed AFTER the status re-apply above so it
                # reflects the freshest idle/staleness transitions. Degraded mode is
                # excluded — it has no `ready` and killing on a coarse signal risks
                # SIGKILL'ing a working agent (T-04-18).
                agg = attention.aggregate_workspace(terms)
                if agg in (AgentStatus.READY, AgentStatus.IDLE, AgentStatus.ENDED):
                    calm_since.setdefault(workspace.workspace_id, now)
                else:
                    # running/waiting/None → reset; a real burst un-calms the workspace.
                    calm_since.pop(workspace.workspace_id, None)
                # 260616-buk decision (i): only the ACTIVE project auto-suspends (the
                # shared hibernate body is active-bundle-bound). Background calm
                # tracking still advances above so a switched-to workspace suspends promptly.
                if (
                    is_active_proj
                    and not self._degraded
                    and attention.should_autosuspend(
                        agg,
                        calm_since.get(workspace.workspace_id),
                        now,
                        self._att_config.auto_suspend_minutes,
                    )
                ):
                    to_suspend.append(workspace)

        # Suspend AFTER the iteration (each suspend drops layouts/widgets/maps and
        # rebuilds the sidebar — never mutate while iterating the store snapshot).
        for workspace in to_suspend:
            self._auto_suspend(workspace)

        self._update_footer()
        return GLib.SOURCE_CONTINUE

    def _update_footer(self) -> None:
        """Render ``N agentes ativos · <total> RAM`` (active count in green)."""
        # getattr guard: partially-constructed windows in unit tests call
        # _apply_theme before the sidebar footer exists.
        if getattr(self, "_footer_label", None) is None:
            return
        workspaces = self._store.all()
        n = caps.active_count(workspaces)
        # D-10 (UX pivot): aggregate sums every active workspace's every terminal RAM
        # (workspace-level pair + splits + any per-repo split).
        total = sum(
            t.rss_kb
            for workspace in workspaces
            if workspace.state == SessionState.ACTIVE
            for t in self._all_workspace_terminals(workspace)
            if t.rss_kb is not None
        )
        total_str = resource_monitor.format_ram_kb(total if total else None)
        # Theme-sourced count color (the old markup hardcoded the Dracula green).
        count_color = self._current_theme.dot_active
        self._footer_label.set_markup(
            f'<span foreground="{count_color}" weight="bold">{n} agentes ativos</span>'
            f" · {total_str} RAM"
        )

    # --- layout persistence: snapshot -> layouts.json -----------------------

    def _leaf_kind_cwd(self, proj, sid: str, tid: str):
        """Return ``(kind, cwd)`` for one leaf, or None if it can't be resolved.

        Real workspaces read kind from the TerminalRecord and cwd from
        ``_workspace_root_cwd``. The main workspace derives kind (``main:t0`` is the
        pinned shell, every other split is an agent per D-05) and roots at the
        project root.
        """
        workspace = proj.store.get(sid)
        if workspace is not None:
            record = next(
                (t for t in self._all_workspace_terminals(workspace) if t.term_id == tid),
                None,
            )
            if record is None:
                return None
            return (record.kind, self._workspace_root_cwd(workspace))
        if sid == _MAIN_SID:
            cwd = proj.root or GLib.get_home_dir()
            kind = "shell" if tid == f"{_MAIN_SID}:t0" else "agent"
            return (kind, cwd)
        return None

    def _snapshot_layouts(self) -> dict:
        """Build the serializable layouts snapshot across every open project.

        A workspace is skipped if its tree is empty or any visible leaf can't be
        resolved to a (kind, cwd) — never persist a half-known layout.
        """
        projects: dict = {}
        for proj in self._registry.all():
            bundle = self._bundle_for(proj)
            workspaces: dict = {}
            for sid, model in bundle["layouts"].items():
                if model is None or model.root is None:
                    continue
                ids = model.visible_ids()
                if not ids:
                    continue
                leaves: dict = {}
                ok = True
                for tid in ids:
                    kc = self._leaf_kind_cwd(proj, sid, tid)
                    if kc is None:
                        ok = False
                        break
                    leaves[tid] = {"kind": kc[0], "cwd": kc[1]}
                if not ok:
                    continue
                workspaces[sid] = {
                    "focused_id": model.focused_id,
                    "tree": layout_store.tree_to_dict(model.root),
                    "leaves": leaves,
                }
            if workspaces:
                projects[proj.root] = {"workspaces": workspaces}
        return {"version": 1, "projects": projects}

    def _schedule_layout_save(self) -> None:
        """Debounce a layouts save ~500ms after a structural change (crash-safety)."""
        if self._layout_save_source is not None:
            GLib.source_remove(self._layout_save_source)
        self._layout_save_source = GLib.timeout_add(500, self._do_layout_save)

    def _do_layout_save(self) -> bool:
        self._layout_save_source = None
        layout_store.save_layouts(self._layouts_json, self._snapshot_layouts())
        return GLib.SOURCE_REMOVE

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
        if model is None:
            # No active workspace (bootstrap, no project) — neutral placeholder box.
            self._canvas_slot.set_child(self._build_widget(None))
            return
        if model.root is None:
            # Active workspace with no panes: recoverable empty state (quick
            # 260702-kzo) — never a blank/black canvas when there IS a workspace.
            self._canvas_slot.set_child(self._make_empty_state())
            return
        self._canvas_slot.set_child(self._build_widget(model.root))

        # Apply the focused-pane purple ring to exactly one leaf (UI-SPEC).
        self._refresh_focus_ring(model.focused_id)

    def _make_empty_state(self) -> Gtk.Widget:
        """Recoverable empty canvas: a centered StatusPage with '+ Novo terminal'.

        Shown when an ACTIVE workspace has no visible pane (all closed / restored
        empty) instead of a blank/black box (quick 260702-kzo). The button reuses the
        exact split spawn path (``_split_active_pane(None, ...)`` → roots a leaf →
        ``_spawn_into(kind="agent")``) so the recovered pane runs the default agent
        (claude) in the current workspace. It is born focused (app is keyboard-driven:
        Enter/Space activates it directly). No new VTE/libadwaita API beyond the 0.76
        VTE floor — ``Adw.StatusPage``/``Adw.ButtonContent`` exist since libadwaita 1.0.
        """
        btn = Gtk.Button()
        content = Adw.ButtonContent(
            icon_name="list-add-symbolic", label="Novo terminal"
        )
        btn.set_child(content)
        btn.add_css_class("suggested-action")
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.connect("clicked", lambda *_: self._split_active_pane(None, "h"))
        page = Adw.StatusPage(
            icon_name="utilities-terminal-symbolic",
            title="Nenhum terminal aberto",
            description="Crie um pane novo com o agente padrão (claude) neste workspace",
        )
        page.set_child(btn)
        # Keyboard-driven app: focus the button so Enter/Space activates it directly
        # (idle so it is mapped/realized before grabbing focus).
        GLib.idle_add(btn.grab_focus)
        return page

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
            paned.set_wide_handle(True)            # wide hit-area for the gap gutter
            # Card gaps: the separator is styled fully transparent (12px) so the
            # canvas background reads as a gap between cards; it stays draggable.
            paned.add_css_class("arduis-split")
            # Both children resize and CAN shrink: with shrink=False a nested
            # Paned whose children each demand a min-size collapses to a single
            # narrow column on first allocation (the position handle is never
            # initialized). Keep the GTK4 defaults (resize+shrink True) and set an
            # explicit proportional position once the paned is mapped so every
            # split — including nested ones — divides its space 50/50 (Failure 1/2).
            paned.set_resize_start_child(True)
            paned.set_resize_end_child(True)
            paned.set_shrink_start_child(True)
            paned.set_shrink_end_child(True)
            paned.set_start_child(self._build_widget(node.start))
            paned.set_end_child(self._build_widget(node.end))
            self._init_paned_position(paned, node)
            return paned
        return Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

    def _init_paned_position(self, paned: Gtk.Paned, node=None) -> None:
        """Keep a Gtk.Paned split proportional (50/50 default), drag-preserving.

        The one-shot ``map`` + ``get_width()`` approach (commit b487dfe) was wrong
        for NESTED paneds: ``map`` fires while the paned still has a tiny transient
        allocation, so an inner/outer split got pinned to ~half of a few pixels
        (~6px) and never corrected — collapsing the whole subtree to a left sliver.

        Instead we drive the position off ``max-position``, which reflects the REAL
        usable extent and re-notifies as the parent distributes space. We re-apply
        the stored ratio on every ``max-position`` change (never one-shot), and
        learn a new ratio from any ``position`` change the USER makes (a drag) so
        manual sizing is preserved.

        The reactive ``notify::max-position`` path alone is NOT enough
        (split-black-pane-hole): creating a split rebuilds the ENTIRE nested Paned
        tree, and during that fresh multi-pass allocation GTK4 coalesces
        max-position notifications — intermittently a paned settles at its real
        extent WITHOUT a final re-notify, so ``_apply`` never runs on a usable
        allocation and the paned keeps a degenerate position (one child ≈0 extent →
        a black hole). We therefore ALSO drive ``_apply`` from a tick callback that
        re-runs every frame until the paned has a real allocation, then removes
        itself — guaranteeing the first proportional split regardless of
        notification coalescing. Learning is guarded by ``_learned_ratio`` so a
        transient/echoed/degenerate position can never poison the persisted ratio.
        """
        ratio = [node.ratio if node is not None else 0.5]  # start from the persisted fraction
        last_set = [-1]     # last position WE applied — used for echo detection
        settled = [False]   # True once we've applied on a REAL (max-position>1) allocation

        def _apply(*_args) -> bool:
            # NEVER touch the position before the paned has a REAL allocation:
            # a freshly built paned reports max-position = G_MAXINT until its
            # first size_allocate, and applying ratio*G_MAXINT makes GTK clamp
            # position == allocation → gtk_paned_calc_position() latches the end
            # child's child_visible to False (allocated-but-unmapped = an
            # invisible black pane) and NEVER restores it on its own.
            extent = (
                paned.get_width()
                if paned.get_orientation() == Gtk.Orientation.HORIZONTAL
                else paned.get_height()
            )
            if extent <= 1:
                return False  # not allocated yet — wait for the next notify/frame
            maxp = paned.get_property("max-position")
            if maxp <= 1:
                return False
            pos = int(maxp * ratio[0])
            last_set[0] = pos
            paned.set_position(pos)
            # Heal a latched child_visible=False (see above): with a sane
            # proportional position both children own a nonzero share, so they
            # must be child-visible; GTK never flips this back by itself.
            for child in (paned.get_start_child(), paned.get_end_child()):
                if (
                    child is not None
                    and child.get_visible()
                    and not child.get_child_visible()
                ):
                    child.set_child_visible(True)
            settled[0] = True
            return True

        def _learn(*_args) -> None:
            # A position change we did NOT cause is a user drag — remember its ratio,
            # but only if it survives every spurious-emission guard.
            learned = _learned_ratio(
                paned.get_position(),
                paned.get_property("max-position"),
                last_set[0],
                settled[0],
            )
            if learned is None:
                return
            ratio[0] = learned
            if node is not None:
                node.ratio = learned  # persist the learned ratio into the tree

        paned.connect("notify::max-position", _apply)
        paned.connect("notify::position", _learn)

        # Guaranteed final application (split-black-pane-hole / split-broken-after-
        # todays-changes): keep re-applying the proportional position on each frame
        # until the paned's usable extent (max-position) has been STABLE for several
        # consecutive frames — NOT merely until it first exceeds 1.
        #
        # Why stability, not first-hit: a freshly rebuilt nested Paned tree — created
        # by a split AND, since restore-on-boot (D-06), by the boot/resume path —
        # passes through TRANSIENT extents during its multi-pass allocation. GTK4
        # coalesces the final ``notify::max-position``, so a paned can settle at its
        # real extent WITHOUT a last re-notify. Stopping at the FIRST max-position>1
        # frame pins the split to a transient extent (one child ≈0 → a black hole
        # that "self-heals only on resize"). Re-applying until the extent settles
        # guarantees the final application lands on the REAL allocation regardless of
        # notification coalescing. A safety budget caps the ticking so a paned that
        # never gets a usable allocation (hidden/collapsed) cannot tick forever; the
        # reactive ``notify::max-position`` path still handles later resizes.
        frames_left = [600]     # ~10s at 60fps — generous; the split settles far sooner
        stable_frames = [0]     # consecutive frames max-position held (within tolerance)
        last_maxp = [-1]        # last max-position we observed, for the stability check

        def _tick(_widget, _clock) -> bool:
            frames_left[0] -= 1
            # Only count stability on frames where the position was actually
            # APPLIED (real allocation): before the first allocate max-position
            # is a constant G_MAXINT, which would read as "stable" and remove
            # the tick without ever applying.
            if _apply():
                maxp = paned.get_property("max-position")
                # Tolerate ±2px jitter so sub-pixel wobble doesn't reset the counter
                # (which would keep re-applying — and fighting a user drag — for the
                # whole budget).
                if abs(maxp - last_maxp[0]) <= 2:
                    stable_frames[0] += 1
                else:
                    stable_frames[0] = 0
                last_maxp[0] = maxp
            # Stop once the extent has held steady (final allocation reached) or the
            # safety budget is exhausted.
            if stable_frames[0] >= 5 or frames_left[0] <= 0:
                return GLib.SOURCE_REMOVE
            return GLib.SOURCE_CONTINUE

        paned.add_tick_callback(_tick)

    # --- helpers: session lookup + user messaging ---------------------------

    def _session_for_worktree_dir(self, path: str) -> Workspace | None:
        """Return the Workspace owning a repo whose worktree_dir matches ``path``."""
        norm = path.rstrip("/")
        for workspace in self._store.all():
            for repo in workspace.repos:
                if repo.worktree_dir.rstrip("/") == norm:
                    return workspace
        return None

    def _show_error(self, heading: str, body: str) -> None:
        dialog = Adw.AlertDialog(heading=heading, body=body or "")
        dialog.add_response("ok", "OK")
        dialog.set_default_response("ok")
        dialog.set_close_response("ok")
        dialog.present(self)

    def _toast(self, msg: str) -> None:
        """Surface a transient Adw.Toast over the canvas (D-10).

        The single entry point for container progress/result feedback. Best-effort
        — if the overlay was not built (defensive), silently no-op rather than crash
        the GLib loop where the compose on_done callbacks run.
        """
        overlay = getattr(self, "_toast_overlay", None)
        if overlay is None:
            return
        overlay.add_toast(Adw.Toast.new(msg))

    # --- row context menu: Hibernate / Resume (D-08) ------------------------

    def _install_row_actions(self) -> None:
        """Register win.hibernate / win.resume actions (reused from Phase 2)."""
        hibernate = Gio.SimpleAction.new("hibernate", None)
        hibernate.connect("activate", self._on_hibernate)
        self.add_action(hibernate)

        resume = Gio.SimpleAction.new("resume", None)
        resume.connect("activate", self._on_resume)
        self.add_action(resume)

        # UI-02 (D-08): win.set_theme(slug) backs the header "Tema" submenu. The
        # string target is a theme slug; _on_set_theme switches + persists.
        set_theme = Gio.SimpleAction.new("set_theme", GLib.VariantType.new("s"))
        set_theme.connect("activate", self._on_set_theme)
        self.add_action(set_theme)

        # 03.4 (D-03): win.switch_project(root) backs the project-tab +N overflow
        # menu items. String target = project root; _on_switch_project_action swaps.
        switch_project = Gio.SimpleAction.new(
            "switch_project", GLib.VariantType.new("s")
        )
        switch_project.connect("activate", self._on_switch_project_action)
        self.add_action(switch_project)

        # 03.4 (D-10): win.remove_project(root) backs the project-tab right-click
        # "Remover projeto" item. String target = project root; the handler tears
        # down live workspaces (behind a DESTRUCTIVE confirm) then drops from the list.
        remove_project = Gio.SimpleAction.new(
            "remove_project", GLib.VariantType.new("s")
        )
        remove_project.connect("activate", self._on_remove_project_action)
        self.add_action(remove_project)

        # Phase 7 (CONT-01/02, D-11): win.toggle_isolation(workspace_id) backs the row
        # menu "Isolar/Desligar containers" entry. String target is the workspace_id;
        # _on_toggle_isolation dispatches enable vs disable from the persisted state.
        toggle_isolation = Gio.SimpleAction.new(
            "toggle_isolation", GLib.VariantType.new("s")
        )
        toggle_isolation.connect("activate", self._on_toggle_isolation_action)
        self.add_action(toggle_isolation)

        # Phase 8 (REVIEW-01, D-02): win.ver_diff(repo_name) opens a read-only diff
        # leaf for that repo's worktree (string target = repo_name).
        # win.refresh_status (D-03) forces a status re-read; win.open_pr
        # (D-05) runs the ONE allowed write `gh pr create --web`. Both no-target,
        # using _menu_target_sid like hibernate.
        ver_diff = Gio.SimpleAction.new("ver_diff", GLib.VariantType.new("s"))
        ver_diff.connect("activate", self._on_ver_diff)
        self.add_action(ver_diff)

        refresh_status = Gio.SimpleAction.new("refresh_status", None)
        refresh_status.connect("activate", self._on_refresh_status)
        self.add_action(refresh_status)

        open_pr = Gio.SimpleAction.new("open_pr", None)
        open_pr.connect("activate", self._on_open_pr)
        self.add_action(open_pr)

        # Phase 8 (REVIEW-03, D-04): win.conclude is the LOAD-BEARING safe teardown.
        # No-target, uses _menu_target_sid like hibernate; _on_conclude_action
        # presents the confirm dialog, then _conclude_workspace runs the FIXED order.
        conclude = Gio.SimpleAction.new("conclude", None)
        conclude.connect("activate", self._on_conclude_action)
        self.add_action(conclude)

    def _menu_session(self) -> Workspace | None:
        """Resolve the right-clicked row back to its tracked Workspace (D-08)."""
        if self._menu_target_sid is None:
            return None
        return self._store.get(self._menu_target_sid)

    def _on_hibernate(self, _action, _param) -> None:
        """D-08 menu path: hibernate the right-clicked workspace (manual, auto_suspended False).

        Thin guard around the shared ``_hibernate_workspace`` body — the right-clicked
        workspace is resolved via ``_menu_session`` and, when ACTIVE, runs the exact same
        teardown/layout-drop/fallback/rebuild path the auto-suspend tick uses. A
        manual hibernate leaves ``workspace.auto_suspended`` False (hibernate_fields never
        touches it), so resume feeds plain ``claude`` — Phase-2 semantics unchanged.
        """
        workspace = self._menu_session()
        if workspace is None or workspace.state == SessionState.HIBERNATED:
            return
        self._hibernate_workspace(workspace)

    def _hibernate_workspace(self, workspace: Workspace) -> None:
        """Shared hibernate body: kill every group, discard layout, free RAM (D-08).

        Extracted from ``_on_hibernate`` (Plan 04) so BOTH the menu path and the
        idle auto-suspend tick (``_auto_suspend``) go through the SAME proven
        no-orphan machinery (03.2-verified — T-04-18). Tears down EVERY terminal's
        process group (agent + shell + any splits) so nothing is orphaned, deletes
        the workspace's state files (Pitfall 5b — placed AFTER teardown, the Plan-03
        ordering, so EVERY caller cleans its files), flips the model to HIBERNATED
        (clearing every pgid; ``auto_suspended`` is left as the caller set it — the
        menu leaves it False, ``_auto_suspend`` sets it True first), then DISCARDS the
        saved LayoutModel + terminal widgets/maps so resume rebuilds the DEFAULT
        2-terminal layout (D-09) rather than the stale tree. If the hibernated workspace
        IS the visible workspace, fall back to main (always present, D-07).
        """
        sid = workspace.workspace_id

        self._teardown_session_terminals(workspace)  # kill every group (Pitfall 3/5)
        # Phase 7 (D-12, CONT-05, Pitfall 7): container teardown is a SEPARATE
        # channel from the killpg agent teardown above — containers are daemon-owned
        # and NOT in arduis's process group. Tear the stack down ALONGSIDE (never
        # inside) _teardown_session_terminals, then flip the durable state OFF while
        # KEEPING the port map so a resumed workspace re-enables on stable ports.
        self._container_down(workspace)
        c_state = self._container_state.get(sid)
        if c_state is not None and c_state.enabled:
            c_state.enabled = False  # KEEP c_state.ports (stable re-enable)
            containerstate.write_container_state(workspace.workspace_dir, c_state)
            self._container_state[sid] = c_state
        self._clear_workspace_state_files(workspace)  # delete state files (Pitfall 5b)
        hibernate_fields(workspace)  # GTK-free: state=HIBERNATED, all pid/pgid=None
        # The workspace is no longer calm-tracked while hibernated (it is not ACTIVE).
        self._calm_since.pop(sid, None)

        # D-09: discard the worktree's saved layout so resume rebuilds the default,
        # not the saved tree (extra splits are not restored).
        self._layouts.pop(sid, None)
        # Drop the worktree's terminal widgets/maps so no detached VTE widget orphans
        # survive across the hibernate (every id is "{sid}:tN").
        prefix = f"{sid}:"
        for tid in [t for t in self._leaf_by_sid if t.startswith(prefix)]:
            self._leaf_by_sid.pop(tid, None)
        for tid in [t for t in self._term_by_sid if t.startswith(prefix)]:
            self._term_by_sid.pop(tid, None)
        # Drop the worktree's pane-dot + notification handles too (mirror the
        # {sid}: prefix pop pattern) so dropped widgets leave no stale handle.
        for tid in [t for t in self._pane_dot_by_tid if t.startswith(prefix)]:
            self._pane_dot_by_tid.pop(tid, None)
        for tid in [t for t in self._notif_by_tid if t.startswith(prefix)]:
            self._notif_by_tid.pop(tid, None)
        # Degraded-mode handles keyed by terminal id (badge label + activity ts).
        for tid in [t for t in self._badge_by_tid if t.startswith(prefix)]:
            self._badge_by_tid.pop(tid, None)
        for tid in [t for t in self._activity_ts if t.startswith(prefix)]:
            self._activity_ts.pop(tid, None)
        for tid in [t for t in self._activity_last_handled if t.startswith(prefix)]:
            self._activity_last_handled.pop(tid, None)

        # If the hibernated worktree was the visible workspace, fall back to main
        # (always present per D-07) so the canvas isn't pointing at a discarded tree.
        if self._active_workspace_sid == sid:
            self._swap_workspace(_MAIN_SID)

        self._rebuild_sidebar()    # dim/grey-dot the row (D-08, not a tab badge)

    def _auto_suspend(self, workspace: Workspace) -> None:
        """Idle auto-suspend a workspace through the shared hibernate path (RAM-04, D-12).

        Reached ONLY via the ``should_autosuspend`` gate in ``_poll_ram`` (the single
        call site — running/waiting are immune at any age, T-04-09/Pitfall 6, and
        degraded mode never reaches here). Marks the workspace ``auto_suspended`` True so
        resume feeds ``claude --continue`` (the conversation survives), runs the same
        proven no-orphan ``_hibernate_workspace`` body, and ALWAYS notifies — even focused
        — because arduis just killed processes on the user's behalf and that must
        never be silent (T-04-22 repudiation).
        """
        workspace.auto_suspended = True
        self._hibernate_workspace(workspace)  # teardown + state-file clear + layout drop + rebuild
        self._calm_since.pop(workspace.workspace_id, None)
        self._notify_suspended(workspace)

    def _notify_suspended(self, workspace: Workspace) -> None:
        """Always-on suspension notification (D-12, T-04-22) — bypasses the focus gate.

        Unlike ``_maybe_notify`` (which suppresses while focused), this fires whether
        or not the window is active: the user must always be able to tell arduis
        suspended their agent. Reuses the Plan-03 libnotify machinery; the per-terminal
        notification slot is keyed by the workspace id so it never collides with an agent
        terminal's waiting notification. Never raises (a dead daemon is swallowed).
        """
        if not _HAS_NOTIFY:
            return
        title = f"{workspace.branch} suspenso"
        body = GLib.markup_escape_text(
            "Suspensa por inatividade — retome para continuar a conversa."
        )
        icon = "dialog-information"
        slot = f"suspend:{workspace.workspace_id}"
        try:
            notif = self._notif_by_tid.get(slot)
            if notif is None:
                notif = Notify.Notification.new(title, body, icon)
                self._notif_by_tid[slot] = notif
            else:
                notif.update(title, body, icon)
            notif.show()
        except Exception as exc:  # noqa: BLE001 - never let a dead daemon crash us
            print(f"arduis: suspension notification failed: {exc}", file=sys.stderr)

    def _on_resume(self, _action, _param) -> None:
        """D-09: rebuild the DEFAULT 2-terminal layout (agent + shell), not a reattach.

        Resume rebuilds the workspace like create (UX pivot 2026-06-11): fresh workspace-level
        terminal records, a fresh LayoutModel with the single agent-over-shell pair
        rooted at the workspace folder via the shared ``_build_workspace_terminals`` helper,
        then both terminals spawned eagerly — only the agent is fed the configured command.
        The repo set is intact (hibernate only cleared pid/pgid). Earlier extra
        splits are NOT restored (03.1 D-09 stands).
        """
        workspace = self._menu_session()
        if workspace is None or workspace.state == SessionState.ACTIVE:
            return
        self._resume_gated(workspace)

    def _resume_workspace(self, workspace: Workspace) -> None:
        """Resume ``workspace``: rebuild default 2-terminal layout + eager spawn (UX pivot)."""
        if workspace.state == SessionState.ACTIVE:
            return
        branch = workspace.branch

        # Fresh workspace-level terminal records (replaces the hibernated, pgid-cleared
        # pair) so spawn callbacks can write pid/pgid back onto them. The repo set is
        # intact (hibernate only cleared pid/pgid) — repos are worktree metadata.
        workspace.terminals = default_workspace_terminals(branch)
        workspace.state = SessionState.ACTIVE
        # Drop any stale suspension-notification slot for this workspace (its key is
        # "suspend:<workspace_id>", not "<workspace_id>:", so the prefix-pop in _hibernate_workspace
        # does not cover it) so a resumed workspace does not reuse a closed notification.
        self._notif_by_tid.pop(f"suspend:{workspace.workspace_id}", None)

        # Restore the saved custom grid if one exists (agents resume with
        # ``--continue``); otherwise rebuild the DEFAULT 2-terminal workspace.
        saved = self._saved_layout_for(workspace.workspace_id)
        restored = False
        if saved is not None:
            workspace.terminals = []  # _restore_layout appends a record per leaf
            proj = self._project_for_workspace(workspace) or self._active_or_bootstrap()
            restored = self._restore_layout(proj, workspace.workspace_id, saved)
        if restored:
            self._rebuild_sidebar()
            workspace.auto_suspended = False
            return

        # Fallback: no usable saved grid -> default 2-terminal workspace (as before).
        workspace.terminals = default_workspace_terminals(branch)
        self._build_workspace_terminals(workspace, [r.repo_name for r in workspace.repos])
        self._rebuild_sidebar()

        # Spawn the workspace's agent+shell pair eagerly: agent fed claude, shell plain.
        # D-12: if this workspace was AUTO-suspended, the agent's spawn callback (built
        # synchronously inside _spawn_workspace_terminals) has already captured the
        # ``claude --continue`` feed decision from ``workspace.auto_suspended``. Clearing
        # the flag immediately AFTER the spawn call returns is therefore safe — the
        # closure holds the decision — and guarantees one ``--continue`` never leaks
        # into a later manual hibernate→resume cycle.
        self._spawn_workspace_terminals(workspace)
        workspace.auto_suspended = False

    # --- teardown (RAM-01, D-11/D-13) ---------------------------------------

    def _teardown_pgid(self, pid: int) -> None:
        """SIGHUP the child's process GROUP, then SIGKILL-sweep (no orphans)."""
        try:
            pgid = os.getpgid(pid)  # A1: don't assume pgid == pid
            os.killpg(pgid, signal.SIGHUP)
            GLib.timeout_add(_SIGKILL_GRACE_MS, self._sigkill_if_alive, pgid)
        except ProcessLookupError:
            pass  # already gone

    @staticmethod
    def _teardown_pgid_now(pid: int) -> int | None:
        """SIGHUP the child's process GROUP and RETURN its pgid (no timer).

        Close-path variant of ``_teardown_pgid``: it does NOT schedule the GLib
        ``SIGKILL`` sweep (the main loop ends the instant the last window closes, so
        that timer would never fire → orphans). Instead it returns the pgid so the
        caller can run a SYNCHRONOUS sweep (``_sync_sigkill_sweep``) after every group
        has been SIGHUP'd. Returns ``None`` if the process is already gone.
        """
        try:
            pgid = os.getpgid(pid)  # A1: don't assume pgid == pid
            os.killpg(pgid, signal.SIGHUP)
            return pgid
        except ProcessLookupError:
            return None  # already gone

    @staticmethod
    def _sync_sigkill_sweep(pgids, grace_ms: int = _SIGKILL_GRACE_MS) -> None:
        """SYNCHRONOUS no-orphan sweep for the app-exit (close) path (D-13).

        The GLib timer used by ``_teardown_pgid`` never fires on close (the main loop
        ends with the window), so the close path SIGHUPs every group first, then calls
        this. It:
          - builds the live set (skips ``None`` from ``_teardown_pgid_now``);
          - polls in short 50ms slices up to ``grace_ms``, dropping any group whose
            ``killpg(pgid, 0)`` raises ``ProcessLookupError`` (it died on SIGHUP — the
            common case → the loop exits early when the set empties, ~0 added latency);
          - SIGKILLs every survivor after the grace window.
        It NEVER raises out of close — ``ProcessLookupError``/``OSError`` are swallowed.
        If the live set is empty up front it returns immediately (no sleep).
        """
        live = {p for p in pgids if p is not None}
        if not live:
            return  # common case: everything already gone / SIGHUP'd-and-dead
        slice_ms = 50
        waited = 0
        while live and waited < grace_ms:
            time.sleep(slice_ms / 1000.0)
            waited += slice_ms
            for pgid in list(live):
                try:
                    os.killpg(pgid, 0)  # probe: alive?
                except ProcessLookupError:
                    live.discard(pgid)  # died on SIGHUP — drop it
                except OSError:
                    live.discard(pgid)  # e.g. EPERM — can't manage it; stop tracking
            if not live:
                return  # early-exit: all gone → near-zero latency
        # Grace window elapsed: SIGKILL every survivor (true SIGHUP-ignorers).
        for pgid in live:
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # raced to death between probe and kill
            except OSError:
                pass  # never raise out of close

    def _teardown_session_terminals(self, workspace: Workspace) -> None:
        """Tear down EVERY terminal's process group of the workspace (Pitfall 3/4).

        UX pivot: the default workspace is the workspace-level pair (``workspace.terminals``);
        a user split could also attach to a repo (``workspace.repos[*].terminals``).
        Iterating ``_all_workspace_terminals`` ensures NO group is forgotten by the
        hibernate/close/exit call sites — "no orphans" is a hard acceptance bar.
        """
        for t in self._all_workspace_terminals(workspace):
            if t.pid:
                self._teardown_pgid(t.pid)

    def _teardown_session_terminals_now(self, workspace: Workspace) -> list[int]:
        """Close-path variant of ``_teardown_session_terminals`` (no GLib timer).

        SIGHUPs every terminal group of the workspace via ``_teardown_pgid_now`` and
        RETURNS the live pgids so the close handler can run one combined synchronous
        ``_sync_sigkill_sweep`` after ALL groups are SIGHUP'd (so every group gets the
        full grace window in parallel, not serially). Mirrors the hibernate/conclude
        variant exactly except for the no-timer SIGHUP + pgid return.
        """
        pgids: list[int] = []
        for t in self._all_workspace_terminals(workspace):
            if t.pid:
                pgid = self._teardown_pgid_now(t.pid)
                if pgid is not None:
                    pgids.append(pgid)
        return pgids

    def _clear_workspace_state_files(self, workspace: Workspace) -> None:
        """Delete a workspace's per-terminal state files + their map entries (Pitfall 5b).

        State files are arduis-owned RUNTIME data under the status dir
        (XDG_RUNTIME_DIR) — exempt from the D-10 never-delete rule (this is the ONLY
        deletion site in window.py; paths are composed ONLY via
        ``attention.state_file_path`` under ``self._status_dir`` so nothing outside
        it can ever be unlinked — T-04-16). Also drops the per-terminal notification
        handle so a stale Notification is not reused after teardown.
        """
        # 260616-buk (finding #6): derive paths + pop maps with the workspace's OWNING
        # project root, not the active root. At app-exit (_on_close_request) this
        # method runs for EVERY project's workspaces; the active-root _proj_term_id would
        # unlink the WRONG path and leave the background workspace's record stuck in its
        # bundle. Resolve the owner; fall back to the active root for the bootstrap /
        # not-yet-registered case (behavior unchanged for active-project workspaces).
        owner = self._project_for_workspace(workspace)
        root = owner.root if owner is not None else self._project_root
        bundle = self._bundle_for(owner) if owner is not None else self._m()
        record_by_state_file = bundle["record_by_state_file"]
        notif_by_tid = bundle["notif_by_tid"]
        for record in self._all_workspace_terminals(workspace):
            # A3: unlink + drop the SAME project-namespaced path registered at spawn.
            path = attention.state_file_path(
                self._status_dir, self._proj_term_id_for(root, record.term_id)
            )
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            except OSError:
                pass
            record_by_state_file.pop(path, None)
            notif_by_tid.pop(record.term_id, None)
            self._dialog_on_screen.discard(path)

    def _on_close_request(self, *_):
        """No-orphan teardown across ALL panes (D-13): scratch shell + sessions."""
        # Stop the ~2s RAM poll first so no source outlives the window (RAM-03).
        if self._ram_source is not None:
            GLib.source_remove(self._ram_source)
            self._ram_source = None
        # Persist the live pane layouts BEFORE the no-orphans teardown (teardown only
        # kills pids; the layout tree + records it snapshots are still intact here).
        # getattr-guarded so a bare-__new__ test window (no __init__) skips it safely.
        save_source = getattr(self, "_layout_save_source", None)
        if save_source is not None:
            GLib.source_remove(save_source)
            self._layout_save_source = None
        if getattr(self, "_layouts_json", None) is not None:
            layout_store.save_layouts(self._layouts_json, self._snapshot_layouts())
        # Cancel the status-dir watcher so no inotify source outlives the window
        # (Phase 4 / D-05).
        if self._status_monitor is not None:
            self._status_monitor.cancel()
            self._status_monitor = None
        # CLOSE PATH ONLY: the GLib SIGKILL timer never fires here (the main loop
        # ends the instant the last window closes), so a timer-based sweep would leave
        # any SIGHUP-ignoring group orphaned — violating the "no orphans" hard
        # acceptance bar. Collect every group's pgid, SIGHUP them ALL first
        # (_teardown_pgid_now), then run ONE synchronous sweep so each group gets the
        # full grace window in parallel (not serially). The hibernate/conclude paths
        # keep the timer variant (their loop stays alive). Everything that dies on
        # SIGHUP adds ~0 latency (the sweep early-exits when the live set empties).
        pgids: list[int] = []
        if self._shell_pid:
            pgids.append(self._teardown_pgid_now(self._shell_pid))
        # D-11/D-13: tear down EVERY terminal group of EVERY session of EVERY OPEN
        # PROJECT (no cross-project orphans — RESEARCH Pitfall 3). The old loop
        # iterated only the active store (self._store.all()), orphaning background
        # projects' agents. The OUTER loop over registry.all() fixes that; iterating
        # session.pid alone would still orphan split agents (Pitfall 3/4). Also delete
        # each workspace's state files so none linger past the window (Pitfall 5b).
        for project in self._registry.all():
            for session in project.store.all():
                pgids.extend(self._teardown_session_terminals_now(session))
                self._clear_workspace_state_files(session)
        # All groups SIGHUP'd → one combined synchronous SIGKILL sweep (never raises).
        self._sync_sigkill_sweep(pgids)
        # Phase 7 (D-11, D-12, CONT-05, Pitfall 7): tear down every enabled workspace's
        # container stack at app-exit as a SEPARATE loop from the killpg teardown
        # above — never conflated. Iterate ALL projects; each enabled workspace's
        # compose-down uses ITS OWN project's compose identity (per-project
        # container_state + project_name) — NEVER the active project's name for all
        # (a bug that reused one name would leak the other project's containers).
        # The downs are DETACHED fire-and-forget Popens (2026-07-03): the old
        # brief-sync run(timeout=10) froze the close ~10s per workspace. The
        # detached CLI outlives the window and finishes the teardown against the
        # daemon on its own. The hibernate path stays async.
        for project in self._registry.all():
            self._teardown_project_containers(project)
        return False  # allow the window to close

    def _sigkill_if_alive(self, pgid):
        """SIGKILL sweep after the grace period if anything survived."""
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return GLib.SOURCE_REMOVE
