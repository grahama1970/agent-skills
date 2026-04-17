#!/usr/bin/env bash
# /switchboard skill — dispatch and supervise manifest runs
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SWITCHBOARD_PKG="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")/packages/switchboard"
SWITCHBOARD_URL="${SWITCHBOARD_URL:-http://127.0.0.1:7890}"

case "${1:-help}" in
    server-start)
        cd "$SWITCHBOARD_PKG" && bash switchboard.sh start
        ;;
    server-stop)
        cd "$SWITCHBOARD_PKG" && bash switchboard.sh stop
        ;;
    health)
        curl -fsSL "$SWITCHBOARD_URL/health" 2>/dev/null || echo '{"status":"unreachable"}'
        ;;
    start)
        manifest="${2:-}"
        if [[ -z "$manifest" || ! -f "$manifest" ]]; then
            echo "Usage: ./run.sh start <manifest.yaml>" >&2
            exit 1
        fi
        # Convert YAML to JSON and POST to /run/start
        manifest_json=$(python3 -c "
import sys, json, yaml
with open(sys.argv[1]) as f:
    data = yaml.safe_load(f)
print(json.dumps({'manifest': data}))
" "$manifest")
        curl -fsSL -X POST "$SWITCHBOARD_URL/run/start" \
            -H 'Content-Type: application/json' \
            -d "$manifest_json"
        ;;
    status)
        run_id="${2:-}"
        [[ -n "$run_id" ]] || { echo "Usage: ./run.sh status <run_id>" >&2; exit 1; }
        curl -fsSL "$SWITCHBOARD_URL/run/$run_id" 2>/dev/null | python3 -m json.tool
        ;;
    cancel)
        run_id="${2:-}"
        [[ -n "$run_id" ]] || { echo "Usage: ./run.sh cancel <run_id>" >&2; exit 1; }
        curl -fsSL -X POST "$SWITCHBOARD_URL/run/$run_id/cancel"
        ;;
    pause)
        run_id="${2:-}"
        [[ -n "$run_id" ]] || { echo "Usage: ./run.sh pause <run_id>" >&2; exit 1; }
        curl -fsSL -X POST "$SWITCHBOARD_URL/run/$run_id/pause"
        ;;
    list)
        curl -fsSL "$SWITCHBOARD_URL/runs" 2>/dev/null | python3 -m json.tool
        ;;
    tail)
        run_id="${2:-}"
        [[ -n "$run_id" ]] || { echo "Usage: ./run.sh tail <run_id>" >&2; exit 1; }
        log_file="$HOME/.pi/agent/services/switchboard/runs/${run_id}.jsonl"
        if [[ -f "$log_file" ]]; then
            tail -f "$log_file"
        else
            echo "Log file not found: $log_file" >&2
            echo "Run may not have started yet. Check: ./run.sh status $run_id" >&2
            exit 1
        fi
        ;;
    help|--help|-h)
        echo "Usage: ./run.sh {server-start|server-stop|health|start|status|cancel|pause|list|tail}"
        echo ""
        echo "Commands:"
        echo "  server-start         Start the Switchboard server"
        echo "  server-stop          Stop the Switchboard server"
        echo "  health               Check server health"
        echo "  start <manifest>     Submit manifest for execution"
        echo "  status <run_id>      Check run status"
        echo "  cancel <run_id>      Cancel a running execution"
        echo "  pause <run_id>       Pause a running execution"
        echo "  list                 List all runs"
        echo "  tail <run_id>        Tail JSONL event log"
        ;;
    *)
        echo "Unknown command: $1" >&2
        echo "Run './run.sh help' for usage" >&2
        exit 1
        ;;
esac
