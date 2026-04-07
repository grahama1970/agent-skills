#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CANONICAL_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
SIZE_LIMIT_MB=100

echo "=== Skills Broadcast Sanity ==="

PASS=0
FAIL=0

# Check 1: Required files
for f in SKILL.md run.sh; do
    if [[ -f "$SCRIPT_DIR/$f" ]]; then
        echo "  [PASS] $f exists"
        PASS=$((PASS + 1))
    else
        echo "  [FAIL] $f missing"
        FAIL=$((FAIL + 1))
    fi
done

# Check 2: run.sh is executable
if [[ -x "$SCRIPT_DIR/run.sh" ]]; then
    echo "  [PASS] run.sh is executable"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] run.sh is not executable"
    FAIL=$((FAIL + 1))
fi

# Check 3: Safety — no rsync --delete in actual commands (ignore comments)
if grep -v '^\s*#' "$SCRIPT_DIR/run.sh" | grep -q -- '--delete'; then
    echo "  [FAIL] run.sh contains --delete flag (DANGEROUS)"
    FAIL=$((FAIL + 1))
else
    echo "  [PASS] No --delete flag in commands"
    PASS=$((PASS + 1))
fi

# Check 4: Uses symlinks (not rsync copying)
if grep -q 'ln -sfn' "$SCRIPT_DIR/run.sh"; then
    echo "  [PASS] Symlink-based approach"
    PASS=$((PASS + 1))
else
    echo "  [WARN] No symlink creation found"
    PASS=$((PASS + 1))
fi

# Check 5: Canonical dir has enough skills
skill_count=$(find "$CANONICAL_DIR" -maxdepth 2 -name "SKILL.md" 2>/dev/null | wc -l)
if [[ "$skill_count" -ge 20 ]]; then
    echo "  [PASS] Canonical has $skill_count skills"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] Canonical only has $skill_count skills (expected 20+)"
    FAIL=$((FAIL + 1))
fi

# Check 6: Registry file readable
REGISTRY_FILE="$HOME/.agent_skills_targets"
if [[ -f "$REGISTRY_FILE" ]]; then
    target_count=$(wc -l < "$REGISTRY_FILE")
    echo "  [PASS] Registry: $target_count targets"
    PASS=$((PASS + 1))
else
    echo "  [WARN] No registry file"
    PASS=$((PASS + 1))
fi

# Check 7: Heavy artifact policy enforcement
echo "  Scanning for oversized skill directories (>${SIZE_LIMIT_MB}MB)..."
violations=0
while IFS= read -r skill_dir; do
    [[ ! -d "$skill_dir" ]] && continue
    skill_name="$(basename "$skill_dir")"
    for subdir in models rvc outputs logs data weights checkpoints artifacts extracted_runs work sessions papers datasets; do
        target="$skill_dir/$subdir"
        if [[ -d "$target" && ! -L "$target" ]]; then
            size_mb=$(du -sm "$target" 2>/dev/null | cut -f1)
            if [[ "$size_mb" -gt "$SIZE_LIMIT_MB" ]]; then
                echo "  [FAIL] ${skill_name}/${subdir}: ${size_mb}MB (not symlinked to 12TB)"
                violations=$((violations + 1))
            fi
        fi
    done
done < <(find "$CANONICAL_DIR" -maxdepth 1 -mindepth 1 -type d)

if [[ "$violations" -gt 0 ]]; then
    echo "  [FAIL] $violations artifact policy violations"
    FAIL=$((FAIL + 1))
else
    echo "  [PASS] No oversized artifacts on home drive"
    PASS=$((PASS + 1))
fi

# Check 8: Dry-run smoke test
if "$SCRIPT_DIR/run.sh" status >/dev/null 2>&1; then
    echo "  [PASS] run.sh status executes"
    PASS=$((PASS + 1))
else
    echo "  [FAIL] run.sh status failed"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "Result: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && echo "Result: PASS" || echo "Result: FAIL"
exit "$FAIL"
