"""Unit coverage for the TTL throttle backbone (GIT-01).

Pins ``is_fresh`` (monotonic-delta freshness), the ``ReviewCache`` round-trip,
and the ``GIT_TTL_S``/``GH_TTL_S`` module constants Wave 2 imports by name.
Pure import of ``arduis.review_cache`` — no ``gi``. ``now`` is supplied by the
caller (the window passes ``time.monotonic()``) so the helper stays pure and
unit-testable with fixed floats — this is a manual-refresh + TTL throttle, NOT
a poll (gh is network / rate-limited).
"""
from __future__ import annotations

from pathlib import Path

from arduis import review_cache
from arduis.review_cache import GH_TTL_S, GIT_TTL_S, ReviewCache, is_fresh


# --- is_fresh: the freshness predicate ---------------------------------------

def test_is_fresh_none_is_false():
    # no prior read => never fresh
    assert is_fresh(None, now=100.0, ttl=30.0) is False


def test_is_fresh_within_ttl_is_true():
    assert is_fresh(ts=100.0, now=120.0, ttl=30.0) is True  # 20s < 30s


def test_is_fresh_at_or_past_ttl_is_false():
    assert is_fresh(ts=100.0, now=131.0, ttl=30.0) is False  # 31s >= 30s


def test_is_fresh_zero_delta_is_true():
    assert is_fresh(ts=100.0, now=100.0, ttl=30.0) is True  # delta 0 < ttl


def test_is_fresh_exact_ttl_boundary_is_false():
    # delta == ttl is NOT fresh (strict <)
    assert is_fresh(ts=100.0, now=130.0, ttl=30.0) is False


# --- ReviewCache: put/get round-trip -----------------------------------------

def test_cache_put_get_round_trips():
    cache = ReviewCache()
    cache.put("t1", {"pr": 42}, now=100.0)
    assert cache.get("t1") == ({"pr": 42}, 100.0)


def test_cache_get_missing_is_none():
    cache = ReviewCache()
    assert cache.get("missing") is None


def test_cache_put_overwrites():
    cache = ReviewCache()
    cache.put("t1", {"pr": 1}, now=100.0)
    cache.put("t1", {"pr": 2}, now=150.0)
    assert cache.get("t1") == ({"pr": 2}, 150.0)


# --- ReviewCache.fresh_payload: get gated on TTL -----------------------------

def test_fresh_payload_within_ttl_returns_payload():
    cache = ReviewCache()
    cache.put("t1", {"pr": 42}, now=100.0)
    assert cache.fresh_payload("t1", now=120.0, ttl=30.0) == {"pr": 42}


def test_fresh_payload_stale_is_none():
    cache = ReviewCache()
    cache.put("t1", {"pr": 42}, now=100.0)
    assert cache.fresh_payload("t1", now=200.0, ttl=30.0) is None


def test_fresh_payload_missing_is_none():
    cache = ReviewCache()
    assert cache.fresh_payload("missing", now=100.0, ttl=30.0) is None


# --- the documented TTL defaults Wave 2 imports ------------------------------

def test_ttl_constants_are_the_documented_defaults():
    assert GIT_TTL_S == 30.0
    assert GH_TTL_S == 120.0


# --- the GTK-free domain discipline ------------------------------------------

def test_review_cache_module_is_gtk_free():
    source = Path(review_cache.__file__).read_text(encoding="utf-8")
    assert "import gi" not in source
    assert "from gi" not in source
