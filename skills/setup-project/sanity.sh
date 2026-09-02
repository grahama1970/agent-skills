#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -m json.tool "$ROOT/fixtures/agentic_eval.json" >/dev/null
bash "$ROOT/run.sh" plan --config "$ROOT/configs/openai_interview.yaml" >/dev/null
bash "$ROOT/run.sh" audit --config "$ROOT/configs/openai_interview.yaml" >/dev/null
echo 'Result: PASS'
