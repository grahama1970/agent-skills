#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEMORY_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# graph_memory lives in the memory repo, not pi-mono
MEMORY_SRC="$(cd "$SCRIPT_DIR/../../../.." && pwd)/memory/src"
export PYTHONPATH="${MEMORY_ROOT}/src:${MEMORY_SRC}:${SCRIPT_DIR}:${PYTHONPATH:-}"

# Fix 8: Default to Chutes direct so stress tests don't route through
# scillm proxy (which may redirect to Gemini Flash when DeepSeek is UNHEALTHY).
export SCILLM_API_BASE="${SCILLM_API_BASE:-https://llm.chutes.ai/v1}"
export SCILLM_PROXY_KEY="${SCILLM_PROXY_KEY:-${CHUTES_API_KEY:-}}"
export CHUTES_TEXT_MODEL="${CHUTES_TEXT_MODEL:-deepseek-ai/DeepSeek-V3}"

# Bypass the assistant gateway cascade for question mining — it tries local GPT
# (no llama_cpp) then scillm escalation (SCILLM_PROXY_KEY not propagated to
# subprocess), resulting in 0 questions from all sources.
export STRESS_TEST_USE_GATEWAY="${STRESS_TEST_USE_GATEWAY:-0}"

exec python -m sparta_stress_test.cli "$@"
