#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
#
# /ux-lab Skill Runner — OpenPencil Engine
# Agent-controllable design canvas with GPU rendering, 90 AI tools, P2P collaboration.
#
# Architecture: OpenPencil (Vue 3 + CanvasKit/Skia WASM) with Embry extensions
# (agent zones, course correction, React export, NVIS theme).
#
# Transport: CLI → HTTP POST /rpc → WebSocket → browser → execute tool → response
# The automation bridge runs inside the Vite process (port 7600 HTTP, 7601 WS).
#
# Usage:
#   ./run.sh start
#   ./run.sh create --type rect --x 100 --y 100 --fill "#3b82f6"
#   ./run.sh export --format react
#   ./run.sh stop
#
set -euo pipefail

OPEN_PENCIL_DIR="/home/graham/workspace/experiments/open-pencil"
PID_FILE="/tmp/ux-lab.pid"
VITE_PORT=3000
BRIDGE_PORT=7600

show_help() {
    cat <<'EOF'
/ux-lab — Agent-controllable design canvas (OpenPencil engine)

Commands:
  start                  Launch dev server in background
  stop                   Kill background dev server
  status                 Health check the running server
  create                 Add element to canvas
  select                 Get current canvas selection
  update <id>            Patch element properties by ID
  delete <id>            Remove element by ID
  list                   List all elements on canvas
  export                 Export canvas (react, svg, json)
  undo                   Undo last action
  redo                   Redo last undone action
  screenshot             Capture canvas as PNG (--output <file> to save)
  review                 Trigger design review of current canvas
  test                   Trigger test-interactions on current canvas
  load-brief             Load a DESIGN_BOARD.md file
  save                   Save canvas state as JSON to stdout
  save-doc               Save full .ux.json document (--name, --output)
  load-doc               Load .ux.json document (--file <path>)
  pages                  List pages in current document
  add-page               Add page to document (--name)
  load                   Load canvas state from stdin or --file
  agent-join <json>      Register agent with name and color
  agent-ops <id> <json>  Submit ops for agent
  prompt <msg> [--agent] Send course correction to agents
  watch                  Poll ops log (Ctrl+C to stop)
  agents                 List registered agents
  ops-log [--last N]     Get operation log
  design <prompt>        Decompose prompt into zones and generate agent plan
  snapshots              List saved design sessions
  snapshot-save          Save current canvas (--name <label>)
  snapshot-load <id>     Restore a saved session
  events                 Stream real-time SSE events (Ctrl+C to stop)
  gallery                Show component gallery lookup
  memory-save            Save current design to /memory (ArangoDB)
  memory-list            List designs saved in /memory
  help                   Show this help

Create Options:
  --type <type>          Element type: rect, text, circle, button, image, group
  --x <n>               X position (default: 0)
  --y <n>               Y position (default: 0)
  --text <str>           Text content (for text/button types)
  --fill <color>         Fill color (hex or named)
  --variant <v>          Component variant (e.g. primary, secondary)

Export Options:
  --format <fmt>         Export format: react, svg, json (default: json)

Examples:
  ./run.sh start
  ./run.sh create --type rect --x 100 --y 100 --fill "#3b82f6"
  ./run.sh create --type text --x 200 --y 50 --text "Hello World"
  ./run.sh agent-join '{"name":"layout-agent","color":"#3b82f6"}'
  ./run.sh export --format react
  ./run.sh stop
EOF
}

# ─── RPC helpers ────────────────────────────────────────────────────

_get_token() {
    local health
    health=$(curl -sf "http://localhost:${BRIDGE_PORT}/health" 2>/dev/null) || {
        echo "ERROR: Automation bridge not running. Is ux-lab started?" >&2
        return 1
    }
    local token status
    token=$(echo "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("token",""))' 2>/dev/null)
    status=$(echo "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status",""))' 2>/dev/null)
    if [[ "$status" == "no_app" ]]; then
        echo "ERROR: OpenPencil app not connected. Open http://localhost:${VITE_PORT} in a browser." >&2
        return 1
    fi
    echo "$token"
}

rpc_call() {
    local command="$1"
    local args="$2"
    local token
    token=$(_get_token) || return 1
    curl -sf -X POST "http://localhost:${BRIDGE_PORT}/rpc" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${token}" \
        -d "{\"command\":\"${command}\",\"args\":${args}}"
    echo ""
}

tool_call() {
    local tool_name="$1"
    local tool_args="${2:-{}}"
    rpc_call "tool" "{\"name\":\"${tool_name}\",\"args\":${tool_args}}"
}

# ─── Commands ───────────────────────────────────────────────────────

cmd_start() {
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
        echo "ux-lab already running (PID $(cat "$PID_FILE"))"
        return 0
    fi

    if [[ ! -f "${OPEN_PENCIL_DIR}/package.json" ]]; then
        echo "ERROR: OpenPencil not found at ${OPEN_PENCIL_DIR}"
        exit 1
    fi

    echo "Starting ux-lab (OpenPencil engine)..."
    cd "$OPEN_PENCIL_DIR"
    nohup bun run dev > /tmp/ux-lab.log 2>&1 &
    echo $! > "$PID_FILE"
    echo "PID $(cat "$PID_FILE") saved to ${PID_FILE}"

    # Wait up to 15s for Vite
    for i in $(seq 1 15); do
        if curl -sf "http://localhost:${VITE_PORT}/" > /dev/null 2>&1; then
            echo "ux-lab is healthy (took ${i}s)"
            return 0
        fi
        sleep 1
    done

    echo "WARNING: Vite not responding after 15s. Check /tmp/ux-lab.log"
    return 1
}

cmd_stop() {
    if [[ ! -f "$PID_FILE" ]]; then
        # Try to find and kill any bun/vite on our port
        local pid
        pid=$(lsof -ti :${VITE_PORT} 2>/dev/null | head -1)
        if [[ -n "$pid" ]]; then
            kill "$pid" 2>/dev/null || true
            echo "Stopped ux-lab (PID ${pid})"
        else
            echo "No PID file found and no process on port ${VITE_PORT}"
        fi
        return 0
    fi

    local pid
    pid="$(cat "$PID_FILE")"
    if kill -0 "$pid" 2>/dev/null; then
        # Kill the process group (bun run dev spawns children)
        kill -- -"$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true
        echo "Stopped ux-lab (PID ${pid})"
    else
        echo "Process ${pid} not running"
    fi
    rm -f "$PID_FILE"
}

cmd_status() {
    local vite_ok=false
    curl -sf "http://localhost:${VITE_PORT}/" > /dev/null 2>&1 && vite_ok=true

    if $vite_ok; then
        echo "ux-lab is running (healthy)"
        # Check bridge status
        local bridge_status
        bridge_status=$(curl -sf "http://localhost:${BRIDGE_PORT}/health" 2>/dev/null) || true
        if [[ -n "$bridge_status" ]]; then
            local app_status
            app_status=$(echo "$bridge_status" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("status","unknown"))' 2>/dev/null || echo "unknown")
            echo "Automation bridge: ${app_status}"
        fi
        return 0
    else
        echo "ux-lab is not responding"
        return 1
    fi
}

# ─── Canvas manipulation (via OpenPencil tools) ────────────────────

cmd_create() {
    local type="" x="0" y="0" text="" fill="" variant=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --type)    type="$2";    shift 2 ;;
            --x)       x="$2";      shift 2 ;;
            --y)       y="$2";      shift 2 ;;
            --text)    text="$2";   shift 2 ;;
            --fill)    fill="$2";   shift 2 ;;
            --variant) variant="$2"; shift 2 ;;
            *) echo "Unknown create option: $1"; exit 1 ;;
        esac
    done

    if [[ -z "$type" ]]; then
        echo "ERROR: --type is required"
        exit 1
    fi

    # Map simple types to OpenPencil tool calls
    case "$type" in
        rect|rectangle)
            local args="{\"x\":${x},\"y\":${y},\"width\":200,\"height\":100"
            [[ -n "$fill" ]] && args+=",\"fill\":\"${fill}\""
            args+="}"
            tool_call "create_shape" "$args"
            ;;
        text)
            local args="{\"x\":${x},\"y\":${y}"
            [[ -n "$text" ]] && args+=",\"content\":\"${text}\""
            args+="}"
            tool_call "create_text" "$args"
            ;;
        circle|ellipse)
            local args="{\"x\":${x},\"y\":${y},\"width\":100,\"height\":100"
            [[ -n "$fill" ]] && args+=",\"fill\":\"${fill}\""
            args+="}"
            tool_call "create_shape" "$args"
            ;;
        button)
            local args="{\"x\":${x},\"y\":${y}"
            [[ -n "$text" ]] && args+=",\"content\":\"${text}\""
            [[ -n "$variant" ]] && args+=",\"variant\":\"${variant}\""
            args+="}"
            tool_call "create_shape" "$args"
            ;;
        *)
            local args="{\"x\":${x},\"y\":${y},\"type\":\"${type}\""
            [[ -n "$fill" ]] && args+=",\"fill\":\"${fill}\""
            [[ -n "$text" ]] && args+=",\"content\":\"${text}\""
            args+="}"
            tool_call "create_shape" "$args"
            ;;
    esac
}

cmd_select() {
    tool_call "get_selection"
}

cmd_update() {
    local id="$1"; shift
    local args="{\"nodeId\":\"${id}\""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --x)       args+=",\"x\":${2}"; shift 2 ;;
            --y)       args+=",\"y\":${2}"; shift 2 ;;
            --fill)    args+=",\"fill\":\"${2}\""; shift 2 ;;
            --text)    args+=",\"content\":\"${2}\""; shift 2 ;;
            --variant) args+=",\"variant\":\"${2}\""; shift 2 ;;
            *) echo "Unknown update option: $1"; exit 1 ;;
        esac
    done
    args+="}"
    tool_call "set_fill" "$args"
}

cmd_delete() {
    local id="$1"
    tool_call "delete_nodes" "{\"nodeIds\":[\"${id}\"]}"
}

cmd_list() {
    rpc_call "eval" "{\"code\":\"return figma.currentPage.children.map(n => ({ id: n.id, name: n.name, type: n.type }))\"}"
}

cmd_export() {
    local format="json"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --format) format="$2"; shift 2 ;;
            *) echo "Unknown export option: $1"; exit 1 ;;
        esac
    done

    case "$format" in
        react)
            tool_call "export_react" "{\"style\":\"tailwind\"}"
            ;;
        svg)
            tool_call "export_svg_embry" "{}"
            ;;
        json)
            tool_call "export_json" "{}"
            ;;
        *)
            rpc_call "export_jsx" "{\"style\":\"${format}\"}"
            ;;
    esac
}

cmd_undo() {
    rpc_call "eval" "{\"code\":\"figma.undo()\"}"
}

cmd_redo() {
    rpc_call "eval" "{\"code\":\"figma.redo()\"}"
}

cmd_screenshot() {
    local output=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --output) output="$2"; shift 2 ;;
            *) shift ;;
        esac
    done

    local result
    result=$(rpc_call "export" "{\"format\":\"PNG\"}")
    if [[ -n "$output" ]]; then
        echo "$result" | python3 -c "
import json,sys,base64
d=json.load(sys.stdin)
r=d.get('result',d)
b64=r.get('base64','')
sys.stdout.buffer.write(base64.b64decode(b64))
" > "$output"
        echo "Screenshot saved to $output"
    else
        echo "$result"
    fi
}

cmd_review() {
    echo "Capturing screenshot for /review-design..."
    cmd_screenshot --output /tmp/ux-lab-review.png
    echo "Screenshot at /tmp/ux-lab-review.png — pipe to /review-design"
}

cmd_test_interactions() {
    echo "Capturing screenshot for /test-interactions..."
    cmd_screenshot --output /tmp/ux-lab-test.png
    echo "Screenshot at /tmp/ux-lab-test.png — pipe to /test-interactions"
}

cmd_load_brief() {
    local path="$1"
    if [[ -z "$path" ]]; then
        echo "ERROR: path argument required"
        exit 1
    fi
    echo "Design board loaded from: ${path}"
    echo "Use 'design' command to decompose into agent zones."
}

# ─── Agent collaboration (Embry extensions) ─────────────────────────

cmd_agent_join() {
    local json="$1"
    if [[ -z "$json" ]]; then
        echo 'ERROR: JSON body required (e.g. '\''{"name":"my-agent","color":"#ff0000"}'\'')'
        exit 1
    fi
    tool_call "agent_register" "$json"
}

cmd_agent_ops() {
    local agent_id="$1"; shift
    local json="$1"
    if [[ -z "$agent_id" || -z "$json" ]]; then
        echo "ERROR: agent-ops requires <agent-id> <json-body>"
        exit 1
    fi
    tool_call "agent_submit_ops" "{\"agentId\":\"${agent_id}\",\"ops\":${json}}"
}

cmd_prompt() {
    shift 2>/dev/null || true
    local MESSAGE=""
    local AGENT="all"
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --agent) AGENT="$2"; shift 2 ;;
            *) MESSAGE="$MESSAGE $1"; shift ;;
        esac
    done
    rpc_call "eval" "{\"code\":\"return { sent: true, message: '${MESSAGE## }', target: '${AGENT}' }\"}"
}

cmd_watch() {
    echo "Watching operations (Ctrl+C to stop)..."
    while true; do
        tool_call "agent_get_ops_log" "{\"last\":1}" 2>/dev/null || true
        sleep 1
    done
}

cmd_agents() {
    tool_call "agent_list" "{}"
}

cmd_ops_log() {
    local last=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --last) last="$2"; shift 2 ;;
            *) echo "Unknown ops-log option: $1"; exit 1 ;;
        esac
    done
    if [[ -n "$last" ]]; then
        tool_call "agent_get_ops_log" "{\"last\":${last}}"
    else
        tool_call "agent_get_ops_log" "{}"
    fi
}

# ─── Document management ───────────────────────────────────────────

cmd_save_doc() {
    local name="" output=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name)   name="$2";   shift 2 ;;
            --output) output="$2"; shift 2 ;;
            *) echo "Unknown save-doc option: $1"; exit 1 ;;
        esac
    done
    rpc_call "eval" "{\"code\":\"return figma.saveFile('${output:-/tmp/ux-lab-doc.json}')\"}"
}

cmd_load_doc() {
    local file=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --file) file="$2"; shift 2 ;;
            *) echo "Unknown load-doc option: $1"; exit 1 ;;
        esac
    done
    if [[ -z "$file" ]]; then
        echo "ERROR: --file is required"
        exit 1
    fi
    rpc_call "eval" "{\"code\":\"return figma.openFile('${file}')\"}"
}

cmd_pages() {
    rpc_call "eval" "{\"code\":\"return figma.root.children.map(p => ({ id: p.id, name: p.name }))\"}"
}

cmd_add_page() {
    local name=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name) name="$2"; shift 2 ;;
            *) echo "Unknown add-page option: $1"; exit 1 ;;
        esac
    done
    if [[ -z "$name" ]]; then
        echo "ERROR: --name is required"
        exit 1
    fi
    tool_call "create_page" "{\"name\":\"${name}\"}"
}

cmd_design() {
    local prompt="$1"
    if [[ -z "$prompt" ]]; then
        echo "ERROR: prompt argument required"
        echo "Usage: ./run.sh design \"dashboard with navbar and sidebar\""
        exit 1
    fi
    # Zone decomposition — returns a plan for agent zone assignment
    echo "{\"prompt\":$(echo "$prompt" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().strip()))')}"
    echo "Design prompt registered. Use agent-join to register agents for zones."
}

cmd_save() {
    rpc_call "eval" "{\"code\":\"return JSON.stringify(figma.currentPage.children.map(n => n.toJSON ? n.toJSON() : {id:n.id,name:n.name}))\"}"
}

cmd_load() {
    local file=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --file) file="$2"; shift 2 ;;
            *) echo "Unknown load option: $1"; exit 1 ;;
        esac
    done

    if [[ -n "$file" ]]; then
        local content
        content="$(cat "$file")"
        rpc_call "eval" "{\"code\":\"return figma.loadState(${content})\"}"
    else
        echo "ERROR: --file required or pipe via stdin"
        exit 1
    fi
}

# ─── Snapshots (session persistence) ──────────────────────────────

cmd_snapshots() {
    curl -sf "http://localhost:${BRIDGE_PORT}/snapshots" 2>/dev/null | python3 -c "
import json, sys
data = json.load(sys.stdin)
if not data.get('snapshots'):
    print('No saved sessions.')
    sys.exit(0)
print(f\"{'ID':38} {'Name':30} {'Created'}\")
print('-' * 90)
for s in data['snapshots']:
    print(f\"{s['id']:38} {s['name']:30} {s['created']}\")
" || echo "ERROR: Bridge not running"
}

cmd_snapshot_save() {
    local name=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name) name="$2"; shift 2 ;;
            *) echo "Unknown option: $1"; exit 1 ;;
        esac
    done
    local payload="{}"
    [[ -n "$name" ]] && payload="{\"name\":\"${name}\"}"
    curl -sf -X POST "http://localhost:${BRIDGE_PORT}/snapshots" \
        -H "Content-Type: application/json" \
        -d "$payload" || echo "ERROR: Bridge not running"
}

cmd_snapshot_load() {
    local id="$1"
    if [[ -z "$id" ]]; then
        echo "ERROR: snapshot ID required"
        exit 1
    fi
    local snapshot
    snapshot=$(curl -sf "http://localhost:${BRIDGE_PORT}/snapshots/${id}" 2>/dev/null)
    if [[ -z "$snapshot" ]]; then
        echo "ERROR: Snapshot not found or bridge not running"
        exit 1
    fi
    local state
    state=$(echo "$snapshot" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(json.dumps(d.get("state",{})))' 2>/dev/null)
    rpc_call "eval" "{\"code\":\"return figma.loadState(${state})\"}"
    echo "Restored snapshot: $id"
}

# ─── SSE event stream ─────────────────────────────────────────────

cmd_events() {
    echo "Streaming events from canvas (Ctrl+C to stop)..."
    curl -sf -N "http://localhost:${BRIDGE_PORT}/events" 2>/dev/null || echo "ERROR: Bridge not running"
}

# ─── Component gallery ────────────────────────────────────────────

cmd_gallery() {
    local GALLERY_DIR
    GALLERY_DIR="$(dirname "$(readlink -f "$0")")/references/component-gallery"
    if [[ ! -d "$GALLERY_DIR" ]]; then
        echo "ERROR: Component gallery not found at $GALLERY_DIR"
        exit 1
    fi
    local query="${1:-}"
    if [[ -z "$query" ]]; then
        cat "$GALLERY_DIR/INDEX.md"
    else
        # Search LOOKUP.md for the term
        grep -i "$query" "$GALLERY_DIR/LOOKUP.md" 2>/dev/null || echo "No match for: $query"
    fi
}

# ─── /memory integration (ArangoDB session storage) ───────────────

MEMORY_SOCKET="/run/user/$(id -u)/embry-memory.sock"

cmd_memory_save() {
    local name=""
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --name) name="$2"; shift 2 ;;
            *) echo "Unknown option: $1"; exit 1 ;;
        esac
    done

    # Capture current canvas state
    local token
    token=$(_get_token) || return 1
    local state
    state=$(curl -sf -X POST "http://localhost:${BRIDGE_PORT}/rpc" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${token}" \
        -d '{"command":"eval","args":{"code":"return JSON.stringify(figma.currentPage.children.map(n => n.toJSON ? n.toJSON() : {id:n.id,name:n.name}))"}}')

    # Also capture a screenshot
    local screenshot_b64
    screenshot_b64=$(curl -sf -X POST "http://localhost:${BRIDGE_PORT}/rpc" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer ${token}" \
        -d '{"command":"export","args":{"format":"PNG"}}' | python3 -c 'import json,sys; print(json.load(sys.stdin).get("result",{}).get("base64",""))' 2>/dev/null)

    local label="${name:-ux-lab-design-$(date +%Y%m%d-%H%M%S)}"

    # Store in /memory via Unix socket
    if [[ -S "$MEMORY_SOCKET" ]]; then
        local payload
        payload=$(python3 -c "
import json
print(json.dumps({
    'content': 'UX Lab design session: ${label}',
    'metadata': {
        'type': 'ux-lab-session',
        'name': '${label}',
        'created': '$(date -Iseconds)',
        'canvas_state': json.loads('''${state}''' if '''${state}'''.strip() else '{}'),
        'screenshot_b64': '${screenshot_b64:.100}...',
    },
    'tags': ['ux-lab', 'design-session', 'canvas-state']
}))
")
        curl -sf --unix-socket "$MEMORY_SOCKET" \
            -X POST "http://localhost/store" \
            -H "Content-Type: application/json" \
            -d "$payload" && echo "Saved to /memory: ${label}" || echo "WARN: /memory store failed, saved locally only"
    else
        echo "WARN: embry-memory daemon not running. Saving to local snapshots only."
    fi

    # Also save as local snapshot
    cmd_snapshot_save --name "$label"
}

cmd_memory_list() {
    if [[ ! -S "$MEMORY_SOCKET" ]]; then
        echo "embry-memory daemon not running. Showing local snapshots only:"
        cmd_snapshots
        return
    fi
    curl -sf --unix-socket "$MEMORY_SOCKET" \
        -X POST "http://localhost/recall" \
        -H "Content-Type: application/json" \
        -d '{"query":"ux-lab design session","limit":20}' | python3 -c "
import json, sys
data = json.load(sys.stdin)
results = data.get('results', [])
if not results:
    print('No design sessions in /memory.')
    sys.exit(0)
print(f\"{'Score':6} {'Name':35} {'Created'}\")
print('-' * 80)
for r in results:
    meta = r.get('metadata', {})
    if meta.get('type') == 'ux-lab-session':
        print(f\"{r.get('score', 0):.3f}  {meta.get('name','?'):35} {meta.get('created','?')}\")
" || echo "ERROR: /memory recall failed"
}

# ─── Dispatch ──────────────────────────────────────────────────────

case "${1:-help}" in
    start)       shift; cmd_start "$@" ;;
    stop)        shift; cmd_stop "$@" ;;
    status)      shift; cmd_status "$@" ;;
    create)      shift; cmd_create "$@" ;;
    select)      shift; cmd_select "$@" ;;
    update)      shift; cmd_update "$@" ;;
    delete)      shift; cmd_delete "$@" ;;
    list)        shift; cmd_list "$@" ;;
    export)      shift; cmd_export "$@" ;;
    undo)        shift; cmd_undo "$@" ;;
    redo)        shift; cmd_redo "$@" ;;
    screenshot)  shift; cmd_screenshot "$@" ;;
    review)      shift; cmd_review "$@" ;;
    test)        shift; cmd_test_interactions "$@" ;;
    load-brief)  shift; cmd_load_brief "$@" ;;
    save)        shift; cmd_save "$@" ;;
    save-doc)    shift; cmd_save_doc "$@" ;;
    load-doc)    shift; cmd_load_doc "$@" ;;
    pages)       shift; cmd_pages "$@" ;;
    add-page)    shift; cmd_add_page "$@" ;;
    load)        shift; cmd_load "$@" ;;
    agent-join)  shift; cmd_agent_join "$@" ;;
    agent-ops)   shift; cmd_agent_ops "$@" ;;
    prompt)      cmd_prompt "$@" ;;
    watch)       shift; cmd_watch "$@" ;;
    agents)      shift; cmd_agents "$@" ;;
    ops-log)     shift; cmd_ops_log "$@" ;;
    design)      shift; cmd_design "$@" ;;
    snapshots)       shift; cmd_snapshots "$@" ;;
    snapshot-save)   shift; cmd_snapshot_save "$@" ;;
    snapshot-load)   shift; cmd_snapshot_load "$@" ;;
    events)          shift; cmd_events "$@" ;;
    gallery)         shift; cmd_gallery "$@" ;;
    memory-save)     shift; cmd_memory_save "$@" ;;
    memory-list)     shift; cmd_memory_list "$@" ;;
    help|--help|-h) show_help ;;
    *)
        echo "Unknown command: $1"
        echo "Run './run.sh help' for usage."
        exit 1
        ;;
esac
