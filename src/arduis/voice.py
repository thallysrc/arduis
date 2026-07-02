"""GTK-free voice-agent state machine (idle → recording → transcribing → idle).

Command-emitting like ``attention.next_scan_action``: every input method returns a
list of command tuples the controller executes — ``("start_capture",)``,
``("request_stop",)``, ``("transcribe",)``, ``("run_prompt", text)``,
``("toast", msg)``. The machine never reads a clock or touches Gst/Gio; callers pass
integer-millisecond timestamps, so every transition is unit-testable.

End-of-utterance rule (D-V2): stop once speech WAS heard (any RMS ≥ threshold) and
the mic then stayed quiet for ``silence_ms``. Quiet-from-the-start never auto-stops
(the user may be thinking) — only the manual toggle or the ``max_ms`` cap ends those.
``request_stop`` is emitted at most once per session; the state stays "recording"
until ``capture_done()`` because the WAV is only valid after wavenc handles EOS.
"""
from __future__ import annotations


def normalize_transcript(text: str) -> str:
    """Collapse ALL whitespace (whisper segments may span lines) to single spaces."""
    return " ".join(text.split())


class VoiceMachine:
    def __init__(
        self,
        silence_ms: int = 1500,
        threshold_db: float = -40.0,
        max_ms: int = 60000,
    ) -> None:
        self._silence_ms = silence_ms
        self._threshold_db = threshold_db
        self._max_ms = max_ms
        self.state = "idle"
        self._started_ms = 0
        self._last_loud_ms: int | None = None  # None until speech is heard
        self._stop_requested = False

    def toggle(self, now_ms: int) -> list[tuple]:
        if self.state == "idle":
            self.state = "recording"
            self._started_ms = now_ms
            self._last_loud_ms = None
            self._stop_requested = False
            return [("start_capture",)]
        if self.state == "recording":
            return self._request_stop()
        return []  # transcribing: ignore

    def level(self, rms_db: float, now_ms: int) -> list[tuple]:
        if self.state != "recording" or self._stop_requested:
            return []
        if now_ms - self._started_ms >= self._max_ms:
            return self._request_stop()
        if rms_db >= self._threshold_db:
            self._last_loud_ms = now_ms
            return []
        if (
            self._last_loud_ms is not None
            and now_ms - self._last_loud_ms >= self._silence_ms
        ):
            return self._request_stop()
        return []

    def capture_done(self) -> list[tuple]:
        if self.state != "recording":
            return []
        self.state = "transcribing"
        return [("transcribe",)]

    def transcript(self, text: str) -> list[tuple]:
        if self.state != "transcribing":
            return []
        self.state = "idle"
        normalized = normalize_transcript(text)
        if not normalized:
            return [("toast", "Nothing recognized — try again")]
        return [("run_prompt", normalized)]

    def error(self, msg: str) -> list[tuple]:
        self.state = "idle"
        return [("toast", msg)]

    def _request_stop(self) -> list[tuple]:
        if self._stop_requested:
            return []
        self._stop_requested = True
        return [("request_stop",)]
