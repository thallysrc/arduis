---
phase: 04-attention-detection-who-s-waiting
type: security-audit
asvs_level: 2
threats_total: 24
threats_closed: 24
threats_open: 0
accepted_risks: 3
audited_by: gsd-secure-phase
date: 2026-06-13
---

# Phase 04 Security Audit — Attention Detection (Who's Waiting)

Verification of every threat declared in the five plan `<threat_model>` blocks
(T-04-01 .. T-04-24) against the implemented code. Implementation files were
treated as READ-ONLY; no source was modified. SUMMARY files carry no
`## Threat Flags` sections, so there are no unregistered flags.

**Result: 24/24 threats CLOSED (21 mitigated + verified, 3 accepted-risk).**
Full suite: `172 passed` via `/tmp/arduis-venv-ab12/bin/python -m pytest tests/ -q`.

## Threat Verification

| Threat ID | Category | Disposition | Evidence |
|-----------|----------|-------------|----------|
| T-04-01 | DoS | mitigate | `arduis_hook.py:80-85` whole body in try/except → `sys.exit(0)`; `attention.py:283` `HOOK_TIMEOUT_S = 5` pinned into every merged hook entry (`attention.py:382`) |
| T-04-02 | Tampering | mitigate | `arduis_hook.py:23-28` `json.load` wrapped, non-dict coerced to `{}`; unknown events no-op (`:54-55`); no field executed/interpolated |
| T-04-03 | Tampering | accept | `arduis_hook.py:19` only json-dumps to `ARDUIS_STATE_FILE` (set by arduis path builders); no deletes, single idle-peek read. Env-control = account-control, no escalation — accepted as planned |
| T-04-04 | Info disclosure | mitigate | `attention.py:88-101` `status_dir` → `$XDG_RUNTIME_DIR/arduis/status` (0700 tmpfs) with `~/.cache` fallback; script creates parents under that tree |
| T-04-05 | Tampering | mitigate | `spawn.py:49` `envv = TERM_ENV + (extra_env or [])` — discrete KEY=value list through `wrap_env`; argv (`SHELL_ARGV`) untouched, no shell join |
| T-04-06 | Tampering/EoP | mitigate | `attention.py:104-127` `sanitize_term_id` allowlist `[A-Za-z0-9._:-]` + `..` collapse + strip; `state_file_path` joins a flat leaf so dirname is always the status dir |
| T-04-07 | DoS | mitigate | `attention.py:154-185` `read_state` returns None on OSError/ValueError/non-dict/missing-state; never raises on the main loop |
| T-04-08 | Tampering | mitigate | `attention.py:356-389` `merged_settings` deepcopy, append-only, dedupe by `script_path in command`, idempotent; non-dict `hooks` refused (`:369-372`) |
| T-04-09 | DoS (process kill) | mitigate | `attention.py:420-440` `should_autosuspend` True only for READY/IDLE/ENDED past threshold; RUNNING/WAITING/None never; `minutes<=0` off |
| T-04-10 | Tampering | mitigate | `attention.py:458-492` typed per-key coercion; negatives → 0; wrong types → defaults; invalid TOML → `AttentionConfig()` |
| T-04-11 | Info disclosure | mitigate | `attention.py:130-150` `clear_status_dir` unlinks only non-symlink regular direct children; symlinks/subdirs skipped (no follow, no recursion) |
| T-04-12 | Tampering | mitigate | `window.py:435-456` UNPARSEABLE settings → degraded, never write; `:507-528` backup `.arduis-backup` before write + tmp + `os.replace` atomic |
| T-04-13 | Spoofing/Repudiation | mitigate | `window.py:458-505` `Adw.AlertDialog` gate; `is_installed` short-circuits silent re-runs; declined marker touched on "Agora não" |
| T-04-14 | Tampering | mitigate | `window.py:697` notification body via `GLib.markup_escape_text`; title is plain branch name (sanitized upstream) |
| T-04-15 | DoS | mitigate | `window.py:551-559` `_on_status_event` O(1) dict lookup, unknown files ignored; tolerant `read_state`; no threads (`grep` count 0) |
| T-04-16 | EoP/Tampering | mitigate | `window.py:2752-2789` — the ONLY `os.unlink` sites; paths composed exclusively via `attention.state_file_path(self._status_dir, ...)`; no other rm/rmtree in window.py (verified) |
| T-04-17 | DoS | accept | `window.py:589-611` `_pid_alive` uses `killpg(pgid, 0)`/`kill(pid, 0)` (signal 0 sends nothing); reused-pgid worst case is a stale read — accepted as planned |
| T-04-18 | DoS (process kill) | mitigate | `window.py:2338-2349` single `should_autosuspend` call site, degraded excluded (`not self._degraded`); `_auto_suspend` (`:2588`) reachable only via that gate; reuses `_hibernate_task` no-orphan path |
| T-04-19 | Spoofing | accept | Degraded bell mode is lower-confidence "esperando?" label (`window.py:2220`); no auto-suspend in degraded (`:2338`); worst case false hint, never a kill — accepted as planned |
| T-04-20 | Tampering | mitigate | `session.py` `AGENT_RESUME_FEED = b"claude --continue\n"` bytes literal, no interpolation; selected at `window.py:2164`, fed as-is |
| T-04-21 | DoS | mitigate | `window.py:2227+` `_make_activity_cb` throttled per terminal (≥1s); handler is dict-write + occasional label flip |
| T-04-22 | Repudiation | mitigate | `window.py:2588-2630` `_auto_suspend` always calls `_notify_suspended` (bypasses focus gate); sidebar subline "suspensa" |
| T-04-23 | Tampering | mitigate | `04-05-SUMMARY.md` smoke: HOME→/tmp sandbox; check "real ~/.claude untouched (mtime unchanged; no backup in real HOME)" PASS |
| T-04-24 | DoS | mitigate | `04-05-SUMMARY.md` smoke harness kills broadwayd `:91` + spawned groups in `finally`; no orphan processes |

## Accepted Risks Log

Three threats carry an explicit `accept` disposition in the plans; each is
documented and re-confirmed against the implementation:

- **T-04-03 (ARDUIS_STATE_FILE destructive target):** the env var is set by arduis
  from tested path builders; an attacker who controls the user's env already owns
  the account (same privilege, no escalation). The hook only json-dumps to that one
  path. Confirmed: `arduis_hook.py` does no deletes and only one tolerant idle-peek read.
- **T-04-17 (killpg(pgid, 0) on a reused pgid):** signal 0 delivers nothing; the worst
  case is a stale-status misread until the next event. Same probe Phase-3 RAM machinery
  already uses. Confirmed at `window.py:589-611`.
- **T-04-19 (any PTY program ringing BEL to fake "waiting"):** degraded mode is
  explicitly lower-confidence and down-labeled "esperando?"; auto-suspend is disabled in
  degraded mode, so a spoofed bell can never cause a process kill. Confirmed at
  `window.py:2220` / `:2338`.

## Unregistered Flags

None. No SUMMARY carries a `## Threat Flags` section.

## Cross-cutting Verification

- Hook script is stdlib-only (no `import gi`, no `arduis` imports) — confirmed.
- `attention.py` imports no `gi` (GTK-free policy brain) — confirmed.
- `window.py`: zero `threading`/`Thread(` occurrences; the only filesystem deletions
  are the two status-dir-scoped `os.unlink` sites — confirmed.
- Suite: 172 passed.

## Disposition

No open threats. No blockers. Phase 4 mitigations declared in PLAN.md are present
and correct in the implemented code.
