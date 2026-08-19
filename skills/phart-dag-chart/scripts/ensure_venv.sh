#!/usr/bin/env bash
# Point the skill venv at fast local cache via UV_PROJECT_ENVIRONMENT.
#
# This previously symlinked .venv into /mnt/storage12tb. Two measured problems
# (2026-08-19): that path is /dev/sda1, rotational=1 and near-full, while the
# NVMe root has over 1T free -- interpreter startup paid seek latency on rust;
# and the SYMLINK dodged the repo .gitignore's ".venv/" rule (a symlink is not
# a directory), so it showed up as untracked cruft in every git status. The
# skill's own verify contract elsewhere in this repo rejects heavy runtime
# state in the source tree; a symlink pointing at it is the same problem in
# disguise. Override by exporting UV_PROJECT_ENVIRONMENT.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Drop any legacy in-tree .venv symlink from the old scheme.
if [[ -L "$SCRIPT_DIR/.venv" ]]; then
  rm -f "$SCRIPT_DIR/.venv"
fi
if [[ -z "${UV_PROJECT_ENVIRONMENT:-}" ]]; then
  export UV_PROJECT_ENVIRONMENT="${XDG_CACHE_HOME:-$HOME/.cache}/phart-dag-chart/venv"
fi
mkdir -p "$(dirname "$UV_PROJECT_ENVIRONMENT")"
