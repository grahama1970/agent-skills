#!/usr/bin/env bash
# Container health summary (Docker) with graceful degradation.
set -euo pipefail

OUTPUT="${OUTPUT:-markdown}"

usage() {
  cat <<USAGE
Usage: $(basename "$0") [options]

Container health summary for Docker.

Options:
  --json           Output as JSON (single object) or set OUTPUT=json env
  --help           Show this message

Shows:
  - Running containers with status
  - Restart counts (potential instability indicator)
  - Resource usage summary
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --json) OUTPUT="json"; shift;;
    --help|-h) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 1;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  if [[ "$OUTPUT" == "json" ]]; then
    echo "{\"timestamp\":\"$(date -Iseconds)\",\"docker\":\"not installed\",\"containers\":[]}"
  else
    echo "## Container Health"
    echo ""
    echo "Docker not installed."
  fi
  exit 0
fi

# Check if docker daemon is running
if ! docker info >/dev/null 2>&1; then
  if [[ "$OUTPUT" == "json" ]]; then
    echo "{\"timestamp\":\"$(date -Iseconds)\",\"docker\":\"daemon not running\",\"containers\":[]}"
  else
    echo "## Container Health"
    echo ""
    echo "Docker daemon not running."
  fi
  exit 0
fi

list_containers() {
  docker ps -a --format '{{.ID}}|{{.Names}}|{{.Status}}|{{.RunningFor}}|{{.Image}}' 2>/dev/null
}

restart_counts() {
  docker ps -aq 2>/dev/null | xargs -r docker inspect --format '{{.Id}}|{{.Name}}|{{.RestartCount}}' 2>/dev/null | head -20
}

resource_usage() {
  # Get resource usage for running containers
  docker stats --no-stream --format '{{.Name}}|{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}' 2>/dev/null | head -10
}

json_escape() {
  echo -n "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

if [[ "$OUTPUT" == "json" ]]; then
  echo "{"
  echo "  \"timestamp\": \"$(date -Iseconds)\","
  echo "  \"containers\": ["
  first=true
  while IFS='|' read -r id name status running image; do
    [[ -z "$id" ]] && continue
    $first || echo ","
    first=false
    echo -n "    {\"id\":\"$id\",\"name\":\"$(json_escape "${name#/}")\",\"status\":\"$(json_escape "$status")\",\"running_for\":\"$(json_escape "$running")\",\"image\":\"$(json_escape "$image")\"}"
  done < <(list_containers)
  echo ""
  echo "  ],"
  echo "  \"restart_counts\": ["
  first=true
  while IFS='|' read -r id name rc; do
    [[ -z "$id" ]] && continue
    $first || echo ","
    first=false
    echo -n "    {\"id\":\"${id:0:12}\",\"name\":\"$(json_escape "${name#/}")\",\"restart_count\": $rc}"
  done < <(restart_counts)
  echo ""
  echo "  ],"
  echo "  \"resource_usage\": ["
  first=true
  while IFS='|' read -r name cpu mem net; do
    [[ -z "$name" ]] && continue
    $first || echo ","
    first=false
    echo -n "    {\"name\":\"$(json_escape "$name")\",\"cpu\":\"$(json_escape "$cpu")\",\"memory\":\"$(json_escape "$mem")\",\"network\":\"$(json_escape "$net")\"}"
  done < <(resource_usage)
  echo ""
  echo "  ]"
  echo "}"
else
  echo "## Container Health"
  echo ""
  echo "**Generated:** $(date '+%Y-%m-%d %H:%M:%S')"
  echo ""

  # Count containers
  total=$(docker ps -aq 2>/dev/null | wc -l)
  running=$(docker ps -q 2>/dev/null | wc -l)
  echo "**Containers:** $running running / $total total"
  echo ""

  echo "### Running Containers"
  echo ""
  echo "| ID | Name | Status | Running For | Image |"
  echo "|----|------|--------|-------------|-------|"
  while IFS='|' read -r id name status running image; do
    [[ -z "$id" ]] && continue
    echo "| ${id:0:12} | ${name#/} | $status | $running | ${image:0:30} |"
  done < <(list_containers)
  echo ""

  echo "### Restart Counts"
  echo ""
  echo "High restart counts may indicate instability."
  echo ""
  echo "| Name | Restart Count |"
  echo "|------|---------------|"
  while IFS='|' read -r id name rc; do
    [[ -z "$id" ]] && continue
    [[ "$rc" -gt 0 ]] && echo "| ${name#/} | $rc |"
  done < <(restart_counts)
  echo ""

  echo "### Resource Usage"
  echo ""
  echo "| Name | CPU | Memory | Network I/O |"
  echo "|------|-----|--------|-------------|"
  while IFS='|' read -r name cpu mem net; do
    [[ -z "$name" ]] && continue
    echo "| $name | $cpu | $mem | $net |"
  done < <(resource_usage)
fi
