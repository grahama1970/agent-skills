#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

# Frontmatter gate: valid YAML, required fields
python3 - <<'EOF'
import yaml
text = open("SKILL.md").read()
assert text.startswith("---\n"), "frontmatter must open on line 1"
fm = yaml.safe_load(text.split("---\n")[1])
for field in ("name", "description", "triggers", "provides", "composes", "complies"):
    assert fm.get(field), f"missing frontmatter field: {field}"
assert fm["name"] == "best-practices-cinematography"
assert "best-practices-skills" in fm["complies"]
assert "best-practices-kling-video" in fm["composes"]
print("PASS frontmatter")
EOF

# Positive control: core grammar rules present
for needle in "180-degree" "shot/reverse-shot" "camera-right" "Motivated lighting" "bind the shoulder to the element" "ONE variable changed"; do
  grep -qi "$needle" SKILL.md references/shot_grammar.md || { echo "FAIL missing: $needle"; exit 1; }
done
echo "PASS grammar-rules"

# Negative control: no provider mechanics leakage (owned by kling-video skill)
if grep -qE "fal_client|start_image_url|frontal_image_url|/v1/videos" SKILL.md; then
  echo "FAIL: provider mechanics leaked into cinematography skill"; exit 1
fi
echo "PASS ownership-boundary"

# Failure-mode table carries dated receipts
grep -q "2026-09-08" references/shot_grammar.md || { echo "FAIL: undated failure modes"; exit 1; }
echo "PASS dated-receipts"
echo "ALL SANITY PASS"
