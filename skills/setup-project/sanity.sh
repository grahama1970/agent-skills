#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -m json.tool "$ROOT/fixtures/agentic_eval.json" >/dev/null
bash "$ROOT/run.sh" plan --config "$ROOT/configs/openai_interview.yaml" >/dev/null
bash "$ROOT/run.sh" audit --config "$ROOT/configs/openai_interview.yaml" >/dev/null
grep -Fq 'client_contract_gate: auto' "$ROOT/SKILL.md"
grep -Fq 'battle_receipts' "$ROOT/SKILL.md"
grep -Fq 'release_report' "$ROOT/SKILL.md"
echo 'Result: PASS'
