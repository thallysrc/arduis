"""GTK-free [voice] config: whisper.cpp argv + transcript parse (voice agent).

Mirrors ``agentconfig``'s tolerant read: every key is optional and a bad type falls
back to that key's default, never raising. The transcriber is a SHELL COMMAND turned
into argv via shlex (CLAUDE.md: argv lists, never shell strings) and run through
``HostRunner`` + ``Gio.Subprocess`` by the controller. Output is requested as a JSON
file (``-oj -of <base>``) because whisper-cli's stdout format varies across versions;
``transcription[].text`` is the stable contract.
"""
from __future__ import annotations

import json
import os
import shlex
import tomllib
from dataclasses import dataclass

_DEFAULT_COMMAND = "whisper-cli"
_DEFAULT_MODEL = "~/.local/share/arduis/models/ggml-base.en.bin"


@dataclass
class VoiceConfig:
    command: str = _DEFAULT_COMMAND
    model: str = _DEFAULT_MODEL
    language: str = "en"
    silence_ms: int = 1500
    silence_threshold_db: float = -40.0
    max_seconds: int = 60
    history_max: int = 200


def _str(section: dict, key: str, default: str) -> str:
    val = section.get(key)
    if isinstance(val, str) and val.strip():
        return val.strip()
    return default


def _pos_int(section: dict, key: str, default: int) -> int:
    val = section.get(key)
    if isinstance(val, int) and not isinstance(val, bool) and val > 0:
        return val
    return default


def _float(section: dict, key: str, default: float) -> float:
    val = section.get(key)
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    return default


def load_voice_config(path: str) -> VoiceConfig:
    """Read ``[voice]`` from arduis.toml; each bad/missing key -> its default."""
    try:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return VoiceConfig()
    section = data.get("voice")
    if not isinstance(section, dict):
        return VoiceConfig()
    d = VoiceConfig()
    return VoiceConfig(
        command=_str(section, "command", d.command),
        model=_str(section, "model", d.model),
        language=_str(section, "language", d.language),
        silence_ms=_pos_int(section, "silence_ms", d.silence_ms),
        silence_threshold_db=_float(
            section, "silence_threshold_db", d.silence_threshold_db
        ),
        max_seconds=_pos_int(section, "max_seconds", d.max_seconds),
        history_max=_pos_int(section, "history_max", d.history_max),
    )


def transcribe_argv(cfg: VoiceConfig, wav_path: str, out_base: str) -> list[str]:
    """argv to transcribe ``wav_path`` -> ``<out_base>.json`` (whisper-cli flags).

    ``command`` may embed flags (shlex-split); an empty command degrades to the
    default. ``-np`` keeps stderr quiet; the transcript is read from the JSON file,
    not stdout.
    """
    argv = shlex.split(cfg.command or "") or [_DEFAULT_COMMAND]
    return argv + [
        "-m", os.path.expanduser(cfg.model),
        "-l", cfg.language,
        "-f", wav_path,
        "-oj", "-of", out_base,
        "-np",
    ]


def parse_transcript_json(text: str) -> str:
    """Join ``transcription[].text`` segments into one line; garbage -> ``""``."""
    try:
        data = json.loads(text)
    except ValueError:
        return ""
    if not isinstance(data, dict):
        return ""
    segments = data.get("transcription")
    if not isinstance(segments, list):
        return ""
    parts: list[str] = []
    for seg in segments:
        if isinstance(seg, dict) and isinstance(seg.get("text"), str):
            parts.append(seg["text"])
    return " ".join(p.strip() for p in parts if p.strip())
