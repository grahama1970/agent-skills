#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
./run.sh validate fixtures/sample.explainers.jsonl >/tmp/explain-project-sanity.json
./run.sh ask fixtures/sample.explainers.jsonl --question 'What happens if a worker crashes before success?' | grep -q publish.report_last
echo "SANITY PASS"
