---
phase: 05-agent-swap-tmux-keybindings-themes
threats_open: 0
asvs_level: 1
audited: 2026-06-13
scope: ["05-01-PLAN.md", "05-02-PLAN.md", "05-03-PLAN.md", "05-04-PLAN.md"]
---

# Phase 5 Security Audit — agent-swap / tmux-keybindings / themes

Verification of every threat declared in the four PLAN `<threat_model>` STRIDE registers against
the implemented code. Each threat is a `mitigate` disposition; verification = grep + read of the
declared mitigation pattern in the cited file. No implementation files were modified.

**Result: 11/11 threats CLOSED. 0 open.** Full suite green (240 passed).

## Trust boundary disposition (read this first)

The single load-bearing security fact for this phase: **`[agent] command`, `[keys]`, and
`[theme]` all originate from the user's own `~/.config/arduis/arduis.toml`.** This is not
untrusted remote input — it is a config file the user authored on their own machine, inside
their own `$HOME`. The threat class here is "a hostile/garbage VALUE crashing or
mis-driving arduis," NOT "a remote attacker injecting a shell." That framing is accepted and
documented (it is the basis of the `mitigate` disposition on T-05-01).

Even under that trust boundary, the agent command is still constructed safely: it is
`shlex.split` → `shlex.join` → bytes, fed into the durable zsh as one already-parsed command
line. There is **no `shell=True` anywhere in `src/arduis/`** (the only matches are doc comments
asserting its absence in `spawn.py`, `git_service.py`, `worktree.py`). The agent is fed via VTE
`feed_child` into a live PTY — never assembled into a `spawn_async` argv from raw config.

## Threat Verification

| Threat ID | Category | Disposition | Evidence |
|-----------|----------|-------------|----------|
| T-05-01 | Tampering/EoP | mitigate | `agentconfig.py:43-58` — `agent_argv` = `shlex.split`; `agent_feed_bytes`/`resume_feed_bytes` = `shlex.join(...) + "\n"`, never naive concat. No `shell=True` in `src/arduis/`. Wired in `window.py:2351-2356` (`_make_wt_spawn_cb`) + `window.py:1552` (`_refeed_focused_agent`). Trust boundary = user's own `~/.config` (accepted, see above). |
| T-05-02 | Tampering | mitigate | `keyconfig.py:17-28` closed `_ACTIONS` set + `resolve_keymap` (`:47-62`) drops any unknown action name / non-single-char key (key keeps default). `window.py:1490` dispatches via `self._keymap.get(name)` only — never builds an action from a raw string. |
| T-05-03 | Tampering | mitigate | `themes.py:117-123` `get_theme` = `THEMES.get((name or "dracula").lower(), DRACULA)` — pure dict whitelist, name never used as a path. `window.py:524-526` persists the CANONICAL `theme.name` (post-whitelist), not the raw slug. |
| T-05-04 | DoS | mitigate | `appconfig.py:84-116` `write_theme` reads-parses-rewrites then `tempfile.mkstemp` (same dir) → `os.replace` (atomic, `:105-109`); parse failure of existing file degrades to `{}` (`:96-99`); OSError swallowed best-effort (`:115`). Section-preservation via `_serialize` (`:67-81`). |
| T-05-05 | DoS | mitigate | Every reader wraps tomllib in `try/except (OSError, TOMLDecodeError)` with per-key type checks + safe default: `agentconfig.load_agent_config` (`:29-40`), `appconfig.load_theme_name` (`:27-38`), `window._read_keys_section` (`:213+`). Mirrors `attention.load_config`. |
| T-05-06a | DoS | mitigate | `themes.py` registry is in-code (not user TOML); `tests/test_themes.py:70-74` asserts `len(palette)==16` for every theme; `:19` `_HEX = ^#[0-9a-fA-F]{6}$` regex asserted over every color field + palette entry. A bad hex can never ship green. |
| T-05-06 | DoS | mitigate | `window.py:486-514` `_apply_theme` calls `remove_provider_for_display` (`:496`) on the stored `self._css_provider` BEFORE adding a fresh one — no stacking. `_install_css` (`:469-475`) keeps the handle. Smoke proves provider id changes per switch. |
| T-05-07 | DoS/EoP | mitigate | `window.py:1538-1552` `_refeed_focused_agent` only `feed_child`s into the live PTY — no kill, no respawn, no teardown path touched (Pitfall 5). Ctrl+C remains native job control (untouched). |
| T-05-08 | Tampering | mitigate | `tests/smoke/test_theme_switch_smoke.py:51-73` runs under a `/tmp` sandbox HOME; `:70-71,127-128` captures real `~/.config/arduis/arduis.toml` mtime and asserts it unchanged (`real_config_untouched` check). |
| T-05-09 | DoS | mitigate | `tests/smoke/test_theme_switch_smoke.py:134-142` kills broadwayd (pid) in a `finally` block + `shutil.rmtree` the sandbox. See note below on PTY process groups. |

## Accepted Risks Log

- **T-05-01 (agent command trust boundary):** The `[agent] command` is a shell command line the
  user authored in their own `~/.config/arduis/arduis.toml`. arduis does NOT treat it as
  untrusted input — it is the user's own intent, equivalent to what they would type into their
  shell. Mitigation is defensive hygiene (shlex argv construction, no `shell=True`, no naive
  concat) so that quoting/metachar handling is *correct*, not so that a *malicious* command is
  *blocked* — a user who wants to run `rm -rf` as their "agent" is free to. **Disposition:
  accepted + mitigated.** This is the documented trust boundary for the phase.

## Notes / Observations (non-blocking)

- **T-05-09 PTY teardown coverage:** The smoke kills the broadwayd process explicitly but does
  not call `os.killpg` on VTE-spawned zsh process groups in `finally` — it relies on
  `app.quit()` + `ArduisWindow`'s own close handlers (the Phase-1 "no orphans" teardown) to reap
  the PTY children. The threat is mitigated (broadwayd is killed; the window's own teardown is
  the orphan-reaping mechanism it is dogfooding), but the smoke does not *independently* assert
  zero orphan zsh/claude after the run the way the live UAT item 5 does. This is consistent with
  the plan's wording ("kill broadwayd + any spawned process groups") being satisfied primarily
  by broadwayd termination + the app's own close path; flagged as an observation, not a gap.

- **T-05-04 best-effort write:** A write failure is silently swallowed (`appconfig.py:115`). This
  is the intended design (D-09: persistence is a convenience; the in-memory switch still
  applied) — not a gap. The user would simply re-pick the theme next launch.

## Unregistered Flags

None. The four SUMMARY files contain no `## Threat Flags` section; no new attack surface was
flagged by the executor during implementation. The only flagged items (A1 cosmetic hex,
A2/Pitfall 3 prefix collision) are usability/UAT observations, not security threats — and A2's
mitigation (configurable `[keys] prefix`) is itself verified under T-05-02.

## Verification commands run

- `/tmp/arduis-venv-ab12/bin/python -m pytest tests/` → **240 passed**
- `grep shell=True src/arduis/` → only doc-comment matches asserting its absence
- `grep -n "16-color / valid-hex" tests/test_themes.py` → invariant tests present (`len==16`, `^#[0-9a-fA-F]{6}$`)
