#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cmd="${1:-help}"
shift || true
case "$cmd" in
  check-contract)
    exec python3 "$SCRIPT_DIR/scripts/check_contract.py" "$@"
    ;;
  preprocess|ssml|plan-silence|sweep-plan|check-reference)
    exec python3 "$SCRIPT_DIR/scripts/chatterbox_contract_tools.py" "$cmd" "$@"
    ;;
  verify|test)
    exec "$SCRIPT_DIR/sanity.sh" "$@"
    ;;
  help|-h|--help)
    cat <<'EOF'
Usage: ./run.sh <command>

Commands:
  check-contract   Validate SKILL.md preserves required Chatterbox guidance
  preprocess       Normalize text, markdown emphasis, tags, and spaced ellipses
  ssml             Convert a small SSML fragment into Chatterbox text + pauses
  plan-silence     Compile [pause:*] / spaced ellipses into render_chunks JSON
  sweep-plan       Emit a backend-aware exaggeration/cfg_weight grid manifest
  check-reference  Validate a WAV reference clip before voice cloning
  verify           Run sanity.sh
EOF
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    exit 2
    ;;
esac
