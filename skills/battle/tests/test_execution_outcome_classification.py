"""Execution outcome classification tests for Battle campaign receipts."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from battle_skill.invariant_campaign import SAFE_REJECTION_MARKER, _execution_kind, run_campaign  # noqa: E402
from battle_skill.production_adapter import run_production_round  # noqa: E402
from test_campaign_contract import _clean_target, _request  # noqa: E402
from test_production_adapter import AUTH, TARGET, _enrollment  # noqa: E402

JUDGE = str(HERE.parent / "fixtures" / "reference-judges" / "no_data_leak_judge.py")
FN_JUDGE = str(HERE.parent / "fixtures" / "reference-judges" / "functional_anonymize_judge.py")
PROFILE = str(HERE / "fixtures" / "contract_profile.json")


def _write_profile(required: list[str], overrides: dict[str, str] | None = None) -> None:
    Path(PROFILE).write_text(json.dumps({
        "schema": "battle.campaign_profile.v1",
        "profile_id": "execution-classification.v1",
        "required_judges": ["security", "functional"],
        "expectation_overrides": overrides or {},
        "required_case_ids": required,
    }), encoding="utf-8")


def _two_case_generator(path: Path) -> str:
    path.write_text('''
from pathlib import Path

def case(root, name, value):
    d = root / name
    (d / "corpus").mkdir(parents=True, exist_ok=True)
    (d / "policy.json").write_text('{"version":1,"protected_values":[],"sensitive_values":[{"rule_id":"r","subject_id":"s","type":"name","value":"5551234567"}]}')
    (d / "corpus" / "record.txt").write_text(value)
    return d

def generate(work_dir, params):
    root = Path(work_dir)
    yield "must-accept", case(root, "must-accept", "5551234567"), "MUST_ACCEPT"
    yield "must-reject", case(root, "must-reject", "5551234567"), "MUST_REJECT"
''', encoding="utf-8")
    return str(path)


def _target_for_safe_reject(tmp_path: Path) -> str:
    script = tmp_path / "target.py"
    script.write_text(f'''
import pathlib, shutil, sys
src = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2])
if "must-reject" in str(src):
    print("{SAFE_REJECTION_MARKER}", file=sys.stderr)
    raise SystemExit(78)
(out / "corpus").mkdir(parents=True, exist_ok=True)
for f in (src / "corpus").iterdir():
    (out / "corpus" / f.name).write_text(f.read_text().replace("5551234567", "Person-A"))
(out / "report.json").write_text('{{"status":"ready"}}')
''', encoding="utf-8")
    return f"python3 {script} {{input}} {{output}}"


def test_docker_invocation_exit_codes_are_launch_errors() -> None:
    assert _execution_kind(125, False) == "LAUNCH_ERROR"
    assert _execution_kind(126, False) == "LAUNCH_ERROR"
    assert _execution_kind(127, False) == "LAUNCH_ERROR"


def test_must_reject_requires_contract_rejection_marker(tmp_path: Path) -> None:
    _write_profile(["must-accept", "must-reject"])
    r = run_campaign(_two_case_generator(tmp_path / "gen.py"), "exit 1", JUDGE, output_subdir="corpus", profile=json.loads(Path(PROFILE).read_text()), functional_judge=FN_JUDGE)

    reject = next(c for c in r.case_receipts if c["case_id"] == "must-reject")
    assert r.passed is False
    assert reject["execution"]["kind"] == "CRASH"
    assert reject["rejection"]["predicate_verified"] is False
    assert any("unverified-rejection:CRASH" in v for f in r.failures for v in f["violations"])


def test_contract_verified_rejection_can_satisfy_must_reject(tmp_path: Path) -> None:
    _write_profile(["must-accept", "must-reject"])
    r = run_campaign(
        _two_case_generator(tmp_path / "gen.py"),
        _target_for_safe_reject(tmp_path),
        JUDGE,
        output_subdir="corpus",
        profile=json.loads(Path(PROFILE).read_text()),
        functional_judge=FN_JUDGE,
    )

    reject = next(c for c in r.case_receipts if c["case_id"] == "must-reject")
    assert r.passed is True, r.failures
    assert reject["execution"]["kind"] == "CONTRACT_REJECT"
    assert reject["rejection"] == {"code": SAFE_REJECTION_MARKER, "permitted": True, "predicate_verified": True}


def test_launch_error_is_not_counted_as_target_launch(tmp_path: Path) -> None:
    _write_profile(["case-str", "case-int"], {"case-str": "MUST_ACCEPT"})
    base = _request(tmp_path, "exit 125")
    result = run_production_round({
        "schema": "battle.production_adapter_request.v1",
        "authorization_manifest": AUTH,
        "expected_target": TARGET,
        "project_contract_enrollment": str(_enrollment(tmp_path / "enrollment.json")),
        "base_request": base,
    })

    assert result["status"] == "FAIL"
    assert result["target_launches"] == 0
    assert result["campaign"]["aggregation"]["execution_failure_count"] == 2
    assert {c["execution"]["kind"] for c in result["campaign"]["case_receipts"]} == {"LAUNCH_ERROR"}


def test_incomplete_capture_is_not_safe_rejection(tmp_path: Path) -> None:
    _write_profile(["case-str", "case-int"], {"case-str": "MUST_ACCEPT"})
    request = _request(tmp_path, "true")
    receipt = run_production_round({
        "schema": "battle.production_adapter_request.v1",
        "authorization_manifest": AUTH,
        "expected_target": TARGET,
        "project_contract_enrollment": str(_enrollment(tmp_path / "enrollment.json")),
        "base_request": request,
    })

    assert receipt["status"] == "FAIL"
    assert {c["execution"]["kind"] for c in receipt["campaign"]["case_receipts"]} == {"INCOMPLETE_CAPTURE"}
