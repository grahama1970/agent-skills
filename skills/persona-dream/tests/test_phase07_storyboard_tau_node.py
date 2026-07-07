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
    def test_scillm_proxy_key_candidates_include_scillm_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("SCILLM_MASTER_KEY=file-master\n", encoding="utf-8")

            with mock.patch.object(tau_node, "SCILLM_ENV_PATH", env_path), mock.patch.dict(
                "os.environ",
                {"SCILLM_PROXY_KEY": "process-proxy"},
                clear=True,
            ):
                candidates = tau_node._scillm_proxy_key_candidates()

        self.assertEqual(candidates[0], ("env:SCILLM_PROXY_KEY", "process-proxy"))
        self.assertIn((".env:SCILLM_MASTER_KEY", "file-master"), candidates)

    def test_post_scillm_json_retries_scillm_auth_candidates(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return b'{"choices":[{"message":{"content":"{}"}}]}'

        calls = []

        def fake_urlopen(req):
            calls.append(req.get_header("Authorization"))
            if len(calls) == 1:
                raise HTTPError(
                    req.full_url,
                    401,
                    "Unauthorized",
                    hdrs=None,
                    fp=None,
                )
            return FakeResponse()

        with mock.patch.object(
            tau_node,
            "_scillm_proxy_key_candidates",
            return_value=[("bad", "bad-key"), ("good", "good-key")],
        ), mock.patch.object(tau_node.urllib_request, "urlopen", side_effect=fake_urlopen):
            parsed = tau_node._post_scillm_json({"model": "gpt-2", "messages": []})

        self.assertEqual(parsed["choices"][0]["message"]["content"], "{}")
        self.assertEqual(calls, ["Bearer bad-key", "Bearer good-key"])

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


if __name__ == "__main__":
    unittest.main()
