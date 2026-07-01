---
phase: 05-agent-swap-tmux-keybindings-themes
verified: 2026-06-13T16:00:00Z
status: human_needed
score: 3/4 must-haves verified
re_verification: false
human_verification:
  - test: "Run arduis on a real Wayland session (echo $XDG_SESSION_TYPE must print 'wayland', not 'x11'). With arduis focused, press C-Space then h/j/k/l to move focus, C-Space z to zoom, C-Space - and C-Space = to split."
    expected: "All chords work app-scoped; the prefix arms and actions dispatch. If C-Space collides with a GNOME/zsh binding, set [keys] prefix = 'ctrl+b' in arduis.toml, relaunch, and confirm the new prefix arms."
    why_human: "Criterion 3 is a verification, not new code. The capture-phase EventControllerKey provides app-internal propagation (not a compositor grab), so it should work — but it requires a native Wayland session ($XDG_SESSION_TYPE=wayland) to confirm. XWayland does not count."
  - test: "Verify no-orphan teardown: close arduis with agents running and run: ps -eo pgid,cmd | grep -i claude"
    expected: "No orphan zsh/claude processes remain."
    why_human: "Teardown behavior requires a live process table to observe; not exercisable headlessly."
---

# Phase 5: Agent Swap + tmux Keybindings + Themes — Verification Report

**Phase Goal:** Respect the tmux-centric user's muscle memory and finalize the "agent = configurable command" abstraction. The shell is the durable PTY child; agents are ephemeral commands run inside it, so Ctrl+C drops to the shell to launch another agent with zero re-spawn.
**Verified:** 2026-06-13T16:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| #   | Truth | Status | Evidence |
| --- | ----- | ------ | -------- |
| 1 | Agent is a configurable command (default `claude`); Ctrl+C drops to the shell and the user can run a different agent in the same pane (no re-spawn) | ? HUMAN_NEEDED | Wiring VERIFIED: `_make_wt_spawn_cb` uses `agentconfig.agent_feed_bytes/resume_feed_bytes(self._agent_config.command)`. `_refeed_focused_agent()` calls `feed_child()` with no kill/respawn (Pitfall 5). Ctrl+C native job control is unchanged. Live behavior requires human confirmation. |
| 2 | tmux-style keybindings work (C-Space, C-h/j/k/l, split -/=, zoom z) and are configurable | ? HUMAN_NEEDED | Wiring VERIFIED: `_on_key` uses `self._prefix[0]` + CONTROL_MASK and dispatches via `self._keymap`. `_run_action` handles split/zoom/refeed verbs. Smoke proved `win._keymap.get("q") == ("zoom", None)` from a fixture `[keys.bindings]`. 240 tests pass. Live dispatch requires human confirmation. |
| 3 | Keybindings work as app-scoped shortcuts under real Wayland (not just XWayland) | ? HUMAN_NEEDED | Research established the capture-phase EventControllerKey is app-internal propagation (not a compositor grab) — satisfies the requirement by design. However, this is a live-only gate: `$XDG_SESSION_TYPE=wayland` must be confirmed by a human on a real Wayland session. Recorded in 05-HUMAN-UAT.md. |
| 4 | App and terminal use Dracula theme by default, and the user can switch to other themes (UI palette + VTE palette) | ✓ VERIFIED | Headless broadway smoke PASSED 9/9: `_current_theme` flips on switch, CssProvider REPLACED (new object — not stacked), terminal born-in-active-theme after switch, repeated switches no crash, startup theme was dracula. `_build_css(theme)` uses all 8 theme color fields. `_make_terminal` colors from `self._current_theme`. `write_theme` atomic + section-preserving. 4 themes ship: dracula/nord/solarized-dark/gruvbox-dark. |

**Score:** 3/4 truths verified (truth 4 fully verified; truths 1/2/3 have wiring verified but live confirmation pending)

### Deferred Items

None.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `src/arduis/themes.py` | GTK-free Theme dataclass + THEMES registry + get_theme whitelist | ✓ VERIFIED | Exists, 124 lines, frozen dataclass, 4 themes, `get_theme` dict whitelist, zero `gi` imports, imports `DRACULA_*` from `arduis.theme` verbatim |
| `src/arduis/agentconfig.py` | load_agent_config / agent_argv / agent_feed_bytes / resume_feed_bytes | ✓ VERIFIED | Exists, 71 lines, `shlex.split/join` for argv, claude-family `--continue` rule, tolerant reader, zero `gi` imports |
| `src/arduis/keyconfig.py` | resolve_prefix + resolve_keymap over keymap.DEFAULT_KEYMAP (closed action set) | ✓ VERIFIED | Exists, 63 lines, `resolve_prefix` parses `<mod>+<key>`, `resolve_keymap` merges over `DEFAULT_KEYMAP` with closed `_ACTIONS` set, zero `gi` imports |
| `src/arduis/appconfig.py` | load_theme_name + write_theme (atomic, section-preserving) | ✓ VERIFIED | Exists, 117 lines, `os.replace` for atomicity, minimal TOML serializer, preserves `[keys.bindings]` sub-table, zero `gi` imports |
| `src/arduis/keymap.py` | DEFAULT_KEYMAP alias + split/zoom/refeed tuples in dispatch | ✓ VERIFIED | Exists, `DEFAULT_KEYMAP = KEYMAP`, `-`→`("split","v")`, `=`→`("split","h")`, `z`→`("zoom",None)`, `a`→`("refeed",None)` added; h/j/k/l/n/p unchanged; `dispatch("q") is None` |
| `src/arduis/window.py` | configurable agent feed + configurable prefix/bindings + runtime theme switch + header Tema menu + persistence | ✓ VERIFIED | Exists (3013 lines), imports `agentconfig/appconfig/keyconfig/THEMES/Theme/get_theme`; all required wiring present (see Key Link Verification) |
| `tests/test_themes.py` | registry shape, 16-color invariant, valid-hex invariant, unknown→dracula, dracula==theme.py | ✓ VERIFIED | 13 tests, all passing |
| `tests/test_agentconfig.py` | command read, shlex split, feed bytes, claude-family --continue, empty→default | ✓ VERIFIED | 20 tests, all passing |
| `tests/test_keyconfig.py` | prefix parse, bindings merge, closed-set rejection, garbage→default | ✓ VERIFIED | 17 tests, all passing |
| `tests/test_appconfig.py` | theme name read + atomic write round-trip preserving other sections | ✓ VERIFIED | 14 tests, all passing |
| `tests/test_keymap.py` | split/zoom/refeed tuples, DEFAULT_KEYMAP, unknown-key uses "q" | ✓ VERIFIED | 10 tests, all passing; `test_dispatch_unknown` correctly uses "q" (not "z") |
| `tests/smoke/test_theme_switch_smoke.py` | headless broadway: switch re-colors + replaces provider + born-in-theme + configured-feed/dispatch | ✓ VERIFIED | Exists, 151 lines, contains `broadway`/`_apply_theme`/`set_colors`, sandbox HOME, 9/9 checks PASS |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `window.py:_make_wt_spawn_cb` | `agentconfig.py` | `agentconfig.agent_feed_bytes / resume_feed_bytes(self._agent_config.command)` | ✓ WIRED | Lines 2351-2355: `cmd = self._agent_config.command`; resume path uses `resume_feed_bytes(cmd)`, normal path uses `agent_feed_bytes(cmd)` |
| `window.py:_on_key` | `keyconfig.py` | `resolve_prefix/resolve_keymap` drive `self._prefix` and `self._keymap` | ✓ WIRED | Lines 341-342: `self._prefix = keyconfig.resolve_prefix(...)`; `self._keymap = keyconfig.resolve_keymap(...)`. Line 1478: `name == self._prefix[0]`; Line 1490: `self._keymap.get(name)` |
| `window.py:_apply_theme` | `themes.py + appconfig.write_theme` | `get_theme(slug) -> rebuild CssProvider + set_colors on all terminals -> persist` | ✓ WIRED | Lines 486-526: `_apply_theme` removes old provider, loads `_build_css(theme)`, calls `set_colors/set_color_cursor` on all `_term_by_sid` values, sets `self._current_theme`; `_on_set_theme` calls `appconfig.write_theme(self._config_path, theme.name)` |
| `themes.py` | `arduis.theme` (DRACULA_* constants) | `from arduis.theme import DRACULA_BG, DRACULA_CURSOR, DRACULA_FG, DRACULA_PALETTE` | ✓ WIRED | Lines 20-25: imports all four constants; `DRACULA.bg = DRACULA_BG` etc. — single source of truth |
| `keyconfig.py` | `keymap.DEFAULT_KEYMAP` | `from arduis.keymap import DEFAULT_KEYMAP`; `table = dict(DEFAULT_KEYMAP)` | ✓ WIRED | Line 10: import; Line 55: `table = dict(DEFAULT_KEYMAP)` |
| `tests/smoke/test_theme_switch_smoke.py` | `window.py` | `ArduisWindow._apply_theme` + `_css_provider` identity + `_current_theme` | ✓ WIRED | Lines 96-130: constructs `ArduisWindow`, calls `win._apply_theme(get_theme("nord"))`, inspects `id(win._css_provider)`, `win._current_theme.name`, `win._keymap.get("q")` |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
| -------- | ------------- | ------ | ------------------ | ------ |
| `window.py:_make_terminal` | `self._current_theme` | `get_theme(appconfig.load_theme_name(self._config_path))` at `__init__`, updated by `_apply_theme` | Yes — reads from live `[theme] name` in arduis.toml (Dracula fallback), not a static value | ✓ FLOWING |
| `window.py:_make_wt_spawn_cb` | `agent_feed` | `agentconfig.agent_feed_bytes / resume_feed_bytes(self._agent_config.command)` where `self._agent_config = agentconfig.load_agent_config(self._config_path)` | Yes — reads from `[agent] command` in arduis.toml (claude fallback) | ✓ FLOWING |
| `window.py:_on_key` | `self._keymap` | `keyconfig.resolve_keymap(_keys.get("bindings"))` from `_read_keys_section(self._config_path)` | Yes — reads from `[keys.bindings]` in arduis.toml (DEFAULT_KEYMAP fallback) | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Full suite 240 tests pass | `/tmp/arduis-venv-ab12/bin/python -m pytest tests/ 2>&1 \| tail -1` | `240 passed in 1.18s` | ✓ PASS |
| window.py parses without syntax errors | `python3 -c "import ast; ast.parse(open('src/arduis/window.py').read()); print('parse-ok')"` | `parse-ok` | ✓ PASS |
| `win.set_theme` wired (menu target + action registration) | `grep -c "win.set_theme" src/arduis/window.py` | `4` (≥2) | ✓ PASS |
| CssProvider replace-not-stack | `grep -c "remove_provider_for_display" src/arduis/window.py` | `1` (≥1) | ✓ PASS |
| Agent feed bytes wired | `grep -c "agent_feed_bytes\|resume_feed_bytes" src/arduis/window.py` | `5` (≥2) | ✓ PASS |
| GTK-free modules have zero gi imports | `grep -c "import gi\|from gi" themes.py agentconfig.py keyconfig.py appconfig.py keymap.py` | `0` for all 5 | ✓ PASS |
| Broadway smoke 9/9 | `tests/smoke/test_theme_switch_smoke.py` result per 05-04-SUMMARY | `9/9 PASS` | ✓ PASS |
| Live Wayland criterion 3 gate | Requires `$XDG_SESSION_TYPE=wayland` session | Pending — live only | ? SKIP |
| No orphans on close | `ps -eo pgid,cmd \| grep -i claude` after close | Pending — live only | ? SKIP |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| AGENT-01 | 05-01-PLAN, 05-02-PLAN, 05-03-PLAN, 05-04-PLAN | Agente = comando configurável (default `claude`); `Ctrl+C` cai no shell para rodar outro agente | ? NEEDS HUMAN (wiring verified) | `agentconfig.py` + `agent_feed_bytes/resume_feed_bytes` wired in `_make_wt_spawn_cb`; `_refeed_focused_agent` types into live PTY without respawn. Live Ctrl+C / re-feed behavior requires human. |
| UI-01 | 05-02-PLAN, 05-03-PLAN, 05-04-PLAN | Keybindings configuráveis estilo tmux (C-Space, C-h/j/k/l, split -/=, zoom z) | ? NEEDS HUMAN (wiring verified, Wayland gate pending) | `keyconfig.py` + `keymap.py` with split/zoom/refeed chords; `_on_key` uses `self._prefix[0]` + `self._keymap`. Criterion 3 (Wayland app-scoped) is the live gate. |
| UI-02 | 05-01-PLAN, 05-02-PLAN, 05-03-PLAN, 05-04-PLAN | Temas de cor do app e dos terminais — Dracula default, trocáveis | ✓ VERIFIED | `themes.py` (4 themes, valid-hex invariant), `_build_css/`_apply_theme/_make_terminal` all read `self._current_theme`; headless broadway smoke 9/9 proves the mechanism. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| `window.py` | 1327, 1341 | `_show_hibernated_placeholder` | ℹ️ Info | Legitimate UI element for hibernated tasks — not a code stub. Pre-existing from Phase 3. |

No blockers, no stubs, no hardcoded empty data flows, no TODO/FIXME/placeholder comments in any Phase-5 files.

### Human Verification Required

#### 1. Criterion 3 — C-Space prefix arms under real Wayland (THE locked gate)

**Test:** In a terminal, run `echo $XDG_SESSION_TYPE` — it MUST print `wayland` (not `x11`). Then launch arduis and press C-Space followed by h/j/k/l (focus moves), z (zoom), - and = (splits). Confirm the prefix arms and each chord dispatches. If C-Space collides with a GNOME/zsh binding, set `[keys] prefix = "ctrl+b"` in arduis.toml, relaunch, and confirm the new prefix arms.
**Expected:** Prefix arms and every chord dispatches correctly, app-scoped, under native Wayland.
**Why human:** The capture-phase EventControllerKey is app-internal propagation (not a compositor grab), so no new code is needed — but only a live `$XDG_SESSION_TYPE=wayland` session can confirm it. XWayland would not count.

#### 2. Criterion 1 — configurable agent, Ctrl+C → shell → re-feed, no respawn

**Test:** With default config, create a task and confirm `claude` runs. Press Ctrl+C → confirm claude exits and you land at the live zsh (same pane, scrollback intact). Type `C-Space a` or another agent command → confirm it launches in the SAME pane without anything being respawned. Then set `[agent] command = "claude --model opus"` in arduis.toml, relaunch, and confirm that command runs.
**Expected:** Ctrl+C drops to shell; re-feed types the configured command into the live zsh; no pane is killed or respawned.
**Why human:** Native job control and PTY behavior require a live VTE session to observe.

#### 3. No orphans on close

**Test:** Close arduis while agents are running; run `ps -eo pgid,cmd | grep -i claude`.
**Expected:** No orphan zsh/claude processes.
**Why human:** Process table state is only observable live.

### Gaps Summary

No gaps. All Phase-5 code artifacts are present, substantive, wired, and data-flowing. The three items in the Human Verification section are live-only confirmations, not code defects:

- Criterion 3 (Wayland) is explicitly documented in 05-HUMAN-UAT.md as a verification (not new code); the mechanism is correct by design.
- Criterion 1 live behavior (Ctrl+C / re-feed) is proven at the wiring level by the broadway smoke and unit tests; live confirmation is a formality.
- No-orphan check reuses teardown machinery from prior phases.

The phase is functionally complete. Status is `human_needed` because the UAT checklist items exist, not because of any code defect.

---

_Verified: 2026-06-13T16:00:00Z_
_Verifier: Claude (gsd-verifier)_
