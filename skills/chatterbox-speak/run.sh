#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
cmd="${1:-}"
if [ "$cmd" = "probe" ]; then shift; exec uv run --script scripts/scenario_probe.py "$@"; fi
if [ "$cmd" = "eval-context" ]; then shift; exec uv run --script scripts/eval_webgpt_audio.py "$@"; fi
if [ "$cmd" = "compare" ]; then shift; exec uv run --script scripts/compare_variants.py "$@"; fi
if [ "$cmd" = "compare-memory" ]; then shift; exec uv run --script scripts/comparison_memory.py "$@"; fi
if [ "$cmd" = "review" ]; then shift; exec uv run --script scripts/review_terminal.py "$@"; fi
if [ "$cmd" = "review-eval" ]; then shift; exec uv run --script scripts/eval_review.py "$@"; fi
exec uv run --script scripts/speak.py "$@"
