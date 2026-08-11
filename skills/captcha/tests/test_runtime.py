"""Runtime contract tests for ReCAP, Surf, Ask, and durable receipts."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from captcha_skill.constants import DEFAULT_STORAGE_ROOT, RECAP_COMMIT
from captcha_skill.errors import CaptchaSkillError, ErrorCode
from captcha_skill.models import (
    ArtifactContract,
    AuthorizationManifest,
    BoundedJudgment,
    EvaluationAction,
    EvaluationPlan,
    ExecutionSpec,
    ModelEndpointProof,
    RecapBinding,
    RunReceipt,
    RunStatus,
    SeamValidation,
    SurfBinding,
    SurfCapabilities,
    SurfTargetProof,
    TargetProof,
)
from captcha_skill.policy import (
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    validate_authorization,
    write_json_atomic,
)
from captcha_skill.runtime import (
    build_ask_dag,
    build_evaluation_plan,
    build_recap_argv,
    build_recap_environment,
    compute_plan_hash,
    preflight_model_endpoint,
    preflight_surf_target,
    preflight_target,
    status_report,
    verify_run,
)

SKILL_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = SKILL_ROOT / "fixtures"


def _manifest() -> AuthorizationManifest:
    value = json.loads((FIXTURES / "authorization-valid-local.json").read_text())
    return AuthorizationManifest.model_validate(value)


def _authorization(action: EvaluationAction):
    value = json.loads((FIXTURES / "authorization-valid-local.json").read_text())
    manifest = AuthorizationManifest.model_validate(value)
    receipt = validate_authorization(
        manifest,
        manifest_sha256=sha256_bytes(canonical_json_bytes(manifest.model_dump(mode="json"))),
        required_action=action,
        now=datetime(2028, 1, 1, tzinfo=timezone.utc),
    )
    return manifest, receipt


def _surf_capabilities_payload() -> dict[str, object]:
    return {
        "schema": "surf.capabilities.v1",
        "schema_version": "1.0.0",
        "skill": {
            "name": "surf",
            "path": "/repo/skills/surf",
            "skill_md_sha256": "a" * 64,
            "contract_references": ["references/capabilities.schema.json"],
        },
        "engine": {
            "kind": "vendored_surf_cli",
            "package_version": "1.2.3",
            "path": "/repo/skills/surf/vendor/surf-cli",
            "dist_present": True,
            "dist_fresh": True,
            "lock_present": True,
            "content_identity_matches": True,
        },
        "transport": {
            "extension_socket_path": "/tmp/surf.sock",
            "extension_socket_present": True,
            "cdp_fallback": True,
        },
        "providers": {},
        "contracts": {
            "capabilities_schema": "surf.capabilities.v1",
            "provider_result_schema": "surf.provider_result.v1",
            "immutable_submit_schema": "surf.immutable_submit.v1",
            "vendor_update_gate": "surf.vendor_update_gate.v1",
        },
    }


def test_recap_argv_is_pinned_to_dynamic_qwen3() -> None:
    manifest = _manifest()
    root = Path("/mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent")
    runtime_python = root / ".venv/bin/python"

    argv = build_recap_argv(manifest, recap_root=root, recap_python=runtime_python)

    assert argv[0] == str(runtime_python)
    assert argv[argv.index("--provider") + 1] == "dynamic"
    assert argv[argv.index("--model-family") + 1] == "qwen3"
    assert argv[argv.index("--test-mode") + 1] == "custom"
    assert argv[argv.index("--captcha-name") + 1] == "text"
    assert "halligan" not in argv


def test_sterile_recap_environment_drops_proxies_and_unrelated_secrets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    monkeypatch.setenv("HTTP_PROXY", "http://public-proxy.example")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "must-not-cross")
    monkeypatch.setenv("CAPTCHA_LOCAL_MODEL_API_KEY", "local-key")

    env = build_recap_environment(manifest, recap_runs_root=tmp_path / "runs")

    assert "HTTP_PROXY" not in env
    assert "AWS_SECRET_ACCESS_KEY" not in env
    assert env["OPENAI_API_KEY"] == "local-key"
    assert env["OPENAI_BASE_URL"].startswith("http://127.0.0.1:8000")
    assert env["DYNAMIC_PROVIDER_URL"].startswith("http://127.0.0.1:5000")
    assert env["NO_PROXY"] == "127.0.0.1,::1"


def test_plan_reports_missing_runtime_without_false_pass() -> None:
    manifest, authorization = _authorization(EvaluationAction.PLAN)
    plan = build_evaluation_plan(
        manifest,
        authorization,
        recap_root=Path("/definitely/missing/ReCAP-Agent"),
        recap_python=Path("/definitely/missing/ReCAP-Agent/.venv/bin/python"),
        output_root=DEFAULT_STORAGE_ROOT / "outputs",
    )

    assert plan.readiness is RunStatus.NEEDS_ATTENTION
    assert plan.blockers
    assert plan.seam_validation is None
    assert len(plan.plan_sha256) == 64
    assert plan.execution.shell is False


def test_ask_dag_composes_captcha_through_skill_run(tmp_path: Path) -> None:
    manifest_path = FIXTURES / "authorization-valid-local.json"
    recap_root = Path("/mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent")
    dag = build_ask_dag(
        manifest_path=manifest_path,
        recap_root=recap_root,
        recap_python=recap_root / ".venv/bin/python",
        output_root=DEFAULT_STORAGE_ROOT / "outputs",
        timeout_seconds=600,
    )

    assert dag.schema_version == "ask.dag.v1"
    assert len(dag.nodes) == 1
    node = dag.nodes[0]
    assert node.type == "skill.run"
    assert node.input.skill == "captcha"
    assert node.input.args[0] == "evaluate"
    assert "--execute" in node.input.args
    assert node.input.timeout == 720


class _ChallengeHandler(BaseHTTPRequestHandler):
    marker = True

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        if self.path != "/challenge/text":
            self.send_response(404)
            self.end_headers()
            return
        body = (
            b'<html><input name="challenge_id" value="fixture"></html>'
            if self.marker
            else b"<html>unrelated service</html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        _ = format, args


def _serve(handler: type[BaseHTTPRequestHandler]):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_target_preflight_uses_real_loopback_http() -> None:
    server, thread = _serve(_ChallengeHandler)
    try:
        value = json.loads((FIXTURES / "authorization-valid-local.json").read_text())
        value["target_url"] = f"http://127.0.0.1:{server.server_port}"
        manifest = AuthorizationManifest.model_validate(value)

        proof = preflight_target(manifest)

        assert proof.status == "PASS"
        assert proof.challenge_marker_present is True
        assert len(proof.body_sha256) == 64
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_target_preflight_rejects_wrong_loopback_service() -> None:
    class WrongHandler(_ChallengeHandler):
        marker = False

    server, thread = _serve(WrongHandler)
    try:
        value = json.loads((FIXTURES / "authorization-valid-local.json").read_text())
        value["target_url"] = f"http://127.0.0.1:{server.server_port}"
        manifest = AuthorizationManifest.model_validate(value)

        with pytest.raises(CaptchaSkillError) as raised:
            preflight_target(manifest)

        assert raised.value.code is ErrorCode.TARGET_UNAVAILABLE
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_surf_capabilities_contract_accepts_versioned_producer_receipt() -> None:
    capabilities = SurfCapabilities.model_validate(_surf_capabilities_payload())

    assert capabilities.skill.name == "surf"
    assert capabilities.contract_schema == "surf.capabilities.v1"
    assert capabilities.contracts.capabilities_schema == "surf.capabilities.v1"


def _create_pass_run(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    request = run_dir / "request.json"
    authorization_path = run_dir / "authorization-receipt.json"
    plan_path = run_dir / "plan.json"
    surf = run_dir / "surf-capabilities.json"
    surf_target = run_dir / "surf-target-preflight.json"
    surf_screenshot = run_dir / "surf-target-preflight.png"
    target = run_dir / "target-preflight.json"
    model_endpoint = run_dir / "model-endpoint-preflight.json"
    stdout = run_dir / "recap.stdout.log"
    stderr = run_dir / "recap.stderr.log"
    events = run_dir / "events.jsonl"
    status = run_dir / "status.json"
    summary_dir = run_dir / "recap-runs" / "fixture"
    summary_dir.mkdir(parents=True)
    summary = summary_dir / "captcha-benchmark-results.json"

    manifest = _manifest()
    manifest_hash = sha256_bytes(
        canonical_json_bytes(manifest.model_dump(mode="json"))
    )
    authorization = validate_authorization(
        manifest,
        manifest_sha256=manifest_hash,
        required_action=EvaluationAction.EVALUATE,
        now=datetime(2028, 1, 1, tzinfo=timezone.utc),
    )
    recap_root = Path("/mnt/storage12tb/skills/captcha/vendor/ReCAP-Agent")
    recap_python = recap_root / ".venv/bin/python"
    plan_value = {
        "schema_version": "captcha.evaluation_plan.v1",
        "plan_id": "fixture-plan",
        "created_at": "2028-01-01T00:00:00Z",
        "readiness": "PASS",
        "blockers": [],
        "authorization": authorization.model_dump(mode="json"),
        "recap": RecapBinding(
            checkout_root=str(recap_root),
            framework_main=str(recap_root / "captcha_eval_framework/main.py"),
            runtime_python=str(recap_python),
        ).model_dump(mode="json"),
        "surf": SurfBinding(
            command=["/repo/skills/surf/run.sh", "capabilities", "--json"]
        ).model_dump(mode="json"),
        "execution": ExecutionSpec(
            argv=build_recap_argv(
                manifest, recap_root=recap_root, recap_python=recap_python
            ),
            cwd=str(recap_root / "captcha_eval_framework"),
            timeout_seconds=manifest.timeout_seconds,
            output_root=str(run_dir.parent),
            environment_keys=[],
            secret_environment_keys=["OPENAI_API_KEY"],
        ).model_dump(mode="json"),
        "artifact_contract": ArtifactContract(
            required_files=[
                "request.json",
                "authorization-receipt.json",
                "plan.json",
                "surf-capabilities.json",
                "surf-target-preflight.json",
                "surf-target-preflight.png",
                "target-preflight.json",
                "model-endpoint-preflight.json",
                "events.jsonl",
                "recap.stdout.log",
                "recap.stderr.log",
                "captcha.run-receipt.json",
            ],
            generated_files=[
                "recap-runs/*/captcha-benchmark-results.json"
            ],
            heavy_artifacts_policy="fixture artifacts remain under the test root",
        ).model_dump(mode="json"),
        "plan_sha256": "0" * 64,
        "seam_validation": SeamValidation(
            kind="captcha.evaluation_plan"
        ).model_dump(mode="json"),
    }
    plan_value["plan_sha256"] = compute_plan_hash(plan_value)
    plan = EvaluationPlan.model_validate(plan_value)

    capabilities = SurfCapabilities.model_validate(_surf_capabilities_payload())
    surf_screenshot.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
    surf_target_proof = SurfTargetProof(
        schema_version="captcha.surf_target_preflight.v1",
        checked_at=datetime(2028, 1, 1, tzinfo=timezone.utc),
        challenge_url="http://127.0.0.1:5000/challenge/text",
        final_url="http://127.0.0.1:5000/challenge/text",
        tab_id=42,
        challenge_id_present=True,
        screenshot_sha256=sha256_file(surf_screenshot),
        seam_validation=SeamValidation(kind="captcha.surf_local_target"),
    )
    target_proof = TargetProof(
        schema_version="captcha.target_preflight.v1",
        checked_at=datetime(2028, 1, 1, tzinfo=timezone.utc),
        url="http://127.0.0.1:5000/challenge/text",
        status_code=200,
        content_type="text/html",
        body_sha256="b" * 64,
        challenge_marker_present=True,
        seam_validation=SeamValidation(kind="captcha.local_target"),
    )
    model_proof = ModelEndpointProof(
        schema_version="captcha.model_endpoint_preflight.v1",
        checked_at=datetime(2028, 1, 1, tzinfo=timezone.utc),
        url="http://127.0.0.1:8000/v1/models",
        requested_model_id=manifest.model_id,
        advertised_model_ids=[manifest.model_id],
        response_sha256="c" * 64,
        seam_validation=SeamValidation(kind="captcha.local_model_endpoint"),
    )

    write_json_atomic(request, manifest.model_dump(mode="json"))
    write_json_atomic(authorization_path, authorization.model_dump(mode="json"))
    write_json_atomic(plan_path, plan.model_dump(mode="json"))
    write_json_atomic(surf, capabilities.model_dump(mode="json", by_alias=True))
    write_json_atomic(surf_target, surf_target_proof.model_dump(mode="json"))
    write_json_atomic(target, target_proof.model_dump(mode="json"))
    write_json_atomic(model_endpoint, model_proof.model_dump(mode="json"))
    stdout.write_text("ok\n")
    stderr.write_text("")
    events.write_text('{"event":"fixture"}\n')
    summary.write_text((FIXTURES / "recap-summary-valid.json").read_text())

    evidence_paths = [
        request,
        authorization_path,
        plan_path,
        surf,
        surf_target,
        surf_screenshot,
        target,
        model_endpoint,
        stdout,
        stderr,
        events,
        summary,
    ]
    evidence = {
        path.relative_to(run_dir).as_posix(): sha256_file(path)
        for path in evidence_paths
    }
    expected_claim = (
        "The pinned ReCAP agent solved 1 of 2 authorized synthetic dynamic "
        "CAPTCHA tasks in this run."
    )
    receipt = RunReceipt(
        schema_version="captcha.run_receipt.v1",
        run_id="fixture-run",
        status=RunStatus.PASS,
        started_at=datetime(2028, 1, 1, tzinfo=timezone.utc),
        finished_at=datetime(2028, 1, 1, 0, 1, tzinfo=timezone.utc),
        authorization_receipt_path="authorization-receipt.json",
        plan_path="plan.json",
        surf_capabilities_path="surf-capabilities.json",
        surf_target_preflight_path="surf-target-preflight.json",
        target_preflight_path="target-preflight.json",
        model_endpoint_preflight_path="model-endpoint-preflight.json",
        recap_summary_path=(
            "recap-runs/fixture/captcha-benchmark-results.json"
        ),
        stdout_path="recap.stdout.log",
        stderr_path="recap.stderr.log",
        exit_code=0,
        bounded_judgment=BoundedJudgment.CAPABILITY_MEASURED,
        claims=[expected_claim],
        limitations=["fixture only"],
        evidence_sha256=evidence,
        seam_validation=SeamValidation(kind="captcha.run_receipt"),
    )
    receipt_path = run_dir / "captcha.run-receipt.json"
    write_json_atomic(receipt_path, receipt.model_dump(mode="json"))
    write_json_atomic(
        status,
        {
            "schema_version": "captcha.run_status.v1",
            "status": "PASS",
            "updated_at": "2028-01-01T00:01:00Z",
            "phase": "complete",
            "receipt_path": receipt_path.name,
            "receipt_sha256": sha256_file(receipt_path),
            "failure_code": None,
        },
    )
    return run_dir


def test_verify_run_checks_real_evidence_hashes(tmp_path: Path) -> None:
    run_dir = _create_pass_run(tmp_path)

    result = verify_run(run_dir)

    assert result["status"] == "PASS"
    assert result["run_status"] == "PASS"
    assert result["evidence_files_verified"] == 12


def test_verify_run_fails_after_evidence_tamper(tmp_path: Path) -> None:
    run_dir = _create_pass_run(tmp_path)
    (run_dir / "request.json").write_text('{"tampered":true}\n')

    with pytest.raises(CaptchaSkillError) as raised:
        verify_run(run_dir)

    assert raised.value.code is ErrorCode.RECEIPT_INVALID


def test_verify_run_rejects_status_receipt_digest_tamper(tmp_path: Path) -> None:
    run_dir = _create_pass_run(tmp_path)
    status_path = run_dir / "status.json"
    status_value = json.loads(status_path.read_text())
    status_value["receipt_sha256"] = "0" * 64
    write_json_atomic(status_path, status_value)

    with pytest.raises(CaptchaSkillError) as raised:
        verify_run(run_dir)

    assert raised.value.code is ErrorCode.RECEIPT_INVALID
    assert any(
        item["file"] == "status.json#receipt_sha256"
        for item in raised.value.details["mismatches"]
    )


def test_verify_run_rejects_semantic_plan_tamper_even_when_rehashed(
    tmp_path: Path,
) -> None:
    run_dir = _create_pass_run(tmp_path)
    plan_path = run_dir / "plan.json"
    plan_value = json.loads(plan_path.read_text())
    plan_value["execution"]["timeout_seconds"] += 1
    write_json_atomic(plan_path, plan_value)

    receipt_path = run_dir / "captcha.run-receipt.json"
    receipt_value = json.loads(receipt_path.read_text())
    receipt_value["evidence_sha256"]["plan.json"] = sha256_file(plan_path)
    write_json_atomic(receipt_path, receipt_value)

    with pytest.raises(CaptchaSkillError) as raised:
        verify_run(run_dir)

    assert raised.value.code is ErrorCode.RECEIPT_INVALID
    mismatches = raised.value.details["mismatches"]
    assert any(item["file"] == "plan.json#plan_sha256" for item in mismatches)


def test_verify_run_rejects_evidence_path_escape(tmp_path: Path) -> None:
    run_dir = _create_pass_run(tmp_path)
    receipt_path = run_dir / "captcha.run-receipt.json"
    receipt_value = json.loads(receipt_path.read_text())
    receipt_value["evidence_sha256"]["../outside.json"] = "a" * 64
    write_json_atomic(receipt_path, receipt_value)

    with pytest.raises(CaptchaSkillError) as raised:
        verify_run(run_dir)

    assert raised.value.code is ErrorCode.RECEIPT_INVALID


def test_status_sees_ask_composition_but_does_not_infer_other_readiness() -> None:
    report = status_report(
        recap_root=Path("/definitely/missing/ReCAP-Agent"),
        storage_root=Path("/definitely/missing/storage"),
    )

    assert report.ask_skill_present is True
    assert report.ask_declares_captcha is True
    assert report.status is RunStatus.NOT_ESTABLISHED
    assert report.blockers

class _ModelHandler(BaseHTTPRequestHandler):
    model_ids = ["ReCAP-Agent/ReCAP-8B"]

    def do_GET(self) -> None:  # noqa: N802 - stdlib callback name
        if self.path != "/v1/models":
            self.send_response(404)
            self.end_headers()
            return
        body = json.dumps(
            {"object": "list", "data": [{"id": item} for item in self.model_ids]}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        _ = format, args


def test_model_endpoint_preflight_proves_exact_local_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    server, thread = _serve(_ModelHandler)
    monkeypatch.setenv("CAPTCHA_LOCAL_MODEL_API_KEY", "fixture-key")
    try:
        value = json.loads((FIXTURES / "authorization-valid-local.json").read_text())
        value["model_base_url"] = f"http://127.0.0.1:{server.server_port}/v1"
        manifest = AuthorizationManifest.model_validate(value)

        proof = preflight_model_endpoint(manifest)

        assert proof.status == "PASS"
        assert proof.exact_model_match is True
        assert proof.requested_model_id == "ReCAP-Agent/ReCAP-8B"
        assert proof.advertised_model_ids == ["ReCAP-Agent/ReCAP-8B"]
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def test_model_endpoint_preflight_rejects_wrong_model_identity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class WrongModelHandler(_ModelHandler):
        model_ids = ["unrelated/model"]

    server, thread = _serve(WrongModelHandler)
    monkeypatch.setenv("CAPTCHA_LOCAL_MODEL_API_KEY", "fixture-key")
    try:
        value = json.loads((FIXTURES / "authorization-valid-local.json").read_text())
        value["model_base_url"] = f"http://127.0.0.1:{server.server_port}/v1"
        manifest = AuthorizationManifest.model_validate(value)

        with pytest.raises(CaptchaSkillError) as raised:
            preflight_model_endpoint(manifest)

        assert raised.value.code is ErrorCode.MODEL_ID_MISMATCH
        assert raised.value.details["requested_model_id"] == "ReCAP-Agent/ReCAP-8B"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
