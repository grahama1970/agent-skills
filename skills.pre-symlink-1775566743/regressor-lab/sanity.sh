#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SKILL_DIR"

echo "=== regressor-lab sanity ==="

# Check dependencies
echo -n "create-regressor: "
if [[ -x "../create-regressor/run.sh" ]]; then echo "OK"; else echo "MISSING"; exit 1; fi

echo -n "run.sh: "
if [[ -x "./run.sh" ]]; then echo "OK"; else echo "MISSING"; exit 1; fi

echo -n "scripts/collect.py: "
if [[ -f "scripts/collect.py" ]]; then echo "OK"; else echo "MISSING"; exit 1; fi

echo -n "scripts/benchmark.py: "
if [[ -f "scripts/benchmark.py" ]]; then echo "OK"; else echo "MISSING"; exit 1; fi

echo -n "scripts/pipeline.py: "
if [[ -f "scripts/pipeline.py" ]]; then echo "OK"; else echo "MISSING"; exit 1; fi

# Check data sources exist
echo -n "profile source 1: "
if [[ -d "/mnt/storage12tb/extractor_corpus/results" ]]; then echo "OK"; else echo "MISSING"; fi

echo -n "profile source 2: "
if [[ -d "/home/graham/workspace/experiments/extractor/.skills/review-pdf/extracted_runs" ]]; then echo "OK"; else echo "MISSING"; fi

echo "=== sanity PASSED ==="
