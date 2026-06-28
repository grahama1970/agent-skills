from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tau_skill.py"
SPEC = importlib.util.spec_from_file_location("tau_skill", MODULE_PATH)
assert SPEC is not None
tau_skill = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(tau_skill)


class TauSkillGoalEvidenceTests(TestCase):
    def test_goal_objective_manifests_include_chat_ui_proof_rungs(self) -> None:
        paths = [
            tau_skill.PROOFS_ROOT
            / "ux-lab-repeatable-same-message-tui-mirror-20260628T232614Z"
            / "manifest.json",
            tau_skill.PROOFS_ROOT
            / "skill-chat-ui-proof-command-20260628T233232Z"
            / "manifest.json",
            tau_skill.PROOFS_ROOT
            / "skill-e2e-include-chat-ui-20260628T233739Z"
            / "manifest.json",
        ]

        rows = tau_skill.goal_objective_manifests(paths)
        keys = {row["goal_evidence_key"] for row in rows}

        self.assertIn("repeatable_chat_tui_mirror", keys)
        self.assertIn("skill_chat_ui_proof_command", keys)
        self.assertIn("e2e_include_chat_ui", keys)


class TauSkillE2eTests(TestCase):
    def test_e2e_include_chat_ui_runs_chat_ui_proof(self) -> None:
        chat_receipt = {
            "schema": "agent_skills.tau.chat_ui_proof_receipt.v1",
            "ok": True,
            "mocked": False,
            "live": True,
            "assertions": {"handoff_visible_in_chat": True},
        }

        with (
            patch.object(tau_skill, "sanity_payload", return_value={"ok": True}),
            patch.object(tau_skill, "status_payload", return_value={"ok": True}),
            patch.object(tau_skill, "chat_ui_proof_payload", return_value=chat_receipt) as proof,
        ):
            receipt = tau_skill.e2e_payload(include_chat_ui=True, chat_ui_timeout_s=12)

        self.assertTrue(receipt["ok"])
        self.assertEqual(receipt["chat_ui"], chat_receipt)
        self.assertEqual(receipt["required_next_for_ui_claims"], [])
        proof.assert_called_once()
        self.assertEqual(proof.call_args.kwargs["timeout_s"], 12)

    def test_e2e_without_chat_ui_keeps_ui_next_step_boundary(self) -> None:
        with (
            patch.object(tau_skill, "sanity_payload", return_value={"ok": True}),
            patch.object(tau_skill, "status_payload", return_value={"ok": True}),
            patch.object(tau_skill, "chat_ui_proof_payload") as proof,
        ):
            receipt = tau_skill.e2e_payload(include_chat_ui=False, chat_ui_timeout_s=12)

        self.assertTrue(receipt["ok"])
        self.assertIsNone(receipt["chat_ui"])
        self.assertTrue(receipt["required_next_for_ui_claims"])
        proof.assert_not_called()
