#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

# Load .env if present
if [ -f "$PROJECT_ROOT/.env" ]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
cd "$(dirname "$0")"

# ops-workstation skill dispatcher
# Comprehensive workstation operations for AI agents

show_help() {
  cat <<EOF
Workstation Ops - System diagnostics for AI agents

Commands:
  check [opts]      Quick resource check (CPU, memory, disk) - default
  limits [opts]     Kernel limits (inotify, open files, processes)
  memory [opts]     Detailed memory report with leak detection
  gpu [opts]        GPU status and utilization
  health [opts]     Drive health (SMART) and maintenance status
  net [opts]        Network diagnostics (link, IP, DNS, sockets, gateway)
  temps [opts]      Temperature monitoring (CPU, GPU, NVMe)
  audio [opts]      Audio diagnostics (PipeWire, ALSA, XRUN, sink hijack)
  vscode [opts]     VS Code health (V8 OOM, runaway workers, heap config)
  containers        Container health summary (Docker)
  slim [opts]       Find storage savings (media quality, caches, duplicates)
  duplicates [opts] Find exact duplicate files
  crashes [opts]    Analyze system crashes via journalctl
  hogs [opts]       Find sustained CPU hogs (>80% for >30min)
  diagnose [opts]   Full system diagnosis with recommendations
  specs [opts]      Hardware specs and upgrade procedures
  help              Show this help

Quick Reference:
  ./run.sh                     # Am I running low on resources?
  ./run.sh limits              # inotify/file limits (ENOSPC fix)
  ./run.sh gpu                 # Will my model fit in GPU memory?
  ./run.sh memory              # What's using all the RAM?
  ./run.sh health              # Are my drives healthy?
  ./run.sh net                 # Network connectivity check
  ./run.sh temps               # Temperature check
  ./run.sh audio               # Is audio working? (XRUN, mute, hijack)
  ./run.sh audio --fix         # Auto-fix detected audio issues
  ./run.sh slim                # Where can I recover storage?
  ./run.sh vscode              # VS Code frozen / not accepting input?
  ./run.sh vscode --fix        # Kill runaway VS Code workers
  ./run.sh hogs                # Fans always on? Find CPU hogs
  ./run.sh crashes --oom       # Did something get OOM killed?
  OUTPUT=json ./run.sh net     # JSON output for agents

Exit Codes:
  0 = All good
  1 = Warning
  2 = Critical

Examples:
  ./run.sh slim                # Overview of all storage savings
  ./run.sh slim --media        # Find lower quality media versions
  ./run.sh net --no-external   # Skip external ICMP checks
  ./run.sh temps --warn 70     # Custom warning threshold
  ./run.sh containers          # Docker container status
EOF
}

cmd="${1:-check}"
shift 2>/dev/null || true

case "$cmd" in
  check)
    exec bash scripts/check.sh "$@"
    ;;
  limits)
    if [[ "${OUTPUT:-}" == "json" ]]; then
      exec bash scripts/limits.sh --json "$@"
    else
      exec bash scripts/limits.sh "$@"
    fi
    ;;
  memory|mem)
    exec bash scripts/memory-report.sh "$@"
    ;;
  gpu)
    exec bash scripts/gpu-check.sh "$@"
    ;;
  health)
    exec bash scripts/health.sh "$@"
    ;;
  slim)
    exec bash scripts/slim.sh "$@"
    ;;
  net|network)
    # Honor OUTPUT env var for agent-friendly JSON
    if [[ "${OUTPUT:-}" == "json" ]]; then
      exec bash scripts/net.sh --json "$@"
    else
      exec bash scripts/net.sh "$@"
    fi
    ;;
  temps|temperature|thermal)
    if [[ "${OUTPUT:-}" == "json" ]]; then
      exec bash scripts/temps.sh --json "$@"
    else
      exec bash scripts/temps.sh "$@"
    fi
    ;;
  audio|sound)
    if [[ "${OUTPUT:-}" == "json" ]]; then
      exec bash scripts/audio.sh --json "$@"
    else
      exec bash scripts/audio.sh "$@"
    fi
    ;;
  containers|docker)
    if [[ "${OUTPUT:-}" == "json" ]]; then
      exec bash scripts/containers.sh --json "$@"
    else
      exec bash scripts/containers.sh "$@"
    fi
    ;;
  vscode|code)
    if [[ "${OUTPUT:-}" == "json" ]]; then
      exec bash scripts/vscode.sh --json "$@"
    else
      exec bash scripts/vscode.sh "$@"
    fi
    ;;
  duplicates|dupes)
    exec bash scripts/duplicates.sh "$@"
    ;;
  crashes|crash|logs)
    exec bash scripts/crashes.sh "$@"
    ;;
  hogs|hog|sustained)
    if [[ "${OUTPUT:-}" == "json" ]]; then
      exec bash scripts/hogs.sh --json "$@"
    else
      exec bash scripts/hogs.sh "$@"
    fi
    ;;
  diagnose|diag)
    exec bash scripts/diagnose.sh "$@"
    ;;
  specs|info)
    exec bash scripts/specs.sh "$@"
    ;;
  help|--help|-h)
    show_help
    exit 0
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    show_help
    exit 1
    ;;
esac
