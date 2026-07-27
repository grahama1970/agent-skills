#!/usr/bin/env bash
# Sanity check for ops-darpa skill
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "Running ops-darpa sanity checks..."

# Check 1: Verify version command works
echo -n "Checking version... "
if ./run.sh version > /dev/null; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    exit 1
fi

# Check 2: Verify help output contains new commands
echo -n "Checking new commands help... "
HELP_OUTPUT=$(./run.sh --help)
if echo "$HELP_OUTPUT" | grep -q "analyze" && \
   echo "$HELP_OUTPUT" | grep -q "generate" && \
   echo "$HELP_OUTPUT" | grep -q "check"; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "Missing commands in help output"
    exit 1
fi

# Check 3: Verify offices list
echo -n "Checking offices list... "
if ./run.sh offices | grep -q "I2O"; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    exit 1
fi

# Check 4: Create dummy BAA and analyze it
echo -n "Checking analyze command... "
cat > "$TMP_DIR/dummy_baa.txt" << EOF
DARPA BAA TEST DOCUMENT
Required Sections: Executive Summary, Goals and Impact
Volume I: Technical and Management Proposal
Page Limit: Volume I is limited to 25 pages.
Deadline: March 15, 2026
EOF

if ./run.sh analyze "$TMP_DIR/dummy_baa.txt" --json > "$TMP_DIR/analysis.json"; then
    # Verify analysis extracted key info
    if grep -q "25" "$TMP_DIR/analysis.json" && grep -q "March 15, 2026" "$TMP_DIR/analysis.json"; then
        echo -e "${GREEN}PASS${NC}"
    else
        echo -e "${RED}FAIL (Content mismatch)${NC}"
        cat "$TMP_DIR/analysis.json"
        exit 1
    fi
else
    echo -e "${RED}FAIL (Command execution)${NC}"
    exit 1
fi

echo -n "Checking DARPA programs RSS... "
if ./run.sh feed programs --json > "$TMP_DIR/programs.json" && python3 - "$TMP_DIR/programs.json" <<'PY'
import json
import sys
items = json.loads(open(sys.argv[1], encoding="utf-8").read())
if not isinstance(items, list) or not items:
    raise SystemExit("programs feed returned no items")
for item in items[:3]:
    if not item.get("title") or not item.get("link"):
        raise SystemExit("programs feed item missing title/link")
PY
then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    exit 1
fi

echo -n "Checking DARPA opportunities RSS... "
if ./run.sh feed opportunities --json > "$TMP_DIR/opportunities.json" && python3 - "$TMP_DIR/opportunities.json" <<'PY'
import json
import sys
items = json.loads(open(sys.argv[1], encoding="utf-8").read())
if not isinstance(items, list) or not items:
    raise SystemExit("opportunities feed returned no items")
for item in items[:3]:
    if not item.get("title") or not item.get("link"):
        raise SystemExit("opportunities feed item missing title/link")
PY
then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    exit 1
fi

echo -n "Checking Grants.gov API shape... "
if ./run.sh grants cyber --limit 1 --json > "$TMP_DIR/grants.json" && python3 - "$TMP_DIR/grants.json" <<'PY'
import json
import sys
items = json.loads(open(sys.argv[1], encoding="utf-8").read())
if not isinstance(items, list):
    raise SystemExit("grants API did not return a list")
PY
then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    exit 1
fi

# Check 5: Verify create-paper dependency for generate
echo -n "Checking dependencies... "
if [ -f ../create-paper/run.sh ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "create-paper skill not found in ../create-paper"
    exit 1
fi

echo -e "\n${GREEN}All sanity checks passed!${NC}"
