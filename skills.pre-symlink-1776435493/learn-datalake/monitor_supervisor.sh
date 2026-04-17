#!/usr/bin/env bash
# learn-datalake supervisor sidecar monitor
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WATCHDOG_DIR="$SCRIPT_DIR/state/watchdogs"
TASK_MONITOR_RUN="$SCRIPT_DIR/../task-monitor/run.sh"

LABEL="corpus"
INTERVAL_SECONDS="60"
REPORT_PATH=""

while [[ $# -gt 0 ]]; do
    case "$1" in
    --label)
        LABEL="$2"
        shift 2
        ;;
    --interval-seconds)
        INTERVAL_SECONDS="$2"
        shift 2
        ;;
    --report-path)
        REPORT_PATH="$2"
        shift 2
        ;;
    *)
        echo "ERROR: unknown option: $1" >&2
        exit 2
        ;;
    esac
done

if [[ -z "$REPORT_PATH" ]]; then
    REPORT_PATH="$WATCHDOG_DIR/monitor_${LABEL}_report.txt"
fi

STATE_FILE="$WATCHDOG_DIR/supervisor_${LABEL}.json"
SUPERVISOR_LOG="$WATCHDOG_DIR/supervisor_${LABEL}.log"
PID_FILE="$WATCHDOG_DIR/monitor_${LABEL}.pid"
TMP_REPORT="${REPORT_PATH}.tmp"

mkdir -p "$WATCHDOG_DIR"
echo "$$" >"$PID_FILE"

cleanup() {
    rm -f "$PID_FILE"
}
trap cleanup EXIT INT TERM

while true; do
    {
        echo "=== learn-datalake sidecar-monitor $(date -Iseconds) ==="
        echo "label=$LABEL"
        if [[ -x "$TASK_MONITOR_RUN" ]]; then
            echo "-- task_monitor_status_table --"
            "$TASK_MONITOR_RUN" status \
                --name "learn_datalake_supervisor_${LABEL}" \
                --table \
                --watch 0 2>/dev/null | head -n 12
        else
            echo "task_monitor_missing=$TASK_MONITOR_RUN"
        fi

        if [[ -f "$STATE_FILE" ]]; then
            status=$(jq -r '.status // "unknown"' "$STATE_FILE" 2>/dev/null)
            run_id=$(jq -r '.run_id // .last_run_id // "none"' "$STATE_FILE" 2>/dev/null)
            updated_at=$(jq -r '.updated_at // "unknown"' "$STATE_FILE" 2>/dev/null)
            child_pid=$(jq -r '.child_pid // 0' "$STATE_FILE" 2>/dev/null)
            heartbeat_fresh=$(jq -r '.review_heartbeat_fresh // false' "$STATE_FILE" 2>/dev/null)
            heartbeat_age=$(jq -r '.review_heartbeat_age_seconds // -1' "$STATE_FILE" 2>/dev/null)
            run_log=$(jq -r '.run_log // .last_run_log // ""' "$STATE_FILE" 2>/dev/null)

            echo "status=$status run_id=$run_id updated_at=$updated_at"
            echo "child_pid=$child_pid heartbeat_fresh=$heartbeat_fresh heartbeat_age=$heartbeat_age"

            if [[ "$child_pid" =~ ^[0-9]+$ ]] && [[ "$child_pid" -gt 1 ]]; then
                if kill -0 "$child_pid" >/dev/null 2>&1; then
                    echo "child_process=alive"
                else
                    echo "child_process=dead"
                fi
            else
                echo "child_process=unknown"
            fi

            if [[ -n "$run_log" ]] && [[ -f "$run_log" ]]; then
                log_size=$(stat -c '%s' "$run_log" 2>/dev/null || echo -1)
                log_mtime=$(stat -c '%y' "$run_log" 2>/dev/null || echo unknown)
                echo "run_log_size=$log_size run_log_mtime=$log_mtime run_log=$run_log"
                tail -n 10 "$run_log" 2>/dev/null
            else
                echo "run_log=missing"
            fi
        else
            echo "state_file_missing=$STATE_FILE"
        fi

        if [[ -f "$SUPERVISOR_LOG" ]]; then
            echo "-- supervisor_log_tail --"
            tail -n 10 "$SUPERVISOR_LOG" 2>/dev/null
        else
            echo "supervisor_log_missing=$SUPERVISOR_LOG"
        fi

    } >"$TMP_REPORT" 2>/dev/null

    mv -f "$TMP_REPORT" "$REPORT_PATH" 2>/dev/null || true

    # Sync supervisor state → task-monitor bridge file
    TASKMON_BRIDGE="$WATCHDOG_DIR/taskmon_${LABEL}.json"
    if [[ -f "$STATE_FILE" ]]; then
        python3 -c "
import json, sys
try:
    with open('$STATE_FILE') as f:
        sup = json.load(f)
    m = sup.get('run_metrics', {})
    completed = m.get('extraction_success_count', 0) + m.get('extraction_cached_profile_count', 0)
    bridge = {
        'completed': completed,
        'total': int(m.get('documents_total', 0)) or (int(m.get('extraction_attempts', 0)) + int(m.get('extraction_deferred_count', 0))) or completed,
        'description': 'Datalake ingestion ($LABEL)',
        'current_item': m.get('last_extracted_pdf', ''),
        'current_method': f'phase={m.get(\"phase\",\"?\")} workers={m.get(\"workers\",0)}',
        'last_updated': sup.get('updated_at', ''),
        'consecutive_failures': m.get('quality_gate_consecutive_failures', 0),
        'status': sup.get('status', 'unknown'),
        'stats': {
            'success': m.get('extraction_success_count', 0),
            'failed': m.get('extraction_failed_count', 0),
            'status': sup.get('status', 'unknown'),
            'extraction_fail_rate_pct': m.get('extraction_fail_rate_pct', 0),
            'extraction_throughput_per_hour': m.get('extraction_throughput_per_hour', 0),
            'extraction_timeout_rate_pct': m.get('extraction_timeout_rate_pct', 0),
            'restart_count': sup.get('restart_count', 0),
            'quality_gate_action': m.get('quality_gate_action', ''),
            'phase': m.get('phase', ''),
            'blacklist_count': m.get('blacklist_count', 0),
        }
    }
    with open('$TASKMON_BRIDGE', 'w') as f:
        json.dump(bridge, f, indent=2)
except Exception:
    pass
" 2>/dev/null
    fi

    sleep "$INTERVAL_SECONDS"
done
