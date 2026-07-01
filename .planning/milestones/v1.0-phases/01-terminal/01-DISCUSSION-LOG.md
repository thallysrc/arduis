# Phase 1: Terminal - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-08
**Phase:** 01-terminal
**Areas discussed:** Terminal theme ownership, session-sharing mechanism, distribution model (project-level pivot), shell invocation, acceptance tests, window-close teardown

---

## Terminal theme / session model

User clarified: the app must own the terminal theme per window (Dracula default,
switchable), NOT inherit colors from the host `zsh`. The shell contributes behavior
(PATH/aliases/prompt text), the app contributes the palette.

User asked how "session sharing" is done in BridgeMind. Clarified that BridgeMind (Mac, no
sandbox) just spawns the host shell via a direct PTY; the `flatpak-spawn --host` bridge was
only ever a Flatpak-sandbox necessity. Distinguished three meanings: (a) terminal↔host
connection, (b) reattach to live agent across app restart = v2/PERSIST-01, (c) same session
mirrored across panes = not v1.

**Outcome:** App owns palette (Dracula default); theme-switch UI deferred to Phase 5.

---

## "Why not just use a native PTY on Linux too?"

User asked why not create a PTY directly on Linux like BridgeMind. Clarified the PTY is not
the problem — VTE creates one regardless. The issue was only the Flatpak sandbox: a
direct-spawned child runs *inside* the sandbox (no host `zsh`/`claude`/PATH), so
`flatpak-spawn --host` was needed to escape. Natively there is no such constraint.

---

## Distribution model — PROJECT-LEVEL PIVOT

User decided: "flatpak sai do v1. e faz do jeito certo."

Verified on host: Ubuntu 24.04 ships `gir1.2-vte-3.91` / `libvte-2.91-gtk4-0` **0.76.0** in
`main` (no PPA needed); Arch has `vte4` 0.84 in `extra`.

| Option | Selected |
|--------|----------|
| Keep Flatpak primary (bundle VTE, pay `flatpak-spawn` tax) | |
| Native-first (`.deb` + AUR), Flatpak out of v1 | ✓ |
| Keep Flatpak as secondary/non-primary | |

**User's choice:** Native-first, Flatpak fully out of v1.
**Consequence:** Removes the sandbox and the entire `flatpak-spawn --host` risk class.
Phase 1 "Terminal + Sandbox Seam" → "Terminal" (direct PTY). Updated PROJECT.md, ROADMAP.md
(Phase 1 + Phase 9 + overview + Phase 7 docker notes), REQUIREMENTS.md (DIST-01 → v2,
coverage 33→32), STATE.md (blockers/decisions). `HostRunner` kept as a thin no-op seam so a
v2 Flatpak channel stays cheap.

---

## Shell invocation

**User's choice:** Agreed with recommendation — `zsh -l -i` (login + interactive) so full
env loads and `claude`/`gh`/version-manager shims resolve. `TERM=xterm-256color` forced.

## Acceptance tests

**User's choice:** Agreed — manual documented checklist for interactive Ctrl+C / Ctrl+Z+`fg` /
no-orphans; small automated unit test for `os.waitstatus_to_exitcode` decoding.

## Window-close teardown

**User's choice:** Agreed — SIGHUP to the child process group, then SIGKILL after a short
timeout. Native `os.killpg` (no sandbox indirection).

---

## Claude's Discretion

- Exact `HostRunner` API shape; font/scrollback specifics; native run/build tooling; module layout.

## Deferred Ideas

- Flatpak channel → v2 (DIST-01)
- Reattach to live agents across app restart → v2 (PERSIST-01)
- Same session mirrored across panes (tmux multiplexing) → not v1
- `CLAUDE.md` tech-stack cleanup (still describes Flatpak/VTE-bundling) → separate pass
