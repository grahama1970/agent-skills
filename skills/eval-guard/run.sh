#!/usr/bin/env bash
# eval-guard: deterministic completion-claim / triage-classification checker.
set -euo pipefail
cd "$(dirname "$0")"
exec node checker.mjs "$@"
