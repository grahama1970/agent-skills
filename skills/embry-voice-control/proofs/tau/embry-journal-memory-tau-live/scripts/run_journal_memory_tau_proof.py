"""Run one exact journal event through Memory and one bounded Tau tick."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
from typing import Any

import httpx


LANE = Path(__file__).resolve().parents[1]
PHYSICAL_SOURCE_MODES = {
    "physical_live_horus",
    "recorded_physical_horus",
}
CLONE_SOURCE_MODES = {
    "qualified_horus_clone",
    "qualified_horus_audio",
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha256_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def event_hash(value: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical(value)).hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def post(
    client: httpx.Client,
    path: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = client.post(path, json=payload)
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, dict):
        raise ValueError(f"response_not_object:{path}")
    return value


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def reuse_call_receipt(
    path: Path,
    *,
    schema: str,
    request: dict[str, Any],
    source_event_id: str | None = None,
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    receipt = read_json(path)
    if receipt.get("schema") != schema or receipt.get("request") != request:
        raise ValueError(f"partial_receipt_contract_mismatch:{path}")
    if receipt.get("request_sha256") != event_hash(request):
        raise ValueError(f"partial_receipt_request_hash_mismatch:{path}")
    if source_event_id is not None and (
        receipt.get("source_event", {}).get("event_id") != source_event_id
    ):
        raise ValueError(f"partial_receipt_source_event_mismatch:{path}")
    response = receipt.get("response")
    if not isinstance(response, dict):
        raise ValueError(f"partial_receipt_response_missing:{path}")
    return response


def file_locator(path: Path) -> dict[str, str]:
    return {"path": str(path.resolve()), "sha256": sha256_path(path)}


def append_derived(
    journal: httpx.Client,
    source: dict[str, Any],
    event_type: str,
    causation_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    seed = {
        "source_event_id": source["event_id"],
        "type": event_type,
        "payload": payload,
    }
    event = {
        "schema": "embry.voice_event.v1",
        "event_id": event_type + "." + hashlib.sha256(canonical(seed)).hexdigest()[:16],
        "session_id": source["session_id"],
        "turn_id": source["turn_id"],
        "type": event_type,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "causation_id": causation_id,
        "correlation_id": source["correlation_id"],
        "producer": "embry.voice.journal_memory_tau_controller",
        "mocked": False,
        "live": True,
        "artifact_hashes": {
            key: value
            for key, value in payload.items()
            if key.endswith("sha256")
        },
        "receipt_hash": event_hash(seed),
        "payload": payload,
    }
    snapshot_response = journal.get(
        f"/v1/sessions/{source['session_id']}/journal"
    )
    snapshot_response.raise_for_status()
    existing = next(
        (
            item
            for item in snapshot_response.json().get("events", [])
            if item.get("event_id") == event["event_id"]
        ),
        None,
    )
    if existing is not None:
        immutable_fields = (
            "schema",
            "event_id",
            "session_id",
            "turn_id",
            "type",
            "causation_id",
            "correlation_id",
            "producer",
            "mocked",
            "live",
            "artifact_hashes",
            "receipt_hash",
            "payload",
        )
        if any(existing.get(key) != event.get(key) for key in immutable_fields):
            raise ValueError(f"derived_event_conflict:{event['event_id']}")
        return existing
    return post(journal, "/v1/listener/events", event)["event"]


def _verified_json_locator(locator: Any, label: str) -> dict[str, Any]:
    if not isinstance(locator, dict):
        raise ValueError(f"{label}_locator_missing")
    path = Path(str(locator.get("path") or "")).resolve()
    expected = str(locator.get("sha256") or "")
    if not path.is_file():
        raise FileNotFoundError(f"{label}_missing:{path}")
    actual = sha256_path(path)
    if actual != expected:
        raise ValueError(f"{label}_hash_mismatch:{expected}:{actual}")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label}_not_object")
    return value


def _json_contains_scalar(value: Any, expected: str) -> bool:
    expected_normalized = str(expected).removeprefix("sha256:")
    if isinstance(value, dict):
        return any(_json_contains_scalar(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(_json_contains_scalar(item, expected) for item in value)
    if isinstance(value, str):
        return value.removeprefix("sha256:") == expected_normalized
    return False


def _load_contract(
    path: Path,
    source_mode: str,
) -> dict[str, Any]:
    path = path.resolve()
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("mocked") is True or value.get("live") is not True:
        raise ValueError("source_contract_not_live")
    if value.get("status") != "PASS":
        raise ValueError("source_contract_not_pass")

    if source_mode in CLONE_SOURCE_MODES:
        expected = {
            "schema": "embry.audio_e2e.clone_source_contract.v1",
            "source_contract": "qualified_horus_clone",
            "source_identity": "qualified_horus_clone",
            "voice_persona": "horus_lupercal",
            "fresh_physical_human_speech": False,
            "speaker_identity_proven": False,
            "allow_personal_memory": False,
            "memory_source_policy": "non_personal_persona_project_scope",
            "release_readiness_authority": False,
            "suite_ready": False,
        }
        for key, expected_value in expected.items():
            if value.get(key) != expected_value:
                raise ValueError(f"clone_source_contract_invalid:{key}")
        checkpoint = value.get("checkpoint") or {}
        if not checkpoint.get("id") or not str(
            checkpoint.get("sha256") or ""
        ).startswith("sha256:"):
            raise ValueError("clone_checkpoint_provenance_missing")
        training = _verified_json_locator(
            checkpoint.get("training_receipt"),
            "clone_training_receipt",
        )
        if not _json_contains_scalar(training, str(checkpoint["id"])):
            raise ValueError("clone_training_checkpoint_id_missing")
        if not _json_contains_scalar(training, str(checkpoint["sha256"])):
            raise ValueError("clone_training_checkpoint_hash_missing")
        persona = value.get("persona_provenance") or {}
        if persona.get("speaker_id") != "horus_lupercal":
            raise ValueError("clone_persona_provenance_invalid")
        enrollment = _verified_json_locator(
            persona.get("physical_enrollment_receipt"),
            "clone_persona_enrollment",
        )
        profile_sha256 = str(persona.get("profile_sha256") or "")
        if not profile_sha256.startswith("sha256:"):
            raise ValueError("clone_persona_profile_hash_missing")
        if not _json_contains_scalar(enrollment, profile_sha256):
            raise ValueError("clone_persona_profile_hash_mismatch")
        return value

    if source_mode not in PHYSICAL_SOURCE_MODES:
        raise ValueError("source_mode_invalid")
    required = (
        "speaker_id",
        "profile_sha256",
        "threshold",
        "ambiguity_margin",
    )
    if any(value.get(key) is None for key in required):
        raise ValueError("physical_source_contract_fields_missing")
    if value.get("speaker_id") != "horus_lupercal":
        raise ValueError("physical_source_contract_not_horus")
    return {
        **value,
        "source_contract": "physical_horus_identity",
        "source_identity": "horus_lupercal",
        "voice_persona": "horus_lupercal",
        "fresh_physical_human_speech": source_mode == "physical_live_horus",
        "speaker_identity_proven": True,
        "allow_personal_memory": True,
        "release_readiness_authority": False,
        "suite_ready": False,
    }


def _validate_source_evidence(
    source: dict[str, Any],
    evidence: dict[str, Any],
    source_mode: str,
    contract: dict[str, Any],
) -> dict[str, Any]:
    payload = evidence.get("payload") or {}
    if evidence.get("session_id") != source["session_id"]:
        raise ValueError("source_evidence_session_mismatch")
    if evidence.get("turn_id") != source["turn_id"]:
        raise ValueError("source_evidence_turn_mismatch")
    if evidence.get("live") is not True or evidence.get("mocked") is not False:
        raise ValueError("source_evidence_not_live")

    if source_mode in CLONE_SOURCE_MODES:
        if evidence.get("type") != "audio_source.qualification.completed":
            raise ValueError("clone_source_evidence_type_invalid")
        if evidence.get("causation_id") != source["event_id"]:
            raise ValueError("clone_source_evidence_causation_mismatch")
        expected = {
            "source_contract": "qualified_horus_clone",
            "source_identity": "qualified_horus_clone",
            "voice_persona": "horus_lupercal",
            "fresh_physical_human_speech": False,
            "speaker_identity_proven": False,
            "allow_personal_memory": False,
            "release_readiness_authority": False,
            "suite_ready": False,
            "listener_audio_sha256": source["payload"]["audio_sha256"],
        }
        if any(payload.get(key) != expected_value for key, expected_value in expected.items()):
            raise ValueError("clone_source_evidence_contract_mismatch")
        if payload.get("checkpoint", {}).get("sha256") != contract["checkpoint"]["sha256"]:
            raise ValueError("clone_source_evidence_checkpoint_mismatch")
        return payload

    if evidence.get("type") != "speaker.verification.completed":
        raise ValueError("physical_speaker_evidence_type_invalid")
    if payload.get("profile_hash") != contract["profile_sha256"]:
        raise ValueError("physical_speaker_profile_hash_mismatch")
    if payload.get("audio_sha256") != source["payload"].get("audio_sha256"):
        raise ValueError("physical_speaker_audio_hash_mismatch")
    candidates = payload.get("candidates") or []
    horus = next(
        (
            candidate
            for candidate in candidates
            if candidate.get("speaker_id") == "horus_lupercal"
        ),
        None,
    )
    if horus is None:
        raise ValueError("physical_horus_candidate_missing")
    if float(horus.get("confidence") or 0.0) < float(contract["threshold"]):
        raise ValueError("physical_horus_candidate_below_threshold")
    return payload


def _memory_source_request(
    source: dict[str, Any],
    evidence: dict[str, Any],
    evidence_payload: dict[str, Any],
    source_mode: str,
    contract: dict[str, Any],
) -> tuple[dict[str, Any], str, bool]:
    if source_mode in CLONE_SOURCE_MODES:
        # The immutable Orpheus receipt proves the acoustic source, not a human
        # speaker identity.  Resolve with no candidates so Memory emits no
        # speaker/user tags and no speaker-scoped recall profile.
        source_identity = "qualified_horus_clone"
        return (
            {
                "speaker_evidence_id": evidence["event_id"],
                "session_id": source["session_id"],
                "turn_id": source["turn_id"],
                "persona_id": "embry",
                "threshold": 1.0,
                "ambiguity_margin": 0.0,
                "allow_personal_memory": False,
                "candidates": [],
            },
            source_identity,
            False,
        )

    return (
        {
            "speaker_evidence_id": evidence["event_id"],
            "session_id": source["session_id"],
            "turn_id": source["turn_id"],
            "persona_id": "embry",
            "threshold": float(contract["threshold"]),
            "ambiguity_margin": float(contract["ambiguity_margin"]),
            "allow_personal_memory": True,
            "candidates": evidence_payload["candidates"],
        },
        "horus_lupercal",
        True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal-url", required=True)
    parser.add_argument("--consumer-name", default="embry-journal-memory-tau-v1")
    parser.add_argument("--event-id", required=True)
    parser.add_argument(
        "--source-evidence-event-id",
        "--speaker-evidence-event-id",
        dest="source_evidence_event_id",
        required=True,
    )
    parser.add_argument("--expected-session-id", required=True)
    parser.add_argument("--expected-turn-id", required=True)
    parser.add_argument("--expected-sequence", required=True, type=int)
    contract_group = parser.add_mutually_exclusive_group(required=True)
    contract_group.add_argument("--source-contract-receipt", type=Path)
    contract_group.add_argument("--physical-enrollment-receipt", type=Path)
    contract_group.add_argument("--speaker-qualification-receipt", type=Path)
    parser.add_argument(
        "--source-mode",
        choices=tuple(sorted(PHYSICAL_SOURCE_MODES | CLONE_SOURCE_MODES)),
        default="physical_live_horus",
    )
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--tau-repo", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--lease-seconds", default=300, type=int)
    parser.add_argument("--memory-read-timeout-seconds", default=90.0, type=float)
    parser.add_argument("--answer-retry-authorization", type=Path)
    args = parser.parse_args()

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    contract_path = (
        args.source_contract_receipt
        or args.speaker_qualification_receipt
        or args.physical_enrollment_receipt
    ).resolve()
    contract = _load_contract(contract_path, args.source_mode)
    contract_name = str(contract["source_contract"])
    source_identity = str(contract["source_identity"])
    personal_memory_allowed = bool(contract["allow_personal_memory"])
    fresh_physical_human_speech = bool(contract["fresh_physical_human_speech"])

    goal_packet = json.loads((LANE / "goal-packet.json").read_text(encoding="utf-8"))
    goal_hash = "sha256:" + hashlib.sha256(canonical(goal_packet)).hexdigest()

    with httpx.Client(base_url=args.journal_url, timeout=10.0) as journal:
        journal_response = journal.get(
            f"/v1/sessions/{args.expected_session_id}/journal"
        )
        journal_response.raise_for_status()
        journal_payload = journal_response.json()
        by_id = {event["event_id"]: event for event in journal_payload["events"]}
        source = by_id.get(args.event_id)
        source_evidence = by_id.get(args.source_evidence_event_id)
        if source is None or source.get("type") != "listener.final_transcript":
            raise ValueError("source_event_not_final_transcript")
        if (
            source["session_id"],
            source["turn_id"],
            source["sequence"],
        ) != (
            args.expected_session_id,
            args.expected_turn_id,
            args.expected_sequence,
        ):
            raise ValueError("source_event_lineage_mismatch")
        if (
            source.get("live") is not True
            or source.get("mocked") is not False
            or not source.get("payload", {}).get("text")
        ):
            raise ValueError("live_listener_provenance_missing")
        if source_evidence is None:
            raise ValueError("source_evidence_missing")
        evidence_payload = _validate_source_evidence(
            source,
            source_evidence,
            args.source_mode,
            contract,
        )

        claim_path = out / "source-event-claim-receipt.json"
        if claim_path.is_file():
            claim_receipt = read_json(claim_path)
            if claim_receipt.get("source_event", {}).get("event_id") != source["event_id"]:
                raise ValueError("stored_source_claim_event_mismatch")
            if claim_receipt.get("claim", {}).get("consumer_name") != args.consumer_name:
                raise ValueError("stored_source_claim_consumer_mismatch")
        else:
            claim_response = post(
                journal,
                "/v1/listener/events/claim-one",
                {
                "consumer_name": args.consumer_name,
                "event_id": args.event_id,
                "expected_session_id": args.expected_session_id,
                "expected_turn_id": args.expected_turn_id,
                "expected_sequence": args.expected_sequence,
                "expected_type": "listener.final_transcript",
                "lease_seconds": args.lease_seconds,
                },
            )
            claim_receipt = {
            "schema": "embry.voice.source_event_claim_receipt.v1",
            "claim": {
                "consumer_name": args.consumer_name,
                "claimed": True,
                "lease_seconds": args.lease_seconds,
                "response": claim_response,
            },
            "source_event": source,
            "source_evidence_event": source_evidence,
            "journal": {
                "service_url": args.journal_url,
                "session_journal_sha256_at_claim": "sha256:" + journal_payload["sha256"],
            },
            }
            write_json(claim_path, claim_receipt)

        memory_timeout = httpx.Timeout(
            connect=10.0,
            read=args.memory_read_timeout_seconds,
            write=10.0,
            pool=10.0,
        )
        with httpx.Client(base_url=args.memory_url, timeout=memory_timeout) as memory:
            speaker_request, expected_speaker_id, expected_personal_memory = (
                _memory_source_request(
                    source,
                    source_evidence,
                    evidence_payload,
                    args.source_mode,
                    contract,
                )
            )
            speaker_path = out / "memory-speaker-resolution-receipt.json"
            speaker_response = reuse_call_receipt(
                speaker_path,
                schema="embry.memory.speaker_resolution_call_receipt.v1",
                request=speaker_request,
            ) or post(memory, "/speaker/resolve", speaker_request)
            if args.source_mode in CLONE_SOURCE_MODES:
                if speaker_response.get("status") != "unknown":
                    raise ValueError("memory_clone_source_resolution_not_unknown")
                if speaker_response.get("speaker_id") is not None:
                    raise ValueError("memory_clone_source_claimed_speaker_identity")
                if speaker_response.get("recall_profile") is not None:
                    raise ValueError("memory_clone_source_recall_profile_not_null")
                memory_tags = speaker_response.get("memory_tags") or []
                if any(
                    str(tag).startswith(("speaker:", "user:"))
                    for tag in memory_tags
                ):
                    raise ValueError("memory_clone_source_emitted_personal_tags")
            else:
                if speaker_response.get("status") != "known":
                    raise ValueError("memory_physical_source_resolution_not_known")
                if speaker_response.get("speaker_id") != expected_speaker_id:
                    raise ValueError("memory_source_resolution_identity_mismatch")
            if (
                speaker_response.get("allow_personal_memory")
                is not expected_personal_memory
            ):
                raise ValueError("memory_personal_policy_mismatch")
            speaker_call = {
                "schema": "embry.memory.speaker_resolution_call_receipt.v1",
                "request": speaker_request,
                "request_sha256": event_hash(speaker_request),
                "response": speaker_response,
                "response_sha256": event_hash(speaker_response),
                "source_contract": contract_name,
            }
            if not speaker_path.exists():
                write_json(speaker_path, speaker_call)
            memory_source_event = append_derived(
                journal,
                source,
                (
                    "memory.speaker_resolved"
                    if contract_name == "physical_horus_identity"
                    else "memory.synthetic_source_restricted"
                ),
                source_evidence["event_id"],
                {
                    "response_path": str(speaker_path),
                    "response_sha256": sha256_path(speaker_path),
                    "source_contract": contract_name,
                    "source_identity": source_identity,
                    "allow_personal_memory": personal_memory_allowed,
                },
            )

            turn_text = str(source["payload"]["text"])
            listener_evidence = {
                "source": args.source_mode,
                "source_mode": args.source_mode,
                "source_contract": contract_name,
                "source_identity": source_identity,
                "voice_persona": contract.get("voice_persona"),
                "source_event_id": source["event_id"],
                "source_event_sequence": source["sequence"],
                "source_event_receipt_hash": source["receipt_hash"],
                "source_evidence_event_id": source_evidence["event_id"],
                "fresh_physical_human_speech": fresh_physical_human_speech,
                "speaker_identity_proven": bool(contract["speaker_identity_proven"]),
                "allow_personal_memory": personal_memory_allowed,
                "release_readiness_authority": False,
                "suite_ready": False,
            }
            intent_request = {
                "q": turn_text,
                "scope": "embry",
                "fast": True,
            }
            if contract_name == "physical_horus_identity":
                intent_request.update(
                    {
                        "speaker_id": source_identity,
                        "speaker_resolution": speaker_response,
                    }
                )
            intent_path = out / "memory-intent-receipt.json"
            intent_response = reuse_call_receipt(
                intent_path,
                schema="embry.memory.intent_call_receipt.v1",
                request=intent_request,
                source_event_id=source["event_id"],
            ) or post(memory, "/intent", intent_request)
            intent_call = {
                "schema": "embry.memory.intent_call_receipt.v1",
                "request": intent_request,
                "listener_evidence": listener_evidence,
                "request_sha256": event_hash(intent_request),
                "response": intent_response,
                "response_sha256": event_hash(intent_response),
                "speaker_resolution_response_sha256": event_hash(speaker_response),
                "source_event": {
                    key: source[key]
                    for key in (
                        "event_id",
                        "sequence",
                        "session_id",
                        "turn_id",
                        "type",
                    )
                },
            }
            if not intent_path.exists():
                write_json(intent_path, intent_call)
            intent_event = append_derived(
                journal,
                source,
                "memory.intent_resolved",
                memory_source_event["event_id"],
                {
                    "response_path": str(intent_path),
                    "response_sha256": sha256_path(intent_path),
                    "source_contract": contract_name,
                },
            )

            answer_request = {
                "q": turn_text,
                "scope": "embry",
                "persona_id": "embry",
            }
            answer_path = out / "memory-answer-receipt.json"
            answer_response = reuse_call_receipt(
                answer_path,
                schema="embry.memory.answer_call_receipt.v1",
                request=answer_request,
                source_event_id=source["event_id"],
            )
            attempts = sorted(out.glob("memory-answer-attempt-*.json"))
            authorization = None
            if args.answer_retry_authorization:
                authorization = read_json(args.answer_retry_authorization.resolve())
                required = {
                    "schema": "embry.audio_e2e.memory_answer_retry_authorization.v1",
                    "status": "PASS",
                    "source_event_id": source["event_id"],
                    "source_event_sequence": source["sequence"],
                    "session_id": source["session_id"],
                    "turn_id": source["turn_id"],
                    "authorized_execution_index": 2,
                    "prior_result": "transport_timeout_response_unknown",
                    "provider_execution_may_have_continued": True,
                    "idempotent_recovery_available": False,
                    "explicit_second_provider_execution_authorized": True,
                    "suite_ready": False,
                    "release_readiness_authority": False,
                }
                for key, expected in required.items():
                    if authorization.get(key) != expected:
                        raise ValueError(f"answer_retry_authorization_invalid:{key}")
                if not attempts:
                    first_attempt = {
                        "schema": "embry.memory.answer_transport_attempt.v1",
                        "status": "TRANSPORT_TIMEOUT_RESPONSE_UNKNOWN",
                        "execution_index": 1,
                        "request": answer_request,
                        "request_sha256": event_hash(answer_request),
                        "source_event_id": source["event_id"],
                        "provider_execution_may_have_continued": True,
                        "idempotent_recovery_available": False,
                        "inferred_from_campaign_failure": True,
                        "retry_authorization": file_locator(
                            args.answer_retry_authorization.resolve()
                        ),
                        "suite_ready": False,
                    }
                    first_path = out / "memory-answer-attempt-001.json"
                    write_json(first_path, first_attempt)
                    attempts = [first_path]
            if answer_response is None:
                if attempts and authorization is None:
                    raise RuntimeError("memory_answer_prior_timeout_response_unknown")
                if len(attempts) >= 2:
                    raise RuntimeError("memory_answer_retry_budget_exhausted")
                execution_index = len(attempts) + 1
                attempt_path = out / f"memory-answer-attempt-{execution_index:03d}.json"
                attempt = {
                    "schema": "embry.memory.answer_transport_attempt.v1",
                    "status": "STARTED",
                    "execution_index": execution_index,
                    "request": answer_request,
                    "request_sha256": event_hash(answer_request),
                    "source_event_id": source["event_id"],
                    "read_timeout_seconds": args.memory_read_timeout_seconds,
                    "retried_provider_call": execution_index > 1,
                    "idempotent_recovery": False,
                    "suite_ready": False,
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
                write_json(attempt_path, attempt)
                started = time.monotonic()
                try:
                    answer_response = post(memory, "/answer", answer_request)
                except httpx.ReadTimeout as exc:
                    attempt.update({
                        "status": "TRANSPORT_TIMEOUT_RESPONSE_UNKNOWN",
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "provider_execution_may_have_continued": True,
                        "completed_at": datetime.now(timezone.utc).isoformat(),
                    })
                    write_json(attempt_path, attempt)
                    raise RuntimeError(
                        "memory_answer_transport_timeout_response_unknown"
                    ) from exc
                attempt.update({
                    "status": "COMPLETED",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "response_sha256": event_hash(answer_response),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                })
                write_json(attempt_path, attempt)
                attempts.append(attempt_path)
            answer_call = {
                "schema": "embry.memory.answer_call_receipt.v1",
                "request": answer_request,
                "listener_evidence": listener_evidence,
                "request_sha256": event_hash(answer_request),
                "response": answer_response,
                "response_sha256": event_hash(answer_response),
                "source_event": {
                    key: source[key]
                    for key in (
                        "event_id",
                        "sequence",
                        "session_id",
                        "turn_id",
                        "type",
                    )
                },
                "transport": {
                    "recovery_mode": (
                        "explicit_second_provider_execution"
                        if len(attempts) > 1
                        else "first_execution"
                    ),
                    "idempotent_recovery_available": False,
                    "retried_provider_call": len(attempts) > 1,
                    "provider_execution_count": len(attempts),
                    "prior_transport_timeout_response_unknown": len(attempts) > 1,
                    "attempt_receipts": [file_locator(path) for path in attempts],
                    "suite_ready": False,
                },
            }
            if not answer_path.exists():
                write_json(answer_path, answer_call)
            answer_event = append_derived(
                journal,
                source,
                "memory.answer_resolved",
                intent_event["event_id"],
                {
                    "response_path": str(answer_path),
                    "response_sha256": sha256_path(answer_path),
                    "source_contract": contract_name,
                },
            )

        receipts = {
            "source_event_claim": {
                "path": str(claim_path),
                "sha256": sha256_path(claim_path),
            },
            "speaker_resolution": {
                "path": str(speaker_path),
                "sha256": sha256_path(speaker_path),
            },
            "memory_intent": {
                "path": str(intent_path),
                "sha256": sha256_path(intent_path),
            },
            "memory_answer": {
                "path": str(answer_path),
                "sha256": sha256_path(answer_path),
            },
        }
        source_contract_lineage = {
            "name": contract_name,
            "source_identity": source_identity,
            "voice_persona": contract.get("voice_persona"),
            "source_mode": args.source_mode,
            "fresh_physical_human_speech": fresh_physical_human_speech,
            "speaker_identity_proven": bool(contract["speaker_identity_proven"]),
            "allow_personal_memory": personal_memory_allowed,
            "memory_source_policy": (
                contract.get("memory_source_policy")
                or "event_specific_physical_identity_personal_memory"
            ),
            "release_readiness_authority": False,
            "suite_ready": False,
            "receipt_path": str(contract_path),
            "receipt_sha256": sha256_path(contract_path),
        }
        lineage = {
            "source_event": {
                key: source[key]
                for key in (
                    "event_id",
                    "sequence",
                    "session_id",
                    "turn_id",
                    "type",
                    "causation_id",
                    "correlation_id",
                    "receipt_hash",
                )
            },
            "source_evidence_event": {
                key: source_evidence[key]
                for key in (
                    "event_id",
                    "session_id",
                    "turn_id",
                    "type",
                    "causation_id",
                    "receipt_hash",
                )
            },
            "journal": {
                "service_url": args.journal_url,
                "session_journal_sha256_at_claim": "sha256:" + journal_payload["sha256"],
            },
            "source_contract": source_contract_lineage,
            "goal": {
                "goal_id": goal_packet["goal_id"],
                "goal_version": goal_packet["goal_version"],
                "goal_hash": goal_hash,
            },
        }
        if contract_name == "physical_horus_identity":
            lineage["speaker_profile_qualification"] = source_contract_lineage

        packet = {
            "schema": "embry.voice.journal_memory_tau_input.v1",
            "turn_text": turn_text,
            "lineage": lineage,
            "receipts": receipts,
        }
        packet_path = out / "input-packet.json"
        write_json(packet_path, packet)

        command_spec = (
            LANE
            / "command-specs/embry-memory-tau/tau-dispatch-command.json"
        )
        required_evidence = [
            "source_event_claim_receipt",
            "memory.speaker_resolution.v1",
            "embry.memory.intent_call_receipt.v1",
            "embry.memory.answer_call_receipt.v1",
            "tau.turn_plan.v1",
            "persistent_subagent_receipt",
            "embry.voice.journal_memory_tau_tick_receipt.v1",
        ]
        dag = {
            "schema": "tau.dag_contract.v1",
            "dag_id": "embry-journal-memory-tau-live",
            "goal": lineage["goal"],
            "target": {
                "repo": "grahama1970/agent-skills",
                "target": (
                    "skills/embry-voice-control/proofs/tau/"
                    "embry-journal-memory-tau-live"
                ),
                "allowed_paths": [
                    "skills/embry-voice-control/proofs/tau/"
                    "embry-journal-memory-tau-live/**"
                ],
            },
            "context": {
                "summary": (
                    "One live listener event, explicit source contract, "
                    "Memory-first routing, then one bounded Tau tick."
                ),
                "input_packet": {
                    "path": str(packet_path),
                    "sha256": sha256_path(packet_path),
                },
                "source_event_claim": {
                    **receipts["source_event_claim"],
                    **{
                        key: source[key]
                        for key in (
                            "event_id",
                            "sequence",
                            "session_id",
                            "turn_id",
                            "type",
                        )
                    },
                },
                "does_not_require_surface_reachability": True,
            },
            "entry_node": "embry-memory-tau",
            "terminal_nodes": ["human"],
            "limits": {
                "resume": False,
                "default_timeout_seconds": 120,
                "max_total_attempts": 1,
            },
            "nodes": [
                {
                    "id": "embry-memory-tau",
                    "agent": "embry-chatterbox-voice",
                    "executor": "local",
                    "max_attempts": 1,
                    "command_spec": str(command_spec),
                    "required_evidence": required_evidence,
                    "persistent_subagent": {
                        "schema": "tau.persistent_subagent.v1",
                        "surface_id": "embry-voice",
                        "surface_url": "http://localhost:3002/#embry-voice",
                        "session_mode": "persistent",
                        "tau_control": "bounded_receipt_gated_ticks",
                        "dag_parameter": "embry_voice_surface",
                        "required_receipts": [
                            "embry.voice.journal_memory_tau_tick_receipt.v1"
                        ],
                        "unbounded_autonomy_allowed": False,
                        "memory_write_requires_receipt": True,
                    },
                },
                {"id": "human", "agent": "human", "executor": "human"},
            ],
            "edges": [
                {
                    "from": "embry-memory-tau",
                    "to": "human",
                    "condition": "one_memory_grounded_tick_completed_or_blocked",
                }
            ],
            "required_evidence": required_evidence,
            "fail_closed_on": [
                "goal_hash_mismatch",
                "target_changed",
                "missing_required_evidence",
                "max_attempts_exceeded",
                "malformed_handoff",
            ],
        }
        dag_path = out / "dag-contract.json"
        write_json(dag_path, dag)
        tau_run = out / "tau-run"
        completed = subprocess.run(
            [
                "uv",
                "run",
                "tau",
                "dag-run",
                str(dag_path),
                "--receipt-dir",
                str(tau_run),
                "--no-resume",
            ],
            cwd=args.tau_repo,
            text=True,
            capture_output=True,
            timeout=180,
            check=False,
        )
        (out / "tau.stdout.log").write_text(completed.stdout, encoding="utf-8")
        (out / "tau.stderr.log").write_text(completed.stderr, encoding="utf-8")
        dag_receipt_path = tau_run / "dag-receipt.json"
        if completed.returncode != 0 or not dag_receipt_path.is_file():
            raise RuntimeError("tau_dag_failed")
        dag_receipt = json.loads(dag_receipt_path.read_text(encoding="utf-8"))
        if dag_receipt.get("status") != "PASS":
            raise RuntimeError("tau_dag_not_pass")
        step_path = tau_run / "command-loop/command-loop-step-001.receipt.json"
        step = json.loads(step_path.read_text(encoding="utf-8"))
        handoff = json.loads(step["command_results"][0]["stdout"])
        handoff_source = handoff["context"]["source_event"]
        for key in (
            "event_id",
            "sequence",
            "session_id",
            "turn_id",
            "type",
            "receipt_hash",
        ):
            if handoff_source.get(key) != lineage["source_event"].get(key):
                raise ValueError("tau_handoff_source_event_mismatch")
        tick = handoff["context"]["tau_tick"]
        plan_locator = handoff["context"]["tau_turn_plan"]
        plan_path = Path(plan_locator["path"])
        if sha256_path(plan_path) != plan_locator["sha256"]:
            raise ValueError("tau_turn_plan_hash_mismatch")
        turn_plan = json.loads(plan_path.read_text(encoding="utf-8"))
        if (
            turn_plan.get("session_id"),
            turn_plan.get("turn_id"),
            turn_plan.get("source_event_id"),
        ) != (
            source["session_id"],
            source["turn_id"],
            source["event_id"],
        ):
            raise ValueError("tau_turn_plan_lineage_mismatch")
        if turn_plan.get("source_contract", {}).get("name") != contract_name:
            raise ValueError("tau_turn_plan_source_contract_mismatch")
        if turn_plan.get("suite_ready") is not False:
            raise ValueError("tau_turn_plan_suite_ready_invalid")
        if turn_plan.get("tts_render_text_sha256") != hashlib.sha256(
            str(turn_plan.get("tts_render_text", "")).encode()
        ).hexdigest():
            raise ValueError("tau_turn_plan_text_hash_mismatch")

        plan_event = append_derived(
            journal,
            source,
            "tau.turn_plan.completed",
            answer_event["event_id"],
            {
                "turn_plan_path": str(plan_path),
                "turn_plan_sha256": plan_locator["sha256"],
                "tts_render_text_sha256": turn_plan["tts_render_text_sha256"],
                "source_contract": contract_name,
                "suite_ready": False,
            },
        )
        tau_event = append_derived(
            journal,
            source,
            "tau.persistent_tick.completed",
            plan_event["event_id"],
            {
                "dag_receipt_sha256": sha256_path(dag_receipt_path),
                "agent_handoff_sha256": event_hash(handoff),
                "tick_receipt_sha256": tick["receipt_sha256"],
                "source_contract": contract_name,
                "suite_ready": False,
            },
        )
        post(
            journal,
            "/v1/listener/events/ack",
            {
                "consumer_name": args.consumer_name,
                "event_id": source["event_id"],
            },
        )
        duplicate = journal.post(
            "/v1/listener/events/claim-one",
            json={
                "consumer_name": args.consumer_name,
                "event_id": args.event_id,
                "expected_session_id": args.expected_session_id,
                "expected_turn_id": args.expected_turn_id,
                "expected_sequence": args.expected_sequence,
                "expected_type": "listener.final_transcript",
                "lease_seconds": args.lease_seconds,
            },
        )
        duplicate_blocked = (
            duplicate.status_code == 409
            and duplicate.json().get("detail") == "event_already_acked"
        )

    receipt = {
        "schema": "embry.voice.journal_memory_tau_proof_receipt.v2",
        "status": "PASS" if duplicate_blocked else "FAIL",
        "ok": duplicate_blocked,
        "live": True,
        "mocked": False,
        "lineage": lineage,
        "source_contract": source_contract_lineage,
        "suite_ready": False,
        "release_readiness_authority": False,
        "journal_events": {
            "listener_final": source,
            "source_evidence": source_evidence,
            "memory_source_resolution": memory_source_event,
            "memory_intent": intent_event,
            "memory_answer": answer_event,
            "tau_turn_plan": plan_event,
            "tau_tick_completed": tau_event,
        },
        "memory": {
            "source_resolution": speaker_response,
            "source_policy": (
                "event_specific_physical_identity_personal_memory"
                if contract_name == "physical_horus_identity"
                else "qualified_synthetic_source_non_personal_memory"
            ),
            "source_resolution_path": str(speaker_path),
            "source_resolution_sha256": sha256_path(speaker_path),
            "intent_response_path": str(intent_path),
            "intent_response_sha256": sha256_path(intent_path),
            "answer_response_path": str(answer_path),
            "answer_response_sha256": sha256_path(answer_path),
            "allow_personal_memory": personal_memory_allowed,
        },
        "tau": {
            "goal_hash": goal_hash,
            "dag_contract_path": str(dag_path),
            "dag_contract_sha256": sha256_path(dag_path),
            "dag_receipt_path": str(dag_receipt_path),
            "dag_receipt_sha256": sha256_path(dag_receipt_path),
            "agent_handoff_sha256": event_hash(handoff),
            "turn_plan_path": str(plan_path),
            "turn_plan_sha256": plan_locator["sha256"],
            "turn_plan": turn_plan,
            "tick_count": 1,
        },
        "ack": {
            "consumer_name": args.consumer_name,
            "event_id": source["event_id"],
            "acked": True,
        },
        "duplicate_probe": {
            "claim_rejected_as_already_acked": duplicate_blocked,
            "memory_call_count": 0,
            "tau_tick_count": 0,
        },
        "source_mode": args.source_mode,
        "fresh_physical_human_speech": fresh_physical_human_speech,
        "speaker_identity_proven": bool(contract["speaker_identity_proven"]),
        "forbidden_activity": {
            "global_latest_json_reads": [],
            "chatterbox_calls": [],
            "browser_calls": [],
            "typed_transcript_used": False,
            "source_wav_read_by_controller": False,
            "synthetic_audio_relabelled_as_physical": False,
        },
        "failed_gates": [] if duplicate_blocked else [
            "duplicate_source_event_execution"
        ],
    }
    write_json(out / "receipt.json", receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(out / "receipt.json")}))
    return 0 if receipt["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
