#!/usr/bin/env bash
set -euo pipefail

DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$DIR"

./run.sh validate \
  fixtures/sample.explainers.jsonl \
  >/tmp/explain-project-sanity-validate.json

./run.sh ask \
  fixtures/sample.explainers.jsonl \
  --question 'What happens if a worker crashes before success?' \
  >/tmp/explain-project-sanity-route.json

./run.sh cockpit \
  --repo fixtures/cockpit/project \
  --explainers fixtures/cockpit/project/docs/explain/explainers.jsonl \
  --headless \
  --script fixtures/cockpit/scripts/worker-crash-walkthrough.json \
  --out /tmp/explain-project-sanity-proof.json \
  >/tmp/explain-project-sanity-cockpit.json

PYTHONPATH="$DIR/scripts" \
  uv run \
  --with pydantic \
  --with typer \
  --with httpx \
  --with loguru \
  python3 scripts/validate_cockpit_proof.py \
  /tmp/explain-project-sanity-proof.json \
  --expect-valid \
  >/tmp/explain-project-sanity-proof-validation.json

PYTHONPATH="$DIR/scripts" \
  uv run \
  --with pydantic \
  --with httpx \
  --with loguru \
  python3 fixtures/cockpit_contract_eval.py

python3 fixtures/ui_contract_eval.py

python3 \
  ../best-practices-react/scripts/verify-file-size.py \
  ui/src

echo "SANITY PASS"
