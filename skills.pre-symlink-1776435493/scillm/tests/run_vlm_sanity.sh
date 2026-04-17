#!/bin/bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
export CHUTES_API_BASE="https://example.com/v1"
export CHUTES_API_KEY="dummy-key"
export CHUTES_VLM_MODEL="dummy-vlm-model"

# Dry-run describe (local file + remote inline)
"$SKILL_DIR/run.sh" vlm describe "$SKILL_DIR/tests/fixtures/checkerboard.png" \
    --prompt "Describe checkerboard" --json --dry-run >/dev/null

# Dry-run describe remote direct (no inline)
"$SKILL_DIR/run.sh" vlm describe "https://picsum.photos/seed/scillm/32/32" \
    --prompt "Remote direct" --json --dry-run >/dev/null

# Dry-run describe remote inline
"$SKILL_DIR/run.sh" vlm describe "https://picsum.photos/seed/scillm-inline/32/32" \
    --inline-remote-images --prompt "Remote inline" --json --dry-run >/dev/null

# Dry-run batch (local + remote entries)
"$SKILL_DIR/run.sh" vlm batch --input "$SKILL_DIR/tests/fixtures/vlm_batch.jsonl" \
    --json --dry-run --inline-remote-images >/dev/null

echo "VLM sanity (dry-run) passed"
