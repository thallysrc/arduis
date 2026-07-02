"""Superseded by 03.4 project switcher — repo chip-state removed (D-04).

The topbar previously rendered one chip per member repo (03.3). That was the
WRONG level: the topbar holds switchable PROJECTS (each a multi-repo root), not
repos. Member repos now surface only in the "Novo workspace" dialog. This module is
kept empty-but-present so the package surface is unchanged; the project-switcher
widget lives in ``window.py`` (Plan 03+).

Imports NO gi.
"""
from __future__ import annotations
