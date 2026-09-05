#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$ROOT/../agentic-evals/run.sh" run "$ROOT/fixtures/agentic_eval.json" --output /mnt/storage12tb/skills/ops-google-meet/outputs/sanity-report.json
