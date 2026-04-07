#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [ops-sam-gov] Sanity Check ==="

# Check 1: Required files exist
echo "Check 1: Required files..."
for f in SKILL.md run.sh sam_gov_ops.py; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "FAIL: Missing $f"
        exit 1
    fi
done
echo "  All required files present"

# Check 2: run.sh is executable
if [[ ! -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "FAIL: run.sh is not executable"
    exit 1
fi
echo "  run.sh is executable"

# Check 3: Python stdlib imports (script uses urllib, no external deps required)
if python3 -c "
import json, os, sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
" 2>/dev/null; then
    echo "  Python stdlib imports OK"
else
    echo "FAIL: Python stdlib imports failed"
    exit 1
fi

# Check 4: Optional deps (typer, rich - gracefully degrades without them)
if python3 -c "import typer; from rich.console import Console; from rich.table import Table" 2>/dev/null; then
    echo "  Optional deps OK (typer, rich)"
else
    echo "  WARN: typer/rich not installed (skill will use fallback output)"
fi

# Check 5: sam_gov_ops.py is parseable
if python3 -c "import ast; ast.parse(open('$SCRIPT_DIR/sam_gov_ops.py').read())" 2>/dev/null; then
    echo "  sam_gov_ops.py parses without errors"
else
    echo "FAIL: sam_gov_ops.py has syntax errors"
    exit 1
fi

# Check 6: API key check
if [[ -z "${SAMGOV_API_KEY:-}" ]]; then
    PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        set -a
        source "$PROJECT_ROOT/.env"
        set +a
    fi
fi

if [[ -z "${SAMGOV_API_KEY:-}" ]]; then
    echo "  SKIP: SAMGOV_API_KEY not set (cannot test live API)"
    echo "Result: PASS (API key missing, live tests skipped)"
    exit 0
fi
echo "  SAMGOV_API_KEY found"

# Check 7: Live API test - exclusions endpoint (public, lightweight)
response=$(python3 -c "
import os, json
from urllib.request import Request, urlopen
from urllib.parse import urlencode

api_key = os.environ['SAMGOV_API_KEY']
params = urlencode({'api_key': api_key, 'classification': 'Firm', 'limit': '1'})
url = f'https://api.sam.gov/entity-information/v3/exclusions?{params}'
req = Request(url, headers={'Accept': 'application/json'})
try:
    resp = urlopen(req, timeout=10)
    data = json.loads(resp.read())
    print('OK' if 'totalRecords' in data or 'excludedEntity' in str(data) else 'UNEXPECTED')
except Exception as e:
    print(f'ERROR: {e}')
" 2>&1 || true)

if [[ "$response" == "OK" ]]; then
    echo "  Live API test passed (exclusions endpoint)"
else
    echo "  WARN: Live API test returned: $response"
fi

echo "Result: PASS"
