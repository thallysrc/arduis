"""GTK-free per-repo ``.arduis.toml`` [setup] reader + shell-feed bytes (ENV-01/ENV-02).

This is the PER-REPO config (committed in the repo, hand-edited), DISTINCT from the
user-level ``~/.config/arduis/arduis.toml``. It clones ``agentconfig.load_agent_config``'s
tolerance: a missing file, invalid TOML, a wrong-typed ``[setup]``/``commands`` key, or
empty/blank/non-str entries all yield ``RepoSetup(commands=[])`` — a strict no-op identical
to today's behavior (D-01/D-02, criterion 1, Pitfall 7).

Forward-compat (D-02): ONLY ``[setup].commands`` is read this phase; unknown sections/keys
(e.g. Phase 7's ``[containers]``) are ignored SILENTLY — never validate-and-reject.

``setup_feed_bytes`` builds the bytes fed into the live ``zsh -l -i`` shell (D-04/D-05):
a ``cd <dir> &&`` DIRECTORY GUARD (the only ``&&``), then each command on its OWN line
(newline-joined, NEVER ``&&``-chained, so one failure does not hide the rest), then a
trailing newline. Bytes at the VTE 0.76 ``feed_child`` floor. The commands are the user's
RAW shell lines (``&&``/``$VAR``/``cp a b`` are intentional) — only the ``cd`` TARGET is
single-quoted (Pitfall 1/5/6). GTK-free: imports no ``gi`` (the arduis *config discipline).
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field


@dataclass
class RepoSetup:
    commands: list[str] = field(default_factory=list)  # ordered; [] = no setup / no gate


def load_repo_setup(repo_dir: str) -> RepoSetup:
    """Read ``[setup].commands`` from ``<repo_dir>/.arduis.toml`` (ENV-01, D-01/D-02).

    Missing file / invalid TOML / ``[setup]`` not a table / ``commands`` not a list ->
    ``RepoSetup([])`` -> NO setup runs -> behaves exactly as today (criterion 1, Pitfall 7).
    Otherwise keeps only non-empty stripped string entries, in order; non-str / blank /
    whitespace entries are dropped. Unknown sections/keys are ignored silently (D-02).
    """
    path = os.path.join(repo_dir, ".arduis.toml")
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return RepoSetup()
    section = data.get("setup")
    if not isinstance(section, dict):
        return RepoSetup()
    raw = section.get("commands")
    if not isinstance(raw, list):
        return RepoSetup()
    cmds = [c.strip() for c in raw if isinstance(c, str) and c.strip()]
    return RepoSetup(commands=cmds)


def setup_feed_bytes(worktree_dir: str, commands: list[str]) -> bytes:
    """Bytes fed into the worktree's login shell to run setup (ENV-02, D-04/D-05).

    Shape for ``worktree_dir="/t/wt"``, ``commands=["npm install","cp .env.example .env"]``::

        b"cd '/t/wt' &&\\nnpm install\\ncp .env.example .env\\n"

    The ``cd`` directory guard uses ``&&`` so a failed ``cd`` never runs commands in the
    wrong dir; the command LIST is newline-joined (each runs + shows regardless of a prior
    failure — debuggable, criterion 2). The ``cd`` target is ALWAYS single-quoted (POSIX
    single-quote escaping) so the documented ``cd '<dir>' &&`` byte contract holds for every
    path — ``shlex.quote`` only quotes when it detects a special char, which would emit a
    bare ``cd /t/wt &&`` for ordinary paths and break the exact contract. The commands
    themselves are fed RAW (Pitfall 1/5/6). An empty list returns ``b""`` (defensive — the
    caller guards on ``commands == []``).
    """
    if not commands:
        return b""
    quoted = "'" + worktree_dir.replace("'", "'\\''") + "'"
    guard = "cd " + quoted + " &&"
    return (guard + "\n" + "\n".join(commands) + "\n").encode("utf-8")
