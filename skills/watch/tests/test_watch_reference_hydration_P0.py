from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from watch_reference_hydration import (
    STATE_REFERENCE_EMBEDDINGS_READY,
    STATE_REFERENCE_IMAGES_PENDING_APPROVAL,
    STATE_REFERENCE_PACKAGE_MISSING,
    build_graph_vector_persistence_plan,
    build_live_tracking_memory_window_plan,
    build_memory_trace_plan,
    build_reference_hydration_plan,
    load_json,
    load_jsonl,
    validate_hydration_plan,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "reference_hydration_P0"
WATCH_ROOT = Path(__file__).resolve().parents[1]


def test_movie_candidates_do_not_promote_identity() -> None:
    asset = load_json(FIXTURES / "asset_movie_bad_santa.json")
    candidates = load_json(FIXTURES / "movie_reference_candidates_bad_santa.json")
    plan = build_reference_hydration_plan(asset, reference_candidates=candidates)
    assert plan["schema"] == "watch.reference_hydration_plan.v1"
    assert plan["state"] == STATE_REFERENCE_IMAGES_PENDING_APPROVAL
    assert plan["gates"]["can_ingest"] is True
    assert plan["gates"]["can_track"] is True
    assert plan["gates"]["can_promote_identity"] is False
    assert plan["identity_policy"]["public_search_can_prove_scene_visibility"] is False
    assert plan["counts"]["approved_reference_count"] == 0
    assert validate_hydration_plan(plan) == []


def test_non_movie_without_manifest_fails_closed() -> None:
    asset = load_json(FIXTURES / "asset_drone_stream.json")
    plan = build_reference_hydration_plan(asset)
    assert plan["state"] == STATE_REFERENCE_PACKAGE_MISSING
    assert plan["fail_closed"]["active"] is True
    assert "SOURCE_REFERENCE_MANIFEST_MISSING" in plan["fail_closed"]["reasons"]
    assert plan["gates"]["can_ingest"] is False
    assert plan["gates"]["can_track"] is False
    assert plan["gates"]["can_promote_identity"] is False
    assert validate_hydration_plan(plan, expect_fail_closed=True) == []


def test_non_movie_with_approved_manifest_can_reach_embedding_ready() -> None:
    asset = load_json(FIXTURES / "asset_drone_stream.json")
    manifest = load_json(FIXTURES / "source_reference_manifest_drone_valid.json")
    plan = build_reference_hydration_plan(asset, source_manifest=manifest)
    assert plan["state"] == STATE_REFERENCE_EMBEDDINGS_READY
    assert plan["fail_closed"]["active"] is False
    assert plan["gates"]["can_ingest"] is True
    assert plan["gates"]["can_track"] is True
    assert plan["gates"]["can_promote_identity"] is True
    assert plan["counts"]["approved_reference_count"] == 1
    assert validate_hydration_plan(plan) == []


def test_memory_trace_plan_is_planned_not_written_and_recall_gated() -> None:
    asset = load_json(FIXTURES / "asset_movie_bad_santa.json")
    observations = load_json(FIXTURES / "track_observations_bad_santa_0248.json")["observations"]
    evidence = load_json(FIXTURES / "identity_evidence_inconclusive_domain_only.json")["identity_evidence"]
    plan = build_memory_trace_plan(asset, observations, evidence)
    assert plan["schema"] == "watch.memory_trace_write_plan.v1"
    assert plan["write_status"] == "PLANNED_NOT_WRITTEN"
    assert plan["recall_proof_required"] is True
    assert plan["direct_qdrant_or_arango_answer_allowed"] is False
    assert all(record["write_status"] == "PLANNED_NOT_WRITTEN" for record in plan["records"])
    identity_records = [r for r in plan["records"] if r["record_kind"] == "identity_evidence"]
    assert identity_records
    assert identity_records[0]["identity_status"] == "IDENTITY_INCONCLUSIVE"
    assert "DOMAIN_PRIOR_ONLY" in identity_records[0]["promotion_blockers"]


def test_live_tracking_events_collapse_to_recall_gated_memory_windows() -> None:
    asset = load_json(FIXTURES / "asset_movie_bad_santa.json")
    events = load_jsonl(
        WATCH_ROOT
        / "docs"
        / "architecture"
        / "generated"
        / "bad_santa_marcus_0248_yolo_bytetrack"
        / "watch_tracker_event_log.bad_santa_marcus.yolo_bytetrack.jsonl"
    )
    plan = build_live_tracking_memory_window_plan(asset, events, sample_fps=5.0)
    schema = load_json(
        WATCH_ROOT
        / "docs"
        / "architecture"
        / "schemas"
        / "watch_live_tracking_memory_window_plan.schema.json"
    )
    Draft202012Validator(schema).validate(plan)

    assert plan["schema"] == "watch.live_tracking_memory_window_plan.v1"
    assert plan["write_status"] == "PLANNED_NOT_WRITTEN"
    assert plan["event_count"] == 80
    assert plan["track_window_count"] == 10
    assert plan["memory_trace_plan"]["recall_proof_required"] is True
    assert plan["memory_trace_plan"]["direct_qdrant_or_arango_answer_allowed"] is False

    windows = plan["windows"]
    assert {window["identity_status"] for window in windows} == {"IDENTITY_INCONCLUSIVE"}
    assert all(window["event_count"] >= 1 for window in windows)

    trace_records = plan["memory_trace_plan"]["records"]
    assert trace_records
    assert all(record["write_status"] == "PLANNED_NOT_WRITTEN" for record in trace_records)
    identity_records = plan["memory_trace_plan"]["identity_evidence"]
    assert identity_records
    assert all(record["identity_status"] == "IDENTITY_INCONCLUSIVE" for record in identity_records)
    assert all("MEMORY_RECALL_NOT_VERIFIED" in record["promotion_blockers"] for record in identity_records)


def test_live_windows_shape_graph_and_vector_persistence_without_raw_vectors() -> None:
    live_window_plan = load_json(
        WATCH_ROOT
        / "docs"
        / "architecture"
        / "generated"
        / "bad_santa_marcus_0248_live_memory_window_plan"
        / "watch_live_tracking_memory_window_plan.bad_santa_marcus.json"
    )
    plan = build_graph_vector_persistence_plan(live_window_plan)
    schema = load_json(
        WATCH_ROOT
        / "docs"
        / "architecture"
        / "schemas"
        / "watch_graph_vector_persistence_plan.schema.json"
    )
    Draft202012Validator(schema).validate(plan)

    assert plan["schema"] == "watch.graph_vector_persistence_plan.v1"
    assert plan["write_status"] == "PLANNED_NOT_WRITTEN"
    assert plan["memory_recall"]["required_before_answer_claim"] is True
    assert plan["memory_recall"]["allowed_answer_path"] == "$memory recall"
    assert plan["memory_recall"]["direct_qdrant_or_arango_answer_allowed"] is False

    counts = plan["counts"]
    assert counts["track_observations"] == 10
    assert counts["identity_evidence"] == 10
    assert counts["evidence_cases"] == 10
    assert counts["qdrant_point_plans"] == 20

    arango_collections = plan["arango_plan"]["collections"]
    assert arango_collections["watch_evidence_edges"]
    assert all("qdrant_pointers" in doc for doc in arango_collections["watch_track_observations"])
    assert all(
        not any(key in doc for key in ("embedding", "embeddings", "vector", "vectors"))
        for doc in arango_collections["watch_track_observations"]
    )

    qdrant_collections = plan["qdrant_plan"]["collections"]
    point_plans = qdrant_collections["watch_track_crop_embeddings"] + qdrant_collections["watch_identity_evidence_embeddings"]
    assert point_plans
    assert all(point["embedding_status"] == "PLANNED_NOT_WRITTEN" for point in point_plans)
    assert all("point_id" in point and "payload" in point for point in point_plans)
    assert all(
        not any(key in point for key in ("embedding", "embeddings", "vector", "vectors"))
        for point in point_plans
    )
