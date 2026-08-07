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
hash_file="${SURF_CLI_PATH}/dist/.build-source-hash"
lock_wait_seconds="${SURF_CLI_BUILD_LOCK_TIMEOUT_SECONDS:-300}"
build_timeout_seconds="${SURF_CLI_BUILD_TIMEOUT_SECONDS:-600}"

# Content hash of the build inputs whose mtime we compare against dist. Used to
# distinguish a real source change from a spurious mtime bump (git checkout,
# worktree switch, touch) that would otherwise trigger the wedge-prone npm ci.
_source_hash() {
  local files=()
  [[ -f "${src_sw}" ]] && files+=("${src_sw}")
  [[ -f "${native_host}" ]] && files+=("${native_host}")
  if [[ ${#files[@]} -eq 0 ]]; then
    echo "no-source"
    return 0
  fi
  cat "${files[@]}" | sha256sum | cut -d' ' -f1
}

needs_build() {
  # Hard triggers: dist genuinely absent -> must build.
  if [[ ! -f "${dist_manifest}" ]]; then
    return 0
  fi
  if [[ -f "${src_sw}" && ! -f "${dist_sw}" ]]; then
    return 0
  fi
  # Soft triggers: mtime says a source is newer than dist. mtime is fragile —
  # git checkout / worktree switch / touch all bump it without any content
  # change — so confirm the content actually differs before paying for a full
  # npm ci + build (the operation that wedges surf, issue #1306).
  local mtime_stale=0
  if [[ -f "${src_sw}" && -f "${dist_sw}" && "${src_sw}" -nt "${dist_sw}" ]]; then
    mtime_stale=1
  fi
  if [[ -f "${native_host}" && -f "${dist_sw}" && "${native_host}" -nt "${dist_sw}" ]]; then
    mtime_stale=1
  fi
  if [[ ${mtime_stale} -eq 0 ]]; then
    return 1
  fi
  # mtime is stale but does the CONTENT match the last successful build? If so
  # the staleness is spurious: realign dist mtime so the check stops firing and
  # skip the rebuild.
  if [[ -f "${hash_file}" ]] && [[ "$(_source_hash)" == "$(cat "${hash_file}" 2>/dev/null)" ]]; then
    touch "${dist_manifest}" "${dist_sw}" 2>/dev/null || true
    return 1
  fi
  return 0
}

if ! needs_build; then
  # Record/refresh the baseline hash for an already-current dist so the very
  # first spurious mtime bump is covered without needing a prior build.
  [[ -f "${dist_manifest}" && ! -f "${hash_file}" ]] && { _source_hash > "${hash_file}" 2>/dev/null || true; }
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

# ── automatic wedged-lock recovery (#1224) ─────────────────────────────
# A holder stuck in kernel D state (e.g. io_uring-wedged npm, unkillable)
# would otherwise block every surf command until reboot. If every current
# holder is wedged or gone, rotate the lock inode and take a fresh lock —
# the same recovery a human would perform, done automatically with a
# receipt. A holder in any runnable state means a real build is in
# progress: never rotate then.
_lock_holder_pids() {
  fuser "${lock_file}" 2>/dev/null | tr -s ' \t' '\n' | grep -E '^[0-9]+$' || true
}

_holders_all_wedged() {
  # env override for tests: comma-separated states, e.g. "D" or "S,R"
  if [[ -n "${SURF_TEST_LOCK_HOLDER_STATES:-}" ]]; then
    local IFS=','
    for st in ${SURF_TEST_LOCK_HOLDER_STATES}; do
      [[ "${st}" == D* || "${st}" == Z* ]] || return 1
    done
    return 0
  fi
  local pids pid state found=0
  pids="$(_lock_holder_pids)"
  [[ -z "${pids}" ]] && return 0
  for pid in ${pids}; do
    [[ "${pid}" == "$$" ]] && continue
    state="$(awk '{print $3}' "/proc/${pid}/stat" 2>/dev/null || echo GONE)"
    found=1
    [[ "${state}" == D* || "${state}" == Z* || "${state}" == GONE ]] || return 1
  done
  return 0
}

_rotate_wedged_lock() {
  local rotated="${lock_file}.wedged-$(date +%s)"
  mv "${lock_file}" "${rotated}" 2>/dev/null || return 1
  printf '{"schema":"surf.build_lock_incident.v1","code":"wedged_lock_rotated","lock_file":"%s","rotated_to":"%s","holders":"%s","recovered":true}\n' \
    "${lock_file}" "${rotated}" "$(_lock_holder_pids | tr '\n' ',' )" >&2
  return 0
}

exec 9>"${lock_file}"
if ! flock -w "${lock_wait_seconds}" 9; then
  if _holders_all_wedged && _rotate_wedged_lock; then
    exec 9>"${lock_file}"
    if ! flock -w 10 9; then
      echo "Error: fresh lock still contended after wedged-lock rotation" >&2
      exit 75
    fi
  else
    printf '{"schema":"surf.build_lock_incident.v1","code":"build_lock_timeout","lock_file":"%s","waited_seconds":%s,"holders":"%s","hint":"a live build holds the lock; retry later or run surf setup"}\n' \
      "${lock_file}" "${lock_wait_seconds}" "$(_lock_holder_pids | tr '\n' ',')" >&2
    echo "Error: timed out after ${lock_wait_seconds}s waiting for surf-cli build lock at ${lock_file}" >&2
    exit 75
  fi
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

# Record the source hash so a later spurious mtime bump (git/worktree/touch)
# with identical content skips the rebuild instead of wedging on npm ci.
_source_hash > "${hash_file}" 2>/dev/null || true

if needs_build; then
  echo "Error: surf-cli build completed but dist is still stale at ${SURF_CLI_PATH}" >&2
  exit 1
fi
