"""GTK-free ``gh`` translation layer for Phase 8 (REVIEW-02 / GIT-01).

This is the pure, unit-testable seam for GitHub-CLI introspection. It mirrors
``compose.py``'s argv-builder + json-shape-parse split: it builds the list-form
``gh`` argv, parses the STABLE ``--json`` contract, probes for gh's presence, and
maps gh's exit codes / absence to glanceable pt-BR sublines — it never invokes a
process. The async IO is ``git_service.run_git_async``'s job: ``gh`` is just
another argv list on the SAME runner, so there is NO new service module (D-01).

The correctness here is threefold:
- READ is read-only and via ``--json`` (never text-scraped) — ``argv_pr_view`` +
  ``parse_pr_view`` (REVIEW-02). The ONE allowed WRITE is ``gh pr create --web``
  (D-05, A8) — the AFK-safe browser form, asserted by argv shape only and NEVER
  executed in tests.
- DEGRADE gracefully (D-06): when gh is ABSENT (``gh_available()`` is False) the
  window shows ``GH_ABSENT_MSG`` and never calls gh; when gh returns exit code
  ``4`` (= needs authentication, VERIFIED on host via ``gh help exit-codes``) the
  window shows ``GH_UNAUTH_MSG``. Both are STATIC states — no retry storm.
- ``parse_pr_view`` RAISES (``ValueError``/``TypeError``) on garbage / non-dict
  rather than returning ``None``, so the Wave-2 caller wraps it in
  ``try/except (ValueError, TypeError)`` and degrades WITHOUT crashing the GLib
  loop (T-08-05).

GTK-free discipline (CLAUDE.md / D-01): this module imports ``json`` / ``shutil``
ONLY — never ``gi``. ``test_gh.py`` asserts that by scanning the source.

Threats (see 08-02-PLAN threat register):
- T-08-04 (tampering/EoP): every argv is a Python LIST with the branch a DISCRETE
  element — no shell, no ``shell=True`` (the Wave-2 caller routes it through
  HostRunner, mirroring git_service T-02-01).
- T-08-05 (injection): ``parse_pr_view`` does ``json.loads`` + a dict shape-guard
  and the result is DISPLAYED only (a subline) — never eval'd, never used to build
  a path or command.
- T-08-07 (the ONE write): ``gh pr create --web`` is roadmap-sanctioned
  (REVIEW-02); ``--web`` keeps it browser-driven and read-only-in-app afterward.
"""
from __future__ import annotations

import json
import shutil

__all__ = [
    "PR_VIEW_FIELDS",
    "GH_ABSENT_MSG",
    "GH_UNAUTH_MSG",
    "GH_EXIT_NEEDS_AUTH",
    "argv_pr_view",
    "argv_pr_create_web",
    "parse_pr_view",
    "gh_available",
    "degrade_message",
    "format_pr_subline",
    "format_branch_subline",
]


# --- the stable --json contract (gh 2.93, VERIFIED on host) ------------------

PR_VIEW_FIELDS = "state,number,title,url,isDraft,reviewDecision,mergeable,headRefName"

# gh exit-code table (VERIFIED on host via `gh help exit-codes`):
#   0 = ok ; 1 = generic failure ; 2 = cancelled ; 4 = requires authentication
GH_EXIT_NEEDS_AUTH = 4

# Degrade sublines (D-06) — PINNED pt-BR strings the Wave-2/3 window displays.
GH_ABSENT_MSG = "gh ausente"
GH_UNAUTH_MSG = "gh não autenticado"


# --- argv builders (REVIEW-02 / D-05, T-08-04) -------------------------------

def argv_pr_view(branch: str) -> list[str]:
    """``gh pr view <branch> --json <fields>`` as a LIST (read-only).

    Run with ``cwd=<worktree dir>`` (via ``run_git_async(..., cwd=...)``, D-07) so
    gh infers the repo from the worktree's git remote — no ``-R owner/repo`` dance.
    The branch is a DISCRETE argv element (T-08-04); ``--json`` forces the STABLE
    machine contract (never text-scraped).
    """
    return ["gh", "pr", "view", branch, "--json", PR_VIEW_FIELDS]


def argv_pr_create_web() -> list[str]:
    """``gh pr create --web`` — the ONE allowed write (D-05/A8, T-08-07).

    ``--web`` opens the browser PR form: zero in-app prompt UI, AFK-safe, and the
    app stays read-only-in-app afterward. Asserted by argv SHAPE only — this is
    NEVER executed in any test.
    """
    return ["gh", "pr", "create", "--web"]


# --- the json-shape parser (REVIEW-02, T-08-05) ------------------------------

def parse_pr_view(stdout: str) -> dict:
    """``json.loads`` the ``gh pr view --json`` output + guard the dict shape.

    Returns the PR dict on valid JSON. RAISES (does NOT return ``None``) so the
    contract is explicit and the caller degrades via ``try/except``:
    - ``json.loads`` raises ``ValueError`` (``json.JSONDecodeError`` subclass) on
      malformed JSON;
    - a non-dict top-level (a JSON list / scalar) raises ``TypeError``.

    The Wave-2 caller wraps this in ``except (ValueError, TypeError)`` and degrades
    silently — gh garbage NEVER crashes the GLib loop (T-08-05).
    """
    data = json.loads(stdout)
    if not isinstance(data, dict):
        raise TypeError("unexpected gh pr view shape")
    return data


# --- gh presence probe + degrade mapping (D-06) ------------------------------

def gh_available() -> bool:
    """True iff ``gh`` is on ``PATH``. The window checks this BEFORE any gh call.

    When False, the window shows ``GH_ABSENT_MSG`` and never invokes gh — there is
    no process to crash and no retry storm.
    """
    return shutil.which("gh") is not None


def degrade_message(rc: int) -> str | None:
    """Map a NON-zero gh exit code to a degrade subline, else ``None``.

    Only exit ``4`` (= needs authentication, VERIFIED) maps to a STATIC degrade
    state (``GH_UNAUTH_MSG``); every other non-zero rc returns ``None`` so the
    caller falls through to its own "sem PR" / generic handling without a retry
    storm.
    """
    return GH_UNAUTH_MSG if rc == GH_EXIT_NEEDS_AUTH else None


# --- glanceable subline formatters (GIT-01 display) --------------------------

def format_pr_subline(pr: dict) -> str:
    """Render a parsed PR dict to a short glanceable subline string.

    e.g. ``"PR #42 open"``, ``"PR #7 open (rascunho)"``. Tolerant of missing keys
    (gh may return a partial dict): a missing ``number`` yields ``"sem PR"``. Pure
    — no ``gi``, never mutates the input.
    """
    num = pr.get("number")
    if num is None:
        return "sem PR"
    state = (pr.get("state") or "").lower()
    draft = " (rascunho)" if pr.get("isDraft") else ""
    return f"PR #{num} {state}{draft}"


def format_branch_subline(branch: str, ahead: int, behind: int) -> str:
    """Render the branch + ahead/behind counts (the Plan-01 tuple) to a subline.

    e.g. ``"feat/x · ↑3 ↓0"``; when ``ahead == behind == 0`` (no upstream / in
    sync) just the branch name (``"feat/x"``). The window concatenates this with
    the PR subline. Pure and unit-testable.
    """
    if ahead == 0 and behind == 0:
        return branch
    return f"{branch} · ↑{ahead} ↓{behind}"
