"""Runner-attested execution provenance tests for Battle receipts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from battle_skill.campaign_contract import run_contract_campaign, verify_campaign_receipt  # noqa: E402
from test_campaign_contract import _clean_target, _profile, _request  # noqa: E402


def _receipt(tmp_path: Path) -> Path:
    _profile()
    run_contract_campaign(_request(tmp_path, _clean_target(tmp_path)))
    return tmp_path / "work" / "receipt.json"


def test_contract_receipt_exposes_runner_attested_execution(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    doc = json.loads(receipt.read_text(encoding="utf-8"))
    report = verify_campaign_receipt(receipt)

    attestations = [case["execution_attestation"] for case in doc["case_receipts"]]
    assert report["passed"] is True, report["problems"]
    assert report["execution_provenance"] == "RUNNER_ATTESTED"
    assert all(item["status"] == "PASS" for item in attestations)
    assert all(item["payload"]["input_manifest_sha256"].startswith("sha256:") for item in attestations)
    assert all(item["payload"]["output_manifest_sha256"].startswith("sha256:") for item in attestations)
    assert all(item["signature"].startswith("hmac-sha256:") for item in attestations)


def test_rewriting_unsigned_execution_fields_cannot_forge_attestation(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    doc = json.loads(receipt.read_text(encoding="utf-8"))
    doc["case_receipts"][0]["execution"]["exit_code"] = 99
    receipt.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")

    report = verify_campaign_receipt(receipt)

    assert report["passed"] is False
    assert any("runner attestation invalid" in problem for problem in report["problems"])


def test_missing_runner_attestation_remains_not_verified(tmp_path: Path) -> None:
    receipt = _receipt(tmp_path)
    doc = json.loads(receipt.read_text(encoding="utf-8"))
    for case in doc["case_receipts"]:
        case["execution_attestation"] = None
    receipt.write_text(json.dumps(doc, indent=2, sort_keys=True), encoding="utf-8")

    report = verify_campaign_receipt(receipt)

    assert report["passed"] is True, report["problems"]
    assert report["execution_provenance"] == "NOT_VERIFIED"
