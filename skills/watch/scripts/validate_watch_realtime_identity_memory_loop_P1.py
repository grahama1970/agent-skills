#!/usr/bin/env python3
"""Validate Watch realtime identity memory loop P1 fixtures.

This harness intentionally uses only the Python standard library so it can run in
minimal repo environments. It validates the fail-closed invariants that matter
for the architecture slice; it is not a replacement for full JSON Schema tests.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

FIXTURE_REL = Path("skills/watch/tests/fixtures/realtime_identity_memory_loop_P1")

VECTOR_FIELD_NAMES = {"vector", "embedding", "embeddings", "dense_vector"}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def assert_no_raw_vectors(value: Any, path: str = "$.") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = key.lower()
            assert lowered not in VECTOR_FIELD_NAMES, f"raw vector field {path}{key} is forbidden in Arango docs"
            assert_no_raw_vectors(child, f"{path}{key}.")
    elif isinstance(value, list):
        # Lists of ids are fine. Numeric vector-like lists are not allowed in Arango fixtures.
        if value and all(isinstance(item, (int, float)) for item in value):
            raise AssertionError(f"numeric vector-like list is forbidden at {path}")
        for idx, child in enumerate(value):
            assert_no_raw_vectors(child, f"{path}[{idx}].")


def validate(root: Path) -> None:
    fixtures = root / FIXTURE_REL
    assert fixtures.exists(), f"missing fixture directory: {fixtures}"

    movie_plan = load_json(fixtures / "movie_asset_reference_plan.json")
    assert movie_plan["schema"] == "watch.asset_reference_hydration_plan.v1"
    assert movie_plan["asset_type"] == "movie"
    assert movie_plan["reference_source_policy"] == "MOVIE_DOMAIN_AUTO_DISCOVERY"
    assert movie_plan["public_search_allowed"] is True
    assert movie_plan["identity_promotion_allowed"] is False
    assert movie_plan["approved_reference_count"] == 0
    discovery_api = movie_plan["candidate_discovery_api"]
    assert discovery_api["provider"] == "brave_image_search_api"
    assert discovery_api["endpoint"] == "https://api.search.brave.com/res/v1/images/search"
    assert discovery_api["result_count_target"] <= discovery_api["result_count_max"]
    assert discovery_api["candidate_only"] is True
    assert discovery_api["approval_required"] is True
    assert {"image_url", "thumbnail_url", "source_page_url"} <= set(discovery_api["required_result_fields"])
    candidate_queries = movie_plan.get("candidate_reference_queries", [])
    assert len(candidate_queries) >= 5
    assert all(query["provider"] == "brave_images" for query in candidate_queries)
    assert all(query["target_entity_id"] == "character:bad_santa:willie" for query in candidate_queries)
    assert all(query["candidate_only"] is True for query in candidate_queries)
    assert all(query["approval_required"] is True for query in candidate_queries)
    assert all(query["identity_promotion_allowed"] is False for query in candidate_queries)
    assert any("source=images" in query["url"] for query in candidate_queries)
    assert any("-group" in query["query"] and "-cast" in query["query"] for query in candidate_queries)
    assert any("site:gettyimages.com" in query["query"] for query in candidate_queries)

    drone_plan = load_json(fixtures / "drone_missing_reference_manifest_fail_closed.json")
    assert drone_plan["asset_type"] == "drone"
    assert drone_plan["reference_source_policy"] == "SOURCE_MANIFEST_REQUIRED"
    assert drone_plan["public_search_allowed"] is False
    assert drone_plan["identity_promotion_allowed"] is False
    assert drone_plan["failure_code"] == "SOURCE_REFERENCE_MANIFEST_REQUIRED"

    verifier_profile = load_json(fixtures / "identity_verifier_profile.P1a.json")
    assert verifier_profile["schema"] == "watch.identity_verifier_profile.v1a"
    assert verifier_profile["detector"]["name"] == "ultralytics_yolo"
    assert verifier_profile["tracker"]["name"] == "bytetrack"
    assert verifier_profile["verification_cadence_fps"] <= 5
    assert verifier_profile["reference_gate"]["min_approved_images_per_entity"] >= 3
    assert verifier_profile["reference_gate"]["target_approved_images_per_entity"] >= 6
    assert verifier_profile["reference_gate"]["promotion_allowed_without_approved_refs"] is False
    verifier_lanes = {lane["lane"] for lane in verifier_profile["verifier_stack"]}
    assert {"face", "body_costume_reid", "multimodal_context"} <= verifier_lanes
    thresholds = verifier_profile["thresholds"]
    assert thresholds["face_cosine_min"] > thresholds["multimodal_cosine_min"]
    assert thresholds["min_repeated_crop_agreement"] >= 2
    assert verifier_profile["promotion_policy"]["default_identity_status"] == "IDENTITY_INCONCLUSIVE"
    assert "approved_reference_package" in verifier_profile["promotion_policy"]["identity_supported_requires"]
    assert "brave_search_is_candidate_reference_only" in verifier_profile["fail_closed_boundaries"]

    track_events = load_jsonl(fixtures / "realtime_track_events.jsonl")
    assert len(track_events) >= 3
    for event in track_events:
        assert event["schema"] == "watch.realtime_track_event.v1"
        assert event["detector"]["name"] == "ultralytics_yolo"
        assert event["tracker"]["name"] == "bytetrack"
        assert event["identity_status"] == "OBSERVATION_ONLY"
        assert event["bbox"]["normalized"] is True

    overlay = load_json(fixtures / "ui_realtime_overlay_event.inconclusive.json")
    assert overlay["schema"] == "watch.ui_realtime_overlay_event.v1"
    assert overlay["identity_status"] in {"OBSERVATION_ONLY", "IDENTITY_CANDIDATE", "IDENTITY_INCONCLUSIVE"}
    assert overlay["identity_status"] != "IDENTITY_SUPPORTED"
    assert overlay["track_id"]
    assert overlay["source_event_ref"].startswith("jsonl://")
    assert overlay["stale_after_ms"] > 0

    identity = load_json(fixtures / "identity_verification.inconclusive.json")
    assert identity["schema"] == "watch.identity_verification_result.v1"
    assert identity["approved_reference_count"] == 0
    assert identity["identity_status"] == "IDENTITY_INCONCLUSIVE"
    assert identity["promotion_allowed"] is False
    assert "DOMAIN_PRIOR_ONLY" in identity["failure_codes"]

    trace = load_json(fixtures / "trace_observation.memory_planned.json")
    assert trace["schema"] == "watch.trace_observation.v1"
    assert trace["memory_write_status"] == "PLANNED"
    assert trace["qdrant_point_ids"]
    assert trace["row_text_receipt_ref"]

    arango_doc = load_json(fixtures / "arango_metadata_doc.no_vectors.json")
    assert arango_doc["vector_storage_policy"] == "NO_RAW_VECTORS_IN_ARANGO"
    assert arango_doc["qdrant_point_ids"]
    assert_no_raw_vectors(arango_doc)

    receipt = load_json(fixtures / "memory_write_receipt.planned.json")
    assert receipt["schema"] == "watch.memory_write_receipt.v1"
    assert receipt["status"] == "PLANNED_ONLY"
    assert receipt["raw_vectors_in_arango"] is False

    recall = load_json(fixtures / "recall_receipt.verified.example.json")
    assert recall["schema"] == "watch.recall_receipt.v1"
    assert recall["memory_recall_used"] is True
    assert recall["extracted_entities"]
    assert recall["source_refs"]

    case = load_json(fixtures / "evidence_case.anchored.example.json")
    assert case["schema"] == "watch.evidence_case.v1"
    assert case["entity_ids"], "evidence case requires entity ids"
    assert case["time_range"]["start_media_time_s"] < case["time_range"]["end_media_time_s"]
    assert case["trace_observation_ids"]
    assert case["source_refs"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="repository root")
    args = parser.parse_args()
    validate(Path(args.root))
    print("p1_contracts_ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
