"""Project one adaptive campaign journal into a public-safe UX fixture."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from jsonschema import validate  # type: ignore[import-untyped]

FORBIDDEN_PATH_MARKERS = ("/tmp/", "tau-live", "reviewed/", "arena/private", "scillm")


def build_normalized_adaptive_fixture(
    *, campaign_root: Path, source_index_path: Path, fixture_id: str
) -> dict[str, Any]:
    index = _read_json(source_index_path)
    if index.get("campaign_root_id") != campaign_root.name:
        raise ValueError("source index campaign identity mismatch")
    events = [
        json.loads(line)
        for line in (campaign_root / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    if not events or any(
        event.get("run_id") != index.get("run_id") for event in events
    ):
        raise ValueError("journal is empty or contains cross-run events")
    if [event["seq"] for event in events] != list(range(1, len(events) + 1)):
        raise ValueError("journal sequence is not contiguous")
    elapsed = [event["timing"]["elapsed_seconds"] for event in events]
    if elapsed != sorted(elapsed):
        raise ValueError("journal elapsed time decreases")
    public_events = [
        {
            "seq": event["seq"],
            "event_id": event["event_id"],
            "elapsed_seconds": event["timing"]["elapsed_seconds"],
            "event_type": event["event_type"],
            "generation": event.get("generation"),
            "team": event.get("team"),
            "lane_id": event.get("lane_id"),
            "receipt_ref": event["source_receipt"],
            "payload": event.get("payload", {}),
        }
        for event in events
    ]
    fixture = {
        "schema": "battle.normalized_adaptive_lineage_fixture.v1",
        "fixture_id": fixture_id,
        "battle_id": index["battle_id"],
        "run_id": index["run_id"],
        "proof_mode": "receipt_backed_fixture",
        "live_source": "adaptive_red_blue_lineage_v2",
        "causal_continuity_proven": True,
        "campaign": {
            "campaign_clock_id": events[0]["campaign_clock_id"],
            "elapsed_seconds": elapsed[-1],
            "generation_count": 2,
            "teams": ["red", "blue"],
        },
        "events": public_events,
        "receipt_refs": index["public_receipts"],
        "selection": index["selection"],
        "memory_evaluation": index["memory_evaluation"],
        "claim_boundary": {
            "may_claim": [
                "two receipt-continuous Red/Blue generations",
                "parent-authored spawn requests",
                "semantic genome mutation",
                "deterministic selection",
                "memory-policy evaluation",
            ],
            "must_not_claim": [
                "Judge exploit success unless Judge says RED_SUCCESS",
                "child improvement unless selection proves it",
                "durable memory write or recall",
                "population-scale or production readiness",
            ],
        },
        "provenance": {
            "raw_paths_redacted": True,
            "source_run_count": 1,
            "source_proof_id": campaign_root.name,
        },
    }
    serialized = json.dumps(fixture, sort_keys=True)
    if any(marker in serialized for marker in FORBIDDEN_PATH_MARKERS):
        raise ValueError("normalized fixture exposes a raw runtime path")
    return fixture


def write_fixture_copies(
    *, fixture: dict[str, Any], local_path: Path, public_path: Path
) -> dict[str, Any]:
    schema_path = (
        Path(__file__).resolve().parents[2]
        / "schemas"
        / "battle.normalized_adaptive_lineage_fixture.v1.schema.json"
    )
    validate(instance=fixture, schema=_read_json(schema_path))
    payload = json.dumps(fixture, indent=2, sort_keys=True) + "\n"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(payload, encoding="utf-8")
    public_path.write_text(payload, encoding="utf-8")
    digest = hashlib.sha256(payload.encode()).hexdigest()
    return {
        "schema": "battle.normalized_adaptive_lineage_validation.v1",
        "status": "PASS",
        "local_public_byte_identical": local_path.read_bytes()
        == public_path.read_bytes(),
        "fixture_sha256": digest,
    }


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value
