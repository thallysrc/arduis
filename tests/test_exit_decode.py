"""Tests for raw waitstatus decoding (D-12): exit 0 -> 0, 42 -> 42, SIGINT -> -2."""
import os
import signal

from arduis.exit_status import decode_exit


def _raw_status_for_exit(code: int) -> int:
    pid = os.fork()
    if pid == 0:  # child
        os._exit(code)
    _, status = os.waitpid(pid, 0)
    return status


def _raw_status_for_signal(signum: int) -> int:
    pid = os.fork()
    if pid == 0:  # child
        os.kill(os.getpid(), signum)
        os._exit(0)  # unreachable if the signal lands
    _, status = os.waitpid(pid, 0)
    return status


def test_exit_zero():
    assert decode_exit(_raw_status_for_exit(0)) == 0


def test_exit_42():
    assert decode_exit(_raw_status_for_exit(42)) == 42


def test_sigint_decodes_to_negative_two():
    assert decode_exit(_raw_status_for_signal(signal.SIGINT)) == -2
