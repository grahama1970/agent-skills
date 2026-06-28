#!/usr/bin/env bash
set -euo pipefail
unset VIRTUAL_ENV

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export UV_PROJECT_ENVIRONMENT="${PDF_LAB_UV_ENV:-/mnt/storage12tb/skills/pdf-lab/.venv}"

echo "pdf-lab sanity check..."

# Check pyproject.toml exists
if [ ! -f "$SCRIPT_DIR/pyproject.toml" ]; then
  echo "FAIL: pyproject.toml not found"
  exit 1
fi

# Check pdf_lab.py exists
if [ ! -f "$SCRIPT_DIR/pdf_lab.py" ]; then
  echo "FAIL: pdf_lab.py not found"
  exit 1
fi

# Test that python can import without errors
if ! uv run --project "$SCRIPT_DIR" python -c "import sys; sys.path.insert(0, '$SCRIPT_DIR'); import pdf_lab" 2>/dev/null; then
  echo "FAIL: cannot import pdf_lab module"
  exit 1
fi

# Test help command via run.sh
if ! "$SCRIPT_DIR/run.sh" --help 2>&1 | grep -q "pdf-lab"; then
  echo "FAIL: run.sh --help did not show expected output"
  exit 1
fi

# Positive-control runtime verification fixture.
POSITIVE_JOB="$(mktemp -d)"
NEGATIVE_JOB=""
trap 'rm -rf "$POSITIVE_JOB" "${NEGATIVE_JOB:-}"' EXIT
printf '{"accuracy": 1.0, "passed": true}\n' > "$POSITIVE_JOB/comparison.json"
if ! "$SCRIPT_DIR/run.sh" verify --job-dir "$POSITIVE_JOB" >/tmp/pdf-lab-positive-verify.json; then
  echo "FAIL: verify rejected positive-control comparison artifact"
  exit 1
fi
if [ ! -f "$POSITIVE_JOB/verify-receipt.json" ]; then
  echo "FAIL: verify did not write verify-receipt.json"
  exit 1
fi
if ! uv run --project "$SCRIPT_DIR" python - "$POSITIVE_JOB/verify-receipt.json" <<'PY'
import json
import sys

receipt = json.load(open(sys.argv[1], encoding="utf-8"))
assert receipt["schema_version"] == "skill.runtime_verify.v1"
assert receipt["status"] == "PASS"
assert receipt["stable"] is True
PY
then
  echo "FAIL: positive verify receipt schema/status invalid"
  exit 1
fi

# Negative-control fixture: an empty job must fail closed.
NEGATIVE_JOB="$(mktemp -d)"
if "$SCRIPT_DIR/run.sh" verify --job-dir "$NEGATIVE_JOB" >/tmp/pdf-lab-negative-verify.json 2>&1; then
  echo "FAIL: verify accepted empty job directory"
  exit 1
fi
if ! uv run --project "$SCRIPT_DIR" python - "$NEGATIVE_JOB/verify-receipt.json" <<'PY'
import json
import sys

receipt = json.load(open(sys.argv[1], encoding="utf-8"))
assert receipt["status"] == "FAIL"
assert any(not check["passed"] for check in receipt["checks"])
PY
then
  echo "FAIL: negative verify receipt schema/status invalid"
  exit 1
fi

# Maintainer ticket packet must be generated for a failing job.
if ! "$SCRIPT_DIR/run.sh" file-maintainer-ticket --job-dir "$NEGATIVE_JOB" >/tmp/pdf-lab-ticket.json; then
  echo "FAIL: maintainer ticket command failed for negative job"
  exit 1
fi
if ! uv run --project "$SCRIPT_DIR" python - "$NEGATIVE_JOB/maintainer-ticket.json" <<'PY'
import json
import sys

ticket = json.load(open(sys.argv[1], encoding="utf-8"))
assert ticket["schema_version"] == "skill.maintainer_ticket.v1"
assert ticket["skill_id"] == "pdf-lab"
assert ticket["verify_status"] == "FAIL"
PY
then
  echo "FAIL: maintainer ticket schema/status invalid"
  exit 1
fi

echo "PASS: pdf-lab sanity check"
exit 0
