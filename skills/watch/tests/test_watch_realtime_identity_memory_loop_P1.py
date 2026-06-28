from __future__ import annotations

import json
from pathlib import Path

from skills.watch.scripts.validate_watch_realtime_identity_memory_loop_P1 import assert_no_raw_vectors, validate
from skills.watch.scripts.build_watch_candidate_reference_manifest import build_manifest

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "skills" / "watch" / "tests" / "fixtures" / "realtime_identity_memory_loop_P1"


def load_json(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def load_jsonl(name: str):
    return [json.loads(line) for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def test_p1_fixture_contracts_validate():
    validate(ROOT)


def test_movie_assets_auto_plan_reference_hydration_without_identity_promotion():
    plan = load_json("movie_asset_reference_plan.json")
    assert plan["asset_type"] == "movie"
    assert plan["reference_source_policy"] == "MOVIE_DOMAIN_AUTO_DISCOVERY"
    assert plan["public_search_allowed"] is True
    assert plan["candidate_source_refs"]
    assert plan["approved_reference_count"] == 0
    assert plan["identity_promotion_allowed"] is False


def test_search_oracle_outputs_become_candidate_references_only():
    plan = load_json("movie_asset_reference_plan.json")
    brave_context = load_json("brave_llm_context_bad_santa_willie.sample.json")
    perplexity_leads = load_json("perplexity_image_leads_bad_santa_willie.sample.json")
    manifest = build_manifest(
        plan,
        brave_llm_context=brave_context,
        perplexity_leads=perplexity_leads,
    )

    assert manifest["schema"] == "watch.reference_manifest.v1"
    assert manifest["asset_id"] == "bad_santa_2003_canary"
    assert manifest["source_type"] == "movie_domain_search"
    assert manifest["scene_truth_claimed"] is False
    assert manifest["identity_promotion_allowed"] is False
    assert manifest["approved_reference_count"] == 0
    assert manifest["embedded_reference_count"] == 0
    assert {"brave_llm_context", "perplexity_image_leads"} <= set(manifest["providers"])
    assert len(manifest["references"]) == 5
    assert all(ref["entity_id"] == "character:bad_santa:willie" for ref in manifest["references"])
    assert all(ref["candidate_only"] is True for ref in manifest["references"])
    assert all(ref["approval_required"] is True for ref in manifest["references"])
    assert all(ref["approval_status"] == "CANDIDATE" for ref in manifest["references"])
    assert all(ref["download_status"] == "NOT_DOWNLOADED" for ref in manifest["references"])
    assert all(ref["embedding_status"] == "NOT_EMBEDDED" for ref in manifest["references"])


def test_drone_without_source_manifest_fails_closed_and_disables_public_search():
    plan = load_json("drone_missing_reference_manifest_fail_closed.json")
    assert plan["asset_type"] == "drone"
    assert plan["reference_source_policy"] == "SOURCE_MANIFEST_REQUIRED"
    assert plan["public_search_allowed"] is False
    assert plan["identity_promotion_allowed"] is False
    assert plan["failure_code"] == "SOURCE_REFERENCE_MANIFEST_REQUIRED"


def test_p1a_identity_verifier_stack_is_explicit_and_fail_closed():
    profile = load_json("identity_verifier_profile.P1a.json")
    assert profile["schema"] == "watch.identity_verifier_profile.v1a"
    assert profile["detector"]["name"] == "ultralytics_yolo"
    assert profile["tracker"]["name"] == "bytetrack"
    assert profile["verification_cadence_fps"] == 5
    assert profile["reference_gate"]["min_approved_images_per_entity"] == 3
    assert profile["reference_gate"]["target_approved_images_per_entity"] == 6
    assert profile["reference_gate"]["promotion_allowed_without_approved_refs"] is False
    lanes = {lane["lane"]: lane["default_model"] for lane in profile["verifier_stack"]}
    assert lanes["face"] == "insightface_arcface_compatible"
    assert lanes["body_costume_reid"] == "osnet_or_fastreid_compatible"
    assert lanes["multimodal_context"] == "jina_clip_or_siglip_compatible"
    assert profile["promotion_policy"]["default_identity_status"] == "IDENTITY_INCONCLUSIVE"
    assert "detector_labels_are_observations_only" in profile["fail_closed_boundaries"]
    assert "brave_search_is_candidate_reference_only" in profile["fail_closed_boundaries"]


def test_yolo_bytetrack_events_are_observations_not_identity():
    events = load_jsonl("realtime_track_events.jsonl")
    assert len(events) >= 3
    assert all(event["detector"]["name"] == "ultralytics_yolo" for event in events)
    assert all(event["tracker"]["name"] == "bytetrack" for event in events)
    assert all(event["identity_status"] == "OBSERVATION_ONLY" for event in events)


def test_identity_verification_stays_inconclusive_without_approved_references():
    result = load_json("identity_verification.inconclusive.json")
    assert result["approved_reference_count"] == 0
    assert result["identity_status"] == "IDENTITY_INCONCLUSIVE"
    assert result["promotion_allowed"] is False
    assert "DOMAIN_PRIOR_ONLY" in result["failure_codes"]


def test_arango_fixture_uses_qdrant_pointers_not_raw_vectors():
    doc = load_json("arango_metadata_doc.no_vectors.json")
    assert doc["qdrant_point_ids"]
    assert_no_raw_vectors(doc)


def test_overlay_event_can_render_without_claiming_supported_identity():
    overlay = load_json("ui_realtime_overlay_event.inconclusive.json")
    assert overlay["schema"] == "watch.ui_realtime_overlay_event.v1"
    assert overlay["track_id"] == "track_person_0248_0007"
    assert overlay["bbox"]["normalized"] is True
    assert overlay["identity_status"] == "IDENTITY_INCONCLUSIVE"
    assert overlay["identity_status"] != "IDENTITY_SUPPORTED"
    assert "not_live_identity_proof" in overlay["proof_scope"]
