from __future__ import annotations

import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import capture_phase11_provider_source_snapshot as provider_capture  # noqa: E402
import capture_phase11_public_media_evidence as media_capture  # noqa: E402
import phase11_canonical_common as common  # noqa: E402
import reconcile_phase11_upstream_validation as upstream  # noqa: E402
from phase11_fixture_helpers import (  # noqa: E402
    install_adapter_preflight,
    make_compilation_inputs,
    write_json,
)


def official_schema_body() -> bytes:
    return (
        "fal-ai/kling-video/v3/standard/image-to-video "
        "start_image_url required end_image_url multi_prompt elements generate_audio "
        "duration shot_type negative_prompt cfg_scale 3,4,5,6,7,8,9,10,11,12,13,14,15"
    ).encode()


def official_pricing_body() -> bytes:
    return b"audio off 0.084 audio on 0.126 voice control 0.154"


def test_provider_snapshot_is_official_hash_bound_ttl_limited_and_zero_call(tmp_path: Path):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    output = inputs.context.revision_root / common.DEFAULT_PROVIDER_SNAPSHOT_RELATIVE
    snapshot = provider_capture.build_snapshot(
        context=inputs.context,
        phase10_payload_path=inputs.phase10_payload_path,
        candidate_binding_path=inputs.candidate_binding_path,
        schema_remote=provider_capture.RemoteBody(
            provider_capture.DEFAULT_SCHEMA_URL,
            provider_capture.DEFAULT_SCHEMA_URL,
            200,
            "text/html",
            official_schema_body(),
        ),
        pricing_remote=provider_capture.RemoteBody(
            provider_capture.DEFAULT_PRICING_URL,
            provider_capture.DEFAULT_PRICING_URL,
            200,
            "text/html",
            official_pricing_body(),
        ),
        retrieved_at="2026-07-15T12:00:00+00:00",
        ttl_seconds=86400,
        snapshot_path=output,
        argv=[
            "skills/persona-dream/run.sh",
            "capture-phase11-provider-source-snapshot",
            "--run-root",
            "<RUN_ROOT>",
        ],
    )
    assert common.validate_schema(snapshot, "phase11_provider_source_snapshot.v1.schema.json") == []
    assert snapshot["endpoint"] == "fal-ai/kling-video/v3/standard/image-to-video"
    assert snapshot["mode"] == "standard"
    assert snapshot["pricing_source"]["maximum_expected_cost_usd"] == 0.84
    assert snapshot["retrieval"]["provider_generation_call_attempted"] is False
    assert snapshot["actual_provider_call_attempts"] == 0
    assert snapshot["phase10_endpoint_migration"]["phase10_payload_sha256"] == common.sha256_file(inputs.phase10_payload_path)

    write_json(output, snapshot)
    loaded = common.load_provider_snapshot(
        output,
        datetime(2026, 7, 15, 13, tzinfo=timezone.utc),
        inputs.context,
    )
    assert loaded.blockers == ()
    stale = common.load_provider_snapshot(
        output,
        datetime(2026, 7, 16, 13, 0, 1, tzinfo=timezone.utc),
        inputs.context,
    )
    assert "BLOCKED_PROVIDER_SOURCE_SNAPSHOT_TTL_EXPIRED" in stale.blockers


def test_public_media_capture_binds_six_unique_request_assets_without_human_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)

    def fake_fetch(url: str, _timeout: float):
        _artifact_id, entry = common.artifact_for_url(inputs.context, url)
        body = common.safe_indexed_file(inputs.context.revision_root, str(entry["relative_path"])).read_bytes()
        return 200, url, {"Content-Type": str(entry.get("media_type") or "image/png")}, body

    monkeypatch.setattr(media_capture, "fetch_bytes", fake_fetch)
    manifest = media_capture.capture(
        inputs=inputs,
        timeout=1,
        checked_at="2026-07-15T12:00:00+00:00",
        allow_test_host=True,
    )
    assert manifest["status"] == "PASS_PROVIDER_MEDIA_TRANSITIONS_TECHNICAL"
    assert manifest["request_asset_count"] == 6
    assert manifest["publication_authorization_present"] is False
    assert all(entry["publication_authorization"]["state"] == "MISSING_HUMAN_APPROVAL" for entry in manifest["entries"])
    assert all(entry["public_probe"]["sha256"].startswith("sha256:") for entry in manifest["entries"])
    assert manifest["actual_provider_call_attempts"] == 0


def test_upstream_false_green_is_reconciled_without_claiming_deferred_steps(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    write_json(
        inputs.validation_path,
        {
            "schema": "persona_dream.complete_pipeline_report_validation.v1",
            "status": "PASS_PANEL_REVIEWED",
            "passed_step_count": 12,
            "step_count": 15,
            "first_blocker": None,
        },
    )
    monkeypatch.setattr(upstream, "resolve_active_context", lambda *_args, **_kwargs: inputs.context)
    corrected, receipt = upstream.reconcile(
        inputs.context.run_root,
        inputs.context.revision_id,
        "2026-07-15T12:00:00+00:00",
    )
    assert corrected["status"] == "BLOCKED_DOWNSTREAM_NOT_EXECUTED"
    assert corrected["first_blocker"] == "BLOCKED_PHASE11_PROVIDER_SUBMIT_NOT_EXECUTED"
    assert corrected["passed_step_count"] == 12
    assert corrected["step_count"] == 15
    assert [item["status"] for item in corrected["deferred_steps"]] == ["NOT_EXECUTED"] * 3
    assert receipt["status"] == "PASS_PHASE11_UPSTREAM_VALIDATION_RECONCILED"
    assert common.upstream_validation_blockers(inputs.validation_path, inputs.context) == []


def test_technical_evidence_leaves_only_five_hash_bound_human_approvals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)

    def fake_fetch(url: str, _timeout: float):
        _artifact_id, entry = common.artifact_for_url(inputs.context, url)
        body = common.safe_indexed_file(inputs.context.revision_root, str(entry["relative_path"])).read_bytes()
        return 200, url, {"Content-Type": str(entry.get("media_type") or "image/png")}, body

    monkeypatch.setattr(media_capture, "fetch_bytes", fake_fetch)
    transition = media_capture.capture(
        inputs=inputs,
        timeout=1,
        checked_at="2026-07-15T12:00:00+00:00",
        allow_test_host=True,
    )
    inputs = replace(inputs, transition_manifest=transition)
    inputs = install_adapter_preflight(inputs)
    media, approvals, request = common.compile_bundle(inputs)
    assert media["blockers"] == []
    assert request["technical_blockers"] == []
    assert request["status"] == "BLOCKED_AWAITING_HUMAN_APPROVAL"
    assert request["missing_approval_types"] == sorted(common.APPROVAL_TYPES)
    assert approvals["missing_approval_types"] == sorted(common.APPROVAL_TYPES)
    assert request["actual_provider_call_attempts"] == 0
    assert request["provider_live"] is False
    assert request["submitted"] is False
    assert request["provider_ready"] is False
    assert request["live_submit_ready"] is False


def test_corrected_upstream_validation_rebinds_to_active_revision_without_rewriting_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    write_json(
        inputs.validation_path,
        {
            "schema": "persona_dream.complete_pipeline_report_validation.v1",
            "status": "PASS_PANEL_REVIEWED",
            "passed_step_count": 12,
            "step_count": 15,
            "first_blocker": None,
        },
    )
    old_root = inputs.context.run_root / ".persona-dream" / "revisions" / "rev_rejected"
    old_root.mkdir(parents=True)
    old_context = replace(
        inputs.context,
        revision_root=old_root.resolve(),
        revision_id="rev_rejected",
        activation_transaction_id="activation-" + "c" * 32,
    )
    monkeypatch.setattr(upstream, "resolve_active_context", lambda *_args, **_kwargs: old_context)
    _corrected, old_receipt = upstream.reconcile(
        inputs.context.run_root,
        old_context.revision_id,
        "2026-07-15T11:00:00+00:00",
    )
    old_path = old_root / upstream.MIGRATION_RELATIVE
    old_bytes = old_path.read_bytes()
    assert old_receipt["revision_id"] == "rev_rejected"

    monkeypatch.setattr(upstream, "resolve_active_context", lambda *_args, **_kwargs: inputs.context)
    corrected, active_receipt = upstream.reconcile(
        inputs.context.run_root,
        inputs.context.revision_id,
        "2026-07-15T12:00:00+00:00",
    )
    active_path = inputs.context.revision_root / upstream.MIGRATION_RELATIVE
    assert active_receipt["revision_id"] == inputs.context.revision_id
    assert active_receipt["activation_transaction_id"] == inputs.context.activation_transaction_id
    assert active_receipt["source_validation_sha256"] == old_receipt["source_validation_sha256"]
    assert active_path.is_file()
    assert old_path.read_bytes() == old_bytes
    assert corrected["phase11_validation_migration_receipt"].endswith(
        f"{inputs.context.revision_id}/phase_11_submit_return/preflight/upstream_validation_migration_receipt.json"
    )
    assert corrected["actual_provider_call_attempts"] == 0
