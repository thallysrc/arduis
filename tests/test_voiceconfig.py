"""voiceconfig.py — [voice] TOML load, whisper argv builder, transcript JSON parse."""
import json
import os

from arduis import voiceconfig
from arduis.voiceconfig import (
    VoiceConfig,
    load_voice_config,
    parse_transcript_json,
    transcribe_argv,
)


# --- load_voice_config -----------------------------------------------------------
def test_load_missing_file_gives_defaults(tmp_path):
    cfg = load_voice_config(str(tmp_path / "nope.toml"))
    assert cfg == VoiceConfig()
    assert cfg.command == "whisper-cli"
    assert cfg.model == "~/.local/share/arduis/models/ggml-base.en.bin"
    assert cfg.language == "en"
    assert cfg.silence_ms == 1500
    assert cfg.silence_threshold_db == -40.0
    assert cfg.max_seconds == 60
    assert cfg.history_max == 200


def test_load_full_section(tmp_path):
    p = tmp_path / "arduis.toml"
    p.write_text(
        "[voice]\n"
        'command = "whisper-cli -t 8"\n'
        'model = "/models/ggml-small.en.bin"\n'
        'language = "pt"\n'
        "silence_ms = 900\n"
        "silence_threshold_db = -35.5\n"
        "max_seconds = 30\n"
        "history_max = 50\n",
        encoding="utf-8",
    )
    cfg = load_voice_config(str(p))
    assert cfg.command == "whisper-cli -t 8"
    assert cfg.model == "/models/ggml-small.en.bin"
    assert cfg.language == "pt"
    assert cfg.silence_ms == 900
    assert cfg.silence_threshold_db == -35.5
    assert cfg.max_seconds == 30
    assert cfg.history_max == 50


def test_load_bad_types_degrade_per_key(tmp_path):
    p = tmp_path / "arduis.toml"
    p.write_text(
        "[voice]\n"
        "command = 42\n"
        'model = ""\n'
        "silence_ms = -5\n"
        'max_seconds = "long"\n'
        "history_max = 0\n",
        encoding="utf-8",
    )
    cfg = load_voice_config(str(p))
    assert cfg == VoiceConfig()  # every bad key falls back to its default


def test_load_invalid_toml_gives_defaults(tmp_path):
    p = tmp_path / "arduis.toml"
    p.write_text("[voice\nbroken", encoding="utf-8")
    assert load_voice_config(str(p)) == VoiceConfig()


def test_load_missing_section_gives_defaults(tmp_path):
    p = tmp_path / "arduis.toml"
    p.write_text('[agent]\ncommand = "claude"\n', encoding="utf-8")
    assert load_voice_config(str(p)) == VoiceConfig()


def test_int_accepted_for_float_threshold(tmp_path):
    p = tmp_path / "arduis.toml"
    p.write_text("[voice]\nsilence_threshold_db = -30\n", encoding="utf-8")
    assert load_voice_config(str(p)).silence_threshold_db == -30.0


# --- transcribe_argv -------------------------------------------------------------
def test_transcribe_argv_shape():
    cfg = VoiceConfig(command="whisper-cli", model="/m/base.bin")
    argv = transcribe_argv(cfg, "/run/voice/rec.wav", "/run/voice/rec")
    assert argv == [
        "whisper-cli",
        "-m", "/m/base.bin",
        "-l", "en",
        "-f", "/run/voice/rec.wav",
        "-oj", "-of", "/run/voice/rec",
        "-np",
    ]


def test_transcribe_argv_command_with_embedded_flags():
    cfg = VoiceConfig(command="whisper-cli -t 8", model="/m/base.bin")
    argv = transcribe_argv(cfg, "/w.wav", "/w")
    assert argv[:3] == ["whisper-cli", "-t", "8"]


def test_transcribe_argv_expands_user_in_model():
    cfg = VoiceConfig(model="~/models/base.bin")
    argv = transcribe_argv(cfg, "/w.wav", "/w")
    m = argv[argv.index("-m") + 1]
    assert m == os.path.expanduser("~/models/base.bin")
    assert "~" not in m


def test_transcribe_argv_empty_command_degrades_to_default():
    cfg = VoiceConfig(command="   ")
    argv = transcribe_argv(cfg, "/w.wav", "/w")
    assert argv[0] == "whisper-cli"


# --- parse_transcript_json -------------------------------------------------------
def test_parse_joins_segments():
    doc = {
        "transcription": [
            {"text": " Fix the login bug"},
            {"text": " and add a test."},
        ]
    }
    assert parse_transcript_json(json.dumps(doc)) == "Fix the login bug and add a test."


def test_parse_garbage_gives_empty():
    assert parse_transcript_json("{nope") == ""
    assert parse_transcript_json(json.dumps([1, 2])) == ""
    assert parse_transcript_json(json.dumps({"transcription": "x"})) == ""


def test_parse_skips_bad_segments():
    doc = {"transcription": [{"text": "ok"}, {"no": 1}, "str", {"text": 5}]}
    assert parse_transcript_json(json.dumps(doc)) == "ok"


# --- GTK-free ------------------------------------------------------------------
def test_voiceconfig_is_gtk_free():
    with open(voiceconfig.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
    assert "from gi" not in text
