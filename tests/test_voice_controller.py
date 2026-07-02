"""voice_controller — transcription path (Gio.Subprocess + fake whisper-cli).

The Gst capture pipeline needs a real microphone and is exercised in manual UAT;
these tests drive the TRANSCRIBE side end-to-end with a fake ``whisper-cli`` script
that writes the JSON file whisper.cpp would, so the subprocess plumbing, JSON
parsing, temp cleanup and error surfacing are all real (no mocks of our own code).
"""
import json
import os
import stat

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

from arduis.host_runner import HostRunner  # noqa: E402
from arduis.voice_controller import VoiceController  # noqa: E402
from arduis.voiceconfig import VoiceConfig  # noqa: E402


def _fake_whisper(tmp_path, text="hello world", exit_code=0):
    """A stand-in whisper-cli: writes <out_base>.json like the real -oj flag."""
    script = tmp_path / "fake-whisper"
    doc = json.dumps({"transcription": [{"text": text}]})
    script.write_text(
        "#!/bin/sh\n"
        '# find the -of argument -> write its .json\n'
        "while [ $# -gt 0 ]; do\n"
        '  if [ "$1" = "-of" ]; then base="$2"; fi\n'
        "  shift\n"
        "done\n"
        f"printf '%s' '{doc}' > \"$base.json\"\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)


def _controller(tmp_path, command, model_exists=True):
    model = tmp_path / "model.bin"
    if model_exists:
        model.write_bytes(b"x")
    events = {"state": [], "transcript": [], "error": []}
    cfg = VoiceConfig(command=command, model=str(model))
    ctrl = VoiceController(
        cfg,
        HostRunner(),
        on_state=lambda s: events["state"].append(s),
        on_transcript=lambda t: events["transcript"].append(t),
        on_error=lambda m: events["error"].append(m),
        work_dir=str(tmp_path / "work"),
    )
    return ctrl, events


def _pump(pred, timeout_s=10.0):
    ctx = GLib.MainContext.default()
    deadline = GLib.get_monotonic_time() + int(timeout_s * 1e6)
    while GLib.get_monotonic_time() < deadline:
        ctx.iteration(False)
        if pred():
            return True
    return False


def _simulate_finished_capture(ctrl, tmp_path):
    """Put the machine in 'recording' + a WAV on disk, then finish the capture."""
    ctrl._machine.toggle(0)          # idle -> recording (no pipeline: machine only)
    ctrl._machine.toggle(1)          # manual stop request
    wav = tmp_path / "work" / "rec.wav"
    os.makedirs(wav.parent, exist_ok=True)
    wav.write_bytes(b"RIFFxxxxWAVE")
    ctrl._wav_path = str(wav)
    ctrl._execute(ctrl._machine.capture_done())   # -> ("transcribe",)
    return wav


def test_transcribe_success_emits_transcript_and_cleans_up(tmp_path):
    ctrl, events = _controller(tmp_path, _fake_whisper(tmp_path, "Fix the login bug"))
    wav = _simulate_finished_capture(ctrl, tmp_path)

    assert _pump(lambda: events["transcript"] or events["error"])
    assert events["transcript"] == ["Fix the login bug"]
    assert events["error"] == []
    assert ctrl._machine.state == "idle"
    assert not wav.exists()                      # temp wav removed
    assert not wav.with_suffix(".json").exists()  # temp json removed


def test_missing_model_errors_before_spawn(tmp_path):
    ctrl, events = _controller(
        tmp_path, _fake_whisper(tmp_path), model_exists=False
    )
    _simulate_finished_capture(ctrl, tmp_path)

    assert _pump(lambda: events["error"])
    assert events["transcript"] == []
    assert "model" in events["error"][0].lower()
    assert ctrl._machine.state == "idle"


def test_missing_binary_surfaces_error(tmp_path):
    ctrl, events = _controller(tmp_path, str(tmp_path / "no-such-whisper"))
    _simulate_finished_capture(ctrl, tmp_path)

    assert _pump(lambda: events["error"])
    assert events["transcript"] == []
    assert ctrl._machine.state == "idle"


def test_whisper_failure_exit_code_surfaces_error(tmp_path):
    ctrl, events = _controller(tmp_path, _fake_whisper(tmp_path, exit_code=3))
    _simulate_finished_capture(ctrl, tmp_path)

    assert _pump(lambda: events["error"])
    assert events["transcript"] == []
    assert ctrl._machine.state == "idle"


def test_empty_transcription_toasts_not_runs(tmp_path):
    ctrl, events = _controller(tmp_path, _fake_whisper(tmp_path, text="  "))
    _simulate_finished_capture(ctrl, tmp_path)

    assert _pump(lambda: events["error"])
    assert events["transcript"] == []          # nothing recognized -> no run
    assert ctrl._machine.state == "idle"


def test_state_callback_reports_transitions(tmp_path):
    ctrl, events = _controller(tmp_path, _fake_whisper(tmp_path, "ok"))
    _simulate_finished_capture(ctrl, tmp_path)
    assert _pump(lambda: events["transcript"])
    # transcribing was reported, and we ended back at idle
    assert "transcribing" in events["state"]
    assert events["state"][-1] == "idle"
