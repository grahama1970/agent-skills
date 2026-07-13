#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"
python3 -m py_compile skills/create-qras/f36_requirement_qra.py
PYTHONPATH=skills/create-qras python3 -m pytest \
  skills/create-qras/test_f36_requirement_qra.py \
  skills/create-qras/test_generator_auth.py \
  skills/create-qras/test_grounding_checker.py \
  skills/create-qras/test_qra_schema.py -q
./skills/create-qras/run.sh f36-manifest --help >/dev/null
./skills/create-qras/run.sh f36-validate --help >/dev/null
./skills/create-qras/run.sh f36-phase-gate --help >/dev/null

printf '%s\n' \
  'mocked: no' \
  'live: no' \
  'exercised: F36 QRA schema, deterministic assembly, validators, authentication resolution, and CLI dispatch' \
  'unverified: live SciLLM generation, provider receipts, and corpus generation'
