#!/usr/bin/env bash
# Thin project wrapper: no data transformation or matching logic lives here.
set -euo pipefail
unset VIRTUAL_ENV PYTHONPATH
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
ROOT="${ANONYMIZE_DATA_ROOT:-${HOME}/workspace/experiments/oai-trial}"
if [[ ! -f "$ROOT/src/anonymization_trial/__main__.py" ]]; then
  printf '%s\n' 'anonymize_data_project_missing: set ANONYMIZE_DATA_ROOT to the oai-trial checkout' >&2
  exit 2
fi
ROOT="$(cd "$ROOT" && pwd -P)"
if [[ "${1:-}" == setup ]]; then
  command -v uv >/dev/null || { echo 'anonymize_data_uv_missing: install uv before setup' >&2; exit 2; }
  uv sync --project "$ROOT" --extra dev --extra discovery
  "$ROOT/.venv/bin/python" -c 'import rapidfuzz; print("RapidFuzz", rapidfuzz.__version__)'
  exit 0
fi
if [[ "${1:-}" == sanity ]]; then
  shift
  exec "$HERE/sanity.sh" "$@"
fi
ENTRY="$ROOT/.venv/bin/anonymization-trial"
if [[ ! -x "$ENTRY" ]]; then
  echo 'anonymize_data_setup_required: run this skill with the setup subcommand' >&2
  exit 2
fi
ACTUAL="$(cd / && "$ROOT/.venv/bin/python" -c 'import anonymization_trial,pathlib; print(pathlib.Path(anonymization_trial.__file__).resolve().parent)')"
if [[ "$ACTUAL" != "$ROOT/src/anonymization_trial" ]]; then
  echo 'anonymize_data_wrong_install: rerun setup for the configured project checkout' >&2
  exit 2
fi
export TMPDIR="${ANONYMIZE_DATA_WORK_DIR:-/mnt/storage12tb/skills/anonymize-data/work}"
mkdir -p "$TMPDIR"
if [[ $# -eq 0 ]]; then set -- --help; fi
case "$1" in
  --help|-h) ;;
  --*) set -- anonymize "$@" ;;
esac
# The installed entrypoint preserves the caller's cwd for relative data paths.
exec "$ENTRY" "$@"
