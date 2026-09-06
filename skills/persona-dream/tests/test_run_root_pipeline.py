from __future__ import annotations

import json
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_run_root_pipeline import validate_run_root  # noqa: E402
from write_one_scene_kling_review_packet import install_one_scene_kling_review_packet  # noqa: E402

PNG_BYTES = b"\x89PNG\r\n\x1a\nfixture"


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _write_panel_repair_gate_fixture(run_root: Path, panel_hash: str) -> None:
    artifacts = run_root / "receipts/panel_repair_gate_artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    for name in [
        "requirement_matrix.json",
        "generation_receipt.json",
        "callback_or_polling_plan.json",
        "cost_estimate.json",
    ]:
        _write_json(artifacts / name, {"status": "PASS"})
    for name in [
        "script_coverage_receipt.json",
        "post_generation_script_coverage_receipt.json",
        "reference_receipt.json",
        "visual_review_receipt.json",
        "no_overlay_receipt.json",
    ]:
        _write_json(artifacts / name, {"status": "PASS"})
    _write_json(
        artifacts / "provider_media_probe_receipt.json",
        {
            "schema": "persona_dream.provider_media_url_probe_receipt.v1",
            "status": "PASS_PROVIDER_MEDIA_URL_PROBE",
            "url": "https://assets.example.com/persona-dream/panel_001.png",
            "expected_sha256": panel_hash,
            "observed_sha256": panel_hash,
            "http_status": 200,
            "content_length": 12345,
            "mocked": "yes",
            "live": "no",
        },
    )
    _write_json(
        run_root / "receipts/panel_repair_gate_receipt.json",
        {
            "schema": "persona_dream.panel_repair_gate_receipt.v1",
            "run_id": "fixture-complete",
            "panel_id": "panel_001",
            "status": "PASS_PANEL_REVIEWED",
            "script_coverage_status": "PASS",
            "post_generation_script_coverage_status": "PASS",
            "reference_evidence_status": "PASS",
            "visual_review_status": "PASS",
            "no_overlay_status": "PASS",
            "provider_media_status": "PASS",
            "requirement_matrix": "panel_repair_gate_artifacts/requirement_matrix.json",
            "script_coverage_receipt": "panel_repair_gate_artifacts/script_coverage_receipt.json",
            "post_generation_script_coverage_receipt": "panel_repair_gate_artifacts/post_generation_script_coverage_receipt.json",
            "reference_receipt": "panel_repair_gate_artifacts/reference_receipt.json",
            "generation_receipt": "panel_repair_gate_artifacts/generation_receipt.json",
            "visual_review_receipt": "panel_repair_gate_artifacts/visual_review_receipt.json",
            "no_overlay_receipt": "panel_repair_gate_artifacts/no_overlay_receipt.json",
            "provider_media_urls": ["https://assets.example.com/persona-dream/panel_001.png"],
            "provider_media_probe_receipt": "panel_repair_gate_artifacts/provider_media_probe_receipt.json",
            "media_hashes": {"panel_001": panel_hash},
            "provider_mode": "std",
            "provider_resolution": "720p",
            "callback_or_polling_plan": "panel_repair_gate_artifacts/callback_or_polling_plan.json",
            "external_task_id": "fixture-complete-panel-001",
            "voice_id_status": "SILENT_SCENE",
            "provider_voice_ids": {},
            "cost_estimate": "panel_repair_gate_artifacts/cost_estimate.json",
            "provider_packet_status": "PROVIDER_READY",
            "provider_eligibility": True,
            "remaining_blockers": [],
        },
    )


def _write_provider_media_local_staging_receipt(run_root: Path, image_path: Path, panel_hash: str) -> None:
    _write_json(
        run_root
        / "storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_local_staging_receipt.json",
        {
            "schema": "persona_dream.provider_media_local_staging_receipt.v1",
            "status": "PASS_PROVIDER_MEDIA_LOCAL_STAGING",
            "run_id": run_root.name,
            "panel_id": "panel_01",
            "source_path": str(image_path),
            "source_sha256": panel_hash,
            "staged_asset_path": str(image_path),
            "target_repo_path": f"skills/persona-dream/provider_media/{run_root.name}/panel_01.png",
            "staged_sha256": panel_hash,
            "proposed_url": f"https://raw.githubusercontent.com/grahama1970/agent-skills/main/skills/persona-dream/provider_media/{run_root.name}/panel_01.png",
            "does_not_authorize": [
                "git_push",
                "public_upload",
                "provider_readiness",
                "direct_kling_submit",
                "paid_provider_call",
            ],
            "next_required_probe_command": "./run.sh validate-provider-media-url --url https://raw.githubusercontent.com/grahama1970/agent-skills/main/skills/persona-dream/provider_media/run/panel_01.png --expected-sha256 "
            + panel_hash
            + " --json",
        },
    )


def _write_provider_media_publication_work_order(
    run_root: Path,
    image_path: Path,
    panel_hash: str,
    repair_receipt: Path,
) -> None:
    _write_json(
        run_root
        / "storyboard/panel_repair_gate/provider_media_publication_work_orders/panel_01_publication_request.json",
        {
            "schema": "persona_dream.provider_media_publication_work_order.v1",
            "status": "WORK_ORDER_READY_PUBLIC_UPLOAD_AUTH_REQUIRED",
            "authorization_required": [
                "public_upload_of_panel_image",
                "git_commit_and_push_or_equivalent_public_asset_publish",
            ],
            "forbidden_actions": [
                "direct_kling_submit",
                "paid_provider_call",
                "nano_banana_final_panel_generation",
                "gemini_final_panel_generation",
                "provider_readiness_without_live_url_probe",
                "hash_or_receipt_rewrite_without_matching_public_fetch",
            ],
            "source_paths": {
                "run_root": str(run_root),
                "panel_repair_gate_receipt": str(repair_receipt),
                "provider_media_probe_receipt": str(
                    run_root
                    / "storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_fixture/provider_media_url_probe_receipt.json"
                ),
                "panel_image": str(image_path),
            },
            "locked_media": {
                "local_path": str(image_path),
                "sha256": panel_hash,
                "bytes": image_path.stat().st_size,
            },
            "proposed_publication": {
                "method": "git_raw_asset_after_authorized_commit_push",
                "target_repo_path": f"skills/persona-dream/provider_media/{run_root.name}/panel_01.png",
                "proposed_url": f"https://raw.githubusercontent.com/grahama1970/agent-skills/main/skills/persona-dream/provider_media/{run_root.name}/panel_01.png",
                "rollback_path": str(
                    run_root / "storyboard/panel_repair_gate/provider_media_publication_work_orders/rollback"
                ),
            },
            "verification_commands": [
                "./run.sh validate-provider-media-url --url https://raw.githubusercontent.com/grahama1970/agent-skills/main/skills/persona-dream/provider_media/run/panel_01.png --expected-sha256 "
                + panel_hash
                + " --json",
                "./run.sh validate-panel-repair-gate <panel_repair_gate_receipt> --require-provider-eligible",
            ],
            "current_state": {
                "probe_status": "BLOCKED",
                "provider_media_status": "FAIL",
            },
        },
    )


def _write_provider_media_publication_preflight_receipt(run_root: Path, panel_hash: str) -> None:
    target_repo_path = f"skills/persona-dream/provider_media/{run_root.name}/panel_01.png"
    proposed_url = f"https://raw.githubusercontent.com/grahama1970/agent-skills/main/{target_repo_path}"
    _write_json(
        run_root / "receipts/provider_media_publication_preflight.json",
        {
            "schema": "persona_dream.provider_media_publication_preflight_validation.v1",
            "status": "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION",
            "first_blocker": {
                "phase": "provider_media_publication_authorization",
                "reason": "public_upload_or_git_push_authorization_required",
            },
            "preflight_ready": True,
            "staged_asset_path": str(run_root / "storyboard/panel_01.png"),
            "target_repo_path": target_repo_path,
            "proposed_url": proposed_url,
            "locked_sha256": panel_hash,
            "staged_sha256": panel_hash,
            "mocked": "yes",
            "live": "no",
        },
    )


def _write_provider_media_publication_authorization_receipt(run_root: Path, panel_hash: str) -> None:
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


def _write_provider_media_public_probe_receipt(
    run_root: Path,
    panel_hash: str,
    *,
    status: str = "PASS_PROVIDER_MEDIA_URL_PROBE",
    blockers: list[str] | None = None,
) -> None:
    payload: dict[str, object] = {
        "schema": "persona_dream.provider_media_url_probe_receipt.v1",
        "status": status,
        "url": "https://raw.githubusercontent.com/grahama1970/agent-skills/main/skills/persona-dream/provider_media/run/panel_01.png",
        "expected_sha256": panel_hash,
        "observed_sha256": panel_hash if status == "PASS_PROVIDER_MEDIA_URL_PROBE" else None,
        "http_status": 200 if status == "PASS_PROVIDER_MEDIA_URL_PROBE" else None,
        "content_length": 12345 if status == "PASS_PROVIDER_MEDIA_URL_PROBE" else None,
        "blockers": blockers or [],
        "mocked": "yes",
        "live": "no",
    }
    _write_json(
        run_root
        / "storyboard/panel_repair_gate/final_provider_eligibility_work_orders/panel_01_run_fixture/provider_media_url_probe_receipt.json",
        payload,
    )



class TestRunRootPipeline(unittest.TestCase):
    def test_one_scene_fixture_reports_first_missing_upstream_artifact(self) -> None:
        result = validate_run_root(ROOT / "fixtures/one_scene_kling_dry_run")

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["first_blocker"]["phase"], "dream_packet")
        self.assertEqual(result["first_blocker"]["reason"], "missing_artifact")
        self.assertEqual(result["mocked"], "yes")
        self.assertEqual(result["live"], "no")

    def test_one_scene_fixture_backward_reports_missing_publication_work_order_blocker(self) -> None:
        result = validate_run_root(ROOT / "fixtures/one_scene_kling_dry_run", direction="backward")

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["first_blocker"]["phase"], "provider_media_publication_work_order")
        self.assertEqual(result["first_blocker"]["reason"], "missing_artifact")
        self.assertEqual(
            [phase["phase"] for phase in result["phases"][:3]],
            ["kling_scene_packet", "local_provider_media_lock", "provider_media_publication_work_order"],
        )
        self.assertEqual(result["phases"][0]["status"], "PASS")
        self.assertEqual(result["phases"][1]["status"], "PASS")
        self.assertEqual(result["phases"][2]["status"], "BLOCKED")

    def test_installed_blocked_one_scene_packet_walks_back_to_publication_authorization(self) -> None:
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
                    "run_id": "fixture-blocked",
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
                    "run_id": "fixture-blocked",
                    "panel_id": "panel_01",
                    "status": "BLOCKED_PROVIDER_MEDIA_URLS",
                    "provider_eligibility": False,
                    "provider_packet_status": "BLOCKED_PROVIDER_GATE",
                    "remaining_blockers": ["provider_media_url_missing"],
                },
            )

            install_result = install_one_scene_kling_review_packet(
                run_root=run_root,
                panel_source_receipt=source_receipt,
                panel_repair_gate_receipt=repair_receipt,
            )
            _write_provider_media_local_staging_receipt(run_root, image, panel_hash)
            _write_provider_media_public_probe_receipt(
                run_root,
                panel_hash,
                status="BLOCKED",
                blockers=["fetch_failed:HTTP Error 404: Not Found"],
            )
            _write_provider_media_publication_work_order(run_root, image, panel_hash, repair_receipt)
            _write_provider_media_publication_preflight_receipt(run_root, panel_hash)
            result = validate_run_root(run_root, direction="backward")
            forward_result = validate_run_root(run_root)

        self.assertEqual(install_result["status"], "INSTALLED_BLOCKED_REVIEW_PACKET")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["first_blocker"]["phase"], "provider_media_publication_authorization")
        self.assertIn("authorization_receipt_required", result["first_blocker"]["reason"])
        self.assertEqual(result["phases"][0]["status"], "PASS")
        self.assertEqual(result["phases"][1]["status"], "PASS")
        self.assertEqual(result["phases"][2]["phase"], "provider_media_publication_work_order")
        self.assertEqual(result["phases"][2]["status"], "PASS")
        self.assertEqual(result["phases"][3]["phase"], "provider_media_local_staging")
        self.assertEqual(result["phases"][3]["status"], "PASS")
        self.assertEqual(result["phases"][4]["phase"], "provider_media_publication_authorization")
        self.assertEqual(result["phases"][4]["status"], "BLOCKED")
        provider_phase = next(phase for phase in forward_result["phases"] if phase["phase"] == "provider_media_lock")
        self.assertEqual(provider_phase["status"], "BLOCKED")
        self.assertIn("provider_media_url_not_live_accessible", provider_phase["blocker"])

    def test_installed_packet_with_public_probe_reaches_panel_source_blocker(self) -> None:
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
                    "run_id": "fixture-blocked",
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
                    "run_id": "fixture-blocked",
                    "panel_id": "panel_01",
                    "status": "BLOCKED_PROVIDER_MEDIA_URLS",
                    "provider_eligibility": False,
                    "provider_packet_status": "BLOCKED_PROVIDER_GATE",
                    "remaining_blockers": ["provider_media_url_missing"],
                },
            )
            install_one_scene_kling_review_packet(
                run_root=run_root,
                panel_source_receipt=source_receipt,
                panel_repair_gate_receipt=repair_receipt,
            )
            _write_provider_media_local_staging_receipt(run_root, image, panel_hash)
            _write_provider_media_public_probe_receipt(run_root, panel_hash)
            _write_provider_media_publication_work_order(run_root, image, panel_hash, repair_receipt)
            _write_provider_media_publication_preflight_receipt(run_root, panel_hash)
            _write_provider_media_publication_authorization_receipt(run_root, panel_hash)

            result = validate_run_root(run_root, direction="backward")

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["first_blocker"]["phase"], "panel_source_receipt")
        self.assertIn("provider_eligibility_not_true", result["first_blocker"]["reason"])
        self.assertEqual(result["phases"][4]["phase"], "provider_media_publication_authorization")
        self.assertEqual(result["phases"][4]["status"], "PASS")
        self.assertEqual(result["phases"][5]["phase"], "provider_media_public_probe")
        self.assertEqual(result["phases"][5]["status"], "PASS")

    def test_complete_local_dry_run_root_reaches_review_packet_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            (run_root / "artifacts").mkdir()
            (run_root / "receipts").mkdir()

            (run_root / "artifacts/contact_sheet.png").write_bytes(PNG_BYTES)
            (run_root / "artifacts/dream_packet.json").write_text(
                json.dumps(
                    {
                        "schema": "persona_dream.packet.v1",
                        "run_id": "fixture-complete",
                        "mode": "static_dream",
                        "created_at": "2026-06-28T20:00:00Z",
                        "persona": {"id": "horus", "display_name": "Horus"},
                        "secondary_persona": None,
                        "synthetic_content_notice": "Synthetic fixture.",
                        "residue_items": [{"source_id": "fixture-memory-1", "text": "Tea under a void-world sky."}],
                        "contradictions": [],
                        "dream_prompt": "Dream of a tea table under a void-world sky.",
                        "frame_prompts": [{"frame_id": "frame_001", "prompt": "A cinematic patio tea scene."}],
                        "contact_sheet": "artifacts/contact_sheet.png",
                        "reflection": "The dream maps collaboration to a shared table.",
                        "downstream_routes": {},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (run_root / "artifacts/story_contract.json").write_text(
                json.dumps(
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
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            panel_image = run_root / "artifacts/panel_001.png"
            panel_image.write_bytes(b"fixture-panel-image")
            panel_hash = "sha256:" + hashlib.sha256(panel_image.read_bytes()).hexdigest()
            (run_root / "artifacts/panel_continuity_and_repair_ledger.json").write_text(
                json.dumps([{"panel": 1, "visual_review_status": "PENDING"}]) + "\n",
                encoding="utf-8",
            )
            (run_root / "artifacts/panel_001_work_order.json").write_text(
                json.dumps({"panel_id": "panel_001"}) + "\n",
                encoding="utf-8",
            )
            (run_root / "receipts/storyboard_panel_receipt.json").write_text(
                json.dumps(
                    {
                        "schema": "persona_dream.storyboard_panel_receipt.v1",
                        "run_id": "fixture-complete",
                        "panel_id": "panel_001",
                        "status": "PANEL_READY_FOR_SOURCE_REVIEW",
                        "timing": {"start_s": 0.0, "end_s": 0.8},
                        "beat": "Opening two-character table composition under a void-world sky.",
                        "image": {
                            "path": "artifacts/panel_001.png",
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
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            _write_panel_repair_gate_fixture(run_root, panel_hash)

            (run_root / "receipts/visual_review_receipt.json").write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "panel_id": "panel_001",
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
                        "reviewed_image_path": "artifacts/panel_001.png",
                        "hash": panel_hash,
                        "dimensions": {"width": 1280, "height": 720},
                        "timestamp": "2026-06-28T20:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (run_root / "receipts/panel_source_receipt.json").write_text(
                json.dumps(
                    {
                        "schema": "persona_dream.panel_source_receipt.v1",
                        "run_id": "fixture-complete",
                        "panel_id": "panel_001",
                        "status": "PASS_PANEL_SOURCE",
                        "image_path": "artifacts/panel_001.png",
                        "sha256": panel_hash,
                        "producer": {
                            "kind": "subagent",
                            "name": "persona-dream-panel-repair-gate",
                            "receipt": "receipts/panel_repair_gate_receipt.json",
                        },
                        "photoreal_status": "PASS_PHOTOREAL_CINEMATIC",
                        "nano_banana_fallback_used": False,
                        "final_panel_eligible": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            src_packet = ROOT / "fixtures/one_scene_kling_dry_run/receipts/kling_scene_packet.json"
            packet = json.loads(src_packet.read_text(encoding="utf-8"))
            for index, item in enumerate(packet["provider_dry_run_fields"]["image_list"], start=1):
                item["image"] = f"https://assets.example.com/persona-dream/image_{index}.png"
            (run_root / "receipts/kling_scene_packet.json").write_text(
                json.dumps(packet, indent=2) + "\n",
                encoding="utf-8",
            )

            result = validate_run_root(run_root)

        self.assertEqual(result["status"], "DRY_RUN_REVIEW_PACKET_READY")
        self.assertIsNone(result["first_blocker"])
        self.assertEqual(
            [phase["phase"] for phase in result["phases"]],
            [
                "dream_packet",
                "story_contract",
                "storyboard_panel",
                "panel_repair_gate",
                "panel_source_receipt",
                "visual_review_receipt",
                "provider_media_lock",
                "kling_scene_packet",
            ],
        )
        self.assertTrue(all(phase["status"] == "PASS" for phase in result["phases"]))
        self.assertEqual(result["live"], "no")

    def test_invalid_story_contract_blocks_story_contract_phase(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            (run_root / "artifacts").mkdir()
            (run_root / "receipts").mkdir()
            (run_root / "artifacts/contact_sheet.png").write_bytes(PNG_BYTES)
            (run_root / "artifacts/dream_packet.json").write_text(
                json.dumps(
                    {
                        "schema": "persona_dream.packet.v1",
                        "run_id": "fixture-invalid-story",
                        "mode": "static_dream",
                        "created_at": "2026-06-28T20:00:00Z",
                        "persona": {"id": "horus", "display_name": "Horus"},
                        "secondary_persona": None,
                        "synthetic_content_notice": "Synthetic fixture.",
                        "residue_items": [{"source_id": "fixture-memory-1", "text": "Tea under a void-world sky."}],
                        "contradictions": [],
                        "dream_prompt": "Dream of a tea table under a void-world sky.",
                        "frame_prompts": [{"frame_id": "frame_001", "prompt": "A cinematic patio tea scene."}],
                        "contact_sheet": "artifacts/contact_sheet.png",
                        "reflection": "The dream maps collaboration to a shared table.",
                        "downstream_routes": {},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            (run_root / "artifacts/story_contract.json").write_text(
                json.dumps(
                    {
                        "schema": "persona_dream.story_contract.v1",
                        "artifact_id": "fixture_story_contract",
                        "status": "ACCEPTED_AUTOMATED",
                        "created_at": "2026-06-28T20:00:00Z",
                        "seed": "shared dream seed",
                        "story": "Missing the required input idea contract.",
                        "target_duration_s": 8.0,
                        "speaking_characters": ["horus", "embry"],
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            result = validate_run_root(run_root)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["first_blocker"]["phase"], "story_contract")
        self.assertEqual(
            result["first_blocker"]["reason"],
            "schema_validation:pydantic missing at ['input_idea_contract']: Field required",
        )


if __name__ == "__main__":
    unittest.main()
