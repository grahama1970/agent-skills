"""Receipt inventory closure tests for Battle offline verification."""
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


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_extra_retained_output_artifact_fails_even_if_manifest_pass_fields_stay(tmp_path: Path) -> None:
    receipt_path = _receipt(tmp_path)
    extra = tmp_path / "work" / "out" / "case-str" / "corpus" / "extra.txt"
    extra.write_text("unrecorded", encoding="utf-8")

    report = verify_campaign_receipt(receipt_path)

    assert report["passed"] is False
    assert report["artifact_integrity"] == "FAIL"
    assert any("output inventory mismatch" in p and "extra.txt" in p for p in report["problems"])


def test_removed_manifest_entry_fails_as_extra_actual_artifact(tmp_path: Path) -> None:
    receipt_path = _receipt(tmp_path)
    doc = _load(receipt_path)
    removed = doc["output_manifest"].pop()
    _save(receipt_path, doc)

    report = verify_campaign_receipt(receipt_path)

    assert report["passed"] is False
    assert any("output inventory mismatch" in p and removed["path"] in p for p in report["problems"])


def test_duplicate_case_receipts_fail_roster_closure(tmp_path: Path) -> None:
    receipt_path = _receipt(tmp_path)
    doc = _load(receipt_path)
    doc["case_receipts"].append(dict(doc["case_receipts"][0]))
    _save(receipt_path, doc)

    report = verify_campaign_receipt(receipt_path)

    assert report["passed"] is False
    assert any("duplicate receipt case IDs" in p for p in report["problems"])
    assert any("aggregate mismatch cases_total" in p for p in report["problems"])


def test_reassigned_case_receipt_fails_roster_closure(tmp_path: Path) -> None:
    receipt_path = _receipt(tmp_path)
    doc = _load(receipt_path)
    doc["case_receipts"][0]["case_id"] = "other-case"
    _save(receipt_path, doc)

    report = verify_campaign_receipt(receipt_path)

    assert report["passed"] is False
    assert any("case roster mismatch" in p and "other-case" in p for p in report["problems"])


def test_tampered_request_plan_or_counter_fails_verification(tmp_path: Path) -> None:
    receipt_path = _receipt(tmp_path)
    doc = _load(receipt_path)
    doc["request_sha256"] = "sha256:" + "0" * 64
    doc["plan_sha256"] = "sha256:" + "1" * 64
    doc["aggregation"]["cases_total"] = 99
    _save(receipt_path, doc)

    report = verify_campaign_receipt(receipt_path)

    assert report["passed"] is False
    assert any("request_sha256 mismatch" in p for p in report["problems"])
    assert any("plan_sha256 mismatch" in p for p in report["problems"])
    assert any("aggregate mismatch cases_total" in p for p in report["problems"])
