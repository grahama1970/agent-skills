"""Campaign contract tests: run -> receipt -> offline verify, both directions."""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from battle_skill.campaign_contract import (  # noqa: E402
    run_contract_campaign, verify_campaign_receipt, validate_request,
)

JUDGE = str(HERE.parent / "fixtures" / "reference-judges" / "no_data_leak_judge.py")
FN_JUDGE = str(HERE.parent / "fixtures" / "reference-judges" / "functional_anonymize_judge.py")
GEN = str(HERE / "fixtures" / "mini_generator.py")
PROFILE = str(HERE / "fixtures" / "contract_profile.json")


def _profile() -> None:
    Path(PROFILE).write_text(json.dumps({
        "schema": "battle.campaign_profile.v1",
        "profile_id": "test-contract.v1",
        "required_judges": ["security", "functional"],
        "expectation_overrides": {"case-str": "MUST_ACCEPT"},
        "required_case_ids": ["case-str", "case-int"],
    }))


def _request(tmp: Path, target: str) -> dict:
    return {
        "schema": "battle.campaign_request.v1",
        "profile_path": PROFILE,
        "lock_path": PROFILE,  # digest-bound reference; content irrelevant here
        "generator": GEN,
        "judge": JUDGE,
        "functional_judge": FN_JUDGE,
        "target_run_cmd": target,
        "work_root": str(tmp / "work"),
        "gen_params": {},
        "judge_params": {"output_subdir": "corpus"},
    }


CLEAN_TARGET_SCRIPT = """import json, sys, pathlib
src, dst = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
if src.suffix == ".json":
    d = json.loads(src.read_text())
    def rep(v):
        return "Person-A" if v == "5551234567" or v == 5551234567 else v
    if isinstance(d, dict):
        d = {k: rep(v) for k, v in d.items()}
    else:
        d = rep(d)
    dst.write_text(json.dumps(d))
else:
    dst.write_text(src.read_text().replace("5551234567", "Person-A"))
"""


def _clean_target(tmp: Path) -> str:
    # deterministic anonymizing target: replace the value with a stable pseudonym
    script = tmp / "clean_target.py"
    script.write_text(CLEAN_TARGET_SCRIPT)
    return (f"mkdir -p {{output}}/corpus && for f in {{input}}/corpus/*; do "
            f"python3 {script} \"$f\" {{output}}/corpus/$(basename $f); "
            f"done && echo '{{{{\"status\": \"ready\"}}}}' > {{output}}/report.json")


def test_contract_roundtrip_verify_passes(tmp_path: Path):
    _profile()
    request = _request(tmp_path, _clean_target(tmp_path))
    receipt = run_contract_campaign(request)
    assert receipt["verdict"] == "PASS", receipt["aggregation"]
    assert receipt["case_receipts"]
    assert receipt["case_receipts"][0]["schema"] == "battle.case_receipt.v1"
    assert receipt["aggregation"]["schema"] == "battle.campaign_aggregate.v1"
    work = tmp_path / "work"
    assert (work / "receipt.json").is_file()
    report = verify_campaign_receipt(work / "receipt.json")
    assert report["passed"] is True, report["problems"]
    assert report["execution_provenance"] == "RUNNER_ATTESTED"
    assert report["artifact_integrity"] == "PASS" and report["semantic_replay"] == "PASS"


def test_tampered_artifact_fails_verification(tmp_path: Path):
    _profile()
    request = _request(tmp_path, _clean_target(tmp_path))
    run_contract_campaign(request)
    work = tmp_path / "work"
    # tamper one retained output byte
    outs = [p for p in (work / "out").rglob("*.json") if p.is_file()]
    assert outs
    outs[0].write_text(outs[0].read_text() + "tampered")
    report = verify_campaign_receipt(work / "receipt.json")
    assert report["passed"] is False
    assert report["artifact_integrity"] == "FAIL"


def test_verdict_mismatch_fails_verification(tmp_path: Path):
    _profile()
    # destructive target: real verdict FAIL; then tamper receipt verdict to PASS
    request = _request(tmp_path, "mkdir -p {output}/corpus && for f in {input}/corpus/*; do : > {output}/corpus/$(basename $f); done && echo '{{\"status\": \"ready\"}}' > {output}/report.json")
    receipt = run_contract_campaign(request)
    assert receipt["verdict"] == "FAIL"
    work = tmp_path / "work"
    rp = work / "receipt.json"
    doc = json.loads(rp.read_text())
    doc["verdict"] = "PASS"
    rp.write_text(json.dumps(doc))
    report = verify_campaign_receipt(rp)
    assert report["passed"] is False


def test_request_validation_fails_closed(tmp_path: Path):
    try:
        validate_request({"schema": "wrong"})
        assert False, "should have raised"
    except ValueError:
        pass


def test_contract_execution_uses_frozen_plan_without_regenerating(tmp_path: Path):
    _profile()
    counter = tmp_path / "counter.txt"
    gen = tmp_path / "counting_generator.py"
    gen.write_text(f'''
from pathlib import Path

def generate(work_dir, params):
    counter = Path({str(counter)!r})
    count = int(counter.read_text()) if counter.exists() else 0
    counter.write_text(str(count + 1))
    root = Path(work_dir) / "case-str"
    (root / "corpus").mkdir(parents=True, exist_ok=True)
    (root / "policy.json").write_text('{{"version":1,"protected_values":[],"sensitive_values":[{{"rule_id":"r","subject_id":"s","type":"name","value":"5551234567"}}]}}')
    (root / "corpus" / "record.json").write_text('{{"phone":"5551234567"}}')
    yield "case-str", root, "MAY_REJECT"
    root2 = Path(work_dir) / "case-int"
    (root2 / "corpus").mkdir(parents=True, exist_ok=True)
    (root2 / "policy.json").write_text('{{"version":1,"protected_values":[],"sensitive_values":[{{"rule_id":"r","subject_id":"s","type":"name","value":"5551234567"}}]}}')
    (root2 / "corpus" / "record.json").write_text('{{"phone":5551234567}}')
    yield "case-int", root2, "MUST_ACCEPT"
''')
    request = _request(tmp_path, _clean_target(tmp_path))
    request["generator"] = str(gen)
    receipt = run_contract_campaign(request)
    assert receipt["verdict"] == "PASS", receipt["case_receipts"]
    assert counter.read_text() == "1"
