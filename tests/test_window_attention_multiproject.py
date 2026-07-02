"""Multi-project attention surfacing regression (260616-buk, code-review #4/#6).

With two projects "both alive" (03.4), a BACKGROUND project's agent entering WAITING
is the exact signal arduis exists to surface — yet ``_on_status_event`` and ``_poll_ram``
were scoped to the ACTIVE project's bundle only, so the background event was dropped (no
status flip, no desktop notification, no RAM poll/re-read). Finding #6: ``_proj_term_id``
always used the active root, so a background workspace's status-file path was derived wrong.

These are GTK-free: a bare window via ``ArduisWindow.__new__`` with ``_display=None`` and
only the attrs the exercised methods touch (mirrors ``test_window_projects.py``). Two
registered projects (active + background), each a Workspace with an agent ``TerminalRecord``,
per-project bundles via ``_bundle_for``. No display, no Vte, no real status dir writes.
"""
import arduis.window as W
from arduis import attention, resource_monitor
from arduis.attention import AgentStatus, AttentionConfig, StateDoc
from arduis.project import Project, ProjectRegistry
from arduis.session import RepoCheckout, SessionState, SessionStore, Workspace, TerminalRecord


def _agent_workspace(branch, *, pgid=None, status=None):
    """An ACTIVE workspace whose workspace-level agent terminal carries ``status``/``pgid``."""
    agent = TerminalRecord(f"{branch}:t0", "agent", pgid=pgid, status=status)
    shell = TerminalRecord(f"{branch}:t1", "shell")
    return Workspace(
        workspace_id=branch,
        branch=branch,
        workspace_dir=f"/workspaces/{branch}",
        repos=[RepoCheckout(repo_name="backend",
                            worktree_dir=f"/workspaces/{branch}/backend", branch=branch)],
        state=SessionState.ACTIVE,
        terminals=[agent, shell],
    )


def _project_with(root, workspace):
    store = SessionStore()
    store.add(workspace)
    return Project(root=root, member_repos=["backend"], store=store)


def _bare_attention_window(tmp_path):
    """A bare window with a 2-project registry; active=projA, background=projB."""
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    win._registry = ProjectRegistry()
    win._bootstrap = Project(root="")
    win._display = None
    win._degraded = False
    win._att_config = AttentionConfig()  # all defaults (auto_suspend OFF, idle 10m)
    win._status_dir = str(tmp_path)
    win._footer_label = None

    workspace_a = _agent_workspace("alpha")
    workspace_b = _agent_workspace("beta")
    proj_a = _project_with("/projA", workspace_a)
    proj_b = _project_with("/projB", workspace_b)
    win._registry.add(proj_a)
    win._registry.add(proj_b)
    win._registry.set_active("/projA")
    return win, proj_a, workspace_a, proj_b, workspace_b


def _register_agent(win, proj, workspace):
    """Register the workspace's agent record in proj's bundle at its OWNING-root path
    (mirrors the spawn registration: _proj_term_id_for(proj.root, term_id))."""
    agent = workspace.terminals[0]
    path = attention.state_file_path(
        win._status_dir, win._proj_term_id_for(proj.root, agent.term_id)
    )
    win._bundle_for(proj)["record_by_state_file"][path] = (workspace, agent)
    return agent, path


# --- 1. Routing: a background project's status event flips ITS record ----------
def test_status_event_routes_to_background_project_record(tmp_path, monkeypatch):
    """``_on_status_event`` must find a BACKGROUND project's record by searching all
    bundles — the active-only lookup would drop the event (finding #4)."""
    win, proj_a, _ta, proj_b, workspace_b = _bare_attention_window(tmp_path)
    agent_b, path_b = _register_agent(win, proj_b, workspace_b)
    agent_b.status = AgentStatus.RUNNING.value  # had an opinion already

    # The state file (background project) just transitioned to WAITING.
    monkeypatch.setattr(
        attention, "read_state",
        lambda p: StateDoc(state="waiting", ts=1.0, event="", message="approve?", pid=None),
    )
    # Routing is the concern here (not the libnotify side effect, which test 2 covers
    # and which would hit a real daemon headless): record the notify call instead.
    notified = []
    monkeypatch.setattr(win, "_maybe_notify",
                        lambda *a, **k: notified.append(a[0].workspace_id))

    fake = type("F", (), {"get_path": lambda self: path_b})()
    win._on_status_event(None, fake, None, None)

    # The BACKGROUND record flipped to waiting; the active project's record untouched.
    assert agent_b.status == AgentStatus.WAITING.value
    assert proj_a.store.get("alpha").terminals[0].status is None
    # The event was routed (apply → notify) for the BACKGROUND workspace, not dropped.
    assert notified == ["beta"]


# --- 2. Notify fires for a BACKGROUND waiting transition -----------------------
def test_notify_fires_for_background_workspace(tmp_path, monkeypatch):
    """A →waiting transition on a BACKGROUND workspace notifies (window unfocused) and
    dedups in the OWNING bundle's notif store. Degrades gracefully if no libnotify."""
    win, _pa, _ta, proj_b, workspace_b = _bare_attention_window(tmp_path)
    agent_b, _path = _register_agent(win, proj_b, workspace_b)
    win.props = type("P", (), {"is_active": False})()  # unfocused → should notify

    doc = StateDoc(state="waiting", ts=1.0, event="", message="approve?", pid=None)

    if not W._HAS_NOTIFY:
        # No notification daemon binding in this env: assert no crash + record still
        # gets updated by _apply_state_file (the notify call is a guarded no-op).
        win._maybe_notify(workspace_b, agent_b, None, AgentStatus.WAITING.value, doc)
        # Drive the full apply path too to prove it does not raise.
        monkeypatch.setattr(attention, "read_state", lambda p: doc)
        win._apply_state_file(workspace_b, agent_b, _path)
        assert agent_b.status == AgentStatus.WAITING.value
        return

    # libnotify present: stub the Notification object so we capture show() without a
    # real daemon, and assert the handle lands in the BACKGROUND bundle's store.
    shown = {"count": 0}

    class _FakeNotif:
        def __init__(self, *a):
            pass

        def update(self, *a):
            pass

        def show(self):
            shown["count"] += 1

    monkeypatch.setattr(W.Notify, "Notification",
                        type("N", (), {"new": staticmethod(lambda *a: _FakeNotif())}))

    win._maybe_notify(workspace_b, agent_b, None, AgentStatus.WAITING.value, doc)

    assert shown["count"] == 1  # the notification fired for the background workspace
    notif_b = win._bundle_for(proj_b)["notif_by_tid"]
    assert agent_b.term_id in notif_b  # deduped in the OWNING bundle, not the active one
    assert agent_b.term_id not in win._bundle_for(win._registry.get("/projA"))["notif_by_tid"]


# --- 3. Namespace (#6): owning root gives a distinct, stable status path -------
def test_proj_term_id_for_namespaces_per_owning_root(tmp_path):
    """``_proj_term_id_for`` discriminates by the EXPLICIT owning root (finding #6):
    two projects' same-named term never share a status-file path."""
    win, proj_a, _ta, proj_b, _tb = _bare_attention_window(tmp_path)
    term_id = "alpha:t0"

    id_a = win._proj_term_id_for(proj_a.root, term_id)
    id_b = win._proj_term_id_for(proj_b.root, term_id)
    assert id_a != id_b  # distinct discriminators
    assert win._proj_term_id_for(proj_a.root, term_id) == id_a  # stable

    # The poll/clear paths use the owning root → the path string carries projB's disc.
    from arduis.project import project_term_id
    disc_b = project_term_id(proj_b.root, term_id)
    path_b = attention.state_file_path(win._status_dir, win._proj_term_id_for(proj_b.root, term_id))
    assert disc_b.split(":")[0] in path_b  # projB's discriminator is in the derived path
    # Falsy root → bare term_id (degenerate launch, unchanged).
    assert win._proj_term_id_for(None, term_id) == term_id


# --- 4. Poll covers ALL projects (background re-read + RAM write) --------------
def test_poll_ram_covers_background_project(tmp_path, monkeypatch):
    """``_poll_ram`` must poll + re-read EVERY project's workspaces. A background workspace with
    a live pgid gets its rss_kb written and its registered state file re-read
    (status updated) — proving the loop covered the background project (finding #4)."""
    win, _pa, _ta, proj_b, workspace_b = _bare_attention_window(tmp_path)
    agent_b = workspace_b.terminals[0]
    agent_b.pgid = 4242            # a live group → RAM polled
    agent_b.status = AgentStatus.RUNNING.value  # has an opinion → re-read on the tick
    _reg_agent, path_b = _register_agent(win, proj_b, workspace_b)

    win.props = type("P", (), {"is_active": False})()
    monkeypatch.setattr(resource_monitor, "group_rss_kb", lambda pgid: 123456)
    # The background state file re-read returns a WAITING doc (the FileMonitor missed it).
    monkeypatch.setattr(
        attention, "read_state",
        lambda p: StateDoc(state="waiting", ts=1.0, event="", message="m", pid=None),
    )
    # Concern: the loop covers the background project (RAM + re-read). The libnotify
    # side effect is test 2's job (and hits a real daemon headless) — stub it out.
    monkeypatch.setattr(win, "_maybe_notify", lambda *a, **k: None)
    # The 4242 pgid is not a live group here; keep the waiting status (not aged to
    # ENDED by the dead-pid sweep) so the assertion targets the re-read, not liveness.
    monkeypatch.setattr(win, "_pid_alive", lambda record, doc: True)

    assert win._poll_ram() is W.GLib.SOURCE_CONTINUE

    assert agent_b.rss_kb == 123456                  # background RAM was polled
    assert agent_b.status == AgentStatus.WAITING.value  # background state file re-read ran


# --- 5. Reconcile-on-switch is automatic (dot wiring is correct) ---------------
def test_dot_reconciles_waiting_when_active():
    """Once a background record is WAITING, the dot path (used by _refresh_status_ui
    via _rebuild_sidebar on switch) colors it waiting when the workspace is active (D-08)."""
    win = W.ArduisWindow.__new__(W.ArduisWindow)
    # A light, real check that the WAITING→css wiring _refresh_status_ui depends on
    # is correct: an active WAITING agent maps to the orange dot class.
    assert win._dot_css_for(AgentStatus.WAITING, True) == "arduis-dot-waiting"
    # And an inactive (hibernated/background-on-switch-before-active) workspace is grey.
    assert win._dot_css_for(AgentStatus.WAITING, False) == "arduis-dot-hibernated"
