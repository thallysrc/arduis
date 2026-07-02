"""Regression lock for the _learned_ratio guard (split-black-pane-hole).

Bug: creating a split rebuilds the whole nested Gtk.Paned tree. Split position was
applied PURELY reactively from ``notify::max-position``; GTK4 coalesces those
notifications, so a freshly rebuilt paned could settle at its real extent without a
final re-notify — leaving one child at ≈0 extent (a black hole that self-heals on
resize). A secondary hazard: ``_learn`` treated any ``notify::position`` as a user
drag, so a deferred echo of our own ``set_position`` or a transient collapse could
poison ``node.ratio`` and get persisted to layouts.json (a resize-RESISTANT hole).

The tick-callback that guarantees application needs a real GTK frame clock, so it is
covered by manual acceptance. The pure drag-learning guard IS unit-testable and is
locked here: only a genuine user drag on a real allocation should be learned.

window.py imports without a display; ``_learned_ratio`` is a pure module function.
"""
import arduis.window as W


def test_ignores_unallocated_paned():
    """max-position <= 1 means no real allocation yet — never learn from it."""
    assert W._learned_ratio(position=3, max_position=1, last_set=-1, settled=False) is None
    assert W._learned_ratio(position=0, max_position=0, last_set=-1, settled=False) is None


def test_ignores_before_settled():
    """Position changes before we apply our own position are layout noise, not drags."""
    assert W._learned_ratio(position=400, max_position=1000, last_set=-1, settled=False) is None


def test_ignores_echo_of_our_own_set_position():
    """A position equal to what WE last set is an echo (possibly deferred) — not a drag."""
    assert W._learned_ratio(position=500, max_position=1000, last_set=500, settled=True) is None


def test_ignores_degenerate_collapse_to_sliver():
    """A transient collapse to ≈0 or ≈1 is never a deliberate drag — do not persist it."""
    assert W._learned_ratio(position=5, max_position=1000, last_set=500, settled=True) is None
    assert W._learned_ratio(position=995, max_position=1000, last_set=500, settled=True) is None
    assert W._learned_ratio(position=0, max_position=1000, last_set=500, settled=True) is None


def test_learns_a_genuine_user_drag():
    """A real drag on a settled paned (not an echo, not degenerate) IS learned."""
    assert W._learned_ratio(position=300, max_position=1000, last_set=500, settled=True) == 0.3
    assert W._learned_ratio(position=700, max_position=1000, last_set=500, settled=True) == 0.7


def test_learns_at_plausible_boundaries():
    """Ratios just inside the degenerate cutoffs are still legitimate drags."""
    # 0.03 and 0.97 are inside the (0.02, 0.98) plausible band.
    assert W._learned_ratio(position=30, max_position=1000, last_set=500, settled=True) == 0.03
    assert W._learned_ratio(position=970, max_position=1000, last_set=500, settled=True) == 0.97
