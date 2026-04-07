#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== ops-arango Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1: Required files... "
for f in SKILL.md run.sh scripts/dump.sh scripts/maintain.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: $f missing"
        exit 1
    fi
done
echo "OK"

# Check 2: run.sh is executable
echo -n "Check 2: run.sh executable... "
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh not executable"
    exit 1
fi
echo "OK"

# Check 3: help command works
echo -n "Check 3: help command... "
if ! "$SCRIPT_DIR/run.sh" --help >/dev/null 2>&1; then
    echo "FAIL: run.sh --help failed"
    exit 1
fi
echo "OK"

# Check 4: python-arango importable
echo -n "Check 4: python-arango... "
if ! python3 -c "from arango import ArangoClient" 2>/dev/null; then
    echo "FAIL: python-arango not installed (pip install python-arango)"
    exit 1
fi
echo "OK"

# Check 5: arangodump or Docker available
echo -n "Check 5: arangodump/docker... "
if command -v arangodump >/dev/null 2>&1; then
    echo "OK (arangodump in PATH)"
elif command -v docker >/dev/null 2>&1; then
    echo "OK (docker available for container dumps)"
else
    echo "WARN (neither arangodump nor docker found; dump command will fail)"
fi

# Check 6: ArangoDB reachable
echo -n "Check 6: ArangoDB connection... "
ARANGO_URL="${ARANGO_URL:-http://127.0.0.1:8529}"
if ! python3 -c "
import httpx
try:
    r = httpx.get('${ARANGO_URL}/_api/version', timeout=3)
    assert r.status_code == 200 or r.status_code == 401
except Exception:
    exit(1)
" 2>/dev/null; then
    # Try curl as fallback
    if ! curl -s --connect-timeout 3 "${ARANGO_URL}/_api/version" >/dev/null 2>&1; then
        echo "SKIP (ArangoDB not reachable at $ARANGO_URL)"
    else
        echo "OK"
    fi
else
    echo "OK ($ARANGO_URL)"
fi

# Check 7: Backup directory writable
echo -n "Check 7: Backup directory... "
BACKUP_DIR="/mnt/storage12tb/backups/arangodb"
mkdir -p "$BACKUP_DIR" 2>/dev/null
if [[ ! -w "$BACKUP_DIR" ]]; then
    echo "FAIL: $BACKUP_DIR not writable"
    exit 1
fi
echo "OK ($BACKUP_DIR)"

echo "Result: PASS"
