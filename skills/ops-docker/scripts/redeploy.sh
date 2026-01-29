#!/usr/bin/env bash
# Redeploy a Docker Compose stack with optional dry-run and service selection.
set -euo pipefail

STACK_FILE="${STACK_FILE:-docker-compose.yml}"
DRY_RUN=1
HEALTH_CMD="${HEALTH_CMD:-}" # optional command to run after restart
SERVICES=()

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --stack <file>      Compose file to use (default: docker-compose.yml or STACK_FILE env).
  --service <name>    Limit operations to the given service (repeatable).
  --health-cmd <cmd>  Command to run after restart to verify health.
  --execute           Run commands instead of printing them.
  --help              Show this help message.

This script prints the plan by default. Pass --execute to actually pull/build/restart.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stack)
      STACK_FILE="$2"; shift 2;;
    --service)
      SERVICES+=("$2"); shift 2;;
    --health-cmd)
      HEALTH_CMD="$2"; shift 2;;
    --execute)
      DRY_RUN=0; shift;;
    --help|-h)
      usage; exit 0;;
    *)
      echo "Unknown option: $1" >&2
      usage; exit 1;;
  esac
done

if [[ ! -f "$STACK_FILE" ]]; then
  echo "Compose file '$STACK_FILE' not found." >&2
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "(dry-run) Nothing to do." >&2
    exit 0
  else
    exit 1
  fi
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker binary not found in PATH." >&2
  exit 1
fi

compose_cmd=(docker compose -f "$STACK_FILE")
if ! docker compose version >/dev/null 2>&1; then
  if command -v docker-compose >/dev/null 2>&1; then
    compose_cmd=(docker-compose -f "$STACK_FILE")
  else
    echo "Neither 'docker compose' nor 'docker-compose' is available." >&2
    exit 1
  fi
fi

svc_args=()
if [[ ${#SERVICES[@]} -gt 0 ]]; then
  svc_args=("${SERVICES[@]}")
fi

run_compose() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] ${compose_cmd[*]} $*"
  else
    "${compose_cmd[@]}" "$@"
  fi
}

run_compose pull "${svc_args[@]}"
run_compose build "${svc_args[@]}"
run_compose up -d "${svc_args[@]}"
run_compose ps

if [[ -n "$HEALTH_CMD" ]]; then
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] $HEALTH_CMD"
  else
    eval "$HEALTH_CMD"
  fi
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run complete. Re-run with --execute to apply changes."
else
  echo "Redeploy complete."
fi
