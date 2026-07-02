"""Contract tests for the GTK-free per-workspace container state (``arduis.containerstate``).

Pins CONT-04 (D-07): a tolerant no-op read (a corrupt/absent file == "not isolated", never
crashes workspace creation — T-07-05), an atomic uncorruptible write (tmp + os.replace —
T-07-06), and a full-fidelity round-trip of the COMPOSE_PROJECT_NAME + on/off flag +
resolved base->host port map (so badges/URLs stay stable across restarts — criterion 3).
Plus CONT-03 (D-06): the ``[containers].port_offset`` user-config read defaulting to 1000.

The ``ports`` shape matches ``compose.assign_ports``'s output (Plan 01):
``{service: [{"base": int, "host": int, "target": int, "host_ip": str | None}]}``.
"""
import tomllib

from arduis import containerstate
from arduis.containerstate import (
    ContainerState,
    load_container_state,
    read_port_offset,
    state_path,
    write_container_state,
)


def _write_state_file(workspace_dir, text):
    p = workspace_dir / "arduis.container.toml"
    p.write_text(text, encoding="utf-8")
    return str(workspace_dir)


def _write_config(tmp_path, text, name="arduis.toml"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


# --- load_container_state tolerant read (CONT-04 no-op default, T-07-05) -------
def test_load_missing_file_is_no_op(tmp_path):
    assert load_container_state(str(tmp_path)) == ContainerState(
        project_name="", enabled=False, ports={}
    )


def test_load_garbage_toml_is_no_op(tmp_path):
    d = _write_state_file(tmp_path, "this is = = not toml [[[")
    assert load_container_state(d) == ContainerState()


def test_load_no_container_table_is_no_op(tmp_path):
    d = _write_state_file(tmp_path, "[other]\nx = 1\n")
    assert load_container_state(d) == ContainerState()


def test_load_container_not_a_table_is_no_op(tmp_path):
    # [container] present but as a scalar (wrong type) -> default.
    d = _write_state_file(tmp_path, 'container = "oops"\n')
    assert load_container_state(d) == ContainerState()


def test_load_name_and_enabled_only_no_ports(tmp_path):
    d = _write_state_file(
        tmp_path, '[container]\nproject_name = "arduis-feat-x"\nenabled = true\n'
    )
    state = load_container_state(d)
    assert state.project_name == "arduis-feat-x"
    assert state.enabled is True
    assert state.ports == {}


def test_load_wrong_typed_name_and_enabled_degrade(tmp_path):
    d = _write_state_file(tmp_path, "[container]\nproject_name = 123\nenabled = 5\n")
    state = load_container_state(d)
    assert state.project_name == ""
    assert state.enabled is False


# --- round-trip fidelity (criterion 3, CONT-03/04) -----------------------------
def test_full_state_round_trips_verbatim(tmp_path):
    state = ContainerState(
        "arduis-feat-x",
        True,
        {
            "web": [
                {"base": 8080, "host": 9080, "target": 80, "host_ip": None},
                {"base": 9000, "host": 10000, "target": 9000, "host_ip": "127.0.0.1"},
            ],
            "db": [{"base": 5432, "host": 6432, "target": 5432, "host_ip": None}],
        },
    )
    write_container_state(str(tmp_path), state)
    loaded = load_container_state(str(tmp_path))
    assert loaded == state
    # the host_ip-pinned multi-port web entry survives in full
    assert loaded.ports["web"][1] == {
        "base": 9000,
        "host": 10000,
        "target": 9000,
        "host_ip": "127.0.0.1",
    }


def test_enabled_false_round_trips_as_bool(tmp_path):
    write_container_state(
        str(tmp_path), ContainerState("arduis-x", False, {})
    )
    loaded = load_container_state(str(tmp_path))
    assert loaded.enabled is False  # a real bool, not the string "false"
    assert isinstance(loaded.enabled, bool)


def test_empty_state_round_trips(tmp_path):
    write_container_state(str(tmp_path), ContainerState())
    assert load_container_state(str(tmp_path)) == ContainerState()


# --- atomicity / valid TOML / resilience (T-07-06) -----------------------------
def test_written_file_is_valid_toml_with_container_table(tmp_path):
    write_container_state(
        str(tmp_path),
        ContainerState("arduis-x", True, {"web": [{"base": 80, "host": 90, "target": 80, "host_ip": None}]}),
    )
    with open(state_path(str(tmp_path)), "rb") as fh:
        data = tomllib.load(fh)
    assert "container" in data
    assert data["container"]["project_name"] == "arduis-x"
    assert data["container"]["enabled"] is True


def test_write_creates_parent_dir(tmp_path):
    sub = tmp_path / "sub"  # does not exist yet
    write_container_state(str(sub), ContainerState("arduis-x", True, {}))
    assert load_container_state(str(sub)) == ContainerState("arduis-x", True, {})


def test_write_best_effort_swallows_os_replace_error(tmp_path, monkeypatch):
    def _boom(*a, **k):
        raise OSError("no replace")

    monkeypatch.setattr(containerstate.os, "replace", _boom)
    # must NOT raise even though the atomic replace fails
    write_container_state(str(tmp_path), ContainerState("arduis-x", True, {}))


def test_write_leaves_no_tmp_file(tmp_path):
    write_container_state(str(tmp_path), ContainerState("arduis-x", True, {}))
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "arduis.container.toml"]
    assert leftovers == []


# --- defensive port-row dropping (T-07-05) -------------------------------------
def test_load_drops_malformed_port_row_keeps_good(tmp_path):
    # one good row, one type-broken row (host is a string), one missing service.
    text = (
        '[container]\n'
        'project_name = "arduis-x"\n'
        'enabled = true\n\n'
        '[[container.ports]]\n'
        'service = "web"\n'
        'base = 8080\n'
        'host = 9080\n'
        'target = 80\n\n'
        '[[container.ports]]\n'
        'service = "web"\n'
        'base = 9000\n'
        'host = "bad"\n'
        'target = 9000\n\n'
        '[[container.ports]]\n'
        'base = 5432\n'
        'host = 6432\n'
        'target = 5432\n'
    )
    d = _write_state_file(tmp_path, text)
    state = load_container_state(d)  # must not raise
    assert state.ports == {
        "web": [{"base": 8080, "host": 9080, "target": 80, "host_ip": None}]
    }


def test_load_ports_not_a_list_is_dropped(tmp_path):
    d = _write_state_file(
        tmp_path, '[container]\nproject_name = "arduis-x"\nenabled = true\nports = 5\n'
    )
    state = load_container_state(d)
    assert state.project_name == "arduis-x"
    assert state.ports == {}


# --- read_port_offset (CONT-03, D-06, T-07-07) ---------------------------------
def test_read_port_offset_missing_default(tmp_path):
    assert read_port_offset(str(tmp_path / "nope.toml")) == 1000


def test_read_port_offset_garbage_default(tmp_path):
    p = _write_config(tmp_path, "not = = valid [[[")
    assert read_port_offset(p) == 1000


def test_read_port_offset_value(tmp_path):
    p = _write_config(tmp_path, "[containers]\nport_offset = 2000\n")
    assert read_port_offset(p) == 2000


def test_read_port_offset_wrong_type_default(tmp_path):
    p = _write_config(tmp_path, '[containers]\nport_offset = "x"\n')
    assert read_port_offset(p) == 1000


def test_read_port_offset_bool_is_not_int_default(tmp_path):
    # bool is an int subclass; a forged boolean must degrade to the default.
    p = _write_config(tmp_path, "[containers]\nport_offset = true\n")
    assert read_port_offset(p) == 1000


def test_read_port_offset_no_containers_section_default(tmp_path):
    p = _write_config(tmp_path, "[other]\nx = 1\n")
    assert read_port_offset(p) == 1000


# --- GTK-free (the discipline) -------------------------------------------------
def test_containerstate_is_gtk_free():
    with open(containerstate.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
    assert "from gi" not in text
