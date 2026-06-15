# Deferred Items — Phase 03.4

Out-of-scope discoveries logged during execution (NOT fixed here — see scope boundary).

## D-DEFER-01: Pre-existing theme smoke failure `repeated_switches_no_crash`

- **Found during:** Plan 05 Task 2 (running all smokes before the human checkpoint).
- **Smoke:** `tests/smoke/test_theme_switch_smoke.py` → `SMOKE repeated_switches_no_crash FAIL`
  (8/9; the other 8 checks PASS, including `switch_flips_current_theme`, `switch_replaces_provider`,
  `new_terminal_born_in_active_theme`).
- **Why out of scope:** Phase 03.4 touched NO theme code — `git log 75c193e..HEAD -- src/arduis/theme.py
  src/arduis/appconfig.py` is empty. Confirmed pre-existing by running the SAME smoke at the
  pre-03.4 base commit `c67f8ec` (Phase-03.3 tip) in an isolated worktree → identical
  `repeated_switches_no_crash FAIL` (8/9). It is a Phase-5 theme-switch concern, not a regression
  introduced by the multi-project switcher.
- **Likely cause (not investigated, deferred):** repeated CSS provider swaps under headless broadway
  appear to trip a crash/assert on the Nth switch; needs a Phase-5 owner to reproduce on a real
  display and decide if it is a broadway-only artifact or a real provider-leak.
- **Routing:** belongs to the Phase-5 theme-switch plan (UI-02), not Phase 03.4.
