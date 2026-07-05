from __future__ import annotations

import json
from pathlib import Path

from skills.watch.scripts.build_watch_candidate_reference_manifest import build_manifest
from skills.watch.scripts.build_watch_reference_receipt_chain import (
    build_crop_reference_similarity_plan,
    build_download_review_approval_plan,
    build_reference_embedding_receipt_plan,
    assert_no_raw_vectors as assert_no_receipt_vectors,
)
from skills.watch.scripts.validate_watch_realtime_identity_memory_loop_P1 import assert_no_raw_vectors, validate
from skills.watch.scripts.run_realtime_identity_memory_loop import (
    approval_receipt_allows_embedding,
    attach_reference_approval,
    approved_reference_records,
    reference_approval_by_id,
)
from skills.watch.scripts.build_watch_identity_gate_receipt import (
    build_identity_gate_receipt,
    build_qdrant_recall_identity_stop_receipt,
)
from skills.watch.scripts.build_watch_negative_control_receipt import build_negative_control_receipt

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "skills" / "watch" / "tests" / "fixtures" / "realtime_identity_memory_loop_P1"
CANARY_REFERENCE_MANIFEST = (
    ROOT
    / "skills"
    / "watch"
    / "docs"
    / "architecture"
    / "generated"
    / "bad_santa_marcus_0248_approved_reference_canary"
    / "watch_approved_reference_manifest.bad_santa_marcus.canary.json"
)
CANARY_APPROVAL_RECEIPT = (
    ROOT
    / "skills"
    / "watch"
    / "docs"
    / "architecture"
    / "generated"
    / "bad_santa_marcus_0248_reference_download_review_approval_receipt"
    / "watch_reference_download_review_approval_receipt.bad_santa_marcus_canary.json"
)
LIVE_APPROVAL_LINKED_RECEIPT = (
    ROOT
    / "skills"
    / "watch"
    / "docs"
    / "architecture"
    / "generated"
    / "watch_realtime_identity_memory_loop_live_approval_linked_20260628T1315Z"
    / "watch_realtime_identity_memory_loop_live_receipt.json"
)
LIVE_YOLO_TRACK_QDRANT_EVAL_RECEIPT = (
    ROOT
    / "skills"
    / "watch"
    / "docs"
    / "architecture"
    / "generated"
    / "watch_identity_qdrant_marcus_eval"
    / "20260704T172759115162Z_yolo_track_2_only"
    / "watch_identity_qdrant_yolo_track_2_interpolated_marcus_eval.json"
)


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


def test_candidate_references_require_download_review_approval_receipts_before_embedding():
    plan = load_json("movie_asset_reference_plan.json")
    manifest = build_manifest(
        plan,
        brave_llm_context=load_json("brave_llm_context_bad_santa_willie.sample.json"),
        perplexity_leads=load_json("perplexity_image_leads_bad_santa_willie.sample.json"),
    )
    approval_plan = build_download_review_approval_plan(manifest)

    assert approval_plan["schema"] == "watch.reference_download_review_approval_receipt_plan.v1"
    assert approval_plan["status"] == "PLANNED_NOT_RUN"
    assert approval_plan["counts"]["candidate_reference_count"] == 5
    assert approval_plan["counts"]["downloaded_reference_count"] == 0
    assert approval_plan["counts"]["approved_reference_count"] == 0
    assert approval_plan["receipt_requirements"]["download_receipts_required"] is True
    assert approval_plan["receipt_requirements"]["source_review_receipts_required"] is True
    assert approval_plan["receipt_requirements"]["approval_receipts_required"] is True
    assert approval_plan["promotion_policy"]["candidate_url_can_promote_identity"] is False
    assert approval_plan["promotion_policy"]["download_without_approval_can_promote_identity"] is False
    assert approval_plan["promotion_policy"]["scene_truth_claim_allowed"] is False
    assert all(item["download_receipt"]["status"] == "PLANNED_NOT_RUN" for item in approval_plan["reference_receipts"])
    assert all(
        item["source_review_receipt"]["status"] == "BLOCKED_PENDING_DOWNLOAD"
        for item in approval_plan["reference_receipts"]
    )
    assert all(
        item["approval_receipt"]["status"] == "BLOCKED_PENDING_SOURCE_REVIEW"
        for item in approval_plan["reference_receipts"]
    )
    assert all(item["scene_truth_claimed"] is False for item in approval_plan["reference_receipts"])
    assert all(item["identity_promotion_allowed"] is False for item in approval_plan["reference_receipts"])
    assert_no_receipt_vectors(approval_plan)


def test_reference_embedding_and_crop_similarity_receipts_are_blocked_until_real_receipts_exist():
    plan = load_json("movie_asset_reference_plan.json")
    manifest = build_manifest(
        plan,
        brave_llm_context=load_json("brave_llm_context_bad_santa_willie.sample.json"),
        perplexity_leads=load_json("perplexity_image_leads_bad_santa_willie.sample.json"),
    )
    approval_plan = build_download_review_approval_plan(manifest)
    embedding_plan = build_reference_embedding_receipt_plan(approval_plan)
    similarity_plan = build_crop_reference_similarity_plan(load_json("willie_tracking_crops.sample.json"), embedding_plan)

    assert embedding_plan["schema"] == "watch.reference_candidate_embedding_receipt_plan.v1"
    assert embedding_plan["status"] == "BLOCKED_PENDING_APPROVAL_RECEIPTS"
    assert embedding_plan["counts"]["reference_embedding_receipt_count"] == 5
    assert embedding_plan["counts"]["ready_reference_embedding_count"] == 0
    assert embedding_plan["qdrant_reference_point_plan"]["raw_vectors_in_plan"] is False
    assert all(
        point["qdrant_point_plan"]["write_status"] == "BLOCKED_PENDING_APPROVAL_RECEIPT"
        for point in embedding_plan["reference_embedding_receipts"]
    )
    assert all(point["identity_promotion_allowed"] is False for point in embedding_plan["reference_embedding_receipts"])
    assert_no_receipt_vectors(embedding_plan)

    assert similarity_plan["schema"] == "watch.crop_reference_candidate_similarity_receipt_plan.v1"
    assert similarity_plan["status"] == "BLOCKED_PENDING_EMBEDDINGS"
    assert similarity_plan["counts"]["candidate_crop_count"] == 2
    assert similarity_plan["counts"]["reference_embedding_receipt_count"] == 5
    assert similarity_plan["counts"]["planned_similarity_receipt_count"] == 10
    assert similarity_plan["counts"]["ready_similarity_receipt_count"] == 0
    assert all(
        item["similarity_receipt_status"] == "BLOCKED_PENDING_EMBEDDINGS"
        for item in similarity_plan["similarity_receipts"]
    )
    assert all(item["negative_control_required"] is True for item in similarity_plan["similarity_receipts"])
    assert all(item["text_scene_corroboration_required"] is True for item in similarity_plan["similarity_receipts"])
    assert all(item["memory_recall_required"] is True for item in similarity_plan["similarity_receipts"])
    assert all(item["identity_promotion_allowed"] is False for item in similarity_plan["similarity_receipts"])
    assert_no_receipt_vectors(similarity_plan)


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


def test_live_reference_embedding_links_approval_receipt_before_similarity():
    manifest = json.loads(CANARY_REFERENCE_MANIFEST.read_text(encoding="utf-8"))
    approval_receipt = json.loads(CANARY_APPROVAL_RECEIPT.read_text(encoding="utf-8"))
    approval_by_id = reference_approval_by_id(approval_receipt)
    refs = [
        attach_reference_approval(ref, approval_by_id)
        for ref in approved_reference_records(manifest)
    ]

    assert len(refs) == 3
    assert all(ref["approval_gate_status"] == "APPROVAL_RECEIPT_LINKED" for ref in refs)
    assert all(ref["approval_receipt_id"] for ref in refs)
    assert all(ref["approval_receipt_status"] == "APPROVED_CANARY_PIPELINE_ONLY" for ref in refs)
    assert all(ref["approval_scope"] == "CANARY_PIPELINE_ONLY" for ref in refs)
    assert all(approval_receipt_allows_embedding(ref) is True for ref in refs)
    assert all(ref["approval_promotion_allowed"] is False for ref in refs)


def test_overlay_event_can_render_without_claiming_supported_identity():
    overlay = load_json("ui_realtime_overlay_event.inconclusive.json")
    assert overlay["schema"] == "watch.ui_realtime_overlay_event.v1"
    assert overlay["track_id"] == "track_person_0248_0007"
    assert overlay["bbox"]["normalized"] is True
    assert overlay["identity_status"] == "IDENTITY_INCONCLUSIVE"
    assert overlay["identity_status"] != "IDENTITY_SUPPORTED"
    assert "not_live_identity_proof" in overlay["proof_scope"]


def test_identity_gate_withholds_canary_only_references_even_with_similarity_scores():
    source = json.loads(LIVE_APPROVAL_LINKED_RECEIPT.read_text(encoding="utf-8"))
    gate = build_identity_gate_receipt(source, source_path=LIVE_APPROVAL_LINKED_RECEIPT, threshold=0.72)

    assert gate["schema"] == "watch.identity_gate_receipt.v1"
    assert gate["status"] == "IDENTITY_LABELS_WITHHELD"
    assert gate["counts"]["comparison_count"] == 30
    assert gate["counts"]["candidate_count"] == 10
    assert gate["counts"]["promoted_count"] == 0
    assert gate["counts"]["withheld_count"] == 10
    assert gate["counts"]["memory_recall_item_count"] == 10
    assert all(item["ui_label_policy"] == "RENDER_PERSON_OBSERVATION_ONLY" for item in gate["candidates"])
    assert all(item["identity_status"] == "IDENTITY_WITHHELD" for item in gate["candidates"])
    assert any((item["best_similarity"] or 0) >= 0.72 for item in gate["candidates"])
    assert all("REFERENCE_NOT_APPROVED_FOR_IDENTITY_PROMOTION" in item["blockers"] for item in gate["candidates"])
    assert all("NEGATIVE_CONTROL_RECEIPT_MISSING" in item["blockers"] for item in gate["candidates"])


def test_negative_control_receipt_flags_canary_high_similarity_leakage():
    source = json.loads(LIVE_APPROVAL_LINKED_RECEIPT.read_text(encoding="utf-8"))
    receipt = build_negative_control_receipt(source, source_path=LIVE_APPROVAL_LINKED_RECEIPT, threshold=0.72)

    assert receipt["schema"] == "watch.negative_control_receipt.v1"
    assert receipt["status"] == "FAILED_CANARY_REFERENCES_NOT_INDEPENDENT"
    assert receipt["counts"]["comparison_count"] == 30
    assert receipt["counts"]["candidate_crop_count"] == 10
    assert receipt["counts"]["failure_count"] > 0
    assert all(
        item["failure_code"] == "CANARY_REFERENCE_HIGH_SIMILARITY_NOT_INDEPENDENT"
        for item in receipt["failures"]
    )
    assert all(item["reference_approval_scope"] == "CANARY_PIPELINE_ONLY" for item in receipt["failures"])
    assert any(float(item["cosine_similarity"]) >= 0.72 for item in receipt["failures"])


def test_identity_gate_consumes_failed_negative_control_receipt():
    source = json.loads(LIVE_APPROVAL_LINKED_RECEIPT.read_text(encoding="utf-8"))
    negative = build_negative_control_receipt(source, source_path=LIVE_APPROVAL_LINKED_RECEIPT, threshold=0.72)
    gate = build_identity_gate_receipt(
        source,
        source_path=LIVE_APPROVAL_LINKED_RECEIPT,
        threshold=0.72,
        negative_control_receipt=negative,
    )

    assert gate["status"] == "IDENTITY_LABELS_WITHHELD"
    assert gate["input_receipt_statuses"]["negative_control"] == "FAILED_CANARY_REFERENCES_NOT_INDEPENDENT"
    assert all("NEGATIVE_CONTROL_FAILED" in item["blockers"] for item in gate["candidates"])
    assert all("NEGATIVE_CONTROL_RECEIPT_MISSING" not in item["blockers"] for item in gate["candidates"])


def test_qdrant_recall_high_confidence_other_actor_requires_identity_stop():
    source = {
        "schema": "watch.identity_qdrant_eval.v1",
        "mocked": False,
        "live": True,
        "input_transport": "image_data_url",
        "results": [
            {
                "sample_index": 16,
                "time_seconds": 17.205,
                "yolo_track_key": "detector_9_track_2",
                "crop_path": "/tmp/crops/sample_16.png",
                "top_suggestion": {
                    "character_name": "Willie",
                    "actor_name": "Billy Bob Thornton",
                    "confidence": 0.932243,
                    "display_label": "Willie? 0.93",
                },
                "items": [
                    {
                        "character_name": "Willie",
                        "actor_name": "Billy Bob Thornton",
                        "confidence": 0.932243,
                        "visual_score": 0.932243,
                        "crop_path": "/tmp/willie_ref.png",
                    }
                ],
            }
        ],
    }

    receipt = build_qdrant_recall_identity_stop_receipt(
        source,
        source_path=Path("/tmp/live_qdrant_eval.json"),
        accepted_character="Marcus",
        conflict_threshold=0.90,
        suggestion_threshold=0.82,
    )

    assert receipt["schema"] == "watch.qdrant_recall_identity_stop_receipt.v1"
    assert receipt["mocked"] is False
    assert receipt["live"] is True
    assert receipt["status"] == "IDENTITY_RECALL_CONFLICTS_FOUND"
    assert receipt["counts"]["conflict_count"] == 1
    assert receipt["counts"]["stop_control_required_count"] == 1
    assert receipt["counts"]["training_eligible_count"] == 0
    decision = receipt["decisions"][0]
    assert decision["status"] == "IDENTITY_CONFLICT_STOP_REQUIRED"
    assert decision["ui_label_policy"] == "RENDER_CONFLICT_AND_STOP_TRACK_PROPAGATION"
    assert decision["label_to_render"] == "Willie? 0.93"
    assert decision["stop_control_required"] is True
    assert decision["eligible_for_training"] is False
    assert "MEMORY_RECALL_HIGH_CONFIDENCE_OTHER_ACTOR" in decision["blockers"]


def test_qdrant_recall_matching_accepted_label_can_count_for_readiness():
    source = {
        "mocked": False,
        "live": True,
        "results": [
            {
                "sample_index": 1,
                "time_seconds": 0.625,
                "yolo_track_key": "detector_9_track_2",
                "top_suggestion": {
                    "character_name": "Marcus",
                    "actor_name": "Tony Cox",
                    "confidence": 0.978397,
                    "display_label": "Marcus? 0.98",
                },
            }
        ],
    }

    receipt = build_qdrant_recall_identity_stop_receipt(
        source,
        source_path=Path("/tmp/live_qdrant_eval.json"),
        accepted_character="Marcus",
    )

    assert receipt["status"] == "IDENTITY_RECALL_SUPPORTED"
    assert receipt["counts"]["supported_count"] == 1
    assert receipt["counts"]["training_eligible_count"] == 1
    assert receipt["counts"]["conflict_count"] == 0
    decision = receipt["decisions"][0]
    assert decision["status"] == "ACCEPTED_LABEL_SUPPORTED_BY_RECALL"
    assert decision["ui_label_policy"] == "ALLOW_ACCEPTED_TRACK_LABEL"
    assert decision["label_to_render"] == "Marcus"
    assert decision["eligible_for_training"] is True
    assert decision["stop_control_required"] is False


def test_qdrant_recall_without_accepted_label_stays_tentative():
    source = {
        "mocked": False,
        "live": True,
        "results": [
            {
                "sample_index": 2,
                "time_seconds": 1.250,
                "yolo_track_key": "detector_9_track_2",
                "top_suggestion": {
                    "character_name": "Marcus",
                    "actor_name": "Tony Cox",
                    "confidence": 0.86,
                    "display_label": "Marcus? 0.86",
                },
            }
        ],
    }

    receipt = build_qdrant_recall_identity_stop_receipt(
        source,
        source_path=Path("/tmp/live_qdrant_eval.json"),
        accepted_character=None,
    )

    assert receipt["status"] == "IDENTITY_RECALL_SUPPORTED"
    assert receipt["counts"]["tentative_suggestion_count"] == 1
    assert receipt["counts"]["training_eligible_count"] == 0
    decision = receipt["decisions"][0]
    assert decision["status"] == "TENTATIVE_RECALL_SUGGESTION"
    assert decision["ui_label_policy"] == "RENDER_TENTATIVE_SUGGESTION_UNTIL_ACCEPTED"
    assert decision["label_to_render"] == "Marcus? 0.86"
    assert decision["eligible_for_training"] is False
    assert "HUMAN_ACCEPTANCE_REQUIRED" in decision["blockers"]


def test_live_yolo_track_qdrant_eval_receipt_marks_handoff_frame_as_stop():
    source = json.loads(LIVE_YOLO_TRACK_QDRANT_EVAL_RECEIPT.read_text(encoding="utf-8"))

    receipt = build_qdrant_recall_identity_stop_receipt(
        source,
        source_path=LIVE_YOLO_TRACK_QDRANT_EVAL_RECEIPT,
        accepted_character="Marcus",
        conflict_threshold=0.90,
        suggestion_threshold=0.82,
    )

    assert receipt["mocked"] is False
    assert receipt["live"] is True
    assert receipt["input_transport"] == "image_data_url"
    assert receipt["status"] == "IDENTITY_RECALL_CONFLICTS_FOUND"
    assert receipt["counts"]["evaluated_count"] == 18
    assert receipt["counts"]["supported_count"] == 17
    assert receipt["counts"]["conflict_count"] == 1
    assert receipt["counts"]["stop_control_required_count"] == 1
    conflict = [item for item in receipt["decisions"] if item["status"] == "IDENTITY_CONFLICT_STOP_REQUIRED"][0]
    assert conflict["time_seconds"] == 17.205
    assert conflict["accepted_character"] == "Marcus"
    assert conflict["top_character"] == "Willie"
    assert conflict["top_confidence"] >= 0.93
    assert conflict["eligible_for_training"] is False
    assert conflict["supporting_items"][0]["character_name"] == "Willie"
