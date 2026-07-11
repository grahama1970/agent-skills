from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from pipeline_loop_run import build_pipeline_loop_run  # noqa: E402
from test_pipeline_loop_status import _write_json, _write_provider_media_rungs  # noqa: E402
from validate_pipeline_loop_run import validate_pipeline_loop_run  # noqa: E402
from write_one_scene_kling_review_packet import install_one_scene_kling_review_packet  # noqa: E402


PNG_BYTES = b"\x89PNG\r\n\x1a\nfixture"


def _write_publication_authorization_pass(run_root: Path, panel_hash: str) -> None:
    target_repo_path = f"skills/persona-dream/provider_media/{run_root.name}/panel_01.png"
    proposed_url = f"https://raw.githubusercontent.com/grahama1970/agent-skills/main/{target_repo_path}"
    _write_json(
        run_root / "receipts/provider_media_publication_authorization.json",
        {
            "schema": "persona_dream.provider_media_publication_authorization_validation.v1",
            "status": "PASS_PROVIDER_MEDIA_PUBLICATION_AUTHORIZATION",
            "first_blocker": None,
            "locked_sha256": panel_hash,
            "proposed_url": proposed_url,
            "authorized_sha256": panel_hash,
            "authorized_url": proposed_url,
            "target_repo_path": target_repo_path,
            "mocked": "yes",
            "live": "no",
        },
    )


class TestPipelineLoopRun(unittest.TestCase):
    def test_runner_stops_at_external_publication_authorization_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            image = run_root / "storyboard/panel_01.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(PNG_BYTES)
            panel_hash = "sha256:" + hashlib.sha256(image.read_bytes()).hexdigest()
            source_receipt = run_root / "work/panel_source_receipt.json"
            repair_receipt = run_root / "work/panel_repair_gate_receipt.json"
            probe_receipt = (
                run_root
                / "storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_fixture/provider_media_url_probe_receipt.json"
            )
            provider_url = "https://raw.githubusercontent.com/grahama1970/agent-skills/main/panel.png"
            aux_dir = run_root / "work/panel_gate_aux"
            aux_paths = {
                "requirement_matrix": aux_dir / "requirement_matrix.json",
                "script_coverage_receipt": aux_dir / "script_coverage_receipt.json",
                "post_generation_script_coverage_receipt": aux_dir / "post_generation_script_coverage_receipt.json",
                "reference_receipt": aux_dir / "reference_receipt.json",
                "generation_receipt": aux_dir / "generation_receipt.json",
                "visual_review_receipt": aux_dir / "visual_review_receipt.json",
                "no_overlay_receipt": aux_dir / "no_overlay_receipt.json",
                "callback_or_polling_plan": aux_dir / "callback_or_polling_plan.json",
                "cost_estimate": aux_dir / "cost_estimate.json",
            }
            for path in aux_paths.values():
                _write_json(path, {"status": "PASS"})
            _write_json(
                aux_paths["visual_review_receipt"],
                {
                    "status": "PASS",
                    "panel_id": "panel_01",
                    "reviewer_source": "panel-reviewer:webgpt-review:fixture",
                    "passed_entities": ["character_horus", "character_embry", "tea_service"],
                    "blocking_findings": [],
                    "checks": {
                        "characters": "PASS",
                        "props": "PASS",
                        "environment": "PASS",
                        "creatures": "PASS",
                        "effects": "PASS",
                        "script_dialogue": "PASS",
                        "scale": "PASS",
                        "motion_cues": "PASS",
                    },
                    "reviewed_image_path": "storyboard/panel_01.png",
                    "hash": panel_hash,
                    "dimensions": {"width": 1280, "height": 720},
                    "timestamp": "2026-06-28T23:45:00Z",
                },
            )
            _write_json(
                source_receipt,
                {
                    "schema": "persona_dream.panel_source_receipt.v1",
                    "run_id": "fixture",
                    "panel_id": "panel_01",
                    "status": "BLOCKED",
                    "image_path": "storyboard/panel_01.png",
                    "sha256": panel_hash,
                    "producer": {
                        "kind": "subagent",
                        "name": "persona-dream-panel-repair-gate",
                        "receipt": str(repair_receipt),
                    },
                    "photoreal_status": "UNKNOWN",
                    "nano_banana_fallback_used": False,
                    "final_panel_eligible": False,
                    "blockers": ["provider_eligibility_not_true"],
                },
            )
            _write_json(
                repair_receipt,
                {
                    "schema": "persona_dream.panel_repair_gate_receipt.v1",
                    "run_id": "fixture",
                    "panel_id": "panel_01",
                    "status": "BLOCKED_PROVIDER_MEDIA_URLS",
                    "provider_media_status": "FAIL",
                    "provider_packet_status": "BLOCKED_PROVIDER_GATE",
                    "provider_eligibility": False,
                    "remaining_blockers": ["provider_media_url_missing"],
                },
            )
            install_one_scene_kling_review_packet(
                run_root=run_root,
                panel_source_receipt=source_receipt,
                panel_repair_gate_receipt=repair_receipt,
            )
            _write_provider_media_rungs(run_root, image, panel_hash, repair_receipt)

            result = build_pipeline_loop_run(
                run_root=run_root,
                direction="backward",
                max_iterations=3,
                generated_at="2026-06-28T23:30:00Z",
            )

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["stop_reason"], "external_action_required")
        self.assertEqual(len(result["iterations"]), 1)
        self.assertEqual(result["active_loop"]["loop"], "provider_media_loop")
        self.assertEqual(result["active_loop"]["phase"], "provider_media_publication_authorization")
        self.assertIs(result["policy"]["kling_call_allowed"], False)
        self.assertIs(result["policy"]["public_upload_allowed_without_explicit_authorization"], False)
        self.assertIs(result["policy"]["nano_banana_final_panel_allowed"], False)
        self.assertIn("authorization receipt", result["next_action"])

    def test_runner_repairs_missing_local_staging_then_stops_at_publication_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "run-root"
            repo_root = root / "repo"
            image = run_root / "storyboard/panel_01.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(PNG_BYTES)
            _write_json(
                run_root / "story_contract.json",
                {
                    "schema": "persona_dream.story_contract.v1",
                    "artifact_id": "fixture_story_contract",
                    "status": "GENERATED_UNREVIEWED",
                    "created_at": "2026-06-28T20:00:00Z",
                    "input_idea_contract": "artifacts/idea_contract.json",
                    "seed": "shared dream seed",
                    "story": "Horus and Embry review evidence under a void-world patio sky.",
                    "target_duration_s": 8.0,
                    "speaking_characters": ["horus", "embry"],
                },
            )
            panel_hash = "sha256:" + hashlib.sha256(image.read_bytes()).hexdigest()
            source_receipt = run_root / "work/panel_source_receipt.json"
            repair_receipt = run_root / "work/panel_repair_gate_receipt.json"
            probe_receipt = (
                run_root
                / "storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_fixture/provider_media_url_probe_receipt.json"
            )
            provider_url = "https://raw.githubusercontent.com/grahama1970/agent-skills/main/panel.png"
            aux_dir = run_root / "work/panel_gate_aux"
            aux_paths = {
                "requirement_matrix": aux_dir / "requirement_matrix.json",
                "script_coverage_receipt": aux_dir / "script_coverage_receipt.json",
                "post_generation_script_coverage_receipt": aux_dir / "post_generation_script_coverage_receipt.json",
                "reference_receipt": aux_dir / "reference_receipt.json",
                "generation_receipt": aux_dir / "generation_receipt.json",
                "visual_review_receipt": aux_dir / "visual_review_receipt.json",
                "no_overlay_receipt": aux_dir / "no_overlay_receipt.json",
                "callback_or_polling_plan": aux_dir / "callback_or_polling_plan.json",
                "cost_estimate": aux_dir / "cost_estimate.json",
            }
            for path in aux_paths.values():
                _write_json(path, {"status": "PASS"})
            _write_json(
                aux_paths["visual_review_receipt"],
                {
                    "status": "PASS",
                    "panel_id": "panel_01",
                    "reviewer_source": "panel-reviewer:webgpt-review:fixture",
                    "passed_entities": ["character_horus", "character_embry", "tea_service"],
                    "blocking_findings": [],
                    "checks": {
                        "characters": "PASS",
                        "props": "PASS",
                        "environment": "PASS",
                        "creatures": "PASS",
                        "effects": "PASS",
                        "script_dialogue": "PASS",
                        "scale": "PASS",
                        "motion_cues": "PASS",
                    },
                    "reviewed_image_path": "storyboard/panel_01.png",
                    "hash": panel_hash,
                    "dimensions": {"width": 1280, "height": 720},
                    "timestamp": "2026-06-28T23:45:00Z",
                },
            )
            _write_json(
                source_receipt,
                {
                    "schema": "persona_dream.panel_source_receipt.v1",
                    "run_id": "fixture",
                    "panel_id": "panel_01",
                    "status": "BLOCKED",
                    "image_path": "storyboard/panel_01.png",
                    "sha256": panel_hash,
                    "producer": {
                        "kind": "subagent",
                        "name": "persona-dream-panel-repair-gate",
                        "receipt": str(repair_receipt),
                    },
                    "photoreal_status": "UNKNOWN",
                    "nano_banana_fallback_used": False,
                    "final_panel_eligible": False,
                    "blockers": ["provider_eligibility_not_true"],
                },
            )
            _write_json(
                repair_receipt,
                {
                    "schema": "persona_dream.panel_repair_gate_receipt.v1",
                    "run_id": "fixture",
                    "panel_id": "panel_01",
                    "status": "BLOCKED_PROVIDER_MEDIA_URLS",
                    "provider_media_status": "FAIL",
                    "provider_packet_status": "BLOCKED_PROVIDER_GATE",
                    "provider_eligibility": False,
                    "remaining_blockers": ["provider_media_url_missing"],
                },
            )
            install_one_scene_kling_review_packet(
                run_root=run_root,
                panel_source_receipt=source_receipt,
                panel_repair_gate_receipt=repair_receipt,
            )
            _write_provider_media_rungs(run_root, image, panel_hash, repair_receipt)
            local_staging_receipt = (
                run_root
                / "storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_local_staging_receipt.json"
            )
            local_staging_receipt.unlink()

            result = build_pipeline_loop_run(
                run_root=run_root,
                direction="backward",
                max_iterations=3,
                repo_root=repo_root,
                generated_at="2026-06-28T23:35:00Z",
            )

            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["stop_reason"], "external_action_required")
            self.assertEqual(len(result["iterations"]), 2)
            self.assertEqual(result["iterations"][0]["active_loop"]["phase"], "provider_media_local_staging")
            self.assertEqual(
                result["iterations"][0]["repair_action"]["status"],
                "WROTE_PROVIDER_MEDIA_LOCAL_STAGING_RECEIPT",
            )
            self.assertEqual(result["iterations"][1]["active_loop"]["phase"], "provider_media_publication_authorization")
            self.assertTrue(local_staging_receipt.exists())
            staged_asset = repo_root / f"skills/persona-dream/provider_media/{run_root.name}/panel_01.png"
            self.assertEqual("sha256:" + hashlib.sha256(staged_asset.read_bytes()).hexdigest(), panel_hash)

    def test_runner_repairs_missing_publication_work_order_and_local_staging(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_root = root / "run-root"
            repo_root = root / "repo"
            image = run_root / "storyboard/panel_01.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(PNG_BYTES)
            panel_hash = "sha256:" + hashlib.sha256(image.read_bytes()).hexdigest()
            source_receipt = run_root / "work/panel_source_receipt.json"
            repair_receipt = run_root / "work/panel_repair_gate_receipt.json"
            _write_json(
                source_receipt,
                {
                    "schema": "persona_dream.panel_source_receipt.v1",
                    "run_id": "fixture",
                    "panel_id": "panel_01",
                    "status": "BLOCKED",
                    "image_path": "storyboard/panel_01.png",
                    "sha256": panel_hash,
                    "producer": {
                        "kind": "subagent",
                        "name": "persona-dream-panel-repair-gate",
                        "receipt": str(repair_receipt),
                    },
                    "photoreal_status": "UNKNOWN",
                    "nano_banana_fallback_used": False,
                    "final_panel_eligible": False,
                    "blockers": ["provider_eligibility_not_true"],
                },
            )
            _write_json(
                repair_receipt,
                {
                    "schema": "persona_dream.panel_repair_gate_receipt.v1",
                    "run_id": "fixture",
                    "panel_id": "panel_01",
                    "status": "BLOCKED_PROVIDER_MEDIA_URLS",
                    "generated_image_path": str(image),
                    "provider_media_status": "FAIL",
                    "provider_packet_status": "BLOCKED_PROVIDER_GATE",
                    "provider_eligibility": False,
                    "provider_media_urls": ["https://blocked.invalid/panel.png"],
                    "media_hashes": {"panel_01": panel_hash},
                    "remaining_blockers": ["provider_media_url_missing"],
                },
            )
            install_one_scene_kling_review_packet(
                run_root=run_root,
                panel_source_receipt=source_receipt,
                panel_repair_gate_receipt=repair_receipt,
            )
            _write_provider_media_rungs(run_root, image, panel_hash, repair_receipt)
            publication_work_order = (
                run_root
                / "storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_publication_request.json"
            )
            local_staging_receipt = (
                run_root
                / "storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_local_staging_receipt.json"
            )
            publication_work_order.unlink()
            local_staging_receipt.unlink()

            result = build_pipeline_loop_run(
                run_root=run_root,
                direction="backward",
                max_iterations=4,
                repo_root=repo_root,
                generated_at="2026-06-28T23:40:00Z",
            )

            self.assertEqual(result["status"], "BLOCKED")
            self.assertEqual(result["stop_reason"], "external_action_required")
            self.assertEqual(len(result["iterations"]), 3)
            self.assertEqual(result["iterations"][0]["active_loop"]["phase"], "provider_media_publication_work_order")
            self.assertEqual(
                result["iterations"][0]["repair_action"]["status"],
                "WROTE_PROVIDER_MEDIA_PUBLICATION_WORK_ORDER",
            )
            self.assertEqual(result["iterations"][1]["active_loop"]["phase"], "provider_media_local_staging")
            self.assertEqual(
                result["iterations"][1]["repair_action"]["status"],
                "WROTE_PROVIDER_MEDIA_LOCAL_STAGING_RECEIPT",
            )
            self.assertEqual(result["iterations"][2]["active_loop"]["phase"], "provider_media_publication_authorization")
            self.assertTrue(publication_work_order.exists())
            self.assertTrue(local_staging_receipt.exists())

    def test_runner_repairs_panel_source_from_provider_eligible_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            image = run_root / "storyboard/panel_01.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(PNG_BYTES)
            _write_json(
                run_root / "story_contract.json",
                {
                    "schema": "persona_dream.story_contract.v1",
                    "artifact_id": "fixture_story_contract",
                    "status": "GENERATED_UNREVIEWED",
                    "created_at": "2026-06-28T20:00:00Z",
                    "input_idea_contract": "artifacts/idea_contract.json",
                    "seed": "shared dream seed",
                    "story": "Horus and Embry review evidence under a void-world patio sky.",
                    "target_duration_s": 8.0,
                    "speaking_characters": ["horus", "embry"],
                },
            )
            panel_hash = "sha256:" + hashlib.sha256(image.read_bytes()).hexdigest()
            source_receipt = run_root / "work/panel_source_receipt.json"
            repair_receipt = run_root / "work/panel_repair_gate_receipt.json"
            probe_receipt = (
                run_root
                / "storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_fixture/provider_media_url_probe_receipt.json"
            )
            provider_url = "https://raw.githubusercontent.com/grahama1970/agent-skills/main/panel.png"
            aux_dir = run_root / "work/panel_gate_aux"
            aux_paths = {
                "requirement_matrix": aux_dir / "requirement_matrix.json",
                "script_coverage_receipt": aux_dir / "script_coverage_receipt.json",
                "post_generation_script_coverage_receipt": aux_dir / "post_generation_script_coverage_receipt.json",
                "reference_receipt": aux_dir / "reference_receipt.json",
                "generation_receipt": aux_dir / "generation_receipt.json",
                "visual_review_receipt": aux_dir / "visual_review_receipt.json",
                "storyboard_panel_receipt": aux_dir / "storyboard_panel_receipt.json",
                "no_overlay_receipt": aux_dir / "no_overlay_receipt.json",
                "callback_or_polling_plan": aux_dir / "callback_or_polling_plan.json",
                "cost_estimate": aux_dir / "cost_estimate.json",
            }
            for path in aux_paths.values():
                _write_json(path, {"status": "PASS"})
            _write_json(
                aux_paths["visual_review_receipt"],
                {
                    "status": "PASS",
                    "panel_id": "panel_01",
                    "reviewer_source": "panel-reviewer:webgpt-review:fixture",
                    "passed_entities": ["character_horus", "character_embry", "tea_service"],
                    "blocking_findings": [],
                    "checks": {
                        "characters": "PASS",
                        "props": "PASS",
                        "environment": "PASS",
                        "creatures": "PASS",
                        "effects": "PASS",
                        "script_dialogue": "PASS",
                        "scale": "PASS",
                        "motion_cues": "PASS",
                    },
                    "reviewed_image_path": "storyboard/panel_01.png",
                    "hash": panel_hash,
                    "dimensions": {"width": 1280, "height": 720},
                    "timestamp": "2026-06-28T23:45:00Z",
                },
            )
            ledger = run_root / "artifacts/panel_continuity_and_repair_ledger.json"
            work_order = run_root / "artifacts/panel_001_work_order.json"
            _write_json(ledger, [{"panel": 1, "visual_review_status": "PASS"}])
            _write_json(work_order, {"panel_id": "panel_01", "owner_subagent": "persona-dream-panel-repair-gate"})
            _write_json(
                aux_paths["storyboard_panel_receipt"],
                {
                    "schema": "persona_dream.storyboard_panel_receipt.v1",
                    "run_id": "fixture",
                    "panel_id": "panel_01",
                    "status": "PANEL_READY_FOR_SOURCE_REVIEW",
                    "timing": {"start_s": 0.0, "end_s": 7.5},
                    "beat": "Opening photoreal two-character patio composition under a void-world sky.",
                    "image": {
                        "path": "storyboard/panel_01.png",
                        "sha256": panel_hash,
                        "width": 1280,
                        "height": 720,
                    },
                    "required_visible_entities": ["character_horus", "character_embry"],
                    "required_props": ["tea_service", "umbrella"],
                    "required_environment": ["void_world_patio"],
                    "required_dynamic_behaviors": ["tea steam curls", "umbrella fabric ripples"],
                    "continuity_ledger": "artifacts/panel_continuity_and_repair_ledger.json",
                    "work_order": "artifacts/panel_001_work_order.json",
                },
            )
            _write_json(
                source_receipt,
                {
                    "schema": "persona_dream.panel_source_receipt.v1",
                    "run_id": "fixture",
                    "panel_id": "panel_01",
                    "status": "BLOCKED",
                    "image_path": "storyboard/panel_01.png",
                    "sha256": panel_hash,
                    "producer": {
                        "kind": "subagent",
                        "name": "persona-dream-panel-repair-gate",
                        "receipt": str(repair_receipt),
                    },
                    "photoreal_status": "UNKNOWN",
                    "nano_banana_fallback_used": False,
                    "final_panel_eligible": False,
                    "blockers": ["stale_panel_source_receipt"],
                },
            )
            _write_json(
                repair_receipt,
                {
                    "schema": "persona_dream.panel_repair_gate_receipt.v1",
                    "run_id": "fixture",
                    "panel_id": "panel_01",
                    "status": "BLOCKED_PROVIDER_MEDIA_URLS",
                    "script_coverage_status": "PASS",
                    "post_generation_script_coverage_status": "PASS",
                    "reference_evidence_status": "PASS",
                    "visual_review_status": "PASS",
                    "no_overlay_status": "PASS",
                    "provider_media_status": "FAIL",
                    "requirement_matrix": str(aux_paths["requirement_matrix"]),
                    "script_coverage_receipt": str(aux_paths["script_coverage_receipt"]),
                    "post_generation_script_coverage_receipt": str(aux_paths["post_generation_script_coverage_receipt"]),
                    "reference_receipt": str(aux_paths["reference_receipt"]),
                    "generation_receipt": str(aux_paths["generation_receipt"]),
                    "visual_review_receipt": str(aux_paths["visual_review_receipt"]),
                    "storyboard_panel_receipt": str(aux_paths["storyboard_panel_receipt"]),
                    "no_overlay_receipt": str(aux_paths["no_overlay_receipt"]),
                    "generated_image_path": str(image),
                    "media_hashes": {"panel_01": panel_hash},
                    "provider_media_sha256": panel_hash,
                    "provider_media_urls": ["https://blocked.invalid/panel.png"],
                    "provider_media_probe_receipt": str(probe_receipt),
                    "provider_eligibility": False,
                    "provider_packet_status": "BLOCKED_PROVIDER_GATE",
                    "provider_mode": "std",
                    "provider_resolution": "720p",
                    "external_task_id": "fixture-panel-01",
                    "callback_or_polling_plan": str(aux_paths["callback_or_polling_plan"]),
                    "cost_estimate": str(aux_paths["cost_estimate"]),
                    "voice_id_status": "SILENT_SCENE",
                    "provider_voice_ids": {},
                    "visual_style_status": "PASS_PHOTOREAL_CINEMATIC",
                    "nano_banana_fallback_used": False,
                    "remaining_blockers": ["provider_media_url_missing"],
                    "live_call_performed": False,
                    "paid_call_performed": False,
                },
            )
            install_one_scene_kling_review_packet(
                run_root=run_root,
                panel_source_receipt=source_receipt,
                panel_repair_gate_receipt=repair_receipt,
            )
            _write_provider_media_rungs(run_root, image, panel_hash, repair_receipt)
            _write_publication_authorization_pass(run_root, panel_hash)
            _write_json(
                probe_receipt,
                {
                    "schema": "persona_dream.provider_media_url_probe_receipt.v1",
                    "status": "PASS_PROVIDER_MEDIA_URL_PROBE",
                    "url": provider_url,
                    "expected_sha256": panel_hash,
                    "observed_sha256": panel_hash,
                    "http_status": 200,
                    "blockers": [],
                    "mocked": "no",
                    "live": "yes",
                },
            )

            result = build_pipeline_loop_run(
                run_root=run_root,
                direction="backward",
                max_iterations=5,
                generated_at="2026-06-28T23:45:00Z",
            )
            refreshed_path = Path(result["iterations"][0]["repair_action"]["output"])
            refreshed = json.loads(refreshed_path.read_text(encoding="utf-8"))
            installed_visual_path = Path(result["iterations"][1]["repair_action"]["output"])
            installed_visual = json.loads(installed_visual_path.read_text(encoding="utf-8"))
            installed_storyboard_path = Path(result["iterations"][2]["repair_action"]["output"])
            installed_storyboard = json.loads(installed_storyboard_path.read_text(encoding="utf-8"))
            story_work_order_exists = (run_root / "receipts/story_contract_work_order.json").exists()

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["iterations"][0]["active_loop"]["phase"], "panel_source_receipt")
        self.assertEqual(
            result["iterations"][0]["repair_action"]["status"],
            "APPLIED_PROVIDER_MEDIA_PUBLIC_PROBE_AND_WROTE_PANEL_SOURCE_RECEIPT",
        )
        self.assertEqual(result["iterations"][0]["repair_action"]["panel_source_status"], "PASS_PANEL_SOURCE")
        self.assertEqual(
            result["iterations"][0]["repair_action"]["provider_media_probe_application"]["status"],
            "APPLIED_PROVIDER_MEDIA_PUBLIC_PROBE",
        )
        self.assertEqual(result["iterations"][1]["active_loop"]["phase"], "visual_review_receipt")
        self.assertEqual(result["iterations"][1]["repair_action"]["status"], "INSTALLED_VISUAL_REVIEW_RECEIPT")
        self.assertEqual(result["iterations"][1]["repair_action"]["validation_status"], "PASS_VISUAL_REVIEW")
        self.assertEqual(result["iterations"][2]["active_loop"]["phase"], "storyboard_panel")
        self.assertEqual(result["iterations"][2]["repair_action"]["status"], "INSTALLED_STORYBOARD_PANEL_RECEIPT")
        self.assertEqual(result["iterations"][2]["repair_action"]["validation_status"], "PASS_STORYBOARD_PANEL")
        self.assertEqual(result["iterations"][3]["active_loop"]["phase"], "story_contract")
        self.assertEqual(result["iterations"][3]["repair_action"]["status"], "WROTE_STORY_CONTRACT_WORK_ORDER")
        self.assertEqual(result["iterations"][3]["repair_action"]["owner_subagent"], "dreamer")
        self.assertEqual(result["stop_reason"], "work_order_written")
        self.assertEqual(refreshed["status"], "PASS_PANEL_SOURCE")
        self.assertTrue(refreshed["final_panel_eligible"])
        self.assertFalse(refreshed["nano_banana_fallback_used"])
        self.assertEqual(installed_visual["status"], "PASS")
        self.assertEqual(installed_storyboard["status"], "PANEL_READY_FOR_SOURCE_REVIEW")
        self.assertTrue(story_work_order_exists)

    def test_validator_accepts_fail_closed_runner_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pipeline_loop_run.json"
            _write_json(
                path,
                {
                    "schema": "persona_dream.pipeline_loop_run.v1",
                    "generated_at": "2026-06-28T23:30:00Z",
                    "run_root": "/tmp/run-root",
                    "direction": "backward",
                    "status": "BLOCKED",
                    "stop_reason": "external_action_required",
                    "active_loop": {
                        "loop": "provider_media_loop",
                        "phase": "provider_media_public_probe",
                        "blocker": "provider_media_public_probe_not_pass:fetch_failed:HTTP Error 404: Not Found",
                        "default_repair": "Publish the exact staged PNG to the approved stable public URL, rerun validate-provider-media-url, then apply the passing probe.",
                        "validator": "validate-provider-media-url",
                        "external_action_required": True,
                    },
                    "iterations": [
                        {
                            "iteration": 1,
                            "status": "BLOCKED",
                            "active_loop": {
                                "loop": "provider_media_loop",
                                "phase": "provider_media_public_probe",
                                "blocker": "provider_media_public_probe_not_pass:fetch_failed:HTTP Error 404: Not Found",
                                "default_repair": "Publish the exact staged PNG to the approved stable public URL, rerun validate-provider-media-url, then apply the passing probe.",
                                "validator": "validate-provider-media-url",
                                "external_action_required": True,
                            },
                            "first_blocker": {"phase": "provider_media_public_probe"},
                            "phase_count": 11,
                            "stop_condition": "External authorization is required before this loop can repair the blocker.",
                        }
                    ],
                    "policy": {
                        "implicit_local_repair_allowed": False,
                        "kling_call_allowed": False,
                        "nano_banana_final_panel_allowed": False,
                        "public_upload_allowed_without_explicit_authorization": False,
                    },
                    "live": "no",
                    "mocked": "no",
                },
            )

            result = validate_pipeline_loop_run(path)

        self.assertEqual(result["status"], "PASS_PIPELINE_LOOP_RUN_RECEIPT")
        self.assertEqual(result["loop"], "provider_media_loop")
        self.assertEqual(result["phase"], "provider_media_public_probe")
        self.assertEqual(result["stop_reason"], "external_action_required")
        self.assertEqual(result["iteration_count"], 1)

    def test_validator_accepts_work_order_written_stop_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pipeline_loop_run.json"
            _write_json(
                path,
                {
                    "schema": "persona_dream.pipeline_loop_run.v1",
                    "generated_at": "2026-06-28T23:50:00Z",
                    "run_root": "/tmp/run-root",
                    "direction": "backward",
                    "status": "BLOCKED",
                    "stop_reason": "work_order_written",
                    "active_loop": {
                        "loop": "story_loop",
                        "phase": "story_contract",
                        "blocker": "story_contract_not_accepted:GENERATED_UNREVIEWED",
                        "default_repair": "Repair or regenerate the story contract from the current upstream idea/memory revision and mark downstream artifacts stale as needed.",
                        "validator": "validate-story-contract",
                        "external_action_required": False,
                    },
                    "iterations": [
                        {
                            "iteration": 1,
                            "status": "BLOCKED",
                            "active_loop": {
                                "loop": "story_loop",
                                "phase": "story_contract",
                                "blocker": "story_contract_not_accepted:GENERATED_UNREVIEWED",
                                "default_repair": "Repair or regenerate the story contract from the current upstream idea/memory revision and mark downstream artifacts stale as needed.",
                                "validator": "validate-story-contract",
                                "external_action_required": False,
                            },
                            "first_blocker": {"phase": "story_contract"},
                            "phase_count": 11,
                            "repair_action": {"status": "WROTE_STORY_CONTRACT_WORK_ORDER"},
                        }
                    ],
                    "policy": {
                        "implicit_local_repair_allowed": False,
                        "kling_call_allowed": False,
                        "nano_banana_final_panel_allowed": False,
                        "public_upload_allowed_without_explicit_authorization": False,
                    },
                    "live": "no",
                    "mocked": "no",
                },
            )

            result = validate_pipeline_loop_run(path)

        self.assertEqual(result["status"], "PASS_PIPELINE_LOOP_RUN_RECEIPT")
        self.assertEqual(result["stop_reason"], "work_order_written")
        self.assertEqual(result["phase"], "story_contract")

    def test_runner_reports_existing_repair_handler_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = build_pipeline_loop_run(
                run_root=Path(tmp),
                direction="backward",
                max_iterations=1,
                generated_at="2026-06-29T00:04:00Z",
            )

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["stop_reason"], "local_repair_blocked")
        self.assertEqual(result["active_loop"]["phase"], "kling_scene_packet")
        self.assertEqual(
            result["iterations"][0]["repair_action"]["reason"],
            "missing_panel_source_receipt_path",
        )

    def test_validator_accepts_local_repair_blocked_stop_reason(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pipeline_loop_run.json"
            _write_json(
                path,
                {
                    "schema": "persona_dream.pipeline_loop_run.v1",
                    "generated_at": "2026-06-29T00:04:00Z",
                    "run_root": "/tmp/run-root",
                    "direction": "backward",
                    "status": "BLOCKED",
                    "stop_reason": "local_repair_blocked",
                    "active_loop": {
                        "loop": "kling_packet_loop",
                        "phase": "kling_scene_packet",
                        "blocker": "missing_artifact",
                        "default_repair": "Regenerate the blocked one-scene Kling review packet with paid_call_authorized=false and stable source_artifacts.",
                        "validator": "validate-run-root --direction backward",
                        "external_action_required": False,
                    },
                    "iterations": [
                        {
                            "iteration": 1,
                            "status": "BLOCKED",
                            "active_loop": {
                                "loop": "kling_packet_loop",
                                "phase": "kling_scene_packet",
                                "blocker": "missing_artifact",
                                "default_repair": "Regenerate the blocked one-scene Kling review packet with paid_call_authorized=false and stable source_artifacts.",
                                "validator": "validate-run-root --direction backward",
                                "external_action_required": False,
                            },
                            "first_blocker": {"phase": "kling_scene_packet"},
                            "phase_count": 1,
                            "repair_action": {
                                "status": "BLOCKED",
                                "phase": "kling_scene_packet",
                                "reason": "missing_panel_source_receipt_path",
                            },
                        }
                    ],
                    "policy": {
                        "implicit_local_repair_allowed": False,
                        "kling_call_allowed": False,
                        "nano_banana_final_panel_allowed": False,
                        "public_upload_allowed_without_explicit_authorization": False,
                    },
                    "live": "no",
                    "mocked": "no",
                },
            )

            result = validate_pipeline_loop_run(path)

        self.assertEqual(result["status"], "PASS_PIPELINE_LOOP_RUN_RECEIPT")
        self.assertEqual(result["stop_reason"], "local_repair_blocked")
        self.assertEqual(result["phase"], "kling_scene_packet")

    def test_runner_writes_dream_packet_work_order_for_beginning_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp) / "one_scene_kling_dry_run"
            shutil.copytree(ROOT / "fixtures/one_scene_kling_dry_run", run_root)

            result = build_pipeline_loop_run(
                run_root=run_root,
                direction="forward",
                max_iterations=2,
                generated_at="2026-06-28T23:58:00Z",
            )
            output = Path(result["iterations"][0]["repair_action"]["output"])
            work_order = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["stop_reason"], "work_order_written")
        self.assertEqual(result["iterations"][0]["active_loop"]["phase"], "dream_packet")
        self.assertEqual(result["iterations"][0]["repair_action"]["status"], "WROTE_DREAM_PACKET_WORK_ORDER")
        self.assertEqual(result["iterations"][0]["repair_action"]["owner_subagent"], "dreamer")
        self.assertFalse(result["iterations"][0]["repair_action"]["packet_exists"])
        self.assertEqual(work_order["status"], "WORK_ORDER_READY_DREAM_PACKET_REQUIRED")
        self.assertIn("fabricate_residue_source_ids", work_order["forbidden_actions"])

    def test_runner_writes_panel_repair_work_order_for_panel_gate_blocker(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            artifacts = run_root / "artifacts"
            receipts = run_root / "receipts"
            artifacts.mkdir()
            receipts.mkdir()
            (artifacts / "contact_sheet.png").write_bytes(PNG_BYTES)
            panel_image = artifacts / "panel_001.png"
            panel_image.write_bytes(b"fixture-panel-image")
            panel_hash = "sha256:" + hashlib.sha256(panel_image.read_bytes()).hexdigest()
            _write_json(
                artifacts / "dream_packet.json",
                {
                    "schema": "persona_dream.packet.v1",
                    "run_id": "fixture-panel-repair",
                    "mode": "static_dream",
                    "persona": {"id": "horus", "display_name": "Horus"},
                    "residue_items": [{"source_id": "fixture-memory-1", "text": "Tea under a void-world sky."}],
                    "dream_prompt": "Dream of a tea table under a void-world sky.",
                    "frame_prompts": [{"frame_id": "frame_001", "prompt": "A cinematic patio tea scene."}],
                    "contact_sheet": "artifacts/contact_sheet.png",
                    "reflection": "The dream maps collaboration to a shared table.",
                },
            )
            _write_json(
                artifacts / "story_contract.json",
                {
                    "schema": "persona_dream.story_contract.v1",
                    "artifact_id": "fixture_story_contract",
                    "status": "ACCEPTED_AUTOMATED",
                    "created_at": "2026-06-28T20:00:00Z",
                    "input_idea_contract": "artifacts/idea_contract.json",
                    "seed": "shared dream seed",
                    "story": "Horus and Embry review evidence under a void-world patio sky.",
                    "target_duration_s": 8.0,
                    "speaking_characters": ["horus", "embry"],
                },
            )
            _write_json(artifacts / "panel_continuity_and_repair_ledger.json", [{"panel": 1, "visual_review_status": "PENDING"}])
            _write_json(artifacts / "panel_001_work_order.json", {"panel_id": "panel_001"})
            _write_json(
                receipts / "storyboard_panel_receipt.json",
                {
                    "schema": "persona_dream.storyboard_panel_receipt.v1",
                    "run_id": "fixture-panel-repair",
                    "panel_id": "panel_001",
                    "status": "PANEL_READY_FOR_SOURCE_REVIEW",
                    "timing": {"start_s": 0.0, "end_s": 7.5},
                    "beat": "Opening photoreal two-character patio composition under a void-world sky.",
                    "image": {"path": "artifacts/panel_001.png", "sha256": panel_hash, "width": 1280, "height": 720},
                    "required_visible_entities": ["character_horus", "character_embry"],
                    "required_props": ["tea_service", "umbrella"],
                    "required_environment": ["void_world_patio"],
                    "required_dynamic_behaviors": ["tea steam curls", "umbrella fabric ripples"],
                    "continuity_ledger": "artifacts/panel_continuity_and_repair_ledger.json",
                    "work_order": "artifacts/panel_001_work_order.json",
                },
            )
            _write_json(
                receipts / "panel_repair_gate_receipt.json",
                {
                    "schema": "persona_dream.panel_repair_gate_receipt.v1",
                    "run_id": "fixture-panel-repair",
                    "panel_id": "panel_001",
                    "status": "BLOCKED_PROVIDER_MEDIA_URLS",
                    "provider_eligibility": False,
                    "provider_packet_status": "BLOCKED_PROVIDER_GATE",
                    "provider_media_status": "FAIL",
                    "remaining_blockers": ["provider_media_url_missing"],
                    "generated_image_path": str(panel_image),
                    "visual_style_status": "PASS_PHOTOREAL_CINEMATIC",
                    "nano_banana_fallback_used": False,
                },
            )

            result = build_pipeline_loop_run(
                run_root=run_root,
                direction="forward",
                max_iterations=2,
                generated_at="2026-06-28T23:59:00Z",
            )
            output = Path(result["iterations"][0]["repair_action"]["output"])
            work_order = json.loads(output.read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["stop_reason"], "work_order_written")
        self.assertEqual(result["iterations"][0]["active_loop"]["phase"], "panel_repair_gate")
        self.assertEqual(result["iterations"][0]["repair_action"]["status"], "WROTE_PANEL_REPAIR_WORK_ORDER")
        self.assertEqual(result["iterations"][0]["repair_action"]["owner_subagent"], "persona-dream-panel-repair-gate")
        self.assertEqual(result["iterations"][0]["repair_action"]["delegated_subagents"], ["panel-creator", "panel-reviewer"])
        self.assertEqual(work_order["status"], "WORK_ORDER_READY")
        self.assertIn("nano_banana_final_panel_generation", work_order["forbidden_actions"])

    def test_runner_installs_blocked_kling_packet_from_panel_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            image = run_root / "storyboard/panel_01.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(PNG_BYTES)
            panel_hash = "sha256:" + hashlib.sha256(image.read_bytes()).hexdigest()
            source_receipt = run_root / "receipts/panel_source_receipt.json"
            repair_receipt = run_root / "receipts/panel_repair_gate_receipt.json"
            _write_json(
                source_receipt,
                {
                    "schema": "persona_dream.panel_source_receipt.v1",
                    "run_id": "fixture-install-kling",
                    "panel_id": "panel_01",
                    "status": "PASS_PANEL_SOURCE",
                    "image_path": "storyboard/panel_01.png",
                    "sha256": panel_hash,
                    "producer": {
                        "kind": "subagent",
                        "name": "persona-dream-panel-repair-gate",
                        "receipt": str(repair_receipt),
                    },
                    "photoreal_status": "PASS_PHOTOREAL_CINEMATIC",
                    "nano_banana_fallback_used": False,
                    "final_panel_eligible": True,
                },
            )
            _write_json(
                repair_receipt,
                {
                    "schema": "persona_dream.panel_repair_gate_receipt.v1",
                    "run_id": "fixture-install-kling",
                    "panel_id": "panel_01",
                    "status": "BLOCKED_PROVIDER_MEDIA_URLS",
                    "provider_eligibility": False,
                    "provider_packet_status": "BLOCKED_PROVIDER_GATE",
                    "provider_media_status": "FAIL",
                    "remaining_blockers": ["provider_media_url_missing"],
                    "generated_image_path": str(image),
                    "visual_style_status": "PASS_PHOTOREAL_CINEMATIC",
                    "nano_banana_fallback_used": False,
                },
            )

            result = build_pipeline_loop_run(
                run_root=run_root,
                direction="backward",
                max_iterations=2,
                generated_at="2026-06-29T00:01:00Z",
            )
            packet_exists = (run_root / "receipts/kling_scene_packet.json").exists()
            lock_exists = (run_root / "receipts/provider_media_lock_receipt.json").exists()
            packet = json.loads((run_root / "receipts/kling_scene_packet.json").read_text(encoding="utf-8"))

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["iterations"][0]["active_loop"]["phase"], "kling_scene_packet")
        self.assertEqual(
            result["iterations"][0]["repair_action"]["status"],
            "INSTALLED_ONE_SCENE_KLING_REVIEW_PACKET",
        )
        self.assertEqual(result["iterations"][1]["active_loop"]["phase"], "provider_media_publication_work_order")
        self.assertTrue(packet_exists)
        self.assertTrue(lock_exists)
        self.assertFalse(packet["paid_call_authorized"])
        self.assertEqual(packet["status"], "BLOCKED")

    def test_runner_repairs_missing_local_media_lock_from_panel_receipts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            image = run_root / "storyboard/panel_01.png"
            image.parent.mkdir(parents=True)
            image.write_bytes(PNG_BYTES)
            panel_hash = "sha256:" + hashlib.sha256(image.read_bytes()).hexdigest()
            source_receipt = run_root / "work/panel_source_receipt.json"
            repair_receipt = run_root / "work/panel_repair_gate_receipt.json"
            _write_json(
                source_receipt,
                {
                    "schema": "persona_dream.panel_source_receipt.v1",
                    "run_id": "fixture-install-lock",
                    "panel_id": "panel_01",
                    "status": "PASS_PANEL_SOURCE",
                    "image_path": "storyboard/panel_01.png",
                    "sha256": panel_hash,
                    "producer": {
                        "kind": "subagent",
                        "name": "persona-dream-panel-repair-gate",
                        "receipt": str(repair_receipt),
                    },
                    "photoreal_status": "PASS_PHOTOREAL_CINEMATIC",
                    "nano_banana_fallback_used": False,
                    "final_panel_eligible": True,
                },
            )
            _write_json(
                repair_receipt,
                {
                    "schema": "persona_dream.panel_repair_gate_receipt.v1",
                    "run_id": "fixture-install-lock",
                    "panel_id": "panel_01",
                    "status": "BLOCKED_PROVIDER_MEDIA_URLS",
                    "provider_eligibility": False,
                    "provider_packet_status": "BLOCKED_PROVIDER_GATE",
                    "provider_media_status": "FAIL",
                    "remaining_blockers": ["provider_media_url_missing"],
                    "generated_image_path": str(image),
                    "visual_style_status": "PASS_PHOTOREAL_CINEMATIC",
                    "nano_banana_fallback_used": False,
                },
            )
            install_one_scene_kling_review_packet(
                run_root=run_root,
                panel_source_receipt=source_receipt,
                panel_repair_gate_receipt=repair_receipt,
            )
            (run_root / "receipts/provider_media_lock_receipt.json").unlink()

            result = build_pipeline_loop_run(
                run_root=run_root,
                direction="backward",
                max_iterations=2,
                generated_at="2026-06-29T00:02:00Z",
            )
            lock_exists = (run_root / "receipts/provider_media_lock_receipt.json").exists()

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["iterations"][0]["active_loop"]["phase"], "local_provider_media_lock")
        self.assertEqual(
            result["iterations"][0]["repair_action"]["status"],
            "INSTALLED_ONE_SCENE_KLING_REVIEW_PACKET",
        )
        self.assertEqual(result["iterations"][1]["active_loop"]["phase"], "provider_media_publication_work_order")
        self.assertTrue(lock_exists)

    def test_validator_rejects_public_upload_policy_true(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pipeline_loop_run.json"
            _write_json(
                path,
                {
                    "schema": "persona_dream.pipeline_loop_run.v1",
                    "status": "BLOCKED",
                    "stop_reason": "external_action_required",
                    "active_loop": {
                        "loop": "provider_media_loop",
                        "phase": "provider_media_public_probe",
                        "blocker": "blocked",
                        "default_repair": "publish",
                        "validator": "validate-provider-media-url",
                        "external_action_required": True,
                    },
                    "iterations": [
                        {
                            "iteration": 1,
                            "status": "BLOCKED",
                            "active_loop": {"phase": "provider_media_public_probe"},
                            "phase_count": 1,
                        }
                    ],
                    "policy": {
                        "implicit_local_repair_allowed": False,
                        "kling_call_allowed": False,
                        "nano_banana_final_panel_allowed": False,
                        "public_upload_allowed_without_explicit_authorization": True,
                    },
                    "live": "no",
                },
            )

            result = validate_pipeline_loop_run(path)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(
            result["first_blocker"]["reason"],
            "policy_must_be_false:public_upload_allowed_without_explicit_authorization",
        )


if __name__ == "__main__":
    unittest.main()
