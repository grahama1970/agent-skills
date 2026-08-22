#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", required=True)
    parser.add_argument("--status", required=True)
    parser.add_argument("--expected-proof-id", required=True)
    args = parser.parse_args()

    goal_path = Path(args.goal)
    status_path = Path(args.status)
    goal_text = goal_path.read_text(encoding="utf-8")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    proof_id = args.expected_proof_id

    failures: list[str] = []
    if proof_id not in goal_text:
        failures.append(f"goal_missing_{proof_id}")
    if "dream plus Embry's journal/reflection" not in goal_text:
        failures.append("goal_missing_dream_journal_reflection")
    if "answer body" not in goal_text or "unchanged" not in goal_text:
        failures.append("goal_missing_answer_invariance")
    next_step = status.get("next_step") or {}
    if proof_id not in json.dumps(next_step, sort_keys=True):
        failures.append("status_next_step_not_pinned_to_proof_id")
    if "#1179" in str(next_step.get("default", "")):
        failures.append("status_default_still_points_to_1179")
    if status.get("current_phase") != "P2_CORRECTED_GOAL_PAIR_PROOF":
        failures.append("status_current_phase_not_corrected_goal_pair_proof")

    receipt = {
        "schema": "persona_dream.operational_goal_validation.v1",
        "status": "PASS_OPERATIONAL_GOAL_PINNED" if not failures else "FAIL_OPERATIONAL_GOAL_PINNED",
        "proof_id": proof_id,
        "goal": str(goal_path),
        "status_file": str(status_path),
        "failures": failures,
        "mocked": False,
        "live": False,
        "proves": "GOAL.md and CURRENT_STATUS.json point the next deterministic work at PD-CORRECTED-GOAL-V1",
        "does_not_prove": "any live paired dream/journal conversation or Chatterbox delivery effect",
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
