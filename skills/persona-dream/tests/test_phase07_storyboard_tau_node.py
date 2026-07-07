from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase07_storyboard_tau_node as tau_node  # noqa: E402


class TestPhase07StoryboardTauNode(unittest.TestCase):
    def test_reviewer_auth_failure_routes_to_human_repair_not_panel_creator(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            artifact_dir = run_root / "artifacts"
            receipts_dir = run_root / "receipts"
            artifact_dir.mkdir()
            receipts_dir.mkdir()
            packet_path = run_root / "storyboard_packet.json"
            packet = {
                "schema": "persona_dream.storyboard_packet.v1",
                "duration_seconds": 10,
                "panel_count": 0,
                "panels": [],
            }
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            start_payload = {
                "github": {
                    "repo": "grahama1970/agent-skills",
                    "target": str(run_root),
                },
                "goal": {
                    "goal_id": "phase07-auth-regression",
                    "goal_version": 1,
                    "goal_hash": "sha256:phase07-auth-regression",
                },
                "context": {
                    "persona_dream_phase07_storyboard": {
                        "run_id": "phase07-auth-regression",
                        "run_root": str(run_root),
                        "storyboard_packet": str(packet_path),
                    },
                    "tau_dag_node": {
                        "agent": "panel-reviewer",
                        "model_policy": {
                            "provider": "codex",
                            "auth": "codex-oauth",
                            "model": "gpt-2",
                        },
                        "prompt_contract": {"schema": "tau.prompt_contract.v1"},
                    }
                }
            }
            review = {
                "blockers": ["identity review call failed: HTTP Error 401: Unauthorized"],
                "reference_coverage": {},
                "entity_coverage": {},
                "per_panel": [],
            }

            with mock.patch.object(
                tau_node,
                "_promote_reviewer_accepted_frames",
                return_value={"packet_updated": False, "blockers": []},
            ), mock.patch.object(tau_node, "_validate_storyboard_packet", return_value=review):
                handoff = tau_node._run_reviewer(
                    start_payload,
                    artifact_dir,
                    receipts_dir,
                    packet_path,
                    packet,
                    {"run_root": str(run_root)},
                )

            updated_packet = json.loads(packet_path.read_text(encoding="utf-8"))
            self.assertEqual(updated_packet["status"], "AUTH_REPAIR_REQUIRED")
            self.assertFalse(updated_packet["accepted"])
            self.assertTrue(updated_packet["auth_repair_required"])
            self.assertEqual(handoff["result"]["status"], "AUTH_REPAIR_REQUIRED")
            self.assertEqual(handoff["next_agent"]["name"], "human")
            self.assertIn("do not regenerate images", handoff["stop_condition"])


if __name__ == "__main__":
    unittest.main()
