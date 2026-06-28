from __future__ import annotations

import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from build_watch_reference_download_review_approval_receipt import (
    RECEIPT_SCHEMA,
    assert_no_raw_vectors,
    build_receipt,
    load_json,
)


WATCH_ROOT = Path(__file__).resolve().parents[1]
CANARY_MANIFEST = (
    WATCH_ROOT
    / "docs"
    / "architecture"
    / "generated"
    / "bad_santa_marcus_0248_approved_reference_canary"
    / "watch_approved_reference_manifest.bad_santa_marcus.canary.json"
)


def test_canary_manifest_writes_local_artifact_approval_receipts() -> None:
    manifest = load_json(CANARY_MANIFEST)
    receipt = build_receipt(manifest, manifest_path=CANARY_MANIFEST)

    assert receipt["schema"] == RECEIPT_SCHEMA
    assert receipt["status"] == "RECEIPTS_WRITTEN"
    assert receipt["counts"]["reference_count"] == 3
    assert receipt["counts"]["local_artifact_count"] == 3
    assert receipt["counts"]["approved_reference_count"] == 3
    assert receipt["counts"]["canary_approved_reference_count"] == 3
    assert receipt["counts"]["blocked_reference_count"] == 0
    assert receipt["promotion_policy"]["canary_reference_can_promote_identity"] is False

    for item in receipt["reference_receipts"]:
        artifact = item["download_receipt"]["artifact"]
        assert item["download_receipt"]["status"] == "DOWNLOADED_LOCAL_ARTIFACT"
        assert item["source_review_receipt"]["status"] == "SOURCE_REVIEWED_CANARY"
        assert item["approval_receipt"]["status"] == "APPROVED_CANARY_PIPELINE_ONLY"
        assert item["approved_reference_status"] == "APPROVED_FOR_PIPELINE_CANARY_ONLY"
        assert item["identity_promotion_allowed"] is False
        assert "CANARY_REFERENCES_ARE_NOT_INDEPENDENT_PRODUCTION_REFERENCES" in item["promotion_blockers"]
        assert artifact["sha256"] and len(artifact["sha256"]) == 64
        assert artifact["byte_size"] > 0
        assert artifact["media_type"] == "image/png"
        assert artifact["dimensions"]["width"] > 0
        assert artifact["dimensions"]["height"] > 0

    assert_no_raw_vectors(receipt)
