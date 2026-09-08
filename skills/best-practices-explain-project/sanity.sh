#!/usr/bin/env bash
set -euo pipefail
"$(dirname "$0")/run.sh" validate
echo "SANITY PASS"
