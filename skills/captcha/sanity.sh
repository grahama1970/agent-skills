#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

cd "$SCRIPT_DIR"
export PYTHONPATH="${SCRIPT_DIR}/src${PYTHONPATH:+:${PYTHONPATH}}"
export UV_PROJECT_ENVIRONMENT="${UV_PROJECT_ENVIRONMENT:-/tmp/captcha-skill-venv}"
export PYTHONPYCACHEPREFIX="${PYTHONPYCACHEPREFIX:-/tmp/captcha-skill-pycache}"

if ! command -v uv >/dev/null 2>&1; then
  printf 'captcha sanity: uv is required for isolated skill execution\n' >&2
  exit 2
fi

uv sync --project "$SCRIPT_DIR" --extra test
PYTHON=(uv run --project "$SCRIPT_DIR" --extra test python)

"${PYTHON[@]}" -m compileall -q src tests
"${PYTHON[@]}" -m pytest -q

while IFS= read -r source_file; do
  lines="$(wc -l < "$source_file")"
  if (( lines > 800 )); then
    printf 'captcha sanity: Python module exceeds 800 lines: %s (%s)\n' "$source_file" "$lines" >&2
    exit 1
  fi
done < <(find src/captcha_skill -maxdepth 1 -name '*.py' -type f | sort)

./run.sh schemas --check --json >"$TMP_DIR/schemas.json"
./run.sh status --json >"$TMP_DIR/status.json"
./run.sh authorization-preflight \
  --manifest fixtures/authorization-valid-local.json \
  --action plan \
  --receipt-out "$TMP_DIR/authorization.json" \
  --json >"$TMP_DIR/authorization.stdout.json"

./run.sh ask-dag \
  --manifest fixtures/authorization-valid-local.json \
  --recap-root /mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent \
  --recap-python /mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent/.venv/bin/python \
  --output-root /mnt/storage12tb/skills/captcha/outputs \
  --out "$TMP_DIR/ask-dag.json" \
  --json >"$TMP_DIR/ask-dag.stdout.json"

if ./run.sh authorization-preflight \
  --manifest fixtures/authorization-invalid-public.json \
  --action evaluate \
  --json >"$TMP_DIR/invalid.stdout" 2>"$TMP_DIR/invalid.stderr"; then
  echo "captcha sanity: public target authorization unexpectedly passed" >&2
  exit 1
fi

"${PYTHON[@]}" - "$TMP_DIR" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
status = json.loads((root / "status.json").read_text())
authorization = json.loads((root / "authorization.json").read_text())
dag = json.loads((root / "ask-dag.json").read_text())
invalid = json.loads((root / "invalid.stdout").read_text())

if status["schema_version"] != "captcha.status.v1":
    raise SystemExit("status schema mismatch")
if authorization["status"] != "PASS":
    raise SystemExit("authorization receipt did not pass")
if dag["schema_version"] != "ask.dag.v1":
    raise SystemExit("Ask DAG schema mismatch")
node = dag["nodes"][0]
if node["type"] != "skill.run" or node["input"]["skill"] != "captcha":
    raise SystemExit("Ask DAG does not compose captcha through skill.run")
if invalid.get("failure_code") != "target_not_loopback":
    raise SystemExit("public-target failure code mismatch")
PY

echo "captcha sanity: PASS"
