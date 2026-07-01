---
phase: 06-per-worktree-setup-via-arduis-toml
plan: 01
subsystem: infra
tags: [tomllib, hashlib, trust-gate, config, security, supply-chain, sha256, gtk-free]

requires:
  - phase: 05-agent-swap-and-themes
    provides: agentconfig tolerant-reader pattern + appconfig atomic tmp+os.replace write idiom (cloned here)
provides:
  - "repoconfig.load_repo_setup(repo_dir) -> RepoSetup — tolerant per-repo .arduis.toml [setup].commands reader (ENV-01)"
  - "repoconfig.setup_feed_bytes(worktree_dir, commands) -> bytes — cd-guarded, newline-joined shell-feed payload (ENV-02)"
  - "trust.setup_hash(commands) -> str — content hash trust key (re-prompts on any change)"
  - "trust.load_trusted/is_trusted/record_trust — fail-closed tolerant + atomic trust list at ~/.config/arduis/trusted_setups.toml"
affects: [window.py wiring (Plan 02), Phase 7 containers (shares .arduis.toml)]

tech-stack:
  added: []
  patterns:
    - "Tolerant stdlib tomllib reader returning a safe-default dataclass on ANY failure (cloned from agentconfig.load_agent_config)"
    - "Fail-closed security read: missing/garbage/wrong-type trust list -> {} -> re-prompt everything (never fail-open)"
    - "Content-hash trust key (direnv-allow model): sha256 over ordered command list, re-prompts on edit/add/remove/reorder"
    - "Atomic best-effort write: tmp + os.replace, makedirs parent, swallow OSError (cloned from appconfig.write_theme)"
    - "Local quoted-key TOML serializer for path keys containing /, ., - (separate from appconfig._serialize)"

key-files:
  created:
    - src/arduis/repoconfig.py
    - src/arduis/trust.py
    - tests/test_repoconfig.py
    - tests/test_trust.py
  modified: []

key-decisions:
  - "setup_feed_bytes always single-quotes the cd target (POSIX single-quote escaping), NOT shlex.quote — shlex.quote leaves ordinary paths bare (cd /t/wt) and would break the documented cd '<dir>' && byte contract"
  - "Trust list serialized with a small LOCAL quoted-key serializer in trust.py — NOT appconfig._serialize (which imposes a fixed user-config section order)"
  - "setup_hash hashes the RAW command list, not the cd-guarded feed, so the trust key is the repo's authored intent independent of where the worktree lands"

patterns-established:
  - "GTK-free domain module (no gi import) unit-tested headless — every src/arduis/*config.py + trust.py follows this discipline"
  - "Security read is fail-closed; security write is atomic + best-effort (a torn or failed write can never corrupt or forge the trust record)"

requirements-completed: [ENV-01, ENV-02]

duration: 9 min
completed: 2026-06-13
---

# Phase 6 Plan 01: Repo Setup Reader + Trust Primitives Summary

**Two GTK-free domain modules — a tolerant `.arduis.toml [setup]` reader with a cd-guarded newline-joined shell-feed builder (ENV-01/ENV-02), and a sha256 content-hash trust gate with a fail-closed, atomically-written `~/.config/arduis/trusted_setups.toml` — pinned by 34 unit tests.**

## Performance

- **Duration:** 9 min
- **Started:** 2026-06-13T00:00:00Z (approx)
- **Completed:** 2026-06-13
- **Tasks:** 3
- **Files modified:** 4 created

## Public Contract for Wave 2 (window.py / Plan 02)

These are the exact signatures Plan 02 wires into the task-create flow:

### `src/arduis/repoconfig.py`

```python
@dataclass
class RepoSetup:
    commands: list[str] = field(default_factory=list)   # ordered; [] = no setup / no gate

def load_repo_setup(repo_dir: str) -> RepoSetup
    # Reads <repo_dir>/.arduis.toml [setup].commands.
    # Absent file / invalid TOML / [setup] not a table / commands not a list -> RepoSetup([]).
    # Otherwise: non-empty stripped string entries, in order; blank/non-str dropped.
    # Unknown sections (e.g. Phase 7 [containers]) ignored silently. Never raises.

def setup_feed_bytes(worktree_dir: str, commands: list[str]) -> bytes
    # Empty commands -> b"" (defensive; caller should guard on commands == []).
    # Otherwise the EXACT shape (single-quoted cd target, newline-joined commands, NOT &&-chained):
    #   setup_feed_bytes("/t/wt", ["npm install", "cp .env.example .env"])
    #     == b"cd '/t/wt' &&\nnpm install\ncp .env.example .env\n"
    # Commands fed RAW (no shlex-wrap): && / $VAR / cp a b are preserved verbatim.
    # cd target with a space: starts with  cd '/t/my wt' &&\n
```

### `src/arduis/trust.py`

```python
def setup_hash(commands: list[str]) -> str
    # sha256("\n".join(commands)).hexdigest() — 64-char lowercase hex.
    # Stable for identical lists; CHANGES on any edit/add/remove/REORDER (order is semantic).

def load_trusted(path: str) -> dict[str, str]
    # {repo_id: hash} from [trusted] table. Fail-closed: missing/garbage/[trusted]-not-a-table
    # -> {}; non-str values dropped. Never raises.

def is_trusted(path: str, repo_id: str, commands_hash: str) -> bool
    # True ONLY for an exact (repo_id, commands_hash) pair. Fail-closed otherwise.

def record_trust(path: str, repo_id: str, commands_hash: str) -> None
    # Read-merge (preserves prior entries), overwrite a changed hash for the same repo,
    # re-serialize the whole [trusted] table, write atomically (tmp+os.replace, makedirs
    # parent). Best-effort: a failed write is swallowed. Never raises.
```

### Trust file path + shape (D-10)

- **Path:** `~/.config/arduis/trusted_setups.toml`
- **Shape:** one `[trusted]` table; each key is a quoted absolute repo path, value the sha256 hex:
  ```toml
  [trusted]
  "/home/u/Projects/my-repo" = "<sha256hex>"
  ```
- **repo_id (D-09):** Plan 02 passes `os.path.realpath(<project_root>/<repo_name>)` — `trust.py` treats it as an opaque key (does NOT compute realpath itself).

## Accomplishments

- `repoconfig.py`: tolerant `[setup].commands` reader (no-op on absent/garbage/wrong-type) + `setup_feed_bytes` cd-guard builder (ENV-01/ENV-02).
- `trust.py`: content-hash trust key + fail-closed tolerant trust list + atomic uncorruptible writer (criterion 4 primitives, threats T-06-01..04 mitigated at the module level).
- 34 new unit tests (15 repoconfig + 19 trust); full suite 240 -> 274 passed, zero regressions; both modules GTK-free.

## Task Commits

1. **Task 1: repoconfig.py reader + setup_feed_bytes** - `8f01b93` (feat)
2. **Task 2: trust.py hash + atomic trust list** - `2d9de72` (feat)
3. **Task 3: Full suite green** - no code change (suite was already green at 274 passed)

_Note: This is a TDD plan; per the plan's instruction each task combines RED+GREEN into one feat commit (module + its tests written together)._

## Files Created/Modified

- `src/arduis/repoconfig.py` - `RepoSetup`, `load_repo_setup`, `setup_feed_bytes` (GTK-free, stdlib only)
- `src/arduis/trust.py` - `setup_hash`, `load_trusted`, `is_trusted`, `record_trust` (GTK-free, stdlib only)
- `tests/test_repoconfig.py` - 15 tests: tolerant parse + ordering + drop-blank/non-str + exact feed-bytes shape + raw commands + GTK-free
- `tests/test_trust.py` - 19 tests: hash stability/change + fail-closed tolerant read + atomic round-trip + exactness + parent-dir + best-effort + path-key + GTK-free

## Decisions Made

- **Single-quote the cd target, not `shlex.quote`** — `shlex.quote("/t/wt")` returns `/t/wt` (no special char), which fails the plan's own documented `cd '/t/wt' &&` byte contract. Using deterministic POSIX single-quote escaping (`'...'` with `'\''` for embedded quotes) honors the exact byte contract for every path. Recorded as a deviation (Rule 1).
- **Local quoted-key serializer in `trust.py`** — per `<plan_decisions>`, did NOT import `appconfig._serialize` (it imposes a fixed user-config `_SECTION_ORDER`). The trust file is a separate single-`[trusted]`-table file with `/`/`.`/`-` path keys.
- **Hash the RAW commands, not the feed** — trust key is the repo's authored intent, independent of worktree location.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `setup_feed_bytes` cd-target quoting: `shlex.quote` contradicts the documented byte contract**
- **Found during:** Task 1 (repoconfig.py / setup_feed_bytes)
- **Issue:** The plan's `<action>` code snippet used `shlex.quote(worktree_dir)`, but the plan's own `<behavior>` and the Wave 2 contract require the EXACT bytes `cd '/t/wt' &&\n...`. `shlex.quote` only quotes when it detects a special character, so for an ordinary path like `/t/wt` it returns the bare `/t/wt`, producing `cd /t/wt &&` — failing `test_feed_exact_cd_guard_newline_joined`.
- **Fix:** Replaced `shlex.quote(worktree_dir)` with deterministic POSIX single-quoting (`"'" + worktree_dir.replace("'", "'\\''") + "'"`), which always single-quotes the target and still safely escapes embedded quotes. Removed the now-unused `shlex` import and updated the docstring. The "space in path" test (`cd '/t/my wt' &&`) and the "raw commands not shlex-wrapped" test both still pass, confirming the security property (only the dir target is quoted; commands stay raw) is preserved.
- **Files modified:** src/arduis/repoconfig.py
- **Verification:** `tests/test_repoconfig.py -x -q` -> 15 passed, including the exact-shape and space-in-path cases.
- **Committed in:** `8f01b93` (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug).
**Impact on plan:** Necessary for correctness — the fix makes the implementation satisfy the plan's own documented byte contract and the Wave 2 contract. No scope creep; the security property (only the cd target is quoted, commands are raw) is unchanged.

## Issues Encountered

None - the only friction was the `shlex.quote` vs. exact-contract mismatch, handled as the Rule 1 deviation above.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Wave 2 (Plan 02, `window.py` wiring) can now call: `load_repo_setup(repo_dir)` per chosen repo, `setup_hash(setup.commands)` to derive the trust key, `is_trusted(TRUST_PATH, realpath, hash)` to decide whether to gate, `record_trust(...)` on "Confiar e rodar", and `setup_feed_bytes(worktree_dir, setup.commands)` to feed the shell terminal (on CREATE only, into the `t1` shell, before the agent — Pitfall 2/3).
- Trust file path constant for Plan 02: `~/.config/arduis/trusted_setups.toml` (expand `~` in the wiring; `trust.py` itself takes an explicit path for testability).
- No blockers. Both modules GTK-free; full suite green (274 passed).

## Self-Check: PASSED

- All 4 created files exist on disk (repoconfig.py, trust.py, test_repoconfig.py, test_trust.py).
- Both task commits present in git history (8f01b93, 2d9de72).
- Full suite: 274 passed (240 baseline + 34 new), zero regressions.
- GTK-free verified: `grep -c "import gi\|from gi"` == 0 for both modules.

---
*Phase: 06-per-worktree-setup-via-arduis-toml*
*Completed: 2026-06-13*
