#!/usr/bin/env bash
# Cheap local proof: README parses and drift check runs (no live probes,
# no mutation). Exit 0 = parser healthy and site content matches README.
set -euo pipefail
cd "$(dirname "$0")"
./run.sh audit --no-live --json >/dev/null
echo "monitor-website sanity: OK (README parsed, no drift, no live probes)"
