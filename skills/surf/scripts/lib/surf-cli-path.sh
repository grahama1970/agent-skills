# Resolve vendored surf-cli location for the surf skill.
# Override with SURF_CLI_PATH when testing an external checkout.

if [[ -z "${SKILL_DIR:-}" ]]; then
  echo "surf-cli-path: SKILL_DIR must be set before sourcing" >&2
  return 1 2>/dev/null || exit 1
fi

if [[ -z "${SURF_CLI_PATH:-}" ]]; then
  SURF_CLI_PATH="${SKILL_DIR}/vendor/surf-cli"
fi

export SURF_CLI_PATH
export SURF_CLI="${SURF_CLI_PATH}"
export SURF_CLI_CLI="${SURF_CLI_PATH}/native/cli.cjs"
