#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(cd "${SKILL_DIR}/../../.." && pwd)}"
APP_DIR="${SPARTA_EXPLORER_ROOT:-${WORKSPACE_ROOT}/sparta/explorer}"
[[ -f "${APP_DIR}/package.json" ]]
[[ -f "${SKILL_DIR}/ui/package.json" ]] || {
  echo "UX Lab shared UI package missing at ${SKILL_DIR}/ui." >&2
  exit 1
}
(
  cd "${SKILL_DIR}/ui"
  npm ci
  npm run typecheck
)
bash "${SKILL_DIR}/tests/test_tau_dag_wrapper.sh"
forbidden_pattern="$(printf 'pi%smono' '-')"
if grep -R --line-number --fixed-strings "${forbidden_pattern}" "${APP_DIR}" "${SKILL_DIR}" --exclude-dir=node_modules --exclude-dir=tests --exclude='*.json.bak'; then
  echo "Forbidden legacy runtime reference found." >&2
  exit 1
fi
curl -fsS "${SPARTA_EXPLORER_API_URL:-http://127.0.0.1:3001}/api/f36/explorer-projection" \
  | jq -e '.requirement.requirement_revision_id == "F36B-M00-S01-C01-CYB-004@R2" and .posture.compliance_credit == 0 and (.projection_fingerprint | length > 0)' >/dev/null
echo "Sparta Explorer wrapper sanity: PASS"
