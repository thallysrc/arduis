"""voice.py — VoiceMachine (idle→recording→transcribing→idle) + normalize_transcript.

The machine is command-emitting (like attention.next_scan_action): pure logic, the
controller executes the returned command tuples. Times are integer milliseconds
supplied by the caller — the machine never reads a clock.
"""
from arduis.voice import VoiceMachine, normalize_transcript


def make(silence_ms=1500, threshold_db=-40.0, max_ms=60000):
    return VoiceMachine(
        silence_ms=silence_ms, threshold_db=threshold_db, max_ms=max_ms
    )


# --- normalize_transcript --------------------------------------------------------
def test_normalize_collapses_all_whitespace():
    assert normalize_transcript("  Fix\nthe\t login\r\n  bug  ") == "Fix the login bug"


def test_normalize_empty_and_blank():
    assert normalize_transcript("") == ""
    assert normalize_transcript(" \n\t ") == ""


# --- happy path ------------------------------------------------------------------
def test_toggle_from_idle_starts_capture():
    m = make()
    assert m.state == "idle"
    assert m.toggle(now_ms=0) == [("start_capture",)]
    assert m.state == "recording"


def test_silence_after_speech_requests_stop():
    m = make(silence_ms=1500)
    m.toggle(now_ms=0)
    assert m.level(-20.0, now_ms=100) == []          # speech
    assert m.level(-55.0, now_ms=1000) == []          # quiet, only 900ms
    assert m.level(-55.0, now_ms=1700) == [("request_stop",)]  # quiet ≥1500ms
    assert m.state == "recording"  # still recording until capture_done (EOS)


def test_quiet_before_any_speech_never_stops():
    m = make(silence_ms=1500)
    m.toggle(now_ms=0)
    assert m.level(-60.0, now_ms=5000) == []  # never spoke: keep waiting
    assert m.state == "recording"


def test_speech_resets_silence_window():
    m = make(silence_ms=1500)
    m.toggle(now_ms=0)
    m.level(-20.0, now_ms=100)
    m.level(-55.0, now_ms=1000)
    m.level(-20.0, now_ms=1400)   # spoke again
    assert m.level(-55.0, now_ms=2800) == []  # only 1400ms quiet since last speech
    assert m.level(-55.0, now_ms=2950) == [("request_stop",)]


def test_capture_done_moves_to_transcribing():
    m = make()
    m.toggle(now_ms=0)
    m.level(-20.0, now_ms=100)
    m.level(-55.0, now_ms=1700)
    assert m.capture_done() == [("transcribe",)]
    assert m.state == "transcribing"


def test_transcript_runs_prompt_and_returns_to_idle():
    m = make()
    m.toggle(now_ms=0)
    m.capture_done()
    cmds = m.transcript("  Fix the\nlogin bug ")
    assert cmds == [("run_prompt", "Fix the login bug")]
    assert m.state == "idle"


def test_empty_transcript_toasts_instead_of_running():
    m = make()
    m.toggle(now_ms=0)
    m.capture_done()
    cmds = m.transcript("  \n ")
    assert len(cmds) == 1 and cmds[0][0] == "toast"
    assert m.state == "idle"


# --- manual stop / caps ------------------------------------------------------------
def test_manual_toggle_stops_even_without_speech():
    m = make()
    m.toggle(now_ms=0)
    assert m.toggle(now_ms=500) == [("request_stop",)]
    assert m.capture_done() == [("transcribe",)]  # still transcribes


def test_max_duration_cap_requests_stop():
    m = make(max_ms=60000)
    m.toggle(now_ms=0)
    m.level(-20.0, now_ms=100)          # speaking continuously
    assert m.level(-20.0, now_ms=59999) == []
    assert m.level(-20.0, now_ms=60000) == [("request_stop",)]


def test_stop_requested_only_once():
    m = make(silence_ms=1500)
    m.toggle(now_ms=0)
    m.level(-20.0, now_ms=100)
    assert m.level(-55.0, now_ms=1700) == [("request_stop",)]
    assert m.level(-55.0, now_ms=1800) == []   # no double stop
    assert m.toggle(now_ms=1900) == []          # manual toggle after auto-stop: no-op


def test_toggle_during_transcribing_ignored():
    m = make()
    m.toggle(now_ms=0)
    m.toggle(now_ms=100)
    m.capture_done()
    assert m.state == "transcribing"
    assert m.toggle(now_ms=200) == []
    assert m.state == "transcribing"


def test_level_in_idle_ignored():
    m = make()
    assert m.level(-20.0, now_ms=100) == []
    assert m.state == "idle"


# --- errors ------------------------------------------------------------------------
def test_error_resets_to_idle_with_toast():
    m = make()
    m.toggle(now_ms=0)
    cmds = m.error("gst broke")
    assert cmds == [("toast", "gst broke")]
    assert m.state == "idle"


def test_error_during_transcribing_resets():
    m = make()
    m.toggle(now_ms=0)
    m.toggle(now_ms=100)
    m.capture_done()
    m.error("whisper missing")
    assert m.state == "idle"
    # machine is reusable after an error
    assert m.toggle(now_ms=1000) == [("start_capture",)]


def test_fresh_session_state_reset_after_run():
    m = make(silence_ms=1500)
    m.toggle(now_ms=0)
    m.level(-20.0, now_ms=100)
    m.level(-55.0, now_ms=1700)
    m.capture_done()
    m.transcript("first")
    # second session: old speech/silence state must not leak
    m.toggle(now_ms=10000)
    assert m.level(-60.0, now_ms=12000) == []  # no speech yet this session


# --- GTK-free ------------------------------------------------------------------
def test_voice_is_gtk_free():
    from arduis import voice

    with open(voice.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
    assert "from gi" not in text
