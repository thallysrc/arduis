"""GTK-free trust gate primitives for repo-supplied setup (criterion 4, D-07/D-09/D-10).

``.arduis.toml`` is committed in the repo, so its ``[setup]`` commands are arbitrary code
the repo author chose — running them on worktree-add is a supply-chain RCE surface. This
module supplies the security primitives Plan 02's gate consumes; it never RUNS commands —
it only HASHES and records authorization.

Model (the direnv-allow content-bound grant):
  * ``setup_hash(commands)`` is a sha256 over the ordered, newline-joined command list. ANY
    edit/add/remove/REORDER changes the hash, so a ``git pull`` that swaps in a different
    ``[setup]`` re-prompts — trust is bound to the CONTENT, not the repo path alone (D-07).
  * Trust identity (``repo_id``) is an OPAQUE string key — Plan 02 passes
    ``os.path.realpath(<project_root>/<repo_name>)``; this module never computes realpath
    itself (keeps it pure/testable/GTK-free) (D-09).
  * The trust list lives at ``~/.config/arduis/trusted_setups.toml`` as one ``[trusted]``
    table ``{ "<repo_realpath>" = "<sha256hex>" }``. Read is fail-closed and tolerant
    (missing/garbage/wrong-type -> ``{}`` -> re-prompt EVERYTHING — never fail-open). Write
    is atomic best-effort (tmp + ``os.replace``, mirroring ``appconfig.write_theme``) so a
    torn write can never corrupt the security record (D-10).

GTK-free: imports no ``gi`` (the arduis *config discipline — fully unit-testable headless).
"""
from __future__ import annotations

import hashlib
import os
import tempfile
import tomllib


def setup_hash(commands: list[str]) -> str:
    """sha256 hex of the ordered, newline-joined command list (D-07).

    Stable for identical lists; changes on any edit/add/remove/REORDER (order is
    semantically meaningful for setup). Hashes the RAW commands (NOT the cd-guarded feed)
    so the trust key is the repo's authored intent, independent of where the worktree lands.
    """
    return hashlib.sha256("\n".join(commands).encode("utf-8")).hexdigest()


def load_trusted(path: str) -> dict[str, str]:
    """Return ``{repo_id: trusted_hash}`` from the trust list (D-10).

    Fail-closed: a missing file / invalid TOML / ``[trusted]`` not a table -> ``{}``
    (re-prompt everything). Non-str values are dropped (a forged/garbage entry never
    grants trust). Mirrors ``agentconfig.load_agent_config``'s tolerance.
    """
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    trusted = data.get("trusted")
    if not isinstance(trusted, dict):
        return {}
    return {k: v for k, v in trusted.items() if isinstance(v, str)}


def is_trusted(path: str, repo_id: str, commands_hash: str) -> bool:
    """True only for an EXACT ``(repo_id, commands_hash)`` pair in the trust list.

    A changed setup (new hash) or an untrusted repo returns False -> Plan 02 re-prompts.
    Fail-closed: an unreadable list makes everything untrusted.
    """
    return load_trusted(path).get(repo_id) == commands_hash


def _esc(s: str) -> str:
    """Escape a string for a double-quoted TOML value/key (mirror appconfig._fmt_scalar)."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _serialize_trusted(trusted: dict[str, str]) -> str:
    """Serialize ``{repo_id: hash}`` to a single ``[trusted]`` table.

    Repo-path keys contain ``/``/``.``/``-`` so each is emitted as a QUOTED string key
    (``"<path>" = "<hash>"``); a separate local serializer (NOT ``appconfig._serialize``,
    which imposes a fixed user-config section order) keeps this file self-contained.
    """
    lines = [f'"{_esc(k)}" = "{_esc(v)}"' for k, v in trusted.items()]
    return "[trusted]\n" + "\n".join(lines) + "\n"


def record_trust(path: str, repo_id: str, commands_hash: str) -> None:
    """Atomically persist ``trusted[repo_id] = commands_hash``, preserving prior entries (D-10).

    Read-merges the existing list (so trusting repo B never drops repo A), overwrites a
    changed hash for the same repo (the re-prompt-then-trust path), re-serializes the WHOLE
    ``[trusted]`` table, and writes via tmp + ``os.replace`` (makedirs parent, swallow
    ``OSError``) — the ``appconfig.write_theme`` idiom. Best-effort: a failed write is
    swallowed because a fail-closed read simply re-prompts anyway (never fail-open).
    """
    trusted = load_trusted(path)  # read-merge (preserve prior entries)
    trusted[repo_id] = commands_hash
    text = _serialize_trusted(trusted)
    try:
        d = os.path.dirname(path) or "."
        os.makedirs(d, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=d, prefix=".arduis-trust-")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
            os.replace(tmp, path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
    except OSError:
        pass  # best-effort (a fail-closed read re-prompts anyway)
