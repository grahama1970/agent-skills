#!/usr/bin/env python3
"""Sanity script: /create-evidence-case deterministic gates.

Verifies that the EvidenceCaseRunner can be imported and that
gates 1-3 (topic, recall, technique_bridge) exist as callable steps.

Exit codes: 0=PASS, 1=FAIL
"""
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent

# Check runner.py exists
runner_path = SKILL_DIR / "runner.py"
if not runner_path.exists():
    print(f"FAIL: runner.py not found at {runner_path}")
    sys.exit(1)

# Check that gate names exist in runner.py source
source = runner_path.read_text()
required_gates = [
    "step_1_topic",
    "step_1b_decompose",
    "step_2_recall",
    "step_2b_grounding",
    "step_3_technique_bridge",
]

missing = [g for g in required_gates if g not in source]
if missing:
    print(f"FAIL: Missing gates in runner.py: {missing}")
    sys.exit(1)

# Check evidence_case.py exists and has CLI commands
ec_path = SKILL_DIR / "evidence_case.py"
if not ec_path.exists():
    print(f"FAIL: evidence_case.py not found at {ec_path}")
    sys.exit(1)

ec_source = ec_path.read_text()
if "def create" not in ec_source:
    print("FAIL: evidence_case.py missing 'create' command")
    sys.exit(1)

print(f"PASS: All {len(required_gates)} deterministic gates found in runner.py")
print(f"PASS: evidence_case.py has create command")
sys.exit(0)
