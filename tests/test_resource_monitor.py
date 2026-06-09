"""RED contract tests for the GTK-free /proc RAM monitor (``arduis.resource_monitor``).

Pins the process-group RSS contract Plan 03-03 must satisfy. Fails now (RED)
because ``arduis.resource_monitor`` does not exist yet.

The tests NEVER read the real ``/proc`` (T-03-01): every ``/proc`` access is
monkeypatched — internal helpers (``_pids_in_group``/``_rss_kb_for_pid``) or
``builtins.open`` with a path-dispatching fake — so the suite is deterministic
and host-independent.

Decisions pinned:
- D-12: RSS is summed across the whole process GROUP (every pid whose stat pgrp
  matches), not just the shell pid.
- D-13: reads ``/proc`` directly (``smaps_rollup`` -> ``statm`` fallback), not psutil.
- D-14 + UI-SPEC copywriting: pt-BR figures — ``"312 MB"`` under 1024 MB,
  ``"1,2 GB"`` (decimal comma, one place) above, ``None`` -> ``"—"``.
- Pitfall 3: a pid that vanishes (FileNotFoundError on both files) contributes 0,
  never a traceback.
- Pitfall 5: ``smaps_rollup`` unreadable -> fall back to ``statm`` resident pages.
"""
import os

from arduis import resource_monitor
from arduis.resource_monitor import format_ram_kb, group_rss_kb

_PAGE = os.sysconf("SC_PAGE_SIZE")


def test_group_rss_sum(monkeypatch):
    # D-12: sum RSS over every pid in the group.
    monkeypatch.setattr(resource_monitor, "_pids_in_group", lambda pgid: [101, 102])
    monkeypatch.setattr(
        resource_monitor,
        "_rss_kb_for_pid",
        lambda pid: {101: 200000, 102: 112000}[pid],
    )
    assert group_rss_kb(1200) == 312000


def test_stat_paren_comm():
    # comm may contain spaces AND parens; the pgrp parse must split on the LAST ')'.
    # Synthetic stat line: pid (comm-with-parens) state ppid pgrp ...
    line = "1234 (zsh (login)) S 1 1200 1200 0 0 0 0"
    # parse the way the module must: everything after the last ')' is the fields,
    # and field index 3 (0-based) of that tail is pgrp.
    tail = line[line.rfind(")") + 1:].split()
    pgrp = int(tail[2])  # state, ppid, pgrp -> index 2
    assert pgrp == 1200


def test_rss_fallback(monkeypatch):
    # Pitfall 5: smaps_rollup raises FileNotFoundError -> fall back to statm field 2.
    real_open = open

    def fake_open(path, *args, **kwargs):
        p = os.fspath(path)
        if "smaps_rollup" in p:
            raise FileNotFoundError(p)
        if p.endswith("/statm"):
            import io

            return io.StringIO("0 50 0 0 0 0 0")  # field 2 (index 1) = 50 resident pages
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fake_open)
    expected = 50 * _PAGE // 1024
    assert resource_monitor._rss_kb_for_pid(4242) == expected


def test_rss_missing_pid(monkeypatch):
    # Pitfall 3: pid vanished -> both files raise FileNotFoundError -> 0, no traceback.
    def fake_open(path, *args, **kwargs):
        raise FileNotFoundError(os.fspath(path))

    monkeypatch.setattr("builtins.open", fake_open)
    assert resource_monitor._rss_kb_for_pid(999999) == 0


def test_ram_format():
    # D-14 / UI-SPEC: pt-BR comma; MB under 1024 MB, GB (one decimal) above; None -> em-dash.
    assert format_ram_kb(312000) == "312 MB"
    assert format_ram_kb(1258291) == "1,2 GB"
    assert format_ram_kb(None) == "—"


def test_resource_monitor_is_gtk_free():
    with open(resource_monitor.__file__, encoding="utf-8") as fh:
        text = fh.read()
    assert "import gi" not in text
