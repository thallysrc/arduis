# Phase 3: Parallel Worktrees + Sidebar + RAM Groundwork - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-06-09
**Phase:** 03-parallel-worktrees-sidebar-ram-groundwork
**Areas discussed:** Pane layout model, Sidebar shape & behavior, Switch-shortcut scope, RAM visibility + active cap

---

## Pane layout model

### Multi-pane structure
| Option | Description | Selected |
|--------|-------------|----------|
| Single splittable canvas | One nested-GtkPaned tree fills main area; sidebar switches focus; matches v1 mockup | ✓ |
| Tabbed pane-trees | Keep Adw.TabView; each tab holds a GtkPaned tree (tmux windows model) | |
| Custom tiling manager | Hand-rolled BSP tiling widget; most power, most risk | |

### Worktree↔pane coupling
| Option | Description | Selected |
|--------|-------------|----------|
| Decoupled (sidebar=all, panes=subset) | Worktree can be active without a visible pane; select hidden → swap into focused pane | ✓ |
| Coupled (1 active = 1 pane) | Sidebar mirrors panes 1:1 | |

### New-worktree pane placement
| Option | Description | Selected |
|--------|-------------|----------|
| Splits the focused pane | New agent shows beside current one (tmux split feel) | ✓ |
| Replaces the focused pane | New agent takes over active pane | |
| Sidebar only, place manually | Appears in sidebar; user assigns to a pane | |

### Layout conveniences in Phase 3
| Option | Description | Selected |
|--------|-------------|----------|
| Free splits + zoom-focus | split/drag + zoom toggle; presets deferred | |
| Free splits + preset layouts | also add Layout-button presets (grid 2×2, columns) now | ✓ |
| Free splits only | no zoom, no presets | |

**Notes:** Zoom chord (`C-Space z`) exposed as a control now; the chord itself is Phase 5.
Preset subset selection when worktrees > cells is Claude's discretion (most-recently-focused).

---

## Sidebar shape & behavior

### Row content
| Option | Description | Selected |
|--------|-------------|----------|
| Dot + branch + RAM sub-line | dot = active/hibernated in P3 (enriched to running/waiting in P4) | ✓ |
| Dot + branch only | RAM elsewhere | |
| Branch + RAM, no dot | no dot until Phase 4 | |

### Selection behavior
| Option | Description | Selected |
|--------|-------------|----------|
| Focus if visible, else swap into focused pane | coherent with decoupled model | ✓ |
| Always swap into focused pane | | |
| Click focuses/swaps; double-click new split | | |

### $HOME scratch shell in sidebar
| Option | Description | Selected |
|--------|-------------|----------|
| Yes — pinned 'main' entry | matches mockup `main · zsh` row | ✓ |
| No — drop the scratch shell | | |

### Hibernate/Resume location
| Option | Description | Selected |
|--------|-------------|----------|
| Sidebar row right-click menu | reuses Phase-2 win.hibernate/win.resume actions | ✓ |
| Inline hover button | | |
| Both sidebar menu + pane header | | |

---

## Switch-shortcut scope

### Shortcut set in Phase 3
| Option | Description | Selected |
|--------|-------------|----------|
| Pane-focus move + worktree next/prev + by-number | full PAR-03 switching deliverable | ✓ |
| Worktree next/prev + by-number only | no directional pane move | |
| Worktree next/prev only | minimal | |

### Prefix mechanism
| Option | Description | Selected |
|--------|-------------|----------|
| Build C-Space prefix now (hardcoded) | prefix state machine now; config + split/zoom chords in Phase 5 | ✓ |
| Direct chords now, prefix system in Phase 5 | | |

### Wayland correctness scope
| Option | Description | Selected |
|--------|-------------|----------|
| App-scoped now; Wayland gate in Phase 5 | use app-scoped ShortcutController; explicit Wayland gate is UI-01 SC#3 | ✓ |
| Wayland app-scope is a Phase 3 gate too | | |

---

## RAM visibility + active cap

### What RSS to measure
| Option | Description | Selected |
|--------|-------------|----------|
| Whole process group (zsh + claude + children) via pgid | true cost; pgid already tracked | ✓ |
| Agent process + descendants only | under-counts | |
| Shell pid RSS only | badly under-counts | |

### Measurement method
| Option | Description | Selected |
|--------|-------------|----------|
| Read /proc directly (zero dependency) | /proc/<pid>/stat + smaps_rollup; GTK-free; no new package dep | ✓ |
| Add psutil dependency | convenient but new runtime dep for .deb/AUR | |

### Display + aggregate
| Option | Description | Selected |
|--------|-------------|----------|
| Sidebar row sub-line + footer total | per-worktree on rows + aggregate footer (~2s poll) | ✓ |
| Sidebar row only | no aggregate | |
| Sidebar row + pane header | | |

### Cap enforcement when at cap
| Option | Description | Selected |
|--------|-------------|----------|
| Prompt to hibernate one first | block + prompt; user hibernates one; then proceed | ✓ |
| Create it hibernated | create worktree, agent stays hibernated | |
| Hard block with message | refuse until user frees a slot manually | |
| Soft warning, allow anyway | advisory only | |

**Notes:** Cap counts active (non-hibernated) agents now; containers join the same cap in
Phase 7. Default ~6, configurable. Stored as an interim app-level setting until `.arduis.toml`
(Phase 6).

## Claude's Discretion

- GtkPaned tree management details, min pane size, focus tracking, hidden-worktree set
  representation.
- Preset-layout subset selection (most-recently-focused).
- ResourceMonitor poll cadence (~2s), RSS aggregation, RAM display format/units.
- Interim cap-setting storage mechanism (Phase-6 sourceable).
- Sidebar visual details within the Dracula palette.
- Pane-close behavior (default: hide worktree, keep active; hibernate stays explicit).

## Deferred Ideas

- Attention status dots + hooks watcher → Phase 4 (STATUS-01/02/03); idle auto-suspend → Phase 4 (RAM-04).
- Full configurable keybindings + split/zoom chords + Wayland gate → Phase 5 (UI-01); theme switching → Phase 5 (UI-02).
- `.arduis.toml` cap/config + setup commands → Phase 6.
- Containers + cap share + port badges → Phase 7.
- Conclude/remove worktree + teardown + diff/PR → Phase 8.
- Persist layout / reopen worktrees across quit→restart → v2 (PERSIST-01).
- Drag worktrees from sidebar into specific panes → revisit if focus-or-swap proves limiting.
