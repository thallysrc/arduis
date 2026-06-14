"""Unit coverage for the GTK-free ``gh.py`` (REVIEW-02 / GIT-01, D-05/D-06).

This pins the gh CONTRACT the Wave-2/3 window wiring will call, WITHOUT ever
invoking gh (the ``gh pr create`` builder — the ONE allowed write — is asserted
by argv SHAPE only, never executed):

- the argv builders (``argv_pr_view``, ``argv_pr_create_web``) return the exact
  verified list-form argv (gh 2.93, 08-RESEARCH);
- ``parse_pr_view`` does ``json.loads`` + a dict shape-guard, returning the dict
  on valid JSON and RAISING (ValueError/TypeError) on garbage / non-dict so the
  caller can degrade WITHOUT crashing the GLib loop (T-08-05);
- ``gh_available`` is the ``shutil.which`` absence probe (D-06);
- the degrade helpers map exit-4 -> "gh não autenticado" and absent ->
  "gh ausente" so gh missing/unauthed never crashes (D-06, gh exit-code 4 =
  needs auth, VERIFIED on host);
- the subline formatters render the glanceable status strings (GIT-01).

GTK-free discipline (CLAUDE.md / D-01): the source imports NO ``gi``; this test
asserts that directly by scanning the module source.
"""
from __future__ import annotations

import inspect

from arduis import gh


# --- argv builders (REVIEW-02 / D-05, T-08-04) -------------------------------

def test_argv_pr_view_shape():
    assert gh.argv_pr_view("feat/x") == [
        "gh", "pr", "view", "feat/x", "--json", gh.PR_VIEW_FIELDS,
    ]


def test_pr_view_fields_contains_expected_keys():
    for key in ("state", "number", "url", "isDraft"):
        assert key in gh.PR_VIEW_FIELDS


def test_argv_pr_create_web_is_the_one_allowed_write():
    # The ONE allowed write — argv shape only; NEVER executed.
    assert gh.argv_pr_create_web() == ["gh", "pr", "create", "--web"]


# --- parse_pr_view: dict on valid JSON, RAISES on garbage (T-08-05) ----------

def test_parse_pr_view_returns_dict_on_valid_json():
    out = '{"number":42,"state":"OPEN","isDraft":false}'
    assert gh.parse_pr_view(out) == {
        "number": 42, "state": "OPEN", "isDraft": False,
    }


def test_parse_pr_view_raises_value_error_on_bad_json():
    # json.JSONDecodeError is a ValueError subclass.
    import pytest
    with pytest.raises(ValueError):
        gh.parse_pr_view("not json")


def test_parse_pr_view_raises_type_error_on_list_top_level():
    import pytest
    with pytest.raises(TypeError):
        gh.parse_pr_view("[1,2,3]")


def test_parse_pr_view_raises_type_error_on_scalar_top_level():
    import pytest
    with pytest.raises(TypeError):
        gh.parse_pr_view("42")


# --- gh_available probe (D-06) -----------------------------------------------

def test_gh_available_returns_bool():
    assert isinstance(gh.gh_available(), bool)


def test_gh_available_true_when_which_finds_gh(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/gh")
    assert gh.gh_available() is True


def test_gh_available_false_when_which_returns_none(monkeypatch):
    import shutil
    monkeypatch.setattr(shutil, "which", lambda name: None)
    assert gh.gh_available() is False


# --- degrade helpers (D-06) — PINNED pt-BR strings ---------------------------

def test_degrade_constants_pinned():
    assert gh.GH_ABSENT_MSG == "gh ausente"
    assert gh.GH_UNAUTH_MSG == "gh não autenticado"
    assert gh.GH_EXIT_NEEDS_AUTH == 4


def test_degrade_message_exit_4_is_unauthed():
    assert gh.degrade_message(4) == "gh não autenticado"


def test_degrade_message_other_rc_is_none():
    assert gh.degrade_message(1) is None
    assert gh.degrade_message(2) is None


# --- subline formatters (GIT-01 display) -------------------------------------

def test_format_pr_subline_open():
    assert gh.format_pr_subline({"number": 42, "state": "OPEN"}) == "PR #42 open"


def test_format_pr_subline_draft():
    assert gh.format_pr_subline(
        {"number": 7, "state": "OPEN", "isDraft": True}
    ) == "PR #7 open (rascunho)"


def test_format_pr_subline_no_number_is_sem_pr():
    assert gh.format_pr_subline({}) == "sem PR"


def test_format_branch_subline_with_ahead_behind():
    assert gh.format_branch_subline("feat/x", 3, 0) == "feat/x · ↑3 ↓0"


def test_format_branch_subline_in_sync_is_branch_only():
    assert gh.format_branch_subline("feat/x", 0, 0) == "feat/x"


# --- GTK-free discipline (CLAUDE.md / D-01) ----------------------------------

def test_gh_module_is_gtk_free():
    source = inspect.getsource(gh)
    assert "import gi" not in source
    assert "from gi" not in source
