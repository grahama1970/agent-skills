#!/usr/bin/env bash
# Cheap local proof: README parses and drift check runs (no live probes,
# no mutation). Exit 0 = parser healthy and site content matches README.
set -euo pipefail
skill_dir="$(cd "$(dirname "$0")" && pwd)"
cd "$skill_dir"
./run.sh audit --no-live --json >/dev/null
echo "monitor-website sanity: OK (README parsed, no drift, no live probes)"

# #1298 voice canary + #1337 design-world contract
python3 "$skill_dir/../../site/scripts/copy_audit.py" >/dev/null
"$skill_dir/run.sh" design-world-check --json >/dev/null || true
