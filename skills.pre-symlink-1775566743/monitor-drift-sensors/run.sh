#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ---------- subcommands ----------

cmd_analyze() {
    local dry_run=0
    local input_file=""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run) dry_run=1; shift ;;
            -*) echo "Unknown flag: $1" >&2; exit 1 ;;
            *) input_file="$1"; shift ;;
        esac
    done

    if [[ $dry_run -eq 1 ]]; then
        input_file="${SCRIPT_DIR}/fixtures/drift_sample.jsonl"
    fi

    if [[ -z "$input_file" ]]; then
        echo "Usage: $0 analyze <data.jsonl> [--dry-run]" >&2
        echo "  --dry-run  Use built-in fixture data" >&2
        exit 1
    fi

    if [[ "$input_file" != "-" ]] && [[ ! -f "$input_file" ]]; then
        echo "Error: file not found: $input_file" >&2
        exit 1
    fi

    uv run --project "$SCRIPT_DIR" python "${SCRIPT_DIR}/detect.py" "$input_file"
}

cmd_watch() {
    local sensor=""
    local threshold="3.0"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --sensor) sensor="$2"; shift 2 ;;
            --threshold) threshold="$2"; shift 2 ;;
            -*) echo "Unknown flag: $1" >&2; exit 1 ;;
            *) echo "Unknown arg: $1" >&2; exit 1 ;;
        esac
    done

    if [[ -z "$sensor" ]]; then
        echo "Usage: $0 watch --sensor NAME [--threshold FLOAT]" >&2
        exit 1
    fi

    echo "watch mode requires running daemons"
    echo "  sensor:    $sensor"
    echo "  threshold: $threshold"
    echo ""
    echo "Start daemons first, then this command will query the"
    echo "ArangoDB sensor_readings collection in real-time."
}

cmd_status() {
    echo "=== monitor-drift-sensors status ==="
    echo ""
    echo "Algorithm Parameters:"
    echo "  CUSUM threshold (h):        5.0"
    echo "  CUSUM drift allowance (k):  0.5"
    echo "  Page-Hinkley threshold:     10.0"
    echo "  Page-Hinkley delta:         0.01"
    echo "  Warmup samples:             5"
    echo ""
    echo "Last run: check ./run.sh analyze --dry-run for live results"
}

# ---------- dispatch ----------

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 {analyze|watch|status}" >&2
    exit 1
fi

subcmd="$1"; shift
case "$subcmd" in
    analyze) cmd_analyze "$@" ;;
    watch)   cmd_watch "$@" ;;
    status)  cmd_status "$@" ;;
    *)       echo "Unknown subcommand: $subcmd" >&2; exit 1 ;;
esac
