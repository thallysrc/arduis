"""Contract tests for the GTK-free per-repo setup config (``arduis.repoconfig``).

Pins ENV-01 (D-01/D-02): tolerant ``[setup].commands`` read with a strict no-op default
on absent/garbage/wrong-type (criterion 1, Pitfall 7), ordered command list with
non-str/blank entries dropped, and forward-compat silent ignore of unknown sections.
Pins ENV-02 (D-04/D-05): ``setup_feed_bytes`` cd-guard + newline-joined (NOT &&-chained)
byte payload at the 0.76 feed_child floor, raw (un-shlex-wrapped) commands.
"""
from arduis import repoconfig
from arduis.repoconfig import RepoSetup, load_repo_setup, setup_feed_bytes


def _write(tmp_path, text):
    p = tmp_path / ".arduis.toml"
    p.write_text(text, encoding="utf-8")
    return str(tmp_path)


# --- load_repo_setup tolerance (criterion 1) -----------------------------------
def test_load_absent_file_noop(tmp_path):
    assert load_repo_setup(str(tmp_path)) == RepoSetup(commands=[])


def test_load_garbage_toml_noop(tmp_path):
    d = _write(tmp_path, "this is = = not toml [[[")
    assert load_repo_setup(d) == RepoSetup([])


def test_load_no_setup_table_noop(tmp_path):
    d = _write(tmp_path, '[agent]\ncommand = "x"\n')
    assert load_repo_setup(d) == RepoSetup([])


def test_load_setup_not_a_table_noop(tmp_path):
    d = _write(tmp_path, "setup = 3\n")
    assert load_repo_setup(d) == RepoSetup([])


def test_load_commands_not_a_list_noop(tmp_path):
    d = _write(tmp_path, '[setup]\ncommands = "npm install"\n')
    assert load_repo_setup(d) == RepoSetup([])


# --- load_repo_setup parsing ---------------------------------------------------
def test_load_valid_preserves_order(tmp_path):
    d = _write(
        tmp_path,
        '[setup]\ncommands = ["npm install","cp .env.example .env","npm run db:migrate"]\n',
    )
    assert load_repo_setup(d).commands == [
        "npm install",
        "cp .env.example .env",
        "npm run db:migrate",
    ]


def test_load_drops_blank_and_non_str_and_strips(tmp_path):
    d = _write(tmp_path, '[setup]\ncommands = ["  npm install  ", "", 3, true, "cp a b"]\n')
    assert load_repo_setup(d).commands == ["npm install", "cp a b"]


def test_load_empty_list(tmp_path):
    d = _write(tmp_path, "[setup]\ncommands = []\n")
    assert load_repo_setup(d) == RepoSetup([])


def test_load_unknown_keys_ignored_forward_compat(tmp_path):
    d = _write(tmp_path, '[setup]\ncommands = ["x"]\n[containers]\nfoo = 1\n')
    assert load_repo_setup(d).commands == ["x"]


# --- setup_feed_bytes (ENV-02) -------------------------------------------------
def test_feed_returns_bytes_ending_newline():
    out = setup_feed_bytes("/t/wt", ["npm install"])
    assert isinstance(out, bytes)
    assert out.endswith(b"\n")


def test_feed_exact_cd_guard_newline_joined():
    assert setup_feed_bytes("/t/wt", ["npm install", "cp .env.example .env"]) == (
        b"cd '/t/wt' &&\nnpm install\ncp .env.example .env\n"
    )


def test_feed_empty_list_is_empty_bytes():
    assert setup_feed_bytes("/t/wt", []) == b""


def test_feed_cd_target_with_space_is_quoted():
    out = setup_feed_bytes("/t/my wt", ["x"]).decode("utf-8")
    assert out.startswith("cd '/t/my wt' &&\n")


def test_feed_commands_are_raw_not_shlex_wrapped():
    out = setup_feed_bytes("/t", ["cp a b && echo $X"])
    assert b"cp a b && echo $X" in out


# --- GTK-free ------------------------------------------------------------------
def test_repoconfig_is_gtk_free():
    with open(repoconfig.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
    assert "from gi" not in text
