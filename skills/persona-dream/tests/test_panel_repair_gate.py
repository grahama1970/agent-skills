from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_panel_repair_gate import validate_receipt  # noqa: E402


FIXTURES = ROOT / "scripts/fixtures"


def _load_valid_receipt() -> dict[str, object]:
    return json.loads((FIXTURES / "panel_repair_gate_valid.json").read_text(encoding="utf-8"))


class TestPanelRepairGate(unittest.TestCase):
    def test_provider_eligible_fixture_passes_final_gate(self) -> None:
        receipt = _load_valid_receipt()

        errors = validate_receipt(receipt, require_provider_eligible=True, base_dir=FIXTURES)

        self.assertEqual(errors, [])

    def test_partial_pass_status_is_rejected_as_final_panel_status(self) -> None:
        receipt = _load_valid_receipt()
        receipt["status"] = "PASS_VISUAL_REVIEW"

        errors = validate_receipt(receipt, require_provider_eligible=True, base_dir=FIXTURES)

        self.assertIn("PASS_VISUAL_REVIEW is an intermediate subgate, not a final panel status", errors)

    def test_provider_eligible_receipt_requires_media_probe_receipt(self) -> None:
        receipt = _load_valid_receipt()
        receipt.pop("provider_media_probe_receipt")

        errors = validate_receipt(receipt, require_provider_eligible=True, base_dir=FIXTURES)

        self.assertIn(
            "provider_media_probe_receipt is required when provider_media_status=PASS or provider eligibility is required",
            errors,
        )
        self.assertIn("receipt is not provider eligible", errors)

    def test_failed_media_probe_blocks_provider_eligibility(self) -> None:
        receipt = _load_valid_receipt()
        receipt["provider_media_probe_receipt"] = "panel_repair_gate_artifacts/provider_media_probe_failed.json"

        errors = validate_receipt(receipt, require_provider_eligible=True, base_dir=FIXTURES)

        self.assertIn(
            "provider_media_probe_receipt: provider media probe receipt status must be PASS_PROVIDER_MEDIA_URL_PROBE",
            errors,
        )
        self.assertIn("receipt is not provider eligible", errors)

    def test_nano_banana_fallback_blocks_provider_eligibility(self) -> None:
        receipt = _load_valid_receipt()
        receipt["nano_banana_fallback_used"] = True

        errors = validate_receipt(receipt, require_provider_eligible=True, base_dir=FIXTURES)

        self.assertIn(
            "nano_banana_fallback_used is forbidden for final/provider-eligible panels",
            errors,
        )
        self.assertIn("receipt is not provider eligible", errors)

    def test_gemini_backend_blocks_provider_eligibility(self) -> None:
        receipt = _load_valid_receipt()
        receipt["generation_backend"] = "gemini"

        errors = validate_receipt(receipt, require_provider_eligible=True, base_dir=FIXTURES)

        self.assertIn(
            "generation_backend=gemini is forbidden for final/provider-eligible panels",
            errors,
        )
        self.assertIn("receipt is not provider eligible", errors)

    def test_local_photoreal_candidate_status_does_not_pass_provider_gate(self) -> None:
        receipt = copy.deepcopy(_load_valid_receipt())
        receipt["status"] = "PASS_LOCAL_PHOTOREAL_PROVIDER_MEDIA_READY"
        receipt["provider_eligibility"] = False
        receipt["provider_packet_status"] = "BLOCKED_PROVIDER_GATE"
        receipt["remaining_blockers"] = [
            "live_kling_execution_still_blocked",
            "photoreal_cinematic_panel_regeneration_required",
        ]

        errors = validate_receipt(receipt, require_provider_eligible=True, base_dir=FIXTURES)

        self.assertIn("--require-provider-eligible requires provider_eligibility=true", errors)
        self.assertIn("receipt is not provider eligible", errors)
        self.assertTrue(any(error.startswith("status must be one of") for error in errors))


if __name__ == "__main__":
    unittest.main()
