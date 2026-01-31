#!/bin/bash
#
# preflight.sh - Pre-flight checklist for task files
# Validates sanity scripts and completion tests BEFORE execution begins
#
# Usage: ./preflight.sh <task_file.md>
# Exit codes: 0=PASS, 1=FAIL
#

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

TASK_FILE="${1:-01_TASKS.md}"

if [ ! -f "$TASK_FILE" ]; then
    echo -e "${RED}ERROR: Task file not found: $TASK_FILE${NC}"
    exit 1
fi

echo -e "${CYAN}=== PRE-FLIGHT CHECK: $TASK_FILE ===${NC}"
echo ""

FAILED=0

# ============================================================================
# Check 1: Questions/Blockers
# ============================================================================
echo -e "${YELLOW}[1/7] Questions/Blockers...${NC}"

# Look for Questions/Blockers section (case-insensitive, flexible spacing)
# Matches: "## Questions/Blockers", "## Questions / Blockers", "## QUESTIONS/BLOCKERS"
BLOCKERS=$(sed -n '/^##[[:space:]]*[Qq]uestions[[:space:]]*\/[[:space:]]*[Bb]lockers/I,/^##/p' "$TASK_FILE" 2>/dev/null | grep -E '^\s*-\s*[^N]' | grep -vi 'none' | grep -vi 'n/a' | grep -vi 'nothing' | grep -vi 'no questions' | grep -vi 'no blockers' | head -5)

if [ -n "$BLOCKERS" ]; then
    echo -e "      ${RED}❌ Unresolved blockers found:${NC}"
    echo "$BLOCKERS" | sed 's/^/      /'
    FAILED=1
else
    echo -e "      ${GREEN}✅ None${NC}"
fi

# ============================================================================
# Check 2: Sanity Scripts Exist
# ============================================================================
echo -e "${YELLOW}[2/7] Sanity scripts exist...${NC}"

# Extract sanity scripts from the Crucial Dependencies table
# Pattern matches full paths like tools/tasks_loop/sanity/script.py
SANITY_SCRIPTS=$(grep -oE '[a-zA-Z0-9_/]*sanity/[a-zA-Z0-9_]+\.py' "$TASK_FILE" | sort -u)

if [ -z "$SANITY_SCRIPTS" ]; then
    echo -e "      ${GREEN}✅ No sanity scripts required (standard libs only)${NC}"
else
    for script in $SANITY_SCRIPTS; do
        if [ -f "$script" ]; then
            echo -e "      ${GREEN}✅ $script${NC}"
        else
            echo -e "      ${RED}❌ $script (MISSING)${NC}"
            FAILED=1
        fi
    done
fi

# ============================================================================
# Check 3: Sanity Scripts Pass
# ============================================================================
echo -e "${YELLOW}[3/7] Sanity scripts pass...${NC}"

if [ -z "$SANITY_SCRIPTS" ]; then
    echo -e "      ${GREEN}✅ No sanity scripts to run${NC}"
else
    for script in $SANITY_SCRIPTS; do
        if [ -f "$script" ]; then
            # Run the sanity script and capture exit code
            set +e
            OUTPUT=$(python "$script" 2>&1)
            EXIT_CODE=$?
            set -e

            if [ $EXIT_CODE -eq 0 ]; then
                echo -e "      ${GREEN}✅ $script (exit 0)${NC}"
            elif [ $EXIT_CODE -eq 42 ]; then
                echo -e "      ${YELLOW}⚠️  $script (exit 42: CLARIFY - needs human input)${NC}"
                echo "$OUTPUT" | tail -3 | sed 's/^/         /'
                FAILED=1
            else
                echo -e "      ${RED}❌ $script (exit $EXIT_CODE)${NC}"
                echo "$OUTPUT" | tail -3 | sed 's/^/         /'
                FAILED=1
            fi
        fi
    done
fi

# ============================================================================
# Check 4: Definition of Done Defined
# ============================================================================
echo -e "${YELLOW}[4/7] Definition of Done defined...${NC}"

# Extract tasks - flexible patterns matching orchestrate.ts parser:
# - [ ] **Task 1**: Title
# - [ ] Task 1: Title
# - [ ] 1. Title
# Case insensitive, allows extra spaces
TASKS=$(grep -iE '^\s*-\s*\[[ xX]?\]\s*(\*\*)?[Tt]ask\s*[0-9]+|^\s*-\s*\[[ xX]?\]\s*[0-9]+\.' "$TASK_FILE" | sed -E 's/.*([Tt]ask\s*[0-9]+|[0-9]+\.).*/Task \1/' | sed 's/Task Task/Task/' | sed 's/\..*//')

if [ -z "$TASKS" ]; then
    echo -e "      ${YELLOW}⚠️  No tasks found${NC}"
else
    # For each task, check if it has a Definition of Done
    TASK_COUNT=0
    MISSING_DOD=0

    while IFS= read -r task; do
        TASK_COUNT=$((TASK_COUNT + 1))
        # Extract task number for flexible matching
        TASK_NUM=$(echo "$task" | grep -oE '[0-9]+')

        # Build patterns that match both formats:
        # - **Task N**: or Task N: or N.
        # Use flexible section extraction
        SECTION=$(sed -n "/\*\*[Tt]ask\s*$TASK_NUM\*\*\|[Tt]ask\s*$TASK_NUM:\|-\s*\[\s*[xX ]\?\s*\]\s*$TASK_NUM\./,/^\s*-\s*\[\s*[xX ]\?\s*\]\s*\(\*\*[Tt]ask\|[Tt]ask\s*[0-9]\|[0-9]\+\.\)/p" "$TASK_FILE" 2>/dev/null || true)

        # Fallback: if section is empty, try simpler extraction
        if [ -z "$SECTION" ]; then
            SECTION=$(grep -A 20 -E "\*\*[Tt]ask\s*$TASK_NUM\*\*|[Tt]ask\s*$TASK_NUM:|$TASK_NUM\." "$TASK_FILE" | head -20)
        fi

        # Check if task is explore/research (N/A is OK)
        IS_EXPLORE=$(echo "$SECTION" | grep -i 'explore\|research' | head -1)
        HAS_DOD=$(echo "$SECTION" | grep -i 'Definition of Done' | head -1)
        HAS_TEST=$(echo "$SECTION" | grep -E 'Test:.*test_|Test:.*\.py' | head -1)

        if [ -n "$IS_EXPLORE" ]; then
            echo -e "      ${GREEN}✅ $task (explore/research - N/A)${NC}"
        elif [ -n "$HAS_TEST" ]; then
            echo -e "      ${GREEN}✅ $task${NC}"
        elif [ -n "$HAS_DOD" ]; then
            # Has DoD but might be MISSING
            if echo "$HAS_DOD" | grep -qi 'MISSING'; then
                echo -e "      ${RED}❌ $task (Definition of Done marked MISSING)${NC}"
                MISSING_DOD=$((MISSING_DOD + 1))
            else
                echo -e "      ${YELLOW}⚠️  $task (has DoD but no test specified)${NC}"
            fi
        else
            echo -e "      ${RED}❌ $task (no Definition of Done)${NC}"
            MISSING_DOD=$((MISSING_DOD + 1))
        fi
    done <<< "$TASKS"

    if [ $MISSING_DOD -gt 0 ]; then
        FAILED=1
    fi
fi

# ============================================================================
# Check 5: Test Files Exist
# ============================================================================
echo -e "${YELLOW}[5/7] Test files exist...${NC}"

# Extract test file references from Definition of Done
TEST_FILES=$(grep -oE 'tests?/[a-zA-Z0-9_/]+\.py' "$TASK_FILE" | sort -u)

if [ -z "$TEST_FILES" ]; then
    echo -e "      ${YELLOW}⚠️  No test files referenced${NC}"
else
    for test_file in $TEST_FILES; do
        # Extract just the file path (before ::)
        FILE_PATH=$(echo "$test_file" | cut -d: -f1)
        if [ -f "$FILE_PATH" ]; then
            echo -e "      ${GREEN}✅ $FILE_PATH${NC}"
        else
            echo -e "      ${RED}❌ $FILE_PATH (MISSING)${NC}"
            FAILED=1
        fi
    done
fi

# ============================================================================
# Check 6: Batch Quality Monitor (for long-running/batch tasks)
# ============================================================================
echo -e "${YELLOW}[6/7] Batch quality monitoring...${NC}"

# Check if task file mentions batch processing, pipeline, or extraction
IS_BATCH=$(grep -iE 'batch|pipeline|extract|long-running|overnight|nightly|hours?' "$TASK_FILE" | head -1)

if [ -n "$IS_BATCH" ]; then
    echo -e "      ${CYAN}Batch/pipeline task detected${NC}"

    # Check for output quality validation requirements
    HAS_OUTPUT_DIR=$(grep -iE 'output.*dir|artifacts|output_path' "$TASK_FILE" | head -1)
    HAS_QUALITY_MONITOR=$(grep -iE 'quality.*monitor|quality.*gate|output.*validation|watchdog' "$TASK_FILE" | head -1)

    if [ -z "$HAS_QUALITY_MONITOR" ]; then
        echo -e "      ${YELLOW}⚠️  No quality monitoring defined for batch task${NC}"
        echo -e "      ${YELLOW}   Recommendation: Add output validation with:${NC}"
        echo -e "      ${YELLOW}   - OUTPUT_DIR=<path> for quality-gate.sh to sample${NC}"
        echo -e "      ${YELLOW}   - Or background quality monitor script${NC}"
        # Warning only, not blocking (yet)
    else
        echo -e "      ${GREEN}✅ Quality monitoring defined${NC}"
    fi

    # Check for inline quality validation in code
    if [ -n "$HAS_OUTPUT_DIR" ]; then
        echo -e "      ${GREEN}✅ Output directory specified${NC}"
    fi
else
    echo -e "      ${GREEN}✅ Not a batch task (quality check N/A)${NC}"
fi

# ============================================================================
# Check 7: Chutes Budget (for LLM tasks)
# ============================================================================
echo -e "${YELLOW}[7/7] Chutes budget check...${NC}"

if grep -qiE 'chutes|llm|scillm|batch' "$TASK_FILE"; then
    echo -e "      ${CYAN}LLM/Batch task detected, checking quota...${NC}"
    CHUTES_RUNNER=".pi/skills/ops-chutes/run.sh"
    if [ -f "$CHUTES_RUNNER" ]; then
        if "$CHUTES_RUNNER" budget-check; then
            echo -e "      ${GREEN}✅ Chutes budget is OK${NC}"
        else
            echo -e "      ${RED}❌ Chutes budget exhausted${NC}"
            FAILED=1
        fi
    else
        echo -e "      ${YELLOW}⚠️  ops-chutes skill not found at $CHUTES_RUNNER (skipping)${NC}"
    fi
else
    echo -e "      ${GREEN}✅ No LLM/Batch keywords detected (skipping)${NC}"
fi

# ============================================================================
# Final Result
# ============================================================================
echo ""
if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ PRE-FLIGHT PASS${NC}"
    echo "   All checks passed. Ready to execute tasks."
    exit 0
else
    echo -e "${RED}❌ PRE-FLIGHT FAILED${NC}"
    echo ""
    echo "   Cannot proceed until all checks pass."
    echo "   Work with human to resolve issues above."
    echo ""
    echo "   Common fixes:"
    echo "   - Questions/Blockers: Answer questions, mark as 'None'"
    echo "   - Missing sanity scripts: Create with human collaboration"
    echo "   - Failing sanity scripts: Fix dependencies or script"
    echo "   - Missing Definition of Done: Define test + assertion with human"
    echo "   - Missing test files: Create test file (can be failing initially)"
    echo "   - Batch tasks: Add OUTPUT_DIR or quality monitor script"
    exit 1
fi
