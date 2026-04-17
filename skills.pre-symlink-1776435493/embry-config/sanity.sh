#!/usr/bin/env bash
# Sanity check for embry-config
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

echo "=== embry-config sanity check ==="

# 1. Check SKILL.md exists
echo "1/3 Checking SKILL.md..."
if [[ ! -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "FAIL: SKILL.md not found"
    exit 1
fi

# 2. Check for embry.yaml in common locations
echo "2/3 Checking for embry.yaml..."
EMBRY_YAML=""
for loc in "$PROJECT_ROOT/embry.yaml" "$PROJECT_ROOT/.pi/embry.yaml" "$HOME/.config/embry/embry.yaml"; do
    if [[ -f "$loc" ]]; then
        EMBRY_YAML="$loc"
        echo "  Found: $EMBRY_YAML"
        break
    fi
done

if [[ -z "$EMBRY_YAML" ]]; then
    echo "WARNING: embry.yaml not found in common locations"
    echo "  Skill will work when embry.yaml is created"
fi

# 3. Validate SKILL.md describes expected config sections
echo "3/3 Validating SKILL.md content..."
for section in "version" "services" "persona" "skills"; do
    if ! grep -q "$section" "$SCRIPT_DIR/SKILL.md"; then
        echo "WARNING: SKILL.md does not mention '$section' section"
    fi
done

echo "embry-config sanity check PASSED"
