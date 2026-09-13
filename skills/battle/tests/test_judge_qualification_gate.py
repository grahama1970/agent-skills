"""Ranked production campaigns require exact Judge qualification."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from battle_skill.production_adapter import run_production_round  # noqa: E402
from battle_skill.qualify_judges import qualify  # noqa: E402
from test_campaign_contract import FN_JUDGE, JUDGE, _clean_target, _profile, _request  # noqa: E402
from test_production_adapter import AUTH, TARGET, _enrollment  # noqa: E402


INTERPRETATION = {"output_subdir": "corpus"}


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _lock(path: Path, *, digest: str = "sha256:" + "1" * 64) -> Path:
    path.write_text(json.dumps({
        "schema": "battle.evaluator_lock.v1",
        "source_repo": "battle-test",
        "commit": "test",
        "bundle_files": ["judge.py"],
        "bundle_manifest_sha256": digest,
    }), encoding="utf-8")
    return path


def _evaluator_image(lock_path: Path) -> str:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    return f"{lock['source_repo']}@{lock['commit']}:{lock['bundle_manifest_sha256']}"


def _ctl_dir(root: Path, name: str, out_text: bytes, in_text: bytes = b"note: Mara Ellison ok\n") -> Path:
    d = root / name
    (d / "in" / "corpus").mkdir(parents=True)
    (d / "out" / "corpus").mkdir(parents=True)
    (d / "policy.json").write_text(json.dumps({"sensitive_values": [
        {"rule_id": "r", "subject_id": "s", "type": "name", "value": "Mara Ellison"}]}))
    (d / "in" / "corpus" / "a.txt").write_bytes(in_text)
    (d / "out" / "corpus" / "a.txt").write_bytes(out_text)
    (d / "out" / "report.json").write_text(json.dumps({"status": "ready"}))
    return d


def _manifest(root: Path) -> Path:
    good = _ctl_dir(root, "good", b"note: Person-A ok\n")
    leak = _ctl_dir(root, "leak", b"note: Mara Ellison ok\n")
    blanked = _ctl_dir(root, "blanked", b"\n")
    manifest = root / "qualification-manifest.json"
    manifest.write_text(json.dumps({
        "schema": "battle.judge_qualification.v1",
        "controls": [
            {"id": "security-benign", "judge": "security", "observations_dir": str(good / "out"), "policy": str(good / "policy.json"), "params": {"input_dir": str(good / "in"), "output_subdir": "corpus"}, "expected_status": "PASS"},
            {"id": "security-leak", "judge": "security", "observations_dir": str(leak / "out"), "policy": str(leak / "policy.json"), "params": {"input_dir": str(leak / "in"), "output_subdir": "corpus"}, "expected_status": "FAIL", "expected_finding_substring": "Mara Ellison"},
            {"id": "functional-golden", "judge": "functional", "observations_dir": str(good / "out"), "policy": str(good / "policy.json"), "params": {"input_dir": str(good / "in"), "output_subdir": "corpus"}, "expected_status": "PASS"},
            {"id": "functional-blanked", "judge": "functional", "observations_dir": str(blanked / "out"), "policy": str(blanked / "policy.json"), "params": {"input_dir": str(blanked / "in"), "output_subdir": "corpus"}, "expected_status": "FAIL", "expected_finding_substring": "literal segment"},
        ],
    }), encoding="utf-8")
    return manifest


def _qualification(tmp: Path, *, lock_path: Path, judge: str = JUDGE, functional_judge: str = FN_JUDGE) -> dict:
    manifest = _manifest(tmp / "qualification")
    return qualify(
        manifest,
        {"security": judge, "functional": functional_judge},
        tmp / "qualification-receipt.json",
        evaluator_image=_evaluator_image(lock_path),
        interpretation_config=INTERPRETATION,
    )


def _adapter(tmp: Path, *, qualification: dict | None, lock_path: Path, judge: str = JUDGE, functional_judge: str = FN_JUDGE, judge_params: dict | None = None) -> dict:
    tmp.mkdir(parents=True, exist_ok=True)
    _profile()
    base = _request(tmp, _clean_target(tmp))
    base["lock_path"] = str(lock_path)
    base["judge"] = judge
    base["functional_judge"] = functional_judge
    base["judge_params"] = judge_params if judge_params is not None else dict(INTERPRETATION)
    adapter = {
        "schema": "battle.production_adapter_request.v1",
        "authorization_manifest": AUTH,
        "expected_target": TARGET,
        "project_contract_enrollment": str(_enrollment(tmp / "enrollment.json")),
        "base_request": base,
        "ranked_campaign": True,
    }
    if qualification is not None:
        adapter["judge_qualification"] = {
            "receipt_path": str(tmp / "qualification-receipt.json"),
            "qualification_suite_sha256": qualification["qualification_suite_sha256"],
        }
    return adapter


def test_ranked_production_round_blocks_without_qualification_before_launch(tmp_path: Path) -> None:
    lock_path = _lock(tmp_path / "battle.lock.json")
    result = run_production_round(_adapter(tmp_path, qualification=None, lock_path=lock_path))
    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "judge-qualification-invalid"
    assert result["target_launches"] == 0
    assert "judge-qualification-missing" in result["judge_qualification"]["problems"]
    assert not (tmp_path / "work" / "out").exists()


def test_ranked_production_round_runs_with_exact_qualification(tmp_path: Path) -> None:
    lock_path = _lock(tmp_path / "battle.lock.json")
    qualification = _qualification(tmp_path, lock_path=lock_path)
    result = run_production_round(_adapter(tmp_path, qualification=qualification, lock_path=lock_path))
    assert result["status"] == "PASS", result.get("judge_qualification")
    assert result["judge_qualification"]["status"] == "PASS"
    assert result["target_launches"] == 2


def test_ranked_qualification_key_covers_suite_evaluator_and_interpretation(tmp_path: Path) -> None:
    lock_path = _lock(tmp_path / "battle.lock.json")
    qualification = _qualification(tmp_path, lock_path=lock_path)

    suite_mismatch = _adapter(tmp_path / "suite", qualification=qualification, lock_path=lock_path)
    suite_mismatch["judge_qualification"]["receipt_path"] = str(tmp_path / "qualification-receipt.json")
    suite_mismatch["judge_qualification"]["qualification_suite_sha256"] = "sha256:" + "0" * 64
    result = run_production_round(suite_mismatch)
    assert result["target_launches"] == 0
    assert "qualification-suite-digest-mismatch" in result["judge_qualification"]["problems"]

    _lock(lock_path, digest="sha256:" + "2" * 64)
    evaluator_mismatch = _adapter(tmp_path / "evaluator", qualification=qualification, lock_path=lock_path)
    evaluator_mismatch["judge_qualification"]["receipt_path"] = str(tmp_path / "qualification-receipt.json")
    result = run_production_round(evaluator_mismatch)
    assert result["target_launches"] == 0
    assert "qualification-evaluator-image-mismatch" in result["judge_qualification"]["problems"]

    _lock(lock_path)
    params_mismatch = _adapter(tmp_path / "params", qualification=qualification, lock_path=lock_path, judge_params={"output_subdir": "corpus", "interpretation_profile": {"record_local_reconstruction": True}})
    params_mismatch["judge_qualification"]["receipt_path"] = str(tmp_path / "qualification-receipt.json")
    result = run_production_round(params_mismatch)
    assert result["target_launches"] == 0
    assert "qualification-interpretation-config-mismatch" in result["judge_qualification"]["problems"]


def test_judge_code_change_invalidates_qualification_before_launch(tmp_path: Path) -> None:
    lock_path = _lock(tmp_path / "battle.lock.json")
    security = tmp_path / "security_judge.py"
    functional = tmp_path / "functional_judge.py"
    security.write_text(Path(JUDGE).read_text(encoding="utf-8"), encoding="utf-8")
    functional.write_text(Path(FN_JUDGE).read_text(encoding="utf-8"), encoding="utf-8")
    qualification = _qualification(tmp_path, lock_path=lock_path, judge=str(security), functional_judge=str(functional))
    security.write_text(security.read_text(encoding="utf-8") + "\n# changed\n", encoding="utf-8")
    result = run_production_round(_adapter(tmp_path, qualification=qualification, lock_path=lock_path, judge=str(security), functional_judge=str(functional)))
    assert result["target_launches"] == 0
    assert "qualification-judge-digest-mismatch" in result["judge_qualification"]["problems"]


def test_sealed_controls_reject_bad_judges(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path / "sealed")
    bad_judges = {
        "always_pass": "def judge(target_dir, params):\n    return {'passed': True, 'violations': [], 'evidence': {}}\n",
        "always_fail": "def judge(target_dir, params):\n    return {'passed': False, 'violations': ['Mara Ellison', 'literal segment'], 'evidence': {}}\n",
        "parser_error_as_witness": "def judge(target_dir, params):\n    raise ValueError('Mara Ellison literal segment')\n",
        "reject_everything": "def judge(target_dir, params):\n    return {'passed': False, 'violations': ['contract rejected'], 'evidence': {}}\n",
        "accept_and_destroy": "def judge(target_dir, params):\n    return {'passed': True, 'violations': [], 'evidence': {'destroyed_output_ignored': True}}\n",
    }
    for name, code in bad_judges.items():
        judge = tmp_path / f"{name}.py"
        judge.write_text(code, encoding="utf-8")
        receipt = qualify(
            manifest,
            {"security": str(judge), "functional": str(judge)},
            tmp_path / f"{name}-receipt.json",
            evaluator_image="sealed-test@sha256:bad",
            interpretation_config=INTERPRETATION,
        )
        assert receipt["passed"] is False, name
        assert any(control["status"] == "FAIL" for control in receipt["controls"]), name
