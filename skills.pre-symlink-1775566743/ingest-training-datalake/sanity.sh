#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== ingest-training-datalake sanity ==="

if ! command -v uv >/dev/null 2>&1; then
  echo "FAIL: uv not found"
  exit 1
fi
echo "PASS: uv found"

./run.sh --help >/dev/null
echo "PASS: CLI help"

TMP_ROOT="/tmp/ingest_training_datalake_sanity"
rm -rf "$TMP_ROOT"
mkdir -p "$TMP_ROOT/arxiv" "$TMP_ROOT/nasa"
touch "$TMP_ROOT/arxiv/a.pdf" "$TMP_ROOT/nasa/b.pdf" "$TMP_ROOT/nasa/c.html"

./run.sh assess "$TMP_ROOT" \
  --allowed-root /tmp \
  --output-json /tmp/ingest_training_assess.json >/dev/null
echo "PASS: assess command"

./run.sh plan "$TMP_ROOT" \
  --allowed-root /tmp \
  --no-store-memory \
  --output-manifest /tmp/ingest_training_manifest.txt \
  --output-plan-json /tmp/ingest_training_plan.json >/dev/null
echo "PASS: plan command"

./run.sh cycle "$TMP_ROOT" \
  --allowed-root /tmp \
  --no-store-memory \
  --output-dir /tmp/ingest_training_cycles >/dev/null
echo "PASS: cycle command"

echo "=== sanity passed ==="
