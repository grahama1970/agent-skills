#!/bin/bash
# Run all sanity scripts
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Running Sanity Scripts for create-storyboard ==="
echo

FAILED=0

# Run each sanity script
for script in *.sh *.py; do
    [ "$script" = "run_all.sh" ] && continue
    [ ! -f "$script" ] && continue
    
    echo "--- $script ---"
    if [[ "$script" == *.py ]]; then
        if python3 "$script"; then
            echo "✓ $script PASSED"
        else
            echo "✗ $script FAILED"
            FAILED=$((FAILED + 1))
        fi
    else
        if bash "$script"; then
            echo "✓ $script PASSED"
        else
            echo "✗ $script FAILED"
            FAILED=$((FAILED + 1))
        fi
    fi
    echo
done

echo "=== Summary ==="
if [ $FAILED -eq 0 ]; then
    echo "All sanity scripts PASSED ✓"
    exit 0
else
    echo "$FAILED sanity script(s) FAILED ✗"
    exit 1
fi
