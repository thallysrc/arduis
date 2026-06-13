# Phase 07: Opt-in Isolated Containers - Context

**Gathered:** 2026-06-13
**Status:** Ready for planning
**Mode:** Autonomous — user delegated decisions and is AFK; Fable inaccessible to subagents this session (ran on Opus 4.8). Decisions adopt the recommended defaults from 07-RESEARCH.md (HIGH-confidence, behaviors verified LIVE on the host with docker 29.3.1 / compose v5.1.1). Revisitable at UAT.

<domain>
## Phase Boundary

Per-TASK isolated docker-compose stacks, OFF by default. Docker runs on the host directly through
the HostRunner seam (no-op native). The compose base is the SINGLE root `docker-compose.yml`
(already mirrored into the task folder by 03.2's `symlink_plan` — A1 CONFIRMED); a generated
`docker-compose.override.yml` in the task folder rewrites each service's `ports` via the
Compose-spec `!override` tag; `COMPOSE_PROJECT_NAME` is unique per task; ports are probed free
(deterministic offset + retry) and persisted; teardown wires into task conclude/hibernate +
app-exit; a startup pass reconciles orphaned `arduis-*` projects after a crash.

**Out of scope:** the `docker` Python SDK / python-on-whales (CLAUDE.md — shell `docker compose`
via HostRunner only); per-repo compose files (rejected by 03.2 — ONE root compose); editing the
base compose; non-compose container runtimes; secrets injection (credentials out of v1).
</domain>

<decisions>
## Implementation Decisions

### The ports override primitive (THE central finding)
- **D-01:** The override MUST use the Compose-spec **`ports: !override`** YAML tag to REPLACE a
  service's ports list. Verified live: a plain override CONCATENATES (`8080` + `19080` → both
  bind → collision); `!override` replaces (`['19080']`). This supersedes the CLAUDE.md note
  ("rewrite the whole ports list"), which was necessary but INSUFFICIENT — the tag is required.
- **D-02:** Read the base stack AUTHORITATIVELY with `docker compose config --format json` (via
  HostRunner) — resolves extends/anchors/env. Parse `services.<name>.ports[].published` (string)
  to enumerate services + published ports. Do NOT hand-parse raw YAML.

### Override generation + isolation (CONT-02/03)
- **D-03:** `COMPOSE_PROJECT_NAME = "arduis-" + sanitized(branch)` (reuse the existing branch
  sanitizer), unique per task → isolated container names / networks / volumes (isolated DB free).
  Passed as env on EVERY `docker compose` invocation. Persisted per task.
- **D-04:** The override is generated as a REAL file `<task_dir>/docker-compose.override.yml`
  using **PyYAML** (OD-1) — emitting the `!override` tag cleanly is fragile by hand. PyYAML is a
  new dependency; justified because correct `!override` emission is the load-bearing correctness
  point and PyYAML is a standard, packaged lib (`python3-yaml` on Ubuntu, `python-yaml` on Arch).
  Add it to the Phase-9 packaging dep list.
- **D-05:** Invocation: `docker compose -f <task_dir>/docker-compose.yml -f <task_dir>/docker-compose.override.yml`
  — the base is the 03.2 symlink (resolves to the root file under $HOME), the override is the
  generated real file. Both under $HOME → snap-docker can read them (D-09).

### Port probing + persistence (CONT-03/04)
- **D-06:** Deterministic per-task offset (config `port_offset = 1000`, in `~/.config/arduis/arduis.toml`
  `[containers]`); map each base published port → base+offset, then PROBE free with a stdlib
  `socket.bind(("127.0.0.1", port))` try/except, retry with the next offset step on collision.
  Persist the FINAL resolved base→host port map per task so badges/URLs stay stable across
  restarts. Document the probe-then-bind TOCTOU as accepted (the window is tiny; compose `up`
  fails visibly if lost).
- **D-07 (OD-2):** Container state (COMPOSE_PROJECT_NAME, resolved port map, on/off) persisted in
  `<task_dir>/arduis.container.toml` (disk = source of truth, consistent with 03.2; survives
  restart; GTK-free reader/writer mirroring appconfig's atomic pattern).

### Async execution + UX (criterion 5, CONT-01/04)
- **D-08:** All `docker compose` calls go through HostRunner → `Gio.Subprocess` async (mirror
  `git_service.run_git_async`), NEVER blocking the GTK loop (image pulls are slow). Three new
  modules: `compose.py` (GTK-free: override gen, sanitize, offset+probe, config-json parse),
  `containerstate.py` (GTK-free persistence), `docker_service.py` (thin async wrapper).
- **D-09:** snap-docker on Ubuntu CANNOT read compose files outside `$HOME` (verified). Production
  task folders are under `$HOME` so real use is fine; TESTS/smokes must stage fixtures under
  `$HOME`, never `/tmp`. The HostRunner path is unchanged (docker on host directly).
- **D-10 (OD-3):** Progress UX = a toast (`Adw.ToastOverlay`) + a spinner on the task row while
  `up`/`down` runs; resolved ports shown as badges on the task row (OD-4 toggle lives in the
  sidebar row context menu). This is a UI phase — DESIGN section in RESEARCH.
- **D-11 (OD-5):** Opt-in IS the trust gate — no separate dialog. Turning on isolation for a task
  (default OFF) is the explicit user action; auto-detect the root `docker-compose.yml` to even
  offer it (CONT-01).

### Teardown + crash reconciliation (CONT-05/criterion 4)
- **D-12:** `docker compose -p <name> down --remove-orphans --volumes` on task conclude/hibernate
  AND app-exit (wire into `_on_close_request` + the hibernate path). Container teardown is a
  SEPARATE channel from the existing `killpg` agent-terminal teardown (Pitfall 7 — don't conflate).
- **D-13:** Startup reconciliation: `docker compose ls --all --filter name=arduis --format json`
  → find orphaned `arduis-*` projects with no live task → offer/auto cleanup (down). Default:
  surface them and let the user reconcile (don't auto-`down -v` on startup — a running stack the
  user wants might match; be conservative with volume deletion).
</decisions>

<specifics>
## Specific Ideas
- A1 CONFIRMED: `symlink_plan` mirrors every root entry except chosen repos + `.git`, so the root
  `docker-compose.yml` AND any build-context dirs it references are already in the task folder as
  relative symlinks — `-f <task_dir>/docker-compose.yml` resolves and relative build contexts work
  verbatim. No `symlink_plan` change needed.
- TDD the GTK-free trio (`compose.py`, `containerstate.py`): override-`!override` emission,
  sanitize, offset+probe (mock socket), config-json parse, state round-trip. The window wiring +
  real `up`/`down` is headless-smoke (command argv shape) + host-only live UAT.
- Honest acceptance limit: a headless smoke can prove the override BYTES (incl. the `!override`
  tag), the argv shape of every `docker compose` call, port-probe logic (mocked sockets), and
  state persistence — but NOT a real stack coming up. Real `up`/badges/teardown/reconcile is a
  host-only live UAT item.

## Most tasks have NO compose → the feature stays OFF, strict no-op (CONT-01).
</specifics>

<deferred>
## Deferred Ideas
- Auto-`down -v` orphans on startup → conservative surface-and-confirm for v1 (volume deletion is
  destructive).
- Health-check gating / "stack ready" detection, log streaming into a pane → later degrau.
- Per-service selective up, compose profiles → as needs emerge.
</deferred>

---

*Phase: 07-opt-in-isolated-containers*
*Decisions: 13 locked (autonomous, research-recommended defaults; `!override` is the load-bearing one)*
*Ready for: planning (UI hint: yes)*
