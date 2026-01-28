#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# system-headroom skill dispatcher
# Usage: run.sh [args...]
# Runs the check.sh script to check system resources

exec bash scripts/check.sh "$@"
