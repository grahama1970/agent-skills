#!/bin/bash
# Sanity check for darpa-ops skill
set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

echo "Running darpa-ops sanity checks..."

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
cat > /tmp/dummy_baa.txt << EOF
DARPA BAA TEST DOCUMENT
Required Sections: Executive Summary, Goals and Impact
Volume I: Technical and Management Proposal
Page Limit: Volume I is limited to 25 pages.
Deadline: March 15, 2026
EOF

if ./run.sh analyze /tmp/dummy_baa.txt --json > /tmp/analysis.json; then
    # Verify analysis extracted key info
    if grep -q "25" /tmp/analysis.json && grep -q "March 15, 2026" /tmp/analysis.json; then
        echo -e "${GREEN}PASS${NC}"
    else
        echo -e "${RED}FAIL (Content mismatch)${NC}"
        cat /tmp/analysis.json
        exit 1
    fi
else
    echo -e "${RED}FAIL (Command execution)${NC}"
    exit 1
fi

rm /tmp/dummy_baa.txt /tmp/analysis.json

# Check 5: Verify paper-writer dependency for generate
echo -n "Checking dependencies... "
if [ -f ../paper-writer/run.sh ]; then
    echo -e "${GREEN}PASS${NC}"
else
    echo -e "${RED}FAIL${NC}"
    echo "paper-writer skill not found in ../paper-writer"
    exit 1
fi

echo -e "\n${GREEN}All sanity checks passed!${NC}"
