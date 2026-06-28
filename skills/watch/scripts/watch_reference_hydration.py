#!/usr/bin/env python3
"""P0 reference-hydration helpers for the Watch skill.

This module is intentionally stdlib-only. It builds deterministic reference
hydration plans, source-manifest gates, observation ids, and planned memory
trace payloads. It does not write Qdrant, Arango, or memory records.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import uuid
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Optional

WATCH_NAMESPACE_UUID = uuid.UUID("7a17ce7d-9dbf-5e8a-bc40-8ef36138c84d")
MOVIE_KIND = "cinema_movie"
NON_MOVIE_KINDS = {"drone", "itar", "rtsp", "youtube"}
ASSET_KINDS = {MOVIE_KIND, *NON_MOVIE_KINDS}

HYDRATION_SCHEMA = "watch.reference_hydration_plan.v1"
SOURCE_MANIFEST_SCHEMA = "watch.source_reference_manifest.v1"
REFERENCE_PACKAGE_SCHEMA = "watch.reference_package.v1"
TRACK_OBSERVATION_SCHEMA = "watch.track_observation.v1"
IDENTITY_EVIDENCE_SCHEMA = "watch.identity_evidence.v1"
MEMORY_TRACE_SCHEMA = "watch.memory_trace_write_plan.v1"
LIVE_TRACKING_MEMORY_WINDOW_SCHEMA = "watch.live_tracking_memory_window_plan.v1"
GRAPH_VECTOR_PERSISTENCE_SCHEMA = "watch.graph_vector_persistence_plan.v1"
MEMORY_RECALL_VERIFICATION_SCHEMA = "watch.memory_recall_verification_plan.v1"
IDENTITY_REINFORCEMENT_PLAN_SCHEMA = "watch.identity_reinforcement_plan.v1"
REFERENCE_EMBEDDING_RECEIPT_PLAN_SCHEMA = "watch.reference_embedding_receipt_plan.v1"

STATE_REFERENCE_PACKAGE_MISSING = "REFERENCE_PACKAGE_MISSING"
STATE_REFERENCE_CANDIDATES_COLLECTED = "REFERENCE_CANDIDATES_COLLECTED"
STATE_REFERENCE_IMAGES_PENDING_APPROVAL = "REFERENCE_IMAGES_PENDING_APPROVAL"
STATE_REFERENCE_EMBEDDINGS_READY = "REFERENCE_EMBEDDINGS_READY"
STATE_IDENTITY_SUPPORTED = "IDENTITY_SUPPORTED"
STATE_IDENTITY_INCONCLUSIVE = "IDENTITY_INCONCLUSIVE"
STATE_IDENTITY_REFUTED = "IDENTITY_REFUTED"
STATE_IDENTITY_CANDIDATE = "IDENTITY_CANDIDATE"

APPROVED = "APPROVED"
PLANNED_NOT_WRITTEN = "PLANNED_NOT_WRITTEN"


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(value: Any) -> str:
    if not isinstance(value, str):
        value = canonical_json(value)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_id(prefix: str, value: Any) -> str:
    return f"{prefix}:{sha256_text(value)[:32]}"


def qdrant_point_id(canonical_id: str) -> str:
    return str(uuid.uuid5(WATCH_NAMESPACE_UUID, canonical_id))


def load_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_jsonl(path: str | Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for line_no, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: invalid JSONL record: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_no}: JSONL record must be an object")
        records.append(value)
    return records


def write_json(path: str | Path, value: Any) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def compute_asset_id(asset: Mapping[str, Any]) -> str:
    declared = asset.get("asset_id")
    if declared:
        return str(declared)
    material = {
        "asset_kind": asset.get("asset_kind"),
        "canonical_uri": asset.get("canonical_uri") or asset.get("source_uri") or asset.get("title"),
        "media_sha256": asset.get("media_sha256") or asset.get("declared_source_id") or asset.get("source_id"),
        "title": asset.get("title"),
        "release_year": asset.get("release_year"),
    }
    return stable_id("watch_asset", material)


def compute_segment_id(asset_id: str, start_ms: int, end_ms: int) -> str:
    return stable_id("watch_segment", {"asset_id": asset_id, "start_ms": start_ms, "end_ms": end_ms})


def compute_reference_package_id(asset_or_domain_id: str, entity_key: str, package_version: str = "v1") -> str:
    return stable_id("watch_refpkg", {"scope": asset_or_domain_id, "entity_key": entity_key, "package_version": package_version})


def compute_reference_item_id(reference_package_id: str, source_uri: str, image_sha256_or_external_id: str) -> str:
    return stable_id("watch_ref", {"reference_package_id": reference_package_id, "source_uri": source_uri, "source_hash": image_sha256_or_external_id})


def compute_track_observation_id(observation: Mapping[str, Any]) -> str:
    material = {
        "asset_id": observation.get("asset_id"),
        "segment_id": observation.get("segment_id"),
        "track_id": observation.get("track_id"),
        "frame_index": observation.get("frame_index"),
        "media_time_ms": observation.get("media_time_ms"),
        "bbox": observation.get("bbox"),
        "crop_sha256": observation.get("crop_sha256"),
        "source_event_id": observation.get("source_event_id"),
    }
    return stable_id("watch_obs", material)


def compute_identity_evidence_id(evidence: Mapping[str, Any]) -> str:
    material = {
        "track_observation_id": evidence.get("track_observation_id"),
        "reference_package_id": evidence.get("reference_package_id"),
        "approved_reference_ids": evidence.get("approved_reference_ids", []),
        "verifier_version": evidence.get("verifier_version", "watch_reference_hydration_P0"),
        "identity_status": evidence.get("identity_status"),
    }
    return stable_id("watch_identity", material)


def compute_case_anchor_id(asset_id: str, entity_ids: Iterable[str], time_range: Mapping[str, Any], evidence_ids: Iterable[str]) -> str:
    return stable_id("watch_case", {
        "asset_id": asset_id,
        "entity_ids": sorted(str(entity_id) for entity_id in entity_ids if entity_id),
        "time_range": dict(time_range),
        "evidence_ids": sorted(str(evidence_id) for evidence_id in evidence_ids if evidence_id),
    })


def approved_references(package: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    return [ref for ref in package.get("references", []) if ref.get("approval_status") == APPROVED]


def package_has_ready_embeddings(package: Mapping[str, Any]) -> bool:
    refs = approved_references(package)
    if not refs:
        return False
    for ref in refs:
        qdrant = ref.get("qdrant") or {}
        if qdrant.get("write_status") not in {"WRITTEN", "EXISTS"}:
            return False
        if not qdrant.get("collection") or not qdrant.get("point_id"):
            return False
    return True


def normalize_reference_candidates(asset: Mapping[str, Any], candidates: Mapping[str, Any] | None) -> List[Dict[str, Any]]:
    if not candidates:
        return []
    asset_id = compute_asset_id(asset)
    packages: List[Dict[str, Any]] = []
    for entity in candidates.get("entities", []):
        entity_id = entity.get("entity_id") or stable_id("watch_entity", {"asset_id": asset_id, "name": entity.get("display_name") or entity.get("character_name")})
        entity_key = entity.get("entity_key") or entity.get("character_name") or entity.get("display_name") or entity_id
        refpkg_id = entity.get("reference_package_id") or compute_reference_package_id(asset_id, entity_key)
        refs: List[Dict[str, Any]] = []
        for idx, source in enumerate(entity.get("candidate_sources", [])):
            source_uri = source.get("url") or source.get("source_uri") or f"candidate:{idx}"
            external_id = source.get("sha256") or source.get("external_id") or sha256_text(source_uri)
            ref_id = source.get("reference_item_id") or compute_reference_item_id(refpkg_id, source_uri, external_id)
            refs.append({
                "reference_item_id": ref_id,
                "approval_status": source.get("approval_status", "CANDIDATE"),
                "source": {
                    "source_type": source.get("source_type", "movie_public_search_candidate"),
                    "url": source_uri,
                    "title": source.get("title"),
                    "snippet": source.get("snippet"),
                    "proves_scene_visibility": False,
                },
                "qdrant": {
                    "collection": "watch_reference_image_embeddings",
                    "point_id": qdrant_point_id(ref_id),
                    "write_status": source.get("qdrant_write_status", PLANNED_NOT_WRITTEN),
                    "model": source.get("embedding_model", "jina-clip-v2-planned"),
                },
            })
        packages.append({
            "schema": REFERENCE_PACKAGE_SCHEMA,
            "reference_package_id": refpkg_id,
            "entity": {
                "entity_id": entity_id,
                "display_name": entity.get("display_name") or entity.get("character_name") or entity_key,
                "entity_kind": entity.get("entity_kind", "movie_character"),
                "aliases": entity.get("aliases", []),
            },
            "approval_status": entity.get("approval_status", "CANDIDATE"),
            "references": refs,
            "domain_prior_only": True,
        })
    return packages


def validate_source_manifest(manifest: Mapping[str, Any] | None, asset_kind: str) -> List[str]:
    errors: List[str] = []
    if not manifest:
        return ["SOURCE_REFERENCE_MANIFEST_MISSING"]
    if manifest.get("schema") != SOURCE_MANIFEST_SCHEMA:
        errors.append("SOURCE_REFERENCE_MANIFEST_SCHEMA_INVALID")
    if manifest.get("asset_kind") != asset_kind:
        errors.append("SOURCE_REFERENCE_MANIFEST_ASSET_KIND_MISMATCH")
    provenance = manifest.get("provenance") or {}
    if provenance.get("approval_status") != APPROVED:
        errors.append("SOURCE_REFERENCE_MANIFEST_NOT_APPROVED")
    packages = manifest.get("reference_packages") or []
    if not packages:
        errors.append("SOURCE_REFERENCE_PACKAGES_EMPTY")
    if not any(package_has_ready_embeddings(pkg) for pkg in packages):
        errors.append("SOURCE_REFERENCE_EMBEDDINGS_NOT_READY")
    return errors


def derive_reference_state(asset_kind: str, packages: List[Mapping[str, Any]], source_manifest_errors: List[str]) -> str:
    if asset_kind in NON_MOVIE_KINDS and source_manifest_errors:
        return STATE_REFERENCE_PACKAGE_MISSING
    if any(package_has_ready_embeddings(pkg) for pkg in packages):
        return STATE_REFERENCE_EMBEDDINGS_READY
    if packages:
        if any(pkg.get("references") for pkg in packages):
            return STATE_REFERENCE_IMAGES_PENDING_APPROVAL
        return STATE_REFERENCE_CANDIDATES_COLLECTED
    return STATE_REFERENCE_PACKAGE_MISSING


def build_reference_hydration_plan(
    asset: Mapping[str, Any],
    reference_candidates: Mapping[str, Any] | None = None,
    source_manifest: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    asset_kind = asset.get("asset_kind")
    if asset_kind not in ASSET_KINDS:
        raise ValueError(f"unsupported asset_kind: {asset_kind!r}")

    normalized_asset = copy.deepcopy(dict(asset))
    normalized_asset["asset_id"] = compute_asset_id(normalized_asset)

    packages: List[Dict[str, Any]] = []
    source_manifest_errors: List[str] = []

    if asset_kind == MOVIE_KIND:
        packages = normalize_reference_candidates(normalized_asset, reference_candidates)
        if not packages:
            source_manifest_errors.append("MOVIE_REFERENCE_CANDIDATES_MISSING")
    else:
        source_manifest_errors = validate_source_manifest(source_manifest, asset_kind)
        packages = copy.deepcopy((source_manifest or {}).get("reference_packages") or [])

    state = derive_reference_state(asset_kind, packages, source_manifest_errors)
    fail_closed_active = asset_kind in NON_MOVIE_KINDS and bool(source_manifest_errors)

    approved_ref_count = sum(len(approved_references(pkg)) for pkg in packages)
    ready_package_count = sum(1 for pkg in packages if package_has_ready_embeddings(pkg))
    candidate_source_count = sum(len(pkg.get("references", [])) for pkg in packages)

    can_ingest = not fail_closed_active and (asset_kind == MOVIE_KIND or ready_package_count > 0)
    can_track = can_ingest
    can_promote_identity = ready_package_count > 0

    return {
        "schema": HYDRATION_SCHEMA,
        "asset": normalized_asset,
        "state": state,
        "gates": {
            "can_ingest": can_ingest,
            "can_track": can_track,
            "can_promote_identity": can_promote_identity,
            "requires_human_approval": approved_ref_count == 0,
        },
        "reference_packages": packages,
        "counts": {
            "reference_package_count": len(packages),
            "candidate_source_count": candidate_source_count,
            "approved_reference_count": approved_ref_count,
            "ready_reference_package_count": ready_package_count,
        },
        "fail_closed": {
            "active": fail_closed_active,
            "reasons": source_manifest_errors,
        },
        "proof_scope": ["reference_hydration_plan", "planned_persistence_only"],
        "identity_policy": {
            "detector_label_can_promote_identity": False,
            "public_search_can_prove_scene_visibility": False,
            "requires_approved_references": True,
            "requires_observation_evidence": True,
            "requires_memory_recall_proof_for_answer_claim": True,
        },
    }


def validate_hydration_plan(plan: Mapping[str, Any], expect_fail_closed: bool = False) -> List[str]:
    errors: List[str] = []
    if plan.get("schema") != HYDRATION_SCHEMA:
        errors.append("HYDRATION_PLAN_SCHEMA_INVALID")
    asset = plan.get("asset") or {}
    asset_kind = asset.get("asset_kind")
    if asset_kind not in ASSET_KINDS:
        errors.append("ASSET_KIND_INVALID")
    gates = plan.get("gates") or {}
    fail_closed = plan.get("fail_closed") or {}
    if expect_fail_closed and not fail_closed.get("active"):
        errors.append("EXPECTED_FAIL_CLOSED_NOT_ACTIVE")
    if fail_closed.get("active") and (gates.get("can_ingest") or gates.get("can_track") or gates.get("can_promote_identity")):
        errors.append("FAIL_CLOSED_GATE_LEAK")
    if asset_kind in NON_MOVIE_KINDS and not fail_closed.get("active") and not plan.get("counts", {}).get("ready_reference_package_count"):
        errors.append("NON_MOVIE_REQUIRES_READY_SOURCE_REFERENCES")
    if gates.get("can_promote_identity") and not plan.get("counts", {}).get("ready_reference_package_count"):
        errors.append("IDENTITY_PROMOTION_WITHOUT_READY_REFERENCES")
    return errors


def normalize_track_observation(raw: Mapping[str, Any], asset: Mapping[str, Any]) -> Dict[str, Any]:
    asset_id = compute_asset_id(asset)
    start_ms = int(raw.get("segment_start_ms", raw.get("media_time_ms", 0)))
    end_ms = int(raw.get("segment_end_ms", start_ms + 1000))
    observation = copy.deepcopy(dict(raw))
    observation.setdefault("schema", TRACK_OBSERVATION_SCHEMA)
    observation.setdefault("asset_id", asset_id)
    observation.setdefault("segment_id", compute_segment_id(asset_id, start_ms, end_ms))
    observation.setdefault("identity_status", "UNVERIFIED")
    observation.setdefault("source_event_id", raw.get("event_id", "unknown_event"))
    observation["track_observation_id"] = raw.get("track_observation_id") or compute_track_observation_id(observation)
    qdrant_id = qdrant_point_id(observation["track_observation_id"])
    observation.setdefault("qdrant", {
        "collection": "watch_track_crop_embeddings",
        "point_id": qdrant_id,
        "write_status": PLANNED_NOT_WRITTEN,
        "model": "jina-clip-v2-planned",
    })
    return observation


def _bbox_xyxy_to_bbox(bbox_xyxy: Iterable[Any]) -> Dict[str, Any]:
    coords = [float(v) for v in bbox_xyxy]
    if len(coords) != 4:
        raise ValueError(f"bbox_xyxy must have four numbers, got {coords!r}")
    x1, y1, x2, y2 = coords
    return {
        "x": x1,
        "y": y1,
        "width": max(0.0, x2 - x1),
        "height": max(0.0, y2 - y1),
        "coordinate_space": "source_frame_pixels",
    }


def _candidate_confidence(event: Mapping[str, Any]) -> float:
    candidates = event.get("candidate_entities") or []
    if not candidates:
        return 0.0
    return max(float(candidate.get("confidence") or 0.0) for candidate in candidates)


def _representative_event(events: List[Mapping[str, Any]]) -> Mapping[str, Any]:
    return max(
        events,
        key=lambda event: (
            _candidate_confidence(event),
            float(event.get("media_time_seconds") or 0.0),
        ),
    )


def _window_time_range(events: List[Mapping[str, Any]]) -> Dict[str, int]:
    times = [float(event.get("media_time_seconds") or 0.0) for event in events]
    start_ms = int(min(times) * 1000)
    end_ms = int(max(times) * 1000)
    if end_ms <= start_ms:
        end_ms = start_ms + 200
    return {"start_ms": start_ms, "end_ms": end_ms}


def build_live_tracking_memory_window_plan(
    asset: Mapping[str, Any],
    events: Iterable[Mapping[str, Any]],
    sample_fps: float = 5.0,
) -> Dict[str, Any]:
    """Collapse live 5 FPS tracker events into bounded memory-write plans.

    The result remains a planned artifact. It never writes Qdrant, Arango, or
    memory, and it never promotes a candidate entity to supported identity.
    """

    normalized_asset = copy.deepcopy(dict(asset))
    normalized_asset["asset_id"] = compute_asset_id(normalized_asset)
    event_list = [copy.deepcopy(dict(event)) for event in events]
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for event in event_list:
        if event.get("schema_version") != "watch.live_track_update.v1":
            raise ValueError(f"unsupported live event schema: {event.get('schema_version')!r}")
        if event.get("event_type") != "track_update":
            continue
        track_id = str(event.get("track_id") or "")
        if not track_id:
            raise ValueError("live track event missing track_id")
        grouped.setdefault(track_id, []).append(event)

    observations: List[Dict[str, Any]] = []
    identity_evidence_records: List[Dict[str, Any]] = []
    windows: List[Dict[str, Any]] = []

    for track_id in sorted(grouped):
        track_events = sorted(grouped[track_id], key=lambda event: float(event.get("media_time_seconds") or 0.0))
        representative = _representative_event(track_events)
        time_range = _window_time_range(track_events)
        raw_observation = {
            "schema": TRACK_OBSERVATION_SCHEMA,
            "track_id": track_id,
            "segment_start_ms": time_range["start_ms"],
            "segment_end_ms": time_range["end_ms"],
            "media_time_ms": int(float(representative.get("media_time_seconds") or 0.0) * 1000),
            "bbox": _bbox_xyxy_to_bbox(representative.get("bbox_xyxy") or [0, 0, 0, 0]),
            "source_event_id": stable_id("watch_live_event_window", {
                "stream_id": representative.get("stream_id"),
                "asset_uid": representative.get("asset_uid"),
                "segment_id": representative.get("segment_id"),
                "track_id": track_id,
                "start_ms": time_range["start_ms"],
                "end_ms": time_range["end_ms"],
                "event_count": len(track_events),
            }),
            "identity_status": STATE_IDENTITY_CANDIDATE,
            "detected_class": representative.get("detected_class"),
            "live_event_count": len(track_events),
            "live_time_range": time_range,
            "candidate_entities": representative.get("candidate_entities") or [],
        }
        observation = normalize_track_observation(raw_observation, normalized_asset)
        observations.append(observation)

        candidates = representative.get("candidate_entities") or []
        primary_candidate = candidates[0] if candidates else {}
        identity_status = STATE_IDENTITY_INCONCLUSIVE
        identity_evidence_records.append({
            "schema": IDENTITY_EVIDENCE_SCHEMA,
            "track_observation_id": observation["track_observation_id"],
            "entity_id": primary_candidate.get("entity_id"),
            "entity_name": primary_candidate.get("name"),
            "reference_package_id": primary_candidate.get("reference_package_id"),
            "approved_reference_ids": [],
            "identity_status": identity_status,
            "verifier_version": "watch_live_tracking_memory_window_P0",
            "evidence": {
                "visual_match_status": "PROVISIONAL",
                "detector_status": representative.get("status", "PROVISIONAL"),
                "candidate_basis": primary_candidate.get("basis", []),
                "candidate_confidence": primary_candidate.get("confidence"),
                "event_count": len(track_events),
                "sample_fps": sample_fps,
            },
            "persistence": {},
            "promotion_blockers": [
                "LIVE_TRACK_PROVISIONAL",
                "REFERENCE_IMAGES_NOT_APPROVED",
                "APPROVED_REFERENCE_EMBEDDINGS_MISSING",
                "MEMORY_RECALL_NOT_VERIFIED",
            ],
        })
        windows.append({
            "track_id": track_id,
            "event_count": len(track_events),
            "time_range_ms": time_range,
            "representative_media_time_ms": observation["media_time_ms"],
            "track_observation_id": observation["track_observation_id"],
            "candidate_entities": representative.get("candidate_entities") or [],
            "identity_status": identity_status,
        })

    memory_trace_plan = build_memory_trace_plan(normalized_asset, observations, identity_evidence_records)
    return {
        "schema": LIVE_TRACKING_MEMORY_WINDOW_SCHEMA,
        "write_status": PLANNED_NOT_WRITTEN,
        "asset": normalized_asset,
        "sample_fps": sample_fps,
        "event_count": len(event_list),
        "track_window_count": len(windows),
        "windows": windows,
        "memory_trace_plan": memory_trace_plan,
        "proof_scope": [
            "live_event_windowing",
            "bounded_memory_trace_plan",
            "planned_persistence_only",
        ],
        "claims": {
            "proves": [
                "5fps live tracker events can be collapsed into bounded track observations",
                "candidate identity remains inconclusive without approved references and recall proof",
                "memory trace payloads are planned without direct Qdrant or Arango answers",
            ],
            "does_not_prove": [
                "real-time browser overlay animation",
                "supported character identity",
                "Qdrant write success",
                "Arango write success",
                "$memory recall success",
            ],
        },
    }


def _assert_no_raw_vectors(value: Any, path: str = "$") -> None:
    forbidden = {"embedding", "embeddings", "vector", "vectors", "dense_vector"}
    if isinstance(value, Mapping):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key) in forbidden:
                raise ValueError(f"raw vector-like field is forbidden at {child_path}")
            _assert_no_raw_vectors(child, child_path)
    elif isinstance(value, list):
        if len(value) > 8 and all(isinstance(item, (int, float)) for item in value):
            raise ValueError(f"raw numeric vector array is forbidden at {path}")
        for index, child in enumerate(value):
            _assert_no_raw_vectors(child, f"{path}[{index}]")


def build_graph_vector_persistence_plan(live_window_plan: Mapping[str, Any]) -> Dict[str, Any]:
    """Build planned Arango/Qdrant persistence records for a live window plan.

    Arango records contain metadata, graph edges, and Qdrant pointers only.
    Qdrant records are point plans without raw vectors; actual embedding is a
    later runtime step owned by the memory/vector layer.
    """

    if live_window_plan.get("schema") != LIVE_TRACKING_MEMORY_WINDOW_SCHEMA:
        raise ValueError(f"unsupported live window plan schema: {live_window_plan.get('schema')!r}")

    asset = copy.deepcopy(dict(live_window_plan.get("asset") or {}))
    asset_id = asset.get("asset_id") or compute_asset_id(asset)
    memory_trace = live_window_plan.get("memory_trace_plan") or {}
    observations = memory_trace.get("track_observations") or []
    identity_evidence = memory_trace.get("identity_evidence") or []

    collections: Dict[str, List[Dict[str, Any]]] = {
        "watch_assets": [],
        "watch_track_observations": [],
        "watch_identity_evidence": [],
        "watch_evidence_cases": [],
        "watch_evidence_edges": [],
        "watch_memory_receipts": [],
    }
    qdrant_points: Dict[str, List[Dict[str, Any]]] = {
        "watch_track_crop_embeddings": [],
        "watch_identity_evidence_embeddings": [],
        "watch_segment_text_embeddings": [],
    }

    collections["watch_assets"].append({
        "_key": asset_id.replace(":", "_"),
        "asset_id": asset_id,
        "schema": asset.get("schema", "watch.asset_metadata.v1"),
        "asset_kind": asset.get("asset_kind"),
        "title": asset.get("title"),
        "release_year": asset.get("release_year"),
        "canonical_uri": asset.get("canonical_uri"),
        "media_sha256": asset.get("media_sha256"),
    })

    identity_by_observation = {
        evidence.get("track_observation_id"): evidence
        for evidence in identity_evidence
    }

    for observation in observations:
        obs_id = observation["track_observation_id"]
        qdrant = observation.get("qdrant") or {}
        qdrant_pointer = {
            "collection": qdrant.get("collection", "watch_track_crop_embeddings"),
            "point_id": qdrant.get("point_id", qdrant_point_id(obs_id)),
            "model": qdrant.get("model", "jina-clip-v2-planned"),
            "write_status": PLANNED_NOT_WRITTEN,
        }
        collections["watch_track_observations"].append({
            "_key": obs_id.replace(":", "_"),
            "track_observation_id": obs_id,
            "asset_id": asset_id,
            "segment_id": observation.get("segment_id"),
            "track_id": observation.get("track_id"),
            "media_time_ms": observation.get("media_time_ms"),
            "bbox": observation.get("bbox"),
            "identity_status": observation.get("identity_status"),
            "source_event_id": observation.get("source_event_id"),
            "qdrant_pointers": [qdrant_pointer],
        })
        qdrant_points["watch_track_crop_embeddings"].append({
            "collection": qdrant_pointer["collection"],
            "point_id": qdrant_pointer["point_id"],
            "embedding_status": PLANNED_NOT_WRITTEN,
            "source_record_id": obs_id,
            "source_collection": "watch_track_observations",
            "modality": "frame_crop",
            "payload": {
                "asset_id": asset_id,
                "segment_id": observation.get("segment_id"),
                "track_observation_id": obs_id,
                "time_range": observation.get("live_time_range"),
                "schema": observation.get("schema"),
                "model": qdrant_pointer["model"],
                "source_sha256": observation.get("crop_sha256"),
            },
        })
        collections["watch_evidence_edges"].append({
            "_key": stable_id("watch_edge", {"from": asset_id, "to": obs_id, "type": "HAS_TRACK_OBSERVATION"}).replace(":", "_"),
            "_from": f"watch_assets/{asset_id.replace(':', '_')}",
            "_to": f"watch_track_observations/{obs_id.replace(':', '_')}",
            "edge_type": "HAS_TRACK_OBSERVATION",
            "asset_id": asset_id,
        })

        evidence = identity_by_observation.get(obs_id)
        if not evidence:
            continue
        evidence_id = evidence.get("identity_evidence_id") or compute_identity_evidence_id(evidence)
        entity_id = evidence.get("entity_id")
        qdrant_identity_pointer = {
            "collection": "watch_identity_evidence_embeddings",
            "point_id": qdrant_point_id(evidence_id),
            "model": "jina-clip-v2-planned",
            "write_status": PLANNED_NOT_WRITTEN,
        }
        collections["watch_identity_evidence"].append({
            "_key": evidence_id.replace(":", "_"),
            "identity_evidence_id": evidence_id,
            "track_observation_id": obs_id,
            "asset_id": asset_id,
            "entity_id": entity_id,
            "entity_name": evidence.get("entity_name"),
            "identity_status": evidence.get("identity_status"),
            "promotion_blockers": evidence.get("promotion_blockers", []),
            "qdrant_pointers": [qdrant_identity_pointer],
        })
        qdrant_points["watch_identity_evidence_embeddings"].append({
            "collection": qdrant_identity_pointer["collection"],
            "point_id": qdrant_identity_pointer["point_id"],
            "embedding_status": PLANNED_NOT_WRITTEN,
            "source_record_id": evidence_id,
            "source_collection": "watch_identity_evidence",
            "modality": "identity_evidence_summary",
            "payload": {
                "asset_id": asset_id,
                "segment_id": observation.get("segment_id"),
                "track_observation_id": obs_id,
                "identity_evidence_id": evidence_id,
                "entity_id": entity_id,
                "identity_status": evidence.get("identity_status"),
                "time_range": observation.get("live_time_range"),
                "schema": evidence.get("schema"),
                "model": qdrant_identity_pointer["model"],
            },
        })
        collections["watch_evidence_edges"].append({
            "_key": stable_id("watch_edge", {"from": obs_id, "to": evidence_id, "type": "HAS_IDENTITY_EVIDENCE"}).replace(":", "_"),
            "_from": f"watch_track_observations/{obs_id.replace(':', '_')}",
            "_to": f"watch_identity_evidence/{evidence_id.replace(':', '_')}",
            "edge_type": "HAS_IDENTITY_EVIDENCE",
            "asset_id": asset_id,
        })

        time_range = observation.get("live_time_range") or {}
        case_id = compute_case_anchor_id(asset_id, [entity_id] if entity_id else [], time_range, [evidence_id])
        collections["watch_evidence_cases"].append({
            "_key": case_id.replace(":", "_"),
            "case_id": case_id,
            "asset_id": asset_id,
            "case_anchor": {
                "entity_ids": [entity_id] if entity_id else [],
                "time_range": time_range,
                "track_ids": [observation.get("track_id")],
                "evidence_ids": [evidence_id],
            },
            "verdict": {
                "status": "INCONCLUSIVE",
                "failure_code": "NEEDS_HUMAN_REVIEW",
                "human_review_required": True,
            },
            "write_status": PLANNED_NOT_WRITTEN,
        })
        collections["watch_evidence_edges"].append({
            "_key": stable_id("watch_edge", {"from": evidence_id, "to": case_id, "type": "ANCHORS_CASE"}).replace(":", "_"),
            "_from": f"watch_identity_evidence/{evidence_id.replace(':', '_')}",
            "_to": f"watch_evidence_cases/{case_id.replace(':', '_')}",
            "edge_type": "ANCHORS_CASE",
            "asset_id": asset_id,
        })

    collections["watch_memory_receipts"].append({
        "_key": stable_id("watch_receipt", {"asset_id": asset_id, "plan_schema": GRAPH_VECTOR_PERSISTENCE_SCHEMA}).replace(":", "_"),
        "asset_id": asset_id,
        "write_status": PLANNED_NOT_WRITTEN,
        "recall_proof_required": True,
        "source_plan_schema": live_window_plan.get("schema"),
    })

    arango_plan = {
        "write_status": PLANNED_NOT_WRITTEN,
        "collections": collections,
        "forbidden": {
            "raw_vectors_allowed": False,
        },
    }
    qdrant_plan = {
        "write_status": PLANNED_NOT_WRITTEN,
        "collections": qdrant_points,
        "forbidden": {
            "direct_answer_path_allowed": False,
            "raw_vector_values_in_plan": False,
        },
    }
    plan = {
        "schema": GRAPH_VECTOR_PERSISTENCE_SCHEMA,
        "write_status": PLANNED_NOT_WRITTEN,
        "asset": asset,
        "source_live_window_plan_schema": live_window_plan.get("schema"),
        "arango_plan": arango_plan,
        "qdrant_plan": qdrant_plan,
        "memory_recall": {
            "required_before_answer_claim": True,
            "allowed_answer_path": "$memory recall",
            "direct_qdrant_or_arango_answer_allowed": False,
        },
        "counts": {
            "track_observations": len(collections["watch_track_observations"]),
            "identity_evidence": len(collections["watch_identity_evidence"]),
            "evidence_cases": len(collections["watch_evidence_cases"]),
            "graph_edges": len(collections["watch_evidence_edges"]),
            "qdrant_point_plans": sum(len(points) for points in qdrant_points.values()),
        },
        "proof_scope": [
            "arango_metadata_shape",
            "qdrant_pointer_shape",
            "planned_persistence_only",
        ],
        "claims": {
            "proves": [
                "bounded live windows can be shaped into Arango metadata and graph edge documents",
                "Qdrant persistence is represented as point plans with deterministic ids and payload metadata",
                "raw vectors are excluded from the graph persistence plan",
            ],
            "does_not_prove": [
                "Arango write success",
                "Qdrant write success",
                "$memory recall success",
                "supported character identity",
            ],
        },
    }
    _assert_no_raw_vectors(plan)
    return plan


def build_memory_recall_verification_plan(graph_vector_plan: Mapping[str, Any]) -> Dict[str, Any]:
    """Build planned $memory recall probes for Watch graph/vector persistence.

    This is not a recall result. It is the deterministic proof contract that a
    later live `/intent` + `/recall` run must satisfy before Watch can claim
    that entity/time retrieval works.
    """

    if graph_vector_plan.get("schema") != GRAPH_VECTOR_PERSISTENCE_SCHEMA:
        raise ValueError(f"unsupported graph/vector plan schema: {graph_vector_plan.get('schema')!r}")

    asset = copy.deepcopy(dict(graph_vector_plan.get("asset") or {}))
    asset_id = asset.get("asset_id") or compute_asset_id(asset)
    title = asset.get("title") or asset_id
    arango_collections = ((graph_vector_plan.get("arango_plan") or {}).get("collections") or {})
    cases = arango_collections.get("watch_evidence_cases") or []
    identity_evidence = arango_collections.get("watch_identity_evidence") or []
    observations = arango_collections.get("watch_track_observations") or []

    entity_ids = sorted({
        entity_id
        for case in cases
        for entity_id in ((case.get("case_anchor") or {}).get("entity_ids") or [])
        if entity_id
    })
    primary_entity_id = entity_ids[0] if entity_ids else None
    primary_entity_name = None
    for evidence in identity_evidence:
        if evidence.get("entity_id") == primary_entity_id:
            primary_entity_name = evidence.get("entity_name")
            break
    primary_entity_name = primary_entity_name or primary_entity_id or "tracked entity"

    all_case_ids = [case.get("case_id") for case in cases if case.get("case_id")]
    all_segment_ids = sorted({obs.get("segment_id") for obs in observations if obs.get("segment_id")})
    all_time_ranges = [
        (case.get("case_anchor") or {}).get("time_range")
        for case in cases
        if (case.get("case_anchor") or {}).get("time_range")
    ]
    start_ms = min((int(r.get("start_ms", 0)) for r in all_time_ranges), default=0)
    end_ms = max((int(r.get("end_ms", 0)) for r in all_time_ranges), default=start_ms)

    recall_requests = []
    if primary_entity_id:
        recall_requests.append({
            "request_id": stable_id("watch_recall_probe", {
                "asset_id": asset_id,
                "entity_id": primary_entity_id,
                "kind": "entity_segments",
            }),
            "kind": "entity_segments",
            "route": ["intent", "extract_entities", "recall"],
            "http": {
                "method": "POST",
                "path": "/recall",
                "body": {
                    "q": f"Which Watch evidence cases or movie segments contain {primary_entity_name} in {title}?",
                    "collections": ["watch_evidence_cases", "watch_identity_evidence", "watch_track_observations"],
                    "k": 10,
                },
            },
            "expected_constraints": {
                "asset_id": asset_id,
                "entity_id": primary_entity_id,
                "min_case_count": len(all_case_ids),
                "expected_case_ids": all_case_ids,
                "expected_segment_ids": all_segment_ids,
                "time_range_ms": {"start_ms": start_ms, "end_ms": end_ms},
            },
            "acceptance": {
                "requires_found": True,
                "requires_items_key": True,
                "requires_no_results_key_dependency": True,
                "requires_expected_asset": True,
                "requires_expected_entity": True,
                "requires_scores": ["bm25", "dense"],
                "dense_score_may_be_zero_until_qdrant_written": True,
            },
        })

    recall_requests.append({
        "request_id": stable_id("watch_recall_probe", {
            "asset_id": asset_id,
            "kind": "negative_entity_control",
        }),
        "kind": "negative_entity_control",
        "route": ["intent", "extract_entities", "recall"],
        "http": {
            "method": "POST",
            "path": "/recall",
            "body": {
                "q": f"Which Watch evidence cases contain Willie in {title} for this planned Marcus canary window?",
                "collections": ["watch_evidence_cases", "watch_identity_evidence", "watch_track_observations"],
                "k": 10,
            },
        },
        "expected_constraints": {
            "asset_id": asset_id,
            "forbidden_entity_ids": ["movie_domain_entities/willie_bad_santa_2003"],
            "forbidden_case_ids": all_case_ids,
            "reason": "This planned canary graph/vector artifact only contains provisional Marcus candidates.",
        },
        "acceptance": {
            "requires_no_forbidden_case_ids": True,
            "requires_no_wrong_entity_promotion": True,
        },
    })

    return {
        "schema": MEMORY_RECALL_VERIFICATION_SCHEMA,
        "verification_status": "PLANNED_NOT_QUERIED",
        "asset": asset,
        "source_graph_vector_plan_schema": graph_vector_plan.get("schema"),
        "memory_pipeline": ["intent", "extract_entities", "recall", "create_evidence_case", "answer", "clarify", "deflect"],
        "recall_requests": recall_requests,
        "proof_requirements": {
            "live_http_required": True,
            "memory_base_url": "http://127.0.0.1:8601",
            "read_response_key": "items",
            "forbidden_response_key_dependency": "results",
            "direct_qdrant_or_arango_answer_allowed": False,
            "answer_claim_requires_recall_artifact": True,
        },
        "expected_written_state_before_running": {
            "graph_vector_plan_write_status": graph_vector_plan.get("write_status"),
            "requires_arango_write_receipts": True,
            "requires_qdrant_write_receipts_for_dense_scores": True,
        },
        "proof_scope": [
            "recall_probe_contract",
            "planned_not_queried",
        ],
        "claims": {
            "proves": [
                "Watch recall proof must be question-shaped and use /recall items",
                "Expected asset/entity/time constraints are explicit before live recall",
                "Direct Qdrant or Arango answer paths remain forbidden",
            ],
            "does_not_prove": [
                "$memory recall success",
                "Arango write success",
                "Qdrant write success",
                "supported character identity",
            ],
        },
    }


def build_identity_reinforcement_plan(
    reference_manifest: Mapping[str, Any],
    graph_vector_plan: Mapping[str, Any],
    recall_verification_plan: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build the planned Watch identity reinforcement loop.

    The plan joins public/movie-domain reference candidates, live crop point
    plans, text/scene corroboration requirements, and `$memory recall` proof
    requirements. It does not run image search, embeddings, person re-ID,
    Arango/Qdrant writes, or recall.
    """

    if reference_manifest.get("schema_version") != "watch.identity_reference_manifest.v1":
        raise ValueError(f"unsupported reference manifest schema: {reference_manifest.get('schema_version')!r}")
    if graph_vector_plan.get("schema") != GRAPH_VECTOR_PERSISTENCE_SCHEMA:
        raise ValueError(f"unsupported graph/vector plan schema: {graph_vector_plan.get('schema')!r}")
    if recall_verification_plan.get("schema") != MEMORY_RECALL_VERIFICATION_SCHEMA:
        raise ValueError(f"unsupported recall plan schema: {recall_verification_plan.get('schema')!r}")

    asset = copy.deepcopy(dict(graph_vector_plan.get("asset") or {}))
    asset_id = asset.get("asset_id") or compute_asset_id(asset)
    qdrant_collections = ((graph_vector_plan.get("qdrant_plan") or {}).get("collections") or {})
    crop_point_plans = qdrant_collections.get("watch_track_crop_embeddings") or []
    identity_point_plans = qdrant_collections.get("watch_identity_evidence_embeddings") or []
    recall_requests = recall_verification_plan.get("recall_requests") or []

    entity_plans = []
    for candidate in reference_manifest.get("candidates") or []:
        entity_id = candidate.get("entity_id")
        review_crops = candidate.get("review_crops") or []
        approved_references = candidate.get("approved_references") or []
        reference_sources = candidate.get("reference_source_candidates") or []
        expected_pair_count = len(review_crops) * max(1, candidate.get("required_positive_reference_count", 3))
        blocked = not approved_references
        entity_plans.append({
            "entity_id": entity_id,
            "entity_name": candidate.get("name"),
            "actor_name": candidate.get("actor_name"),
            "status": "BLOCKED_PENDING_APPROVED_REFERENCES" if blocked else "READY_FOR_EMBEDDING_COMPARISON",
            "domain_reference_source_count": sum(int(source.get("result_count") or 0) for source in reference_sources),
            "approved_reference_count": len(approved_references),
            "review_crop_count": len(review_crops),
            "expected_crop_reference_pair_count": expected_pair_count,
            "required_positive_reference_count": candidate.get("required_positive_reference_count", 3),
            "required_negative_reference_count": candidate.get("required_negative_reference_count", 3),
            "reference_source_statuses": sorted({source.get("status") for source in reference_sources if source.get("status")}),
            "promotion_blockers": (
                [
                    "APPROVED_REFERENCE_IMAGES_MISSING",
                    "REFERENCE_IMAGE_EMBEDDINGS_NOT_WRITTEN",
                    "CROP_REFERENCE_COMPARISON_NOT_RUN",
                    "TEXT_SCENE_CORROBORATION_NOT_RUN",
                    "MEMORY_RECALL_NOT_VERIFIED",
                ]
                if blocked
                else [
                    "REFERENCE_IMAGE_EMBEDDINGS_NOT_WRITTEN",
                    "CROP_REFERENCE_COMPARISON_NOT_RUN",
                    "TEXT_SCENE_CORROBORATION_NOT_RUN",
                    "MEMORY_RECALL_NOT_VERIFIED",
                ]
            ),
            "recall_probe_ids": [
                request.get("request_id")
                for request in recall_requests
                if request.get("kind") == "entity_segments"
            ],
        })

    plan = {
        "schema": IDENTITY_REINFORCEMENT_PLAN_SCHEMA,
        "status": "PLANNED_NOT_RUN",
        "asset": asset,
        "source_reference_manifest_schema": reference_manifest.get("schema_version"),
        "source_graph_vector_plan_schema": graph_vector_plan.get("schema"),
        "source_recall_verification_plan_schema": recall_verification_plan.get("schema"),
        "reinforcement_loop": [
            {
                "stage": "domain_reference_seed",
                "source": "brave-search/movie-domain-memory",
                "output": "movie-domain actor/character candidates and reference-source URLs",
                "scene_truth_allowed": False,
            },
            {
                "stage": "live_crop_stream",
                "source": "Ultralytics YOLO + ByteTrack sampled at 5fps",
                "output": "bounded track crops and Qdrant crop point plans",
                "scene_truth_allowed": True,
            },
            {
                "stage": "multimodal_embedding_compare",
                "source": "Jina/Qdrant multimodal reference-image and crop points",
                "output": "crop/reference similarity receipts with positive and negative controls",
                "scene_truth_allowed": False,
            },
            {
                "stage": "text_scene_corroboration",
                "source": "SRT, Whisper, scene marker, VLM description, and row metadata",
                "output": "evidence that the candidate belongs to the row/time range",
                "scene_truth_allowed": True,
            },
            {
                "stage": "memory_recall_answer_gate",
                "source": "$memory /intent then /recall",
                "output": "question-shaped recall items with expected asset/entity/time constraints",
                "scene_truth_allowed": True,
            },
        ],
        "entity_reinforcement_plans": entity_plans,
        "qdrant_requirements": {
            "crop_point_plan_count": len(crop_point_plans),
            "identity_evidence_point_plan_count": len(identity_point_plans),
            "reference_image_collection": "watch_reference_image_embeddings",
            "track_crop_collection": "watch_track_crop_embeddings",
            "raw_vectors_in_arango_allowed": False,
        },
        "memory_requirements": {
            "allowed_answer_path": "$memory recall",
            "requires_intent_before_recall": True,
            "requires_items_key": True,
            "forbidden_results_key_dependency": True,
            "direct_qdrant_or_arango_answer_allowed": False,
            "recall_request_count": len(recall_requests),
        },
        "promotion_policy": {
            "supported_identity_requires": [
                "approved_reference_images",
                "reference_image_embedding_receipts",
                "track_crop_embedding_receipts",
                "crop_reference_similarity_receipt_with_negative_controls",
                "text_or_scene_row_corroboration",
                "memory_recall_items_matching_asset_entity_time",
            ],
            "domain_reference_seed_can_promote_identity": False,
            "detector_label_can_promote_identity": False,
            "human_override_allowed_with_receipt": True,
        },
        "negative_controls": [
            {
                "control_id": stable_id("watch_identity_negative_control", {"asset_id": asset_id, "control": "wrong_entity_promotion"}),
                "description": "A Marcus canary query must not promote Willie cases from this planned artifact.",
                "forbidden_entity_ids": ["movie_domain_entities/willie_bad_santa_2003"],
            }
        ],
        "counts": {
            "entity_plan_count": len(entity_plans),
            "domain_reference_source_count": sum(plan["domain_reference_source_count"] for plan in entity_plans),
            "approved_reference_count": sum(plan["approved_reference_count"] for plan in entity_plans),
            "review_crop_count": sum(plan["review_crop_count"] for plan in entity_plans),
            "planned_crop_reference_pair_count": sum(plan["expected_crop_reference_pair_count"] for plan in entity_plans),
            "qdrant_point_plan_count": len(crop_point_plans) + len(identity_point_plans),
            "recall_request_count": len(recall_requests),
        },
        "proof_scope": [
            "identity_reinforcement_contract",
            "planned_not_run",
        ],
        "claims": {
            "proves": [
                "Brave/movie-domain references are treated as priors, not scene truth",
                "Live crop, text/scene corroboration, Qdrant receipts, and memory recall are all required before identity support",
                "Negative controls are explicit before any recall or identity promotion claim",
            ],
            "does_not_prove": [
                "Brave image download success",
                "reference image approval",
                "Jina embedding success",
                "Qdrant write success",
                "Arango write success",
                "$memory recall success",
                "supported character identity",
                "real-time annotation tracking",
            ],
        },
    }
    _assert_no_raw_vectors(plan)
    return plan


def build_reference_embedding_receipt_plan(
    reference_manifest: Mapping[str, Any],
    identity_reinforcement_plan: Mapping[str, Any],
) -> Dict[str, Any]:
    """Build the planned reference-image embedding receipt gate.

    This joins Brave/movie-domain reference-source URLs to explicit download,
    approval, and Jina/Qdrant receipt requirements. It does not download
    images, approve references, run embeddings, write Qdrant, write Arango, or
    promote any scene identity.
    """

    if reference_manifest.get("schema_version") != "watch.identity_reference_manifest.v1":
        raise ValueError(f"unsupported reference manifest schema: {reference_manifest.get('schema_version')!r}")
    if identity_reinforcement_plan.get("schema") != IDENTITY_REINFORCEMENT_PLAN_SCHEMA:
        raise ValueError(f"unsupported identity reinforcement schema: {identity_reinforcement_plan.get('schema')!r}")

    asset = copy.deepcopy(dict(identity_reinforcement_plan.get("asset") or {}))
    asset_id = asset.get("asset_id") or compute_asset_id(asset)
    entity_requirements: List[Dict[str, Any]] = []
    qdrant_point_plans: List[Dict[str, Any]] = []

    for candidate in reference_manifest.get("candidates") or []:
        entity_id = candidate.get("entity_id")
        entity_name = candidate.get("name")
        actor_name = candidate.get("actor_name")
        approved_references = candidate.get("approved_references") or []
        required_positive = int(candidate.get("required_positive_reference_count") or 3)
        required_negative = int(candidate.get("required_negative_reference_count") or 3)
        source_urls = [
            url
            for source in (candidate.get("reference_source_candidates") or [])
            for url in (source.get("urls") or [])
            if url
        ]
        planned_slots = []
        for slot_kind, required_count in (("positive", required_positive), ("negative", required_negative)):
            for index in range(required_count):
                slot_id = stable_id("watch_reference_slot", {
                    "asset_id": asset_id,
                    "entity_id": entity_id,
                    "slot_kind": slot_kind,
                    "index": index,
                })
                point_id = qdrant_point_id(slot_id)
                source_url = source_urls[index % len(source_urls)] if source_urls else None
                slot = {
                    "slot_id": slot_id,
                    "slot_kind": slot_kind,
                    "entity_id": entity_id,
                    "entity_name": entity_name,
                    "actor_name": actor_name,
                    "source_url_candidate": source_url,
                    "download_receipt_required": True,
                    "approval_receipt_required": True,
                    "embedding_receipt_required": True,
                    "embedding_status": "BLOCKED_PENDING_APPROVED_SOURCE_IMAGE",
                    "scene_truth_allowed": False,
                    "promotion_allowed": False,
                    "qdrant_point_plan": {
                        "collection": "watch_reference_image_embeddings",
                        "point_id": point_id,
                        "embedding_status": "BLOCKED_PENDING_APPROVED_SOURCE_IMAGE",
                        "modality": "reference_image",
                        "embedding_model": "jina-clip-v2-planned",
                        "payload": {
                            "asset_id": asset_id,
                            "entity_id": entity_id,
                            "entity_name": entity_name,
                            "actor_name": actor_name,
                            "slot_kind": slot_kind,
                            "slot_index": index,
                            "source_url_candidate": source_url,
                            "domain_prior_only": True,
                            "scene_truth_allowed": False,
                        },
                    },
                }
                planned_slots.append(slot)
                qdrant_point_plans.append(slot["qdrant_point_plan"])

        blocked = len(approved_references) < required_positive
        entity_requirements.append({
            "entity_id": entity_id,
            "entity_name": entity_name,
            "actor_name": actor_name,
            "status": "BLOCKED_PENDING_APPROVED_REFERENCES" if blocked else "READY_FOR_REFERENCE_EMBEDDING",
            "candidate_source_count": len(source_urls),
            "approved_reference_count": len(approved_references),
            "required_positive_reference_count": required_positive,
            "required_negative_reference_count": required_negative,
            "planned_reference_image_slot_count": len(planned_slots),
            "planned_reference_image_slots": planned_slots,
            "promotion_blockers": (
                [
                    "APPROVED_REFERENCE_IMAGES_MISSING",
                    "REFERENCE_DOWNLOAD_RECEIPTS_MISSING",
                    "REFERENCE_APPROVAL_RECEIPTS_MISSING",
                    "REFERENCE_IMAGE_EMBEDDING_RECEIPTS_MISSING",
                    "NEGATIVE_CONTROL_REFERENCES_MISSING",
                ]
                if blocked
                else [
                    "REFERENCE_IMAGE_EMBEDDING_RECEIPTS_MISSING",
                    "NEGATIVE_CONTROL_REFERENCES_MISSING",
                ]
            ),
        })

    plan = {
        "schema": REFERENCE_EMBEDDING_RECEIPT_PLAN_SCHEMA,
        "status": "PLANNED_NOT_WRITTEN",
        "asset": asset,
        "source_reference_manifest_schema": reference_manifest.get("schema_version"),
        "source_identity_reinforcement_schema": identity_reinforcement_plan.get("schema"),
        "entity_reference_requirements": entity_requirements,
        "qdrant_reference_point_plan": {
            "collection": "watch_reference_image_embeddings",
            "write_status": PLANNED_NOT_WRITTEN,
            "points": qdrant_point_plans,
            "raw_vectors_in_plan": False,
        },
        "memory_requirements": {
            "allowed_answer_path": "$memory recall",
            "requires_intent_before_recall": True,
            "requires_items_key": True,
            "forbidden_results_key_dependency": True,
            "direct_qdrant_or_arango_answer_allowed": False,
        },
        "receipt_requirements": {
            "download_receipts_required": True,
            "human_or_policy_approval_receipts_required": True,
            "embedding_write_receipts_required": True,
            "negative_control_receipts_required": True,
            "similarity_comparison_receipts_required_before_identity_support": True,
        },
        "promotion_policy": {
            "domain_reference_seed_can_promote_identity": False,
            "reference_url_can_promote_identity": False,
            "reference_embedding_without_track_crop_can_promote_identity": False,
            "supported_identity_requires": [
                "approved_reference_images",
                "reference_image_embedding_receipts",
                "track_crop_embedding_receipts",
                "crop_reference_similarity_receipt_with_negative_controls",
                "text_or_scene_row_corroboration",
                "memory_recall_items_matching_asset_entity_time",
            ],
        },
        "counts": {
            "entity_requirement_count": len(entity_requirements),
            "approved_reference_count": sum(req["approved_reference_count"] for req in entity_requirements),
            "planned_reference_image_slot_count": sum(req["planned_reference_image_slot_count"] for req in entity_requirements),
            "qdrant_reference_point_plan_count": len(qdrant_point_plans),
        },
        "proof_scope": [
            "reference_embedding_receipt_contract",
            "planned_not_written",
        ],
        "claims": {
            "proves": [
                "Brave/movie-domain reference URLs are converted into explicit download, approval, and embedding receipt requirements",
                "Reference-image Qdrant plans contain point ids and payload metadata without raw vectors",
                "Reference images remain priors and cannot become scene truth or supported identity without track-crop comparison and memory recall",
            ],
            "does_not_prove": [
                "Brave image download success",
                "approved reference images",
                "Jina embedding success",
                "Qdrant write success",
                "Arango write success",
                "track crop/reference similarity",
                "$memory recall success",
                "supported character identity",
                "real-time annotation tracking",
            ],
        },
    }
    _assert_no_raw_vectors(plan)
    return plan


def identity_promotion_errors(identity_evidence: Mapping[str, Any]) -> List[str]:
    errors: List[str] = []
    status = identity_evidence.get("identity_status")
    approved_reference_ids = identity_evidence.get("approved_reference_ids") or []
    evidence = identity_evidence.get("evidence") or {}
    persistence = identity_evidence.get("persistence") or {}
    if status == STATE_IDENTITY_SUPPORTED:
        if not identity_evidence.get("track_observation_id"):
            errors.append("SUPPORTED_IDENTITY_MISSING_OBSERVATION")
        if not identity_evidence.get("reference_package_id"):
            errors.append("SUPPORTED_IDENTITY_MISSING_REFERENCE_PACKAGE")
        if not approved_reference_ids:
            errors.append("SUPPORTED_IDENTITY_MISSING_APPROVED_REFERENCES")
        if evidence.get("visual_match_status") != "SUPPORTED":
            errors.append("SUPPORTED_IDENTITY_MISSING_VISUAL_SUPPORT")
        if not persistence.get("arango_write_receipt"):
            errors.append("SUPPORTED_IDENTITY_MISSING_ARANGO_RECEIPT")
        if not persistence.get("qdrant_write_receipt"):
            errors.append("SUPPORTED_IDENTITY_MISSING_QDRANT_RECEIPT")
        if not persistence.get("memory_case_receipt"):
            errors.append("SUPPORTED_IDENTITY_MISSING_MEMORY_CASE_RECEIPT")
        if not persistence.get("recall_proof_id"):
            errors.append("SUPPORTED_IDENTITY_MISSING_RECALL_PROOF")
    return errors


def build_memory_trace_plan(
    asset: Mapping[str, Any],
    observations: Iterable[Mapping[str, Any]],
    identity_evidence_records: Iterable[Mapping[str, Any]],
) -> Dict[str, Any]:
    normalized_asset = copy.deepcopy(dict(asset))
    normalized_asset["asset_id"] = compute_asset_id(normalized_asset)
    normalized_observations = [normalize_track_observation(obs, normalized_asset) for obs in observations]

    identity_records = []
    for raw in identity_evidence_records:
        record = copy.deepcopy(dict(raw))
        record.setdefault("schema", IDENTITY_EVIDENCE_SCHEMA)
        record.setdefault("identity_status", STATE_IDENTITY_INCONCLUSIVE)
        record.setdefault("promotion_blockers", [])
        record["identity_evidence_id"] = raw.get("identity_evidence_id") or compute_identity_evidence_id(record)
        blockers = set(record.get("promotion_blockers", []))
        blockers.update(identity_promotion_errors(record))
        if record.get("identity_status") != STATE_IDENTITY_SUPPORTED and not blockers:
            blockers.add("IDENTITY_NOT_SUPPORTED")
        record["promotion_blockers"] = sorted(blockers)
        identity_records.append(record)

    records = []
    for obs in normalized_observations:
        records.append({
            "record_kind": "track_observation",
            "id": obs["track_observation_id"],
            "arango_collection": "watch_track_observations",
            "qdrant_collection": obs.get("qdrant", {}).get("collection"),
            "qdrant_point_id": obs.get("qdrant", {}).get("point_id"),
            "write_status": PLANNED_NOT_WRITTEN,
        })
    for evidence in identity_records:
        records.append({
            "record_kind": "identity_evidence",
            "id": evidence["identity_evidence_id"],
            "arango_collection": "watch_identity_evidence",
            "qdrant_collection": "watch_identity_evidence_embeddings",
            "qdrant_point_id": qdrant_point_id(evidence["identity_evidence_id"]),
            "write_status": PLANNED_NOT_WRITTEN,
            "identity_status": evidence.get("identity_status"),
            "promotion_blockers": evidence.get("promotion_blockers", []),
        })

    return {
        "schema": MEMORY_TRACE_SCHEMA,
        "write_status": PLANNED_NOT_WRITTEN,
        "asset": normalized_asset,
        "memory_pipeline": ["intent", "extract_entities", "recall", "create_evidence_case", "answer", "clarify", "deflect"],
        "records": records,
        "track_observations": normalized_observations,
        "identity_evidence": identity_records,
        "recall_proof_required": True,
        "direct_qdrant_or_arango_answer_allowed": False,
        "notes": [
            "This is a planned write payload only.",
            "Arango stores metadata and Qdrant pointers, never raw vectors.",
            "A later $memory recall proof is required before claiming retrieval works.",
        ],
    }
