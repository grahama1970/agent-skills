#!/usr/bin/env bash
# remote-control skill — start Claude Code remote-control in a registered project
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_SERVER="${HOME}/workspace/experiments/embry-os/services/mcp-daemon/server.py"
MCP_VENV="${HOME}/workspace/experiments/embry-os/services/mcp-daemon/.venv"
PROJECTS_JSON="$HOME/.agent-inbox/projects.json"

# ── Helpers ──────────────────────────────────────────────────────────────────

resolve_project() {
  local name="$1"
  if [[ ! -f "$PROJECTS_JSON" ]]; then
    echo "ERROR: No projects registry at $PROJECTS_JSON" >&2
    echo "Run: agent-inbox scan ~/workspace/experiments" >&2
    return 1
  fi
  python3 -c "
import json, sys
data = json.load(open('$PROJECTS_JSON'))
name = '$name'
if name not in data:
    # Fuzzy match: check if name is a substring of any key
    matches = [k for k in data if name.lower() in k.lower()]
    if len(matches) == 1:
        name = matches[0]
    elif len(matches) > 1:
        print(f'Ambiguous: {matches}', file=sys.stderr)
        sys.exit(1)
    else:
        print(f'Unknown project: {name}', file=sys.stderr)
        print(f'Available: {sorted(data.keys())}', file=sys.stderr)
        sys.exit(1)
path = data[name]
if isinstance(path, dict):
    path = path.get('path', '')
print(path)
"
}

list_projects() {
  if [[ ! -f "$PROJECTS_JSON" ]]; then
    echo "No projects registry at $PROJECTS_JSON"
    exit 1
  fi
  python3 -c "
import json
from pathlib import Path
data = json.load(open('$PROJECTS_JSON'))
for name, val in sorted(data.items()):
    p = val if isinstance(val, str) else val.get('path', '?')
    pp = Path(p)
    branch = 'n/a'
    head = pp / '.git' / 'HEAD'
    if head.exists():
        h = head.read_text().strip()
        branch = h[16:] if h.startswith('ref: refs/heads/') else h[:12]
    print(f'  {name:<30} {branch:<30} {p}')
"
}

# ── Main ─────────────────────────────────────────────────────────────────────

# First arg determines behavior
arg="${1:-}"

case "$arg" in
  health)
    echo "=== MCP Server Health ==="
    [[ -f "$MCP_SERVER" ]] && echo "Server: OK" || echo "Server: MISSING ($MCP_SERVER)"
    [[ -d "$MCP_VENV" ]] && echo "Venv: OK" || echo "Venv: MISSING"
    if [[ -f "$PROJECTS_JSON" ]]; then
      COUNT=$(python3 -c "import json; print(len(json.load(open('$PROJECTS_JSON'))))" 2>/dev/null)
      echo "Registry: $COUNT projects"
    else
      echo "Registry: MISSING"
    fi
    if claude mcp list 2>/dev/null | grep -q "embry-projects.*Connected"; then
      echo "MCP: CONNECTED"
    else
      echo "MCP: NOT CONNECTED"
    fi
    ;;

  install)
    echo "Installing embry-projects MCP server..."
    if [[ ! -d "$MCP_VENV" ]]; then
      cd "$(dirname "$MCP_SERVER")"
      uv venv
      uv pip install "mcp[cli]>=1.0" "httpx>=0.27"
    fi
    claude mcp add --transport stdio --scope user embry-projects -- "$MCP_VENV/bin/python" "$MCP_SERVER"
    echo "Done. Restart Claude Code session for MCP to connect."
    ;;

  help|-h|--help)
    cat <<'USAGE'
remote-control — Start Claude Code remote-control in a registered project

Usage:
  /remote-control <project>     Start remote-control in a project (looks up path from agent-inbox)
  /remote-control               List available projects
  /remote-control health        Check MCP server and registry status
  /remote-control install       Install MCP server venv and register with Claude Code

Examples:
  /remote-control pi-mono       → cd to pi-mono, start remote-control
  /remote-control sparta        → cd to sparta, start remote-control
  /remote-control extractor     → cd to extractor, start remote-control

From iPad: open the URL in Safari or scan the QR code.
USAGE
    ;;

  "")
    # No args — list available projects
    echo "Available projects (use: /remote-control <name>):"
    echo ""
    list_projects
    ;;

  *)
    # Treat arg as a project name
    PROJECT_PATH=$(resolve_project "$arg") || exit 1

    if [[ ! -d "$PROJECT_PATH" ]]; then
      echo "ERROR: Project path does not exist: $PROJECT_PATH"
      exit 1
    fi

    # Pre-flight
    if ! command -v claude &>/dev/null; then
      echo "ERROR: claude CLI not found"
      exit 1
    fi

    echo "Project: $arg"
    echo "Path:    $PROJECT_PATH"
    echo ""
    echo "Starting remote-control session..."
    echo "Connect from iPad by opening the URL or scanning the QR code."
    echo ""

    cd "$PROJECT_PATH"
    exec claude remote-control --name "$arg"
    ;;
esac
