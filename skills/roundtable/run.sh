#!/usr/bin/env bash
# Generate a pi-subagents workflowScript (roundtable or compete) with first-class $ask web models.
# Usage: ./run.sh --mode roundtable --packet-file p.md --seat gpt=openai-codex/gpt-5.5:high --seat opus=anthropic/claude-opus-4-8:high --web webgpt --web webkimi --web-research webx --out /tmp/rt.js
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
exec python3 "$DIR/scripts/gen.py" "$@"
