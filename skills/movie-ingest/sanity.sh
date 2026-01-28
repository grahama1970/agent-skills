#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Basic sanity: ensure scenes helper and CLI respond
"$SCRIPT_DIR"/run.sh --help >/dev/null
"$SCRIPT_DIR"/run.sh scenes find --help >/dev/null
