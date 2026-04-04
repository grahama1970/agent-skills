#!/usr/bin/env bash
# Sanity check for SABnzbd API access
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment variables
if [[ -f "$SKILL_DIR/../../../.env" ]]; then
    export $(grep -v '^#' "$SKILL_DIR/../../../.env" | grep -E '^SABNZBD_' | xargs)
elif [[ -f "$HOME/workspace/experiments/pi-mono/.env" ]]; then
    export $(grep -v '^#' "$HOME/workspace/experiments/pi-mono/.env" | grep -E '^SABNZBD_' | xargs)
fi

# Check required environment variables
if [[ -z "${SABNZBD_API_KEY:-}" ]]; then
    echo "FAIL: SABNZBD_API_KEY not set in environment"
    exit 1
fi

if [[ -z "${SABNZBD_BASE_URL:-}" ]]; then
    echo "FAIL: SABNZBD_BASE_URL not set in environment"
    exit 1
fi

echo "=== SABnzbd API Sanity Check ==="
echo "Testing SABnzbd queue API..."

# Test queue API (returns queue status, may be empty)
API_URL="${SABNZBD_BASE_URL%/}/api"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    "${API_URL}?mode=queue&apikey=${SABNZBD_API_KEY}&output=json" \
    2>&1)

# Extract status code
HTTP_STATUS=$(echo "$RESPONSE" | grep "HTTP_STATUS:" | cut -d: -f2)
BODY=$(echo "$RESPONSE" | sed '/HTTP_STATUS:/d')

if [[ "$HTTP_STATUS" != "200" ]]; then
    echo "FAIL: Got HTTP status $HTTP_STATUS (expected 200)"
    echo "Response: $BODY"
    exit 1
fi

# Check if response is valid JSON
if ! echo "$BODY" | python3 -m json.tool > /dev/null 2>&1; then
    echo "FAIL: Response is not valid JSON"
    echo "Response: $BODY"
    exit 1
fi

# Check if response has expected structure (queue object)
if echo "$BODY" | grep -q '"queue"' || echo "$BODY" | grep -q '"slots"'; then
    echo "PASS: SABnzbd API returned valid JSON response"
    echo "Status: $HTTP_STATUS"
    echo "Response structure validated (queue API accessible)"

    # Show queue status
    QUEUE_SIZE=$(echo "$BODY" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('queue', {}).get('noofslots', 0))" 2>/dev/null || echo "0")
    echo "Current queue size: $QUEUE_SIZE items"
    exit 0
else
    echo "FAIL: Response doesn't match expected SABnzbd API structure"
    echo "Response: $BODY"
    exit 1
fi
