#!/bin/bash
#
# verify-all.sh - Run sanity checks for all installed skills
#

# set -e removed to allow continuos verification

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$SCRIPT_DIR"
PASSED=0
FAILED=0
FAILED_SKILLS=()

echo "=========================================="
echo "Starting Global Skill Verification"
echo "=========================================="
echo "Scanning $SKILLS_DIR for sanity.sh scripts..."

# Find all sanity.sh files (maxdepth 2 to stay within skill roots)
SCRIPTS=$(find "$SKILLS_DIR" -maxdepth 2 -name "sanity.sh" | sort)

for script in $SCRIPTS; do
    skill=$(basename "$(dirname "$script")")
    echo "------------------------------------------"
    echo "Verifying skill: $skill"
    echo "Script: $script"
    
    # Run the script via bash. 
    # Use subshell to protect current env?
    # Some sanity scripts assume CWD is the skill dir or repo root.
    # We will cd to repo root relative to .pi/skills? or just run from here?
    # Most run.sh scripts resolve their own SCRIPT_DIR.
    # But running from pi-mono root is safest convention.
    
    # Assuming .pi/skills is typically ~/.pi/skills or repo/.pi/skills
    # We try to run from the directory containing the script to be safe, 
    # or arguably from the project root if we can deduce it.
    
    # Try running from the directory of the script
    (
        cd "$(dirname "$script")"
        if ./sanity.sh; then
             exit 0
        else
             exit 1
        fi
    )
    
    RET=$?
    if [ $RET -eq 0 ]; then
        echo "✅ PASS: $skill"
        ((PASSED++))
    else
        echo "❌ FAIL: $skill"
        ((FAILED++))
        FAILED_SKILLS+=("$skill")
    fi
done

echo "=========================================="
echo "Verification Complete"
echo "Passed: $PASSED"
echo "Failed: $FAILED"

if [ $FAILED -ne 0 ]; then
    echo "Failed Skills: ${FAILED_SKILLS[*]}"
    exit 1
fi

echo "All checks passed."
exit 0
