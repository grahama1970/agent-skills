#!/bin/bash
# Surf - Unified browser automation for AI agents
# Single entry point for ALL Chrome/browser interactions
#
# Usage:
#   surf cdp start [port]     # Start Chrome with CDP
#   surf cdp stop             # Stop Chrome CDP
#   surf cdp status           # Check CDP status
#   surf cdp env              # Output export commands for shells
#   surf go "https://..."     # Navigate (via surf-cli)
#   surf read                 # Read page content
#   surf click e5             # Click element
#   surf snap                 # Screenshot

set -e

CDP_PORT="${CDP_PORT:-9222}"
CHROME_USER_DATA="${CHROME_USER_DATA:-/tmp/chrome-cdp-profile}"
CDP_PID_FILE="/tmp/chrome-cdp.pid"
REPO="github:nicobailon/surf-cli"

# Resolve skill directory (for relative paths)
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ─────────────────────────────────────────────────────────────
# Chrome Detection
# ─────────────────────────────────────────────────────────────
find_chrome() {
    for cmd in google-chrome google-chrome-stable chromium chromium-browser; do
        if command -v "$cmd" &> /dev/null; then
            echo "$cmd"
            return 0
        fi
    done
    # macOS
    if [[ -x "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" ]]; then
        echo "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        return 0
    fi
    return 1
}

# ─────────────────────────────────────────────────────────────
# CDP Management
# ─────────────────────────────────────────────────────────────
cdp_start() {
    local port="${1:-$CDP_PORT}"

    # Check if already running
    if curl -s "http://127.0.0.1:${port}/json/version" &>/dev/null; then
        echo "Chrome CDP already running on port ${port}"
        cdp_status "$port"
        return 0
    fi

    local chrome
    chrome=$(find_chrome) || {
        echo "Error: Chrome not found. Install Google Chrome or Chromium." >&2
        return 1
    }

    echo "Starting Chrome with CDP on port ${port}..."

    # Create profile directory
    mkdir -p "$CHROME_USER_DATA"

    # Start Chrome with CDP flags
    "$chrome" \
        --remote-debugging-port="$port" \
        --user-data-dir="$CHROME_USER_DATA" \
        --no-first-run \
        --no-default-browser-check \
        --disable-background-networking \
        --disable-client-side-phishing-detection \
        --disable-default-apps \
        --disable-extensions \
        --disable-hang-monitor \
        --disable-popup-blocking \
        --disable-prompt-on-repost \
        --disable-sync \
        --disable-translate \
        --metrics-recording-only \
        --safebrowsing-disable-auto-update \
        --window-size=1280,900 \
        "about:blank" &>/dev/null &

    local pid=$!
    echo "$pid" > "$CDP_PID_FILE"
    echo "$port" > "${CDP_PID_FILE}.port"

    # Wait for CDP endpoint
    echo -n "Waiting for CDP..."
    for i in {1..30}; do
        if curl -s "http://127.0.0.1:${port}/json/version" &>/dev/null; then
            echo " ready!"
            echo ""
            cdp_status "$port"
            return 0
        fi
        echo -n "."
        sleep 0.5
    done

    echo ""
    echo "Error: Chrome CDP did not start within 15 seconds" >&2
    kill "$pid" 2>/dev/null || true
    rm -f "$CDP_PID_FILE" "${CDP_PID_FILE}.port"
    return 1
}

cdp_stop() {
    if [[ -f "$CDP_PID_FILE" ]]; then
        local pid
        pid=$(cat "$CDP_PID_FILE")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null
            echo "Chrome CDP stopped (PID: $pid)"
        else
            echo "Chrome CDP process not running (stale PID file)"
        fi
        rm -f "$CDP_PID_FILE" "${CDP_PID_FILE}.port"
    else
        # Fallback: kill any Chrome with remote-debugging
        if pkill -f "remote-debugging-port" 2>/dev/null; then
            echo "Chrome CDP stopped (found via process name)"
        else
            echo "No Chrome CDP process found"
        fi
    fi
}

cdp_status() {
    local port="${1:-$CDP_PORT}"

    # Try to read port from saved file
    if [[ -z "$1" && -f "${CDP_PID_FILE}.port" ]]; then
        port=$(cat "${CDP_PID_FILE}.port")
    fi

    if curl -s "http://127.0.0.1:${port}/json/version" &>/dev/null; then
        local version
        version=$(curl -s "http://127.0.0.1:${port}/json/version")
        local browser ws
        browser=$(echo "$version" | grep -oP '"Browser":\s*"\K[^"]+' || echo "unknown")
        ws=$(echo "$version" | grep -oP '"webSocketDebuggerUrl":\s*"\K[^"]+' || echo "unknown")

        echo "Chrome CDP Status: RUNNING"
        echo "  Port: ${port}"
        echo "  Browser: ${browser}"
        echo "  WebSocket: ${ws}"
        if [[ -f "$CDP_PID_FILE" ]]; then
            echo "  PID: $(cat "$CDP_PID_FILE")"
        fi
        echo ""
        echo "Environment variables for tests:"
        echo "  export BROWSERLESS_DISCOVERY_URL=http://127.0.0.1:${port}/json/version"
        echo "  export BROWSERLESS_WS=${ws}"
        return 0
    else
        echo "Chrome CDP Status: NOT RUNNING"
        echo "  Run: surf cdp start"
        return 1
    fi
}

cdp_env() {
    local port="${1:-$CDP_PORT}"

    # Try to read port from saved file
    if [[ -z "$1" && -f "${CDP_PID_FILE}.port" ]]; then
        port=$(cat "${CDP_PID_FILE}.port")
    fi

    if curl -s "http://127.0.0.1:${port}/json/version" &>/dev/null; then
        local ws
        ws=$(curl -s "http://127.0.0.1:${port}/json/version" | grep -oP '"webSocketDebuggerUrl":\s*"\K[^"]+' || echo "")
        echo "export BROWSERLESS_DISCOVERY_URL=http://127.0.0.1:${port}/json/version"
        if [[ -n "$ws" ]]; then
            echo "export BROWSERLESS_WS=${ws}"
        fi
        echo "export CDP_PORT=${port}"
    else
        echo "# Chrome CDP not running - start with: surf cdp start" >&2
        return 1
    fi
}

cdp_test() {
    local port="${1:-$CDP_PORT}"
    local url="${2:-https://example.com}"

    # Try to read port from saved file
    if [[ -z "$1" && -f "${CDP_PID_FILE}.port" ]]; then
        port=$(cat "${CDP_PID_FILE}.port")
    fi

    echo "Testing CDP connection on port ${port}..."

    # 1. Check CDP endpoint
    if ! curl -s "http://127.0.0.1:${port}/json/version" &>/dev/null; then
        echo "FAIL: CDP endpoint not responding"
        echo "  Run: surf cdp start"
        return 1
    fi
    echo "  [1/4] CDP endpoint: OK"

    # 2. List tabs
    local tabs
    tabs=$(curl -s "http://127.0.0.1:${port}/json/list" 2>/dev/null)
    if [[ -z "$tabs" ]]; then
        echo "FAIL: Cannot list tabs"
        return 1
    fi
    local tab_count
    tab_count=$(echo "$tabs" | grep -c '"id"' || echo "0")
    echo "  [2/4] Tab listing: OK ($tab_count tabs)"

    # 3. Open new tab with test URL
    echo "  [3/4] Opening test page: $url"
    local new_tab
    new_tab=$(curl -s "http://127.0.0.1:${port}/json/new?${url}" 2>/dev/null)
    if echo "$new_tab" | grep -q '"id"'; then
        local tab_id
        tab_id=$(echo "$new_tab" | grep -oP '"id":\s*"\K[^"]+' | head -1)
        echo "        Tab created: $tab_id"
        sleep 1
        # Close the test tab
        curl -s "http://127.0.0.1:${port}/json/close/${tab_id}" &>/dev/null
        echo "  [4/4] Tab lifecycle: OK (created and closed)"
    else
        echo "  [4/4] Tab lifecycle: SKIP (could not create tab)"
    fi

    echo ""
    echo "CDP test passed! Ready for Puppeteer/testing."
}

cdp_help() {
    echo "surf cdp - Chrome DevTools Protocol management"
    echo ""
    echo "Commands:"
    echo "  start [port]  Start Chrome with CDP (default: 9222)"
    echo "  stop          Stop Chrome CDP"
    echo "  status        Show CDP status and connection info"
    echo "  env           Output export commands for shell (use with eval)"
    echo "  test [url]    Test CDP by opening a page (default: example.com)"
    echo ""
    echo "Examples:"
    echo "  surf cdp start"
    echo "  surf cdp status"
    echo "  surf cdp test"
    echo "  eval \"\$(surf cdp env)\"  # Set env vars"
    echo "  surf cdp stop"
}

# ─────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────

# Handle CDP subcommands
if [[ "$1" == "cdp" ]]; then
    case "$2" in
        start)  cdp_start "$3" ;;
        stop)   cdp_stop ;;
        status) cdp_status "$3" ;;
        env)    cdp_env "$3" ;;
        test)   cdp_test "$3" "$4" ;;
        *)      cdp_help ;;
    esac
    exit $?
fi

# Handle help
if [[ "$1" == "--help" || "$1" == "-h" || -z "$1" ]]; then
    echo "surf - Unified browser automation for AI agents"
    echo ""
    echo "CDP Management:"
    echo "  surf cdp start [port]   Start Chrome with CDP"
    echo "  surf cdp stop           Stop Chrome CDP"
    echo "  surf cdp status         Show CDP status"
    echo "  surf cdp env            Output export commands"
    echo ""
    echo "Browser Automation (via surf-cli):"
    echo "  surf go <url>           Navigate to URL"
    echo "  surf read               Read page content"
    echo "  surf click <ref>        Click element (e.g., e5)"
    echo "  surf type <text>        Type text"
    echo "  surf snap               Take screenshot"
    echo "  surf tab.list           List tabs"
    echo "  surf js <code>          Execute JavaScript"
    echo ""
    echo "See: surf cdp --help, or npx github:nicobailon/surf-cli --help"
    exit 0
fi

# Pass through to surf-cli for all other commands
if command -v npx &> /dev/null; then
    exec npx "$REPO" "$@"
elif command -v surf &> /dev/null; then
    exec surf "$@"
else
    echo "Error: Neither npx nor surf-cli found" >&2
    echo "Install Node.js: https://nodejs.org/" >&2
    exit 1
fi
