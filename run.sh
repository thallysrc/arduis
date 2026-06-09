#!/usr/bin/env bash
# Native dev run script (replaces the obsolete Flatpak dev.sh — D-15).
# Spawns the host zsh through a direct PTY; no flatpak-spawn, no sandbox.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 src/main.py
