# Phase 06: Per-Worktree Setup via `.arduis.toml` - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning
**Mode:** Autonomous — user delegated decisions and is AFK; Fable inaccessible to subagents this session (ran on Opus 4.8). Every decision adopts the recommended default from 06-RESEARCH.md (HIGH-confidence, zero new deps, all mechanisms are existing tested codebase patterns). Revisitable at UAT.

<domain>
## Phase Boundary

A new worktree is born "ready to work": each chosen repo's PER-REPO `.arduis.toml` (committed in
the repo, distinct from the user-level `~/.config/arduis/arduis.toml`) is read with sensible
defaults (NO file → strict no-op, behaves exactly as today), and its `[setup]` commands run ON
CREATION, visibly, through the SAME `zsh -l -i` login shell the agent uses (so nvm/asdf/mise
shims + PATH resolve). Running arbitrary repo-committed commands is gated by a trust prompt
(trusted-repo-only, content-hashed so a changed setup re-prompts).

**Out of scope:** secrets/credentials (CLAUDE.md — out of v1); setup on RESUME (CREATE-only — a
resumed task already has node_modules/.env); exit-code parsing / agent-gating on setup failure
(the live shell shows errors naturally); a GUI editor for `.arduis.toml` (hand-edited in the repo);
running setup for repos not chosen for the task.
</domain>

<decisions>
## Implementation Decisions

### `.arduis.toml` schema + reader (ENV-01)
- **D-01:** A NEW GTK-free `repoconfig.py` with a tolerant `tomllib` reader (clone of
  `agentconfig.load_agent_config`): reads `<repo_worktree>/.arduis.toml`, returns a typed result
  with a `[setup] commands = [...]` ordered list. Missing file / invalid TOML / wrong-typed key →
  empty commands (strict no-op). Read-only stdlib `tomllib`.
- **D-02:** Schema is minimal for v1: `[setup] commands = ["npm install", "cp .env.example .env"]`
  (ordered list of shell command strings). No other keys this phase (the file may grow later).

### Where + when setup runs (ENV-02, criteria 2/3)
- **D-03 (OD-1):** Feed setup as bytes into the repo's existing SHELL terminal (the `t1` plain
  zsh), NOT the agent terminal, BEFORE the agent is fed its command. That terminal is already
  `zsh -l -i` via HostRunner → full login env (shims/PATH) for free, visible, Ctrl+C-able. Reject
  Gio.Subprocess (non-login, invisible).
- **D-04:** Setup runs in `_finalize_task_creation` (CREATE only — never on resume; Pitfall 3).
  In the 03.2 multi-repo task model the default terminals sit at the TASK ROOT, so each repo's
  setup block is prefixed with `cd <worktree_dir>` (Pitfall 1 — directory guard).
- **D-05 (OD-6):** Commands are newline-joined per repo (each runs + shows regardless of a prior
  failure — debuggable, matches "the shell shows everything"). Only `cd <worktree_dir>` is the
  `&&` directory guard; the command LIST is NOT `&&`-chained (one failure must not hide the rest).
- **D-06 (OD-5):** No exit-code surfacing in v1 — the live shell shows stderr + non-zero exit
  naturally; failing setup must NEVER block the agent or crash task creation.

### Trust gate (criterion 4 — the security crux)
- **D-07:** Trust keyed by a **sha256 content-hash of the setup commands** (not repo path alone),
  so a `git pull` that swaps in a different/hostile `[setup]` re-prompts (direnv-allow model).
  Fail-closed: a tolerant/missing trust list → re-prompt everything.
- **D-08 (OD-2):** ONE consolidated `Adw.AlertDialog` per task creation, grouping commands under
  each repo name, showing the EXACT commands, with "Confiar e rodar" / "Pular". Repos whose
  current setup-hash is already trusted are omitted from the dialog and run silently. Mirrors the
  Phase-4 `_present_hook_consent` pattern.
- **D-09 (OD-3):** Trust identity = `os.path.realpath(<project_root>/<repo_name>)` (the repo
  SOURCE dir on this machine — deterministic, no extra git call). Combined with the content-hash:
  a trust record is `{repo_realpath: sha256(commands)}`.
- **D-10 (OD-4):** Trust list persisted at `~/.config/arduis/trusted_setups.toml`, `[trusted]`
  table `{repo_path = sha256hex}`, written via the existing `appconfig._serialize` atomic
  tmp+`os.replace` idiom. GTK-free reader/writer.
</decisions>

<specifics>
## Specific Ideas
- The trust dialog must show the literal commands so the user sees what they're authorizing (no
  hidden execution) — this IS the security control. "Pular" leaves the worktree created but
  un-setup (the user can run commands by hand in the shell pane).
- TDD: new `tests/test_repoconfig.py` (schema/tolerant-read) + `tests/test_trust.py`
  (hash identity, trust persistence, changed-setup-re-prompts, fail-closed). The window wiring
  (dialog + feed) is verified via the headless broadway smoke + live UAT.
- Setup feed reuses the Phase-5 `feed_child` path; the directory guard `cd <worktree_dir> &&` is
  the only structural addition to the fed bytes.
</specifics>

<deferred>
## Deferred Ideas
- Setup on manual resume of a never-setup task → out of v1 (run by hand in the shell pane).
- Soft "setup falhou" surfacing / exit-code parsing → later degrau if dogfooding demands it.
- Richer `.arduis.toml` schema (env vars, per-command cwd, ordering hints) → as needs emerge.
- Remote-URL trust identity (portable across checkouts) → v1 uses realpath; revisit if needed.
</deferred>

---

*Phase: 06-per-worktree-setup-via-arduis-toml*
*Decisions: 10 locked (autonomous, research-recommended defaults)*
*Ready for: planning*
