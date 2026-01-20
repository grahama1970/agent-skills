#!/bin/bash
#
# quality-gate.sh
# Auto-detects project type and runs verification tests.
# Intended to be run by Agents to self-verify their work.
#

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper for banners
banner() {
    echo -e "${YELLOW}=== $1 ===${NC}"
}

fail() {
    echo -e "${RED}FAILED: $1${NC}"
    exit 1
}

pass() {
    echo -e "${GREEN}PASSED: $1${NC}"
    exit 0
}

# Handle exit code 3 (skip) as failure for implementation tasks
# Per orchestrate skill: NEVER skip tests for implementation tasks
check_skip_exit() {
    local exit_code=$1
    local test_name=$2
    if [ "$exit_code" -eq 3 ]; then
        echo -e "${RED}REJECTED: $test_name returned exit code 3 (SKIP)${NC}"
        echo "Per orchestrate skill policy: Skipped tests are NOT acceptable."
        echo "Fix the infrastructure or the test before proceeding."
        exit 1
    fi
    return $exit_code
}

banner "Quality Gate: Auto-Detecting Verifier"

if [ -f "Makefile" ]; then
    echo "Detected Makefile."
    if grep -q "^test:" Makefile; then
        echo "Running 'make test'..."
        make test || fail "make test failed"
        pass "make test"
    elif grep -q "^check:" Makefile; then
         echo "Running 'make check'..."
         make check || fail "make check failed"
         pass "make check"
    else
        echo "No 'test' or 'check' target in Makefile."
    fi
fi

if [ -f "pyproject.toml" ] || [ -f "requirements.txt" ] || [ -f "setup.py" ]; then
    echo "Detected Python project."
    if command -v pytest &>/dev/null; then
        echo "Running pytest..."
        # Run specific test file if provided as argument, else explore
        if [ ! -z "$1" ]; then
             pytest "$1" || fail "pytest $1 failed"
        else
             # Quiet mode, exit on first failure
             pytest -q -x || fail "pytest failed"
        fi
        pass "pytest"
    elif [ -f "manage.py" ]; then
        echo "Django detected. Running tests..."
        python manage.py test || fail "Django tests failed"
        pass "Django tests"
    else
        # Fallback to python unittest discovery
        echo "Running python -m unittest..."
        python3 -m unittest discover || fail "unittest failed"
        pass "unittest"
    fi
fi

if [ -f "package.json" ]; then
    echo "Detected Node.js project."
    if grep -q '"test":' package.json; then
        echo "Running npm test..."
        npm test || fail "npm test failed"
        pass "npm test"
    else
        echo "No 'test' script in package.json."
    fi
fi

if [ -f "Cargo.toml" ]; then
    echo "Detected Rust project."
    echo "Running cargo test..."
    cargo test || fail "cargo test failed"
    pass "cargo test"
fi

if [ -f "go.mod" ]; then
    echo "Detected Go project."
    echo "Running go test..."
    go test ./... || fail "go test failed"
    pass "go test"
fi

# Fallback: Check for a generic test script
if [ -f "./test.sh" ]; then
    echo "Detected generic ./test.sh"
    ./test.sh || fail "./test.sh failed"
    pass "./test.sh"
fi

# If we get here, we found no tests to run
echo -e "${RED}FAILED: No recognizable test suite found.${NC}"
echo "Checked: Makefile, Python, Node, Rust, Go, test.sh"
echo ""
echo "Per orchestrate skill policy: Tests are NON-NEGOTIABLE."
echo "Every implementation task must have a verifiable test."
echo "Please create a test before marking this task complete."
exit 1 # Hard fail - unverified work is incomplete work
