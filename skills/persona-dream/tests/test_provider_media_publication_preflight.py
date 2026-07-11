from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_provider_media_publication_preflight import validate_provider_media_publication_preflight  # noqa: E402


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _write_preflight_inputs(root: Path) -> tuple[Path, Path]:
    run_root = root / "run-root"
    run_root.mkdir()
    source_image = root / "panel.png"
    source_image.write_bytes(b"panel")
    repair_receipt = root / "panel_repair_gate_receipt.json"
    probe_receipt = root / "provider_media_url_probe_receipt.json"
    work_order = root / "publication_request.json"
    staging = root / "local_staging_receipt.json"
    target_repo_path = "skills/persona-dream/provider_media/run-root/panel_01.png"
    proposed_url = f"https://raw.githubusercontent.com/grahama1970/agent-skills/main/{target_repo_path}"
    locked_sha256 = "sha256:" + hashlib.sha256(source_image.read_bytes()).hexdigest()

    _write_json(repair_receipt, {"status": "BLOCKED_PROVIDER_MEDIA_URLS"})
    _write_json(probe_receipt, {"schema": "persona_dream.provider_media_url_probe_receipt.v1", "status": "BLOCKED"})
    _write_json(
        work_order,
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
                "provider_media_probe_receipt": str(probe_receipt),
                "panel_image": str(source_image),
            },
            "locked_media": {"local_path": str(source_image), "sha256": locked_sha256},
            "proposed_publication": {
                "target_repo_path": target_repo_path,
                "proposed_url": proposed_url,
            },
            "verification_commands": [
                f"./run.sh validate-provider-media-url --url {proposed_url} --expected-sha256 {locked_sha256} --json",
                "./run.sh validate-panel-repair-gate <panel_repair_gate_receipt> --require-provider-eligible",
            ],
        },
    )
    staged_asset = root / "repo" / target_repo_path
    staged_asset.parent.mkdir(parents=True)
    staged_asset.write_bytes(b"panel")
    _write_json(
        staging,
        {
            "schema": "persona_dream.provider_media_local_staging_receipt.v1",
            "status": "PASS_PROVIDER_MEDIA_LOCAL_STAGING",
            "staged_asset_path": str(staged_asset),
            "target_repo_path": target_repo_path,
            "proposed_url": proposed_url,
            "staged_sha256": locked_sha256,
            "does_not_authorize": [
                "git_push",
                "public_upload",
                "provider_readiness",
                "direct_kling_submit",
                "paid_provider_call",
            ],
            "next_required_probe_command": (
                f"./run.sh validate-provider-media-url --url {proposed_url} "
                f"--expected-sha256 {locked_sha256} --json"
            ),
        },
    )
    return work_order, staging


class TestProviderMediaPublicationPreflight(unittest.TestCase):
    def test_preflight_ready_still_blocks_for_publication_authorization(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            work_order, staging = _write_preflight_inputs(Path(tmp))

            result = validate_provider_media_publication_preflight(
                work_order_path=work_order,
                local_staging_receipt_path=staging,
            )

        self.assertEqual(result["status"], "BLOCKED_AWAITING_PUBLICATION_AUTHORIZATION")
        self.assertEqual(result["first_blocker"]["phase"], "provider_media_publication_authorization")
        self.assertTrue(result["preflight_ready"])
        self.assertEqual(result["work_order_validation_status"], "PASS_PROVIDER_MEDIA_PUBLICATION_WORK_ORDER")
        self.assertEqual(result["local_staging_validation_status"], "PASS_PROVIDER_MEDIA_LOCAL_STAGING")
        self.assertIn("direct_kling_submit", result["does_not_authorize"])
        self.assertIn("validate-provider-media-url", result["next_required_probe_command"])

    def test_blocks_when_staged_url_does_not_match_work_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            work_order, staging = _write_preflight_inputs(root)
            staging_doc = json.loads(staging.read_text(encoding="utf-8"))
            staging_doc["proposed_url"] = "https://raw.githubusercontent.com/grahama1970/agent-skills/main/other.png"
            _write_json(staging, staging_doc)

            result = validate_provider_media_publication_preflight(
                work_order_path=work_order,
                local_staging_receipt_path=staging,
            )

        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("staged_url_mismatch", result["first_blocker"]["reason"])


if __name__ == "__main__":
    unittest.main()
