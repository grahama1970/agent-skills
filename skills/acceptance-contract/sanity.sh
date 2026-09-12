#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
if [[ -z "${UV_PROJECT_ENVIRONMENT:-}" || "${UV_PROJECT_ENVIRONMENT:-}" == "$SCRIPT_DIR/.venv" || "${UV_PROJECT_ENVIRONMENT:-}" == "skills/acceptance-contract/.venv" ]]; then
  export UV_PROJECT_ENVIRONMENT="/mnt/storage12tb/skills/acceptance-contract/.venv"
fi
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

(cd "$SCRIPT_DIR" && uv run --project "$SCRIPT_DIR" pytest -q tests)
uv run --project "$SCRIPT_DIR" python "$ROOT/skills/best-practices-skills/scripts/validate_skill.py" "$SCRIPT_DIR" --json >/tmp/acceptance-contract-skill-validate.json

cat >"$TMP/brief.md" <<'BRIEF'
# Client brief
The system must remove customer phone numbers in every representation.
Valid CSV rows must accept non-sensitive literals unchanged.
Outputs must not leak policy values.
Should images be in scope?
BRIEF

"$SCRIPT_DIR/run.sh" extract "$TMP/brief.md" --out "$TMP/out-file" --project-name demo --goal-mode create >/tmp/acceptance-contract-file-receipt.json
uv run --project "$SCRIPT_DIR" python - "$TMP/out-file/acceptance_bundle.json" <<'PY'
import json, sys
p = sys.argv[1]
data = json.load(open(p, encoding="utf-8"))
if data["schema"] != "acceptance_contract.bundle.v1":
    raise SystemExit("wrong bundle schema")
if len(data["requirements"]) != 3 or len(data["acceptance_cases"]) != 3:
    raise SystemExit("wrong extracted requirement count")
if not data["open_questions"]:
    raise SystemExit("expected open question")
PY

mkdir -p "$TMP/dir"
cp "$TMP/brief.md" "$TMP/dir/brief.md"
"$SCRIPT_DIR/run.sh" extract "$TMP/dir" --out "$TMP/out-dir" --project-name demo --goal-mode amend >/tmp/acceptance-contract-dir-receipt.json

(cd "$TMP" && zip -q brief.zip brief.md)
"$SCRIPT_DIR/run.sh" extract "$TMP/brief.zip" --out "$TMP/out-zip" --project-name demo --goal-mode none >/tmp/acceptance-contract-zip-receipt.json

echo '{"schema":"acceptance_contract.sanity.v1","status":"PASS","proofs":["/tmp/acceptance-contract-skill-validate.json","/tmp/acceptance-contract-file-receipt.json","/tmp/acceptance-contract-dir-receipt.json","/tmp/acceptance-contract-zip-receipt.json"]}'
