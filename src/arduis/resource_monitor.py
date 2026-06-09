"""GTK-free, zero-dependency ``/proc`` RSS accounting for per-worktree RAM.

Pure synchronous process-group RSS accounting plus the pt-BR RAM formatter. The
two are the production side of the RAM-03 (per-worktree RSS) promise.

Decisions:
- D-12: per-worktree RAM is the SUMMED RSS of *every* pid in the worktree's
  process group (the shell + the agent + any children), derived from each pid's
  ``stat`` pgrp — not just the shell pid.
- D-13: reads ``/proc`` directly (``smaps_rollup`` -> ``statm`` fallback) with the
  stdlib only; no third-party process library (rejected dependency).
- D-14: this module is pure synchronous accounting; the off-loop ~2s polling that
  CALLS it (so it never blocks the GTK main loop) lives in ``window.py`` (Plan
  03-05). It is bounded to the 5-12 process working set (Assumption A1), so each
  call is a handful of tiny virtual-file reads.

Pitfalls handled:
- Pitfall 3 (pid reuse / mid-walk exit): every per-pid read swallows
  ``FileNotFoundError``/``ProcessLookupError``/``PermissionError`` and contributes
  0, never a traceback or a stranger's RSS. Group membership is re-derived live
  each call (no cached pid lists).
- Pitfall 5 (``smaps_rollup`` unreadable): fall back to ``statm`` resident pages.
- Pitfall 7 (pt-BR figures): MB under 1024 MB, GB with one decimal above, decimal
  COMMA, ``None`` -> em-dash (UI-SPEC footer ``"N agentes ativos · <total> RAM"``).
"""
from __future__ import annotations

import os

_PAGE = os.sysconf("SC_PAGE_SIZE")  # bytes per page, for the statm fallback


def _rss_kb_for_pid(pid: int) -> int:
    """Resident set size of one pid in kB.

    Prefer ``/proc/<pid>/smaps_rollup`` (its ``Rss:`` line is already in kB). If
    that is unreadable (older kernels, races, permissions), fall back to
    ``/proc/<pid>/statm`` field 2 (resident pages) x page size // 1024. If BOTH
    fail the pid has vanished -> return 0 (Pitfall 3), no traceback.
    """
    try:
        with open(f"/proc/{pid}/smaps_rollup", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("Rss:"):
                    return int(line.split()[1])  # already kB
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass  # fall through to statm

    try:
        with open(f"/proc/{pid}/statm", encoding="utf-8") as fh:
            resident_pages = int(fh.read().split()[1])  # field 2 (0-based index 1)
        return resident_pages * _PAGE // 1024
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return 0  # Pitfall 3 — pid gone, contribute nothing


def _pids_in_group(pgid: int) -> list[int]:
    """Every pid whose process group equals ``pgid`` (live, re-derived per call).

    Scans ``/proc`` numeric entries and parses each ``stat`` line. The comm field
    is parenthesized and may itself contain spaces and parens (e.g.
    ``(zsh (login))``), so we split on the LAST ``)`` and read pgrp from the tail.
    In the tail the fields are: state, ppid, pgrp -> index 2. Per-entry errors
    (vanished pid, permission, malformed line) are swallowed (T-03-05/T-03-06).
    """
    pids: list[int] = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat", encoding="utf-8") as fh:
                line = fh.read()
            tail = line[line.rfind(")") + 1:].split()
            if int(tail[2]) == pgid:  # state, ppid, pgrp -> index 2
                pids.append(int(entry))
        except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError, IndexError):
            continue  # skip mid-walk exits / other users / malformed
    return pids


def group_rss_kb(pgid: int) -> int:
    """Summed RSS (kB) of the whole process group ``pgid`` (D-12).

    Calls the two module-level helpers by name so tests can monkeypatch them.
    """
    return sum(_rss_kb_for_pid(p) for p in _pids_in_group(pgid))


def format_ram_kb(rss_kb: int | None) -> str:
    """Format an RSS figure in pt-BR (D-14 / UI-SPEC / Pitfall 7).

    ``None`` -> ``"—"``. Under 1024 MB -> integer MB (``"312 MB"``). At/above
    1024 MB -> GB with one decimal and a decimal COMMA (``"1,2 GB"``).
    """
    if rss_kb is None:
        return "—"
    mb = rss_kb / 1000  # kB -> MB (decimal MB matches UI-SPEC "312 MB")
    if mb < 1024:
        return f"{int(mb)} MB"
    gb = mb / 1024  # MB -> GB (binary), one decimal with a pt-BR comma
    return f"{gb:.1f} GB".replace(".", ",")
