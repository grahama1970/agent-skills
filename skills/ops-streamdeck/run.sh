#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Stream Deck Skill - Main Entry Point
# Auto-installs via uvx from git if needed

set -e

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get the skill name from directory name
SKILL_NAME="$(basename "$SCRIPT_DIR")"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Log function
log() {
    echo -e "${GREEN}[$SKILL_NAME]${NC} $*"
}

# Error function
error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

# Check if uvx is available
if ! command -v uvx &> /dev/null; then
    error "uvx not found. Install with: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

# Parse command
COMMAND="${1:-help}"

# Show help
show_help() {
    cat << EOF
Stream Deck Skill - Agent-accessible interface for Stream Deck control

USAGE:
    $0 <command> [options]

COMMANDS:
    daemon          Daemon management commands
    button          Button operation commands
    status          Status query commands
    config          Configuration commands
    health-check    Verify services and button icons
    fix             Auto-fix button configuration (safe)
    help            Show this help message

DAEMON COMMANDS:
    start              Start streamdeck daemon (background)
    start --foreground  Start daemon in foreground (for debugging)
    stop               Stop streamdeck daemon
    restart            Restart streamdeck daemon
    status             Check if daemon is running
    logs               View daemon logs

BUTTON COMMANDS:
    <id>              Execute button press event
    <id> --hold       Execute button long-press event
    list-buttons       List all available button IDs
    button-info <id>  Get information about a button

AGENT COMMANDS (D-Bus):
    agent ask "prompt"  Send prompt to Pi agent via D-Bus
    agent ping          Health check the Pi agent daemon
    agent state         Get agent state (model, session, streaming)
    agent abort         Cancel current agent operation

STATUS COMMANDS:
    status             Get overall daemon status
    status --json      Get status in JSON format
    status --buttons    Get button states

CONFIG COMMANDS:
    config             Show current configuration
    config --set <key> <value>  Set configuration value
    config --get <key>  Get configuration value

ENVIRONMENT VARIABLES:
    STREAMDECK_DAEMON_PORT    Daemon API port (default: 48970)
    STREAMDECK_DAEMON_HOST    Daemon API host (default: 127.0.0.1)
    STREAMDECK_LOG_LEVEL       Log level (DEBUG, INFO, WARNING, ERROR)

EXAMPLES:
    # Start daemon
    $0 daemon start

    # Execute button
    $0 button 0

    # Get status
    $0 status

    # Restart daemon
    $0 restart

For more information, see SKILL.md
EOF
}

# Daemon management — uses systemd user services (the actual running infrastructure)
STREAMDECK_SERVICES="streamdeck streamdeck-clock streamdeck-weather streamdeck-monitor streamdeck-plant-monitor streamdeck-living-room-monitor"

daemon_start() {
    log "Starting streamdeck services..."

    local failed=0
    for svc in $STREAMDECK_SERVICES; do
        if systemctl --user is-active "${svc}.service" &>/dev/null; then
            log "  $svc already running"
        else
            systemctl --user start "${svc}.service" 2>/dev/null && \
                log "  $svc started" || \
                { error "  $svc failed to start"; failed=1; }
        fi
    done

    if [ "$failed" -eq 0 ]; then
        log "All services started"
    else
        error "Some services failed to start"
        exit 1
    fi
}

daemon_stop() {
    log "Stopping streamdeck services..."

    for svc in $STREAMDECK_SERVICES; do
        if systemctl --user is-active "${svc}.service" &>/dev/null; then
            systemctl --user stop "${svc}.service" 2>/dev/null && \
                log "  $svc stopped" || \
                error "  $svc failed to stop"
        fi
    done
    log "All services stopped"
}

daemon_restart() {
    log "Restarting streamdeck services..."
    daemon_stop
    sleep 2
    daemon_start
}

daemon_status() {
    log "Stream Deck service status:"
    echo ""

    local all_ok=true
    for svc in $STREAMDECK_SERVICES; do
        local status=$(systemctl --user is-active "${svc}.service" 2>/dev/null || echo "inactive")
        if [ "$status" = "active" ]; then
            echo "  [OK]   $svc"
        else
            echo "  [FAIL] $svc ($status)"
            all_ok=false
        fi
    done

    echo ""
    if [ "$all_ok" = true ]; then
        log "All services running"
    else
        error "Some services are not running"
        return 1
    fi
}

daemon_logs() {
    log "Stream Deck service logs (last 50 lines):"
    journalctl --user -u "streamdeck*" --no-pager -n 50 2>/dev/null || \
        log "No journal logs available"
}

# Button operations — read config from ~/.streamdeck_ui.json
STREAMDECK_CONFIG="$HOME/.streamdeck_ui.json"

button_execute() {
    local button_id="$1"
    local hold="${2:-}"

    log "Executing button: $button_id"

    if [ ! -f "$STREAMDECK_CONFIG" ]; then
        error "Config file not found: $STREAMDECK_CONFIG"
        exit 1
    fi

    # Extract the command for this button from the config
    local cmd=$(python3 -c "
import json, sys
with open('$STREAMDECK_CONFIG') as f:
    cfg = json.load(f)
deck_id = list(cfg['state'].keys())[0]
btn = cfg['state'][deck_id]['buttons']['0'].get('$button_id', {})
cmd = btn.get('command', '')
if not cmd:
    print('NO_COMMAND', file=sys.stderr)
    sys.exit(1)
print(cmd)
" 2>/dev/null)

    if [ -z "$cmd" ] || [ "$cmd" = "NO_COMMAND" ]; then
        error "Button $button_id has no command configured"
        exit 1
    fi

    if [ "$hold" = "--hold" ]; then
        log "Long-press event (executing same command)"
    fi

    log "Running: $cmd"
    eval "$cmd"
    log "Button $button_id executed"
}

button_list() {
    log "Listing configured buttons..."

    if [ ! -f "$STREAMDECK_CONFIG" ]; then
        error "Config file not found: $STREAMDECK_CONFIG"
        exit 1
    fi

    python3 << 'LIST_EOF'
import json
with open("$HOME/.streamdeck_ui.json".replace("$HOME", __import__("os").environ["HOME"])) as f:
    cfg = json.load(f)
deck_id = list(cfg["state"].keys())[0]
buttons = cfg["state"][deck_id]["buttons"]["0"]
print(f"{'ID':>4}  {'Text':20}  {'Command':40}  Icon")
print("-" * 90)
for btn_id in sorted(buttons.keys(), key=int):
    btn = buttons[btn_id]
    text = btn.get("text", "")
    cmd = btn.get("command", "")
    states = btn.get("states", {})
    icon = states.get("0", {}).get("icon", "")
    if text or cmd or icon:
        icon_short = icon.split("/")[-1] if icon else ""
        print(f"{btn_id:>4}  {text:20}  {cmd:40}  {icon_short}")
LIST_EOF
}

button_info() {
    local button_id="$1"
    log "Button $button_id info:"

    if [ ! -f "$STREAMDECK_CONFIG" ]; then
        error "Config file not found: $STREAMDECK_CONFIG"
        exit 1
    fi

    python3 -c "
import json
with open('${STREAMDECK_CONFIG}') as f:
    cfg = json.load(f)
deck_id = list(cfg['state'].keys())[0]
btn = cfg['state'][deck_id]['buttons']['0'].get('$button_id', {})
print(json.dumps(btn, indent=2))
"
}

# Status queries
status_show() {
    local mode="${1:-}"

    if [ "$mode" = "--json" ]; then
        # JSON output for machine parsing
        python3 << 'STATUS_JSON_EOF'
import json, subprocess, os
from pathlib import Path

result = {"services": {}, "hardware": False, "buttons": 0}

services = ["streamdeck", "streamdeck-clock", "streamdeck-weather",
            "streamdeck-monitor", "streamdeck-plant-monitor", "streamdeck-living-room-monitor"]

for svc in services:
    r = subprocess.run(["systemctl", "--user", "is-active", f"{svc}.service"],
                       capture_output=True, text=True)
    result["services"][svc] = r.stdout.strip()

# Hardware check
r = subprocess.run(["lsusb"], capture_output=True, text=True)
result["hardware"] = "elgato" in r.stdout.lower()

# Button count
config = Path.home() / ".streamdeck_ui.json"
if config.exists():
    with open(config) as f:
        cfg = json.load(f)
    deck_id = list(cfg["state"].keys())[0]
    result["buttons"] = len(cfg["state"][deck_id]["buttons"]["0"])

print(json.dumps(result, indent=2))
STATUS_JSON_EOF
    elif [ "$mode" = "--buttons" ]; then
        button_list
    else
        daemon_status
    fi
}

# Configuration
config_show() {
    log "Current configuration:"
    
    local config_file="$HOME/.streamdeck/daemon.json"
    
    if [ -f "$config_file" ]; then
        cat "$config_file" | python3 -m json.tool
    else
        log "No configuration file found at: $config_file"
    fi
}

config_set() {
    local key="$1"
    local value="$2"
    
    log "Setting configuration: $key = $value"
    
    local config_file="$HOME/.streamdeck/daemon.json"
    
    # Create config if doesn't exist
    if [ ! -f "$config_file" ]; then
        mkdir -p "$(dirname "$config_file")"
        echo '{"daemon": {}, "buttons": {}}' > "$config_file"
    fi
    
    # Update config
    export CONFIG_KEY="$key"
    export CONFIG_VAL="$value"
    
    python3 << EOF
import json
import os
import sys

config_file = '$config_file'
key = os.environ['CONFIG_KEY']
val_str = os.environ['CONFIG_VAL']

# Try to parse value as JSON, fallback to string
try:
    value = json.loads(val_str)
except:
    value = val_str

with open(config_file, 'r') as f:
    config = json.load(f)

# Set value
if key.startswith('daemon.'):
    # Strip 'daemon.' prefix (7 chars)
    real_key = key[7:]
    config['daemon'][real_key] = value
else:
    parts = key.split('.')
    if len(parts) == 2:
        button_id, button_key = parts
        if button_id not in config['buttons']:
            config['buttons'][button_id] = {}
        config['buttons'][button_id][button_key] = value
    else:
        print(f'Invalid key: {key}', file=sys.stderr)
        exit(1)

with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)

print(f'Configuration updated: {key} = {value}')
EOF
}

config_get() {
    local key="$1"
    
    local config_file="$HOME/.streamdeck/daemon.json"
    
    if [ ! -f "$config_file" ]; then
        log "No configuration file found"
        exit 1
    fi
    
    python3 << EOF
import json

with open('$config_file', 'r') as f:
    config = json.load(f)

# Get value
if '$key'.startswith('daemon.'):
    value = config['daemon'].get('$key'[7:])
elif '.' in '$key':
    parts = '$key'.split('.')
    if len(parts) == 2:
        button_id, button_key = parts
        value = config['buttons'].get(button_id, {}).get(button_key)
    else:
        print(f'Invalid key: {$key}', file=sys.stderr)
        exit(1)
else:
    print(f'Invalid key: {$key}', file=sys.stderr)
    exit(1)

if value is None:
    print(f'Key not found: {$key}', file=sys.stderr)
    exit(1)

print(value)
EOF
}

# Health check - verify services and button icons
health_check() {
    local fix_mode="${1:-}"

    log "Running Stream Deck health check..."
    echo ""

    python3 << 'HEALTH_EOF'
import json
import os
import subprocess
from pathlib import Path

issues = []
fixes = []

print("=== Stream Deck Health Check ===\n")

# 1. Check services
services = {
    'streamdeck': 'Stream Deck UI',
    'streamdeck-clock': 'Clock Widget',
    'streamdeck-weather': 'Weather Widget',
    'streamdeck-monitor': 'System Monitor',
    'streamdeck-plant-monitor': 'Plant Light Monitor',
    'streamdeck-living-room-monitor': 'Living Room Monitor'
}

print("Services:")
for svc, name in services.items():
    result = subprocess.run(['systemctl', '--user', 'is-active', f'{svc}.service'],
                           capture_output=True, text=True)
    status = result.stdout.strip()
    if status == "active":
        print(f"  [OK] {name}")
    else:
        print(f"  [FAIL] {name} ({status})")
        issues.append(f"Service {svc} is {status}")
        fixes.append(f"systemctl --user start {svc}.service")

# 2. Check config file
config_path = Path.home() / '.streamdeck_ui.json'
if not config_path.exists():
    print(f"\n[FAIL] Config file not found: {config_path}")
    issues.append("Config file missing")
else:
    with open(config_path) as f:
        config = json.load(f)

    deck_id = list(config['state'].keys())[0]

    # Expected button configurations
    expected = {
        '1': ('${HOME}/workspace/streamdeck/icon/screen_sleep.png', 'Screen Sleep'),
        '7': ('/tmp/streamdeck_clock_icon', 'Clock (dynamic)'),
        '15': ('/tmp/streamdeck_weather_icon', 'Weather (dynamic)'),
    }

    print("\nKey Buttons:")
    for btn_num, (expected_path, name) in expected.items():
        btn_data = config['state'][deck_id]['buttons']['0'].get(btn_num, {})
        states = btn_data.get('states', {})
        actual = states.get('0', {}).get('icon', 'NOT SET')

        # Check if icon matches expected (for dynamic, just check prefix)
        if expected_path.startswith('/tmp/'):
            ok = actual.startswith(expected_path)
        else:
            ok = actual == expected_path

        if ok:
            print(f"  [OK] Button {btn_num} ({name})")
        else:
            print(f"  [FAIL] Button {btn_num} ({name})")
            print(f"         Expected: {expected_path}")
            print(f"         Actual:   {actual}")
            issues.append(f"Button {btn_num} has wrong icon")
            fixes.append(f"fix_button:{btn_num}:{expected_path}")

# 3. Check dynamic icon files exist
print("\nDynamic Icons:")
dynamic_icons = [
    '/tmp/streamdeck_clock_icon_0.png',
    '/tmp/streamdeck_clock_icon_1.png',
    '/tmp/streamdeck_weather_icon_0.png'
]
for icon in dynamic_icons:
    if os.path.exists(icon):
        print(f"  [OK] {icon.split('/')[-1]}")
    else:
        print(f"  [FAIL] {icon.split('/')[-1]} missing")
        issues.append(f"Dynamic icon missing: {icon}")

# Summary
print("\n" + "="*40)
if issues:
    print(f"ISSUES FOUND: {len(issues)}")
    for issue in issues:
        print(f"  - {issue}")
    print(f"\nRun './run.sh fix' to auto-repair")
    exit(1)
else:
    print("ALL CHECKS PASSED")
    exit(0)
HEALTH_EOF
}

# Fix - auto-repair button configuration
fix_buttons() {
    log "Auto-fixing Stream Deck configuration..."
    echo ""

    # CRITICAL: The streamdeck service writes its in-memory state to disk on shutdown!
    # We must stop ALL services, wait for them to fully stop, then edit config.
    log "Step 1: Stopping ALL streamdeck services..."
    systemctl --user stop streamdeck-clock.service streamdeck-weather.service 2>/dev/null
    sleep 1
    systemctl --user stop streamdeck.service
    sleep 2  # Wait for service to fully stop and write state

    log "Step 2: Fixing button configuration..."
    python3 << 'FIX_EOF'
import json
import shutil
from pathlib import Path

config_path = Path.home() / '.streamdeck_ui.json'
backup_path = Path.home() / '.streamdeck_ui.json.backup'

# Check if backup has correct values - if so, restore from it
restore_from_backup = False
if backup_path.exists():
    try:
        with open(backup_path) as f:
            backup_config = json.load(f)
        deck_id = list(backup_config['state'].keys())[0]
        btn1_backup = backup_config['state'][deck_id]['buttons']['0']['1']['states']['0'].get('icon', '')
        if 'screen_sleep' in btn1_backup:
            print("  Backup has correct values - restoring from backup")
            shutil.copy(backup_path, config_path)
            restore_from_backup = True
    except Exception as e:
        print(f"  Could not check backup: {e}")

if not restore_from_backup:
    # Manual fix
    with open(config_path) as f:
        config = json.load(f)

    deck_id = list(config['state'].keys())[0]

    fixes = {
        '1': '${HOME}/workspace/streamdeck/icon/screen_sleep.png',
        '15': '/tmp/streamdeck_weather_icon_0.png',
    }

    for btn_num, icon_path in fixes.items():
        if btn_num in config['state'][deck_id]['buttons']['0']:
            old_icon = config['state'][deck_id]['buttons']['0'][btn_num]['states']['0'].get('icon', '')
            config['state'][deck_id]['buttons']['0'][btn_num]['states']['0']['icon'] = icon_path
            print(f"  Fixed button {btn_num}: {old_icon.split('/')[-1]} -> {icon_path.split('/')[-1]}")

    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)

# Always update backup with known-good config
print("  Updating backup with fixed config...")
shutil.copy(config_path, backup_path)
print("  Config saved and backed up")
FIX_EOF

    log "Step 3: Starting streamdeck.service (waiting for full init)..."
    systemctl --user start streamdeck.service
    sleep 3  # Longer wait for full initialization

    log "Step 4: Restarting dynamic icon services..."
    systemctl --user restart streamdeck-clock.service streamdeck-weather.service
    sleep 2

    log "Step 5: Verifying fix..."
    echo ""
    health_check
}

# Main command dispatcher
case "$COMMAND" in
    # Daemon commands
    daemon)
        case "${2:-}" in
            start)
                daemon_start "${3:-}"
                ;;
            stop)
                daemon_stop
                ;;
            restart)
                daemon_restart
                ;;
            status)
                daemon_status
                ;;
            logs)
                daemon_logs
                ;;
            *)
                error "Unknown daemon command: ${2:-}"
                show_help
                exit 1
                ;;
        esac
        ;;
    
    # Button commands
    button)
        case "${2:-}" in
            list-buttons)
                button_list
                ;;
            button-info)
                if [ -z "${3:-}" ]; then
                    error "Button ID required"
                    exit 1
                fi
                button_info "$3"
                ;;
            *)
                if [ -z "${2:-}" ]; then
                    error "Button ID required"
                    exit 1
                fi
                button_execute "$2" "$3"
                ;;
        esac
        ;;
    
    # Status commands
    status)
        status_show "${2:-}"
        ;;
    
    # Config commands
    config)
        case "${2:-}" in
            "")
                config_show
                ;;
            set|--set)
                if [ -z "${3:-}" ] || [ -z "${4:-}" ]; then
                    error "Key and value required"
                    exit 1
                fi
                config_set "$3" "$4"
                ;;
            get|--get)
                if [ -z "${3:-}" ]; then
                    error "Key required"
                    exit 1
                fi
                config_get "$3"
                ;;
            *)
                error "Unknown config command: ${2:-}"
                show_help
                exit 1
                ;;
        esac
        ;;
    
    # Health check
    health-check|health|check)
        health_check
        ;;

    # Fix buttons
    fix|repair)
        fix_buttons
        ;;

    # Agent D-Bus commands
    agent)
        case "${2:-}" in
            ask)
                if [ -z "${3:-}" ]; then
                    error "Prompt required: $0 agent ask 'your prompt'"
                    exit 1
                fi
                log "Asking agent via D-Bus..."
                busctl --user --timeout=120000000 call org.embry.Agent /org/embry/Agent org.embry.Agent Ask s "$3" 2>&1 || {
                    error "D-Bus agent not available. Is embry-agent.service running?"
                    exit 1
                }
                ;;
            ping)
                busctl --user call org.embry.Agent /org/embry/Agent org.embry.Agent Ping 2>&1 || {
                    error "D-Bus agent not available"
                    exit 1
                }
                ;;
            state)
                busctl --user call org.embry.Agent /org/embry/Agent org.embry.Agent GetState 2>&1 || {
                    error "D-Bus agent not available"
                    exit 1
                }
                ;;
            abort)
                busctl --user call org.embry.Agent /org/embry/Agent org.embry.Agent Abort 2>&1 || {
                    error "D-Bus agent not available"
                    exit 1
                }
                ;;
            *)
                error "Unknown agent command: ${2:-}"
                echo "Available: ask, ping, state, abort"
                exit 1
                ;;
        esac
        ;;

    # Default
    help|--help|-h)
        show_help
        ;;

    *)
        error "Unknown command: $COMMAND"
        show_help
        exit 1
        ;;
esac

exit 0
