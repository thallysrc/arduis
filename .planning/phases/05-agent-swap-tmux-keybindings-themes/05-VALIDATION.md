# Phase 05 Validation Architecture — Agent Swap + tmux Keybindings + Themes

**Derived from:** 05-RESEARCH.md §"Validation Architecture"
**nyquist_validation:** ON (config.json `workflow.nyquist_validation: true`)
**Baseline:** 172 tests passing before this phase.

---

```
status: validated
nyquist_compliant: true
wave_0_complete: true
validated: 2026-06-15
```

---

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]`, `pythonpath=["src"]`, `testpaths=["tests"]`) |
| Runner | `/tmp/arduis-venv/bin/python -m pytest` (venv with `--system-site-packages` for PyGObject) |
| Quick run | `/tmp/arduis-venv/bin/python -m pytest tests/test_themes.py tests/test_keyconfig.py tests/test_agentconfig.py tests/test_appconfig.py tests/test_keymap.py -x` |
| Full suite | `/tmp/arduis-venv/bin/python -m pytest tests/ -q` |
| Headless GTK | `gtk4-broadwayd :9N` + `GDK_BACKEND=broadway BROADWAY_DISPLAY=:9N` (do NOT override `XDG_RUNTIME_DIR` — broadway finds its socket there; the Phase-4 smoke lesson) |

GTK-free modules (`themes.py`, `agentconfig.py`, `keyconfig.py`, `appconfig.py`, `keymap.py`)
are unit-testable directly on the host. `window.py` (GTK) is covered by the headless broadway
smoke (`tests/smoke/test_theme_switch_smoke.py`, run as `__main__`, 9/9 PASS per 05-04 SUMMARY)
+ the live human-verify checklist (Plan 05-04 Task 2, persisted to `05-HUMAN-UAT.md`).

## Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File / Status |
|--------|----------|-----------|-------------------|---------------|
| AGENT-01 | `agent_argv("claude --model opus")` → `["claude","--model","opus"]`; empty → `["claude"]`; quotes handled; `agent_feed_bytes` ends in `\n`; `resume_feed_bytes` appends `--continue` only for claude-family (basename) | unit | `pytest tests/test_agentconfig.py` | `tests/test_agentconfig.py` — ✅ 20 tests passing |
| AGENT-01 | configured command feeds on create/split/resume; `C-Space a` re-feeds without respawn; Ctrl+C drops to live shell | headless smoke + manual UAT | `tests/smoke/test_theme_switch_smoke.py` (run as `__main__`): configured-feed-bytes check PASS; live Ctrl+C/refeed behavior is Manual-Only | smoke 05-04 9/9 PASS / UAT (Manual-Only) |
| UI-01 | `resolve_keymap` merges `[keys.bindings]` over `DEFAULT_KEYMAP`, drops unknown action (closed set) / bad key; `resolve_prefix` parses `ctrl+space`/`ctrl+b`, garbage → default; `dispatch` returns split/zoom/refeed tuples | unit | `pytest tests/test_keyconfig.py tests/test_keymap.py` | `tests/test_keyconfig.py` ✅ 17 tests + `tests/test_keymap.py` ✅ 10 tests = 27 passing |
| UI-01 | C-Space prefix arms app-scoped under native Wayland (not XWayland); configurable prefix rebinds | manual UAT | live checklist item 1 (assert `$XDG_SESSION_TYPE=wayland`) | UAT 05-04 — Manual-Only (Wayland gate) |
| UI-02 | `get_theme(name)` → correct Theme / Dracula for unknown; every Theme has exactly 16 palette colors + valid `#rrggbb` hex; Dracula == theme.py | unit | `pytest tests/test_themes.py` | `tests/test_themes.py` ✅ 13 tests passing |
| UI-02 | `load_theme_name` tolerant; `write_theme` atomic + section-preserving (no tomli-w) | unit | `pytest tests/test_appconfig.py` | `tests/test_appconfig.py` ✅ 14 tests passing |
| UI-02 | runtime switch re-colors all live terminals + REPLACES (not stacks) the CssProvider; new terminals born in active theme | headless smoke + manual UAT | `tests/smoke/test_theme_switch_smoke.py` (run as `__main__`): switch/provider-replace/born-in-theme checks all PASS; live visual rendering is Manual-Only | smoke 05-04 9/9 PASS / UAT (Manual-Only) |

## Wave 0 Completion

All Wave-0 test files created and passing:

- [x] `tests/test_themes.py` — 13 tests: registry shape (4 slugs), 16-color palette invariant, valid-hex invariant, unknown→Dracula whitelist, Dracula==theme.py, frozen/GTK-free (UI-02) — **Plan 05-01** ✅
- [x] `tests/test_agentconfig.py` — 20 tests: `[agent] command` read, shlex split (+quotes), feed-bytes (`\n`, round-trip), claude-family `--continue` resume, empty→`claude`, GTK-free (AGENT-01) — **Plan 05-02 Task 2** ✅
- [x] `tests/test_keyconfig.py` — 17 tests: prefix parse + garbage→default, bindings merge over defaults, closed-action-set rejection, bad-key drop, GTK-free (UI-01) — **Plan 05-02 Task 2** ✅
- [x] `tests/test_appconfig.py` — 14 tests: `[theme] name` read tolerant, atomic `write_theme` round-trip + section-preservation (incl. nested `[keys.bindings]`) + re-readable by `attention.load_config` + no tmp leftover + uncreatable-parent no-raise (UI-02) — **Plan 05-02 Task 3** ✅
- [x] extend `tests/test_keymap.py` — 10 tests total (+split/zoom/refeed/DEFAULT_KEYMAP cases; unknown-key case → "q") (UI-01) — **Plan 05-02 Task 1** ✅
- [x] `tests/smoke/test_theme_switch_smoke.py` — headless broadway script (not a pytest item): 9/9 PASS — provider-replace-not-stack + `_current_theme` flip + born-in-theme + configured-feed bytes + resolved-binding; sandbox HOME; no orphans (UI-02/AGENT-01) — **Plan 05-04 Task 1** ✅

## Sampling Rate

- **Per task commit:** `/tmp/arduis-venv/bin/python -m pytest tests/test_themes.py tests/test_keyconfig.py tests/test_agentconfig.py tests/test_appconfig.py tests/test_keymap.py -x`
- **Per wave merge:** `/tmp/arduis-venv/bin/python -m pytest tests/ -q` (full suite, no regression on baseline 172 + new)
- **Phase gate:** full suite green (240 passed at phase close) + headless broadway smoke 9/9 PASS + Manual-Only UAT items persisted to `05-HUMAN-UAT.md`.

## Live UAT Items (Manual-Only — do NOT block nyquist_compliant)

1. **Criterion 3 (GATE):** `$XDG_SESSION_TYPE == wayland`; `C-Space` arms + `h/j/k/l/z/-/=`
   dispatch app-scoped under native Wayland (not XWayland). Prefix rebind (`ctrl+b`) works if
   C-Space collides (Pitfall 3 / A2). — **Requires live Wayland session; no display available.**
2. **Criterion 1:** configured agent runs; Ctrl+C → live zsh (same pane, scrollback kept);
   `C-Space a` / typing relaunches in the SAME pane (no respawn). — **Wiring proven by smoke; interactive behavior requires live terminal.**
3. **Criterion 2:** tmux chords behave; `[keys.bindings]` override takes effect; garbage ignored. — **Logic proven by unit tests; live keypress capture requires display.**
4. **Criterion 4:** "Tema" menu switches UI + every live VTE (incl. a pane created after the
   switch); repeated switches no drift/crash; choice persists; other config sections intact. — **Switch mechanism proven by smoke; visual rendering requires display.**
5. **No orphans** on close. — **Requires live process group inspection.**

Persisted to `05-HUMAN-UAT.md` (status: partial) for `/gsd-progress` visibility.

## Validation Sign-Off

- [x] All Wave-0 test files exist on disk
- [x] 74 unit tests pass (`test_agentconfig.py` 20 + `test_appconfig.py` 14 + `test_keyconfig.py` 17 + `test_keymap.py` 10 + `test_themes.py` 13)
- [x] Headless broadway smoke: 9/9 PASS (run as `__main__`, per 05-04 SUMMARY)
- [x] Full suite at phase close: 240 passed (172 baseline + 68 Phase-5 new), no regression
- [x] Manual-only items correctly categorized — live GTK rendering, Wayland session, interactive keypress capture; none are automatable without a display
- [x] Real `~/.config/arduis/arduis.toml` untouched during smoke (T-05-08, verified by mtime check)

**Approval:** validated 2026-06-15 (post-execution reconcile)

## Notes for the Verifier

- A wrong non-Dracula palette hex (Nord/Solarized/Gruvbox) is **cosmetic** (A1) — Pitfall 6's
  valid-hex test + parse guard prevent a crash; record any color the user wants corrected in the
  05-04 SUMMARY, do not treat as a phase blocker.
- Criterion 3 is **verification, not code** (the capture-phase machine already satisfies it —
  05-RESEARCH §Wayland); the gate is the live `$XDG_SESSION_TYPE=wayland` confirmation.
- `session.py` is NOT modified this phase — the configurable feed is built in `window.py` from
  `agentconfig`; the `AGENT_FEED`/`AGENT_RESUME_FEED` literals may remain as unused constants.
- `tests/smoke/test_theme_switch_smoke.py` collects 0 items under pytest (it is a `__main__`
  harness, not a pytest module). It must be run directly: `python tests/smoke/test_theme_switch_smoke.py`. It skips gracefully if `gtk4-broadwayd` is absent.

---

## Validation Audit 2026-06-15

**Context:** This document was a stale plan-time draft (no status frontmatter, all Wave-0 items unchecked, no sign-off). The phase shipped on 2026-06-13 with all implementation and tests committed. This audit reconciles the document to reflect reality.

### Metrics

| Metric | Count |
|--------|-------|
| Automated gaps found | 0 |
| Automated gaps resolved | 0 (all were already filled by execution) |
| Genuine gaps escalated | 0 |
| Manual-only items (correctly deferred) | 5 (live Wayland + display-dependent behavior) |

### What is genuinely covered

All non-manual requirements are covered by passing automated tests:

- **AGENT-01 (configurable agent command):** 20 unit tests in `test_agentconfig.py` cover `[agent] command` read with safe defaults, `shlex` argv construction including quoted arguments, `agent_feed_bytes` round-trip and `\n` terminator, and the claude-family `--continue` resume rule keyed on `os.path.basename`. The smoke additionally verifies the configured feed bytes reach the live `ArduisWindow._agent_config` at runtime.
- **UI-01 (tmux-style chord keymap):** 17 unit tests in `test_keyconfig.py` + 10 in `test_keymap.py` cover prefix parsing (`ctrl+space`/`ctrl+b`/garbage→default), bindings merge over `DEFAULT_KEYMAP` through the closed action-name set, unknown-action and bad-key rejection, and `dispatch` returning the correct `("split","v")`, `("split","h")`, `("zoom",None)`, `("refeed",None)` tuples. The closed-set enforcement means user config cannot fabricate actions.
- **UI-02 (Dracula default + swappable themes):** 13 unit tests in `test_themes.py` cover the registry shape (exactly 4 slugs), `get_theme` whitelist with case-insensitive fallback to Dracula, the `set_colors`-protecting invariants (exactly 16 palette entries, every color field matches `^#[0-9a-fA-F]{6}$`), and Dracula byte-identity with `theme.py`. 14 unit tests in `test_appconfig.py` cover the full persistence layer (tolerant read, atomic tmp+`os.replace` write, section preservation across `[keys.bindings]`, re-readability by `attention.load_config`). The smoke verifies the runtime switch mechanism: provider replace-not-stack, `_current_theme` flip, and born-in-theme behavior.

### What remains manual-only (correct, does not block nyquist_compliant)

Live GTK rendering, Wayland keyboard capture, interactive PTY job control (Ctrl+C/Ctrl+Z+fg), and visual theme switch — all require a live display and/or interactive session. These are correctly categorized as Manual-Only in `05-HUMAN-UAT.md`. The underlying wiring is proven by unit tests and the headless broadway smoke; what is deferred is only the human-observable confirmation that the rendering looks correct under a real compositor.

*Reconciled: 2026-06-15*
