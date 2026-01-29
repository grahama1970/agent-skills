#!/usr/bin/env bash
# Network diagnostics: link state, IP, DNS resolution, open sockets, gateway reachability.
set -euo pipefail

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Network diagnostics for workstation:
  - Interface status (link, speed, duplex, errors if available)
  - IP addresses and default routes
  - DNS resolution & latency
  - Open TCP/UDP sockets summary
  - Default gateway reachability

Options:
  --json           Output as JSON (single object) or set OUTPUT=json env
  --iface <if>     Only check specific interface
  --no-external    Skip external ICMP connectivity checks
  --help           Show this message
USAGE
}

OUTPUT="${OUTPUT:-markdown}"
IFACE=""
NO_EXTERNAL=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) OUTPUT="json"; shift;;
    --iface) IFACE="$2"; shift 2;;
    --no-external) NO_EXTERNAL=true; shift;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

list_ifaces() {
  # List all non-loopback interfaces
  ip -o link show 2>/dev/null | awk -F': ' '{print $2}' | grep -v '^lo$' || true
}

iface_info() {
  local if="$1"
  local link="unknown" speed="unknown" duplex="unknown" rx_err="0" tx_err="0"
  if command -v ethtool >/dev/null 2>&1; then
    # Use subshells with || true to handle pipefail for virtual interfaces
    link=$(ethtool "$if" 2>/dev/null | awk -F': ' '/Link detected/ {print $2}' || true)
    speed=$(ethtool "$if" 2>/dev/null | awk -F': ' '/Speed/ {print $2}' || true)
    duplex=$(ethtool "$if" 2>/dev/null | awk -F': ' '/Duplex/ {print $2}' || true)
    rx_err=$(ethtool -S "$if" 2>/dev/null | awk '/rx_errors/ {print $2}' | head -1 || true)
    tx_err=$(ethtool -S "$if" 2>/dev/null | awk '/tx_errors/ {print $2}' | head -1 || true)
    # Default empty values
    link="${link:-unknown}"
    speed="${speed:-unknown}"
    duplex="${duplex:-unknown}"
    rx_err="${rx_err:-0}"
    tx_err="${tx_err:-0}"
  fi
  local ipaddr
  ipaddr=$(ip -o -4 addr show "$if" 2>/dev/null | awk '{print $4}' | head -1 || true)
  echo "$if|${ipaddr:-none}|${link}|${speed}|${duplex}|${rx_err}|${tx_err}"
}

dns_check() {
  local start end ms ok msg
  start=$(date +%s%3N)
  if getent hosts github.com >/dev/null 2>&1; then
    end=$(date +%s%3N)
    ms=$((end - start))
    ok=true; msg="DNS OK (github.com resolves in ${ms}ms)"
  else
    ok=false; msg="DNS resolution failed for github.com"
    ms=0
  fi
  echo "$ok|$msg|$ms"
}

sockets_summary() {
  if command -v ss >/dev/null 2>&1; then
    ss -tuna 2>/dev/null | awk 'NR>1 {print $1}' | sort | uniq -c | awk '{printf "%s|%s\n",$2,$1}'
  elif command -v netstat >/dev/null 2>&1; then
    netstat -tuna 2>/dev/null | awk 'NR>2 {print $1}' | sort | uniq -c | awk '{printf "%s|%s\n",$2,$1}'
  else
    echo ""
  fi
}

routes_default() {
  ip route show default 2>/dev/null | head -5
}

gateway_ping() {
  local gw
  gw=$(ip route show default 2>/dev/null | awk '/default/ {print $3}' | head -1)
  [[ -z "$gw" ]] && { echo "false|No default gateway|0"; return; }
  if ping -c1 -W1 "$gw" >/dev/null 2>&1; then
    echo "true|Gateway $gw reachable|1"
  else
    echo "false|Gateway $gw unreachable|0"
  fi
}

external_check() {
  if $NO_EXTERNAL; then
    echo "skipped|External checks disabled"
    return
  fi
  if ping -c1 -W1 1.1.1.1 >/dev/null 2>&1 || ping -c1 -W1 8.8.8.8 >/dev/null 2>&1; then
    echo "ok|External connectivity OK"
  else
    echo "fail|No external connectivity (ICMP blocked or down)"
  fi
}

json_escape() {
  echo -n "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

output_markdown() {
  echo "## Network Diagnostics"
  echo ""
  echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""
  echo "### Interfaces"
  echo ""
  echo "| Interface | IPv4 | Link | Speed | Duplex | rx_errors | tx_errors |"
  echo "|-----------|------|------|-------|--------|-----------|-----------|"
  local ifs
  if [[ -n "$IFACE" ]]; then
    ifs="$IFACE"
  else
    ifs=$(list_ifaces)
  fi
  for i in $ifs; do
    IFS='|' read -r name ip link speed duplex rx tx < <(iface_info "$i")
    echo "| $name | ${ip:-none} | ${link:-unknown} | ${speed:-unknown} | ${duplex:-unknown} | ${rx:-0} | ${tx:-0} |"
  done
  echo ""
  echo "### Default Routes"
  echo ""
  local routes
  routes=$(routes_default)
  if [[ -n "$routes" ]]; then
    echo "\`\`\`"
    echo "$routes"
    echo "\`\`\`"
  else
    echo "No default route found."
  fi
  echo ""
  echo "### Gateway Reachability"
  echo ""
  IFS='|' read -r gw_ok gw_msg _ < <(gateway_ping)
  echo "$gw_msg"
  echo ""
  echo "### DNS"
  echo ""
  IFS='|' read -r dns_ok dns_msg dns_ms < <(dns_check)
  echo "$dns_msg"
  IFS='|' read -r ext_status ext_msg < <(external_check)
  echo "$ext_msg"
  echo ""
  echo "### Open Sockets (summary)"
  echo ""
  echo "| Proto | Count |"
  echo "|-------|-------|"
  sockets_summary | while IFS='|' read -r proto count; do
    [[ -n "$proto" ]] && echo "| $proto | $count |"
  done
}

output_json() {
  echo "{"
  echo "  \"timestamp\": \"$(date -Iseconds)\","
  echo "  \"interfaces\": ["
  local first=true
  local ifs
  if [[ -n "$IFACE" ]]; then
    ifs="$IFACE"
  else
    ifs=$(list_ifaces)
  fi
  for i in $ifs; do
    $first || echo ","
    first=false
    IFS='|' read -r name ip link speed duplex rx tx < <(iface_info "$i")
    echo -n "    {\"name\":\"$(json_escape "$name")\",\"ipv4\":\"$(json_escape "${ip:-none}")\",\"link\":\"$(json_escape "${link:-unknown}")\",\"speed\":\"$(json_escape "${speed:-unknown}")\",\"duplex\":\"$(json_escape "${duplex:-unknown}")\",\"rx_errors\": ${rx:-0},\"tx_errors\": ${tx:-0}}"
  done
  echo ""
  echo "  ],"
  IFS='|' read -r gw_ok gw_msg gw_rc < <(gateway_ping)
  IFS='|' read -r dns_ok dns_msg dns_ms < <(dns_check)
  IFS='|' read -r ext_status ext_msg < <(external_check)
  echo "  \"routes\": ["
  local rfirst=true
  while read -r rline; do
    [[ -z "$rline" ]] && continue
    $rfirst || echo ","
    rfirst=false
    echo -n "    \"$(json_escape "$rline")\""
  done < <(routes_default)
  echo ""
  echo "  ],"
  echo "  \"gateway\": {\"ok\": $gw_ok, \"message\": \"$(json_escape "$gw_msg")\"},"
  echo "  \"dns\": {\"ok\": $dns_ok, \"message\": \"$(json_escape "$dns_msg")\", \"latency_ms\": $dns_ms},"
  echo "  \"external\": {\"status\": \"$(json_escape "$ext_status")\", \"message\": \"$(json_escape "$ext_msg")\"},"
  echo "  \"sockets\": ["
  local sfirst=true
  sockets_summary | while IFS='|' read -r proto count; do
    [[ -z "$proto" ]] && continue
    $sfirst || echo ","
    sfirst=false
    echo -n "    {\"proto\":\"$(json_escape "$proto")\",\"count\": $count}"
  done
  echo ""
  echo "  ]"
  echo "}"
}

if [[ "$OUTPUT" == "json" ]]; then
  output_json
else
  output_markdown
fi
