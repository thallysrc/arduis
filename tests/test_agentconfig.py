"""Contract tests for the GTK-free [agent] config layer (``arduis.agentconfig``).

Pins AGENT-01 (D-01/D-03): tolerant ``[agent] command`` read with a safe "claude"
default, shlex argv, feed bytes that round-trip (Pitfall 4), and the claude-family
``--continue`` resume rule.
"""
import shlex

from arduis import agentconfig
from arduis.agentconfig import (
    AgentConfig,
    agent_argv,
    agent_feed_bytes,
    load_agent_config,
    resume_feed_bytes,
)


def _write(tmp_path, text):
    p = tmp_path / "arduis.toml"
    p.write_text(text, encoding="utf-8")
    return str(p)


# --- load_agent_config ---------------------------------------------------------
def test_load_missing_path_default(tmp_path):
    assert load_agent_config(str(tmp_path / "nope.toml")) == AgentConfig(command="claude")


def test_load_command_with_args(tmp_path):
    p = _write(tmp_path, '[agent]\ncommand = "claude --model opus"\n')
    assert load_agent_config(p).command == "claude --model opus"


def test_load_empty_command_default(tmp_path):
    p = _write(tmp_path, '[agent]\ncommand = ""\n')
    assert load_agent_config(p).command == "claude"


def test_load_whitespace_command_default(tmp_path):
    p = _write(tmp_path, '[agent]\ncommand = "   "\n')
    assert load_agent_config(p).command == "claude"


def test_load_non_str_command_default(tmp_path):
    p = _write(tmp_path, "[agent]\ncommand = 123\n")
    assert load_agent_config(p).command == "claude"


def test_load_invalid_toml_default(tmp_path):
    p = _write(tmp_path, "[agent]\ncommand = \n not valid")
    assert load_agent_config(p).command == "claude"


def test_load_missing_section_default(tmp_path):
    p = _write(tmp_path, "[attention]\nidle_minutes = 5\n")
    assert load_agent_config(p).command == "claude"


# --- agent_argv ----------------------------------------------------------------
def test_argv_with_args():
    assert agent_argv("claude --model opus") == ["claude", "--model", "opus"]


def test_argv_empty_default():
    assert agent_argv("") == ["claude"]


def test_argv_single():
    assert agent_argv("aider") == ["aider"]


def test_argv_handles_quotes():
    assert agent_argv('claude --model "opus 4"') == ["claude", "--model", "opus 4"]


# --- agent_feed_bytes ----------------------------------------------------------
def test_feed_bytes_simple():
    assert agent_feed_bytes("claude") == b"claude\n"


def test_feed_bytes_endswith_newline():
    assert agent_feed_bytes("claude --model opus").endswith(b"\n")


def test_feed_bytes_round_trips():
    # The fed bytes shlex.split back to the same argv (no mangling — Pitfall 4).
    cmd = 'claude --model "opus 4"'
    feed = agent_feed_bytes(cmd).decode("utf-8").rstrip("\n")
    assert shlex.split(feed) == ["claude", "--model", "opus 4"]


def test_feed_bytes_empty_default():
    assert agent_feed_bytes("") == b"claude\n"


# --- resume_feed_bytes (D-03) --------------------------------------------------
def test_resume_claude_appends_continue():
    assert resume_feed_bytes("claude") == b"claude --continue\n"


def test_resume_claude_with_args_appends_continue():
    feed = resume_feed_bytes("claude --model opus").decode("utf-8").rstrip("\n")
    assert shlex.split(feed) == ["claude", "--model", "opus", "--continue"]
    assert resume_feed_bytes("claude --model opus").endswith(b"\n")


def test_resume_non_claude_no_continue():
    assert resume_feed_bytes("aider") == b"aider\n"


def test_resume_claude_absolute_path_appends_continue():
    feed = resume_feed_bytes("/usr/bin/claude").decode("utf-8").rstrip("\n")
    assert shlex.split(feed) == ["/usr/bin/claude", "--continue"]


# --- prompt_feed_bytes (voice agent) --------------------------------------------
def test_prompt_feed_simple():
    assert agentconfig.prompt_feed_bytes("claude", "fix the login bug") == (
        b"claude 'fix the login bug'\n"
    )


def test_prompt_feed_shell_parses_same_argv():
    prompt = "it's \"quoted\" and has $(date) `backticks` & ; | metachars"
    feed = agentconfig.prompt_feed_bytes("claude --model opus", prompt)
    line = feed.decode("utf-8")
    assert line.endswith("\n") and line.count("\n") == 1
    assert shlex.split(line) == ["claude", "--model", "opus", prompt]


def test_prompt_feed_unicode():
    feed = agentconfig.prompt_feed_bytes("claude", "corrigir acentuação çãé")
    assert shlex.split(feed.decode("utf-8")) == ["claude", "corrigir acentuação çãé"]


def test_prompt_feed_empty_command_degrades_to_claude():
    feed = agentconfig.prompt_feed_bytes("", "hello")
    assert shlex.split(feed.decode("utf-8")) == ["claude", "hello"]


# --- GTK-free ------------------------------------------------------------------
def test_agentconfig_is_gtk_free():
    with open(agentconfig.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
    assert "from gi" not in text
