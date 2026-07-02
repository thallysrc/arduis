"""GTK-free [keys] config layer over keymap.DEFAULT_KEYMAP (UI-01, D-04/D-05).

A configurable prefix + a flat char->action-name bindings map merged over the
defaults. CLOSED action set — an unrecognized action name is DROPPED (the key keeps
its default), mirroring keymap.dispatch returning None for unknown keys, so no action
is ever fabricated from config. The capture-phase machine in window.py is untouched.
"""
from __future__ import annotations

from arduis.keymap import DEFAULT_KEYMAP

_DEFAULT_PREFIX = ("space", "ctrl")
_SUPPORTED_MODS = {"ctrl"}  # the machine only checks CONTROL_MASK today

# action NAME -> action TUPLE (the closed set, UI-01 D-04). Any name not here is
# dropped on merge so config can never fabricate an unintended action (T-05-02).
_ACTIONS: dict[str, tuple] = {
    "focus_left": ("focus_dir", "left"),
    "focus_right": ("focus_dir", "right"),
    "focus_up": ("focus_dir", "up"),
    "focus_down": ("focus_dir", "down"),
    "worktree_next": ("worktree", "next"),
    "worktree_prev": ("worktree", "prev"),
    "split_v": ("split", "v"),
    "split_h": ("split", "h"),
    "zoom": ("zoom", None),
    "refeed_agent": ("refeed", None),
    "voice_toggle": ("voice", None),
}


def resolve_prefix(prefix: str | None) -> tuple[str, str]:
    """Parse a ``"<mod>+<key>"`` prefix string into ``(keyval, mods)`` (D-04/D-05).

    ``"ctrl+space"`` -> ``("space","ctrl")``; ``"ctrl+b"`` -> ``("b","ctrl")``.
    Case-insensitive. Mods are limited to ``{"ctrl"}`` (the machine only checks
    CONTROL_MASK today). Garbage / None / no ``+`` / empty key / unsupported mod ->
    the default ``("space","ctrl")``.
    """
    if not isinstance(prefix, str) or "+" not in prefix:
        return _DEFAULT_PREFIX
    mod, _, key = prefix.lower().partition("+")
    if mod not in _SUPPORTED_MODS or not key:
        return _DEFAULT_PREFIX
    return (key, mod)


def resolve_keymap(bindings: dict | None) -> dict[str, tuple]:
    """Merge a flat char->action-name ``[keys.bindings]`` map over DEFAULT_KEYMAP.

    Starts from a COPY of the defaults. For each ``key, action_name``: keep only
    when ``key`` is a single-char str AND ``action_name`` is a recognized name in the
    closed set; otherwise skip (the key keeps its default). A None/empty bindings
    map returns a copy of the defaults unchanged (D-05).
    """
    table = dict(DEFAULT_KEYMAP)
    for key, action_name in (bindings or {}).items():
        if not isinstance(key, str) or len(key) != 1:
            continue
        action = _ACTIONS.get(action_name) if isinstance(action_name, str) else None
        if action is not None:
            table[key] = action
    return table
