"""Artifact snapshot confinement tests for Battle campaign materialization."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from battle_skill.campaign_contract import resolve_plan, run_contract_campaign  # noqa: E402
from battle_skill.production_adapter import run_production_round  # noqa: E402
from test_campaign_contract import PROFILE, _clean_target, _request  # noqa: E402
from test_production_adapter import AUTH, TARGET, _enrollment  # noqa: E402


def _generator(path: Path, body: str) -> str:
    path.write_text(body, encoding="utf-8")
    return str(path)


def _single_case_generator(case_id: str = "case-str") -> str:
    return f'''
from pathlib import Path

def generate(work_dir, params):
    root = Path(work_dir) / {case_id!r}
    (root / "corpus").mkdir(parents=True, exist_ok=True)
    (root / "policy.json").write_text('{{"version":1,"protected_values":[],"sensitive_values":[{{"rule_id":"r","subject_id":"s","type":"name","value":"5551234567"}}]}}')
    (root / "corpus" / "record.json").write_text('{{"phone":"5551234567"}}')
    yield {case_id!r}, root, "MAY_REJECT"
'''


def _profile_one_case() -> None:
    Path(PROFILE).write_text(json.dumps({
        "schema": "battle.campaign_profile.v1",
        "profile_id": "test-contract.v1",
        "required_judges": ["security", "functional"],
        "expectation_overrides": {"case-str": "MUST_ACCEPT"},
        "required_case_ids": ["case-str"],
    }), encoding="utf-8")


def _request_with_generator(tmp_path: Path, generator: str, target: str | None = None) -> dict:
    _profile_one_case()
    request = _request(tmp_path, target or _clean_target(tmp_path))
    request["generator"] = generator
    request["gen_params"] = {"outside": str(tmp_path / "outside")}
    return request


def test_unsafe_case_id_is_rejected_before_output_path_creation(tmp_path: Path) -> None:
    request = _request_with_generator(
        tmp_path,
        _generator(tmp_path / "bad_id_generator.py", _single_case_generator("../escape")),
    )

    with pytest.raises(ValueError, match="unsafe case id"):
        run_contract_campaign(request)

    assert not (tmp_path / "work" / "out").exists()
    assert not (tmp_path / "escape").exists()


def test_generator_output_symlink_is_rejected_before_target_launch(tmp_path: Path) -> None:
    sentinel = tmp_path / "target-ran"
    generator = _generator(tmp_path / "symlink_generator.py", f'''
from pathlib import Path

def generate(work_dir, params):
    root = Path(work_dir) / "case-str"
    (root / "corpus").mkdir(parents=True, exist_ok=True)
    (root / "policy.json").write_text('{{"version":1,"protected_values":[],"sensitive_values":[{{"rule_id":"r","subject_id":"s","type":"name","value":"5551234567"}}]}}')
    (Path(params["outside"])).mkdir(parents=True, exist_ok=True)
    (Path(params["outside"]) / "secret.txt").write_text("host-secret")
    (root / "corpus" / "leak.txt").symlink_to(Path(params["outside"]) / "secret.txt")
    yield "case-str", root, "MAY_REJECT"
''')
    request = _request_with_generator(tmp_path, generator, f"touch {sentinel} && mkdir -p {{output}}/corpus")

    with pytest.raises(ValueError, match="symlink"):
        run_contract_campaign(request)

    assert not sentinel.exists()


def test_generator_case_directory_must_stay_under_owned_root(tmp_path: Path) -> None:
    generator = _generator(tmp_path / "external_generator.py", '''
from pathlib import Path

def generate(work_dir, params):
    root = Path(params["outside"])
    (root / "corpus").mkdir(parents=True, exist_ok=True)
    (root / "policy.json").write_text('{"version":1,"protected_values":[],"sensitive_values":[]}')
    (root / "corpus" / "record.json").write_text('{"ok":true}')
    yield "case-str", root, "MAY_REJECT"
''')
    request = _request_with_generator(tmp_path, generator)

    with pytest.raises(ValueError, match="escapes owned root"):
        run_contract_campaign(request)


def test_resolved_plan_uses_sealed_snapshot_after_generator_file_mutation(tmp_path: Path) -> None:
    generator = _generator(tmp_path / "snapshot_generator.py", _single_case_generator())
    request = _request_with_generator(tmp_path, generator)

    plan = resolve_plan(request)
    source_file = tmp_path / "work" / "plan-gen" / "case-str" / "corpus" / "record.json"
    snapshot_file = Path(plan["cases"][0]["input_dir"]) / "corpus" / "record.json"
    source_file.write_text('{"phone":"CHANGED"}', encoding="utf-8")

    assert json.loads(snapshot_file.read_text())["phone"] == "5551234567"
    assert plan["cases"][0]["input_dir"].startswith(str(tmp_path / "work" / "plan-cases"))


def test_production_adapter_returns_blocked_zero_launches_for_unsafe_artifact(tmp_path: Path) -> None:
    request = _request_with_generator(
        tmp_path,
        _generator(tmp_path / "bad_id_generator.py", _single_case_generator("../escape")),
    )
    result = run_production_round({
        "schema": "battle.production_adapter_request.v1",
        "authorization_manifest": AUTH,
        "expected_target": TARGET,
        "project_contract_enrollment": str(_enrollment(tmp_path / "enrollment.json")),
        "base_request": request,
    })

    assert result["status"] == "BLOCKED"
    assert result["failure_code"] == "campaign-artifact-confinement-invalid"
    assert result["target_launches"] == 0
