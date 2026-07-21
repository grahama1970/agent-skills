#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_ROOT="${WORKSPACE_ROOT:-$(cd "${SKILL_DIR}/../../.." && pwd)}"
REGISTRY="${SKILL_DIR}/scripts/project_registry.py"
HUB_SERVER="${SKILL_DIR}/scripts/serve_project_hub.py"

tau_dag_view() {
    local tau_bin="${TAU_BIN:-}"
    if [[ -z "$tau_bin" ]]; then
        tau_bin="$(command -v tau || true)"
    fi
    if [[ -z "$tau_bin" || ! -x "$tau_bin" ]]; then
        echo "Tau is required for the DAG viewer. Set TAU_BIN or install tau on PATH." >&2
        return 2
    fi

    local capabilities_file
    capabilities_file="$(mktemp "${TMPDIR:-/tmp}/ux-lab-tau-capabilities.XXXXXX")"
    trap 'rm -f "$capabilities_file"' RETURN

    if ! "$tau_bin" dag-view-capabilities --json >"$capabilities_file"; then
        echo "Tau DAG viewer capability discovery failed." >&2
        return 2
    fi

    if ! python3 - "$capabilities_file" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit(f"invalid Tau DAG viewer capability receipt: {exc}") from exc

if payload.get("schema") != "tau.dag_viewer_capabilities.v1":
    raise SystemExit("unsupported Tau DAG viewer capability schema")
if payload.get("read_only") is not True:
    raise SystemExit("Tau DAG viewer must declare read_only=true")
PY
    then
        echo "Tau DAG viewer capabilities are incompatible with UX Lab delegation." >&2
        return 2
    fi

    rm -f "$capabilities_file"
    trap - RETURN
    exec "$tau_bin" dag-view "$@"
}

case "${1:-start}" in
    tau-dag-view)
        shift
        tau_dag_view "$@"
        ;;
    start|serve)
        shift || true
        [[ $# -eq 0 ]] || { echo "Unexpected arguments for UX Lab hub: $*" >&2; exit 2; }
        exec python3 "${HUB_SERVER}"
        ;;
    list|projects)
        shift || true
        exec python3 "${REGISTRY}" list "$@"
        ;;
    url)
        shift || true
        exec python3 "${REGISTRY}" url "$@"
        ;;
    status)
        shift || true
        exec python3 "${REGISTRY}" status "$@"
        ;;
    start-project)
        shift || true
        exec python3 "${REGISTRY}" start-project "$@"
        ;;
    validate)
        shift || true
        exec python3 "${REGISTRY}" validate "$@"
        ;;
    help|--help|-h)
        printf '%s\n' \
            'Usage:' \
            '  run.sh [start|serve]' \
            '  run.sh list [--json]' \
            '  run.sh url [project] [surface]' \
            '  run.sh status [project]' \
            '  run.sh start-project <project>' \
            '  run.sh tau-dag-view --run-dir /path/to/tau-run'
        ;;
    *)
        echo "Unknown ux-lab command: $1" >&2
        exit 2
        ;;
esac
