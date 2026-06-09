"""HostRunner seam — single funnel for host command execution.

On native (v1) builds this is a no-op: it returns argv/env unchanged so the
caller spawns the host command directly. The Flatpak branch is the single
re-enable point for the deferred v2 channel (DIST-01) and MUST stay
unreachable in v1 — it raises ``NotImplementedError`` (threat T-01-03).
"""
from __future__ import annotations

# v1 is native-only. Flipping this is the single v2 (DIST-01) re-enable point.
_FLATPAK = False


class HostRunner:
    """Single seam for executing host commands. No-op on native builds."""

    def wrap_argv(self, argv: list[str]) -> list[str]:
        if _FLATPAK:
            # v2 (DIST-01): return ["/usr/bin/flatpak-spawn", "--host", *argv]
            raise NotImplementedError("Flatpak channel is v2 (DIST-01)")
        return list(argv)

    def wrap_env(self, env: list[str]) -> list[str]:
        if _FLATPAK:
            # v2 (DIST-01): prepend --env=K=V flags before the command instead
            raise NotImplementedError("Flatpak channel is v2 (DIST-01)")
        return list(env)
