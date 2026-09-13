"""Generic arena protocol tests for non-anonymization Battle campaigns."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
from battle_skill.campaign_contract import run_contract_campaign, verify_campaign_receipt  # noqa: E402
from battle_skill.production_adapter import run_production_round  # noqa: E402
from common.security_authorization import validate_target_authorization  # noqa: E402

TARGET = "http-authz-arena@sha256:test"
IMAGE = "anonymization-trial"


def _sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest_digest(files: list[str]) -> str:
    manifest = [[rel, _sha(Path(rel))] for rel in files]
    manifest.sort()
    return "sha256:" + hashlib.sha256(json.dumps(manifest).encode()).hexdigest()


def _write_auth(path: Path) -> Path:
    path.write_text(json.dumps({
        "schema": "security.target_authorization.v1",
        "authorization_id": "authz-arena-test",
        "issuer": "battle-test",
        "approver": "battle-test",
        "issued_at": "2026-01-01T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
        "target": {"kind": "container", "canonical_id": "http-authz-arena", "immutable_ref": "sha256:test", "image": IMAGE},
        "allowed_target_urls": ["http://127.0.0.1/"],
        "allowed_cidrs": ["127.0.0.1/32"],
        "allowed_ports": [80],
        "runtime_modes": ["docker"],
        "allowed_actions": ["battle"],
        "allowed_probe_classes": ["fixture"],
        "denied_probe_classes": ["destructive"],
        "network_policy": "none",
        "egress_policy": "none",
        "limits": {"requests_per_second": 1, "max_concurrency": 1, "duration_seconds": 60, "cpu": 1, "memory_mb": 256, "storage_mb": 64},
        "permissions": {"destructive": False, "persistence": False, "credential": False, "denial_of_service": False, "nonlocal": False},
        "artifact_root": str(path.parent),
        "redaction_policy": "none",
        "legal_non_opinion_ack": True,
    }), encoding="utf-8")
    return path


def _write_generator(path: Path) -> Path:
    path.write_text(r'''
import json
from pathlib import Path

TARGET = ''' + repr("""
import json
from pathlib import Path
req = json.loads(Path('/arena/input/request.json').read_text())
allow = req.get('subject') == 'alice' and req.get('action') == 'read' and req.get('resource') == 'report-1'
status = 200 if allow else 403
out = Path('/arena/output/observations')
out.mkdir(parents=True, exist_ok=True)
(out / 'response.json').write_text(json.dumps({'status_code': status, 'decision': 'allow' if allow else 'deny', 'request': req}))
""") + r'''

def _case(root, name, request, expectation):
    d = Path(root) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / 'request.json').write_text(json.dumps(request))
    (d / 'target.py').write_text(TARGET)
    return name, d, expectation


def generate(work_dir, params):
    yield _case(work_dir, 'authz-allow-read', {'subject': 'alice', 'action': 'read', 'resource': 'report-1'}, 'MUST_ACCEPT')
    yield _case(work_dir, 'authz-deny-admin', {'subject': 'mallory', 'action': 'admin', 'resource': 'report-1'}, 'MUST_REJECT')
''', encoding="utf-8")
    return path


def _write_judges(root: Path) -> tuple[Path, Path]:
    security = root / "http_authz_security_judge.py"
    security.write_text(r'''
import json
from pathlib import Path

def judge(target_dir, params):
    req = json.loads((Path(params['input_dir']) / 'request.json').read_text())
    response = json.loads((Path(target_dir) / 'observations' / 'response.json').read_text())
    expected = 200 if req == {'subject': 'alice', 'action': 'read', 'resource': 'report-1'} else 403
    ok = response.get('status_code') == expected
    return {'passed': ok, 'violations': [] if ok else [f"status {response.get('status_code')} != {expected}"], 'evidence': {'status_code': response.get('status_code')}}
''', encoding="utf-8")
    functional = root / "http_authz_functional_judge.py"
    functional.write_text(r'''
import json
from pathlib import Path

def judge(target_dir, params):
    response = json.loads((Path(target_dir) / 'observations' / 'response.json').read_text())
    ok = response.get('decision') in {'allow', 'deny'} and isinstance(response.get('request'), dict)
    return {'passed': ok, 'violations': [] if ok else ['missing decision/request observation'], 'evidence': {'decision': response.get('decision')}}
''', encoding="utf-8")
    return security, functional


def _write_protocol(path: Path) -> Path:
    path.write_text(json.dumps({
        "schema": "battle.arena_protocol.v1",
        "arena_id": "http-authorization.v1",
        "fixture_validation": {"kind": "json_files", "required_files": ["request.json"]},
        "observations": {"output_subdir": "observations"},
        "applicable_judges": ["security", "functional"],
        "expectations": ["MUST_ACCEPT", "MUST_REJECT"],
        "reset_behavior": {"mode": "fresh_output_dir_per_case"},
        "expectation_semantics": {"MUST_REJECT": "judge_observation"},
    }), encoding="utf-8")
    return path


def _write_profile(path: Path) -> Path:
    path.write_text(json.dumps({
        "schema": "battle.campaign_profile.v1",
        "profile_id": "http-authz-profile.v1",
        "required_judges": ["security", "functional"],
        "expectation_overrides": {},
        "required_case_ids": ["authz-allow-read", "authz-deny-admin"],
    }), encoding="utf-8")
    return path


def _write_lock(path: Path, files: list[Path]) -> Path:
    bundle_files = [str(p) for p in files]
    path.write_text(json.dumps({
        "schema": "battle.evaluator_lock.v1",
        "source_repo_path": str(path.parent),
        "source_repo": "battle-test",
        "commit": "test",
        "bundle_files": bundle_files,
        "bundle_manifest_sha256": _manifest_digest(bundle_files),
    }), encoding="utf-8")
    return path


def _request(tmp: Path) -> dict:
    generator = _write_generator(tmp / "http_authz_generator.py")
    security, functional = _write_judges(tmp)
    profile = _write_profile(tmp / "profile.json")
    protocol = _write_protocol(tmp / "arena_protocol.json")
    lock = _write_lock(tmp / "battle.lock.json", [generator, security, functional])
    return {
        "schema": "battle.campaign_request.v1",
        "profile_path": str(profile),
        "arena_protocol_path": str(protocol),
        "lock_path": str(lock),
        "generator": str(generator),
        "judge": str(security),
        "functional_judge": str(functional),
        "target_run_cmd": f"docker run --rm -v {{input}}:/arena/input:ro -v {{output}}:/arena/output --entrypoint python3 {IMAGE} /arena/input/target.py",
        "work_root": str(tmp / "work"),
        "gen_params": {},
        "judge_params": {},
    }


def test_http_authorization_arena_runs_without_corpus_or_policy_json(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request["authorization_receipt"] = validate_target_authorization(
        _write_auth(tmp_path / "authorization.json"),
        expected_target=TARGET,
        expected_execution_target=IMAGE,
        requested_action="battle",
        requested_runtime_mode="docker",
    )
    receipt = run_contract_campaign(request)
    assert receipt["verdict"] == "PASS", receipt["aggregation"]
    assert receipt["plan"]["arena_protocol"]["arena_id"] == "http-authorization.v1"
    assert receipt["plan"]["arena_protocol"]["reset_behavior"]["mode"] == "fresh_output_dir_per_case"
    assert receipt["aggregation"]["cases_total"] == 2
    assert receipt["aggregation"]["accepted_count"] == 2
    assert all(c["fixture_precheck"]["witness"]["kind"] == "ARENA_PROTOCOL_FIXTURE" for c in receipt["case_receipts"])
    for case in receipt["plan"]["cases"]:
        case_dir = Path(case["input_dir"])
        assert (case_dir / "request.json").is_file()
        assert not (case_dir / "corpus").exists()
        assert not (case_dir / "policy.json").exists()
    report = verify_campaign_receipt(tmp_path / "work" / "receipt.json")
    assert report["passed"] is True, report["problems"]
    assert report["execution_provenance"] == "RUNNER_ATTESTED"


def test_production_adapter_uses_same_authorized_receipt_path_for_http_arena(tmp_path: Path) -> None:
    request = _request(tmp_path)
    request["authorization_receipt"] = None
    adapter = {
        "schema": "battle.production_adapter_request.v1",
        "authorization_manifest": str(_write_auth(tmp_path / "authorization.json")),
        "expected_target": TARGET,
        "project_contract_enrollment": str(_write_enrollment(tmp_path / "enrollment.json")),
        "base_request": {k: v for k, v in request.items() if k != "authorization_receipt"},
        "enforce_docker_boundary": True,
    }
    result = run_production_round(adapter)
    assert result["status"] == "PASS", result
    assert result["campaign"]["plan"]["arena_protocol"]["arena_id"] == "http-authorization.v1"
    assert result["target_launches"] == 2
    assert result["authorization_receipt"]["expected_execution_target"] == IMAGE


def _write_enrollment(path: Path) -> Path:
    path.write_text(json.dumps({
        "schema": "battle.project_contract_enrollment.v1",
        "target_identity": TARGET,
        "acceptance_contract": {"required": False},
    }), encoding="utf-8")
    return path
