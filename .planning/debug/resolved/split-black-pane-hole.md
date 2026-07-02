---
status: resolved
trigger: "Intermitente: ao fazer splits de terminais na janela do arduis, às vezes uma região do layout fica preta — um buraco onde nenhum pane renderiza (ex.: área superior-esquerda preta enquanto os outros panes renderizam normalmente)."
created: 2026-07-02
updated: 2026-07-02
---

## Current Focus

hypothesis: CONFIRMED + FIXED — tick-callback now guarantees the proportional split position lands even when GTK4 coalesces the settling max-position notification; _learn hardened via pure _learned_ratio guard.
test: 468 tests pass incl. 6 new _learned_ratio cases. Tick-timing behavior is allocation-dependent → manual acceptance.
expecting: no black region after successive splits; no resize needed to fill it.
next_action: MANUAL ACCEPTANCE — do several successive splits in the app; confirm no black hole appears. Layout fix committed as 1145132.

## Symptoms

expected: Ao criar um split, todos os panes ocupam e renderizam sua área; nenhuma região da janela fica vazia/preta.
actual: Às vezes, logo após criar um split novo, uma região do layout fica preta (sem terminal renderizado). Screenshot 2026-07-02 mostra a área superior-esquerda inteira preta enquanto 6 outros panes renderizam normalmente.
errors: Desconhecido — stderr do app não verificado.
reproduction: Intermitente; ao fazer splits sucessivos. O buraco DESAPARECE ao redimensionar a janela ou interagir.
started: Recente; após features de snapshot/restore de layouts e SplitNode.ratio.

## Eliminated

- hypothesis: The uncommitted changes in src/arduis/window.py cause the black hole.
  evidence: `git diff -- src/arduis/window.py` touches only the attention/status scanner (_setup_attention, _apply_state_file, _apply_main_state_file, _terminal_tail_text, _scan_set_status, dialog-on-screen set). The layout code (_reflect_layout, _build_widget, _init_paned_position) is byte-identical to HEAD. The two grep "ratio" hits were false matches inside the word "registration".
  timestamp: 2026-07-02

- hypothesis: node.ratio is poisoned to ~0 by _learn (deferred notify::position echo misread as a drag), producing the collapsed child.
  evidence: Plausible latent hazard (the `applying` guard only suppresses SYNCHRONOUS echoes; GTK4 can defer notify::position to the next size-allocate). BUT a poisoned ratio would NOT self-heal on resize — resize re-fires notify::max-position → _apply(maxp * ~0) = 0 → still black. The observed "vanishes on resize" is inconsistent with ratio poisoning being the PRIMARY cause of this symptom. Kept as a secondary/related risk (persistent holes + polluted layouts.json), not the cause of this report.
  timestamp: 2026-07-02

## Evidence

- timestamp: 2026-07-02
  checked: knowledge-base.md
  found: One prior entry (workspace-sidebar-highlight-wrong-item) — no keyword overlap with split/paned/black/render. No known pattern.
  implication: Novel investigation.

- timestamp: 2026-07-02
  checked: _split_active_pane (window.py:4248) + LayoutModel.split (layout.py:58)
  found: Every split creates a fresh SplitNode with default ratio=0.5, then calls _reflect_layout(), which REBUILDS the entire canvas widget tree from scratch (new Gtk.Paned objects for every SplitNode).
  implication: A new split is not an incremental widget insert — it re-triggers a full nested-tree allocation, exposing any allocation/positioning race across ALL paneds, not just the new one.

- timestamp: 2026-07-02
  checked: _reflect_layout (window.py:5258) + _build_widget (5285)
  found: Tree is built bottom-up (children set, _init_paned_position called) BEFORE the root is attached to _canvas_slot. So every Paned's positioning signals are connected while the Paned is still unallocated (max-position ≈ 0/1). Real allocation only happens after set_child at the end.
  implication: All position application is deferred to signal callbacks that fire during the post-attach allocation passes — timing dependent.

- timestamp: 2026-07-02
  checked: _init_paned_position (window.py:5324) + git show 65a3989 / 49f7178
  found: Split position is set ONLY inside `_apply`, connected to `notify::max-position`: `if maxp <= 1: return  # wait for the next notify` else `set_position(int(maxp * ratio))`. There is NO map/realize/idle/tick fallback that guarantees the position is (re)applied once the paned reaches its final settled allocation. grep confirms set_position exists in exactly one place. The design ASSUMES notify::max-position always re-fires after the paned gets its real usable extent. Commit 65a3989 replaced the older one-shot `map`+get_width() approach (b487dfe), which had the opposite bug (nested paneds pinned to ~6px transient allocation).
  implication: For a nested tree, an inner paned's usable extent depends on its ancestor's position, which is itself set reactively. During the initial multi-pass allocation of a freshly rebuilt tree, GTK4 coalesces GObject notifications; if the FINAL settled max-position value does not differ from an intermediate value (or the final settling pass does not re-emit), the inner paned's `_apply` runs only on a transient/tiny max-position (or never) and the paned keeps a degenerate position → one child gets ≈0 extent → that whole subtree region renders black with no pane in it. This is inherently intermittent (depends on allocation-pass ordering, which varies with tree shape/size/timing). A window resize changes max-position → notify::max-position re-fires → `_apply` runs with the still-intact 0.5 ratio → position corrected → hole vanishes. This matches the "área inteira preta (nenhum pane)" + "desaparece ao redimensionar" symptom exactly.

## Resolution

root_cause: |
  In src/arduis/window.py, `_init_paned_position` (introduced by commit 65a3989 "proportional
  nested-Paned splits via max-position", carried forward by 49f7178) applies each Gtk.Paned's
  split position PURELY reactively from the `notify::max-position` signal, with an early-return
  `if maxp <= 1: return` that "waits for the next notify". There is no guaranteed final
  application (no map/realize/idle/tick fallback). Creating a split calls `_reflect_layout`,
  which tears down and rebuilds the ENTIRE nested Gtk.Paned tree. During that fresh multi-pass
  nested allocation, GTK4 coalesces max-position notifications; intermittently the settled
  max-position for some (often outer/left) paned does not re-notify after it reaches its real
  extent, so `_apply` either ran only on a tiny transient extent or never ran for that paned.
  The paned is left at a degenerate position — one child gets ≈0 width/height — so an entire
  region of the layout has no pane allocated and renders black. Because the model ratio stays a
  clean 0.5, ANY later allocation (window resize / interaction) re-emits notify::max-position,
  `_apply` runs, and the hole self-heals — exactly the reported behavior. Secondary latent
  hazard in the same function: `_learn`'s `applying` flag only suppresses synchronous echoes of
  our own set_position; GTK4 can defer notify::position to a later size-allocate, so a deferred
  echo or transient allocation can be misread as a user drag and poison `node.ratio` (which
  would then also get persisted to layouts.json and produce a resize-RESISTANT hole) — worth
  hardening alongside the fix, though it is not the cause of THIS (self-healing) report.
fix: |
  src/arduis/window.py, `_init_paned_position`: added a GUARANTEED final application
  path alongside the existing reactive `notify::max-position` one. A tick callback
  (`paned.add_tick_callback`) re-runs `_apply` every frame until the paned reaches a
  real settled allocation (`max-position > 1`), then self-removes (`GLib.SOURCE_REMOVE`);
  a 600-frame safety budget prevents unbounded ticking for a paned that never gets a
  usable allocation. This closes the coalesced-notification race: even when GTK4 drops
  the final max-position re-notify for a freshly rebuilt nested tree, the frame clock
  drives the proportional split into place so no child is left at ≈0 extent (no black
  hole). The reactive path is kept for later re-distributions (window resize).

  Secondary hardening: extracted a pure module-level `_learned_ratio(position,
  max_position, last_set, settled)` and routed `_learn` through it. It rejects
  (a) unallocated reads (`max-position <= 1`), (b) pre-settle noise (before we've
  applied our own position), (c) echoes of our own `set_position` via exact `last_set`
  match (robust to GTK4 deferring `notify::position` to a later size-allocate — the old
  synchronous `applying` flag missed this), and (d) degenerate ratios (<=0.02 / >=0.98,
  a transient collapse). This prevents a bad ratio from being persisted to layouts.json
  (which would have produced a resize-RESISTANT hole).
verification: |
  Added tests/test_paned_ratio_guard.py (6 cases) locking the pure `_learned_ratio`
  guard: ignores unallocated/pre-settle/echo/degenerate positions, learns genuine
  drags, and learns at the plausible boundaries. Full suite green: 468 passed. The
  tick-callback timing fix requires a real GTK frame clock (allocation-dependent) so it
  is covered by manual acceptance — repeated successive splits should no longer leave a
  black region, and no resize should be needed to fill it.
files_changed:
  - src/arduis/window.py (_init_paned_position rewrite + new _learned_ratio helper)
  - tests/test_paned_ratio_guard.py (new regression test)
