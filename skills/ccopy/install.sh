#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="${HOME}/.local/bin"
mkdir -p "$TARGET_DIR"
ln -sfn "$ROOT/bin/ccopy" "$TARGET_DIR/ccopy"
ln -sfn "$ROOT/bin/cursor-copy" "$TARGET_DIR/cursor-copy"
echo "Installed ccopy -> $TARGET_DIR/ccopy"
echo "Installed cursor-copy -> $TARGET_DIR/cursor-copy (compat alias)"
echo "Make sure $TARGET_DIR is on PATH."
