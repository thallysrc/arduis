"""Raw waitstatus decode wrapper (D-12).

VTE's ``child-exited`` passes a RAW waitpid status, not an already-decoded
exit code. ``os.waitstatus_to_exitcode`` maps it: a normal exit yields the
exit code; a signal-terminated child yields ``-signum``.
"""
import os


def decode_exit(status: int) -> int:
    """Decode a RAW waitpid status (as VTE child-exited passes). <0 == -signum."""
    return os.waitstatus_to_exitcode(status)
