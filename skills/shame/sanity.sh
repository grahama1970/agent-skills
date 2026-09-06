#!/usr/bin/env bash
# Canonical agentic workflow suite. Requires the normal live Pi/Memory setup.
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SKILL_DIR/../agentic-evals/run.sh" run "$SKILL_DIR/fixtures/agentic_eval.json" "$@"
