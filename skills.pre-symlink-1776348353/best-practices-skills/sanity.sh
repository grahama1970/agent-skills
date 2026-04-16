#!/usr/bin/env bash
set -eo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== [best-practices-skills] Sanity Check ==="

# Check 1: Required files exist
echo -n "Check 1 - SKILL.md exists: "
if [[ -f "$SCRIPT_DIR/SKILL.md" ]]; then
    echo "PASS"
else
    echo "FAIL: missing SKILL.md"
    exit 1
fi

# Check 2: YAML frontmatter
echo -n "Check 2 - SKILL.md frontmatter: "
if python3 - <<PY >/dev/null 2>&1
from pathlib import Path
import re, sys
text = Path("$SCRIPT_DIR/SKILL.md").read_text(encoding="utf-8", errors="ignore")
ok = re.match(r"\A---\n.*?\n---(?:\n|$)", text, re.S) is not None
sys.exit(0 if ok else 1)
PY
then
    echo "PASS"
else
    echo "FAIL: SKILL.md missing YAML frontmatter"
    exit 1
fi

# Check 3: Frontmatter has required fields (including provides/composes)
echo -n "Check 3 - Frontmatter fields: "
python3 -c "
import sys
import re
text = open('$SCRIPT_DIR/SKILL.md').read()
m = re.match(r'\A---\n(.*?)\n---(?:\n|$)', text, re.S)
if not m:
    print('FAIL: no frontmatter block')
    sys.exit(1)
fm = m.group(1)
for field in ['name:', 'description:', 'provides:', 'composes:']:
    if field not in fm:
        print(f'FAIL: missing {field.rstrip(\":\")} field')
        sys.exit(1)
print('PASS')
" || exit 1

# Check 4: Key sections present
echo -n "Check 4 - Key sections: "
MISSING_SECTIONS=0
for section in "Required structure" "Design patterns" "Checklist" "Anti-patterns" "Composition Frontmatter"; do
    if ! grep -q "$section" "$SCRIPT_DIR/SKILL.md"; then
        echo "WARN: missing section '$section'"
        MISSING_SECTIONS=1
    fi
done
[[ $MISSING_SECTIONS -eq 0 ]] && echo "PASS" || echo "WARN (some sections missing)"

# Check 5: No extra CHANGELOG (README.md allowed for provides: skills)
echo -n "Check 5 - No extra docs: "
EXTRA_DOCS=0
if [[ -f "$SCRIPT_DIR/CHANGELOG.md" ]]; then
    echo "WARN: has CHANGELOG.md (anti-pattern)"
    EXTRA_DOCS=1
fi
[[ $EXTRA_DOCS -eq 0 ]] && echo "PASS"

# Check 6: Machine-parseable rules exist
echo -n "Check 6 - Rules and vocabulary: "
if [[ -f "$SCRIPT_DIR/references/rules.yml" ]] && [[ -f "$SCRIPT_DIR/references/capability_vocabulary.yml" ]]; then
    echo "PASS"
else
    echo "FAIL: missing references/rules.yml or references/capability_vocabulary.yml"
    exit 1
fi

# Check 7: Validator script exists and runs
echo -n "Check 7 - Validator self-check: "
if python3 "$SCRIPT_DIR/scripts/validate_skill.py" "$SCRIPT_DIR" --json >/dev/null 2>&1; then
    echo "PASS"
else
    echo "FAIL: validate_skill.py failed on self"
    exit 1
fi

# Check 8: Strict frontmatter gate over all skill docs (excluding fixtures/worktrees)
echo -n "Check 8 - Strict frontmatter gate: "
SKILLS_ROOT="$(dirname "$SCRIPT_DIR")"
if python3 - "$SKILLS_ROOT" <<'PY'
from pathlib import Path
import re
import sys

skills_root = Path(sys.argv[1])
pattern = re.compile(r"\A---\n.*?\n---(?:\n|$)", re.S)
bad = []

for skill_md in sorted(skills_root.rglob("SKILL.md")):
    rel = skill_md.relative_to(skills_root)
    rel_str = rel.as_posix()
    if "/worktrees/" in rel_str or "/tests/fixtures/" in rel_str:
        continue
    text = skill_md.read_text(encoding="utf-8", errors="ignore")
    if pattern.match(text) is None:
        bad.append(rel_str)

if bad:
    print("FAIL: invalid or missing frontmatter delimiters in:")
    for item in bad:
        print(f"  - {item}")
    sys.exit(1)
PY
then
    echo "PASS"
else
    exit 1
fi

echo ""
echo "Result: PASS"
