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

# Pydantic scene-table gate: positive + 4 ambiguity negative controls
RUN="uv run --with pydantic --with typer python scripts/scene_table.py"
$RUN validate fixtures/scene_table_tea.json | grep -q '"status": "PASS"' || { echo "FAIL positive scene table"; exit 1; }
$RUN render fixtures/scene_table_tea.json | grep -q "steam tears sideways" || { echo "FAIL render"; exit 1; }
python3 - <<'EOF'
import json
base = json.load(open("fixtures/scene_table_tea.json"))
cases = {}
b = json.loads(json.dumps(base)); b["elements"][3]["environment_interaction"] = "looks beautiful and atmospheric"; cases["vague"] = b
b = json.loads(json.dumps(base)); b["elements"][2]["environment_interaction"] = "on table"; cases["thin"] = b
b = json.loads(json.dumps(base)); del b["environment"]["temperature"]; cases["noenv"] = b
b = json.loads(json.dumps(base)); del b["elements"][0]["action"]; cases["noaction"] = b
for name, data in cases.items():
    json.dump(data, open(f"/tmp/scene_sanity_{name}.json", "w"))
EOF
for c in vague thin noenv noaction; do
  if $RUN validate /tmp/scene_sanity_$c.json >/dev/null 2>&1; then
    echo "FAIL ambiguity accepted: $c"; exit 1
  fi
done
echo "PASS scene-table-gate (positive + 4 ambiguity rejections)"
echo "ALL SANITY PASS"
