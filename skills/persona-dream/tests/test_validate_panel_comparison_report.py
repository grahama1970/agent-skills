from __future__ import annotations

import hashlib
import json
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from validate_panel_comparison_report import validate_panel_comparison_report  # noqa: E402


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _write_png(path: Path, *, width: int, height: int) -> str:
    raw = b"".join(b"\x00" + (b"\xff\xff\xff" * width) for _ in range(height))
    data = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw))
        + _png_chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _write_status(path: Path, *, bundle_status: str = "BLOCKED") -> None:
    bundle = path.parent / "pipeline_evidence_bundle_validation.json"
    bundle_payload = {
        "schema": "persona_dream.pipeline_evidence_bundle_validation.v1",
        "status": bundle_status,
        "first_blocker": {
            "phase": "provider_media_publication_authorization",
            "reason": "authorization_receipt_required",
        },
        "validations": {
            "panel_comparison_report": {"status": "PASS_PANEL_COMPARISON_REPORT"},
            "pipeline_loop_run": {"status": "PASS_PIPELINE_LOOP_RUN_RECEIPT"},
        },
    }
    _write_json(bundle, bundle_payload)
    _write_json(
        path,
        {
            "schema": "persona_dream.panel_comparison_status.v1",
            "status": "BLOCKED",
            "acceptance_state": "Not asserted by this report.",
            "first_blocker": {
                "phase": "provider_media_publication_authorization",
                "reason": "authorization_receipt_required",
            },
            "policy": {
                "kling_call_allowed": False,
                "nano_banana_final_panel_allowed": False,
            },
            "receipts": {
                "pipeline_evidence_bundle": {
                    "status": "BLOCKED",
                    "path": str(bundle),
                    "first_blocker": {
                        "phase": "provider_media_publication_authorization",
                        "reason": "authorization_receipt_required",
                    },
                    "validation_statuses": {
                        "panel_comparison_report": "PASS_PANEL_COMPARISON_REPORT",
                        "pipeline_loop_run": "PASS_PIPELINE_LOOP_RUN_RECEIPT",
                    },
                },
            },
        },
    )


def _write_report(path: Path, *, image_name: str, sha256: str, forbidden_claim: str = "") -> None:
    path.write_text(
        f"""<!doctype html>
<html><body>
<h1>Panel 01 Comparison</h1>
<p>Real candidate images gathered for visual comparison only; it does not assert final panel acceptance or Kling readiness.</p>
<p>Acceptance state: Not asserted by this report.</p>
<p>status.json first_blocker: provider_media_publication_authorization is BLOCKED.</p>
<p>receipts/pipeline_evidence_bundle_validation.json is the single where-is-stuck artifact.</p>
<p>Nano Banana fallback imagery is non-eligible for final panels.</p>
<p>Next useful action: rerun validation. Do not call Kling.</p>
<p>{forbidden_claim}</p>
<section>
  <article class="candidate">
    <img src="assets/{image_name}" alt="candidate">
    <dl>
      <dt>Dimensions</dt><dd>2 x 1 RGB</dd>
      <dt>SHA-256</dt><dd>{sha256}</dd>
    </dl>
  </article>
</section>
</body></html>
""",
        encoding="utf-8",
    )


class TestValidatePanelComparisonReport(unittest.TestCase):
    def test_valid_report_passes_asset_and_claim_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sha256 = _write_png(root / "assets/panel.png", width=2, height=1)
            _write_status(root / "status.json")
            report = root / "report.html"
            _write_report(report, image_name="panel.png", sha256=sha256)

            result = validate_panel_comparison_report(report)

        self.assertEqual(result["status"], "PASS_PANEL_COMPARISON_REPORT")
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["assets"][0]["sha256"], "sha256:" + sha256)

    def test_missing_image_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _write_status(root / "status.json")
            report = root / "report.html"
            _write_report(report, image_name="missing.png", sha256="0" * 64)

            result = validate_panel_comparison_report(report)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("missing_image_asset", result["first_blocker"]["reason"])

    def test_forbidden_acceptance_claim_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sha256 = _write_png(root / "assets/panel.png", width=2, height=1)
            _write_status(root / "status.json")
            report = root / "report.html"
            _write_report(report, image_name="panel.png", sha256=sha256, forbidden_claim="ready for Kling")

            result = validate_panel_comparison_report(report)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["first_blocker"]["reason"], "forbidden_report_claim:ready for kling")

    def test_bundle_status_mismatch_blocks_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sha256 = _write_png(root / "assets/panel.png", width=2, height=1)
            _write_status(root / "status.json", bundle_status="PASS_PIPELINE_EVIDENCE_BUNDLE")
            report = root / "report.html"
            _write_report(report, image_name="panel.png", sha256=sha256)

            result = validate_panel_comparison_report(report)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertIn("pipeline_evidence_bundle_status_mismatch", result["first_blocker"]["reason"])


if __name__ == "__main__":
    unittest.main()
