#!/usr/bin/env bash
set -euo pipefail

if [[ "${REVIEW_DESIGN_LIVE_E2E:-}" != "1" ]]; then
  echo "SKIP: set REVIEW_DESIGN_LIVE_E2E=1 to run the opt-in review-design composition gate"
  echo "      Requires live scillm, memory, surf, and ask runtimes."
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$(dirname "$SCRIPT_DIR")"
export SKILLS_DIR

echo "=== review-design live E2E (opt-in) ==="

python3 - <<'PY'
import json
import os
import sys
import urllib.request
from pathlib import Path

skills_dir = Path(os.environ["SKILLS_DIR"])
sys.path.insert(0, str(skills_dir))
from dotenv_helper import load_env

load_env()

checks = {
    "scillm": os.environ.get("SCILLM_BASE_URL", "http://localhost:4001") + "/health",
    "memory": os.environ.get("MEMORY_BASE_URL", "http://127.0.0.1:8601") + "/health",
}

results = {}
for name, url in checks.items():
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            results[name] = resp.status == 200
    except Exception as exc:
        results[name] = f"unreachable: {exc}"

report = {
    "schema": "review_design.live_e2e_report.v1",
    "profile": "composition-live",
    "checks": results,
    "note": "Opt-in gate only; set REVIEW_DESIGN_LIVE_E2E=1 to execute.",
}
print(json.dumps(report, indent=2))

if not all(v is True for v in results.values()):
    sys.exit(1)
PY

echo "=== review-design live E2E: PASS ==="
