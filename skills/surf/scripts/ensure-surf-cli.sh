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

dist_manifest="${SURF_CLI_PATH}/dist/manifest.json"
src_sw="${SURF_CLI_PATH}/src/service-worker/index.ts"
dist_sw="${SURF_CLI_PATH}/dist/service-worker/index.js"
native_host="${SURF_CLI_PATH}/native/host.cjs"
lock_file="${SURF_CLI_PATH}/.ensure-surf-cli-build.lock"
lock_wait_seconds="${SURF_CLI_BUILD_LOCK_TIMEOUT_SECONDS:-300}"
build_timeout_seconds="${SURF_CLI_BUILD_TIMEOUT_SECONDS:-600}"

needs_build() {
  if [[ ! -f "${dist_manifest}" ]]; then
    return 0
  fi
  if [[ -f "${src_sw}" && ! -f "${dist_sw}" ]]; then
    return 0
  fi
  if [[ -f "${src_sw}" && -f "${dist_sw}" && "${src_sw}" -nt "${dist_sw}" ]]; then
    return 0
  fi
  if [[ -f "${native_host}" && -f "${dist_sw}" && "${native_host}" -nt "${dist_sw}" ]]; then
    return 0
  fi
  return 1
}

if ! needs_build; then
  exit 0
fi

command -v flock >/dev/null 2>&1 || {
  echo "Error: flock is required to serialize surf-cli builds" >&2
  exit 1
}

command -v timeout >/dev/null 2>&1 || {
  echo "Error: timeout is required to bound surf-cli builds" >&2
  exit 1
}

exec 9>"${lock_file}"
if ! flock -w "${lock_wait_seconds}" 9; then
  echo "Error: timed out after ${lock_wait_seconds}s waiting for surf-cli build lock at ${lock_file}" >&2
  exit 75
fi

if ! needs_build; then
  exit 0
fi

echo "Building vendored surf-cli at ${SURF_CLI_PATH} with timeout ${build_timeout_seconds}s..." >&2
build_script='
set -euo pipefail
cd "$1"
if [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi
npm run build
'

build_rc=0
timeout --kill-after=5 "${build_timeout_seconds}" bash -c "${build_script}" bash "${SURF_CLI_PATH}" || build_rc=$?
if [[ ${build_rc} -ne 0 ]]; then
  if [[ ${build_rc} -eq 124 || ${build_rc} -eq 137 ]]; then
    echo "Error: surf-cli build timed out after ${build_timeout_seconds}s at ${SURF_CLI_PATH}" >&2
  else
    echo "Error: surf-cli build failed with exit ${build_rc} at ${SURF_CLI_PATH}" >&2
  fi
  exit "${build_rc}"
fi

if needs_build; then
  echo "Error: surf-cli build completed but dist is still stale at ${SURF_CLI_PATH}" >&2
  exit 1
fi
