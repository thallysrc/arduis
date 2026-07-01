---
status: resolved
trigger: "After splitting to 3 terminals the nested Gtk.Paned layout collapses to a ~6px sliver on the left; the other two terminals render nothing."
created: 2026-06-10
updated: 2026-07-01
resolution_note: "Fix verified by headless broadway re-run (3 terminals all >100px, close/re-fill correct, zero layout GTK-CRITICAL). Live confirmation waived by user 2026-07-01 (yolo risk acceptance); reopen if the sliver reappears in real use."
---

## Current Focus

hypothesis: Nested Gtk.Paned position is set on the wrong widget / at the wrong time. The map-based 50/50 (`_init_paned_position`) only centers each paned ONCE on its own first map; for a right-leaning nested chain the inner paned maps before the outer has distributed space (or the outer never re-positions after the inner grows), leaving inner paneds at position 0.
test: headless broadway driver — build main + split twice, walk widget tree printing allocations + paned positions.
expecting: at least one paned with position 0 / a terminal with width < 10px, confirming the sliver.
next_action: write throwaway driver, run under broadway, capture allocations + stderr.

## Symptoms

expected: 3 terminals visible in nested Paned splits, each with a sane (>100px) width.
actual: ONE terminal squeezed to ~6px sliver at the LEFT edge; the other two render nothing; rest of canvas empty.
errors: unknown yet — must capture stderr for GTK-CRITICAL (possible widget-already-has-parent during reflect rebuild).
reproduction: open a worktree (2 terminals side by side), then split (⊟) once -> 3 terminals -> collapse.
started: 2-terminal worked; broke when going to 3. Commit b487dfe ("repair canvas reflection") moved the collapse from right to left, two terminals invisible.

## Eliminated

## Evidence

- timestamp: 2026-06-10T20:02
  checked: headless broadway driver — 2 terminals, then split to 3, walked widget tree.
  found: |
    AFTER 2 TERMINALS: correct. Paned pos=365, start Box w=363 (VTE 361), end Box w=340 (VTE 338). Works.
    AFTER 3 TERMINALS: BROKEN STRUCTURE, not mis-position. Tree is:
      Paned(outer) w=0 pos=0
        [start] Paned(inner) w=0 pos=0
          GtkPanedHandle
          [end] Box feat:t1   <-- inner has ONLY an end child, NO start child
        GtkPanedHandle        <-- outer has ONLY a handle, NO end child
    => feat:t0 and feat:t2 leaves are ENTIRELY MISSING from the widget tree.
    AFTER CLOSE (3->2): Paned w=710 pos=353 but contains ONLY a GtkPanedHandle — both children gone.
  implication: |
    This is NOT a paned-position bug. Leaves are not being (re)parented during the reflect rebuild.
    Only the LAST-built leaf in each paned survives; earlier set_start_child/set_end_child silently
    drop their widget. The w=0 cascades from missing children, not from position 0. _init_paned_position
    is a red herring (it skips when extent<=1, which is always true here because children are absent).

- timestamp: 2026-06-10T20:02
  checked: stderr under broadway.
  found: "Gtk-CRITICAL gtk_widget_unparent: assertion 'GTK_IS_WIDGET (widget)' failed" (during close path), AND no "already has a parent" crash — but the structural loss above is the real signal.
  implication: the unparent loop in _reflect_layout is mishandling widgets; combined with set_start/end_child this drops children.

## Evidence (cont.)

- timestamp: 2026-06-10T20:10
  checked: probe3 — real _make_leaf Boxes + real _reflect_layout, NO VTE spawn, two builds.
  found: |
    build 2 (3 nested leaves) has ALL leaves present and structurally CORRECT, BUT positions are wrong:
      outer Paned pos=14 (start = inner Paned crushed to w=14), end = t1 Box w=691.
      inner Paned pos=4  (t0 w=247? — actually inner got w=14 so children clipped).
    => the leaves are NOT lost; the SLIVER is a POSITION bug. The outer paned position is pinned to 14px.
  implication: |
    _init_paned_position sets position = get_width()//2 on the FIRST map signal. For NESTED paneds the
    map fires while the widget still has a tiny transient allocation (28px -> pos 14; 8px -> pos 4). The
    one-shot disconnect then NEVER corrects it. So the outer split pins to 14px and the inner subtree is
    crushed to a sliver. This is the LEFT-sliver from commit b487dfe.

- timestamp: 2026-06-10T20:11
  checked: difference between probe3 (correct leaves) and full driver (w=0 / leaves "missing").
  found: full driver shows w=0 across the whole subtree because the outer pos pinned to ~6px crushes EVERYTHING; the apparent "missing start/end children" in the walk is the sliver collapsing children to 0px (they ARE parented, just zero-sized), plus a sub-pixel position making the start subtree effectively invisible.
  implication: single root cause — premature/one-shot position pinning in _init_paned_position. The map-time get_width() is unreliable for nested paneds.

## Resolution

root_cause: |
  _init_paned_position pins each Gtk.Paned's split position to get_width()//2 on its FIRST "map"
  signal, then disconnects (one-shot). For NESTED paneds the map fires while the paned still has a
  tiny transient allocation, so the outer split is pinned to ~14px (the inner subtree is crushed to a
  ~6px sliver) and never corrected. Symptom: one terminal as a left sliver, the rest at ~0px.
fix: |
  Replaced the one-shot map/get_width() positioning with a max-position-driven proportional handler:
  connect notify::max-position -> set position = int(max_position * ratio) (ratio default 0.5),
  re-applied on EVERY max-position change (not one-shot), and connect notify::position to learn a new
  ratio from user drags (guarded by an _applying flag so our own set_position doesn't loop). max-position
  reflects the REAL usable extent and settles correctly even for nested paneds.
verification: |
  Headless broadway driver re-run AFTER fix: 3 terminals -> outer Paned pos=352/710 (50%), inner Paned
  pos=173/352 (50%), VTE widths 281/281/351 (all >100px, all visible). Close 1 of 3 -> 2 terminals
  re-fill at 350/349px. Layout-reflect path emits ZERO GTK-CRITICAL (verified via a no-spawn close
  probe). The single remaining gtk_widget_unparent critical is a pre-existing VTE-teardown artifact
  (fires only when the spawned zsh pgid is killed; present before the fix; not a layout defect).
files_changed: [src/arduis/window.py]
