#!/bin/bash
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
    status           Status query commands
    config           Configuration commands
    help             Show this help message

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

# Daemon management
daemon_start() {
    local foreground="${1:-}"
    
    log "Starting streamdeck daemon..."
    
    # Build command
    local cmd="uvx --from \"git+https://github.com/grahama1970/streamdeck.git@main\" streamdeck-daemon"
    
    if [ "$foreground" = "--foreground" ]; then
        log "Running in foreground mode..."
        $cmd "$@"
    else
        log "Running in background mode..."
        nohup $cmd "$@" > /dev/null 2>&1 &
        sleep 1
        
        # Check if started
        if $0 daemon status &> /dev/null; then
            log "Daemon started successfully"
        else
            error "Failed to start daemon"
            exit 1
        fi
    fi
}

daemon_stop() {
    log "Stopping streamdeck daemon..."
    
    # Use API to stop daemon
    local port="${STREAMDECK_DAEMON_PORT:-48970}"
    local host="${STREAMDECK_DAEMON_HOST:-127.0.0.1}"
    
    curl -s -X POST "http://${host}:${port}/stop" > /dev/null 2>&1
    
    sleep 1
    
    if ! $0 daemon status &> /dev/null; then
        log "Daemon stopped successfully"
    else
        error "Failed to stop daemon"
        exit 1
    fi
}

daemon_restart() {
    log "Restarting streamdeck daemon..."
    $0 daemon stop
    sleep 1
    $0 daemon start
}

daemon_status() {
    local port="${STREAMDECK_DAEMON_PORT:-48970}"
    local host="${STREAMDECK_DAEMON_HOST:-127.0.0.1}"
    
    local response=$(curl -s "http://${host}:${port}/status" 2>/dev/null)
    
    if [ -n "$response" ]; then
        echo "$response" | python3 -m json.tool
    else
        log "Daemon is not running"
        return 1
    fi
}

daemon_logs() {
    local log_file="$HOME/.streamdeck/daemon.log"
    
    if [ -f "$log_file" ]; then
        log "Showing last 50 lines of daemon log:"
        tail -n 50 "$log_file"
    else
        log "No log file found at: $log_file"
    fi
}

# Button operations
button_execute() {
    local button_id="$1"
    local hold="${2:-}"
    
    log "Executing button: $button_id"
    
    local port="${STREAMDECK_DAEMON_PORT:-48970}"
    local host="${STREAMDECK_DAEMON_HOST:-127.0.0.1}"
    
    local endpoint="http://${host}:${port}/buttons/${button_id}"
    
    if [ "$hold" = "--hold" ]; then
        endpoint="${endpoint}/hold"
        log "Executing long-press event"
    fi
    
    local response=$(curl -s -X POST "$endpoint" 2>/dev/null)
    
    if [ -n "$response" ]; then
        log "Button executed successfully"
    else
        error "Failed to execute button"
        exit 1
    fi
}

button_list() {
    log "Listing available buttons..."
    
    local port="${STREAMDECK_DAEMON_PORT:-48970}"
    local host="${STREAMDECK_DAEMON_HOST:-127.0.0.1}"
    
    curl -s "http://${host}:${port}/buttons" | python3 -m json.tool
}

button_info() {
    local button_id="$1"
    
    log "Getting info for button: $button_id"
    
    local port="${STREAMDECK_DAEMON_PORT:-48970}"
    local host="${STREAMDECK_DAEMON_HOST:-127.0.0.1}"
    
    curl -s "http://${host}:${port}/buttons/${button_id}" | python3 -m json.tool
}

# Status queries
status_show() {
    local json="${1:-}"
    
    local port="${STREAMDECK_DAEMON_PORT:-48970}"
    local host="${STREAMDECK_DAEMON_HOST:-127.0.0.1}"
    
    local url="http://${host}:${port}/status"
    
    if [ "$json" = "--json" ]; then
        url="${url}?format=json"
    elif [ "$json" = "--buttons" ]; then
        url="${url}?buttons=true"
    fi
    
    curl -s "$url" | python3 -m json.tool
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
    python3 << EOF
import json

with open('$config_file', 'r') as f:
    config = json.load(f)

# Set value
if '$key'.startswith('daemon.'):
    config['daemon']['$key'] = $value
else:
    parts = '$key'.split('.')
    if len(parts) == 2:
        button_id, button_key = parts
        if button_id not in config['buttons']:
            config['buttons'][button_id] = {}
        config['buttons'][button_id][button_key] = $value
    else:
        print(f'Invalid key: {$key}', file=sys.stderr)
        exit(1)

with open('$config_file', 'w') as f:
    json.dump(config, f, indent=2)

print(f'Configuration updated: {$key} = {$value}')
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

if value is not None:
    print(f'Key not found: {$key}', file=sys.stderr)
    exit(1)

print(value)
EOF
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
            set)
                if [ -z "${3:-}" ] || [ -z "${4:-}" ]; then
                    error "Key and value required"
                    exit 1
                fi
                config_set "$3" "$4"
                ;;
            get)
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
