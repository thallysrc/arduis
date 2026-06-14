"""TTL throttle backbone for the read-only git/gh introspection (GIT-01, GTK-free).

The Phase-8 status reads (branch ahead/behind, PR state) are THROTTLED, not
polled: a manual refresh action + this TTL cache + an in-flight debounce (the
window mirrors ``_compose_busy``). gh in particular is network / rate-limited,
so there is deliberately NO poll loop — Wave 2 gates every read on this cache
(T-08-03).

``now`` is supplied by the caller: the window passes ``time.monotonic()`` so the
freshness math uses monotonic deltas (immune to wall-clock jumps), while this
module stays pure and unit-testable with injected fixed floats. Imports stdlib
only — no ``gi`` (mirrors the ``review.py`` / ``worktree.py`` GTK-free discipline).

Wave 2 imports ``is_fresh``, ``ReviewCache``, and the two TTL constants by name.
"""
from __future__ import annotations

# Documented TTL defaults (08-RESEARCH §4; tunable after dogfooding).
# git reads are cheap/local => short TTL; gh reads hit the network / rate limit
# => a longer TTL.
GIT_TTL_S: float = 30.0
GH_TTL_S: float = 120.0


def is_fresh(ts: float | None, now: float, ttl: float) -> bool:
    """``True`` iff ``ts`` exists and is within ``ttl`` of ``now``.

    ``None`` (no prior read) is never fresh. The bound is strict (``< ttl``),
    so a delta exactly equal to ``ttl`` counts as expired. ``now``/``ts`` are
    monotonic seconds supplied by the caller.
    """
    return ts is not None and (now - ts) < ttl


class ReviewCache:
    """A tiny ``task_id``-keyed cache of ``(payload, ts)`` records.

    The throttle backbone Wave 2 calls: ``put`` stores a read with the monotonic
    timestamp it was taken at; ``get`` returns the raw record; ``fresh_payload``
    returns the payload only while it is within ``ttl`` (else ``None``, signalling
    "re-read needed"). The cache is monotonic-agnostic — all time comes in via
    ``now`` — so tests inject fixed floats.
    """

    def __init__(self) -> None:
        self._d: dict[str, tuple[object, float]] = {}

    def put(self, task_id: str, payload: object, now: float) -> None:
        """Store ``payload`` for ``task_id`` stamped at ``now`` (overwrites)."""
        self._d[task_id] = (payload, now)

    def get(self, task_id: str) -> tuple[object, float] | None:
        """Return the raw ``(payload, ts)`` record, or ``None`` if absent."""
        return self._d.get(task_id)

    def fresh_payload(self, task_id: str, now: float, ttl: float) -> object | None:
        """Return the payload only if present AND within ``ttl``, else ``None``."""
        rec = self._d.get(task_id)
        if rec is None or not is_fresh(rec[1], now, ttl):
            return None
        return rec[0]
