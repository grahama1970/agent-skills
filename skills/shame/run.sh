#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cmd="${1:-help}"
shift || true

case "$cmd" in
  capture)
    node "$SKILL_DIR/scripts/capture-last-assistant.mjs" "$@"
    ;;
  path)
    printf '%s\n' "${LAZY_REPORT_SHAME_TRAINING_JSONL:-/mnt/storage12tb/skills/shame/training/classifier-feedback.jsonl}"
    ;;
  help|--help|-h)
    cat <<'EOF'
Usage:
  run.sh capture [--session FILE] [--entry-id ID] [--response-sha256 HASH]
                 [--verdict allow|reject|warn|needs_review] [--reason REASON]
                 [--note TEXT] [--out FILE]
                 [--memory|--no-memory] [--memory-collection NAME]
  run.sh capture --text TEXT --verdict reject --reason commit_laundering
  run.sh path

Default output:
  JSONL:  /mnt/storage12tb/skills/shame/training/classifier-feedback.jsonl
  Memory: collection shame_training_examples via POST /store, then read back via /recall/by-keys

Legacy --label is accepted for: false_positive, false_negative,
good_status_report, commit_laundering, jargon_no_status.
EOF
    ;;
  *)
    echo "unknown command: $cmd" >&2
    exit 2
    ;;
esac
