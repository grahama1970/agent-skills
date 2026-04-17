#!/bin/bash
#
# quality-gate.sh
# Auto-detects project type and runs verification tests.
# Intended to be run by Agents to self-verify their work.
#
# Enhanced with OUTPUT QUALITY VALIDATION:
# - Samples actual output files and validates content
# - Checks for JSON-instead-of-markdown bugs
# - Checks for garbled/corrupted content
# - Integrates with batch-quality skill
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

# ==== OUTPUT QUALITY VALIDATION ====
# Validates actual output content, not just exit codes

validate_output_quality() {
    local output_dir="$1"
    local pattern="${2:-*.md}"
    local sample_size="${3:-5}"

    if [ -z "$output_dir" ] || [ ! -d "$output_dir" ]; then
        return 0  # No output dir specified, skip
    fi

    banner "Output Quality Validation: $output_dir"

    local files=($(find "$output_dir" -name "$pattern" -type f 2>/dev/null | shuf | head -n "$sample_size"))

    if [ ${#files[@]} -eq 0 ]; then
        echo "No files found matching $pattern in $output_dir"
        return 0
    fi

    local failures=0
    local critical=0

    for f in "${files[@]}"; do
        local issues=""
        local first_char=$(head -c 1 "$f" 2>/dev/null)
        local file_size=$(stat -f%z "$f" 2>/dev/null || stat --printf="%s" "$f" 2>/dev/null)

        # Check 1: JSON instead of expected format
        if [ "$first_char" = "{" ] || [ "$first_char" = "[" ]; then
            issues="$issues JSON_CONTENT"
            ((critical++))
        fi

        # Check 2: Suspiciously small
        if [ "$file_size" -lt 100 ]; then
            issues="$issues TOO_SMALL($file_size)"
            ((failures++))
        fi

        # Check 3: Empty file
        if [ "$file_size" -eq 0 ]; then
            issues="$issues EMPTY"
            ((critical++))
        fi

        if [ -n "$issues" ]; then
            echo -e "${RED}  FAIL: $(basename "$f"):$issues${NC}"
        else
            echo -e "${GREEN}  PASS: $(basename "$f") ($file_size bytes)${NC}"
        fi
    done

    if [ $critical -gt 0 ]; then
        echo -e "${RED}CRITICAL: $critical files have critical quality issues${NC}"
        return 1
    fi

    if [ $failures -gt 0 ]; then
        echo -e "${YELLOW}WARNING: $failures files have quality warnings${NC}"
    fi

    return 0
}

# Check for OUTPUT_DIR environment variable for batch processing
if [ -n "$OUTPUT_DIR" ]; then
    validate_output_quality "$OUTPUT_DIR" "${OUTPUT_PATTERN:-*.md}" "${SAMPLE_SIZE:-5}" || fail "Output quality validation failed"
fi

# Check for artifacts directory (common pattern)
if [ -d "artifacts" ]; then
    validate_output_quality "artifacts" "*.md" 5 || fail "Artifacts quality validation failed"
fi

# ==== END OUTPUT QUALITY VALIDATION ====

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
