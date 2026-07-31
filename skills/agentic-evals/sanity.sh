#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/mnt/storage12tb/skills/agentic-evals/.venv}"
export UV_LINK_MODE="${UV_LINK_MODE:-copy}"
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
OUT="$(mktemp)"

"$SCRIPT_DIR/run.sh" run "$SCRIPT_DIR/fixtures/agentic_eval.json" --output "$OUT" >/dev/null

uv run --project "$SCRIPT_DIR" python - "$OUT" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
assert report["schema"] == "agentic_evals.report.v1"
assert report["readiness"] == "READY"
assert report["mocked"] is False
assert report["fixture_backed"] is True
assert report["live"] is False
assert report["proof_scope"] == "fixture wiring smoke"
assert report["case_count"] == 2
assert report["trial_count"] == 6
assert all(case["pass_rate"] == 1.0 for case in report["cases"])
PY

rm -f "$OUT"
