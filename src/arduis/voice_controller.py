"""Voice-agent controller — Gst capture + whisper.cpp transcription (gi module).

The second gi-importing SERVICE module after ``git_service``: it owns the GStreamer
mic pipeline and the whisper subprocess, executing the command tuples emitted by
the GTK-free ``voice.VoiceMachine``. window.py only wires the mic button /
keybinding to ``toggle()`` and renders the three callbacks:

- ``on_state(state)``      — "idle" / "recording" / "transcribing" (button CSS)
- ``on_transcript(text)``  — normalized non-empty prompt → run it in a new pane
- ``on_error(msg)``        — toast (includes "nothing recognized")

Concurrency (CLAUDE.md): everything rides the GLib main loop — the Gst bus uses a
signal watch (callbacks on the main loop), whisper runs via ``run_git_async``
(``Gio.Subprocess`` + ``communicate_utf8_async``), and the max-duration backstop is
a ``GLib.timeout_add_seconds``. NO threads, NO asyncio.

Capture stop discipline (D-V2): stopping sends EOS so wavenc finalizes the RIFF
header; the pipeline is torn down only on the bus ``message::eos`` — a direct
NULL-state jump would truncate the WAV.
"""
from __future__ import annotations

import os
import re

import gi

gi.require_version("Gtk", "4.0")
from gi.repository import GLib  # noqa: E402

from arduis import voiceconfig  # noqa: E402
from arduis.git_service import run_git_async  # noqa: E402
from arduis.host_runner import HostRunner  # noqa: E402
from arduis.voice import VoiceMachine  # noqa: E402
from arduis.voiceconfig import VoiceConfig  # noqa: E402

_PIPELINE_TMPL = (
    "autoaudiosrc ! audioconvert ! audioresample "
    "! audio/x-raw,format=S16LE,rate=16000,channels=1 "
    '! level interval=100000000 ! wavenc ! filesink location="{path}"'
)


def _now_ms() -> int:
    return GLib.get_monotonic_time() // 1000


class VoiceController:
    def __init__(
        self,
        config: VoiceConfig,
        runner: HostRunner,
        on_state,
        on_transcript,
        on_error,
        work_dir: str | None = None,
    ) -> None:
        self._config = config
        self._runner = runner
        self._on_state = on_state
        self._on_transcript = on_transcript
        self._on_error = on_error
        # Temp WAV/JSON live in the runtime dir (mirrors attention.status_dir's
        # preference); ``work_dir`` is injectable for tests.
        self._work_dir = work_dir or os.path.join(
            GLib.get_user_runtime_dir(), "arduis", "voice"
        )
        self._machine = VoiceMachine(
            silence_ms=config.silence_ms,
            threshold_db=config.silence_threshold_db,
            max_ms=config.max_seconds * 1000,
        )
        self._gst = None            # lazy-imported Gst module (None until used)
        self._gst_ok: bool | None = None
        self._pipeline = None
        self._bus = None
        self._wav_path: str | None = None
        self._rec_seq = 0
        self._cap_source: int | None = None

    @property
    def state(self) -> str:
        return self._machine.state

    def toggle(self) -> None:
        """Mic button / C-Space v: start listening, or stop-and-transcribe."""
        self._execute(self._machine.toggle(_now_ms()))

    # --- command execution -----------------------------------------------------

    def _execute(self, cmds: list[tuple]) -> None:
        for cmd in cmds:
            kind = cmd[0]
            if kind == "start_capture":
                self._start_capture()
            elif kind == "request_stop":
                self._request_stop()
            elif kind == "transcribe":
                self._transcribe()
            elif kind == "run_prompt":
                self._on_transcript(cmd[1])
            elif kind == "toast":
                self._on_error(cmd[1])
        self._on_state(self._machine.state)

    # --- capture (GStreamer) ----------------------------------------------------

    def _ensure_gst(self) -> bool:
        if self._gst_ok is not None:
            return self._gst_ok
        try:
            gi.require_version("Gst", "1.0")
            from gi.repository import Gst  # noqa: PLC0415 (lazy: only when the mic is used)

            ok, _argv = Gst.init_check(None)
            self._gst = Gst if ok else None
            self._gst_ok = bool(ok)
        except (ImportError, ValueError):
            self._gst_ok = False
        return self._gst_ok

    def _start_capture(self) -> None:
        if not self._ensure_gst():
            self._execute(
                self._machine.error(
                    "GStreamer indisponível — instale gstreamer1.0-plugins-good"
                )
            )
            return
        Gst = self._gst
        os.makedirs(self._work_dir, exist_ok=True)
        self._rec_seq += 1
        self._wav_path = os.path.join(self._work_dir, f"rec-{self._rec_seq}.wav")
        try:
            self._pipeline = Gst.parse_launch(
                _PIPELINE_TMPL.format(path=self._wav_path)
            )
        except GLib.Error as exc:
            self._execute(self._machine.error(f"Falha no pipeline de áudio: {exc}"))
            return
        self._bus = self._pipeline.get_bus()
        self._bus.add_signal_watch()
        self._bus.connect("message::element", self._on_bus_element)
        self._bus.connect("message::eos", self._on_bus_eos)
        self._bus.connect("message::error", self._on_bus_error)
        self._pipeline.set_state(Gst.State.PLAYING)
        # Backstop for the max-duration cap: level messages normally enforce it,
        # but if none arrive this one-shot forces the stop path (machine.toggle in
        # "recording" = request_stop with the same only-once bookkeeping).
        self._cap_source = GLib.timeout_add_seconds(
            self._config.max_seconds + 2, self._cap_timeout
        )

    def _cap_timeout(self) -> bool:
        self._cap_source = None
        if self._machine.state == "recording":
            self._execute(self._machine.toggle(_now_ms()))
        return GLib.SOURCE_REMOVE

    def _on_bus_element(self, _bus, msg) -> None:
        s = msg.get_structure()
        if s is None or s.get_name() != "level":
            return
        rms = self._level_rms_db(s)
        if rms is not None:
            self._execute(self._machine.level(rms, _now_ms()))

    @staticmethod
    def _level_rms_db(structure) -> float | None:
        """Max per-channel RMS dB from a level message; None when unreadable.

        ``get_value("rms")`` returns the channel array on current PyGObject;
        older bindings can't introspect GstValueArray, so fall back to parsing
        ``to_string()`` (the documented workaround).
        """
        try:
            values = structure.get_value("rms")
            if values:
                return max(float(v) for v in values)
        except Exception:  # noqa: BLE001 — binding-specific failure, use fallback
            pass
        try:
            text = structure.to_string()
            match = re.search(r"rms=\(double\)?[{<]([^}>]*)[}>]", text)
            if match:
                nums = [float(x) for x in match.group(1).split(",")]
                if nums:
                    return max(nums)
        except (ValueError, TypeError):
            pass
        return None

    def _request_stop(self) -> None:
        if self._pipeline is None:
            return
        Gst = self._gst
        # EOS lets wavenc finalize the RIFF header; teardown happens on message::eos.
        self._pipeline.send_event(Gst.Event.new_eos())

    def _on_bus_eos(self, _bus, _msg) -> None:
        self._teardown_pipeline()
        self._execute(self._machine.capture_done())

    def _on_bus_error(self, _bus, msg) -> None:
        err, _debug = msg.parse_error()
        self._teardown_pipeline()
        self._cleanup_temps()
        self._execute(self._machine.error(f"Erro de áudio: {err.message}"))

    def _teardown_pipeline(self) -> None:
        if self._cap_source is not None:
            GLib.source_remove(self._cap_source)
            self._cap_source = None
        if self._bus is not None:
            self._bus.remove_signal_watch()
            self._bus = None
        if self._pipeline is not None:
            self._pipeline.set_state(self._gst.State.NULL)
            self._pipeline = None

    # --- transcription (whisper.cpp via Gio.Subprocess) --------------------------

    def _transcribe(self) -> None:
        wav = self._wav_path
        if wav is None or not os.path.exists(wav):
            self._execute(self._machine.error("Gravação não encontrada"))
            return
        model = os.path.expanduser(self._config.model)
        if not os.path.exists(model):
            self._cleanup_temps()
            self._execute(
                self._machine.error(
                    f"Modelo whisper não encontrado: {model} — ajuste [voice] model"
                )
            )
            return
        out_base = wav[: -len(".wav")] if wav.endswith(".wav") else wav
        argv = voiceconfig.transcribe_argv(self._config, wav, out_base)
        run_git_async(argv, self._make_whisper_done(out_base), runner=self._runner)

    def _make_whisper_done(self, out_base: str):
        def _done(exit_status: int, _out: str, err: str) -> None:
            json_path = out_base + ".json"
            try:
                if exit_status != 0:
                    detail = (err or "").strip().splitlines()
                    tail = detail[-1] if detail else f"exit {exit_status}"
                    self._execute(self._machine.error(f"whisper falhou: {tail}"))
                    return
                try:
                    with open(json_path, encoding="utf-8") as fh:
                        text = voiceconfig.parse_transcript_json(fh.read())
                except OSError:
                    text = ""
                self._execute(self._machine.transcript(text))
            finally:
                self._cleanup_temps()

        return _done

    def _cleanup_temps(self) -> None:
        wav = self._wav_path
        self._wav_path = None
        if wav is None:
            return
        for path in (wav, wav[: -len(".wav")] + ".json" if wav.endswith(".wav") else wav + ".json"):
            try:
                os.unlink(path)
            except OSError:
                pass
