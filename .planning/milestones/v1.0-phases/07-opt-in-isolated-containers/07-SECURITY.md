---
phase: 07-opt-in-isolated-containers
threats_open: 0
threats_closed: 16
threats_total: 16
asvs_level: 2
audited: 2026-06-14
auditor: gsd-secure-phase
---

# Phase 07 — Opt-in Isolated Containers — Security Audit

## Trust Boundary (the destructive surface)

arduis drives `docker compose` **on the host directly** (native build, no sandbox), running
the **user's own** repo-committed root `docker-compose.yml` for a task the user explicitly
opted into. The two boundaries that matter:

1. **branch name → `COMPOSE_PROJECT_NAME` → argv → docker daemon.** A user-chosen (possibly
   hostile) branch name crosses into a docker invocation. Mitigated by an allow-list
   sanitizer + list-form argv (never a shell string).
2. **`docker compose down --remove-orphans --volumes` is DESTRUCTIVE** — it deletes the
   stack's named volumes (a DB). The audit's central question: is `down -v` ever reachable
   against anything other than the task's **own** per-task project name? **Confirmed: no.**
   Every `down` call site derives the project from `compose.sanitize_project_name(branch)`
   or the persisted `state.project_name` (always an `arduis-*` per-task name) and passes it
   via `-p <project>`. There is **no bare `down`** anywhere, and the startup reconcile
   **never** auto-runs `down -v` — it only surfaces orphans via a toast. arduis can therefore
   never auto-delete a user's main-stack volumes.

## Verification Summary

**16/16 threats closed.** 11 `mitigate` verified present in code; 5 `accept` documented below.
Full suite: 344 passed (`/tmp/arduis-venv-ab12/bin/python -m pytest tests/`).
No `shell=True`, `os.system`, or `os.popen` in any audited module (only docstring assertions
of their absence).

### Mitigated Threats

| Threat ID | Category | Evidence |
|-----------|----------|----------|
| T-07-01 | Tampering / EoP | `compose.sanitize_project_name` (compose.py:79-92) — allow-list regex `[^a-z0-9_-]+ → -`, dash-run collapse, `arduis-` prefix guarantees the leading-char rule, empty→`arduis-task`. Branch can never inject. |
| T-07-02 | Tampering | `override_bytes`/`_port_string` (compose.py:201-239) build port strings only from `int` host/target (from `assign_ports`) + host_ip read from the authoritative `config` model; PyYAML emits a structured doc, never string concat. |
| T-07-03 | DoS (self) | `assign_ports` (compose.py:166-185) caps at `range(10)`, then raises `PortAssignmentError`. No unbounded loop. |
| T-07-05 | DoS | `load_container_state` (containerstate.py:134-175) swallows `OSError`/`TOMLDecodeError`→`ContainerState()`; `_clean_port_entry` drops malformed rows, never raises. |
| T-07-06 | Tampering | `write_container_state` (containerstate.py:178-203) tmp `mkstemp` + `os.replace` (atomic); OSError swallowed best-effort → degrades to "no state", never a torn record. |
| T-07-08 | Tampering / EoP | `run_compose_async` (docker_service.py:40-57) passes the list-form argv straight to `Gio.Subprocess.new` via `HostRunner.wrap_argv` — no shell, no join. |
| T-07-09 | DoS (self) | `run_compose_async` uses `Gio.Subprocess` + `communicate_utf8_async` on the GLib loop — no blocking `subprocess.run`, no threads/asyncio. |
| T-07-11 | DoS | Every `json.loads` of compose stdout is wrapped: `_enable_isolation._on_config` (window.py:1482-1486) and `_reconcile_orphans._on_ls` (window.py:1667-1671) catch `(ValueError, TypeError)` → toast / early return, never an unhandled exception on the loop. |
| T-07-12 | DoS (self) | Orphan cleanup on two channels: `_container_down` on hibernate/app-exit (window.py:1630-1650, 3469, 3740-3756) + startup `_reconcile_orphans` (window.py:1652-1691, called at :2380). |
| T-07-13 | Tampering | Container teardown is its OWN channel: `_container_down` runs `docker compose down`, and is invoked ALONGSIDE (never inside) `_teardown_session_terminals`/killpg (window.py:3463-3469). Grep confirms `_container_down` never appears inside `_teardown_session_terminals` (window.py:3663+). Containers are daemon-owned, not in arduis's process group. |
| T-07-14 | DoS | App-exit `subprocess.run(down, timeout=10, check=False)` (window.py:3752-3756) is capped and best-effort (errors swallowed) — the window still closes. Hibernate path stays async. |
| T-07-15 | DoS (hygiene) | `tests/test_compose_smoke.py:25-33` sandboxes `$HOME` via `monkeypatch.setenv("HOME", ...)` so `write_container_state` never touches the real `~/.config` (D-09). No real docker invoked in the smoke. |

### Accepted Risks (logged)

| Threat ID | Category | Rationale |
|-----------|----------|-----------|
| T-07-04 | EoP (RCE-adjacent) | Running an untrusted repo's compose `up` is RCE-adjacent. **Accepted:** `compose.py` only GENERATES bytes/argv — it executes nothing. The consent gate is the opt-in, default-OFF, explicit per-task toggle in Wave 3 (`_on_toggle_isolation`, window.py:1434). No separate trust dialog in v1; revisit at dogfooding. |
| T-07-07 | Tampering | A forged `[containers].port_offset`. **Accepted:** `read_port_offset` (containerstate.py:206-227) returns an int or the 1000 default (bool rejected). An out-of-range int only shifts ports, which are probed free anyway. The config is the user's own file — no privilege boundary crossed. |
| T-07-10 | EoP | A malicious committed root `docker-compose.yml` runs containers on `up`. **Accepted:** same consent gate as T-07-04 — `up` never runs without a deliberate per-task toggle on a project the user chose. Residual risk documented; revisit at dogfooding. |
| Port-probe TOCTOU | DoS (self) | `port_free` (compose.py:125-140) probe-then-`up` has a tiny race window. **Accepted (D-06):** if the port is lost between probe and bind, compose `up` fails **visibly** (non-zero exit → `_on_up` fires `down` to clean the partial stack, leaves the toggle OFF — window.py:1509-1520). No silent corruption. |
| `down -v` scoping | (residual note) | `down --remove-orphans --volumes` is destructive but **always scoped** to the task's own `arduis-*` `COMPOSE_PROJECT_NAME` via `-p`. The startup reconcile is deliberately conservative — surfaces orphans, **never** auto-`down -v` (window.py:1652-1691). arduis never auto-deletes a user's volumes. |
| T-07-16 | DoS (UAT only) | The live UAT crash-test intentionally leaves an orphan stack, reaped by the checklist (`docker compose -p arduis-<branch> down -v`). UAT-only; no code surface. |

## Unregistered Flags

None. The SUMMARY files contain no `## Threat Flags` section. The cross-plan coordination
note in 07-02-SUMMARY (port-map shape adapter) and the env-isolation note in 07-03-SUMMARY
(`COMPOSE_PROJECT_NAME` via `-p` argv vs. `Gio.SubprocessLauncher.setenv`) were inspected and
are not security surface — isolation is enforced by `-p <project>` on the argv, which is
present and tested.

## Notes

- `parse_published_ports` (compose.py:97-120) is tolerant — missing `services`/`ports` yields
  fewer entries, never raises.
- The `ports: !override` tag (compose.py:190-198) is a correctness AND DoS-avoidance control:
  a plain `ports` override CONCATENATES the base port (`['8080','19080']`) → host collision;
  `!override` REPLACES it. Verified by smoke (`"8080:80" not in text`).
- Implementation files were not modified during this audit (read-only).
