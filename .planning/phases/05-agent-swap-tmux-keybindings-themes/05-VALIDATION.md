# Phase 05 Validation Architecture — Agent Swap + tmux Keybindings + Themes

**Derived from:** 05-RESEARCH.md §"Validation Architecture"
**nyquist_validation:** ON (config.json `workflow.nyquist_validation: true`)
**Baseline:** 172 tests passing before this phase.

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `pythonpath=["src"]`, `testpaths=["tests"]`) |
| Runner | `/tmp/arduis-venv-ab12/bin/python -m pytest` (venv with `--system-site-packages` for PyGObject) |
| Quick run | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_themes.py tests/test_keyconfig.py tests/test_agentconfig.py tests/test_appconfig.py tests/test_keymap.py -x` |
| Full suite | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/ -q` |
| Headless GTK | `gtk4-broadwayd :9N` + `GDK_BACKEND=broadway BROADWAY_DISPLAY=:9N` (do NOT override `XDG_RUNTIME_DIR` — broadway finds its socket there; the Phase-4 smoke lesson) |

GTK-free modules (`themes.py`, `agentconfig.py`, `keyconfig.py`, `appconfig.py`, `keymap.py`)
are unit-testable directly on the host. `window.py` (GTK) is covered by the headless broadway
smoke (Plan 04 Task 1) + the live human-verify checklist (Plan 04 Task 2).

## Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File / Status |
|--------|----------|-----------|-------------------|---------------|
| AGENT-01 | `agent_argv("claude --model opus")` → `["claude","--model","opus"]`; empty → `["claude"]`; quotes handled; `agent_feed_bytes` ends in `\n`; `resume_feed_bytes` appends `--continue` only for claude-family (basename) | unit | `pytest tests/test_agentconfig.py -x` | `tests/test_agentconfig.py` — Wave 0 (05-02 Task 2) |
| AGENT-01 | configured command feeds on create/split/resume; `C-Space a` re-feeds without respawn; Ctrl+C drops to live shell | headless smoke + manual UAT | smoke (feed-bytes) + live checklist item 2 | smoke 05-04 / UAT |
| UI-01 | `resolve_keymap` merges `[keys.bindings]` over `DEFAULT_KEYMAP`, drops unknown action (closed set) / bad key; `resolve_prefix` parses `ctrl+space`/`ctrl+b`, garbage → default; `dispatch` returns split/zoom/refeed tuples | unit | `pytest tests/test_keyconfig.py tests/test_keymap.py -x` | `tests/test_keyconfig.py` (new) + extend `tests/test_keymap.py` — Wave 0 (05-02 Tasks 1-2) |
| UI-01 | C-Space prefix arms app-scoped under native Wayland (not XWayland); configurable prefix rebinds | manual UAT | live checklist item 1 (assert `$XDG_SESSION_TYPE=wayland`) | UAT 05-04 — THE GATE |
| UI-02 | `get_theme(name)` → correct Theme / Dracula for unknown; every Theme has exactly 16 palette colors + valid `#rrggbb` hex; Dracula == theme.py | unit | `pytest tests/test_themes.py -x` | `tests/test_themes.py` (new) — Wave 0 (05-01) |
| UI-02 | `load_theme_name` tolerant; `write_theme` atomic + section-preserving (no tomli-w) | unit | `pytest tests/test_appconfig.py -x` | `tests/test_appconfig.py` (new) — Wave 0 (05-02 Task 3) |
| UI-02 | runtime switch re-colors all live terminals + REPLACES (not stacks) the CssProvider; new terminals born in active theme | headless smoke + manual UAT | smoke (provider-identity + `_current_theme` flip + born-in-theme) + live checklist item 4 | smoke 05-04 / UAT |

## Sampling Rate

- **Per task commit:** `/tmp/arduis-venv-ab12/bin/python -m pytest tests/test_themes.py tests/test_keyconfig.py tests/test_agentconfig.py tests/test_appconfig.py tests/test_keymap.py -x`
- **Per wave merge:** `/tmp/arduis-venv-ab12/bin/python -m pytest tests/ -q` (full suite, no regression on baseline 172 + new)
- **Phase gate:** full suite green + headless broadway smoke pass + manual UAT (live Wayland, criterion 3) before `/gsd-verify-work`.

## Wave 0 Gaps (tests that must be created/extended before/with the code)

- [ ] `tests/test_themes.py` — registry shape (4 slugs), 16-color palette invariant, valid-hex invariant, unknown→Dracula whitelist, Dracula==theme.py, frozen/GTK-free (UI-02) — **Plan 05-01**
- [ ] `tests/test_agentconfig.py` — `[agent] command` read, shlex split (+quotes), feed-bytes (`\n`, round-trip), claude-family `--continue` resume, empty→`claude`, GTK-free (AGENT-01) — **Plan 05-02 Task 2**
- [ ] `tests/test_keyconfig.py` — prefix parse + garbage→default, bindings merge over defaults, closed-action-set rejection, bad-key drop, GTK-free (UI-01) — **Plan 05-02 Task 2**
- [ ] `tests/test_appconfig.py` — `[theme] name` read tolerant, atomic `write_theme` round-trip + section-preservation (incl. nested `[keys.bindings]`) + re-readable by `attention.load_config` + no tmp leftover + uncreatable-parent no-raise (UI-02) — **Plan 05-02 Task 3**
- [ ] extend `tests/test_keymap.py` — split(`-`/`=`)/zoom(`z`)/refeed(`a`) tuples in `dispatch`; `DEFAULT_KEYMAP` exposed; REPLACE the stale `dispatch("z") is None` case with a genuinely-unmapped key (`"q"`) (UI-01) — **Plan 05-02 Task 1**
- [ ] `tests/smoke/test_theme_switch_smoke.py` — headless broadway: provider-replace-not-stack + `_current_theme` flip + born-in-theme + configured-feed bytes + resolved-binding; sandbox HOME (real config untouched); no orphans (UI-02/AGENT-01) — **Plan 05-04 Task 1**

## Live UAT Items (human-verify, Plan 05-04 Task 2)

1. **Criterion 3 (GATE):** `$XDG_SESSION_TYPE == wayland`; `C-Space` arms + `h/j/k/l/z/-/=`
   dispatch app-scoped under native Wayland (not XWayland). Prefix rebind (`ctrl+b`) works if
   C-Space collides (Pitfall 3 / A2).
2. **Criterion 1:** configured agent runs; Ctrl+C → live zsh (same pane, scrollback kept);
   `C-Space a` / typing relaunches in the SAME pane (no respawn).
3. **Criterion 2:** tmux chords behave; `[keys.bindings]` override takes effect; garbage ignored.
4. **Criterion 4:** "Tema" menu switches UI + every live VTE (incl. a pane created after the
   switch); repeated switches no drift/crash; choice persists; other config sections intact.
5. **No orphans** on close.

## Notes for the Verifier

- A wrong non-Dracula palette hex (Nord/Solarized/Gruvbox) is **cosmetic** (A1) — Pitfall 6's
  valid-hex test + parse guard prevent a crash; record any color the user wants corrected in the
  05-04 SUMMARY, do not treat as a phase blocker.
- Criterion 3 is **verification, not code** (the capture-phase machine already satisfies it —
  05-RESEARCH §Wayland); the gate is the live `$XDG_SESSION_TYPE=wayland` confirmation.
- `session.py` is NOT modified this phase — the configurable feed is built in `window.py` from
  `agentconfig`; the `AGENT_FEED`/`AGENT_RESUME_FEED` literals may remain as unused constants.
