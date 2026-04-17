#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${HOME}/.embry/dum-dum"
mkdir -p "$DATA_DIR"

# ---------- subcommands ----------

cmd_probe() {
    local model=""
    local dry_run=0
    local json_out=0
    local -a args=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --model) model="$2"; shift 2 ;;
            --dry-run) dry_run=1; shift ;;
            --json) json_out=1; shift ;;
            -*) echo "Unknown flag: $1" >&2; exit 1 ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done

    [[ $dry_run -eq 1 ]] && args+=(--dry-run)
    [[ $json_out -eq 1 ]] && args+=(--json)

    if [[ $dry_run -eq 0 ]] && [[ -z "$model" ]]; then
        echo "Usage: $0 probe --model MODEL [--dry-run] [--json]" >&2
        exit 1
    fi

    [[ -n "$model" ]] && args+=(--model "$model")

    uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/probe.py" "${args[@]}"
}

cmd_collect() {
    local dry_run=0
    local all_sessions=0
    local json_out=0
    local -a args=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) dry_run=1; shift ;;
            --all) all_sessions=1; shift ;;
            --json) json_out=1; shift ;;
            -*) echo "Unknown flag: $1" >&2; exit 1 ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done

    [[ $dry_run -eq 1 ]] && args+=(--dry-run)
    [[ $all_sessions -eq 1 ]] && args+=(--all)
    [[ $json_out -eq 1 ]] && args+=(--json)

    uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/collect.py" "${args[@]}"
}

cmd_drift() {
    local dry_run=0
    local json_out=0
    local -a args=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) dry_run=1; shift ;;
            --json) json_out=1; shift ;;
            -*) echo "Unknown flag: $1" >&2; exit 1 ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done

    [[ $dry_run -eq 1 ]] && args+=(--dry-run)
    [[ $json_out -eq 1 ]] && args+=(--json)

    uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/drift.py" "${args[@]}"
}

cmd_dashboard() {
    local -a args=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --export) args+=(--export "$2"); shift 2 ;;
            -*) echo "Unknown flag: $1" >&2; exit 1 ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done

    uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/dashboard.py" "${args[@]}"
}

cmd_status() {
    local json_out=0
    local -a args=()

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --json) json_out=1; shift ;;
            -*) echo "Unknown flag: $1" >&2; exit 1 ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done

    [[ $json_out -eq 1 ]] && args+=(--json)

    uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/status.py" "${args[@]}"
}

# ---------- dispatch ----------

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 {probe|collect|drift|dashboard|status}" >&2
    exit 1
fi

subcmd="$1"; shift
case "$subcmd" in
    probe)     cmd_probe "$@" ;;
    collect)   cmd_collect "$@" ;;
    drift)     cmd_drift "$@" ;;
    dashboard) cmd_dashboard "$@" ;;
    status)    cmd_status "$@" ;;
    *)         echo "Unknown subcommand: $subcmd" >&2; exit 1 ;;
esac
