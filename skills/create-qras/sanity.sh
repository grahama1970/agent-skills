#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$REPO_ROOT"
python3 -m py_compile skills/create-qras/f36_requirement_qra.py
python3 -m pytest skills/create-qras/test_f36_requirement_qra.py -q
./skills/create-qras/run.sh f36-webgpt-export --help >/dev/null
./skills/create-qras/run.sh f36-webgpt-import --help >/dev/null

printf '%s\n' \
  'mocked: no' \
  'live: no' \
  'exercised: deterministic F36 WebGPT export/import, stable batch cardinality and IDs, closed complete-family schema, byte-identical answers, fail-closed authority/SPARTA checks, atomic quarantine, transport-proof truthfulness, and CLI dispatch' \
  'unverified: WebGPT browser transport, engineering semantic correctness, full 3680-family generation, SPARTA applicability/crosswalk evidence, certification, and operational correctness'
