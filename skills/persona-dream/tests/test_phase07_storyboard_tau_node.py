from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase07_storyboard_tau_node as tau_node  # noqa: E402


class TestPhase07StoryboardTauNode(unittest.TestCase):
    def test_post_scillm_json_routes_through_tau_composite(self) -> None:
        # Tau-only routing: _post_scillm_json must delegate to the composite Tau
        # VLM adapter (never POST to scillm directly) and return its OpenAI-shaped
        # response unchanged.
        seen: dict[str, object] = {}

        def fake_post(payload, *, artifact_dir, caller_skill):
            seen["payload"] = payload
            seen["caller_skill"] = caller_skill
            return {"choices": [{"message": {"content": "{}"}}], "_tau_route": "composite"}

        payload = {"model": "gpt-2", "messages": [{"role": "user", "content": []}]}
        with mock.patch.object(tau_node._tau_composite, "post_openai_vlm_via_tau", side_effect=fake_post):
            parsed = tau_node._post_scillm_json(payload)

        self.assertEqual(parsed["choices"][0]["message"]["content"], "{}")
        self.assertIs(seen["payload"], payload)
        self.assertEqual(seen["caller_skill"], "persona-dream-phase07-panel-reviewer")

    def test_post_scillm_json_fails_closed_on_route_error(self) -> None:
        def fake_post(payload, *, artifact_dir, caller_skill):
            raise tau_node._tau_composite.CompositeVlmError("tau route down")

        with mock.patch.object(tau_node._tau_composite, "post_openai_vlm_via_tau", side_effect=fake_post):
            with self.assertRaises(ValueError):
                tau_node._post_scillm_json({"model": "gpt-2", "messages": []})

    def test_purge_invalid_accepted_frames_removes_non_reviewer_acceptance(self) -> None:
        panel = {
            "panel_id": "sb_002",
            "start_frame": {
                "accepted_frame": {
                    "status": "ACCEPTED_START_FRAME",
                    "accepted_by": None,
                    "identity_continuity_review": {"status": "PASS"},
                }
            },
            "end_frame": {
                "accepted_frame": {
                    "status": "ACCEPTED_END_FRAME",
                    "accepted_by": "panel-reviewer",
                    "identity_continuity_review": {"status": "FAIL"},
                }
            },
        }

        changed = tau_node._purge_invalid_accepted_frames(panel)

        self.assertTrue(changed)
        self.assertNotIn("accepted_frame", panel["start_frame"])
        self.assertNotIn("accepted_frame", panel["end_frame"])

    def test_purge_invalid_accepted_frames_keeps_reviewer_pass(self) -> None:
        panel = {
            "panel_id": "sb_001",
            "start_frame": {
                "accepted_frame": {
                    "status": "ACCEPTED_START_FRAME",
                    "accepted_by": "panel-reviewer",
                    "identity_continuity_review": {"status": "PASS"},
                }
            },
            "end_frame": {},
        }

        changed = tau_node._purge_invalid_accepted_frames(panel)

        self.assertFalse(changed)
        self.assertIn("accepted_frame", panel["start_frame"])

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

    def test_provider_route_allows_vlm_reviewer_model_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_dir = root / "artifacts"
            receipts_dir = root / "receipts"
            artifact_dir.mkdir()
            receipts_dir.mkdir()
            payload = {
                "context": {
                    "tau_dag_node": {
                        "agent": "panel-reviewer",
                        "model_policy": {
                            "provider": "codex",
                            "auth": "codex-oauth",
                            "model": "gpt-5.5",
                        },
                        "prompt_contract": {"schema": "tau.prompt_contract.v1"},
                    }
                }
            }

            receipt = tau_node._provider_route_receipt(
                payload,
                role="panel-reviewer",
                artifact_dir=artifact_dir,
                receipts_dir=receipts_dir,
            )

        self.assertEqual(receipt["status"], "PASS")
        self.assertEqual(receipt["blockers"], [])

    def test_provider_route_still_requires_gpt2_creator_model_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact_dir = root / "artifacts"
            receipts_dir = root / "receipts"
            artifact_dir.mkdir()
            receipts_dir.mkdir()
            payload = {
                "context": {
                    "tau_dag_node": {
                        "agent": "panel-creator",
                        "model_policy": {
                            "provider": "codex",
                            "auth": "codex-oauth",
                            "model": "gpt-5.5",
                        },
                        "prompt_contract": {"schema": "tau.prompt_contract.v1"},
                    }
                }
            }

            receipt = tau_node._provider_route_receipt(
                payload,
                role="panel-creator",
                artifact_dir=artifact_dir,
                receipts_dir=receipts_dir,
            )

        self.assertEqual(receipt["status"], "BLOCKED_PROVIDER_ROUTE")
        self.assertIn("model_policy_model_mismatch:gpt-5.5", receipt["blockers"])

    def test_existing_identity_review_must_match_current_reviewer_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            receipt_path = root / "sb_001_start_frame_identity_continuity_review.json"
            receipt_path.write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "model": "gpt-2",
                        "reviewer_source": "tau-panel-reviewer:gpt-2:composite",
                        "model_policy_enforced": True,
                    }
                ),
                encoding="utf-8",
            )
            existing_review = {
                "status": "PASS",
                "model": "gpt-2",
                "reviewer_source": "tau-panel-reviewer:gpt-2:composite",
                "model_policy_enforced": True,
            }

            matches = tau_node._identity_review_receipt_matches_policy(
                existing_review,
                identity_review_policy={"model": "gpt-5.5"},
                receipt_path=receipt_path,
            )

        self.assertFalse(matches)

    def test_targeted_panel_proof_does_not_require_full_storyboard_panel_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packet_path = Path(tmp) / "storyboard_packet.json"
            packet = {
                "schema": "persona_dream.storyboard_packet.v1",
                "duration_seconds": 10,
                "panel_count": 0,
                "generation_scope": {
                    "mode": "failed_unlocked_only",
                    "target_panel_ids": ["sb_001"],
                },
                "panels": [],
            }

            review = tau_node._validate_storyboard_packet(packet, packet_path=packet_path, reviewer=True)

        self.assertNotIn("panel_count_below_minimum:0", review["blockers"])
        self.assertFalse(any(item.startswith("missing_coverage_seed_ids:") for item in review["blockers"]))
        self.assertIn("missing_target_panel_ids:sb_001", review["blockers"])

    def test_full_storyboard_still_requires_minimum_panel_count(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            packet_path = Path(tmp) / "storyboard_packet.json"
            packet = {
                "schema": "persona_dream.storyboard_packet.v1",
                "duration_seconds": 10,
                "panel_count": 0,
                "panels": [],
            }

            review = tau_node._validate_storyboard_packet(packet, packet_path=packet_path, reviewer=True)

        self.assertIn("panel_count_below_minimum:0", review["blockers"])

    def test_panel_identity_contract_is_written_from_required_entities(self) -> None:
        panel = {"required_entities": ["Embry", "Kai", "Lava Reef"]}

        tau_node._ensure_panel_required_identities(panel)

        self.assertEqual(panel["required_identities"], ["Embry", "Kai"])


if __name__ == "__main__":
    unittest.main()
