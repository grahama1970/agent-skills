#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cmd="${1:-help}"
shift || true
case "$cmd" in
  analyze)
    exec python3 "$SCRIPT_DIR/scripts/analyze_voice.py" "$@"
    ;;
  fixture-wav)
    exec python3 "$SCRIPT_DIR/scripts/make_fixture_wav.py" "$@"
    ;;
  verify|test)
    exec "$SCRIPT_DIR/sanity.sh" "$@"
    ;;
  help|-h|--help)
    cat <<'EOF'
Usage: ./run.sh <command> [options]

Commands:
  analyze      Evaluate a Chatterbox WAV/FLAC/MP3 voice artifact
  fixture-wav  Generate a deterministic synthetic WAV for tests/evals
  verify       Run sanity.sh

Example:
  ./run.sh analyze --audio generated.wav --target-label reassuring --target-arousal 0.35 --target-valence 0.4 --json
EOF
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    exit 2
    ;;
esac
