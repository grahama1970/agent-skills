#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT="${PORT:-5179}"
HOST="${HOST:-localhost}"
URL="http://${HOST}:${PORT}/"
STATE_DIR="${STATE_DIR:-/tmp/create-evidence-case-viewer}"
PID_FILE="${STATE_DIR}/viewer-${PORT}.pid"
LOG_FILE="${STATE_DIR}/viewer-${PORT}.log"

mkdir -p "$STATE_DIR"

ensure_deps() {
  cd "$ROOT"
  if [[ ! -d node_modules ]]; then
    npm install
  fi
}

wait_for_port_pid() {
  local attempts="${1:-40}"
  local pid=""
  for _ in $(seq 1 "$attempts"); do
    pid="$(find_port_pids | head -n 1 || true)"
    if [[ -n "$pid" ]]; then
      echo "$pid"
      return 0
    fi
    sleep 0.25
  done
  return 1
}

find_port_pids() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti tcp:"$PORT" 2>/dev/null || true
  else
    ss -ltnp "( sport = :${PORT} )" 2>/dev/null | awk -F 'pid=' 'NF > 1 {split($2, a, /[ ,)]/); print a[1]}' | sort -u
  fi
}

is_pid_running() {
  local pid="$1"
  kill -0 "$pid" 2>/dev/null
}

healthcheck() {
  curl -fsS --max-time 2 "$URL" >/dev/null 2>&1
}

stop_existing() {
  local pids=()
  if [[ -f "$PID_FILE" ]]; then
    local pid
    pid="$(cat "$PID_FILE")"
    if [[ -n "$pid" ]] && is_pid_running "$pid"; then
      pids+=("$pid")
    fi
  fi

  while IFS= read -r pid; do
    [[ -n "$pid" ]] && pids+=("$pid")
  done < <(find_port_pids)

  if [[ "${#pids[@]}" -eq 0 ]]; then
    rm -f "$PID_FILE"
    return 0
  fi

  printf '%s\n' "${pids[@]}" | sort -u | while read -r pid; do
    [[ -z "$pid" ]] && continue
    kill "$pid" 2>/dev/null || true
  done

  sleep 1

  while IFS= read -r pid; do
    [[ -n "$pid" ]] && kill -9 "$pid" 2>/dev/null || true
  done < <(find_port_pids)

  rm -f "$PID_FILE"
}

start_server() {
  ensure_deps
  stop_existing

  cd "$ROOT"
  export CHOKIDAR_USEPOLLING="${CHOKIDAR_USEPOLLING:-1}"
  export CHOKIDAR_INTERVAL="${CHOKIDAR_INTERVAL:-300}"
  : >"$LOG_FILE"

  setsid bash -lc "
    cd \"$ROOT\"
    export CHOKIDAR_USEPOLLING=\"$CHOKIDAR_USEPOLLING\"
    export CHOKIDAR_INTERVAL=\"$CHOKIDAR_INTERVAL\"
    exec ./node_modules/.bin/vite --host \"$HOST\" --port \"$PORT\" --strictPort
  " >>"$LOG_FILE" 2>&1 </dev/null &

  local pid=""
  pid="$(wait_for_port_pid 80 || true)"
  if [[ -z "$pid" ]]; then
    echo "viewer failed to bind port $PORT; last log lines:" >&2
    tail -n 40 "$LOG_FILE" >&2 || true
    return 1
  fi
  echo "$pid" >"$PID_FILE"

  for _ in $(seq 1 40); do
    if ! is_pid_running "$pid"; then
      echo "viewer failed to start; last log lines:" >&2
      tail -n 40 "$LOG_FILE" >&2 || true
      return 1
    fi
    if healthcheck; then
      echo "viewer running at $URL"
      echo "pid: $pid"
      echo "log: $LOG_FILE"
      return 0
    fi
    sleep 0.5
  done

  echo "viewer did not become healthy; last log lines:" >&2
  tail -n 40 "$LOG_FILE" >&2 || true
  return 1
}

show_status() {
  local pid=""
  if [[ -f "$PID_FILE" ]]; then
    pid="$(cat "$PID_FILE")"
  fi

  if [[ -n "$pid" ]] && is_pid_running "$pid" && healthcheck; then
    echo "running"
    echo "url: $URL"
    echo "pid: $pid"
    echo "log: $LOG_FILE"
    return 0
  fi

  echo "stopped"
  echo "url: $URL"
  [[ -f "$PID_FILE" ]] && echo "stale pid file: $PID_FILE"
  [[ -f "$LOG_FILE" ]] && echo "log: $LOG_FILE"
  return 1
}

show_logs() {
  touch "$LOG_FILE"
  tail -n "${TAIL_LINES:-80}" "$LOG_FILE"
}

usage() {
  cat <<EOF
Usage: $(basename "$0") <start|stop|restart|status|logs>
Environment:
  PORT=5179
  HOST=localhost
  STATE_DIR=/tmp/create-evidence-case-viewer
EOF
}

cmd="${1:-status}"

case "$cmd" in
  start)
    start_server
    ;;
  stop)
    stop_existing
    echo "viewer stopped"
    ;;
  restart)
    start_server
    ;;
  status)
    show_status
    ;;
  logs)
    show_logs
    ;;
  *)
    usage >&2
    exit 1
    ;;
esac
