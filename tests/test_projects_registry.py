"""Contract tests for the GTK-free Project + ProjectRegistry spine (D-01/D-02/D-07; A3).

Pins the multi-project model the 03.4 corrective rests on, ALL GTK-free (imports NO
``gi``): a ``Project`` owns its root + member_repos + its OWN ``SessionStore`` (D-02 —
stores are never shared) + a switch-back ``last_active_workspace``; a ``ProjectRegistry``
tracks open projects keyed by absolute root with a single active pointer (add / get /
all / active / set_active / remove); ``ensure_project`` is the D-07 launch-autoregister
helper (idempotent per root); and ``project_term_id`` (A3) derives a stable per-project
discriminator so two projects with same-named branches never collide on the global
attention status-file path — and the result still survives ``attention.sanitize_term_id``
unchanged (no new unsafe chars, no surviving ``..``).
"""
from arduis import project as project_mod
from arduis.attention import sanitize_term_id
from arduis.project import (
    Project,
    ProjectRegistry,
    ensure_project,
    project_term_id,
)
from arduis.session import SessionStore, Workspace


def _workspace(workspace_id: str = "feat", branch: str = "feat") -> Workspace:
    return Workspace(workspace_id=workspace_id, branch=branch, workspace_dir=f"/tmp/x/{workspace_id}")


# --- Project ------------------------------------------------------------------
def test_project_holds_root_members_and_own_store():
    # D-01: a Project encapsulates root + member_repos + its own SessionStore.
    p = Project(root="/x/Livon-Saude", member_repos=["backend", "frontend"])
    assert p.name == "Livon-Saude"  # basename
    assert p.member_repos == ["backend", "frontend"]
    assert isinstance(p.store, SessionStore)
    assert p.last_active_workspace is None


def test_two_projects_have_independent_stores():
    # D-02: each project owns its OWN store; adding to A never leaks into B.
    a = Project(root="/x/A")
    b = Project(root="/x/B")
    a.store.add(_workspace("feat"))
    assert len(a.store.all()) == 1
    assert b.store.all() == []  # not shared


# --- ProjectRegistry ----------------------------------------------------------
def test_registry_add_get_active_setactive_remove():
    reg = ProjectRegistry()
    p = Project(root="/x/A")
    reg.add(p)
    assert reg.get("/x/A") is p
    assert reg.all() == [p]
    # active is None until explicitly set
    assert reg.active() is None
    reg.set_active("/x/A")
    assert reg.active() is p
    # remove drops it AND clears the active pointer (it was active)
    reg.remove("/x/A")
    assert reg.get("/x/A") is None
    assert reg.all() == []
    assert reg.active() is None


def test_registry_keyed_by_root_dedup():
    # Adding two Projects with the SAME root replaces, never duplicates.
    reg = ProjectRegistry()
    reg.add(Project(root="/x/A"))
    reg.add(Project(root="/x/A"))
    assert len(reg.all()) == 1


def test_registry_all_preserves_insertion_order():
    reg = ProjectRegistry()
    reg.add(Project(root="/x/A"))
    reg.add(Project(root="/x/B"))
    reg.add(Project(root="/x/C"))
    assert [p.root for p in reg.all()] == ["/x/A", "/x/B", "/x/C"]


def test_remove_non_active_keeps_active_pointer():
    reg = ProjectRegistry()
    a = Project(root="/x/A")
    b = Project(root="/x/B")
    reg.add(a)
    reg.add(b)
    reg.set_active("/x/A")
    reg.remove("/x/B")  # removing the NON-active one
    assert reg.active() is a  # active pointer untouched


# --- ensure_project (D-07 launch autoregister, registry-level) ----------------
def test_launch_autoregister_selects_active():
    reg = ProjectRegistry()
    # NEW root -> registered and returned
    p = ensure_project(reg, "/x/A", ["backend"])
    assert reg.get("/x/A") is p
    assert p.member_repos == ["backend"]
    # SAME root again -> returns the SAME instance, no duplicate
    again = ensure_project(reg, "/x/A", ["backend", "frontend"])
    assert again is p
    assert len(reg.all()) == 1


# --- project_term_id (A3 namespacing) -----------------------------------------
def test_term_id_namespaced_per_project():
    # Two projects whose basename collides ("Foo") AND share a branch-derived
    # term_id ("feat:t0") must yield DISTINCT namespaced ids (no status-file bleed).
    a = project_term_id("/a/Foo", "feat:t0")
    b = project_term_id("/b/Foo", "feat:t0")
    assert a != b
    # Stable across calls for the same (root, term_id).
    assert project_term_id("/a/Foo", "feat:t0") == a
    # The original term_id is still present in the namespaced result.
    assert a.endswith("feat:t0")
    # The result is allowlist-safe: sanitize_term_id leaves it UNCHANGED (no
    # new unsafe chars introduced, no surviving "..").
    assert sanitize_term_id(a) == a
    assert sanitize_term_id(b) == b
    assert ".." not in a


def test_term_id_discriminator_is_hex():
    # The discriminator is an 8-hex sha1 prefix joined by ":".
    out = project_term_id("/some/root", "feat:t0")
    disc, _, rest = out.partition(":")
    assert len(disc) == 8
    assert all(c in "0123456789abcdef" for c in disc)
    assert rest == "feat:t0"


# --- GTK-free guard -----------------------------------------------------------
def test_project_module_is_gtk_free():
    with open(project_mod.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
    assert "from gi" not in text
