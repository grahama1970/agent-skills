#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(cd "${SKILL_DIR}/../../.." && pwd)}"
export WORKSPACE_ROOT
[[ -f "${SKILL_DIR}/ui/package.json" ]] || {
  echo "UX Lab shared UI package missing at ${SKILL_DIR}/ui." >&2
  exit 1
}
bash -n "${SKILL_DIR}/run.sh"
python3 -m py_compile "${SKILL_DIR}/scripts/project_registry.py" "${SKILL_DIR}/scripts/serve_project_hub.py"
"${SKILL_DIR}/run.sh" validate
"${SKILL_DIR}/run.sh" list --json | jq -e '.schema == "ux_lab.project_list.v1" and (.projects | length >= 5)' >/dev/null
"${SKILL_DIR}/run.sh" url persona-dream hub | grep -q 'project=persona-dream'
"${SKILL_DIR}/run.sh" status persona-dream | jq -e '.projects[0].workspace_exists == true and .projects[0].mounted_surface_count >= 1' >/dev/null
bash "${SKILL_DIR}/tests/test_tau_dag_wrapper.sh"
forbidden_pattern="$(printf 'pi%smono' '-')"
runtime_files=(
  "${SKILL_DIR}/run.sh"
  "${SKILL_DIR}/sanity.sh"
  "${SKILL_DIR}/projects.v1.json"
  "${SKILL_DIR}/scripts"
)
if grep -R --line-number --fixed-strings "${forbidden_pattern}" "${runtime_files[@]}" --exclude-dir=__pycache__; then
  echo "Forbidden legacy runtime reference found." >&2
  exit 1
fi
echo "UX Lab wrapper sanity: PASS"
