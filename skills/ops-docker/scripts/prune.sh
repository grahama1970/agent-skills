#!/usr/bin/env bash
# Review Docker disk usage and optionally prune unused resources.
set -euo pipefail

DRY_RUN=1
PRUNE_OPTS=("--all" "--force")
AGE_FILTER="${DOCKER_PRUNE_UNTIL:-}"  # e.g. '24h'
usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Options:
  --until <duration>   Only prune resources unused since duration (e.g. 24h).
  --execute            Prune resources (default is to print plan).
  --help               Show this message.

Environment:
  DOCKER_PRUNE_UNTIL  Default value for --until.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --until)
      AGE_FILTER="$2"; shift 2;;
    --execute)
      DRY_RUN=0; shift;;
    --help|-h)
      usage; exit 0;;
    *)
      echo "Unknown option: $1" >&2
      usage; exit 1;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "docker binary not found in PATH." >&2
  exit 1
fi

echo "Docker disk usage before prune:"
docker system df || true

echo
if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] docker container prune --force"
  echo "[dry-run] docker image prune ${PRUNE_OPTS[*]}"
  echo "[dry-run] docker volume prune --force"
  echo "[dry-run] docker builder prune ${PRUNE_OPTS[*]}"
else
  docker container prune --force
  if [[ -n "$AGE_FILTER" ]]; then
    docker image prune --force --filter "until=$AGE_FILTER"
    docker builder prune --force --filter "until=$AGE_FILTER"
  else
    docker image prune "${PRUNE_OPTS[@]}"
    docker builder prune "${PRUNE_OPTS[@]}"
  fi
  docker volume prune --force
fi

echo
echo "Docker disk usage after prune:"
docker system df || true

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "Dry run complete. Re-run with --execute to prune resources."
fi
