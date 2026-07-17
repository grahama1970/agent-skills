from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import phase11_canonical_common as common  # noqa: E402
import phase11_execution_common as execution  # noqa: E402
from phase11_fixture_helpers import (  # noqa: E402
    fixture_fal_importer,
    install_adapter_preflight,
    make_compilation_inputs,
    write_json,
)
from test_phase11_canonical_live_request import install_transition_evidence  # noqa: E402


def test_active_completed_attempt_has_completed_terminal_state():
    ledger = ROOT / (
        "reports/pipeline-complete/.persona-dream/revisions/rev_upstream_bf3b05d47fb8/"
        "phase_11_submit_return/attempts/"
        "ca90ba9fd76a1e2d682b326e65b18f5e8168d81bf829cb9e8c6a3db6779c840f/"
        "attempt_ledger.v1.json"
    )
    if not ledger.is_file():
        pytest.skip("active live attempt ledger not installed")
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    assert payload["state"] == "COMPLETED"
    assert payload["history"][-1]["event"] == "COMPLETED"
    assert payload["provider_terminal_state"] == "COMPLETED"


def ready_inputs(tmp_path: Path):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    request_body, blockers, _ = common.compile_request_body(inputs)
    assert blockers == []
    return install_transition_evidence(inputs, request_body)


def authorization_packet(inputs, path: Path, *, expires_at: str = "2026-07-15T13:00:00+00:00"):
    state = execution.build_execution_state(inputs)
    packet = {
        "schema": "persona_dream.phase11_authorization_packet.v1",
        "decision": "APPROVE",
        "decision_source": "EXPLICIT_HUMAN",
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "approver": {
            "id": "fixture-human-approver",
            "display_name": "Fixture Human Approver",
            "authority_basis": "fixture-only test authority",
        },
        "approved_at": "2026-07-15T12:00:00+00:00",
        "expires_at": expires_at,
        "purpose": execution.AUTHORIZATION_PURPOSE,
        "authorization_scope": execution.AUTHORIZATION_SCOPE,
        "currency": "USD",
        "maximum_spend_usd": 0.84,
        "revoked": False,
        "revocation_state": "NOT_REVOKED",
        "approval_types": list(common.APPROVAL_TYPES),
        "bindings": state.bindings,
        "acknowledgements": {
            "authorize_one_paid_generation": True,
            "no_automatic_resubmit": True,
            "ambiguous_submit_requires_human_reconciliation": True,
            "provider_return_does_not_authorize_watch_or_cognition": True,
        },
    }
    write_json(path, packet)
    return packet


def test_zero_call_preflight_is_required_before_approval_readiness(tmp_path: Path):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    request_body, blockers, _ = common.compile_request_body(inputs)
    assert blockers == []
    inputs = install_transition_evidence(inputs, request_body, install_preflight=False)
    media, approvals, blocked = common.compile_bundle(inputs)
    assert blocked["status"] == "BLOCKED_PROVIDER_GATE"
    assert "BLOCKED_PHASE11_ADAPTER_PREFLIGHT_REQUIRED" in blocked["technical_blockers"]
    common.write_compiled_bundle(
        inputs.context.revision_root / common.DEFAULT_OUTPUT_RELATIVE,
        media, approvals, blocked,
    )

    call_count = {"submit": 0}

    class NoCallClient:
        def submit(self, *_args, **_kwargs):
            call_count["submit"] += 1
            raise AssertionError("preflight called provider submit")

        def get_handle(self, *_args, **_kwargs):
            raise AssertionError

        def status(self, *_args, **_kwargs):
            raise AssertionError

        def result(self, *_args, **_kwargs):
            raise AssertionError

    class NoCallHandle:
        def status(self):
            raise AssertionError

        def get(self):
            raise AssertionError

    module = type("FalFixture", (), {
        "__version__": "fixture",
        "SyncClient": NoCallClient,
        "SyncRequestHandle": NoCallHandle,
    })
    implementation = type("FalImplementation", (), {"MAX_ATTEMPTS": 10})

    def importer(name: str):
        return module if name == "fal_client" else implementation

    receipt = execution.run_adapter_preflight(
        inputs,
        current=datetime(2026, 7, 15, 12, tzinfo=timezone.utc),
        poll_interval_seconds=5,
        max_polls=180,
        adapter_script_path=ROOT / "scripts" / "phase11_fal_canary_adapter.py",
        environ={"FAL_API_KEY": "fixture-secret-not-persisted"},
        importer=importer,
        ffprobe_resolver=lambda _name: "/usr/bin/ffprobe",
    )
    assert receipt["status"] == "PASS_PHASE11_ADAPTER_PREFLIGHT"
    assert receipt["approval_validation"]["missing_types"] == sorted(common.APPROVAL_TYPES)
    assert receipt["credential"]["source_variable"] == "FAL_API_KEY"
    assert "fixture-secret-not-persisted" not in json.dumps(receipt)
    assert call_count["submit"] == 0
    assert receipt["actual_provider_call_attempts"] == 0

    _media, approvals, ready = common.compile_bundle(inputs)
    assert ready["technical_blockers"] == []
    assert ready["status"] == "BLOCKED_AWAITING_HUMAN_APPROVAL"
    assert ready["missing_approval_types"] == sorted(common.APPROVAL_TYPES)
    assert approvals["missing_approval_types"] == sorted(common.APPROVAL_TYPES)


def test_preflight_blocks_absent_key_and_absent_ffprobe_without_provider_call(tmp_path: Path):
    inputs = ready_inputs(tmp_path)
    receipt = execution.run_adapter_preflight(
        inputs,
        current=datetime(2026, 7, 15, 12, tzinfo=timezone.utc),
        poll_interval_seconds=5,
        max_polls=180,
        adapter_script_path=ROOT / "scripts" / "phase11_fal_canary_adapter.py",
        environ={},
        importer=fixture_fal_importer,
        ffprobe_resolver=lambda _name: None,
    )
    assert receipt["status"] == "BLOCKED_PHASE11_ADAPTER_PREFLIGHT"
    assert "BLOCKED_FAL_CREDENTIAL_MISSING" in receipt["technical_blockers"]
    assert "BLOCKED_PHASE11_FFPROBE_MISSING" in receipt["technical_blockers"]
    assert receipt["actual_provider_call_attempts"] == 0


def test_approval_writer_rejects_wrong_hash_stale_or_revoked_and_dry_run_writes_nothing(tmp_path: Path):
    inputs = ready_inputs(tmp_path)
    packet_path = inputs.context.run_root / "phase11-human" / "authorization_packet.json"
    packet = authorization_packet(inputs, packet_path)
    wrong = json.loads(json.dumps(packet))
    wrong["bindings"]["request_body_sha256"] = "sha256:" + "0" * 64
    write_json(packet_path, wrong)
    with pytest.raises(common.Phase11Blocked) as wrong_hash:
        execution.write_approval_receipts(
            inputs,
            wrong,
            packet_path=packet_path,
            current=datetime(2026, 7, 15, 12, 5, tzinfo=timezone.utc),
            dry_run=False,
        )
    assert wrong_hash.value.code == "BLOCKED_PHASE11_AUTHORIZATION_PACKET_BINDING:bindings"

    stale = authorization_packet(inputs, packet_path, expires_at="2026-07-15T12:01:00+00:00")
    with pytest.raises(common.Phase11Blocked) as expired:
        execution.write_approval_receipts(
            inputs,
            stale,
            packet_path=packet_path,
            current=datetime(2026, 7, 15, 12, 5, tzinfo=timezone.utc),
            dry_run=False,
        )
    assert expired.value.code == "BLOCKED_PHASE11_AUTHORIZATION_PACKET_EXPIRED"

    packet = authorization_packet(inputs, packet_path)
    dry = execution.write_approval_receipts(
        inputs,
        packet,
        packet_path=packet_path,
        current=datetime(2026, 7, 15, 12, 5, tzinfo=timezone.utc),
        dry_run=True,
    )
    assert dry["status"] == "PASS_PHASE11_APPROVAL_PACKET_VALIDATED_DRY_RUN"
    assert not inputs.approval_root.exists()

    written = execution.write_approval_receipts(
        inputs,
        packet,
        packet_path=packet_path,
        current=datetime(2026, 7, 15, 12, 5, tzinfo=timezone.utc),
        dry_run=False,
    )
    assert written["approval_receipt_count"] == 5
    request_hash = execution.build_execution_state(inputs).bindings["request_body_sha256"]
    paid_path = (
        inputs.approval_root
        / execution.request_digest(request_hash)
        / common.APPROVAL_FILES["paid_call_authorization"]
    )
    paid = common.read_object(paid_path)
    paid["revoked"] = True
    paid["revocation_state"] = "REVOKED"
    write_json(paid_path, paid)
    state = execution.build_execution_state(inputs)
    _statuses, _missing, blockers = common.inspect_approvals(
        inputs,
        state.bindings,
        datetime(2026, 7, 15, 12, 5, tzinfo=timezone.utc),
    )
    assert any("paid_call_authorization:revoked" in blocker for blocker in blockers)


def test_submit_fence_prevents_duplicate_and_resumes_existing_task(tmp_path: Path):
    inputs = ready_inputs(tmp_path)
    request_hash = execution.build_execution_state(inputs).bindings["request_body_sha256"]
    calls = {"count": 0}

    def submit():
        calls["count"] += 1
        return "task-fixture-1"

    first = execution.submit_once(
        inputs,
        request_hash,
        current=datetime(2026, 7, 15, 12, 10, tzinfo=timezone.utc),
        submit=submit,
    )
    assert first.action == "submitted_once"
    assert first.request_id == "task-fixture-1"
    assert calls["count"] == 1

    second = execution.submit_once(
        inputs,
        request_hash,
        current=datetime(2026, 7, 15, 12, 11, tzinfo=timezone.utc),
        submit=lambda: (_ for _ in ()).throw(AssertionError("duplicate submit")),
    )
    assert second.action == "resume_existing_task"
    assert second.request_id == "task-fixture-1"
    assert calls["count"] == 1


def test_ambiguous_submit_is_persisted_and_never_resubmitted(tmp_path: Path):
    inputs = ready_inputs(tmp_path)
    request_hash = execution.build_execution_state(inputs).bindings["request_body_sha256"]
    with pytest.raises(common.Phase11Blocked) as ambiguous:
        execution.submit_once(
            inputs,
            request_hash,
            current=datetime(2026, 7, 15, 12, 10, tzinfo=timezone.utc),
            submit=lambda: (_ for _ in ()).throw(TimeoutError("unknown provider acceptance")),
        )
    assert ambiguous.value.code == "BLOCKED_PHASE11_AMBIGUOUS_SUBMIT_REQUIRES_HUMAN_RECONCILIATION"
    ledger = common.read_object(execution.attempt_ledger_path(inputs, request_hash))
    assert ledger["state"] == "AMBIGUOUS_SUBMIT"
    assert ledger["actual_provider_call_attempts"] == 1
    with pytest.raises(common.Phase11Blocked) as retry:
        execution.submit_once(
            inputs,
            request_hash,
            current=datetime(2026, 7, 15, 12, 11, tzinfo=timezone.utc),
            submit=lambda: "must-not-submit",
        )
    assert retry.value.code == "BLOCKED_PHASE11_AMBIGUOUS_SUBMIT_REQUIRES_HUMAN_RECONCILIATION"


FAILED_REQUEST_HASH = "sha256:444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71"


def test_new_request_hash_isolated_from_consumed_failed_ledger(tmp_path: Path) -> None:
    inputs = ready_inputs(tmp_path)
    current_state = execution.build_execution_state(inputs)
    current_hash = current_state.bindings["request_body_sha256"]
    assert current_hash != FAILED_REQUEST_HASH

    failed_path = execution.attempt_ledger_path(inputs, FAILED_REQUEST_HASH)
    failed = execution.new_preflight_ledger(
        inputs, FAILED_REQUEST_HASH, datetime(2026, 7, 16, 11, tzinfo=timezone.utc)
    )
    failed.update(
        {
            "state": "FAILED",
            "submit_intent_count": 1,
            "actual_provider_call_attempts": 1,
            "request_id": "019f6acb-853c-7552-bc73-ff8a6548afb1",
            "poll_count": 2,
            "provider_terminal_state": "RESULT_VALIDATION_FAILED",
            "automatic_resubmit_allowed": False,
            "last_error": {
                "status": "BLOCKED_PHASE11_PROVIDER_REQUEST_VALIDATION",
                "automatic_resubmit_allowed": False,
            },
        }
    )
    execution.atomic_write_json(failed_path, failed)
    failed_bytes = failed_path.read_bytes()

    observation, blockers = common.request_attempt_observation(inputs, current_hash)
    assert blockers == []
    assert observation["state"] == "PREFLIGHT_READY"
    assert observation["actual_provider_call_attempts"] == 0
    assert failed_path.read_bytes() == failed_bytes
    assert common.read_object(failed_path)["actual_provider_call_attempts"] == 1


def test_compiler_reports_authoritative_selected_request_attempt_count(tmp_path: Path) -> None:
    inputs = ready_inputs(tmp_path)
    request_hash = execution.build_execution_state(inputs).bindings["request_body_sha256"]
    ledger_path = execution.attempt_ledger_path(inputs, request_hash)
    ledger = common.read_object(ledger_path)
    ledger.update(
        {
            "state": "FAILED",
            "submit_intent_count": 1,
            "actual_provider_call_attempts": 1,
            "request_id": "task-failed-1",
            "provider_terminal_state": "RESULT_VALIDATION_FAILED",
            "automatic_resubmit_allowed": False,
        }
    )
    execution.atomic_write_json(ledger_path, ledger)

    _media, approvals, request = common.compile_bundle(inputs)
    assert request["actual_provider_call_attempts"] == 1
    assert request["generation_call_started"] is True
    assert request["provider_live"] is True
    assert request["submitted"] is True
    assert approvals["actual_provider_call_attempts"] == 1
    assert approvals["bindings"]["actual_provider_call_attempts"] == 1
    assert "BLOCKED_PHASE11_ATTEMPT_LEDGER_STATE:FAILED" in request["technical_blockers"]


def test_terminal_provider_result_error_is_persisted_and_never_resubmitted(
    tmp_path: Path,
) -> None:
    inputs = ready_inputs(tmp_path)
    request_hash = execution.build_execution_state(inputs).bindings["request_body_sha256"]
    decision = execution.submit_once(
        inputs,
        request_hash,
        current=datetime(2026, 7, 16, 12, tzinfo=timezone.utc),
        submit=lambda: "task-result-validation-1",
    )
    assert decision.request_id == "task-result-validation-1"

    class Response:
        status_code = 422

        @staticmethod
        def json():
            return {
                "detail": [
                    {
                        "loc": ["body", "multi_prompt", 0, "prompt"],
                        "msg": "Value error, Prompt must not exceed 512 characters.",
                        "type": "value_error",
                        "ctx": {"error": "Prompt must not exceed 512 characters."},
                        "input": "x" * 513,
                    }
                ]
            }

    class FalClientHTTPError(RuntimeError):
        def __init__(self) -> None:
            super().__init__("422 provider result validation")
            self.response = Response()

    receipt, ledger = execution.persist_provider_result_error(
        inputs,
        request_hash,
        endpoint="fal-ai/kling-video/v3/standard/image-to-video",
        request_id="task-result-validation-1",
        current=datetime(2026, 7, 16, 12, 1, tzinfo=timezone.utc),
        poll_count=2,
        error=FalClientHTTPError(),
    )
    assert receipt["status"] == "BLOCKED_PHASE11_PROVIDER_REQUEST_VALIDATION"
    assert receipt["http_status"] == 422
    assert receipt["error_count"] == 1
    assert receipt["errors"][0]["input_character_count"] == 513
    assert receipt["actual_provider_call_attempts"] == 1
    assert receipt["automatic_resubmit_allowed"] is False
    assert receipt["returned_video"] is False
    assert receipt["watch_invoked"] is False
    assert ledger["state"] == "FAILED"
    assert ledger["actual_provider_call_attempts"] == 1
    assert ledger["request_id"] == "task-result-validation-1"
    assert ledger["last_error"]["receipt_sha256"].startswith("sha256:")

    calls = {"count": 0}
    with pytest.raises(common.Phase11Blocked) as blocked:
        execution.submit_once(
            inputs,
            request_hash,
            current=datetime(2026, 7, 16, 12, 2, tzinfo=timezone.utc),
            submit=lambda: calls.__setitem__("count", calls["count"] + 1),
        )
    assert blocked.value.code == "BLOCKED_PHASE11_PROVIDER_REQUEST_VALIDATION"
    assert calls["count"] == 0
