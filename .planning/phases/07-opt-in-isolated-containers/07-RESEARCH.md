# Phase 7: Opt-in Isolated Containers - Research

**Researched:** 2026-06-13
**Domain:** docker compose orchestration via shell-out (HostRunner) + GTK4 async wiring
**Confidence:** HIGH (the load-bearing claims — ports-concatenate gotcha, `!override` fix, snap-docker confinement, compose JSON shapes — were all verified live on the host with docker 29.3.1 / compose v5.1.1)

## Summary

Phase 7 adds per-TASK isolated docker-compose stacks, OFF by default. The mechanism is almost
entirely "build argv → run `docker compose ...` through the `HostRunner` seam → parse JSON".
There is **no Python docker library** (CLAUDE.md "What NOT to Use"), and the isolation primitive is
`COMPOSE_PROJECT_NAME` per task, which gives separate container names, networks, and volumes (an
isolated DB per task for free). The compose base is the SINGLE root `docker-compose.yml` read from
the meta-repo's `main`; arduis generates a `docker-compose.override.yml` into the task folder (which
mirrors the root layout, so relative build contexts/bind-mounts resolve verbatim).

The single most important finding, **verified live on this host**, overturns a naive reading of
CLAUDE.md's "rewrite the WHOLE `ports` list" guidance: **a normal override file does NOT replace the
ports list — Compose CONCATENATES it.** An override adding `19080:80` to a base `8080:80` yields BOTH
ports published (`['8080','19080']`), so every task's stack would also re-bind the original host port
→ guaranteed collision with `main`'s stack and across tasks. The fix, also verified live, is the
Compose-spec `!override` YAML tag (`ports: !override`), which replaces the list entirely
(`['19080']`). This is THE central design constraint for the override generator. [VERIFIED: live
`docker compose config` on host, 2026-06-13]

Second critical finding: **the host docker is SNAP docker** (`/snap/bin/docker`, 29.3.1). Snap
confinement means `docker compose -f <path>` **cannot read files outside `$HOME`** (a `-f /tmp/...`
path returns "no such file or directory"). The user's real task folders live under `../<root>-tasks/`
(a sibling of the project, inside `$HOME`) so production is fine — but **smoke tests that stage compose
files under `/tmp` will fail on Ubuntu/snap**, and the planner must stage test fixtures under `$HOME`.
On Arch (native docker) there is no such restriction. [VERIFIED: live on host, 2026-06-13]

**Primary recommendation:** Use `docker compose config --format json` (through HostRunner, async) as
the AUTHORITATIVE reader of the base stack's services + published ports (no new dep, resolves
env/extends/anchors), then generate a minimal `docker-compose.override.yml` that, per service with a
remapped port, emits `ports: !override` with the offset-and-probed host port list. Write the override
with **PyYAML** (already installed; the `!override` tag needs a custom representer but is trivial) OR a
tiny hand-rolled emitter mirroring `appconfig._serialize` — recommend PyYAML for ports-with-tag
correctness (see Open Decision OD-1). Persist `COMPOSE_PROJECT_NAME` + the resolved port map per task
in a small state file in the task folder (disk = source of truth, matching 03.2). All compose calls go
through `HostRunner.wrap_argv` + `Gio.Subprocess` async, never blocking the GTK loop.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `docker compose` CLI (shell-out) | host: 29.3.1 / compose v5.1.1 [VERIFIED] | Bring up/down/inspect the per-task stack | CLAUDE.md mandates shell-out via HostRunner; no Python docker SDK |
| `Gio.Subprocess` + `communicate_utf8_async` (PyGObject) | system | Async compose calls off the GTK loop | CLAUDE.md primary concurrency tool; same pattern as `git_service.run_git_async` |
| `HostRunner.wrap_argv` (`src/arduis/host_runner.py`) | in-repo | Single host-exec funnel (no-op native) | CLAUDE.md load-bearing seam; every compose call routes through it |
| `socket` (stdlib) | 3.12 | Probe a candidate host port free before `up` | Zero dep; `bind()` try/except is the standard probe |
| `tomllib` (stdlib) read / atomic-write (mirror `appconfig`) | 3.11+ | Persist project-name + resolved port map per task | Matches existing config persistence; no tomli-w |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| PyYAML | 6.0.1 [VERIFIED installed] | Parse base compose (fallback) + WRITE the override with the `!override` tag | Recommended for writing the override (tag correctness); see OD-1 |
| `shlex` (stdlib) | 3.12 | Not needed — argv stays a list literal | Only if any human-facing command echo is built (avoid) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `docker compose config --format json` to read services/ports | PyYAML parse of raw `docker-compose.yml` | Raw parse misses `extends`, env-interpolation, anchors, and multiple base files; `compose config` returns the RESOLVED model and is authoritative. **Read via `config`, not raw YAML.** [VERIFIED shape on host] |
| PyYAML to WRITE the override | Hand-rolled emitter (like `appconfig._serialize`) | Hand-roll avoids a dep but must correctly emit the `!override` tag and quoted `"host:container"` strings — fiddly. PyYAML is already installed and is a system package on both distros. See OD-1. |
| `docker compose` CLI | `docker` PyPI SDK / `python-on-whales` | CLAUDE.md "NEVER here — adds deps + two execution models". |

**Installation:** Nothing to install for the core path. If PyYAML is chosen as a hard dep for writing
the override, it is `python3-yaml` (Ubuntu) / `python-yaml` (Arch) — both system packages, add to the
Phase 9 packaging deps. (Already present on the dev host.)

**Version verification (host, 2026-06-13):**
- `docker --version` → `Docker version 29.3.1` [VERIFIED]
- `docker compose version` → `Docker Compose version v5.1.1` [VERIFIED]
- `python3 -c "import yaml; print(yaml.__version__)"` → `6.0.1` [VERIFIED]
- docker is **snap** (`readlink -f $(which docker)` → `/usr/bin/snap`; `snap list docker` → 29.3.1 rev 3505) [VERIFIED]

## Architecture Patterns

### Recommended module structure
```
src/arduis/
├── compose.py            # NEW — GTK-free: argv builders + parse compose-config JSON
│                         #   + port-offset+probe + override-doc generation + sanitize project name
├── containerstate.py     # NEW — GTK-free: read/atomic-write per-task container state
│                         #   (project_name + resolved port map), mirrors appconfig atomic write
├── docker_service.py     # NEW — thin gi module: run compose argv async via Gio.Subprocess
│                         #   (mirrors git_service.run_git_async — the ONLY new gi-importing svc)
└── window.py             # wiring: opt-in toggle, badges, up/down, teardown + startup reconcile
```
This mirrors the established split exactly: GTK-free tested logic (`worktree.py`, `attention.py`,
`appconfig.py`) + one thin async service (`git_service.py`) + window orchestration.

### Pattern 1: Authoritative stack read via `docker compose config --format json`
**What:** Resolve the base stack's services and their published ports from the model Compose itself
computes — not a raw YAML parse.
**When to use:** Before generating the override (to enumerate which services have published ports).
**Example (verified shape on host):**
```jsonc
// Source: `docker compose -f <base> config --format json` on host, 2026-06-13
// services.<name>.ports is a LIST of long-form dicts:
{
  "web": { "ports": [
    { "mode": "ingress", "target": 80,   "published": "8080", "protocol": "tcp" },
    { "mode": "ingress", "host_ip": "127.0.0.1", "target": 9000, "published": "9000", "protocol": "tcp" }
  ]},
  "db":  { "ports": [
    { "mode": "ingress", "target": 5432, "published": "5432", "protocol": "tcp" }
  ]}
}
```
Note `published` is a STRING; `target` is an INT; `host_ip` is present only when the base pinned it.
[VERIFIED: live on host]

### Pattern 2: Override generation with `ports: !override` (the load-bearing pattern)
**What:** Per service that publishes a host port, emit a `ports: !override` list with the
offset+probed host ports — REPLACING the base list, not appending.
**Why:** Verified live — a plain override CONCATENATES (`['8080','19080']`); `!override` REPLACES
(`['19080']`). [VERIFIED: live `docker compose config` on host]
**Example override the generator should produce:**
```yaml
# generated into <task_dir>/docker-compose.override.yml
# Source: Compose merge spec — !override replaces, default appends
services:
  web:
    ports: !override
      - "19080:80"
      - "127.0.0.1:20000:9000"
  db:
    ports: !override
      - "16432:5432"
```
Preserve `host_ip` when the base had it (`"127.0.0.1:20000:9000"`); the published number is
`base_published + offset` after probing.

### Pattern 3: COMPOSE_PROJECT_NAME isolation, passed as argv env (not a `.env` file)
**What:** A unique, persisted project name per task: `arduis-<sanitized-branch>`. Pass it on every
invocation. Precedence: the `-p` flag wins over the env var over `name:` over the directory name.
**Recommendation:** use the **`-p <name>` flag** on every call (highest precedence, explicit, no env
plumbing) AND/OR `COMPOSE_PROJECT_NAME` in the env list — pick `-p` as primary (deterministic, visible
in argv). [CITED: docs.docker.com/compose/how-tos/project-name]
**Sanitization (constraint, verified from docs):** project names must be lowercase letters, digits,
dashes, underscores, and must **begin with a lowercase letter or digit**. The `arduis-` prefix
satisfies the leading-char rule; sanitize the branch by lowercasing and replacing every other char
with `-` (then collapse repeats). [CITED: docs.docker.com/compose/how-tos/project-name]
```python
import re
def sanitize_project_name(branch: str) -> str:
    s = re.sub(r"[^a-z0-9_-]+", "-", branch.lower()).strip("-")
    return f"arduis-{s}" if s else "arduis-task"
```

### Pattern 4: Port probe (stdlib socket bind) + deterministic offset
**What:** `published_host = base_published + port_offset` (config `port_offset = 1000`), then PROBE
each candidate free; on collision, retry with an incremented offset step until free; persist the final
map.
**Probe (verified on host):**
```python
import socket
def port_free(port: int, host: str = "127.0.0.1") -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)  # strict — no reuse
    try:
        s.bind((host, port)); return True
    except OSError:
        return False
    finally:
        s.close()
```
[VERIFIED: live — `port_free(8080)` returned False because the user's stack holds it; `port_free(59999)` True]
**Which host:** probe `127.0.0.1` (loopback). Compose published ports default to `0.0.0.0`, but a
loopback bind is the conservative free-check (if loopback is taken the wildcard bind would also fail
for that port). Preserve the base's `host_ip` in the generated string. The TOCTOU race (probe-then-
`up`) is acceptable and documented (Pitfall 6).

### Pattern 5: Async compose call (mirror `git_service.run_git_async`)
**What:** A thin `docker_service.run_compose_async(argv, on_done, runner)` that wraps argv through
`HostRunner` and runs `Gio.Subprocess` with `communicate_utf8_async`. Identical shape to the existing
`git_service.run_git_async` (lines 30–47 of `git_service.py`).
**Example:**
```python
# Source: in-repo pattern, src/arduis/git_service.py
def run_compose_async(argv, on_done, runner=None):
    wrapped = (runner or HostRunner()).wrap_argv(argv)
    proc = Gio.Subprocess.new(
        wrapped,
        Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE,
    )
    def _cb(p, res):
        ok, out, err = p.communicate_utf8_finish(res)
        on_done(p.get_exit_status(), out or "", err or "")
    proc.communicate_utf8_async(None, None, _cb)
```
`docker compose up -d` can take minutes (image pull) — async is mandatory (Pitfall 3).

### Anti-Patterns to Avoid
- **Plain override of `ports` (no `!override` tag):** silently DOUBLE-publishes the base port → host
  collision. The single biggest trap in this phase. [VERIFIED]
- **Raw-YAML parsing the base compose to read ports:** misses `extends`/anchors/env-interpolation/
  multiple files. Use `docker compose config --format json`. [VERIFIED shape]
- **Blocking `subprocess.run(["docker","compose","up"])` on the GTK loop:** freezes the UI during pulls.
- **Staging test compose files under `/tmp`:** snap docker can't read them on Ubuntu. Stage under `$HOME`.
- **Assuming `pgid == pid` / killing docker by signal:** containers are owned by the docker daemon, not
  arduis's process tree — teardown is `docker compose down`, NOT `os.killpg`. (The killpg machinery is
  for the AGENT terminals only.)

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Resolve services + published ports of the stack | A YAML parser that walks `extends`/anchors/env | `docker compose config --format json` | Compose's own resolver is authoritative; raw parse is wrong for real stacks [VERIFIED] |
| Replace the ports list in the override | A post-merge port deduper | The `!override` YAML tag | The spec gives an exact primitive; deduping after concat is fragile [VERIFIED] |
| Per-task isolation (names/networks/volumes) | Manual name-prefixing of every resource | `COMPOSE_PROJECT_NAME` / `-p` | Compose namespaces ALL resources by project for free, incl. an isolated DB volume |
| Talk to the docker daemon | docker PyPI SDK / python-on-whales | `docker compose` CLI via HostRunner | CLAUDE.md forbids the dep; CLI is the contract |
| Find orphaned stacks after a crash | A custom container registry | `docker compose ls --all --filter name=arduis --format json` | Compose tracks projects; one command lists them [VERIFIED shape] |

**Key insight:** This phase is a thin, well-tested *translation layer* over the compose CLI. Every
piece of real logic has a CLI/spec primitive — the risk is in the GENERATION correctness (the
`!override` tag, sanitization, offset map) and the ASYNC wiring, not in any algorithm.

## Runtime State Inventory

> Phase 7 is greenfield feature work (new modules + window wiring), not a rename/refactor. The only
> persisted state this phase INTRODUCES is per-task container state (project name + resolved ports),
> covered below under DESIGN. No existing stored data / OS-registered state / secrets are renamed.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None renamed. NEW: per-task `arduis.container.toml` (project name + port map) in the task folder | new write path only |
| Live service config | NEW: docker stacks named `arduis-*` (created by this phase) | teardown + startup reconcile (designed below) |
| OS-registered state | None — containers are daemon-owned, torn down via `compose down` | none |
| Secrets/env vars | None — `COMPOSE_PROJECT_NAME`/`-p` is derived, not secret | none |
| Build artifacts | None | none |

## Common Pitfalls

### Pitfall 1: `ports` concatenate — the base port survives the override (HIGHEST RISK)
**What goes wrong:** Generated `docker-compose.override.yml` lists `19080:80` but Compose ALSO keeps
the base `8080:80`, so the task's stack tries to bind 8080 too → collides with `main`'s running stack
and with sibling tasks; `up` fails or, worse, two tasks fight over the same port.
**Why it happens:** Compose merge rule: multi-value options (`ports`, `expose`, `dns`, …) are
**concatenated**, not replaced. [VERIFIED: live + CITED: docs.docker.com/reference/compose-file/merge]
**How to avoid:** Emit `ports: !override` (replaces the list). [VERIFIED live: `['8080','19080']`
without tag vs `['19080']` with tag]
**Warning signs:** A generated config that, under `docker compose config`, still shows the original
published port.

### Pitfall 2: snap docker cannot read compose files outside `$HOME`
**What goes wrong:** `docker compose -f /tmp/.../docker-compose.yml ...` → "no such file or
directory" on Ubuntu (snap), even though the file exists. Production task folders are under
`../<root>-tasks/` (inside `$HOME`) so real use is fine, but TESTS that stage fixtures in `/tmp` fail.
**Why it happens:** snap strict confinement only exposes `$HOME` (+ `removable-media`, etc.). Native
docker on Arch has no such limit. [VERIFIED: live — `/tmp` failed, `$HOME` succeeded]
**How to avoid:** Stage all smoke/integration fixtures under `$HOME` (e.g. a temp dir created with
`tempfile.mkdtemp(dir=os.path.expanduser("~"))`). Document this for the test author. The dev MEMORY
note already uses a `/tmp` venv for pytest — the venv is fine; only the COMPOSE FILE PATHS must be
under `$HOME`.
**Warning signs:** Tests green on Arch, red on Ubuntu (or vice-versa) with file-not-found from docker.

### Pitfall 3: `up` is slow (image pull) — must be async + show progress
**What goes wrong:** First `up` of a never-pulled image blocks for minutes; a sync call freezes the GTK
loop and looks hung.
**How to avoid:** `Gio.Subprocess` async (Pattern 5); surface progress (see DESIGN — spinner on the
toggle + stream into a dedicated pane/terminal). Disable the toggle while a compose op is in flight.
**Warning signs:** UI unresponsive after flipping the isolation toggle.

### Pitfall 4: override must live where relative build contexts resolve
**What goes wrong:** A base service with `build: ./backend` or a relative bind-mount `./data:/data`
resolves relative to the override file's directory; if the override lives somewhere that doesn't
mirror the root, the context path is wrong.
**Why it's already handled:** The task folder mirrors the root layout (worktrees keep the repo dir
names, the rest is relative symlinks — `symlink_plan` in `task_layout.py`, materialized in
`_create_task` window.py:1976). Generating the override INTO the task folder means relative paths
resolve verbatim. **Verify** the symlink set already covers a root `docker-compose.yml` and any
build-context dirs the base references. [ASSUMED — see Assumptions A1]
**How to avoid:** Read the base from `main` but `-f <task_dir>/docker-compose.yml` (the mirrored copy/
symlink) + `-f <task_dir>/docker-compose.override.yml` so BOTH resolve under the task folder.

### Pitfall 5: partial `up` failure (some services up, one fails)
**What goes wrong:** `up -d` brings up 3 of 4 services then errors; the toggle is "on" but the stack is
half-up, and the persisted port map may be partly stale.
**How to avoid:** On non-zero `up` exit, treat the task as NOT isolated: run `down` to clean the
partial stack, surface the error, leave the toggle OFF. Persist ports only AFTER a successful `up`.
**Warning signs:** Containers running for a task whose toggle reads "off".

### Pitfall 6: port-probe TOCTOU (probe-then-`up` race)
**What goes wrong:** A port probes free, but another process (or another task's near-simultaneous
`up`) binds it before this task's `up` runs.
**How to avoid:** Accept the race (documented). Serialize `up` operations (one compose op in flight at
a time — the toggle is disabled during an op anyway). On `up` failure whose stderr indicates a port
collision, re-probe from a higher offset and regenerate the override once before giving up.
**Warning signs:** Intermittent "port is already allocated" on `up`.

### Pitfall 7: teardown is `compose down`, NOT killpg
**What goes wrong:** Reusing the agent-terminal `_teardown_pgid` machinery on containers does nothing
(containers are daemon children, not in arduis's process group) → orphaned containers leak RAM (the
exact thing this phase is supposed to prevent).
**How to avoid:** Container teardown = `docker compose -p <name> down --remove-orphans --volumes` via
HostRunner. Wire it into `_hibernate_task` (window.py:2815) and `_on_close_request` (window.py:3072)
ALONGSIDE the existing pgid teardown — they are two separate teardown channels.
**Warning signs:** `docker compose ls` shows `arduis-*` projects after the app closed / a task
hibernated.

## Code Examples

### Build the compose argv set (project name, base from main, override in task folder)
```python
# Source: in-repo HostRunner + verified flags on host
def compose_argv(project: str, task_dir: str, *cmd: str) -> list[str]:
    base = f"{task_dir}/docker-compose.yml"          # mirrored under task_dir (Pitfall 4)
    override = f"{task_dir}/docker-compose.override.yml"
    return ["docker", "compose", "-p", project, "-f", base, "-f", override, *cmd]
# up:   compose_argv(p, d, "up", "-d")
# down: compose_argv(p, d, "down", "--remove-orphans", "--volumes")
```

### Read base ports authoritatively
```python
# Source: verified `config --format json` shape on host
argv = ["docker", "compose", "-f", f"{task_dir}/docker-compose.yml", "config", "--format", "json"]
# run async via docker_service; in on_done:
model = json.loads(stdout)
for svc, spec in model.get("services", {}).items():
    for p in spec.get("ports", []):
        target = int(p["target"]); published = int(p["published"])
        host_ip = p.get("host_ip")   # preserve if present
```

### Startup orphan reconcile
```python
# Source: verified `docker compose ls` JSON shape on host
argv = ["docker", "compose", "ls", "--all", "--filter", "name=arduis", "--format", "json"]
# on_done: json.loads(stdout) -> [{"Name": "arduis-feat-x", "Status": "exited(1)", "ConfigFiles": "..."}]
# for each arduis-* project with no matching live task -> offer/auto `down --remove-orphans --volumes`
```
[VERIFIED: `docker compose ls --all --format json` returns a list of `{Name,Status,ConfigFiles}` on host]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Override ports by listing them (assume replace) | `ports: !override` to replace | Compose Spec / Docker Compose ≥ v2.24.4 (host has v5.1.1) | Without the tag, ports double — THE phase gotcha [VERIFIED] |
| `docker-compose` (v1, python) | `docker compose` (v2/v5 plugin, Go) | v2 GA 2021+ | argv is `docker compose ...`; `--format json` available [VERIFIED] |
| Per-repo compose files | ONE root compose covering all services | 03.2 re-anchor (2026-06-10) | one shared network, atomic duplication (CLAUDE.md) |

**Deprecated/outdated:**
- `docker-compose` (hyphen, v1) — host uses the `docker compose` plugin. Build argv as
  `["docker", "compose", ...]`.
- `version:` top-level key in compose files — obsolete in the Compose Spec (harmless if present).

## DESIGN: Opt-in toggle + port badges (UI hint: yes)

This is a UI phase. The design rides the EXISTING sidebar-row + pane-header-badge machinery.

### Auto-detect (CONT-01)
- The feature is AVAILABLE for a project only if a root `docker-compose.yml` (or `compose.yaml`)
  exists at `self._project_root`. Check once at project resolve; if absent, the toggle is hidden/
  insensitive everywhere (most tasks have no compose → strict no-op, like the Phase-6 missing-file
  case). [ASSUMED A2 — confirm the filename set; default to `docker-compose.yml` then `compose.yaml`]

### Opt-in toggle (CONT-01/02), default OFF
- A per-task toggle. **Recommended home:** the sidebar row's right-click menu (where Hibernate/Resume
  already live — window.py `_make_row_menu_cb`), entry **"Isolar containers"** (checkbox/toggle). This
  matches the established interaction model and needs no new chrome.
- Default OFF (the heaviest RAM line item — never auto-on). Flipping ON runs: read base ports → offset
  +probe → generate override → persist → `up -d` (all async). Flipping OFF runs `down
  --remove-orphans --volumes` and clears the running state (KEEP the persisted port map so re-enabling
  reuses stable ports — badges/URLs stay stable across restarts, criterion 3).
- Disable the toggle + show a spinner while a compose op is in flight (Pitfall 3).

### Port badges (CONT-04)
- arduis already renders pane-header badges (`arduis-badge` CSS, `_badge_by_tid`, window.py:963) and
  sidebar dots. **Recommended:** show resolved ports as small badges. Two viable spots:
  1. **Sidebar row sub-line** (under the branch, where RAM text lives) — e.g. `web:19080 db:16432`.
     Cheapest; always visible; matches the existing sub-line pattern.
  2. **A dedicated "containers" strip** in the workspace header when isolation is ON.
  Recommend the **sidebar sub-line badges** for v1 (least new chrome, always visible). Clicking a badge
  could copy `http://127.0.0.1:<port>` (nice-to-have, defer).
- Badges read from the PERSISTED port map (stable across restart), not from a live `docker` query.

### Progress surfacing (Pitfall 3)
- **Recommended:** stream `up`/`down` into a NEW shell-kind terminal leaf in the task workspace (reuse
  `_make_task_leaf`), titled `compose`, OR a simpler `Adw` toast + spinner on the toggle. Recommend the
  **toast + spinner** for v1 (a full streamed pane is more wiring); escalate to a pane only if the user
  wants live pull output. (Open Decision OD-3.)

## DESIGN: Per-task container state persistence (CONT-02/03/04)

- **Where:** a small file in the TASK FOLDER — `<task_dir>/arduis.container.toml` (disk = source of
  truth, matching 03.2's no-app-state-file model; survives restart; rediscovered by the startup scan).
  Alternative: under `~/.config/arduis/`. Recommend the **task folder** (co-located, rediscovered by
  `_scan_tasks` which already walks task folders). [Open Decision OD-2]
- **Contents:** `project_name`, `isolation_enabled` (bool), and a `ports` table mapping
  `service -> {base, host}` so badges and re-enable are deterministic.
- **Write:** atomic tmp + `os.replace`, mirroring `appconfig.write_theme` (window.py uses this pattern
  throughout). GTK-free in `containerstate.py`.
- **Read:** at startup, `_scan_tasks` (window.py:1725) already builds HIBERNATED tasks from disk —
  extend it to load the container state so the port badges render before any `up`.

## Validation Architecture

> nyquist_validation: no `.planning/config.json` key found disabling it → treat as ENABLED.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (per dev MEMORY: `/tmp` venv `--system-site-packages`) |
| Config file | repo pytest config (existing — 274 tests as of Phase 6) |
| Quick run command | `pytest tests/test_compose.py -x` |
| Full suite command | `pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONT-01 | auto-detect compose; toggle hidden when absent; default OFF | unit | `pytest tests/test_compose.py::test_detect -x` | ❌ Wave 0 |
| CONT-02 | sanitize_project_name + stable persisted name | unit | `pytest tests/test_compose.py::test_project_name -x` | ❌ Wave 0 |
| CONT-02/03 | override emits `ports: !override` (replace, not append) | unit | `pytest tests/test_compose.py::test_override_replaces -x` | ❌ Wave 0 |
| CONT-03 | offset map + probe + retry on collision | unit | `pytest tests/test_compose.py::test_port_probe -x` | ❌ Wave 0 |
| CONT-02/03 | parse `config --format json` ports shape | unit (fixture JSON) | `pytest tests/test_compose.py::test_parse_config -x` | ❌ Wave 0 |
| CONT-04 | persisted port map round-trips (atomic write) | unit | `pytest tests/test_containerstate.py -x` | ❌ Wave 0 |
| CONT-05 | down/teardown argv + reconcile query builders | unit | `pytest tests/test_compose.py::test_teardown_argv -x` | ❌ Wave 0 |
| CONT-01..05 | end-to-end up→badge→down on REAL docker | smoke (manual/UAT) | host-only, see honesty note | ❌ manual |

### Sampling Rate
- **Per task commit:** `pytest tests/test_compose.py tests/test_containerstate.py -x`
- **Per wave merge:** `pytest`
- **Phase gate:** full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_compose.py` — covers CONT-01/02/03/05 (the GTK-free `compose.py`)
- [ ] `tests/test_containerstate.py` — covers CONT-04 persistence round-trip
- [ ] A captured `config --format json` FIXTURE (the verified shape above) so the parser is tested
      without invoking docker

### Honesty about what a smoke CAN and CANNOT do
- **CAN (GTK-free, no docker):** every generation/parse/probe/persist unit — the `!override` tag in the
  emitted YAML, sanitization, offset map, JSON-fixture parsing, atomic round-trip. This is the bulk of
  the real logic and is fully testable headless.
- **CAN (host with real docker):** a live up→`compose config` shows the remapped (single) port →
  badge → `down` leaves `compose ls` empty. This is REAL and was partially exercised here (the
  `!override` replace-vs-append behavior is verified on the host). But it needs a real image pull and a
  free port range, so it is a **host-only smoke / UAT item**, not CI-portable, and **must run under
  `$HOME` on snap docker (Ubuntu)**.
- **CANNOT (headless broadway):** the GTK smoke used in Phases 4–6 proves UI wiring but cannot bring up
  real containers meaningfully in a hermetic harness. Treat real-container behavior as a LIVE UAT
  checklist (matching the project's pattern of headless-smoke + human-verify).

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| docker engine | all of Phase 7 | ✓ (snap) | 29.3.1 | feature stays OFF/unavailable if absent |
| docker compose plugin | all of Phase 7 | ✓ | v5.1.1 | none — required for the feature |
| `!override` tag support | override generation | ✓ (compose ≥ v2.24.4; host v5.1.1) | — | none (without it, ports double) |
| PyYAML | writing override (if OD-1 = PyYAML) | ✓ | 6.0.1 | hand-rolled emitter |
| python3 socket/tomllib | probe + persist | ✓ | 3.12 | — |

**Missing dependencies with no fallback:** none on the dev host. On a machine WITHOUT docker, the
feature must self-disable (auto-detect: if `docker` is absent OR no root compose, the toggle is
unavailable — strict no-op, like Phase-6's missing `.arduis.toml`).

**Note (Phase 9 packaging):** add `python3-yaml`/`python-yaml` to package deps if PyYAML becomes a hard
dep (OD-1). docker itself is NOT a package dependency (the user supplies it; snap on Ubuntu, native on
Arch) — arduis only shells out to it.

## Security Domain

> `security_enforcement` not found as `false` in config → treat as enabled. Phase 7 surface is modest
> (no network/auth/crypto), but two real concerns exist.

### Applicable ASVS Categories
| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | — |
| V3 Session Management | no | — |
| V4 Access Control | no | docker socket access is the user's own (host docker, no arduis sandbox) |
| V5 Input Validation | yes | sanitize the branch → project name (regex allow-list); argv stays a LIST (no shell) |
| V6 Cryptography | no | — |

### Known Threat Patterns for shell-out-to-docker
| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Branch name injected into project name / argv | Tampering / EoP | Allow-list sanitize (`[a-z0-9_-]`, leading char); argv is a Python LIST through HostRunner — NO `shell=True`, nothing joined into a shell string (matches `git_service`/`spawn` threat posture T-02-01/T-01-01) |
| Malicious root `docker-compose.yml` (committed code runs containers) | EoP | SAME risk class as Phase-6 `.arduis.toml` setup commands — running an untrusted repo's compose is RCE-adjacent. **Consider** gating first `up` behind the existing trust model (`trust.py`) or at minimum a confirmation. The opt-in default-OFF toggle is itself a consent gate. [ASSUMED A3 — confirm whether the Phase-6 trust gate should extend to compose `up`] |
| Path traversal in the override target | Tampering | Compose path is composed only from `task_dir` (arduis-controlled, mirrors root), never from compose-file content; the ONLY deletion site rule (T-04-16) does not apply (no unlink here) |
| Stale `arduis-*` stacks after crash leak RAM/ports | DoS (self) | Startup reconcile via `compose ls --filter name=arduis` + teardown |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The 03.2 `symlink_plan` materialization already places a root `docker-compose.yml` (and any build-context dirs it references) under the task folder so `-f <task_dir>/docker-compose.yml` resolves | Pitfall 4 / DESIGN | If the root compose isn't mirrored, the planner must add it to `symlink_plan` (or copy it) before `up`; build contexts could fail to resolve. **Planner MUST verify `symlink_plan` covers the root compose + referenced build dirs.** |
| A2 | Auto-detect filename is `docker-compose.yml` (then `compose.yaml`) at the project root | DESIGN auto-detect | Could miss a project using `compose.yaml`; cheap to check both — recommend checking both names |
| A3 | Whether running an untrusted repo's compose `up` should reuse the Phase-6 `trust.py` gate | Security | If skipped, a malicious committed compose could run containers on `up`; default-OFF + explicit toggle is a partial consent gate. Orchestrator/discuss should decide. |
| A4 | `COMPOSE_PROJECT_NAME` via `-p` flag is preferred over the env var | Pattern 3 | Both work; `-p` is more explicit/deterministic. Low risk. |

## Open Questions (each with a recommended default — user is AFK)

1. **OD-1: PyYAML vs hand-rolled emitter for writing the override (with the `!override` tag)?**
   - Known: PyYAML 6.0.1 is installed and is a system package on both distros; the `!override` tag
     needs a one-line custom representer. The hand-rolled `appconfig._serialize` exists but doesn't do
     YAML or tags.
   - **Recommended default: use PyYAML** (correctness of the `!override` tag + quoted port strings;
     already available; add `python3-yaml`/`python-yaml` to Phase-9 deps). It is a small, blessed
     system dep — acceptable given CLAUDE.md only forbids the docker SDK, not PyYAML.

2. **OD-2: Where to persist per-task container state?**
   - **Recommended default: `<task_dir>/arduis.container.toml`** (disk = source of truth, co-located,
     rediscovered by the existing `_scan_tasks` walk). Atomic write mirroring `appconfig`.

3. **OD-3: How to surface `up`/`down` progress?**
   - **Recommended default: Adw toast + a spinner on the toggle (disable toggle during the op)** for
     v1; escalate to a streamed `compose` pane (`_make_task_leaf`) only if live pull output is wanted.

4. **OD-4: Toggle home — sidebar row menu vs a workspace-header switch?**
   - **Recommended default: sidebar row right-click menu** ("Isolar containers"), beside Hibernate/
     Resume (`_make_row_menu_cb`) — matches the established model, zero new chrome.

5. **OD-5: Should compose `up` go through the Phase-6 trust gate (A3)?**
   - **Recommended default: NO separate trust dialog for v1** — the opt-in, default-OFF, explicit
     per-task toggle IS the consent gate (the user deliberately enables containers for a known
     project). Document the residual risk (a malicious committed root compose). Revisit if dogfooding
     surfaces a concern.

6. **OD-6: Offset retry policy on port collision.**
   - **Recommended default:** start at `base + port_offset` (config `port_offset = 1000`); on a probe
     collision for ANY service, bump the WHOLE task's offset by another `port_offset` step and re-probe
     all (keeps a task's ports clustered/predictable); cap at e.g. 10 attempts, then surface an error.

## Sources

### Primary (HIGH confidence)
- Live host verification (docker 29.3.1 / compose v5.1.1), 2026-06-13:
  - `docker compose config --format json` ports shape (long-form dict, `published` is a string)
  - `ports: !override` REPLACES (`['19080']`) vs plain override CONCATENATES (`['8080','19080']`)
  - snap docker cannot read `-f /tmp/...` (confinement); `$HOME` works
  - `docker compose ls --all --filter name=arduis --format json` shape (`[{Name,Status,ConfigFiles}]`)
  - `socket.bind` strict probe (`SO_REUSEADDR 0`)
  - `docker ps --filter label=com.docker.compose.project=<name>` lists a project's containers
- In-repo: `src/arduis/host_runner.py`, `git_service.py`, `spawn.py`, `session.py`, `appconfig.py`,
  `window.py` (`_scan_tasks` 1725, `_create_task` 1947, `_hibernate_task` 2815, `_teardown_*`/
  `_on_close_request` 3012–3091), `task_layout.py` (`task_dir_for`, `symlink_plan`)
- CLAUDE.md "Docker Compose Orchestration (Phase 7)" section (project decisions)
- [docs.docker.com/compose/how-tos/project-name](https://docs.docker.com/compose/how-tos/project-name/) — name constraints + precedence
- [docs.docker.com/reference/compose-file/merge](https://docs.docker.com/reference/compose-file/merge/) — ports concatenate; `!override`/`!reset` tags

### Secondary (MEDIUM confidence)
- [akrabat.com — Changing port maps in Docker Compose](https://akrabat.com/changing-port-maps-in-docker-compose/) — `!override` usage corroboration
- [codestudy.net — Override ports instead of merging](https://www.codestudy.net/blog/docker-compose-override-a-ports-property-instead-of-merging-it/) — same

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — versions verified live on host; pattern mirrors existing `git_service`
- Override/ports behavior: HIGH — replace-vs-append verified live, not assumed
- snap-docker confinement: HIGH — reproduced live (`/tmp` fail, `$HOME` pass)
- Architecture/DESIGN: MEDIUM-HIGH — grounded in existing window.py machinery; UI placement is a
  recommendation with an open decision
- Symlink coverage of the root compose (A1): MEDIUM — must be verified against `symlink_plan` by the planner

**Research date:** 2026-06-13
**Valid until:** ~2026-07-13 (docker compose merge semantics are stable; the `!override` tag is spec-level)
