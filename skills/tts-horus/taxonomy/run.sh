#!/usr/bin/env bash
# Taxonomy - Extract Federated Taxonomy tags
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/taxonomy.py" "$@"
