# Voice Agent for arduis

## Context

The user wants a handsfree voice loop in arduis: toggle the mic, speak a prompt in English, and arduis transcribes it, **immediately** creates a new terminal pane in the current project/workspace, and runs `claude "<prompt>"` in it. Every transcription is saved to a persistent history list so any past prompt can be re-run with one click.

Confirmed product decisions:
- Lives **inside arduis** (mic toggle in the header + history popover) — no separate app, no IPC.
- STT = **local whisper.cpp** (`whisper-cli`), shelled out via the existing HostRunner/`Gio.Subprocess` pattern. No Python ML deps.
- Trigger = **toggle**: press mic (or `C-Space v`) → record → silence (1.5s) or manual toggle-off or 60s cap → transcribe → **run directly** (handsfree, no confirmation).
- Runs in a **new terminal pane in the current workspace** (no new worktree per prompt in v1; no wake word; English only).
- Audio capture = **GStreamer via PyGObject** (main-loop native, no threads — house rule), using the `level` element for silence detection. Verified: Gst 1.24.2 imports on this machine; `pw-record` alternative rejected (would need raw PCM reading on the main loop).

## Architecture

Three new **GTK-free pure modules** (unit-testable, no `gi` imports) + one gi-importing controller, so `window.py` grows only ~120 lines:

| Module | Responsibility |
|--------|---------------|
| `src/arduis/voice.py` | `VoiceMachine` state machine (idle → recording → transcribing → idle) emitting command tuples, silence/max-cap logic, `normalize_transcript()` |
| `src/arduis/voiceconfig.py` | `[voice]` TOML load, `transcribe_argv()`, `parse_transcript_json()` |
| `src/arduis/voice_store.py` | History JSON persistence (atomic writes, `projects_store.py` pattern) |
| `src/arduis/voice_controller.py` | Gst pipeline + bus watch + `Gio.Subprocess` transcription orchestration; callbacks `on_state/on_transcript/on_error` |

GTK glue in `window.py`: mic ToggleButton + history MenuButton/Popover in the header, `_run_voice_prompt()`, keybinding wiring.

### Key mechanics

**Audio pipeline** (built with `Gst.parse_launch`; no user input enters the string):
```
autoaudiosrc ! audioconvert ! audioresample
  ! audio/x-raw,format=S16LE,rate=16000,channels=1
  ! level interval=100000000 ! wavenc ! filesink location=$XDG_RUNTIME_DIR/arduis/voice/rec-<ts>.wav
```
`level` posts `message::element` every 100ms with RMS dB → fed to `VoiceMachine.level(rms_db, now_ms)`. End-of-utterance: speech was seen AND quiet (< −40dB) for `silence_ms` (1500). Stop = send EOS so wavenc finalizes the WAV header; only tear down the pipeline (`set_state(NULL)`) on the bus `message::eos`.

**Transcription**: `Gio.Subprocess` + `communicate_utf8_async` (the `git_service.run_git_async` pattern, argv through `HostRunner`). Argv: `shlex.split(cfg.command) + ["-m", model, "-l", "en", "-f", wav, "-oj", "-of", base, "-np"]` — parse the JSON output file (`transcription[].text`), not stdout (varies across whisper.cpp versions). Missing model/binary → toast, feature degrades gracefully. Temp wav/json deleted after parse.

**Run prompt** — reuse the existing split machinery end-to-end. `_split_active_pane` (window.py:4291) already handles terminal factory, layout split, empty-canvas recovery, `TerminalRecord`, and `_spawn_into` (window.py:4865) with the attention-hook env. Add one additive optional param threaded through:
- `_split_active_pane(..., feed: bytes | None = None)` → `_spawn_into(..., feed_override: bytes | None = None)`
- At the feed site: `feed_override if feed_override is not None else agentconfig.agent_feed_bytes(...)`. Byte-identical behavior when not passed.
- No active workspace → `_split_active_pane` already falls back to the pinned main workspace at project root; mic stays enabled.

**Feed bytes** (safe quoting — prompt may contain quotes/`$(...)`/newlines), new helper in `agentconfig.py` beside `agent_feed_bytes` (agentconfig.py:52):
```python
def prompt_feed_bytes(command: str, prompt: str) -> bytes:
    argv = agent_argv(command) + [prompt]
    return (shlex.join(argv) + "\n").encode("utf-8")
```
`normalize_transcript` collapses all whitespace to single spaces first, so exactly one line is fed. Empty normalized text → toast "nada reconhecido", nothing runs.

**History**: `GLib.get_user_config_dir()/arduis/voice_history.json`, entries `{"text", "ts", "count"}`, newest first, capped at `history_max` (200), atomic mkstemp+`os.replace`. UI: header `Gtk.MenuButton` → Popover with scrolled `Gtk.ListBox`; each row = ellipsized label (tooltip = full text) + play button → `_run_voice_prompt(text)`.

**Keybinding**: closed-set pattern — `keymap.KEYMAP["v"] = ("voice", None)`, `keyconfig._ACTIONS["voice_toggle"]`, new `kind == "voice"` branch in `_run_action` (window.py:2991) → `_toggle_voice()`. Rebindable via `[keys.bindings]`.

**Recording indicator**: `.voice-recording` CSS class (pulsing opacity keyframes in the existing `_build_css`) + icon swap on the mic button.

## `[voice]` config schema (~/.config/arduis/arduis.toml)

```toml
[voice]
command = "whisper-cli"                                   # shlex-split; may embed flags
model = "~/.local/share/arduis/models/ggml-base.en.bin"   # expanduser'd
language = "en"
silence_ms = 1500
silence_threshold_db = -40.0
max_seconds = 60
history_max = 200
```
All keys optional with those defaults (tolerant load, mirroring `agentconfig.load_agent_config`). Add `"voice"` to `appconfig._SECTION_ORDER` (appconfig.py:18) so the theme writer preserves the section.

## Steps (each shippable, main stays green)

**1 — History store (pure).** Create `src/arduis/voice_store.py` (`load_history`, `append_entry` with cap+atomic write) + `tests/test_voice_store.py` (round-trip, cap, garbage-file tolerance).

**2 — Config + argv + parse + feed bytes (pure).** Create `src/arduis/voiceconfig.py` (`VoiceConfig`, `load_voice_config`, `transcribe_argv`, `parse_transcript_json`). Modify `src/arduis/agentconfig.py` (add `prompt_feed_bytes`) and `src/arduis/appconfig.py` (`_SECTION_ORDER` + "voice"). Tests: `tests/test_voiceconfig.py`; extend `tests/test_agentconfig.py` (quotes, `$(...)`, unicode, empty) and `tests/test_appconfig.py`.

**3 — State machine (pure).** Create `src/arduis/voice.py` (`VoiceMachine`, `normalize_transcript`) + `tests/test_voice.py` (transition table, silence sequence, manual stop, max cap, toggle-during-transcribing ignored, multi-line normalization).

**4 — Run-prompt plumbing + history UI** (usable via "run again" before capture exists). Modify `src/arduis/window.py`: thread `feed=`/`feed_override=` through `_split_active_pane`/`_spawn_into`; add `_run_voice_prompt(prompt)`; header mic button (placeholder-insensitive) + history popover. Test: `tests/smoke/test_voice_history_smoke.py` (mirror `test_setup_feed_smoke.py` — activate a history row, assert new leaf + fed bytes equal `prompt_feed_bytes(...)`).

**5 — Capture + transcription controller (the voice loop).** Create `src/arduis/voice_controller.py` (lazy `Gst.init_check` → toast + disable on failure; pipeline/EOS/bus watch; `GLib.timeout_add` max-cap tick; `Gio.Subprocess` transcription; temp cleanup). Wire in `window.py` (lazy instantiation on first toggle, state→CSS, transcript→toast+`_run_voice_prompt`). Modify `keymap.py`/`keyconfig.py` + extend their tests.

**6 — Polish + packaging.** `.voice-recording` pulse CSS; docs note for `[voice]` + model download hint; GStreamer deps (`gir1.2-gstreamer-1.0`, `gir1.2-gst-plugins-base-1.0`, `gstreamer1.0-plugins-good` / AUR `gstreamer gst-plugins-base gst-plugins-good`) + `whisper-cli` as Recommends/optdepends in packaging manifests (covered by `tests/test_packaging_install_tree.py`).

## Existing code to reuse
- `src/arduis/window.py` — `_split_active_pane` (4291), `_spawn_into` (4865), `_run_action` (2991), `_toast` (5561), header build (~600–650)
- `src/arduis/agentconfig.py` — `agent_argv` (43), `agent_feed_bytes` (52) as templates
- `src/arduis/git_service.py:47` — `run_git_async`: the `Gio.Subprocess` + `communicate_utf8_async` template (argv-generic; may be reused directly)
- `src/arduis/projects_store.py` — atomic-JSON template for the history store
- `src/arduis/keyconfig.py` / `keymap.py` — keybinding closed action set
- `src/arduis/host_runner.py` — argv/env seam for the whisper subprocess

## Verification

**pytest** (`python -m pytest`, Stop hook blocks on red): new `test_voice_store.py`, `test_voiceconfig.py`, `test_voice.py`, `tests/smoke/test_voice_history_smoke.py`; extended `test_agentconfig.py`, `test_appconfig.py`, `test_keymap.py`, `test_keyconfig.py`.

**Manual smoke** (needs `whisper-cli` + a `ggml-base.en.bin` model):
1. No config/binary → mic toggle shows toast, app unharmed.
2. Toggle mic in a workspace, speak, silence 1.5s → new pane splits, `claude 'your prompt'` typed into zsh, claude starts.
3. Prompt appears atop the history popover; run-again spawns another pane.
4. Prompt containing quotes/`$(date)` arrives literally (no shell execution).
5. Manual toggle-off mid-speech still transcribes; 60s cap stops.
6. Mic with no workspace runs in project root.
7. Restart → history persists; theme change keeps `[voice]` section intact.
8. `C-Space v` toggles; rebind works.
9. `$XDG_RUNTIME_DIR/arduis/voice/` clean after each run.
10. UI stays responsive during recording/transcription (no threads).
