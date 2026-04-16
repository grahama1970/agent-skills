#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# ops-embry-agent: Manage the Embry Agent D-Bus daemon.
set -euo pipefail

SERVICE_NAME="embry-agent.service"
DBUS_NAME="org.embry.Agent"
DBUS_PATH="/org/embry/Agent"
DBUS_IFACE="org.embry.Agent"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_DIR="${SCRIPT_DIR}/../../systemd"

usage() {
    echo "Usage: run.sh <command> [args]"
    echo ""
    echo "Commands:"
    echo "  status      Show daemon status"
    echo "  start       Start the daemon"
    echo "  stop        Stop the daemon"
    echo "  restart     Restart the daemon"
    echo "  logs [N]    Show last N log lines (default 50)"
    echo "  install     Install systemd user service"
    echo "  uninstall   Remove systemd user service"
    echo "  ping        D-Bus health check"
    echo "  help        Show this help"
}

cmd_status() {
    echo "=== systemd status ==="
    systemctl --user status "$SERVICE_NAME" --no-pager 2>/dev/null || echo "Service not found or not running."
    echo ""
    echo "=== D-Bus name ==="
    if busctl --user list 2>/dev/null | grep -q "$DBUS_NAME"; then
        echo "$DBUS_NAME: REGISTERED"
    else
        echo "$DBUS_NAME: NOT REGISTERED"
    fi
}

cmd_start() {
    systemctl --user start "$SERVICE_NAME"
    echo "Started $SERVICE_NAME"
    # Wait briefly for D-Bus registration
    sleep 2
    cmd_ping
}

cmd_stop() {
    systemctl --user stop "$SERVICE_NAME"
    echo "Stopped $SERVICE_NAME"
}

cmd_restart() {
    systemctl --user restart "$SERVICE_NAME"
    echo "Restarted $SERVICE_NAME"
    sleep 2
    cmd_ping
}

cmd_logs() {
    local lines="${1:-50}"
    journalctl --user -u "$SERVICE_NAME" --no-pager -n "$lines"
}

cmd_install() {
    bash "${SYSTEMD_DIR}/install.sh"
}

cmd_uninstall() {
    bash "${SYSTEMD_DIR}/install.sh" --uninstall
}

cmd_ping() {
    local result
    if result=$(busctl --user call "$DBUS_NAME" "$DBUS_PATH" "$DBUS_IFACE" Ping 2>/dev/null); then
        echo "Ping: $result"
    else
        echo "Ping: FAILED (daemon not responding)"
        return 1
    fi
}

case "${1:-help}" in
    status)   cmd_status ;;
    start)    cmd_start ;;
    stop)     cmd_stop ;;
    restart)  cmd_restart ;;
    logs)     cmd_logs "${2:-50}" ;;
    install)  cmd_install ;;
    uninstall) cmd_uninstall ;;
    ping)     cmd_ping ;;
    help|-h|--help) usage ;;
    *)        echo "Unknown command: $1"; usage; exit 1 ;;
esac
