"""Judge-qualification command tests: control pairs both directions."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from battle_skill.qualify_judges import qualify  # noqa: E402

JUDGES = {
    "security": str(HERE.parent / "fixtures" / "reference-judges" / "no_data_leak_judge.py"),
    "functional": str(HERE.parent / "fixtures" / "reference-judges" / "functional_anonymize_judge.py"),
}


def _ctl_dir(root: Path, name: str, out_text: bytes, in_text: bytes = b"note: Mara Ellison ok\n"):
    d = root / name
    (d / "in" / "corpus").mkdir(parents=True)
    (d / "out" / "corpus").mkdir(parents=True)
    (d / "policy.json").write_text(json.dumps({"sensitive_values": [
        {"rule_id": "r", "subject_id": "s", "type": "name", "value": "Mara Ellison"}]}))
    (d / "in" / "corpus" / "a.txt").write_bytes(in_text)
    (d / "out" / "corpus" / "a.txt").write_bytes(out_text)
    (d / "out" / "report.json").write_text(json.dumps({"status": "ready"}))
    return d


def _manifest(root: Path, controls: list[dict]) -> Path:
    m = root / "manifest.json"
    m.write_text(json.dumps({"schema": "battle.judge_qualification.v1", "controls": controls}))
    return m


def test_qualification_passes_on_correct_controls(tmp_path: Path):
    good = _ctl_dir(tmp_path, "good", b"note: Person-A ok\n")
    leak = _ctl_dir(tmp_path, "leak", b"note: Mara Ellison ok\n")
    m = _manifest(tmp_path, [
        {"id": "good", "judge": "functional",
         "observations_dir": str(good / "out"), "policy": str(good / "policy.json"),
         "params": {"input_dir": str(good / "in"), "output_subdir": "corpus"},
         "expected_status": "PASS"},
        {"id": "leak", "judge": "security",
         "observations_dir": str(leak / "out"), "policy": str(leak / "policy.json"),
         "params": {"input_dir": str(leak / "in"), "output_subdir": "corpus"},
         "expected_status": "FAIL", "expected_finding_substring": "Mara Ellison"},
    ])
    r = qualify(m, JUDGES, tmp_path / "receipt.json")
    assert r["passed"] is True, r["controls"]
    assert set(r["judge_sha256"]) == {"security", "functional"}


def test_qualification_fails_on_wrong_expectation(tmp_path: Path):
    leak = _ctl_dir(tmp_path, "leak", b"note: Mara Ellison ok\n")
    m = _manifest(tmp_path, [
        {"id": "leak-misjudged", "judge": "security",
         "observations_dir": str(leak / "out"), "policy": str(leak / "policy.json"),
         "params": {"input_dir": str(leak / "in"), "output_subdir": "corpus"},
         "expected_status": "PASS"},  # wrong: judge correctly FAILs
    ])
    r = qualify(m, JUDGES, tmp_path / "receipt.json")
    assert r["passed"] is False
    assert r["controls"][0]["status"] == "FAIL"


def test_qualification_requires_finding_substring_when_declared(tmp_path: Path):
    blanked = _ctl_dir(tmp_path, "blanked", b"\n")
    m = _manifest(tmp_path, [
        {"id": "blanked", "judge": "functional",
         "observations_dir": str(blanked / "out"), "policy": str(blanked / "policy.json"),
         "params": {"input_dir": str(blanked / "in"), "output_subdir": "corpus"},
         "expected_status": "FAIL", "expected_finding_substring": "literal segment"},
    ])
    r = qualify(m, JUDGES, tmp_path / "receipt.json")
    assert r["passed"] is True  # blanked output fails with literal-segment finding
