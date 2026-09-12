"""Portable offline replay package tests for Battle receipts."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from battle_skill.campaign_contract import export_portable_replay_package, run_contract_campaign, verify_campaign_receipt  # noqa: E402
from test_campaign_contract import _clean_target, _profile, _request  # noqa: E402


def _make_receipt(tmp_path: Path) -> Path:
    _profile()
    run_contract_campaign(_request(tmp_path, _clean_target(tmp_path)))
    return tmp_path / "work" / "receipt.json"


def test_portable_replay_survives_move_and_original_workspace_deletion(tmp_path: Path) -> None:
    receipt = _make_receipt(tmp_path)
    package = tmp_path / "portable"
    export = export_portable_replay_package(receipt, package)
    moved = tmp_path / "moved-package"
    shutil.move(str(package), moved)
    shutil.rmtree(tmp_path / "work")

    report = verify_campaign_receipt(moved / "receipt.json")
    replay_receipt = json.loads((moved / "receipt.json").read_text(encoding="utf-8"))

    assert export["status"] == "PASS"
    assert report["passed"] is True, report["problems"]
    assert replay_receipt["request"]["work_root"] == "evidence"
    assert not Path(replay_receipt["request"]["judge"]).is_absolute()
    assert replay_receipt["portable_replay"]["original_work_root"].endswith("work")


def test_portable_replay_missing_package_evidence_does_not_fall_back_to_original(tmp_path: Path) -> None:
    receipt = _make_receipt(tmp_path)
    package = tmp_path / "portable"
    export_portable_replay_package(receipt, package)
    victim = next((package / "evidence" / "out").rglob("*.json"))
    victim.unlink()

    report = verify_campaign_receipt(package / "receipt.json")

    assert report["passed"] is False
    assert report["artifact_integrity"] == "FAIL"
    assert any("output inventory mismatch" in problem or "missing" in problem for problem in report["problems"])


def test_exported_receipt_rewrites_request_and_plan_digests_for_relative_paths(tmp_path: Path) -> None:
    receipt = _make_receipt(tmp_path)
    package = tmp_path / "portable"
    export_portable_replay_package(receipt, package)
    exported = json.loads((package / "receipt.json").read_text(encoding="utf-8"))

    assert exported["request_sha256"].startswith("sha256:")
    assert exported["plan_sha256"].startswith("sha256:")
    assert all(not Path(exported["request"][key]).is_absolute() for key in ("profile_path", "lock_path", "generator", "judge", "functional_judge"))
    assert all(case["input_dir"].startswith("evidence/plan-cases/") for case in exported["plan"]["cases"])
    assert verify_campaign_receipt(package / "receipt.json")["passed"] is True
