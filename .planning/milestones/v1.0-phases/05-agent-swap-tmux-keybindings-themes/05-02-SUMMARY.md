---
phase: 05-agent-swap-tmux-keybindings-themes
plan: 02
subsystem: config
tags: [tomllib, shlex, keymap, agent, theme, atomic-write, gtk-free, tdd]

# Dependency graph
requires:
  - phase: 03-workspace
    provides: keymap.KEYMAP + dispatch (the GTK-free prefix table extended here)
  - phase: 04-attention
    provides: attention.load_config (the tolerant tomllib safe-default reader pattern mirrored) + arduis.toml [attention] + session AGENT_FEED/AGENT_RESUME_FEED literals
provides:
  - "keymap: split('-'/'=')/zoom(z)/refeed(a) action tuples + DEFAULT_KEYMAP alias"
  - "agentconfig: load_agent_config / agent_argv / agent_feed_bytes / resume_feed_bytes (AGENT-01, D-01/D-03)"
  - "keyconfig: resolve_prefix(s)->(keyval,mods) + resolve_keymap(bindings)->dict[char,tuple] over a closed action set (UI-01, D-04/D-05)"
  - "appconfig: load_theme_name(path)->str + write_theme(path,name) atomic section-preserving (UI-02, D-09)"
affects: [05-03-window-wiring, plan-03, window.py, _run_action, _make_terminal, theme-menu]

# Tech tracking
tech-stack:
  added: []  # zero new dependencies — stdlib only (tomllib/shlex/os/tempfile)
  patterns:
    - "Tolerant tomllib reader with per-key safe default (mirrors attention.load_config)"
    - "Closed action-name set: config can never fabricate an action (mirrors dispatch->None)"
    - "Minimal stdlib TOML serializer (str/bool/int/float + one nested level) — no tomli-w"
    - "Atomic tmp + os.replace, best-effort OSError-swallowed persistence"

key-files:
  created:
    - src/arduis/agentconfig.py
    - src/arduis/keyconfig.py
    - src/arduis/appconfig.py
    - tests/test_agentconfig.py
    - tests/test_keyconfig.py
    - tests/test_appconfig.py
  modified:
    - src/arduis/keymap.py
    - tests/test_keymap.py

key-decisions:
  - "DEFAULT_KEYMAP is the SAME object as KEYMAP (alias), so keyconfig imports a named default without reshaping the table"
  - "resume_feed_bytes appends --continue ONLY when basename(argv[0])=='claude' (D-03); non-claude resumes with the bare command"
  - "write_theme uses a hand-written minimal TOML serializer (no tomli-w dependency, D-09); inline comments are lost on rewrite"
  - "z is now zoom — test_keymap.py::test_dispatch_unknown switched to 'q' (the planned Phase-3->5 contract change)"

patterns-established:
  - "Config layer = one GTK-free module + one focused test file per section ([agent]/[keys]/[theme])"
  - "Every reader tolerates missing file / invalid TOML / wrong-typed key with a safe default"

requirements-completed: [AGENT-01, UI-01, UI-02]

# Metrics
duration: 6min
completed: 2026-06-13
---

# Phase 5 Plan 2: Config/Registry Modules + Keymap Extension Summary

**Three GTK-free config layers (agent command -> safe argv/feed bytes, [keys] prefix + closed-set bindings merge, atomic section-preserving [theme] writer) plus the Phase-5 split/zoom/refeed keymap chords — all stdlib, zero new dependencies, fully unit-tested.**

## Performance

- **Duration:** ~6 min
- **Tasks:** 3 (all TDD RED+GREEN combined)
- **Files modified:** 8 (3 modules + 3 test files created, keymap.py + test_keymap.py extended)
- **Tests:** 227 passed (172 baseline + 55 new)

## Accomplishments
- **keymap.py:** added `-`→`("split","v")`, `=`→`("split","h")`, `z`→`("zoom",None)`, `a`→`("refeed",None)` to `KEYMAP`; exposed `DEFAULT_KEYMAP = KEYMAP`; h/j/k/l/n/p + digit-jump byte-unchanged.
- **agentconfig.py:** `[agent] command` → `shlex.split` argv → `shlex.join`+`\n`+encode feed bytes (round-trips, Pitfall 4); claude-family `--continue` resume rule (D-03).
- **keyconfig.py:** `resolve_prefix` parses `"<mod>+<key>"` (ctrl-only, garbage→default); `resolve_keymap` merges `[keys.bindings]` over `DEFAULT_KEYMAP` through a closed action-name set.
- **appconfig.py:** `load_theme_name` tolerant read; `write_theme` atomic tmp+`os.replace` rewrite via a minimal stdlib TOML serializer that preserves every other section incl. the `[keys.bindings]` sub-table — no `tomli-w`.

## Task Commits

1. **Task 1: extend keymap.py + update stale test** — `8d82c18` (feat)
2. **Task 2: agentconfig + keyconfig** — `e935c75` (feat)
3. **Task 3: appconfig (read + atomic write)** — `360c6ad` (feat)

## Contracts window.py (Plan 03) wires

```python
# agentconfig — the agent feed (bytes, ends in "\n"):
load_agent_config(path) -> AgentConfig(command: str)   # default "claude"
agent_argv(command: str) -> list[str]                  # [] -> ["claude"]
agent_feed_bytes(command: str) -> bytes                # e.g. b"claude\n"
resume_feed_bytes(command: str) -> bytes               # claude-family -> + " --continue"

# keyconfig — prefix + bindings over the defaults:
resolve_prefix(prefix: str | None) -> tuple[str, str]  # (keyval, mods); default ("space","ctrl")
resolve_keymap(bindings: dict | None) -> dict[str, tuple]  # copy of DEFAULT_KEYMAP, merged

# closed action-name set keyconfig accepts (any other name is DROPPED):
#   focus_left/right/up/down, worktree_next/prev, split_v, split_h, zoom, refeed_agent

# appconfig — theme name persistence:
load_theme_name(path: str) -> str        # default "dracula"
write_theme(path: str, name: str) -> None  # atomic, section-preserving, best-effort
```

**Keymap action tuples Plan 03's `_run_action` must now handle:** `("split","v")`, `("split","h")`, `("zoom",None)`, `("refeed",None)` — in addition to the existing `("focus_dir",dir)`, `("worktree",next|prev)`, `("jump",n)`.

**test_keymap.py contract change:** `test_dispatch_unknown` now uses `"q"` (z is zoom in Phase 5). This is the planned Phase-3→5 change, not a regression.

## Files Created/Modified
- `src/arduis/keymap.py` — split/zoom/refeed entries + `DEFAULT_KEYMAP` alias; docstring D-10 note updated
- `src/arduis/agentconfig.py` — `[agent]` reader + argv/feed/resume helpers
- `src/arduis/keyconfig.py` — `[keys]` prefix + bindings merge over the closed action set
- `src/arduis/appconfig.py` — `[theme]` reader + atomic section-preserving writer + minimal TOML serializer
- `tests/test_keymap.py` — split/zoom/refeed/DEFAULT_KEYMAP cases; unknown-key case → "q"
- `tests/test_agentconfig.py` — 20 cases (read/argv/feed/resume/gtk-free)
- `tests/test_keyconfig.py` — 17 cases (prefix parse + bindings merge + closed-set rejection)
- `tests/test_appconfig.py` — 14 cases (read + round-trip + section preservation + atomicity + resilience)

## Decisions Made
- `DEFAULT_KEYMAP = KEYMAP` (alias, same object) — `resolve_keymap` copies it (`dict(DEFAULT_KEYMAP)`) so the live default is never mutated.
- `resume_feed_bytes` keys the `--continue` rule on `os.path.basename(argv[0]) == "claude"` so `/usr/bin/claude` still qualifies but `aider` does not (D-03).
- Minimal hand-written TOML serializer in appconfig (bool checked before int since `bool` is an `int` subclass), deterministic section order, only the value types arduis owns — refusing `tomli-w` per D-09.

## Deviations from Plan

None - plan executed exactly as written. The implementation snippets in the plan's `<action>` blocks were used verbatim; tests cover every `<behavior>` case.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All four GTK-free contracts are pinned and tested; Plan 03 (`window.py` wiring) can read `[agent]`/`[keys]`/`[theme]` at startup and add the split/zoom/refeed cases to `_run_action` + the "Tema" menu without reshaping the spawn/feed or the prefix machine.
- Disjoint from Plan 05-01 (themes.py): no shared files. `themes.get_theme` (Plan 01) re-whitelists the `load_theme_name` result, so a bogus persisted name is harmless.

## Self-Check: PASSED

All 6 created files present on disk; all 3 task commits (`8d82c18`, `e935c75`, `360c6ad`) found in git log. Full suite: 227 passed.

---
*Phase: 05-agent-swap-tmux-keybindings-themes*
*Completed: 2026-06-13*
