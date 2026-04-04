#!/bin/bash
set -euo pipefail

# Install Systemd Services for Task Monitor and Scheduler
# Uses 'uvx' to auto-load Python dependencies.
# Ensures services auto-restart on failure.

SYSTEMD_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_DIR"

# Resolve absolute paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MONITOR_SCRIPT="$SCRIPT_DIR/monitor.py"
SCHEDULER_SCRIPT="$(cd "$SCRIPT_DIR/../scheduler" && pwd)/scheduler.py"

# Find uvx binary (usually same location as uv)
UVX_BIN="$(which uvx 2>/dev/null || echo "$HOME/.cargo/bin/uvx")"
if [ ! -x "$UVX_BIN" ]; then
    echo "Error: 'uvx' not found. Please install uv (e.g. curl -LsSf https://astral.sh/uv/install.sh | sh)"
    exit 1
fi

echo "Installing services..."
echo "  Monitor:   $MONITOR_SCRIPT"
echo "  Scheduler: $SCHEDULER_SCRIPT"

# 1. Task Monitor Service (API)
cat <<EOF > "$SYSTEMD_DIR/pi-task-monitor.service"
[Unit]
Description=Pi Task Monitor API
After=network.target

[Service]
ExecStart=$UVX_BIN "$MONITOR_SCRIPT" serve --port 8765
WorkingDirectory=$(dirname "$MONITOR_SCRIPT")
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

# 2. Scheduler Service (Daemon)
cat <<EOF > "$SYSTEMD_DIR/pi-scheduler.service"
[Unit]
Description=Pi Scheduler Daemon
After=network.target

[Service]
ExecStart=$UVX_BIN "$SCHEDULER_SCRIPT" start
WorkingDirectory=$(dirname "$SCHEDULER_SCRIPT")
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

# Reload and Enable
systemctl --user daemon-reload
systemctl --user enable pi-task-monitor
systemctl --user enable pi-scheduler
systemctl --user restart pi-task-monitor
systemctl --user restart pi-scheduler

echo "Services installed and started:"
systemctl --user status pi-task-monitor --no-pager
systemctl --user status pi-scheduler --no-pager
