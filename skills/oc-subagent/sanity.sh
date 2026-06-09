#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCILLM_REPO="${SCILLM_REPO:-/home/graham/workspace/experiments/scillm}"

python3 -m py_compile "$SKILL_DIR/scripts/run_mvp_e2e.py"

PERSONA_ROOT="$SKILL_DIR/personas"
SKILLS_ROOT="$(cd "$SKILL_DIR/.." && pwd)"

PERSONA_ROOT="$PERSONA_ROOT" SKILLS_ROOT="$SKILLS_ROOT" python3 - <<'PY'
import os
import re
import sys
import tomllib
from pathlib import Path

import yaml

persona_root = Path(os.environ["PERSONA_ROOT"])
skills_root = Path(os.environ["SKILLS_ROOT"])
errors = []

personas = {}
for d in sorted(p for p in persona_root.iterdir() if p.is_dir()):
    y = d / "persona.yaml"
    t = d / "pyproject.toml"
    if not y.exists():
        errors.append(f"{d.name}: missing persona.yaml")
        continue
    if not t.exists():
        errors.append(f"{d.name}: missing pyproject.toml")
        continue
    try:
        data = yaml.safe_load(y.read_text())
    except Exception as exc:
        errors.append(f"{d.name}: invalid YAML: {exc}")
        continue
    try:
        tomllib.loads(t.read_bytes().decode())
    except Exception as exc:
        errors.append(f"{d.name}: invalid TOML: {exc}")
    pid = data.get("id")
    personas[pid] = data
    if pid != d.name:
        errors.append(f"{d.name}: id {pid!r} must match directory")
    if "skill_help_protocol@v1" not in data.get("protocols", []):
        errors.append(f"{d.name}: missing skill_help_protocol@v1")
    primary_skills = data.get("primary_skills", [])
    if "memory" not in primary_skills:
        errors.append(f"{d.name}: primary_skills must include memory")
    for skill in primary_skills:
        if not (skills_root / skill / "SKILL.md").exists():
            errors.append(f"{d.name}: primary skill {skill!r} missing from skills inventory")
    if "LOCAL_PATH_REDACTED" in y.read_text():
        errors.append(f"{d.name}: contains LOCAL_PATH_REDACTED")
    if re.search(r"allow_raw_helper_prompt|raw_helper_prompt_blob_allowed", y.read_text()):
        errors.append(f"{d.name}: appears to authorize raw helper prompt blobs")

for pid, data in personas.items():
    def walk(obj):
        if isinstance(obj, dict):
            if "helper_agent" in obj:
                yield obj["helper_agent"]
            for value in obj.values():
                yield from walk(value)
        elif isinstance(obj, list):
            for value in obj:
                yield from walk(value)
    for helper in walk(data):
        if helper not in personas:
            errors.append(f"{pid}: helper_agent {helper!r} does not exist")

work_product_owners = {
    "fetcher": {"fetcher"},
    "analytics": {"data-analyst"},
    "lean4-prove": {"theorem-prover"},
    "test-interactions": {"qa-tester"},
    "create-report": {"reporter"},
    "batch-report": {"reporter"},
    "corpus-report": {"reporter"},
    "review-prompt": {"proof-reader"},
    "review-design": {"designer"},
    "create-design-board": {"designer"},
    "doc2qra": {"assurance", "doc-qra"},
    "sparta-review": {"assurance"},
    "qra-review": {"assurance"},
    "sparta-qra-validator-gpt": {"assurance"},
    "review-assurance-case": {"assurance"},
    "create-evidence-case": {"assurance"},
    "create-qras": {"assurance"},
    "cmmc-assessor": {"assurance"},
    "review-sparta": {"cyber-analyst"},
    "reality-check-sparta": {"cyber-analyst"},
    "sparta-stress-test": {"cyber-analyst"},
    "match-requirement": {"cyber-analyst"},
    "monitor-sparta": {"cyber-analyst"},
    "monitor-security": {"cyber-analyst"},
    "ops-runpod": {"devops"},
    "ops-docker": {"devops"},
    "ops-workstation": {"devops"},
    "monitor-workstation": {"devops"},
    "ops-llm": {"devops"},
    "ops-chutes": {"devops"},
    "ops-huggingface": {"devops"},
    "service-status": {"devops"},
    "create-gpt": {"model-trainer"},
    "create-classifier": {"model-trainer"},
    "classifier-lab": {"model-trainer"},
    "classifier-lab-subagent": {"model-trainer"},
    "create-regressor": {"model-trainer"},
    "create-table-classifier": {"model-trainer"},
    "create-intent-map": {"model-trainer"},
    "train-persona": {"model-trainer"},
    "gpt-lab": {"model-trainer"},
    "benchmark-models": {"model-trainer"},
    "prompt-lab": {"model-trainer"},
}
for pid, data in personas.items():
    primary_skills = set(data.get("primary_skills", []))
    for skill, allowed_owners in work_product_owners.items():
        if skill in primary_skills and pid not in allowed_owners:
            errors.append(
                f"{pid}: work-product skill {skill!r} belongs to "
                f"{', '.join(sorted(allowed_owners))}"
            )
    for profile in data.get("domain_persona_profiles", []) or []:
        profile_id = profile.get("id", "<unknown>")
        for skill in profile.get("priority_skills", []) or []:
            allowed_owners = work_product_owners.get(skill)
            if allowed_owners and pid not in allowed_owners:
                errors.append(
                    f"{pid}/{profile_id}: work-product priority skill {skill!r} "
                    f"belongs to {', '.join(sorted(allowed_owners))}"
                )

readme = (persona_root / "README.md").read_text()
if "project agent is the planner" not in readme.lower():
    errors.append("README: missing project-agent boundary")
if "memory-backed domain" not in readme or "profiles" not in readme:
    errors.append("README: missing memory-backed domain profile boundary")

if errors:
    print("persona sanity failed:", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    raise SystemExit(1)
print(f"persona sanity ok ({len(personas)} personas)")
PY

if [[ ! -d "$SCILLM_REPO" ]]; then
  echo "SKIP: SCILLM_REPO not found: $SCILLM_REPO"
  exit 0
fi

cd "$SCILLM_REPO"
pytest -q \
  tests/test_opencode_subagent_persistence_probe.py::test_oc_subagent_persistence_proof_contract_offline \
  tests/test_transport_room_oc_subagent_mvp.py::test_oc_subagent_mvp_transport_room_receipt_contract
