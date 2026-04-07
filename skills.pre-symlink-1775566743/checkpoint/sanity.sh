#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== Checkpoint Skill Sanity ==="

echo "Test 1: Help output"
"$SCRIPT_DIR/run.sh" --help > /dev/null
echo "  PASS: help works"

echo "Test 2: Save command help"
"$SCRIPT_DIR/run.sh" save --help > /dev/null
echo "  PASS: save help works"

echo "Test 3: Recall command help"
"$SCRIPT_DIR/run.sh" recall --help > /dev/null
echo "  PASS: recall help works"

echo "Test 4: List command help"
"$SCRIPT_DIR/run.sh" list --help > /dev/null
echo "  PASS: list help works"

echo "All sanity checks passed"
