#!/usr/bin/env bash
# Native dev run script (replaces the obsolete Flatpak dev.sh — D-15).
# Spawns the host zsh through a direct PTY; no flatpak-spawn, no sandbox.
#
# Does NOT cd into the repo: arduis resolves the *launch* directory's git repo
# (D-03 — the + button is disabled outside a repo), so the caller's cwd MUST be
# preserved. main.py puts src/ on sys.path via its own absolute path, so no cd
# is needed for imports.
set -euo pipefail
DIR="$(dirname "$(readlink -f "$0")")"
exec python3 "$DIR/src/main.py"
