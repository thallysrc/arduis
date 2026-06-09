# Phase 1 — Terminal: Manual Acceptance Checklist (D-14)

This is the human acceptance gate for Phase 1 (TERM-01). The interactive PTY
signals (Ctrl+C, Ctrl+Z/`fg`), real GTK/VTE rendering, no-orphan teardown
timing, and the Wayland session **cannot** be asserted by an automated command
on the X11 dev host — hence a manual checklist. Exit/signal decoding itself is
covered by the automated unit tests (`tests/test_exit_decode.py`).

## Prerequisites

The GTK4 VTE binding must be installed (verified absent on the dev host in
`01-RESEARCH.md` — only the GTK3 `Vte-2.91` typelib was present):

```bash
# Ubuntu 24.04
sudo apt install -y gir1.2-vte-3.91 libvte-2.91-gtk4-0
# Arch
sudo pacman -S --needed vte4
```

Confirm the binding imports:

```bash
python3 -c "import gi; gi.require_version('Vte','3.91'); from gi.repository import Vte; print('vte-ok')"
```

Then launch the app from the repo root:

```bash
./run.sh
```

---

## Criterion #1 — Working host shell in the app's Dracula palette

**Steps**
1. Run `./run.sh`.
2. Confirm a GTK4/libadwaita window titled **arduis** opens with a single terminal.
3. Confirm your own `zsh` prompt appears (your prompt text, aliases, functions).
4. Confirm the **background is `#282a36`** (Dracula) and the foreground/ANSI
   colors are the app's Dracula palette — i.e. the colors come from arduis, not
   from whatever theme your shell would otherwise impose (D-06/D-07).

**Expected:** A live host `zsh` rendered in the app-owned Dracula palette.

**Sign-off:** PASS / FAIL — date: __________ — distro/session: __________

---

## Criterion #2 — `claude` / `gh` / `docker` resolve (login+interactive shims)

**Steps**
1. In the embedded terminal, run:
   ```bash
   which claude gh docker
   ```

**Expected:** each returns a path (the login+interactive `zsh -l -i` loaded
`.zprofile`/`.zshrc`, so PATH and version-manager shims resolve — D-09). If any
prints `command not found` but works in a normal terminal, the login/interactive
flags regressed.

**Sign-off:** PASS / FAIL — date: __________ — distro/session: __________

---

## Criterion #3 — Signals & job control (Ctrl+C, Ctrl+Z/`fg`)

**Steps**
1. Run `sleep 100`, then press **Ctrl+C** → you return to the prompt immediately.
2. Run `sleep 100` again, then press **Ctrl+Z** → the shell reports the job
   *suspended*; run `fg` → the `sleep` resumes in the foreground (D-11).

**Expected:** Ctrl+C interrupts the child; Ctrl+Z suspends and `fg` resumes.

**Sign-off:** PASS / FAIL — date: __________ — distro/session: __________

---

## Criterion #4 — No orphans on close + correct exit/signal decode

**No-orphan teardown (D-13):**
1. In the embedded terminal, note the shell PID: `echo $$`.
2. Close the arduis window.
3. From **another** terminal, confirm no leftover child:
   ```bash
   pgrep -af zsh                       # the closed window's zsh must NOT appear
   ps -o pid,pgid,cmd -g <pgid>        # using the pgid of the noted PID — empty
   ```

**Expected:** `close-request` sends `SIGHUP` to the child **process group**, then
`SIGKILL` after ~1.5s; no leftover host `zsh`/agent remains.

**Exit/signal decode (D-12):**
4. In a fresh run, type `exit 42` in the terminal → the window closes (and, if
   logged, `self._last_exit == 42`).
5. In another fresh run, start a `sleep 100` and press **Ctrl+C**; if the shell
   then exits, the decoded value for a SIGINT-terminated child is `-2`
   (`os.waitstatus_to_exitcode` maps signal death to `-signum`). The decode
   itself is independently verified by `tests/test_exit_decode.py`
   (0 → 0, 42 → 42, SIGINT → -2).

**Sign-off:** PASS / FAIL — date: __________ — distro/session: __________

---

## Criterion #5 — Runs under real Wayland on Ubuntu 0.76 + Arch 0.84

**Caveat (Pitfall 6):** the dev host session is currently **X11**
(`XDG_SESSION_TYPE=x11`), so a real-Wayland check cannot be done in that session.
Functional behavior (PTY signals, teardown, palette) is backend-independent, so
this is a **coverage check**, not a code concern.

**Steps**
1. Log into a **real Wayland session** (or run under a nested compositor /
   `GDK_BACKEND=wayland`).
2. On **Ubuntu 24.04** (system `gir1.2-vte-3.91` **0.76**): repeat criteria #1–#4.
3. On **Arch** (`vte4` **0.84**): repeat criteria #1–#4.
4. Code targets the VTE **0.76 API floor**, so the same codebase must run on both
   without version guards.

**Expected:** identical behavior under Wayland on both distros. If a real Wayland
session is unavailable now, record X11-only coverage and the reason.

**Sign-off:** PASS / FAIL / NOT-RUN (reason) — date: __________ — distro/session: __________

---

## Phase 1 Gate

Phase 1 acceptance passes when criteria **#1–#4 are PASS** and **#5** is recorded
with its session type (X11-only coverage noted if Wayland is unavailable).
