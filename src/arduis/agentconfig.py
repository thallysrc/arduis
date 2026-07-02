"""GTK-free [agent] config: command -> argv -> feed bytes (AGENT-01, D-01/D-03).

The agent is a SHELL COMMAND fed into the durable zsh (never a spawn_async argv) —
that is why Ctrl+C drops to the live shell. shlex makes args safe (CLAUDE.md);
feed_child needs bytes at the 0.76 floor. Mirrors attention.load_config's tolerant
read with a safe default ("claude").
"""
from __future__ import annotations

import os
import shlex
import tomllib
from dataclasses import dataclass

_DEFAULT = "claude"


@dataclass
class AgentConfig:
    command: str = _DEFAULT


def load_agent_config(path: str) -> AgentConfig:
    """Read ``[agent] command`` from arduis.toml (D-01), stdlib tomllib.

    A missing file, invalid TOML, a non-str/empty/whitespace command yields the
    safe default ``"claude"`` (mirrors attention.load_config; Pitfall 4).
    """
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return AgentConfig()
    section = data.get("agent")
    if not isinstance(section, dict):
        return AgentConfig()
    cmd = section.get("command")
    if not isinstance(cmd, str) or not cmd.strip():
        return AgentConfig()
    return AgentConfig(command=cmd.strip())


def agent_argv(command: str) -> list[str]:
    """shlex-split the command into argv (CLAUDE.md: never a shell string).

    An empty/whitespace command degrades to ``["claude"]`` (Pitfall 4).
    """
    argv = shlex.split(command or "")
    return argv or [_DEFAULT]


def agent_feed_bytes(command: str) -> bytes:
    """The bytes fed into the durable shell to launch the agent (ends in ``\\n``).

    Re-serialized via ``shlex.join`` so the live shell parses the SAME argv with no
    metachar injection (Pitfall 4); bytes for the 0.76 ``feed_child``.
    """
    return (shlex.join(agent_argv(command)) + "\n").encode("utf-8")


def prompt_feed_bytes(command: str, prompt: str) -> bytes:
    """Feed ``<agent argv> '<prompt>'`` into the durable shell (voice agent).

    The spoken prompt becomes ONE extra argv element; ``shlex.join`` keeps quotes,
    ``$(...)`` and other metachars inert so the shell passes the prompt literally to
    the agent (Pitfall 4). Ends in ``\\n`` — exactly one line is fed.
    """
    argv = agent_argv(command) + [prompt]
    return (shlex.join(argv) + "\n").encode("utf-8")


def resume_feed_bytes(command: str) -> bytes:
    """D-03: claude-family argv[0] -> append ``--continue``; else feed the bare command.

    ``--continue`` is a claude flag, so a non-claude agent (basename(argv[0]) !=
    "claude") resumes with its plain command. Same shlex.join + ``\\n`` + encode.
    """
    argv = agent_argv(command)
    if os.path.basename(argv[0]) == "claude":
        argv = argv + ["--continue"]
    return (shlex.join(argv) + "\n").encode("utf-8")
