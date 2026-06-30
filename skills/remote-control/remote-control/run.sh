#!/usr/bin/env bash
# remote-control skill — start/manage Claude Code remote-control sessions
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_SERVER="${HOME}/workspace/experiments/embry-os/services/mcp-daemon/server.py"
MCP_VENV="${HOME}/workspace/experiments/embry-os/services/mcp-daemon/.venv"
PROJECTS_JSON="$HOME/.agent-inbox/projects.json"

cmd="${1:-help}"
shift || true

case "$cmd" in
  start)
    # Parse optional --name flag
    SESSION_NAME="embry-remote"
    while [[ $# -gt 0 ]]; do
      case "$1" in
        --name) SESSION_NAME="$2"; shift 2 ;;
        *) echo "Unknown flag: $1"; exit 1 ;;
      esac
    done

    # Pre-flight checks
    if ! command -v claude &>/dev/null; then
      echo "ERROR: claude CLI not found in PATH"
      exit 1
    fi

    VERSION=$(claude --version 2>/dev/null | grep -oP '[\d.]+' | head -1)
    echo "Claude Code version: $VERSION"

    if [[ ! -f "$MCP_SERVER" ]]; then
      echo "ERROR: MCP server not found at $MCP_SERVER"
      exit 1
    fi

    if [[ ! -f "$PROJECTS_JSON" ]]; then
      echo "ERROR: No projects registry at $PROJECTS_JSON"
      echo "Run: agent-inbox scan ~/workspace/experiments"
      exit 1
    fi

    PROJECT_COUNT=$(python3 -c "import json; print(len(json.load(open('$PROJECTS_JSON'))))" 2>/dev/null || echo "?")
    echo "Projects registered: $PROJECT_COUNT"
    echo ""
    echo "Starting remote-control session: $SESSION_NAME"
    echo "Connect from iPad by opening the URL or scanning the QR code."
    echo ""

    exec claude remote-control --name "$SESSION_NAME"
    ;;

  health)
    echo "=== MCP Server Health ==="
    if [[ -f "$MCP_SERVER" ]]; then
      echo "Server file: OK ($MCP_SERVER)"
    else
      echo "Server file: MISSING ($MCP_SERVER)"
    fi

    if [[ -d "$MCP_VENV" ]]; then
      echo "Venv: OK ($MCP_VENV)"
    else
      echo "Venv: MISSING ($MCP_VENV)"
    fi

    if [[ -f "$PROJECTS_JSON" ]]; then
      COUNT=$(python3 -c "import json; print(len(json.load(open('$PROJECTS_JSON'))))" 2>/dev/null)
      echo "Registry: OK ($COUNT projects)"
    else
      echo "Registry: MISSING ($PROJECTS_JSON)"
    fi

    # Check if MCP is registered in claude config
    if claude mcp list 2>/dev/null | grep -q "embry-projects.*Connected"; then
      echo "Claude MCP: CONNECTED"
    elif claude mcp list 2>/dev/null | grep -q "embry-projects"; then
      echo "Claude MCP: REGISTERED (not connected — needs session restart)"
    else
      echo "Claude MCP: NOT REGISTERED"
      echo "  Fix: claude mcp add --transport stdio --scope user embry-projects -- $MCP_VENV/bin/python $MCP_SERVER"
    fi
    ;;

  projects)
    if [[ ! -f "$PROJECTS_JSON" ]]; then
      echo "No projects registry at $PROJECTS_JSON"
      exit 1
    fi
    python3 -c "
import json
data = json.load(open('$PROJECTS_JSON'))
for name, path in sorted(data.items()):
    p = path if isinstance(path, str) else path.get('path', '?')
    print(f'  {name:<35} {p}')
"
    ;;

  install)
    echo "Installing embry-projects MCP server..."
    if [[ ! -d "$MCP_VENV" ]]; then
      echo "Creating venv..."
      cd "$(dirname "$MCP_SERVER")"
      uv venv
      uv pip install "mcp[cli]>=1.0" "httpx>=0.27"
    fi

    claude mcp add --transport stdio --scope user embry-projects -- "$MCP_VENV/bin/python" "$MCP_SERVER"
    echo "Done. Restart Claude Code session for MCP to connect."
    ;;

  help|*)
    cat <<'USAGE'
remote-control — iPad/mobile access to all registered projects

Commands:
  start [--name NAME]   Start a claude remote-control session (default name: embry-remote)
  health                Check MCP server, venv, registry, and Claude config
  projects              List all registered projects from agent-inbox
  install               Install MCP server venv and register with Claude Code

Usage from iPad:
  1. Run: ./run.sh start
  2. Open the URL in Safari on iPad (or scan QR code)
  3. Say: "list my projects" or "run tests in extractor"
USAGE
    ;;
esac
