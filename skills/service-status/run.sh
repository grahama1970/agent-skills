#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
# Check health of all Embry OS service daemons
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Enforce skill-local uv environment for python invocations.
shopt -s expand_aliases
alias python='uv run --project "$SCRIPT_DIR" python'
alias python3='uv run --project "$SCRIPT_DIR" python'



SOCKETS=(
  "state:/run/user/1000/embry/state.sock"
  "voice:/run/user/1000/embry/voice.sock"
  "sparta:/run/user/1000/embry/sparta.sock"
  "memory:/run/user/1000/embry/memory.sock"
  "inference:/run/user/1000/embry/inference.sock"
  "datalake:/run/user/1000/embry/datalake.sock"
  "discord:/run/user/1000/embry/discord.sock"
  "scillm:/run/user/1000/embry/scillm.sock"
)

printf "%-15s %-10s %s\n" "DAEMON" "STATUS" "DETAIL"
printf "%-15s %-10s %s\n" "------" "------" "------"

all_ok=true
for entry in "${SOCKETS[@]}"; do
  name="${entry%%:*}"
  socket="${entry#*:}"

  if [ ! -S "$socket" ]; then
    printf "%-15s %-10s %s\n" "$name" "DOWN" "socket not found"
    all_ok=false
    continue
  fi

  response=$(curl -s --max-time 3 --unix-socket "$socket" http://localhost/health 2>/dev/null) || response=""
  if [ -z "$response" ]; then
    printf "%-15s %-10s %s\n" "$name" "DOWN" "no response"
    all_ok=false
  else
    status=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "parse_error")
    if [ "$status" = "ok" ] || [ "$status" = "healthy" ]; then
      printf "%-15s %-10s %s\n" "$name" "OK" "$response"
    else
      printf "%-15s %-10s %s\n" "$name" "WARN" "$response"
      all_ok=false
    fi
  fi
done

# TCP services (Docker containers with health endpoints)
echo ""
printf "%-15s %-10s %s\n" "--- TCP ---" "" ""

TCP_SERVICES=(
  "subagent:http://localhost:8620/health"
  "embedding:http://localhost:8602/health"
)

for entry in "${TCP_SERVICES[@]}"; do
  name="${entry%%:*}"
  url="${entry#*:}"

  response=$(curl -s --max-time 10 "$url" 2>/dev/null) || response=""
  if [ -z "$response" ]; then
    printf "%-15s %-10s %s\n" "$name" "DOWN" "no response"
    all_ok=false
  else
    status=$(echo "$response" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "parse_error")
    if [ "$status" = "ok" ] || [ "$status" = "healthy" ]; then
      printf "%-15s %-10s %s\n" "$name" "OK" "$response"
    else
      printf "%-15s %-10s %s\n" "$name" "WARN" "$response"
      all_ok=false
    fi
  fi
done

# D-Bus services
echo ""
printf "%-15s %-10s %s\n" "--- D-Bus ---" "" ""

DBUS_NAME="org.embry.Agent"
DBUS_PATH="/org/embry/Agent"
DBUS_IFACE="org.embry.Agent"

if command -v busctl &>/dev/null; then
  dbus_result=$(busctl --user call "$DBUS_NAME" "$DBUS_PATH" "$DBUS_IFACE" Ping 2>/dev/null) || dbus_result=""
  if echo "$dbus_result" | grep -q "pong"; then
    printf "%-15s %-10s %s\n" "embry-agent" "OK" "D-Bus Ping: pong"
  else
    printf "%-15s %-10s %s\n" "embry-agent" "DOWN" "D-Bus Ping failed"
    all_ok=false
  fi
else
  printf "%-15s %-10s %s\n" "embry-agent" "SKIP" "busctl not found"
fi

echo ""
if $all_ok; then
  echo "All daemons healthy."
else
  echo "Some daemons are unhealthy or unreachable."
  exit 1
fi
