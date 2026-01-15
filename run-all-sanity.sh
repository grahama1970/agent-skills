#!/usr/bin/env bash
# Run all skill sanity tests
# Usage: ./run-all-sanity.sh [--fail-fast]

set -uo pipefail

FAIL_FAST=false
if [[ "${1:-}" == "--fail-fast" ]]; then
    FAIL_FAST=true
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

declare -A SKILL_STATUS
declare -A SKILL_REASON

echo "========================================"
echo "  Running All Skill Sanity Tests"
echo "========================================"
echo ""

for skill_dir in "$SCRIPT_DIR"/*/; do
    skill_name=$(basename "$skill_dir")
    sanity_script="$skill_dir/sanity.sh"

    if [[ -x "$sanity_script" ]]; then
        echo ""
        echo "----------------------------------------"
        echo "  Skill: $skill_name"
        echo "----------------------------------------"

        OUTPUT=$("$sanity_script" 2>&1) || true
        echo "$OUTPUT"

        # Parse the result
        if echo "$OUTPUT" | grep -q "Result: PASS"; then
            SKILL_STATUS[$skill_name]="READY"
            SKILL_REASON[$skill_name]=""
        elif echo "$OUTPUT" | grep -q "Result: FAIL"; then
            SKILL_STATUS[$skill_name]="BROKEN"
            SKILL_REASON[$skill_name]=$(echo "$OUTPUT" | grep "\[FAIL\]" | head -1 | sed 's/.*\[FAIL\] //')
        elif echo "$OUTPUT" | grep -q "Result: INCOMPLETE"; then
            SKILL_STATUS[$skill_name]="NOT INSTALLED"
            # Extract the first missing dependency
            SKILL_REASON[$skill_name]=$(echo "$OUTPUT" | grep "\[MISS\]" | head -1 | sed 's/.*\[MISS\] //')
        else
            SKILL_STATUS[$skill_name]="UNKNOWN"
            SKILL_REASON[$skill_name]="Could not parse test output"
        fi

        if $FAIL_FAST && [[ "${SKILL_STATUS[$skill_name]}" == "BROKEN" ]]; then
            echo ""
            echo "FAIL FAST: Stopping at first failure"
            break
        fi
    fi
done

echo ""
echo "========================================"
echo "  Summary"
echo "========================================"
echo ""
printf "%-20s %-15s %s\n" "SKILL" "STATUS" "REASON"
printf "%-20s %-15s %s\n" "-----" "------" "------"

READY_COUNT=0
BROKEN_COUNT=0
NOT_INSTALLED_COUNT=0

# Count first
for skill in "${!SKILL_STATUS[@]}"; do
    status="${SKILL_STATUS[$skill]}"
    case "$status" in
        READY) ((++READY_COUNT)) ;;
        BROKEN) ((++BROKEN_COUNT)) ;;
        "NOT INSTALLED") ((++NOT_INSTALLED_COUNT)) ;;
    esac
done

# Then display sorted
for skill in $(echo "${!SKILL_STATUS[@]}" | tr ' ' '\n' | sort); do
    status="${SKILL_STATUS[$skill]}"
    reason="${SKILL_REASON[$skill]}"

    case "$status" in
        READY)
            printf "%-20s \033[32m%-15s\033[0m %s\n" "$skill" "$status" ""
            ;;
        BROKEN)
            printf "%-20s \033[31m%-15s\033[0m %s\n" "$skill" "$status" "$reason"
            ;;
        "NOT INSTALLED")
            printf "%-20s \033[33m%-15s\033[0m %s\n" "$skill" "$status" "$reason"
            ;;
        *)
            printf "%-20s %-15s %s\n" "$skill" "$status" "$reason"
            ;;
    esac
done

echo ""
echo "Ready: $READY_COUNT | Not Installed: $NOT_INSTALLED_COUNT | Broken: $BROKEN_COUNT"
echo ""

if [[ $BROKEN_COUNT -gt 0 ]]; then
    echo "Some skills are BROKEN - tests failed unexpectedly"
    exit 1
fi

if [[ $NOT_INSTALLED_COUNT -gt 0 ]]; then
    echo "Some skills are NOT INSTALLED - run individual sanity.sh to see install commands"
fi

exit 0
