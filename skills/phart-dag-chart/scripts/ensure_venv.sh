#!/usr/bin/env bash
# Symlink skill .venv to 12TB storage (NVMe is code-only).
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STORE="/mnt/storage12tb/skills/phart-dag-chart"
VEN="$STORE/.venv"
if [[ ! -d /mnt/storage12tb ]]; then
  exit 0
fi
mkdir -p "$STORE"
if [[ -L "$SCRIPT_DIR/.venv" && "$(readlink -f "$SCRIPT_DIR/.venv")" == "$(readlink -f "$VEN")" ]]; then
  exit 0
fi
if [[ -e "$SCRIPT_DIR/.venv" && ! -L "$SCRIPT_DIR/.venv" ]]; then
  rm -rf "$VEN" 2>/dev/null || true
  mv "$SCRIPT_DIR/.venv" "$VEN"
  rmdir "$SCRIPT_DIR/.venv" 2>/dev/null || rm -rf "$SCRIPT_DIR/.venv"
fi
ln -sfn "$VEN" "$SCRIPT_DIR/.venv"
echo "linked $SCRIPT_DIR/.venv -> $VEN" >&2
