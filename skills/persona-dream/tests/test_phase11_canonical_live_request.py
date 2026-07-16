from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import phase11_canonical_common as common  # noqa: E402
import compile_phase11_canonical_live_request as compiler  # noqa: E402
import validate_phase11_canonical_live_request as validator  # noqa: E402
from phase11_fixture_helpers import (  # noqa: E402
    fake_memory_server,
    install_adapter_preflight,
    make_compilation_inputs,
    sha256_bytes,
    write_json,
)


def local_ref(run_root: Path, path: Path) -> dict[str, str]:
    return {
        "relative_path": path.resolve().relative_to(run_root.resolve()).as_posix(),
        "sha256": sha256_bytes(path.read_bytes()),
    }


def install_transition_evidence(
    inputs: common.CompilationInputs,
    request_body: dict[str, Any],
    *,
    install_preflight: bool = True,
) -> common.CompilationInputs:
    slots: dict[str, dict[str, Any]] = {}

    def add(pointer: str, url: str) -> None:
        artifact_id, entry = common.artifact_for_url(inputs.context, url)
        current = slots.setdefault(
            artifact_id,
            {
                "artifact_id": artifact_id,
                "url": url,
                "sha256": entry["sha256"],
                "json_pointers": [],
            },
        )
        assert current["url"] == url
        current["json_pointers"].append(pointer)

    add("/input/start_image_url", request_body["start_image_url"])
    add("/input/end_image_url", request_body["end_image_url"])
    for element_index, element in enumerate(request_body["elements"]):
        add(f"/input/elements/{element_index}/frontal_image_url", element["frontal_image_url"])
        for reference_index, url in enumerate(element["reference_image_urls"]):
            add(f"/input/elements/{element_index}/reference_image_urls/{reference_index}", url)
    assert len(slots) == 7

    entries = []
    for artifact_id, binding in sorted(slots.items()):
        root = inputs.context.run_root / "phase11-fixture-evidence" / artifact_id
        publication = write_json(
            root / "existing_publication_receipt.json",
            {
                "schema": "persona_dream.phase11_existing_publication_receipt.v1",
                "status": "OBSERVED_EXISTING_PUBLIC_COMMIT_PINNED",
                "artifact_id": artifact_id,
                "url": binding["url"],
                "sha256": binding["sha256"],
                "source_commit": "0" * 40,
                "publication_performed_by_this_command": False,
                "publication_authorization_present": False,
                "observed_at": "2026-07-15T11:00:00+00:00",
                "actual_provider_call_attempts": 0,
            },
        )
        probe = write_json(
            root / "public_probe_receipt.json",
            {
                "schema": "persona_dream.phase11_public_media_probe_receipt.v1",
                "status": "PASS_PROVIDER_MEDIA_PUBLIC_FETCH",
                "artifact_id": artifact_id,
                "url": binding["url"],
                "final_url": binding["url"],
                "http_status": 200,
                "content_type": "image/png",
                "content_length": 1,
                "downloaded_sha256": binding["sha256"],
                "checked_at": "2026-07-15T11:00:00+00:00",
                "actual_provider_call_attempts": 0,
            },
        )
        teardown = write_json(
            root / "teardown_policy_receipt.json",
            {
                "schema": "persona_dream.phase11_teardown_policy_receipt.v1",
                "status": "NOT_REQUIRED_PERSISTENT_COMMIT_PINNED",
                "artifact_id": artifact_id,
                "url": binding["url"],
                "source_commit": "0" * 40,
                "reason": "Fixture URL represents persistent commit-pinned content.",
                "actual_provider_call_attempts": 0,
            },
        )
        entries.append(
            {
                "artifact_id": artifact_id,
                "json_pointers": sorted(binding["json_pointers"]),
                "url": binding["url"],
                "sha256": binding["sha256"],
                "publication_authorization": {
                    "approval_type": "publication_authorization",
                    "state": "MISSING_HUMAN_APPROVAL",
                },
                "publication_receipt": local_ref(inputs.context.run_root, publication),
                "public_probe": local_ref(inputs.context.run_root, probe),
                "teardown_policy": local_ref(inputs.context.run_root, teardown),
            }
        )
    transition = {
        "schema": "persona_dream.provider_media_transition_manifest.v1",
        "status": "PASS_PROVIDER_MEDIA_TRANSITIONS_TECHNICAL",
        "run_id": inputs.context.run_id,
        "revision_id": inputs.context.revision_id,
        "activation_transaction_id": inputs.context.activation_transaction_id,
        "checked_at": "2026-07-15T11:00:00+00:00",
        "request_asset_count": 7,
        "entries": entries,
        "publication_authorization_required": True,
        "publication_authorization_present": False,
        "publication_performed_by_this_command": False,
        "actual_provider_call_attempts": 0,
        "provider_live": False,
        "submitted": False,
    }
    assert common.validate_schema(transition, "provider_media_transition_manifest.v1.schema.json") == []
    write_json(inputs.transition_manifest_path, transition)
    resolved = replace(inputs, transition_manifest=transition)
    return install_adapter_preflight(resolved) if install_preflight else resolved


def test_canonical_compiler_normalizes_tier_timing_and_silent_sb003(tmp_path: Path):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    request_body, initial_blockers, transformations = common.compile_request_body(inputs)
    assert initial_blockers == []
    inputs = install_transition_evidence(inputs, request_body)
    media, approvals, request = common.compile_bundle(inputs)

    assert media["role_counts"] == {
        "global_start_anchor": 1,
        "global_end_anchor": 1,
        "continuity_only": 6,
        "element_packs": 2,
    }
    assert media["blockers"] == []
    start_frame = next(item for item in media["storyboard_frames"] if item["artifact_id"] == "sb_001.start_frame")
    assert start_frame["json_pointer"] == "/input/start_image_url"
    assert start_frame["transition_evidence"]["public_probe"]["status"] == "PASS_PROVIDER_MEDIA_PUBLIC_FETCH"
    assert media["element_packs"][0]["images"][0]["json_pointer"] == "/input/elements/0/frontal_image_url"
    assert media["element_packs"][0]["images"][0]["transition_evidence"]["public_probe"]["status"] == "PASS_PROVIDER_MEDIA_PUBLIC_FETCH"
    assert request["status"] == "BLOCKED_AWAITING_HUMAN_APPROVAL"
    assert request["technical_blockers"] == []
    assert request["missing_approval_types"] == [
        "cost_acceptance",
        "exact_request_acceptance",
        "paid_call_authorization",
        "publication_authorization",
        "visual_media_acceptance",
    ]
    assert approvals["receipts"]["publication_authorization"]["state"] == "MISSING"
    assert request["actual_provider_call_attempts"] == 0
    assert request["provider_ready"] is False
    assert request["live_submit_ready"] is False

    prompts = request["provider_request_body"]["multi_prompt"]
    assert [item["duration"] for item in prompts] == ["2", "3", "2", "3"]
    assert [common.TIME_RANGE_RE.search(item["prompt"]).groups() for item in prompts] == [
        ("0", "2"),
        ("2", "5"),
        ("5", "7"),
        ("7", "10"),
    ]
    assert all("Kling v3 Standard I2V" in item["prompt"] for item in prompts)
    assert all("Kling v3 Pro I2V" not in item["prompt"] for item in prompts)
    sb003 = prompts[2]["prompt"]
    assert "quietly says" not in sb003
    assert "Dialogue cue:" not in sb003
    assert "If we paddle now" not in sb003
    assert "nonverbal hand signal" in sb003
    assert common.validate_request_body(
        request["provider_request_body"],
        endpoint=request["endpoint"],
        mode=request["mode"],
    ) == []
    assert request["request_body_canonicalization"] == {
        "encoding": "UTF-8",
        "json": "RFC8259",
        "sort_keys": True,
        "separators": [",", ":"],
        "ensure_ascii": False,
    }
    assert request["request_body_sha256"] == common.canonical_sha256(request["provider_request_body"])
    assert (
        any(item["panel_id"] == "sb_003" and "sb003_dialogue_removed" in item["changes"] for item in transformations)
        or "No spoken dialogue." in inputs.candidate_binding["input"]["multi_prompt"][2]["prompt"]
    )


def test_canonical_outputs_are_portable_and_byte_identical_across_worktree_prefixes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    inputs_a, _candidate_a, _urls_a = make_compilation_inputs(tmp_path / "WORKTREE_A")
    inputs_b, _candidate_b, _urls_b = make_compilation_inputs(tmp_path / "WORKTREE_B")

    bundle_a = common.compile_bundle(inputs_a)
    bundle_b = common.compile_bundle(inputs_b)
    names = ("media_binding_manifest", "approval_requirements", "live_request")
    for name, artifact_a, artifact_b in zip(names, bundle_a, bundle_b):
        assert common.pretty_json_bytes(artifact_a) == common.pretty_json_bytes(artifact_b), name
        assert common.serialized_file_sha256(artifact_a) == common.serialized_file_sha256(artifact_b), name
        assert common.canonical_path_violations(artifact_a) == [], name
        encoded = common.pretty_json_bytes(artifact_a).decode("utf-8")
        assert str(inputs_a.context.run_root) not in encoded
        assert str(inputs_b.context.run_root) not in encoded

    media_a, approvals_a, request_a = bundle_a
    assert media_a["source_files"]["media_lock"]["path"].startswith(
        ".persona-dream/revisions/"
    )
    assert all(
        not Path(frame["revision_relative_path"]).is_absolute()
        for frame in media_a["storyboard_frames"]
    )
    assert all(
        not Path(receipt["path"]).is_absolute()
        for receipt in approvals_a["receipts"].values()
    )
    assert not Path(request_a["source_files"]["phase10_payload"]["path"]).is_absolute()

    # Reproduce the clean-worktree scenario: artifacts compiled in A are
    # independently recomputed by the validator against the same revision in B.
    output_root_b = inputs_b.context.revision_root / common.DEFAULT_OUTPUT_RELATIVE
    common.write_compiled_bundle(output_root_b, *bundle_a)
    monkeypatch.setattr(validator, "load_inputs", lambda *_args, **_kwargs: inputs_b)
    rc = validator.main([
        "--run-root", str(inputs_b.context.run_root),
        "--output-root", str(output_root_b),
        "--now", "2026-07-15T12:00:00+00:00",
        "--test-fixture",
        "--json",
    ])
    assert rc == 0
    receipt = json.loads(
        (output_root_b / "phase11_validation_receipt.v1.json").read_text(encoding="utf-8")
    )
    assert not any(blocker.endswith("_NONDETERMINISTIC") for blocker in receipt["technical_blockers"])
    assert not any(
        blocker.startswith("BLOCKED_PHASE11_CANONICAL_PATH_NONPORTABLE")
        for blocker in receipt["technical_blockers"]
    )



def test_validator_detects_standard_pro_and_timing_contradictions(tmp_path: Path):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    request_body, blockers, _ = common.compile_request_body(inputs)
    assert blockers == []
    request_body["multi_prompt"][0]["prompt"] = request_body["multi_prompt"][0]["prompt"].replace(
        "Kling v3 Standard I2V", "Kling v3 Pro I2V"
    ).replace("time range 0s-2s", "time range 0s-2.5s")
    observed = common.validate_request_body(
        request_body,
        endpoint="fal-ai/kling-video/v3/standard/image-to-video",
        mode="standard",
    )
    assert "BLOCKED_PROVIDER_STANDARD_PRO_NAMING_CONFLICT:sb_001" in observed
    assert "BLOCKED_PROVIDER_TIME_RANGE_CONTRADICTION:sb_001" in observed


def test_provider_snapshot_ttl_is_fail_closed(tmp_path: Path):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    old = dict(inputs.provider_snapshot.value)
    old["retrieved_at"] = "2026-07-13T00:00:00+00:00"
    path = write_json(tmp_path / "old-provider.json", old)
    result = common.load_provider_snapshot(path, datetime(2026, 7, 15, 12, tzinfo=timezone.utc))
    assert "BLOCKED_PROVIDER_SOURCE_SNAPSHOT_TTL_EXPIRED" in result.blockers


def test_upstream_12_of_15_false_green_is_an_explicit_technical_blocker(tmp_path: Path):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    write_json(
        inputs.validation_path,
        {"status": "PASS_PANEL_REVIEWED", "passed_step_count": 12, "step_count": 15, "first_blocker": None},
    )
    request_body, _blockers, _ = common.compile_request_body(inputs)
    inputs = install_transition_evidence(inputs, request_body, install_preflight=False)
    _media, _approvals, request = common.compile_bundle(inputs)
    assert request["status"] == "BLOCKED_PROVIDER_GATE"
    assert "BLOCKED_UPSTREAM_VALIDATION_INCOMPLETE:12/15" in request["technical_blockers"]
    assert "BLOCKED_UPSTREAM_VALIDATION_FALSE_GREEN_FIRST_BLOCKER_NULL" in request["technical_blockers"]


def test_phase11_memory_key_is_stable_request_scoped_and_legacy_readable():
    run_id = "pipeline-complete"
    revision_id = "rev_idea_f3f9c48d5cc2"
    failed_request = "sha256:444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71"
    corrected_request = "sha256:9966f6b65cc323ef4780aa2109e8814d0d61c64e81e33dbb33d023679dd42e16"

    legacy = common.legacy_phase11_memory_key(run_id, revision_id)
    failed = common.phase11_memory_key(run_id, revision_id, failed_request)
    corrected = common.phase11_memory_key(run_id, revision_id, corrected_request)

    assert legacy == "pd_phase11_d1440cf980f38c916f0fa93bff648b17e036e58feb43a941"
    assert failed == "pd_phase11_ab56b1cf2875c1c9c35871073006bdc779397deae2777732"
    assert corrected == "pd_phase11_11c0a72cef02a4966cb3f21852341629a21dccbc6d2789ad"
    assert len({legacy, failed, corrected}) == 3
    assert common.phase11_memory_key(run_id, revision_id, failed_request) == failed
    assert common.phase11_memory_key(run_id, revision_id, corrected_request) == corrected

    with pytest.raises(common.Phase11Blocked) as invalid:
        common.phase11_memory_key(run_id, revision_id, "sha256:not-a-request-hash")
    assert invalid.value.code == "BLOCKED_PHASE11_REQUEST_BODY_HASH_INVALID"


def test_phase11_recall_is_revision_scoped_and_rejects_wrong_identity_or_zero_dense(tmp_path: Path):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    request_hash = "sha256:" + "1" * 64
    payload = common.phase11_recall_payload(inputs, "project_knowledge", request_hash)
    assert payload["tags"] == [f"phase11-request:{request_hash.removeprefix('sha256:')}"]
    assert payload["collections"] == ["project_knowledge"]
    assert payload["k"] == 20
    assert payload["threshold"] == 0.0
    assert request_hash in payload["q"]
    assert common.phase11_memory_key(inputs.context.run_id, inputs.context.revision_id, request_hash) in payload["q"]

    expected_key = "pd_phase11_expected"
    with pytest.raises(common.Phase11Blocked) as wrong_identity:
        common.validate_phase11_recall_items(
            [{"doc": {"_key": "pd_phase11_wrong"}, "scores": {"dense": 0.91}}],
            expected_key,
        )
    assert wrong_identity.value.code == "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED"
    assert wrong_identity.value.details == {"matching_identity_count": 0}

    with pytest.raises(common.Phase11Blocked) as zero_dense:
        common.validate_phase11_recall_items(
            [{"doc": {"_key": expected_key}, "scores": {"dense": 0.0}}],
            expected_key,
        )
    assert zero_dense.value.code == "BLOCKED_MEMORY_SEMANTIC_SYNC_REQUIRED"
    assert zero_dense.value.details == {"matching_identity_count": 1}

    accepted = common.validate_phase11_recall_items(
        [{"doc": {"_key": expected_key}, "scores": {"dense": 0.73}}],
        expected_key,
    )
    assert accepted == {
        "matching_identity_count": 1,
        "dense_matching_count": 1,
        "max_dense": 0.73,
    }


def test_phase11_memory_record_exact_reread_and_dense_recall(tmp_path: Path):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    request_body, _blockers, _ = common.compile_request_body(inputs)
    inputs = install_transition_evidence(inputs, request_body)
    media, approvals, request = common.compile_bundle(inputs)
    output_root = inputs.context.revision_root / "phase_11_submit_return" / "canonical"
    paths = common.write_compiled_bundle(output_root, media, approvals, request)
    document = common.memory_document(
        inputs,
        gate_status=request["status"],
        media_file_sha256=sha256_bytes(paths["media_manifest"].read_bytes()),
        approval_file_sha256=sha256_bytes(paths["approval_requirements"].read_bytes()),
        request_file_sha256=sha256_bytes(paths["live_request"].read_bytes()),
        request_body_sha256=request["request_body_sha256"],
        technical_blockers=request["technical_blockers"],
        missing_approvals=request["missing_approval_types"],
    )
    with fake_memory_server() as (memory_url, state):
        state.collections.setdefault("project_knowledge", {})["pd_active_fixture"] = {
            "_key": "pd_active_fixture",
            "record_type": "active_revision_pointer",
            "run_id": inputs.context.run_id,
            "active_revision_id": inputs.context.revision_id,
            "semantic_sync_state": "synced",
        }
        evidence = common.persist_phase11_boundary(
            inputs,
            document,
            memory_url=memory_url,
            collection="project_knowledge",
            connect_timeout=1,
            read_timeout=5,
        )
    assert evidence["persisted"] is True
    assert evidence["exact_reread_count"] == 1
    assert evidence["semantic_sync_state"] == "synced"
    assert evidence["request_body_sha256"] == request["request_body_sha256"]
    assert evidence["phase11_key"] == common.phase11_memory_key(
        inputs.context.run_id, inputs.context.revision_id, request["request_body_sha256"]
    )
    assert evidence["legacy_phase11_key"] == common.legacy_phase11_memory_key(
        inputs.context.run_id, inputs.context.revision_id
    )
    request_tag = f"phase11-request:{request['request_body_sha256'].removeprefix('sha256:')}"
    assert evidence["recall"]["tags"] == [request_tag]
    assert evidence["recall"]["matching_identity_count"] == 1
    assert evidence["recall"]["dense_matching_count"] == 1
    assert evidence["recall"]["max_dense"] > 0
    recall_payloads = [payload for path, payload in state.requests if path == "/recall"]
    assert len(recall_payloads) == 1
    assert recall_payloads[0]["tags"] == [request_tag]
    assert document["_key"] in state.collections["project_knowledge"]
    assert request_tag in document["tags"]
    assert "revision_id" not in document
    assert document["phase11_revision_id"] == inputs.context.revision_id
    assert not common.FORBIDDEN_VECTOR_FIELDS.intersection(document)


def test_active_pointer_override_and_activation_hash_tampering_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    run_root = tmp_path / "pipeline-complete"
    revision_root = run_root / ".persona-dream" / "revisions" / "rev-active"
    revision_root.mkdir(parents=True)
    pointer_path = write_json(
        run_root / ".persona-dream" / "state" / "active_revision.json",
        {"revisionId": "rev-active", "runId": run_root.name},
    )
    activation_path = write_json(
        revision_root / "revision_activation_receipt.json",
        {
            "schema": "persona_dream.revision_activation_receipt.v1",
            "status": "PASS_ACTIVE_CONSISTENT",
            "source_commit": "a" * 40,
            "memory_url": "http://127.0.0.1:8601",
            "collection": "project_knowledge",
            "mocked": True,
            "live": False,
            "activated_at": "2026-07-15T00:00:00+00:00",
            "activation_transaction_id": "activation-" + "0" * 32,
            "memory": {},
        },
    )
    manifest = write_json(revision_root / "revision_manifest.json", {"runId": run_root.name, "revisionId": "rev-active"})
    index = write_json(revision_root / "revision_artifact_index.json", {"artifacts": {}})
    event_path = write_json(run_root / ".persona-dream" / "repair" / "queue-events" / "work" / "000001-completed.json", {"event": "expected"})
    snapshot = SimpleNamespace(
        run_root=run_root.resolve(),
        revision_root=revision_root.resolve(),
        run_id=run_root.name,
        revision_id="rev-active",
        source_revision_id="rev-source",
        source_commit="a" * 40,
        index_path=index.resolve(),
        manifest_path=manifest.resolve(),
        index_sha256=sha256_bytes(index.read_bytes()),
        manifest_sha256=sha256_bytes(manifest.read_bytes()),
    )
    monkeypatch.setattr(common, "load_snapshot", lambda *_args: snapshot)
    monkeypatch.setattr(common, "validate_prepare_verify_chain", lambda *_args: {"runtime_release_id": "fixture", "prepare_sha256": "sha256:" + "1" * 64, "verify_sha256": "sha256:" + "2" * 64})
    monkeypatch.setattr(common, "validate_local_pointer", lambda *_args: {"path": pointer_path, "sha256": sha256_bytes(pointer_path.read_bytes()), "value": {}})
    monkeypatch.setattr(common, "validate_repair_queue", lambda *_args: {"event_path": event_path, "work_order_sha256": "sha256:" + "3" * 64, "queue_sha256": "sha256:" + "4" * 64})
    monkeypatch.setattr(common, "activation_transaction_id", lambda *_args: "activation-" + "f" * 32)
    monkeypatch.setattr(common, "terminal_event", lambda *_args, **_kwargs: {"event": "expected"})
    monkeypatch.setattr(common, "make_file_refs", lambda *_args: {})
    monkeypatch.setattr(common, "validate_existing_activation_receipt", lambda *_args, **_kwargs: None)

    with pytest.raises(common.Phase11Blocked) as override:
        common.resolve_active_context(run_root, "rev-invented")
    assert override.value.code == "BLOCKED_ACTIVE_REVISION_OVERRIDE_MISMATCH"

    with pytest.raises(common.Phase11Blocked) as tampered:
        common.resolve_active_context(run_root)
    assert tampered.value.code == "BLOCKED_REVISION_ACTIVATION_TRANSACTION_HASH_MISMATCH"
    assert activation_path.is_file()


def test_independent_validator_writes_schema_valid_memory_backed_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    request_body, _blockers, _ = common.compile_request_body(inputs)
    inputs = install_transition_evidence(inputs, request_body)
    media, approvals, request = common.compile_bundle(inputs)
    output_root = inputs.context.revision_root / "phase_11_submit_return" / "canonical"
    common.write_compiled_bundle(output_root, media, approvals, request)
    monkeypatch.setattr(validator, "load_inputs", lambda *_args, **_kwargs: inputs)

    with fake_memory_server() as (memory_url, state):
        documents = state.collections.setdefault("project_knowledge", {})
        legacy_key = common.legacy_phase11_memory_key(
            inputs.context.run_id, inputs.context.revision_id
        )
        legacy_failed = {
            "_key": legacy_key,
            "record_type": "phase11_boundary",
            "run_id": inputs.context.run_id,
            "phase11_revision_id": inputs.context.revision_id,
            "request_body_sha256": "sha256:444a5a27e35c70848819aa561fc429f6e48d633c2bcc8ac805f675ac5b5f4b71",
            "actual_provider_call_attempts": 1,
            "provider_terminal_state": "RESULT_VALIDATION_FAILED",
            "provider_result_http_status": 422,
            "authorization_consumed": True,
            "automatic_resubmit_allowed": False,
        }
        documents[legacy_key] = json.loads(json.dumps(legacy_failed))
        documents["pd_active_fixture"] = {
            "_key": "pd_active_fixture",
            "record_type": "active_revision_pointer",
            "run_id": inputs.context.run_id,
            "active_revision_id": inputs.context.revision_id,
            "semantic_sync_state": "synced",
        }
        rc = validator.main([
            "--run-root", str(inputs.context.run_root),
            "--output-root", str(output_root),
            "--persist-memory",
            "--memory-url", memory_url,
            "--collection", "project_knowledge",
            "--now", "2026-07-15T12:00:00+00:00",
            "--test-fixture",
        ])
    assert rc == 0
    receipt_path = output_root / "phase11_validation_receipt.v1.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert common.validate_schema(receipt, "phase11_validation_receipt.v1.schema.json") == []
    assert receipt["validator_status"] == "PASS_PHASE11_CANONICAL_BOUNDARY_VALIDATED"
    assert receipt["gate_status"] == "BLOCKED_AWAITING_HUMAN_APPROVAL"
    assert receipt["memory"]["persisted"] is True
    assert receipt["memory"]["exact_reread_count"] == 1
    assert receipt["memory"]["request_body_sha256"] == request["request_body_sha256"]
    corrected_key = common.phase11_memory_key(
        inputs.context.run_id,
        inputs.context.revision_id,
        request["request_body_sha256"],
    )
    assert receipt["memory"]["phase11_key"] == corrected_key
    assert receipt["memory"]["legacy_phase11_key"] == legacy_key
    assert receipt["memory"]["recall"]["max_dense"] > 0
    assert receipt["mocked"] is True
    assert receipt["live"] is False
    assert receipt["actual_provider_call_attempts"] == 0
    assert state.collections["project_knowledge"][legacy_key] == legacy_failed
    assert corrected_key in state.collections["project_knowledge"]
    assert corrected_key != legacy_key
    assert "provider_result_http_status" not in state.collections["project_knowledge"][corrected_key]


def test_compiler_cli_writes_canonical_artifacts_without_provider_calls(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    inputs, _candidate, _urls = make_compilation_inputs(tmp_path)
    request_body, _blockers, _ = common.compile_request_body(inputs)
    inputs = install_transition_evidence(inputs, request_body)
    output_root = inputs.context.revision_root / "phase_11_submit_return" / "canonical-cli"
    monkeypatch.setattr(compiler, "load_inputs", lambda *_args, **_kwargs: inputs)
    rc = compiler.main([
        "--run-root", str(inputs.context.run_root),
        "--output-root", str(output_root),
        "--now", "2026-07-15T12:00:00+00:00",
        "--json",
    ])
    assert rc == 0
    request = json.loads((output_root / "phase11_live_request.v1.json").read_text(encoding="utf-8"))
    assert common.validate_schema(request, "phase11_live_request.v1.schema.json") == []
    assert request["status"] == "BLOCKED_AWAITING_HUMAN_APPROVAL"
    assert request["actual_provider_call_attempts"] == 0
    assert request["provider_live"] is False
    assert request["submitted"] is False
