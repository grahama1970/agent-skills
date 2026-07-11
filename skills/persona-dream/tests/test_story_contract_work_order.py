from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_story_contract_work_order import validate_story_contract_work_order  # noqa: E402
from write_story_contract_work_order import build_story_contract_work_order  # noqa: E402


def _write_contract(path: Path, **overrides: object) -> None:
    contract = {
        "schema": "persona_dream.story_contract.v1",
        "artifact_id": "fixture_story_contract",
        "status": "GENERATED_UNREVIEWED",
        "created_at": "2026-06-28T20:00:00Z",
        "input_idea_contract": "artifacts/idea_contract.json",
        "seed": "shared dream seed",
        "story": "Horus and Embry review evidence under a void-world patio sky.",
        "target_duration_s": 8.0,
        "speaking_characters": ["horus", "embry"],
    }
    contract.update(overrides)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")


class TestStoryContractWorkOrder(unittest.TestCase):
    def test_story_contract_work_order_captures_review_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            contract = run_root / "story_contract.json"
            output = run_root / "receipts/story_contract_work_order.json"
            _write_contract(contract)

            work_order = build_story_contract_work_order(
                run_root=run_root,
                story_contract=contract,
                created_at="2026-06-28T23:55:00Z",
            )
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(work_order, indent=2) + "\n", encoding="utf-8")
            validation = validate_story_contract_work_order(output)

        self.assertEqual(work_order["status"], "WORK_ORDER_READY_STORY_REVIEW_REQUIRED")
        self.assertEqual(work_order["owner_subagent"], "dreamer")
        self.assertEqual(
            work_order["blocking_validation"]["first_blocker"]["reason"],
            "story_contract_not_accepted:GENERATED_UNREVIEWED",
        )
        self.assertIn("mark_story_accepted_without_review", work_order["forbidden_actions"])
        self.assertEqual(validation["status"], "PASS_STORY_CONTRACT_WORK_ORDER")
        self.assertEqual(validation["current_status"], "GENERATED_UNREVIEWED")
        self.assertEqual(validation["live"], "no")

    def test_story_contract_work_order_validator_rejects_status_only_bypass_missing_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            contract = run_root / "story_contract.json"
            output = run_root / "receipts/story_contract_work_order.json"
            _write_contract(contract)
            work_order = build_story_contract_work_order(run_root=run_root, story_contract=contract)
            work_order["forbidden_actions"].remove("rewrite_status_only_to_bypass_gate")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(work_order, indent=2) + "\n", encoding="utf-8")

            validation = validate_story_contract_work_order(output)

        self.assertEqual(validation["status"], "BLOCKED")
        self.assertIn("rewrite_status_only_to_bypass_gate", validation["first_blocker"]["reason"])


if __name__ == "__main__":
    unittest.main()
