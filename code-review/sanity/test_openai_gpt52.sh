#!/usr/bin/env bash
# Sanity check: OpenAI Codex with GPT-5.2
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/run_sanity.sh" openai gpt-5.2 "${1:-120}"
