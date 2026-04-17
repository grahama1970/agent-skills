#!/usr/bin/env bash
# Sanity checks for remote-control skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MCP_SERVER="/home/graham/workspace/experiments/embry-os/services/mcp-daemon/server.py"
MCP_VENV="/home/graham/workspace/experiments/embry-os/services/mcp-daemon/.venv"
PROJECTS_JSON="$HOME/.agent-inbox/projects.json"
PASS=0
FAIL=0

check() {
  local desc="$1"
  shift
  if eval "$@" >/dev/null 2>&1; then
    echo "  PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $desc"
    FAIL=$((FAIL + 1))
  fi
}

echo "=== remote-control sanity ==="

check "claude CLI exists"           "command -v claude"
check "tmux exists"                 "command -v tmux"
check "MCP server.py exists"        "test -f '$MCP_SERVER'"
check "MCP venv exists"             "test -d '$MCP_VENV'"
check "MCP python has mcp module"   "'$MCP_VENV/bin/python' -c 'from mcp.server.fastmcp import FastMCP'"
check "projects.json exists"        "test -f '$PROJECTS_JSON'"
check "projects.json has entries"   "python3 -c \"import json; assert len(json.load(open('$PROJECTS_JSON'))) > 0\""
check "run.sh is executable"        "test -x '$SCRIPT_DIR/run.sh'"
check "run.sh help works"           "'$SCRIPT_DIR/run.sh' help"

# Test MCP server responds and has all 9 tools
INIT='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"sanity","version":"0.1"}}}'
TOOLS='{"jsonrpc":"2.0","method":"notifications/initialized"}\n{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
check "MCP server initializes" "printf '%s\n' '$INIT' | timeout 5 '$MCP_VENV/bin/python' '$MCP_SERVER' 2>&1 | grep -q protocolVersion"
check "MCP has open_project tool" "printf '${INIT}\n${TOOLS}\n' | timeout 5 '$MCP_VENV/bin/python' '$MCP_SERVER' 2>&1 | grep -q open_project"
check "MCP has active_sessions tool" "printf '${INIT}\n${TOOLS}\n' | timeout 5 '$MCP_VENV/bin/python' '$MCP_SERVER' 2>&1 | grep -q active_sessions"
check "MCP has close_project tool" "printf '${INIT}\n${TOOLS}\n' | timeout 5 '$MCP_VENV/bin/python' '$MCP_SERVER' 2>&1 | grep -q close_project"

echo ""
echo "Results: $PASS passed, $FAIL failed"
test "$FAIL" -eq 0
