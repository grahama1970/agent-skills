#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cmd="${1:-help}"; shift || true
case "$cmd" in
  validate) /usr/bin/python3 "$SKILL_DIR/scripts/receipt_envelope.py" validate "$@" ;;
  graph)    sed -n '/```mermaid/,/```/p' "$SKILL_DIR/SKILL.md" ;;
  *)        echo "usage: run.sh validate <file.json|-> | graph"; exit 2 ;;
esac
