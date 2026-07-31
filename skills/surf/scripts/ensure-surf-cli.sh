#!/usr/bin/env bash
# Build vendored surf-cli when dist/ is missing or older than source.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=scripts/lib/surf-cli-path.sh
source "${SKILL_DIR}/scripts/lib/surf-cli-path.sh"

if [[ ! -f "${SURF_CLI_PATH}/package.json" ]]; then
  echo "Error: vendored surf-cli missing at ${SURF_CLI_PATH}" >&2
  exit 1
fi

need_build=false
dist_manifest="${SURF_CLI_PATH}/dist/manifest.json"
src_sw="${SURF_CLI_PATH}/src/service-worker/index.ts"
dist_sw="${SURF_CLI_PATH}/dist/service-worker/index.js"
native_host="${SURF_CLI_PATH}/native/host.cjs"

if [[ ! -f "${dist_manifest}" ]]; then
  need_build=true
elif [[ -f "${src_sw}" && -f "${dist_sw}" ]]; then
  if [[ "${src_sw}" -nt "${dist_sw}" ]]; then
    need_build=true
  fi
  if [[ -f "${native_host}" && "${native_host}" -nt "${dist_sw}" ]]; then
    need_build=true
  fi
fi

if ! ${need_build}; then
  exit 0
fi

echo "Building vendored surf-cli at ${SURF_CLI_PATH}..." >&2
(
  cd "${SURF_CLI_PATH}"
  if [[ -f package-lock.json ]]; then
    npm ci
  else
    npm install
  fi
  npm run build
)
