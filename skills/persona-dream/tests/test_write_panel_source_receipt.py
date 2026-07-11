from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_panel_source_receipt import validate_panel_source_receipt  # noqa: E402
from write_panel_source_receipt import derive_panel_source_receipt  # noqa: E402


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


class TestWritePanelSourceReceipt(unittest.TestCase):
    def _write_repair_gate(self, run_root: Path, *, pass_final: bool) -> Path:
        (run_root / "artifacts").mkdir()
        (run_root / "receipts").mkdir()
        image = run_root / "artifacts/panel_001.png"
        image.write_bytes(b"panel-source-image")
        status = "PASS_PANEL_REVIEWED" if pass_final else "BLOCKED_HUMAN_REVIEW_REQUIRED"
        repair = {
            "schema": "persona_dream.panel_repair_gate_receipt.v1",
            "run_id": "fixture",
            "panel_id": "panel_001",
            "status": status,
            "script_coverage_status": "PASS",
            "post_generation_script_coverage_status": "PASS",
            "reference_evidence_status": "PASS",
            "visual_review_status": "PASS",
            "no_overlay_status": "PASS",
            "provider_media_status": "PASS",
            "generated_image_path": str(image),
            "generation_receipt": "receipts/generation_receipt.json",
            "media_hashes": {"panel_001": _sha256(image)},
            "provider_media_sha256": _sha256(image),
            "provider_eligibility": pass_final,
            "provider_packet_status": "PROVIDER_READY" if pass_final else "BLOCKED_PROVIDER_GATE",
            "visual_style_status": "PASS_PHOTOREAL_CINEMATIC",
            "remaining_blockers": [] if pass_final else ["human_review_required"],
            "live_call_performed": False,
            "paid_call_performed": False,
        }
        path = run_root / "receipts/panel_repair_gate_receipt.json"
        path.write_text(json.dumps(repair) + "\n", encoding="utf-8")
        return path

    def test_blocked_repair_gate_derives_blocked_panel_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            repair_gate = self._write_repair_gate(run_root, pass_final=False)

            receipt = derive_panel_source_receipt(repair_gate)

        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("repair_gate_status_not_final_reviewed:BLOCKED_HUMAN_REVIEW_REQUIRED", receipt["blockers"])
        self.assertIn("provider_eligibility_not_true", receipt["blockers"])
        self.assertFalse(receipt["final_panel_eligible"])

    def test_final_repair_gate_derives_valid_panel_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            repair_gate = self._write_repair_gate(run_root, pass_final=True)
            output = run_root / "receipts/panel_source_receipt.json"

            receipt = derive_panel_source_receipt(repair_gate, output=output)
            validation = validate_panel_source_receipt(output, run_root=run_root)

        self.assertEqual(receipt["status"], "PASS_PANEL_SOURCE")
        self.assertEqual(validation["status"], "PASS_PANEL_SOURCE")
        self.assertIsNone(validation["first_blocker"])

    def test_nano_banana_fallback_blocks_derivation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_root = Path(tmp)
            repair_gate = self._write_repair_gate(run_root, pass_final=True)
            doc = json.loads(repair_gate.read_text(encoding="utf-8"))
            doc["nano_banana_fallback_used"] = True
            repair_gate.write_text(json.dumps(doc) + "\n", encoding="utf-8")

            receipt = derive_panel_source_receipt(repair_gate)

        self.assertEqual(receipt["status"], "BLOCKED")
        self.assertIn("nano_banana_fallback_used", receipt["blockers"])
        self.assertFalse(receipt["final_panel_eligible"])


if __name__ == "__main__":
    unittest.main()
