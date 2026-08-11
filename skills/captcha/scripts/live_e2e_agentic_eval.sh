#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd -- "${SCRIPT_DIR}/.." && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

if [[ "${CAPTCHA_LIVE_E2E:-}" != "1" ]]; then
  printf 'CAPTCHA_LIVE_E2E_NOT_CONFIGURED: set CAPTCHA_LIVE_E2E=1 after starting the authorized loopback ReCAP dynamic target, loopback OpenAI-compatible model endpoint, Surf transport, and pinned ReCAP runtime.\n' >&2
  exit 2
fi

MANIFEST="${TMP_DIR}/captcha-live-authorization.json"
EVALUATE_JSON="${TMP_DIR}/evaluate.json"
VERIFY_JSON="${TMP_DIR}/verify.json"

python - "$MANIFEST" <<'PY'
from __future__ import annotations

import json
import os
import sys

target = sys.argv[1]
payload = {
    "schema_version": "captcha.target_authorization.v1",
    "authorization_id": os.environ.get("CAPTCHA_LIVE_AUTHORIZATION_ID", "recap-live-agentic-eval"),
    "project": os.environ.get("CAPTCHA_LIVE_PROJECT", "captcha-live-agentic-eval"),
    "operator": os.environ.get("CAPTCHA_LIVE_OPERATOR", "agent-skills-maintainer"),
    "purpose": (
        "Run an opt-in live local ReCAP synthetic CAPTCHA benchmark for agentic "
        "evaluation evidence."
    ),
    "target_url": os.environ.get("CAPTCHA_LIVE_TARGET_URL", "http://127.0.0.1:5000"),
    "model_base_url": os.environ.get("CAPTCHA_LIVE_MODEL_BASE_URL", "http://127.0.0.1:8000/v1"),
    "model_id": os.environ.get("CAPTCHA_LIVE_MODEL_ID", "ReCAP-Agent/ReCAP-8B"),
    "model_family": "qwen3",
    "provider": "dynamic",
    "test_mode": os.environ.get("CAPTCHA_LIVE_TEST_MODE", "custom"),
    "captcha_name": os.environ.get("CAPTCHA_LIVE_CAPTCHA_NAME", "text"),
    "test_size": int(os.environ.get("CAPTCHA_LIVE_TEST_SIZE", "2")),
    "seed": int(os.environ.get("CAPTCHA_LIVE_SEED", "42")),
    "workers": int(os.environ.get("CAPTCHA_LIVE_WORKERS", "1")),
    "max_calls": int(os.environ.get("CAPTCHA_LIVE_MAX_CALLS", "4")),
    "max_tasks": int(os.environ.get("CAPTCHA_LIVE_MAX_TASKS", "2")),
    "timeout_seconds": int(os.environ.get("CAPTCHA_LIVE_TIMEOUT_SECONDS", "900")),
    "allowed_actions": ["evaluate", "verify"],
    "allowed_captcha_types": [os.environ.get("CAPTCHA_LIVE_CAPTCHA_NAME", "text")],
    "recap_commit": "577c7728ed159756a6cb6cbd1a58897fe288f73e",
    "expires_at": os.environ.get("CAPTCHA_LIVE_EXPIRES_AT", "2030-01-01T00:00:00Z"),
    "acknowledgements": {
        "owns_or_controls_target": True,
        "local_synthetic_only": True,
        "no_third_party_bypass": True,
        "defensive_or_research_use": True,
    },
}
with open(target, "w", encoding="utf-8") as handle:
    json.dump(payload, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY

"${SKILL_DIR}/run.sh" authorization-preflight \
  --manifest "$MANIFEST" \
  --action evaluate \
  --json >"${TMP_DIR}/authorization.json"

"${SKILL_DIR}/run.sh" evaluate \
  --manifest "$MANIFEST" \
  --recap-root "${CAPTCHA_LIVE_RECAP_ROOT:-/mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent}" \
  --recap-python "${CAPTCHA_LIVE_RECAP_PYTHON:-/mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent/.venv/bin/python}" \
  --output-root "${CAPTCHA_LIVE_OUTPUT_ROOT:-/mnt/storage12tb/skills/captcha/outputs}" \
  --execute \
  --json >"$EVALUATE_JSON"

RUN_DIR="$(python - "$EVALUATE_JSON" <<'PY'
from __future__ import annotations

import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    payload = json.load(handle)
run_dir = payload.get("run_dir")
if not run_dir:
    raise SystemExit("evaluate output did not include run_dir")
print(run_dir)
PY
)"

"${SKILL_DIR}/run.sh" verify --run-dir "$RUN_DIR" --json >"$VERIFY_JSON"

python - "$EVALUATE_JSON" "$VERIFY_JSON" <<'PY'
from __future__ import annotations

import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    evaluate = json.load(handle)
with open(sys.argv[2], encoding="utf-8") as handle:
    verify = json.load(handle)
if evaluate.get("schema_version") != "captcha.run_receipt.v1":
    raise SystemExit("evaluate receipt schema mismatch")
if evaluate.get("status") != "PASS":
    raise SystemExit("evaluate did not PASS")
if evaluate.get("bounded_judgment") != "CAPABILITY_MEASURED":
    raise SystemExit("live capability was not measured")
if verify.get("status") != "PASS":
    raise SystemExit("verify did not PASS")
print(json.dumps(evaluate, indent=2, sort_keys=True))
print("live_e2e_verified")
PY
