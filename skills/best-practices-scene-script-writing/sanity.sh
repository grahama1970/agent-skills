#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

python3 - <<'EOF'
import yaml
text = open("SKILL.md").read()
assert text.startswith("---\n")
fm = yaml.safe_load(text.split("---\n")[1])
for f in ("name","description","triggers","provides","composes","complies"):
    assert fm.get(f), f"missing {f}"
assert fm["name"] == "best-practices-scene-script-writing"
assert "best-practices-cinematography" in fm["composes"]
assert "agentic-evals" in fm["composes"]
print("PASS frontmatter")
EOF

# Positive: core rules present
for n in "state verb" "Environment and weather are actors" "interact with the environment" "source and a behavior" "slot budget" "Stillness"; do
  grep -qi "$n" SKILL.md || { echo "FAIL missing: $n"; exit 1; }
done
echo "PASS rules"

# Positive: checklist covers all element classes
for c in Characters Props Environment Weather Creatures Lighting Sound Anti-patterns; do
  grep -q "## $c" references/scene_element_checklist.md || { echo "FAIL checklist missing: $c"; exit 1; }
done
echo "PASS checklist"

# Ownership boundary: no provider mechanics, no camera grammar duplication
if grep -qE "fal_client|frontal_image_url|/v1/videos|start_image_url" SKILL.md; then
  echo "FAIL provider mechanics leaked"; exit 1
fi
if grep -qE "180-degree|shot/reverse-shot" SKILL.md; then
  echo "FAIL camera grammar duplicated from cinematography skill"; exit 1
fi
echo "PASS ownership-boundary"
echo "ALL SANITY PASS"
