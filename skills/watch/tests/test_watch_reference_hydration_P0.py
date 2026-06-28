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
    build_identity_reinforcement_plan,
    build_live_tracking_memory_window_plan,
    build_memory_recall_verification_plan,
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


def test_graph_vector_plan_builds_question_shaped_memory_recall_contract() -> None:
    graph_vector_plan = load_json(
        WATCH_ROOT
        / "docs"
        / "architecture"
        / "generated"
        / "bad_santa_marcus_0248_graph_vector_persistence_plan"
        / "watch_graph_vector_persistence_plan.bad_santa_marcus.json"
    )
    plan = build_memory_recall_verification_plan(graph_vector_plan)
    schema = load_json(
        WATCH_ROOT
        / "docs"
        / "architecture"
        / "schemas"
        / "watch_memory_recall_verification_plan.schema.json"
    )
    Draft202012Validator(schema).validate(plan)

    assert plan["schema"] == "watch.memory_recall_verification_plan.v1"
    assert plan["verification_status"] == "PLANNED_NOT_QUERIED"
    assert plan["proof_requirements"]["read_response_key"] == "items"
    assert plan["proof_requirements"]["forbidden_response_key_dependency"] == "results"
    assert plan["proof_requirements"]["direct_qdrant_or_arango_answer_allowed"] is False

    requests = plan["recall_requests"]
    assert {request["kind"] for request in requests} == {"entity_segments", "negative_entity_control"}
    entity_request = next(request for request in requests if request["kind"] == "entity_segments")
    assert entity_request["http"]["path"] == "/recall"
    assert "Which Watch evidence cases or movie segments contain" in entity_request["http"]["body"]["q"]
    assert "watch_evidence_cases" in entity_request["http"]["body"]["collections"]
    assert entity_request["expected_constraints"]["min_case_count"] == 10
    assert len(entity_request["expected_constraints"]["expected_case_ids"]) == 10

    negative = next(request for request in requests if request["kind"] == "negative_entity_control")
    assert "movie_domain_entities/willie_bad_santa_2003" in negative["expected_constraints"]["forbidden_entity_ids"]
    assert negative["acceptance"]["requires_no_wrong_entity_promotion"] is True


def test_identity_reinforcement_plan_keeps_brave_references_as_priors() -> None:
    reference_manifest = load_json(
        WATCH_ROOT
        / "docs"
        / "architecture"
        / "generated"
        / "bad_santa_marcus_0248_identity_references"
        / "watch_identity_reference_manifest.bad_santa_marcus.json"
    )
    graph_vector_plan = load_json(
        WATCH_ROOT
        / "docs"
        / "architecture"
        / "generated"
        / "bad_santa_marcus_0248_graph_vector_persistence_plan"
        / "watch_graph_vector_persistence_plan.bad_santa_marcus.json"
    )
    recall_plan = load_json(
        WATCH_ROOT
        / "docs"
        / "architecture"
        / "generated"
        / "bad_santa_marcus_0248_memory_recall_verification_plan"
        / "watch_memory_recall_verification_plan.bad_santa_marcus.json"
    )
    plan = build_identity_reinforcement_plan(reference_manifest, graph_vector_plan, recall_plan)
    schema = load_json(
        WATCH_ROOT
        / "docs"
        / "architecture"
        / "schemas"
        / "watch_identity_reinforcement_plan.schema.json"
    )
    Draft202012Validator(schema).validate(plan)

    assert plan["schema"] == "watch.identity_reinforcement_plan.v1"
    assert plan["status"] == "PLANNED_NOT_RUN"
    assert plan["promotion_policy"]["domain_reference_seed_can_promote_identity"] is False
    assert plan["promotion_policy"]["detector_label_can_promote_identity"] is False
    assert plan["memory_requirements"]["allowed_answer_path"] == "$memory recall"
    assert plan["memory_requirements"]["requires_items_key"] is True
    assert plan["memory_requirements"]["direct_qdrant_or_arango_answer_allowed"] is False

    counts = plan["counts"]
    assert counts["entity_plan_count"] == 1
    assert counts["approved_reference_count"] == 0
    assert counts["review_crop_count"] == 10
    assert counts["recall_request_count"] == 2
    assert counts["qdrant_point_plan_count"] == 20

    entity_plan = plan["entity_reinforcement_plans"][0]
    assert entity_plan["entity_name"] == "Marcus"
    assert entity_plan["status"] == "BLOCKED_PENDING_APPROVED_REFERENCES"
    assert "APPROVED_REFERENCE_IMAGES_MISSING" in entity_plan["promotion_blockers"]
    assert "MEMORY_RECALL_NOT_VERIFIED" in entity_plan["promotion_blockers"]

    domain_stage = next(stage for stage in plan["reinforcement_loop"] if stage["stage"] == "domain_reference_seed")
    assert domain_stage["scene_truth_allowed"] is False
    assert "movie_domain_entities/willie_bad_santa_2003" in plan["negative_controls"][0]["forbidden_entity_ids"]
