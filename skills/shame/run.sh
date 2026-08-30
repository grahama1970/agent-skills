#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cmd="${1:-help}"
shift || true

case "$cmd" in
  capture)
    node "$SKILL_DIR/scripts/capture-last-assistant.mjs" "$@"
    ;;
  audio)
    node "$SKILL_DIR/scripts/install-shame-audio.mjs" "$@"
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
                 [--memory|--no-memory] [--memory-collection NAME] [--search-collection NAME]
  run.sh capture --text TEXT --verdict reject --reason commit_laundering
  run.sh audio install [--source FILE] [--extension-dir DIR]
  run.sh audio status [--extension-dir DIR]
  run.sh path

Audio command installs one short Chatterbox word: "shame". No bell, no loop.

Default output:
  JSONL:  /mnt/storage12tb/skills/shame/training/classifier-feedback.jsonl
  Memory: structured collection shame_training_examples via POST /store + /recall/by-keys;
          searchable project_knowledge shadow doc via POST /store + /recall

Legacy --label is accepted for: false_positive, false_negative,
good_status_report, commit_laundering, jargon_no_status.
EOF
    ;;
  *)
    echo "unknown command: $cmd" >&2
    exit 2
    ;;
esac
