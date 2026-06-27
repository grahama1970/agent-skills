from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from watch_reference_hydration import (
    STATE_REFERENCE_EMBEDDINGS_READY,
    STATE_REFERENCE_IMAGES_PENDING_APPROVAL,
    STATE_REFERENCE_PACKAGE_MISSING,
    build_memory_trace_plan,
    build_reference_hydration_plan,
    load_json,
    validate_hydration_plan,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "reference_hydration_P0"


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
