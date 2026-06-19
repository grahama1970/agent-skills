#!/bin/bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Surf - Unified browser automation for AI agents
# Single entry point for ALL Chrome/browser interactions
#
# Usage:
#   surf cdp start [port] [--headless]  # Start Chrome with CDP
#   surf cdp stop             # Stop Chrome CDP
#   surf cdp status           # Check CDP status
#   surf cdp env              # Output export commands for shells
#   surf go "https://..."     # Navigate (via surf-cli)
#   surf read                 # Read page content
#   surf click e5             # Click element
#   surf snap                 # Screenshot

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$SCRIPT_DIR"

# Surf doesn't need project .env — only CDP_PORT and CHROME_USER_DATA
# which have sane defaults below

CDP_PORT="${CDP_PORT:-9222}"
CHROME_USER_DATA="${CHROME_USER_DATA:-/tmp/chrome-cdp-profile}"
CDP_PID_FILE="/tmp/chrome-cdp.pid"
# Vendored surf-cli lives under vendor/surf-cli (override with SURF_CLI_PATH).
# shellcheck source=scripts/lib/surf-cli-path.sh
source "${SKILL_DIR}/scripts/lib/surf-cli-path.sh"
# shellcheck source=scripts/lib/webgpt_singleflight.sh
source "${SKILL_DIR}/scripts/lib/webgpt_singleflight.sh"

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
    local headless="${2:-}"

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

    if [[ "$headless" == "headless" ]]; then
        echo "Starting Chrome (headless) with CDP on port ${port}..."
    else
        echo "Starting Chrome with CDP on port ${port}..."
    fi

    # Create profile directory
    mkdir -p "$CHROME_USER_DATA"

    # Note: Google Chrome blocks --load-extension for security.
    # Extension must be loaded manually via chrome://extensions
    # See SKILL.md "Advanced: surf-cli Extension" section.

    # Build Chrome flags
    local -a chrome_flags=(
        --remote-debugging-port="$port"
        --remote-allow-origins=*
        --user-data-dir="$CHROME_USER_DATA"
        --no-first-run
        --no-default-browser-check
        --disable-background-networking
        --disable-client-side-phishing-detection
        --disable-default-apps
        --disable-hang-monitor
        --disable-popup-blocking
        --disable-prompt-on-repost
        --disable-sync
        --disable-translate
        --metrics-recording-only
        --safebrowsing-disable-auto-update
        --window-size=1280,900
    )

    # Add headless flag if requested
    if [[ "$headless" == "headless" ]]; then
        chrome_flags+=(--headless=new)
    fi

    # Start Chrome with CDP flags
    "$chrome" "${chrome_flags[@]}" "about:blank" &>/dev/null &

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

cdp_go() {
    local url="$1"
    local port="${2:-$CDP_PORT}"

    if [[ -z "$url" ]]; then
        echo "Usage: surf cdp go <url>" >&2
        return 1
    fi

    # Get page websocket
    local ws_url
    ws_url=$(curl -s "http://127.0.0.1:${port}/json/list" | uv run --project "$SCRIPT_DIR" python3 -c "
import json, sys
data = json.load(sys.stdin)
pages = [d for d in data if d.get('type') == 'page']
if pages:
    print(pages[0]['webSocketDebuggerUrl'])
" 2>/dev/null)

    if [[ -z "$ws_url" ]]; then
        echo "Error: No browser page found. Run 'surf cdp start' first." >&2
        return 1
    fi

    uv run --project "$SCRIPT_DIR" python3 << PYEOF
import json
import time
import websocket

ws = websocket.create_connection("$ws_url")
ws.send(json.dumps({'id': 1, 'method': 'Page.navigate', 'params': {'url': '$url'}}))
result = json.loads(ws.recv())
print(f"Navigated to: $url")
time.sleep(2)  # Wait for load
ws.close()
PYEOF
}

cdp_read() {
    local port="${1:-$CDP_PORT}"

    # Get page websocket
    local ws_url
    ws_url=$(curl -s "http://127.0.0.1:${port}/json/list" | uv run --project "$SCRIPT_DIR" python3 -c "
import json, sys
data = json.load(sys.stdin)
pages = [d for d in data if d.get('type') == 'page']
if pages:
    print(pages[0]['webSocketDebuggerUrl'])
" 2>/dev/null)

    if [[ -z "$ws_url" ]]; then
        echo "Error: No browser page found. Run 'surf cdp start' first." >&2
        return 1
    fi

    uv run --project "$SCRIPT_DIR" python3 << PYEOF
import json
import websocket

ws = websocket.create_connection("$ws_url")
ws.send(json.dumps({
    'id': 1,
    'method': 'Runtime.evaluate',
    'params': {'expression': 'document.body.innerText'}
}))
result = json.loads(ws.recv())
text = result.get('result', {}).get('result', {}).get('value', '')
ws.close()
print(text)
PYEOF
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
    echo "  go <url>      Navigate to URL (CDP fallback, no extension needed)"
    echo "  read          Read page text content (CDP fallback)"
    echo ""
    echo "Examples:"
    echo "  surf cdp start"
    echo "  surf cdp go https://example.com"
    echo "  surf cdp read"
    echo "  surf cdp status"
    echo "  eval \"\$(surf cdp env)\"  # Set env vars"
    echo "  surf cdp stop"
}

# ─────────────────────────────────────────────────────────────
# CDP Controller (Python-based, no extension required)
# ─────────────────────────────────────────────────────────────
CDP_CONTROLLER="$SKILL_DIR/cdp_controller.py"

run_cdp_controller() {
    local port="${CDP_PORT:-9222}"
    if [[ -f "${CDP_PID_FILE}.port" ]]; then
        port=$(cat "${CDP_PID_FILE}.port")
    fi
    CDP_PORT="$port" uv run --project "$SCRIPT_DIR" python3 "$CDP_CONTROLLER" "$@"
}

# Check if surf-cli socket is available
surf_cli_available() {
    [[ -S "/tmp/surf.sock" ]]
}

# ─────────────────────────────────────────────────────────────
# Main Entry Point
# ─────────────────────────────────────────────────────────────

# Handle CDP subcommands
if [[ "$1" == "cdp" ]]; then
    case "$2" in
        start)
            # Parse: surf cdp start [--headless] [port] or [port] [--headless]
            _port=""
            _headless=""
            for arg in "${@:3}"; do
                if [[ "$arg" == "--headless" ]]; then
                    _headless="headless"
                elif [[ "$arg" =~ ^[0-9]+$ ]]; then
                    _port="$arg"
                fi
            done
            cdp_start "${_port:-$CDP_PORT}" "$_headless"
            ;;
        stop)   cdp_stop ;;
        status) cdp_status "$3" ;;
        env)    cdp_env "$3" ;;
        test)   cdp_test "$3" "$4" ;;
        go)     cdp_go "$3" "$4" ;;
        read)   cdp_read "$3" ;;
        *)      cdp_help ;;
    esac
    exit $?
fi

# Handle setup/sanity check
if [[ "$1" == "setup" || "$1" == "sanity" || "$1" == "doctor" ]]; then
    "$SKILL_DIR/scripts/ensure-surf-cli.sh" || true
    if [[ "${2:-}" == "webgpt" ]]; then
        exec "$SKILL_DIR/scripts/webgpt-sanity.sh" "${@:3}"
    fi
    if [[ "${2:-}" == "web" ]]; then
        exec "$SKILL_DIR/scripts/web-oracles-sanity.sh" "${@:3}"
    fi
    exec "$SKILL_DIR/sanity.sh" "${@:2}"
fi

if [[ "$1" == "extension.build" ]]; then
    exec "$SKILL_DIR/scripts/ensure-surf-cli.sh" "${@:2}"
fi

# Higher-level WebGPT handoff helpers. These intentionally live in the skill
# wrapper because they own file artifacts and completion proof, while surf-cli
# owns browser mechanics.
if [[ "$1" == "extension.reload" ]]; then
    exec "$SKILL_DIR/scripts/extension-reload.sh" "${@:2}"
fi

if [[ "$1" == "extension.fresh" ]]; then
    exec "$SKILL_DIR/scripts/extension-fresh.sh" "${@:2}"
fi

if [[ "$1" == "vendor.sync" ]]; then
    exec "$SKILL_DIR/scripts/vendor-sync.sh" "${@:2}"
fi

if [[ "$1" == "vendor.status" ]]; then
    exec "$SKILL_DIR/scripts/vendor-status.sh" "${@:2}"
fi

if [[ "$1" == "webgpt.submit" ]]; then
    exec "$SKILL_DIR/scripts/webgpt-submit.sh" "${@:2}"
fi

if [[ "$1" == "gemini.submit" ]]; then
    exec "$SKILL_DIR/scripts/gemini-submit.sh" "${@:2}"
fi

if [[ "$1" == "kimi.submit" ]]; then
    exec "$SKILL_DIR/scripts/kimi-submit.sh" "${@:2}"
fi

if [[ "$1" == "webgpt.extract" ]]; then
    exec "$SKILL_DIR/scripts/webgpt-extract.sh" "${@:2}"
fi

if [[ "$1" == "webgpt.sanity" ]]; then
    exec "$SKILL_DIR/scripts/webgpt-sanity.sh" "${@:2}"
fi

if [[ "$1" == "webgpt.e2e-sanity" ]]; then
    exec "$SKILL_DIR/scripts/webgpt-e2e-sanity.sh" "${@:2}"
fi

if [[ "$1" == "cursor-browser.submit" ]]; then
    exec "$SKILL_DIR/scripts/cursor-browser-submit.sh" "${@:2}"
fi

if [[ "$1" == "cursor-browser.tab.list" ]]; then
    export PYTHONPATH="$SKILL_DIR/scripts${PYTHONPATH:+:$PYTHONPATH}"
    exec python3 "$SKILL_DIR/scripts/cursor_browser_client.py" tab.list "${@:2}"
fi

if [[ "$1" == "webgpt.tab-id-background-sanity" ]]; then
    exec "$SKILL_DIR/scripts/webgpt-tab-id-background-sanity.sh" "${@:2}"
fi

if [[ "$1" == "webgpt.no-activate-sanity" ]]; then
    exec "$SKILL_DIR/scripts/webgpt-no-activate-sanity.sh" "${@:2}"
fi

if [[ "$1" == "webgpt.preflight" ]]; then
    exec "$SKILL_DIR/scripts/webgpt-preflight.sh" "${@:2}"
fi

if [[ "$1" == "webgpt.roundtrip-preflight" ]]; then
    exec "$SKILL_DIR/scripts/webgpt-roundtrip-preflight.sh" "${@:2}"
fi

if [[ "$1" == "kde.spaces" ]]; then
    exec python3 "$SKILL_DIR/scripts/kde_spaces.py" inventory "${@:2}"
fi

if [[ "$1" == "kde.helper" ]]; then
    exec python3 "$SKILL_DIR/scripts/kde_spaces.py" serve "${@:2}"
fi

if [[ "$1" == "kde.helper.health" ]]; then
    exec python3 "$SKILL_DIR/scripts/kde_spaces.py" health "${@:2}"
fi

# Handle help
if [[ "$1" == "--help" || "$1" == "-h" || -z "$1" ]]; then
    echo "surf - Unified browser automation for AI agents"
    echo ""
    echo "Setup:"
    echo "  surf setup              Check setup status & show install instructions"
    echo "  surf extension.build    Build vendored surf-cli (npm ci && npm run build)"
    echo "  surf extension.reload   Reload Chrome extension after build"
    echo "  surf extension.fresh    Check whether dist matches source"
    echo "  surf vendor.sync        Sync vendor/surf-cli from Embry fork"
    echo "  surf vendor.status      Show vendored commit + dist freshness"
    echo "  surf install <ext-id>   Install native host for extension"
    echo ""
    echo "Tab Management (requires extension):"
    echo "  surf tab.list           List all browser tabs"
    echo "  surf tab.new <url>      Open new tab"
    echo "  surf tab.activate <id>  Switch to tab"
    echo ""
    echo "Browser Automation:"
    echo "  surf go <url>           Navigate to URL"
    echo "  surf read               Read page with element refs (e1, e2...)"
    echo "  surf click <ref|selector> Click element by ref (e5) or CSS selector"
    echo "  surf type <text>        Type text (--ref <ref> to target element)"
    echo "  surf key <key>          Press key (Enter, Tab, Escape...)"
    echo "  surf snap               Take screenshot (--full for full page)"
    echo "  surf snap-container <selector>  Stitch a nested scroll container screenshot"
    echo "  surf scroll <dir>       Scroll (up/down/top/bottom)"
    echo "  surf wait <seconds>     Wait"
    echo "  surf text               Get page text content"
    echo ""
    echo "WebGPT Handoff:"
    echo "  surf webgpt.submit --input request.md --output response.md"
    echo "  surf webgpt.extract --tab-id ID --output response.md"
    echo "  surf webgpt.sanity      Run a real sentinel round-trip smoke"
    echo "  surf webgpt.e2e-sanity  Fail-closed WebGPT transport sanity matrix"
    echo "  surf webgpt.tab-id-background-sanity [--tab-id|--url]  Fast tab-id + focus proof"
    echo "  surf webgpt.no-activate-sanity --tab-id ID|--url URL  Full sentinel + background proof"
    echo "  surf webgpt.preflight --tab-id ID [--no-activate]  Pre-submit tab/focus checks"
    echo ""
    echo "KDE Workspace Tracking:"
    echo "  surf kde.spaces        Inventory KDE desktops/windows (helper-first)"
    echo "  surf kde.helper        Serve KDE desktop/window metadata from the desktop session"
    echo "  surf kde.helper.health Check the local KDE helper"
    echo ""
    echo "CDP Fallback (when extension not available):"
    echo "  surf cdp start [port] [--headless]  Start Chrome with CDP"
    echo "  surf cdp stop           Stop Chrome CDP"
    echo "  surf cdp status         Show CDP status"
    echo ""
    echo "Run 'surf setup' first to verify installation."
    exit 0
fi

# ─────────────────────────────────────────────────────────────
# Command Routing: surf-cli (extension) preferred, CDP fallback
# ─────────────────────────────────────────────────────────────

LOCAL_FORK_PATH="$SURF_CLI_PATH"
LOCAL_CLI="${LOCAL_FORK_PATH}/native/cli.cjs"

if [[ "$1" == "tab.list" ]]; then
    _with_kde=0
    _want_json=0
    _args=()
    for _arg in "$@"; do
        if [[ "$_arg" == "--with-kde" ]]; then
            _with_kde=1
            continue
        fi
        if [[ "$_arg" == "--json" ]]; then
            _want_json=1
        fi
        _args+=("$_arg")
    done
    if [[ "$_with_kde" == "1" ]]; then
        if ! surf_cli_available; then
            echo "Error: tab.list --with-kde requires surf-cli extension." >&2
            exit 1
        fi
        if [[ ! -f "$LOCAL_CLI" ]]; then
            echo "Error: surf-cli socket present but CLI missing at $LOCAL_CLI" >&2
            exit 1
        fi
        _json="$(node "$LOCAL_CLI" "${_args[@]}" --json)"
        _annotated="$(printf '%s' "$_json" | python3 "$SKILL_DIR/scripts/kde_spaces.py" annotate-tabs)"
        if [[ "$_want_json" == "1" ]]; then
            printf '%s\n' "$_annotated"
        else
            printf '%s\n' "$_annotated" | python3 -c 'import json,sys
data=json.load(sys.stdin)
for tab in data.get("tabs", []):
    kde=tab.get("kde", {})
    print(f"{tab.get(\"id\", \"\")}\t{tab.get(\"title\", \"\")}\t{tab.get(\"url\", \"\")}\twindow={tab.get(\"windowId\", \"\")}\tdesktop={kde.get(\"desktop_index\")}")'
        fi
        exit 0
    fi
fi

# If surf-cli socket is available, route ALL commands through it
if surf_cli_available; then
    if [[ -f "$LOCAL_CLI" ]]; then
        "$SKILL_DIR/scripts/ensure-surf-cli.sh"
        if [[ "${1:-}" == "chatgpt" && "${SURF_WEBGPT_LOCK_HELD:-0}" != "1" ]]; then
            if ! surf_webgpt_acquire_lock "surf chatgpt $*"; then
                echo "surf chatgpt refused concurrent ChatGPT submit; lock is held: $(surf_webgpt_lock_file)" >&2
                echo "Use surf webgpt.submit artifacts, wait for the active submit, or set SURF_WEBGPT_LOCK_TIMEOUT to a bounded wait." >&2
                exit 73
            fi
        fi
        exec node "$LOCAL_CLI" "$@"
    fi
    echo "Error: surf-cli socket present but CLI missing at $LOCAL_CLI" >&2
    echo "Run: surf setup" >&2
    exit 1
fi

if [[ -f "${SURF_CLI_PATH}/package.json" ]]; then
    "$SKILL_DIR/scripts/ensure-surf-cli.sh" 2>/dev/null || true
fi

# Fallback: CDP controller for automation commands when no extension
case "$1" in
    go)
        shift
        run_cdp_controller go "$@"
        exit $?
        ;;
    read)
        shift
        run_cdp_controller read "$@"
        exit $?
        ;;
    click)
        shift
        run_cdp_controller click "$@"
        exit $?
        ;;
    type)
        shift
        run_cdp_controller type "$@"
        exit $?
        ;;
    key)
        shift
        run_cdp_controller key "$@"
        exit $?
        ;;
    snap|screenshot)
        shift
        run_cdp_controller snap "$@"
        exit $?
        ;;
    snap-container|screenshot-container)
        shift
        run_cdp_controller snap-container "$@"
        exit $?
        ;;
    scroll)
        shift
        run_cdp_controller scroll "$@"
        exit $?
        ;;
    wait)
        shift
        run_cdp_controller wait "$@"
        exit $?
        ;;
    text)
        shift
        run_cdp_controller text "$@"
        exit $?
        ;;
    tab.*)
        echo "Error: Tab commands require surf-cli extension." >&2
        echo "  1. Load extension: chrome://extensions → Load unpacked → ${SURF_CLI_PATH}/dist" >&2
        echo "  2. Install host: surf install <extension-id>" >&2
        exit 1
        ;;
    install)
        # Install native host (works without socket)
        if [[ -f "$LOCAL_CLI" ]]; then
            exec node "$LOCAL_CLI" "$@"
        else
            echo "Error: surf-cli not found at $LOCAL_CLI" >&2
            exit 1
        fi
        ;;
    *)
        echo "Note: surf-cli extension not available, using CDP fallback" >&2
        run_cdp_controller "$@"
        ;;
esac
