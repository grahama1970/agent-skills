#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cmd="${1:-help}"; shift || true
case "$cmd" in
  validate) /usr/bin/python3 "$SKILL_DIR/scripts/receipt_envelope.py" validate "$@" ;;
  membership) /usr/bin/python3 "$SKILL_DIR/scripts/membership.py" "${1:-validate}" "${2:-$SKILL_DIR/members.json}" ;;
  graph)    sed -n '/```mermaid/,/```/p' "$SKILL_DIR/SKILL.md" ;;
  *)        echo "usage: run.sh validate <file.json|-> | membership [validate|table] [members.json|-] | graph"; exit 2 ;;
esac
