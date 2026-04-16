#!/usr/bin/env bash
# Sanity check for NZBGeek API access
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(dirname "$SCRIPT_DIR")"

# Load environment variables
if [[ -f "$SKILL_DIR/../../../.env" ]]; then
    export $(grep -v '^#' "$SKILL_DIR/../../../.env" | grep -E '^NZBD_GEEK_' | xargs)
elif [[ -f "$HOME/workspace/experiments/pi-mono/.env" ]]; then
    export $(grep -v '^#' "$HOME/workspace/experiments/pi-mono/.env" | grep -E '^NZBD_GEEK_' | xargs)
fi

# Check required environment variables
if [[ -z "${NZBD_GEEK_API_KEY:-}" ]]; then
    echo "FAIL: NZBD_GEEK_API_KEY not set in environment"
    exit 1
fi

if [[ -z "${NZBD_GEEK_BASE_URL:-}" ]]; then
    echo "FAIL: NZBD_GEEK_BASE_URL not set in environment"
    exit 1
fi

echo "=== NZBGeek API Sanity Check ==="
echo "Testing NZBGeek search API with dummy query..."

# Test search API with a simple query
API_URL="${NZBD_GEEK_BASE_URL%/}/api"
RESPONSE=$(curl -s -w "\nHTTP_STATUS:%{http_code}" \
    "${API_URL}?t=search&q=test&apikey=${NZBD_GEEK_API_KEY}&o=json" \
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

# Check if response has expected structure (channel or error)
if echo "$BODY" | grep -q '"channel"' || echo "$BODY" | grep -q '"error"'; then
    echo "PASS: NZBGeek API returned valid JSON response"
    echo "Status: $HTTP_STATUS"
    echo "Response structure validated"
    exit 0
else
    echo "FAIL: Response doesn't match expected NZBGeek API structure"
    echo "Response: $BODY"
    exit 1
fi
