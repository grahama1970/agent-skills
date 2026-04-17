#!/bin/bash
# learn-datalake/sanity.sh - Validate environment and basic functionality

cd "$(dirname "$0")"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

pass=0
fail=0

check() {
    desc="$1"
    cmd="$2"
    echo -n "Checking $desc... "
    if eval "$cmd" > /dev/null 2>&1; then
        echo -e "${GREEN}PASS${NC}"
        pass=$((pass + 1))
    else
        echo -e "${RED}FAIL${NC}"
        fail=$((fail + 1))
    fi
}

echo "=== learn-datalake sanity checks ==="

# 1. Environment
check "uv installed" "uv --version"
check "python version >= 3.11" "python3 -c 'import sys; assert sys.version_info >= (3, 11)'"

# 2. Dependencies
check "dependencies installable" "uv sync"

# 3. Code Quality (exclude monolith backups)
check "black formatting" "uv run ruff format --check --exclude '*_monolith.py' ."
check "ruff linting" "uv run ruff check --exclude '*_monolith.py' ."

# 4. Functionality
check "cli imports" "uv run python -c 'import learn_datalake.cli'"
check "cli help" "./run.sh --help"
check "once command help" "./run.sh once --help"

echo "=== Results: $pass passed, $fail failed ==="

if [ $fail -eq 0 ]; then
    exit 0
else
    exit 1
fi
