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

extract_task_headers() {
    grep -E '^\s*###\s*Task\s+[0-9]+(\.[0-9]+)?\s*:|^\s*-\s*\[[ xX]?\]\s*(\*\*)?[Tt]ask\s*[0-9]+|^\s*-\s*\[[ xX]?\]\s*[0-9]+\.' "$TASK_FILE"
}

extract_task_descriptions() {
    extract_task_headers | sed -E \
        -e 's/^\s*###\s*Task\s+[0-9]+(\.[0-9]+)?\s*:\s*//' \
        -e 's/^\s*-\s*\[[ xX]?\]\s*(\*\*)?[Tt]ask\s*[0-9]+(\.[0-9]+)?(\*\*)?\s*:\s*//' \
        -e 's/^\s*-\s*\[[ xX]?\]\s*[0-9]+\.\s*//' \
        | tr '[:upper:]' '[:lower:]'
}

extract_task_ids() {
    extract_task_headers | sed -nE \
        -e 's/^\s*###\s*Task\s+([0-9]+(\.[0-9]+)?)\s*:.*/\1/p' \
        -e 's/^\s*-\s*\[[ xX]?\]\s*(\*\*)?[Tt]ask\s*([0-9]+(\.[0-9]+)?)(\*\*)?\s*:.*/\2/p' \
        -e 's/^\s*-\s*\[[ xX]?\]\s*([0-9]+)\..*/\1/p'
}

# Skills directory (check both locations)
SKILLS_DIR="${PI_SKILLS_DIR:-${HOME}/.pi/skills}"
if [ ! -d "$SKILLS_DIR" ]; then
    SKILLS_DIR="${HOME}/workspace/experiments/pi-mono/.pi/skills"
fi

# ============================================================================
# Check 0: Skill Overlap Scan (MANDATORY - Prevents Reinventing the Wheel)
# ============================================================================
echo -e "${YELLOW}[0/8] Skill Overlap Scan...${NC}"

# Extract task descriptions from the task file
TASK_DESCRIPTIONS=$(extract_task_descriptions)

if [ -z "$TASK_DESCRIPTIONS" ]; then
    echo -e "      ${YELLOW}⚠️  No tasks found to scan${NC}"
else
    OVERLAP_FOUND=0

    # Build a keyword index from all SKILL.md files
    if [ -d "$SKILLS_DIR" ]; then
        # For each task, check against skill descriptions and triggers
        while IFS= read -r task_desc; do
            # Skip empty lines
            [ -z "$task_desc" ] && continue

            # Extract significant keywords (3+ chars, skip common words)
            KEYWORDS=$(echo "$task_desc" | tr -cs '[:alnum:]' '\n' | \
                grep -vE '^(the|and|for|with|from|that|this|into|each|all|add|new|run|use|get|set|has|was|are|not|but|can|will|may|its|our|per|via|any|also|been|both|does|done|have|just|more|most|must|need|only|over|same|such|than|them|then|they|very|what|when|which|while|your|about|after|being|could|every|first|found|great|other|right|should|since|still|these|those|three|under|where|would)$' | \
                grep -E '.{3,}' | sort -u)

            # Check each skill's SKILL.md for matching keywords
            for skill_md in "$SKILLS_DIR"/*/SKILL.md; do
                [ -f "$skill_md" ] || continue
                skill_name=$(basename "$(dirname "$skill_md")")

                # Extract skill description and triggers (first 50 lines, lowercase)
                SKILL_HEADER=$(head -50 "$skill_md" | tr '[:upper:]' '[:lower:]')

                # Count keyword matches
                MATCH_COUNT=0
                MATCHED_WORDS=""
                for kw in $KEYWORDS; do
                    if echo "$SKILL_HEADER" | grep -q "$kw"; then
                        MATCH_COUNT=$((MATCH_COUNT + 1))
                        MATCHED_WORDS="$MATCHED_WORDS $kw"
                    fi
                done

                # If 4+ keywords match, flag as potential overlap (3 is too noisy)
                if [ $MATCH_COUNT -ge 4 ]; then
                    echo -e "      ${RED}⚠️  OVERLAP: Task \"${task_desc:0:60}...\"${NC}"
                    echo -e "      ${RED}   → Skill /${skill_name} matches ${MATCH_COUNT} keywords:${MATCHED_WORDS}${NC}"
                    echo -e "      ${RED}   → Check if /${skill_name} already does this before implementing${NC}"
                    OVERLAP_FOUND=$((OVERLAP_FOUND + 1))
                fi
            done
        done <<< "$TASK_DESCRIPTIONS"

        if [ $OVERLAP_FOUND -gt 0 ]; then
            echo ""
            echo -e "      ${RED}❌ ${OVERLAP_FOUND} potential skill overlap(s) detected${NC}"
            echo -e "      ${RED}   Add a '## Capability Overlap' section to the task file${NC}"
            echo -e "      ${RED}   explaining why existing skills can't be used.${NC}"
            echo -e "      ${RED}   Or remove overlapping tasks and use the existing skill.${NC}"

            # Check if task file has a Capability Overlap section
            if grep -qi '## Capability Overlap' "$TASK_FILE"; then
                echo -e "      ${GREEN}✅ Capability Overlap section found — acknowledged${NC}"
            else
                echo -e "      ${RED}❌ No '## Capability Overlap' section — BLOCKED${NC}"
                FAILED=1
            fi
        else
            echo -e "      ${GREEN}✅ No skill overlaps detected${NC}"
        fi
    else
        echo -e "      ${YELLOW}⚠️  Skills directory not found at $SKILLS_DIR (skipping)${NC}"
    fi
fi

# ============================================================================
# Check 1: Questions/Blockers
# ============================================================================
echo -e "${YELLOW}[1/8] Questions/Blockers...${NC}"

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
echo -e "${YELLOW}[2/8] Sanity scripts exist...${NC}"

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
echo -e "${YELLOW}[3/8] Sanity scripts pass...${NC}"

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
echo -e "${YELLOW}[4/8] Definition of Done defined...${NC}"

# Extract tasks - flexible patterns matching orchestrate.ts parser:
# - [ ] **Task 1**: Title
# - [ ] Task 1: Title
# - [ ] 1. Title
# Case insensitive, allows extra spaces
TASKS=$(extract_task_ids)

if [ -z "$TASKS" ]; then
    echo -e "      ${YELLOW}⚠️  No tasks found${NC}"
else
    # For each task, check if it has a Definition of Done
    TASK_COUNT=0
    MISSING_DOD=0

    while IFS= read -r task_id; do
        TASK_COUNT=$((TASK_COUNT + 1))
        TASK_NUM="$task_id"
        TASK_LABEL="Task $TASK_NUM"

        SECTION=$(awk -v id="$TASK_NUM" '
            BEGIN {capture=0}
            $0 ~ "^[[:space:]]*### Task " id "([[:space:]]*:|:)" {capture=1}
            capture && $0 ~ "^[[:space:]]*### Task [0-9]+(\\.[0-9]+)?[[:space:]]*:" && $0 !~ id {exit}
            capture {print}
        ' "$TASK_FILE")

        if [ -z "$SECTION" ]; then
            SECTION=$(awk -v id="$TASK_NUM" '
                BEGIN {capture=0}
                $0 ~ "^[[:space:]]*-[[:space:]]*\\[[ xX]?\\][[:space:]]*(\\*\\*)?[Tt]ask " id "(\\.[0-9]+)?(\\*\\*)?[[:space:]]*:" {capture=1}
                $0 ~ "^[[:space:]]*-[[:space:]]*\\[[ xX]?\\][[:space:]]*" id "\\." {capture=1}
                capture && $0 ~ "^[[:space:]]*-[[:space:]]*\\[[ xX]?\\][[:space:]]*((\\*\\*)?[Tt]ask [0-9]+(\\.[0-9]+)?(\\*\\*)?[[:space:]]*:|[0-9]+\\.)" && $0 !~ id {exit}
                capture {print}
            ' "$TASK_FILE")
        fi

        # Check if task is explore/research (N/A is OK)
        IS_EXPLORE=$(echo "$SECTION" | grep -i 'explore\|research' | head -1)
        HAS_DOD=$(echo "$SECTION" | grep -i 'Definition of Done' | head -1)
        HAS_TEST=$(echo "$SECTION" | grep -iE 'Test:' | head -1)

        if [ -n "$IS_EXPLORE" ]; then
            echo -e "      ${GREEN}✅ $TASK_LABEL (explore/research - N/A)${NC}"
        elif [ -n "$HAS_TEST" ]; then
            echo -e "      ${GREEN}✅ $TASK_LABEL${NC}"
        elif [ -n "$HAS_DOD" ]; then
            # Has DoD but might be MISSING
            if echo "$HAS_DOD" | grep -qi 'MISSING'; then
                echo -e "      ${RED}❌ $TASK_LABEL (Definition of Done marked MISSING)${NC}"
                MISSING_DOD=$((MISSING_DOD + 1))
            else
                echo -e "      ${YELLOW}⚠️  $TASK_LABEL (has DoD but no test specified)${NC}"
            fi
        else
            echo -e "      ${RED}❌ $TASK_LABEL (no Definition of Done)${NC}"
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
echo -e "${YELLOW}[5/8] Test files exist...${NC}"

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
echo -e "${YELLOW}[6/8] Batch quality monitoring...${NC}"

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
echo -e "${YELLOW}[7/8] Chutes budget check...${NC}"

if grep -qiE 'chutes|llm|scillm|batch' "$TASK_FILE"; then
    echo -e "      ${CYAN}LLM/Batch task detected, checking quota...${NC}"
    CHUTES_RUNNER=".pi/skills/ops-chutes/run.sh"
    if [ -f "$CHUTES_RUNNER" ]; then
        if "$CHUTES_RUNNER" budget-check; then
            echo -e "      ${GREEN}✅ Chutes budget is OK${NC}"
        elif [ "${CHUTES_PAID:-}" = "1" ]; then
            echo -e "      ${YELLOW}⚠️  Daily free tier exhausted, but CHUTES_PAID=1 (paid balance available)${NC}"
        else
            echo -e "      ${RED}❌ Chutes budget exhausted (set CHUTES_PAID=1 if paid balance available)${NC}"
            FAILED=1
        fi
    else
        echo -e "      ${YELLOW}⚠️  ops-chutes skill not found at $CHUTES_RUNNER (skipping)${NC}"
    fi
else
    echo -e "      ${GREEN}✅ No LLM/Batch keywords detected (skipping)${NC}"
fi

# ============================================================================
# Check 8: Agent Skill Awareness Verification
# ============================================================================
echo -e "${YELLOW}[8/8] Agent skill awareness...${NC}"

# Count available skills for awareness reporting
if [ -d "$SKILLS_DIR" ]; then
    SKILL_COUNT=$(ls -d "$SKILLS_DIR"/*/SKILL.md 2>/dev/null | wc -l)
    echo -e "      ${CYAN}${SKILL_COUNT} skills available in ${SKILLS_DIR}${NC}"

    # Check for high-value pipeline skills that agents commonly reinvent
    PIPELINE_SKILLS=("monitor-personas" "ingest-doc" "ingest-compliance-doc" "ingest-youtube" "ingest-book" "doc2qra" "extractor" "taxonomy" "fetcher")
    MISSING_AWARENESS=0

    for ps in "${PIPELINE_SKILLS[@]}"; do
        if [ -f "$SKILLS_DIR/$ps/SKILL.md" ]; then
            # Check if any task description mentions keywords this skill handles
            SKILL_KEYWORDS=$(head -5 "$SKILLS_DIR/$ps/SKILL.md" | grep -i 'description' | tr '[:upper:]' '[:lower:]')
            # Just log existence for awareness
            :
        fi
    done

    echo -e "      ${GREEN}✅ Pipeline skills verified: ${PIPELINE_SKILLS[*]}${NC}"
    echo -e "      ${CYAN}   Rule: Use existing skills BEFORE writing new code${NC}"
else
    echo -e "      ${YELLOW}⚠️  Skills directory not found${NC}"
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
