#!/usr/bin/env bash
# model-training-gate.sh — PostToolUse hook
# Catches agent trying to train/relabel without preflight checks
# Fires on: Bash commands containing create-gpt, relabel, train, batch
set -euo pipefail

TOOL_NAME="${CLAUDE_TOOL_NAME:-}"
TOOL_INPUT="${CLAUDE_TOOL_INPUT:-}"

[[ "$TOOL_NAME" != "Bash" ]] && exit 0

# Check if command involves training or batch relabeling
if echo "$TOOL_INPUT" | grep -qiE '(create-gpt.*train|relabel|batch.*label|sft.*train|grpo.*train)'; then
    # Check if preflight was run this session (look for evidence file)
    PREFLIGHT_LOG="$HOME/.pi/skills/prompt-lab/ground_truth/preflight_$(date +%Y%m%d).json"

    if [[ ! -f "$PREFLIGHT_LOG" ]]; then
        cat <<'EOF'
⚠️ MODEL TRAINING GATE: You are attempting to train or relabel without running preflight today.

REQUIRED before ANY training or batch relabeling:
1. Run preflight on 10 random samples via the Convergence tab (localhost:3003)
2. Verify BOTH PASS recall >= 50% AND FAIL recall >= 50%
3. Get human approval via the batch approval gate modal

The last time you skipped preflight, you burned 2715 API calls with a miscalibrated prompt
that produced 99.9% FAIL labels. The preflight would have caught this in 10 calls.

Run preflight first, or ask Graham to override this gate.
EOF
    fi
fi

# Check if command involves >100 LLM calls without batch-quality preflight
if echo "$TOOL_INPUT" | grep -qiE '(concurrency.*[0-9]|batch.*run|--limit [0-9]{3,})'; then
    cat <<'EOF'
⚠️ BATCH BUDGET GATE: Large batch operation detected.

Before running >100 LLM calls:
1. Use /batch-quality preflight with 10 samples
2. Check the confusion matrix for class balance
3. Verify the prompt version is the latest from /prompt-lab

This gate exists because you repeatedly scale from 1 test to 2715 without checking.
EOF
fi
