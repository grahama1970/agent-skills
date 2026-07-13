#!/usr/bin/env python3
"""Validate the F-36 Watch recorded visual evidence contract canary.

This script is intentionally narrow: it validates the schema bundle and the
high-risk semantics from the WebGPT architecture review. It is not a Watch UI
test and it does not exercise live Memory/Qdrant.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "f36_watch_contracts.v1.schema.json"
POSITIVE_PATH = ROOT / "fixtures" / "f36_recorded_visual_canary.positive.json"
NEGATIVE_DIR = ROOT / "fixtures" / "negative"


class ContractError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def pointer_parts(pointer: str) -> list[str]:
    if not pointer.startswith("/"):
        raise ValueError(f"JSON pointer must start with /: {pointer}")
    return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]


def apply_mutation(document: Any, mutation: dict[str, Any]) -> None:
    parts = pointer_parts(mutation["path"])
    current = document
    for part in parts[:-1]:
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    last = parts[-1]
    if mutation.get("delete"):
        if isinstance(current, list):
            del current[int(last)]
        else:
            del current[last]
        return
    if isinstance(current, list):
        current[int(last)] = mutation["value"]
    else:
        current[last] = mutation["value"]


def materialize_negative(path: Path, base: dict[str, Any]) -> tuple[dict[str, Any], str]:
    spec = load_json(path)
    if spec.get("extends") != "../f36_recorded_visual_canary.positive.json":
        raise ContractError("fixture_extends_unsupported", f"{path} must extend the positive canary")
    document = copy.deepcopy(base)
    for mutation in spec.get("mutations", []):
        apply_mutation(document, mutation)
    expected_error = spec.get("expected_error")
    if not expected_error:
        raise ContractError("fixture_missing_expected_error", f"{path} has no expected_error")
    return document, expected_error


def validate_schema(document: dict[str, Any], validator: Draft202012Validator) -> None:
    errors = sorted(validator.iter_errors(document), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        path = "/" + "/".join(str(part) for part in first.path)
        raise ContractError("schema_validation_failed", f"{path}: {first.message}")


def event_sort_key(event: dict[str, Any]) -> tuple[float, int]:
    return (float(event["effective_at"]), int(event["sequence_number"]))


def validate_semantics(document: dict[str, Any]) -> None:
    semantic_manifest = document["semantic_package_manifest"]
    sparta_link = document["sparta_evidence_case_link"]
    bundle = document["visual_evidence_bundle"]

    if sparta_link["semantic_package_hash"] != semantic_manifest["package_sha256"]:
        raise ContractError(
            "semantic_package_hash_mismatch",
            "SPARTA link must pin the same semantic package hash as the fixture manifest",
        )

    if sparta_link["evidence_bundle_hash"] != bundle["manifest_hash"]:
        raise ContractError(
            "evidence_bundle_hash_mismatch",
            "SPARTA link must reference the exact visual evidence bundle hash",
        )

    if document.get("disposition", {}).get("producer") == "watch":
        raise ContractError("watch_authored_disposition", "Watch may not issue f36.disposition.v1 records")

    crops_by_id = {crop["crop_id"]: crop for crop in document["crop_artifacts"]}
    decisions_by_id = {decision["decision_id"]: decision for decision in document["label_decisions"]}

    for decision in document["label_decisions"]:
        crop = crops_by_id.get(decision["crop_id"])
        if not crop:
            raise ContractError("decision_crop_missing", f"{decision['decision_id']} references missing crop")
        if decision["decision_type"] in {"REJECT_LABEL", "REJECT_CROP", "BAD_GEOMETRY", "AMBIGUOUS"}:
            if decision["positive_memory_ingest_allowed"]:
                raise ContractError(
                    "rejected_decision_positive_memory",
                    f"{decision['decision_id']} allows positive memory ingest",
                )

    for receipt in document["memory_ingest_receipts"]:
        crop = crops_by_id.get(receipt["crop_id"])
        decision = decisions_by_id.get(receipt["decision_id"])
        if not crop or not decision:
            raise ContractError("memory_receipt_reference_missing", f"{receipt['receipt_id']} references missing input")
        positive = bool(receipt["eligibility"]["positive_allowed"])
        if crop["quarantine"] or crop["review_state"] in {"REJECTED", "AMBIGUOUS", "BAD_GEOMETRY"}:
            if positive or receipt["status"] == "STORED":
                raise ContractError(
                    "rejected_or_quarantined_crop_positive_memory",
                    f"{receipt['receipt_id']} would poison positive recall",
                )
        if positive != bool(decision["positive_memory_ingest_allowed"]):
            raise ContractError(
                "memory_receipt_decision_mismatch",
                f"{receipt['receipt_id']} disagrees with {decision['decision_id']}",
            )

    for suggestion in document["suggestion_results"]:
        if suggestion["auto_apply_allowed"]:
            raise ContractError("suggestion_auto_apply", f"{suggestion['suggestion_id']} may mutate state")
        if suggestion["display_state"] != "TENTATIVE":
            raise ContractError("suggestion_not_tentative", f"{suggestion['suggestion_id']} is not tentative")

    active_subject_by_sequence: dict[str, str | None] = {}
    stopped_sequences: set[str] = set()
    for event in sorted(document["events"], key=event_sort_key):
        payload = event["payload"]
        if payload["schema"] != "watch.sequence_event.v1":
            continue
        sequence_id = payload["sequence_id"]
        event_type = payload["event_type"]
        subject_id = payload.get("subject_id")

        if sequence_id in stopped_sequences and event_type not in {"ASSIGN", "REASSIGN_START", "START", "END", "SUPERSEDE"}:
            if subject_id:
                raise ContractError(
                    "assignment_crosses_unassign_stop",
                    f"{event['event_id']} carries {subject_id} after UNASSIGN_STOP",
                )

        if event_type == "UNASSIGN_STOP":
            active_subject_by_sequence[sequence_id] = None
            stopped_sequences.add(sequence_id)
            continue
        if event_type in {"ASSIGN", "REASSIGN_START"}:
            if not subject_id:
                raise ContractError("assignment_missing_subject", f"{event['event_id']} has no subject")
            active_subject_by_sequence[sequence_id] = subject_id
            stopped_sequences.discard(sequence_id)


def validate_document(document: dict[str, Any], validator: Draft202012Validator) -> None:
    validate_schema(document, validator)
    validate_semantics(document)


def main() -> int:
    schema = load_json(SCHEMA_PATH)
    validator = Draft202012Validator(schema)
    positive = load_json(POSITIVE_PATH)

    results: list[dict[str, str]] = []
    try:
        validate_document(positive, validator)
        results.append({"fixture": POSITIVE_PATH.name, "result": "PASS", "mocked": "no", "live": "no"})
    except ContractError as error:
        results.append({"fixture": POSITIVE_PATH.name, "result": "FAIL", "error": error.code, "detail": error.detail})

    for path in sorted(NEGATIVE_DIR.glob("*.json")):
        document, expected = materialize_negative(path, positive)
        try:
            validate_document(document, validator)
        except ContractError as error:
            if error.code == expected:
                results.append({"fixture": path.name, "result": "PASS", "caught": error.code})
            else:
                results.append(
                    {
                        "fixture": path.name,
                        "result": "FAIL",
                        "expected": expected,
                        "caught": error.code,
                        "detail": error.detail,
                    }
                )
        else:
            results.append({"fixture": path.name, "result": "FAIL", "expected": expected, "caught": "none"})

    failed = [result for result in results if result["result"] != "PASS"]
    print(json.dumps({"schema": "f36.watch.contract_validation.v1", "results": results, "failed": len(failed)}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
