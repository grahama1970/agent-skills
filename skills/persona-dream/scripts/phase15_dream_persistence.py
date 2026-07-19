#!/usr/bin/env python3
"""Phase 15 - Dream memory, graph, and Qdrant persistence.

Writes ONLY accepted records THROUGH the $memory HTTP contract (no second store,
no direct Arango/Qdrant writes). Records are explicitly synthetic:
{"synthetic_origin": true, "literal_historical_event": false}.

Graph edges use the README relationship vocabulary:
  dream --derived_from--> source memory
  dream --observed_in_scene--> Watch evidence
  dream --supports_interpretation--> accepted ToM candidate

CRITICAL BOUNDARY. The default mode is --dry-run: it writes a persistence PLAN
receipt with exact would-write payloads and hashes and performs ZERO canonical
writes. Live canonical writes require BOTH --allow-canonical-write AND a
non-superseded return id; a superseded / degraded / identity-DRIFT observation
hard-fails. This is non-negotiable: the historical Kling return is superseded
and must never become canonical dream memory.

For proof, --validation-collection performs a REAL /store into a clearly-scoped,
non-canonical collection (persona_dream_loop_validation) with write + exact
reread receipts, demonstrating the persistence machinery without touching
canonical dream memory.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util as _ilu
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEMORY_BASE_URL = os.environ.get("MEMORY_BASE_URL", "http://127.0.0.1:8601")

CANONICAL_DREAM_COLLECTION = "persona_memory"
CANONICAL_EDGE_COLLECTION = "persona_memory_edges"
CANONICAL_TOM_EDGE_COLLECTION = "tom_edges"
TOM_CANDIDATE_COLLECTION = "tom_candidates"
# Immutable Watch-evidence vertices materialized so observed_in_scene edges
# resolve to real documents (not dangling endpoints). Defect 3 fix.
WATCH_EVIDENCE_COLLECTION = "persona_dream_watch_evidence"
# Transactional staging + commit namespaces (retain-and-mark; no delete
# primitive exists on the $memory API). Defect 2 fix.
STAGING_COLLECTION = "persona_dream_canonical_staging"
COMMIT_MANIFEST_COLLECTION = "persona_dream_commit_manifests"
VALIDATION_COLLECTION = "persona_dream_loop_validation"

RENDERER_DEFECT_VERDICTS = {"DRIFT", "FAIL", "MISMATCH", "NO_MATCH"}

# phase13 owns build_observation_index; load it by path so watch-evidence
# vertices are sourced from the SAME deterministic observation index the
# interpretation cited.
_P13_PATH = Path(__file__).resolve().parent / "phase13_self_interpretation.py"
_p13_spec = _ilu.spec_from_file_location("phase13_self_interpretation", _P13_PATH)
assert _p13_spec and _p13_spec.loader
_p13 = _ilu.module_from_spec(_p13_spec)
_p13_spec.loader.exec_module(_p13)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON object required: {path}")
    return value


def canonical_sha(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def write_json(path: Path, value: dict[str, Any]) -> None:
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _http_post(url: str, payload: dict[str, Any], timeout: float = 15.0) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


# --------------------------------------------------------------------------- #
# Deterministic supersession / canonical-write decision                       #
# --------------------------------------------------------------------------- #
def acceptance_receipt_certifies(
    acceptance_receipt: dict[str, Any] | None,
    packet: dict[str, Any],
    return_id: str | None,
) -> tuple[bool, list[str]]:
    """Return (certifies, reasons). An agent-level acceptance receipt certifies a
    return for canonical write only when it is ACCEPTED_AGENT_LEVEL, binds to THIS
    exact return (video sha256 AND return id), and its fail-closed gauntlet gates
    (step 36 continuity, step 38 audio/dialogue) both PASS. Fail-closed: any
    mismatch or missing field means it does NOT certify."""
    if not isinstance(acceptance_receipt, dict):
        return False, ["NO_ACCEPTANCE_RECEIPT"]
    reasons: list[str] = []
    schema = str(acceptance_receipt.get("schema") or "")
    if not schema.startswith("persona_dream.post_return_acceptance_receipt.v"):
        reasons.append(f"ACCEPTANCE_RECEIPT_WRONG_SCHEMA:{schema or 'missing'}")
    if acceptance_receipt.get("status") != "ACCEPTED_AGENT_LEVEL":
        reasons.append(f"ACCEPTANCE_NOT_AGENT_LEVEL:{acceptance_receipt.get('status')}")
    receipt_sha = str(acceptance_receipt.get("return_video_sha256") or "")
    packet_sha = str(packet.get("source_video_sha256") or "")
    if not receipt_sha or receipt_sha != packet_sha:
        reasons.append("ACCEPTANCE_RECEIPT_VIDEO_SHA_MISMATCH")
    if return_id and str(acceptance_receipt.get("return_id") or "") != str(return_id):
        reasons.append("ACCEPTANCE_RECEIPT_RETURN_ID_MISMATCH")
    gate = acceptance_receipt.get("gate_summary") or {}
    if gate.get("step_36") is not True:
        reasons.append("ACCEPTANCE_STEP_36_NOT_PASS")
    if gate.get("step_38") is not True:
        reasons.append("ACCEPTANCE_STEP_38_NOT_PASS")
    if gate.get("agent_level_gauntlet") not in (None, "ACCEPTED"):
        reasons.append(f"ACCEPTANCE_GAUNTLET_NOT_ACCEPTED:{gate.get('agent_level_gauntlet')}")
    return (len(reasons) == 0), reasons


def canonical_write_decision(
    packet: dict[str, Any],
    allow_canonical_write: bool,
    return_id: str | None,
    superseded_return_ids: set[str] | None = None,
    acceptance_receipt: dict[str, Any] | None = None,
) -> tuple[bool, list[str]]:
    """Pure decision. Returns (allowed, blockers).

    HARD blocks (never overridable): a historical-origin return, a renderer
    identity-continuity DEFECT verdict, or a superseded return id can NEVER be
    written to canonical dream memory. The DEGRADED observation status is
    OVERRIDABLE only by a valid agent-level acceptance receipt that binds to this
    exact return and certifies the fail-closed gauntlet gates - this is what
    permits the first legitimate canonical write of an accepted successor return
    whose raw pre-mux packet was labelled DEGRADED before Tau-routed adjudication."""
    blockers: list[str] = []
    if not allow_canonical_write:
        blockers.append("CANONICAL_WRITE_FLAG_NOT_SET")
    if not return_id:
        blockers.append("RETURN_ID_MISSING")

    origin = str(packet.get("evidence_origin") or "")
    status = str(packet.get("status") or "")
    verdict = str(
        (((packet.get("step_hooks") or {}).get("step_36_identity_temporal_continuity") or {})
         .get("vision_review") or {}).get("verdict") or ""
    ).upper()

    # Hard, non-overridable blocks.
    if origin == "historical_provider_return":
        blockers.append("RETURN_IS_HISTORICAL_PROVIDER_RETURN")
    if verdict in RENDERER_DEFECT_VERDICTS:
        blockers.append(f"IDENTITY_CONTINUITY_DEFECT:{verdict}")
    if return_id and superseded_return_ids and return_id in superseded_return_ids:
        blockers.append("RETURN_ID_SUPERSEDED")

    # DEGRADED status is overridable ONLY by a certifying agent-level acceptance receipt.
    certifies, _reasons = acceptance_receipt_certifies(acceptance_receipt, packet, return_id)
    if status.startswith("DEGRADED") and not certifies:
        blockers.append("OBSERVATION_STATUS_DEGRADED")

    return (len(blockers) == 0), blockers


# --------------------------------------------------------------------------- #
# Payload builders                                                            #
# --------------------------------------------------------------------------- #
def build_dream_memory_document(
    dream_id: str,
    revision_id: str,
    run_id: str,
    persona_id: str,
    packet: dict[str, Any],
    interpretation: dict[str, Any],
    tom: dict[str, Any],
    key_prefix: str = "",
) -> dict[str, Any]:
    accepted = interpretation.get("accepted_interpretations", [])
    tom_candidates = tom.get("accepted_tom_candidates", [])
    retrieval_text = " ".join(c.get("statement", "") for c in accepted).strip() or (
        f"Synthetic dream of {persona_id} derived from the Kahalu'u surf memory residue."
    )
    return {
        "_key": f"{key_prefix}dream_{dream_id}",
        "kind": "synthetic_dream_memory",
        "persona_id": persona_id,
        "synthetic_origin": True,
        "literal_historical_event": False,
        "dream_id": dream_id,
        "revision_id": revision_id,
        "run_id": run_id,
        "retrieval_text": retrieval_text,
        "source_video_sha256": packet.get("source_video_sha256"),
        "observation_packet_sha256": interpretation.get("observation_packet_sha256"),
        "accepted_interpretation_ids": [c.get("interpretation_id") for c in accepted],
        "accepted_tom_candidate_ids": [c.get("candidate_id") for c in tom_candidates],
        "tom_state_types": sorted({c.get("tom_state_type") for c in tom_candidates if c.get("tom_state_type")}),
        "source_memory_ids": sorted({b.get("source_id") for b in interpretation.get("source_memory_bindings", [])}),
        "tags": [f"persona:{persona_id}", "synthetic_dream", "persona_dream", "dream_loop_validation"],
        "provenance": {
            "evidence_origin": packet.get("evidence_origin"),
            "observation_status": packet.get("status"),
            "source_revision_id": packet.get("source_revision_id"),
        },
        "created_at": utc_now(),
    }


def build_graph_edges(
    dream_doc: dict[str, Any],
    interpretation: dict[str, Any],
    tom: dict[str, Any],
    dream_collection: str,
    edge_collection: str,
    tom_edge_collection: str,
) -> list[dict[str, Any]]:
    dream_ref = f"{dream_collection}/{dream_doc['_key']}"
    edges: list[dict[str, Any]] = []

    # dream --derived_from--> source memory
    for src in dream_doc.get("source_memory_ids", []):
        edges.append({
            "collection": edge_collection,
            "document": {
                "_key": f"{dream_doc['_key']}__derived_from__{src}",
                "_from": dream_ref,
                "_to": f"persona_memory/{src}",
                "relationship_type": "derived_from",
                "synthetic_origin": True,
                "literal_historical_event": False,
            },
        })

    # dream --observed_in_scene--> Watch evidence (observation ids)
    observed = set()
    for c in interpretation.get("accepted_interpretations", []):
        observed.update(c.get("observation_refs", []))
    for obs_id in sorted(observed):
        edges.append({
            "collection": edge_collection,
            "document": {
                "_key": f"{dream_doc['_key']}__observed_in_scene__{obs_id}",
                "_from": dream_ref,
                "_to": f"persona_dream_watch_evidence/{obs_id}",
                "relationship_type": "observed_in_scene",
                "watch_observation_id": obs_id,
                "synthetic_origin": True,
            },
        })

    # dream --supports_interpretation--> accepted ToM candidate
    for c in tom.get("accepted_tom_candidates", []):
        cid = c.get("candidate_id")
        edges.append({
            "collection": tom_edge_collection,
            "document": {
                "_key": f"{dream_doc['_key']}__supports_interpretation__{cid}",
                "_from": dream_ref,
                "_to": f"tom_candidates/{cid}",
                "relationship_type": "supports_interpretation",
                "tom_state_type": c.get("tom_state_type"),
                "confidence": c.get("confidence"),
                "emotional_intensity": c.get("emotional_intensity"),
                "synthetic_origin": True,
                "literal_historical_event": False,
            },
        })
    return edges


# --------------------------------------------------------------------------- #
# Watch-evidence vertices (Defect 3: materialize the observed_in_scene targets)#
# --------------------------------------------------------------------------- #
def accepted_observed_ids(interpretation: dict[str, Any]) -> list[str]:
    """The Watch observation ids cited by the accepted interpretations - exactly
    the set the observed_in_scene edges point at."""
    observed: set[str] = set()
    for c in interpretation.get("accepted_interpretations", []):
        observed.update(c.get("observation_refs", []))
    return sorted(observed)


def build_watch_evidence_vertices(
    packet: dict[str, Any],
    interpretation: dict[str, Any],
    dream_id: str,
    return_id: str | None,
    adjudication_receipt_sha256: str | None,
) -> list[dict[str, Any]]:
    """Materialize immutable persona_dream_watch_evidence vertices for every
    observed_in_scene target, sourced from the observation packet + the phase13
    observation index + tau step-36 adjudication receipt hash. These are Watch
    evidence, NOT psychological claims: psychological_interpretation_performed is
    explicitly False."""
    index = {o["observation_id"]: o for o in _p13.build_observation_index(packet)}
    frames_by_index: dict[int, dict[str, Any]] = {}
    for fr in packet.get("frame_evidence", []) or []:
        if fr.get("index") is not None:
            frames_by_index[int(fr["index"])] = fr
    hooks = packet.get("step_hooks", {}) or {}
    source_video_sha256 = packet.get("source_video_sha256")

    vertices: list[dict[str, Any]] = []
    for obs_id in accepted_observed_ids(interpretation):
        entry = index.get(obs_id, {})
        obs_type = entry.get("observation_type", "unknown")
        statement = entry.get("summary", "")
        time_range: list[float] | None = None
        evidence_artifacts: list[dict[str, Any]] = []

        if obs_type == "frame":
            # frame_0006 -> index 6
            try:
                fidx = int(obs_id.split("_")[-1])
            except ValueError:
                fidx = None
            fr = frames_by_index.get(fidx) if fidx is not None else None
            if fr:
                ts = fr.get("timestamp_seconds")
                time_range = [ts, ts] if ts is not None else None
                if fr.get("path") and fr.get("sha256"):
                    evidence_artifacts.append({"path": fr["path"], "sha256": fr["sha256"]})
        elif obs_type == "renderer_continuity_review":
            cont = hooks.get("step_36_identity_temporal_continuity") or {}
            window = cont.get("identity_window_seconds")
            if isinstance(window, list) and len(window) == 2:
                time_range = window
            for f in cont.get("identity_review_frames", []) or []:
                if f.get("path"):
                    evidence_artifacts.append({"path": f["path"], "sha256": f.get("sha256")})
        elif obs_type == "speaker_visibility":
            spk = hooks.get("step_38_visible_speaker_lipsync") or {}
            interval = spk.get("spoken_interval_seconds")
            if isinstance(interval, list) and len(interval) == 2:
                time_range = interval
            for f in spk.get("speaker_visibility_frames", []) or []:
                if f.get("path"):
                    evidence_artifacts.append({"path": f["path"], "sha256": f.get("sha256")})
        # coverage_gap and any other type: statement-only evidence.

        vertices.append({
            "_key": obs_id,
            "kind": "persona_dream_watch_evidence",
            "dream_id": dream_id,
            "return_id": return_id,
            "source_video_sha256": source_video_sha256,
            "observation_type": obs_type,
            "time_range": time_range,
            "statement": statement,
            "confidence": None,
            "evidence_artifacts": evidence_artifacts,
            "adjudication_receipt_sha256": adjudication_receipt_sha256,
            "synthetic_origin": True,
            "psychological_interpretation_performed": False,
        })
    return vertices


# --------------------------------------------------------------------------- #
# Live validation-collection write + exact reread proof                       #
# --------------------------------------------------------------------------- #
def _normalize_numbers(obj: Any) -> Any:
    """Collapse integer-valued floats to ints (0.0 -> 0, 5.0 -> 5) recursively.

    ArangoDB stores an integer-valued JSON float as an int, so a byte-for-byte
    reread of e.g. time_range [0.0, 10.04] comes back as [0, 10.04]. That is a
    lossless numeric round-trip (0.0 == 0), NOT corruption, so the reread-fidelity
    hash normalizes both sides identically. A genuinely changed number, a missing
    field, or a changed string is still detected. This normalization applies ONLY
    to the persistence reread check - never to the phase13/phase14 binding hashes
    (canonical_sha), which must stay byte-exact to the drafted artifacts."""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float) and obj == int(obj):
        return int(obj)
    if isinstance(obj, dict):
        return {k: _normalize_numbers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_numbers(v) for v in obj]
    return obj


def store_and_reread(document: dict[str, Any], collection: str, base_url: str) -> dict[str, Any]:
    """Write one document through /store, then reread it through /list and
    prove the stored payload matches by content hash of the caller-owned fields."""
    written_sha = authored_sha(document)
    store_resp = _http_post(f"{base_url.rstrip('/')}/store", {"document": document, "collection": collection})
    reread = _http_post(
        f"{base_url.rstrip('/')}/list",
        {"collection": collection, "limit": 5, "filters": {"_key": document["_key"]}},
    )
    docs = reread.get("documents") or reread.get("items") or []
    match = None
    reread_sha = None
    for d in docs:
        if d.get("_key") == document["_key"]:
            # Compare only the caller-authored fields we wrote.
            reread_subset = {k: d.get(k) for k in document if not k.startswith("_") or k == "_key"}
            reread_sha = canonical_sha(_normalize_numbers(reread_subset))
            match = reread_sha == written_sha
            break
    return {
        "collection": collection,
        "key": document["_key"],
        "written_content_sha256": written_sha,
        "reread_content_sha256": reread_sha,
        "exact_reread_match": bool(match),
        "store_ok": bool(store_resp.get("ok", True)) if isinstance(store_resp, dict) else True,
        "reread_found": reread_sha is not None,
    }


# --------------------------------------------------------------------------- #
# Transactional staged-commit persistence (Defect 2)                          #
# --------------------------------------------------------------------------- #
def authored_sha(document: dict[str, Any]) -> str:
    """Reread-fidelity content hash over the caller-authored fields (keeps _key,
    drops _id/_rev), with integer-valued floats normalized so a lossless daemon
    numeric round-trip does not read as corruption. See _normalize_numbers."""
    authored = {k: v for k, v in document.items() if not k.startswith("_") or k == "_key"}
    return canonical_sha(_normalize_numbers(authored))


def compute_idempotency_key(
    dream_id: str,
    return_id: str | None,
    packet: dict[str, Any],
    phase13_sha: str,
    phase14_sha: str,
) -> str:
    """Deterministic write-set identity: same dream + return + phase13 + phase14
    always yields the same key, so a rerun is detectable and resumable."""
    material = {
        "dream_id": dream_id,
        "return_id": return_id,
        "return_video_sha256": packet.get("source_video_sha256"),
        "phase13_sha256": phase13_sha,
        "phase14_sha256": phase14_sha,
    }
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_write_set(
    dream_doc: dict[str, Any],
    interpretation: dict[str, Any],
    tom: dict[str, Any],
    watch_vertices: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ordered, deterministic canonical write-set: dream node, ToM nodes, Watch
    evidence vertices, then every graph edge. Each entry is
    {collection, document, kind}."""
    ws: list[dict[str, Any]] = [
        {"collection": CANONICAL_DREAM_COLLECTION, "document": dream_doc, "kind": "dream_node"},
    ]
    for cand in tom.get("accepted_tom_candidates", []):
        cid = cand.get("candidate_id")
        if not cid:
            continue
        cand_doc = {**cand, "_key": str(cid), "synthetic_origin": True, "literal_historical_event": False}
        ws.append({"collection": TOM_CANDIDATE_COLLECTION, "document": cand_doc, "kind": "tom_node"})
    for v in watch_vertices:
        ws.append({"collection": WATCH_EVIDENCE_COLLECTION, "document": v, "kind": "watch_vertex"})
    for e in build_graph_edges(
        dream_doc, interpretation, tom,
        CANONICAL_DREAM_COLLECTION, CANONICAL_EDGE_COLLECTION, CANONICAL_TOM_EDGE_COLLECTION,
    ):
        ws.append({"collection": e["collection"], "document": e["document"], "kind": "edge"})
    return ws


def _staging_key(idempotency_key: str, collection: str, target_key: str) -> str:
    digest = hashlib.sha256(f"{collection}/{target_key}".encode()).hexdigest()[:24]
    return f"stg_{idempotency_key[:16]}_{digest}"


def stage_and_verify(
    entry: dict[str, Any], idempotency_key: str, base_url: str
) -> dict[str, Any]:
    """Write a record into the staging collection wrapped with staged=True and
    its authored-content hash, then reread the staged wrapper and verify the
    payload survived byte-for-byte."""
    doc = entry["document"]
    target_collection = entry["collection"]
    target_key = doc["_key"]
    payload_sha = authored_sha(doc)
    staged_doc = {
        "_key": _staging_key(idempotency_key, target_collection, target_key),
        "kind": "canonical_staging_record",
        "idempotency_key": idempotency_key,
        "staged": True,
        "committed": False,
        "target_collection": target_collection,
        "target_key": target_key,
        "record_kind": entry["kind"],
        "payload": doc,
        "payload_sha256": payload_sha,
    }
    _http_post(f"{base_url.rstrip('/')}/store", {"document": staged_doc, "collection": STAGING_COLLECTION})
    reread = _http_post(
        f"{base_url.rstrip('/')}/list",
        {"collection": STAGING_COLLECTION, "limit": 3, "filters": {"_key": staged_doc["_key"]}},
    )
    docs = reread.get("documents") or reread.get("items") or []
    match = False
    reread_payload_sha = None
    for d in docs:
        if d.get("_key") == staged_doc["_key"]:
            reread_payload_sha = authored_sha(d.get("payload") or {})
            match = reread_payload_sha == payload_sha and d.get("payload_sha256") == payload_sha
            break
    return {
        "staging_key": staged_doc["_key"],
        "target_collection": target_collection,
        "target_key": target_key,
        "record_kind": entry["kind"],
        "payload_sha256": payload_sha,
        "reread_payload_sha256": reread_payload_sha,
        "exact_reread_match": bool(match),
    }


def write_commit_manifest(
    idempotency_key: str,
    dream_id: str,
    return_id: str | None,
    phase13_sha: str,
    phase14_sha: str,
    publish_receipts: list[dict[str, Any]],
    staging_all_match: bool,
    base_url: str,
    retroactive: bool = False,
    justification: str | None = None,
) -> dict[str, Any]:
    """Write the single-source-of-truth commit manifest and flip active=True.
    Canonical visibility is defined by this record; it binds the exact phase13 +
    phase14 artifacts and the authored hash of every published record."""
    record_index = [
        {
            "collection": r["collection"],
            "key": r["key"],
            "payload_sha256": r["written_content_sha256"],
            "published_reread_match": r["exact_reread_match"],
        }
        for r in publish_receipts
    ]
    all_published = all(r["exact_reread_match"] for r in publish_receipts)
    manifest_doc = {
        "_key": f"commit_{idempotency_key}",
        "kind": "persona_dream_commit_manifest",
        "schema": "persona_dream.canonical_commit_manifest.v1",
        "idempotency_key": idempotency_key,
        "dream_id": dream_id,
        "return_id": return_id,
        "phase13_sha256": phase13_sha,
        "phase14_sha256": phase14_sha,
        "active": True,
        "retroactive_commit": bool(retroactive),
        "justification": justification,
        "staging_all_exact_reread_match": staging_all_match,
        "published_all_exact_reread_match": all_published,
        "record_count": len(record_index),
        "record_index": record_index,
        "committed_at": utc_now(),
    }
    receipt = store_and_reread(manifest_doc, COMMIT_MANIFEST_COLLECTION, base_url)
    return {
        "key": manifest_doc["_key"],
        "active": True,
        "retroactive_commit": bool(retroactive),
        "record_count": len(record_index),
        "published_all_exact_reread_match": all_published,
        "exact_reread_match": receipt["exact_reread_match"],
        "manifest_sha256": receipt["written_content_sha256"],
        "receipt": receipt,
    }


def existing_commit_manifest(idempotency_key: str, base_url: str) -> dict[str, Any] | None:
    key = f"commit_{idempotency_key}"
    reread = _http_post(
        f"{base_url.rstrip('/')}/list",
        {"collection": COMMIT_MANIFEST_COLLECTION, "limit": 3, "filters": {"_key": key}},
    )
    for d in reread.get("documents") or reread.get("items") or []:
        if d.get("_key") == key:
            return d
    return None


def persist_canonical(
    dream_doc: dict[str, Any],
    interpretation: dict[str, Any],
    tom: dict[str, Any],
    watch_vertices: list[dict[str, Any]],
    base_url: str,
    *,
    dream_id: str,
    return_id: str | None,
    packet: dict[str, Any],
    phase13_sha: str,
    phase14_sha: str,
    retroactive: bool = False,
    justification: str | None = None,
) -> dict[str, Any]:
    """Transactional canonical write:

      1. Compute a deterministic idempotency key (write-set identity).
      2. Detect a prior commit manifest for this key -> resume or quarantine.
      3. Stage every record (staging collection, staged=True) + verify reread.
      4. Only if ALL staged records verify, publish each to its canonical
         collection + verify reread.
      5. Write the commit manifest (active=True) binding phase13 + phase14 and
         every published hash + verify reread.

    canonical_dream_memory_written (decided by the caller) requires staging AND
    publish AND commit-manifest to all reread-match. A mid-set failure leaves the
    commit manifest absent/inactive, so nothing is treated as canonically
    visible."""
    idempotency_key = compute_idempotency_key(dream_id, return_id, packet, phase13_sha, phase14_sha)
    write_set = build_write_set(dream_doc, interpretation, tom, watch_vertices)
    expected_count = len(write_set)

    # --- Detect-and-quarantine on rerun -----------------------------------
    prior = existing_commit_manifest(idempotency_key, base_url)
    resumed = False
    quarantine: dict[str, Any] | None = None
    if prior is not None:
        # Re-verify every published record still rereads exactly.
        reverify = []
        for entry in write_set:
            r = store_and_reread_check_only(entry["document"], entry["collection"], base_url)
            reverify.append(r)
        if all(r["exact_reread_match"] for r in reverify) and len(reverify) == expected_count:
            resumed = True
        else:
            missing = [r["key"] for r in reverify if not r["exact_reread_match"]]
            quarantine = {
                "idempotency_key": idempotency_key,
                "reason": "PRIOR_MANIFEST_WITH_INCOMPLETE_OR_DRIFTED_RECORDS",
                "unverified_keys": missing,
            }
            _http_post(
                f"{base_url.rstrip('/')}/store",
                {
                    "collection": COMMIT_MANIFEST_COLLECTION,
                    "document": {
                        "_key": f"commit_{idempotency_key}",
                        **prior,
                        "active": False,
                        "quarantined": True,
                        "quarantine": quarantine,
                        "quarantined_at": utc_now(),
                    },
                },
            )

    # --- Stage -------------------------------------------------------------
    staging_receipts = [stage_and_verify(entry, idempotency_key, base_url) for entry in write_set]
    staging_all_match = all(r["exact_reread_match"] for r in staging_receipts)
    staging_proof = {
        "collection": STAGING_COLLECTION,
        "expected_count": expected_count,
        "staged_count": len(staging_receipts),
        "all_exact_reread_match": staging_all_match,
        "quarantined": quarantine is not None,
        "receipts": staging_receipts,
    }

    node_receipts: list[dict[str, Any]] = []
    edge_receipts: list[dict[str, Any]] = []
    watch_receipts: list[dict[str, Any]] = []
    commit_manifest: dict[str, Any] | None = None
    all_publish_receipts: list[dict[str, Any]] = []

    # --- Publish (only if staging fully verified and not quarantined) ------
    if staging_all_match and quarantine is None:
        for entry in write_set:
            r = store_and_reread(entry["document"], entry["collection"], base_url)
            all_publish_receipts.append({**r, "record_kind": entry["kind"]})
            if entry["kind"] == "edge":
                edge_receipts.append(r)
            elif entry["kind"] == "watch_vertex":
                watch_receipts.append(r)
            else:
                node_receipts.append(r)

        commit_manifest = write_commit_manifest(
            idempotency_key, dream_id, return_id, phase13_sha, phase14_sha,
            all_publish_receipts, staging_all_match, base_url,
            retroactive=retroactive, justification=justification,
        )

    publish_all_match = bool(all_publish_receipts) and all(
        r["exact_reread_match"] for r in all_publish_receipts
    )
    return {
        "idempotency_key": idempotency_key,
        "records_written": len(all_publish_receipts),
        "expected_record_count": expected_count,
        "all_exact_reread_match": staging_all_match and publish_all_match,
        "staging_all_exact_reread_match": staging_all_match,
        "publish_all_exact_reread_match": publish_all_match,
        "resumed_from_prior_commit": resumed,
        "quarantine": quarantine,
        "node_keys": [r["key"] for r in node_receipts],
        "edge_keys": [r["key"] for r in edge_receipts],
        "watch_vertex_keys": [r["key"] for r in watch_receipts],
        "tom_node_keys": [str(c.get("candidate_id")) for c in tom.get("accepted_tom_candidates", []) if c.get("candidate_id")],
        "node_receipts": node_receipts,
        "edge_receipts": edge_receipts,
        "watch_vertex_receipts": watch_receipts,
        "staging_proof": staging_proof,
        "commit_manifest": commit_manifest,
    }


def store_and_reread_check_only(document: dict[str, Any], collection: str, base_url: str) -> dict[str, Any]:
    """Reread-and-verify WITHOUT writing (used on rerun detection)."""
    written_sha = authored_sha(document)
    reread = _http_post(
        f"{base_url.rstrip('/')}/list",
        {"collection": collection, "limit": 5, "filters": {"_key": document["_key"]}},
    )
    docs = reread.get("documents") or reread.get("items") or []
    match = False
    reread_sha = None
    for d in docs:
        if d.get("_key") == document["_key"]:
            reread_subset = {k: d.get(k) for k in document if not k.startswith("_") or k == "_key"}
            reread_sha = canonical_sha(_normalize_numbers(reread_subset))
            match = reread_sha == written_sha
            break
    return {
        "collection": collection,
        "key": document["_key"],
        "written_content_sha256": written_sha,
        "reread_content_sha256": reread_sha,
        "exact_reread_match": bool(match),
        "reread_found": reread_sha is not None,
    }


# --------------------------------------------------------------------------- #
# Orchestration                                                               #
# --------------------------------------------------------------------------- #
def run_phase15(
    observation_path: Path,
    interpretation_path: Path,
    tom_path: Path,
    dream_id: str,
    revision_id: str,
    run_id: str,
    persona_id: str,
    allow_canonical_write: bool = False,
    return_id: str | None = None,
    validation_collection: str | None = None,
    base_url: str = MEMORY_BASE_URL,
    acceptance_receipt_path: Path | None = None,
    superseded_return_ids: set[str] | None = None,
) -> dict[str, Any]:
    packet = read_json(observation_path)
    interpretation = read_json(interpretation_path)
    tom = read_json(tom_path)
    acceptance_receipt = read_json(acceptance_receipt_path) if acceptance_receipt_path else None

    allowed, blockers = canonical_write_decision(
        packet, allow_canonical_write, return_id,
        superseded_return_ids=superseded_return_ids,
        acceptance_receipt=acceptance_receipt,
    )
    acceptance_certifies, acceptance_reasons = acceptance_receipt_certifies(
        acceptance_receipt, packet, return_id
    )

    # Hash-bind the exact predecessor artifacts (phase13 + phase14).
    phase13_sha = canonical_sha(interpretation)
    phase14_sha = canonical_sha(tom)

    # tau step-36 adjudication receipt hash for Watch-evidence provenance.
    adjudication_receipt_sha256 = None
    if acceptance_receipt is not None:
        adjudication_receipt_sha256 = canonical_sha(acceptance_receipt)

    # Canonical plan (dry-run) - exact would-write payloads + hashes, zero writes.
    canonical_doc = build_dream_memory_document(
        dream_id, revision_id, run_id, persona_id, packet, interpretation, tom
    )
    canonical_edges = build_graph_edges(
        canonical_doc, interpretation, tom,
        CANONICAL_DREAM_COLLECTION, CANONICAL_EDGE_COLLECTION, CANONICAL_TOM_EDGE_COLLECTION,
    )
    watch_vertices = build_watch_evidence_vertices(
        packet, interpretation, dream_id, return_id, adjudication_receipt_sha256
    )
    canonical_plan = {
        "dream_memory_document": {
            "collection": CANONICAL_DREAM_COLLECTION,
            "document": canonical_doc,
            "payload_sha256": canonical_sha(canonical_doc),
        },
        "watch_evidence_vertices": [
            {"collection": WATCH_EVIDENCE_COLLECTION, "document": v, "payload_sha256": canonical_sha(v)}
            for v in watch_vertices
        ],
        "graph_edges": [
            {"collection": e["collection"], "document": e["document"], "payload_sha256": canonical_sha(e["document"])}
            for e in canonical_edges
        ],
        "idempotency_key": compute_idempotency_key(dream_id, return_id, packet, phase13_sha, phase14_sha),
        "phase13_sha256": phase13_sha,
        "phase14_sha256": phase14_sha,
        "qdrant_embedding": {
            "note": "Memory semantic-sync embeds retrieval_text on /store; do not write vector arrays into Arango.",
            "text_hash": canonical_sha(canonical_doc.get("retrieval_text", "")),
            "target_qdrant_collection_hint": "persona_memory",
        },
    }

    canonical_write_proof: dict[str, Any] | None = None
    canonical_dream_memory_written = False
    if allowed:
        # Guarded canonical live-write path. Only reachable for a non-superseded,
        # non-historical, non-defect return whose DEGRADED status (if any) is
        # certified by a binding agent-level acceptance receipt.
        canonical_write_proof = persist_canonical(
            canonical_doc, interpretation, tom, watch_vertices, base_url,
            dream_id=dream_id, return_id=return_id, packet=packet,
            phase13_sha=phase13_sha, phase14_sha=phase14_sha,
        )
        canonical_writes_performed = canonical_write_proof["records_written"]
        # CORRECTNESS gate (Defect 2): presence of a proof object is NOT proof.
        # Require staging AND publish AND commit-manifest reread all match.
        manifest = canonical_write_proof.get("commit_manifest") or {}
        canonical_dream_memory_written = bool(
            canonical_write_proof.get("all_exact_reread_match")
            and manifest.get("exact_reread_match")
            and manifest.get("active")
        )
    else:
        canonical_writes_performed = 0

    # Validation-collection real write proof (non-canonical, permitted).
    validation_proof: dict[str, Any] | None = None
    if validation_collection:
        vcol = validation_collection
        vdoc = build_dream_memory_document(
            dream_id, revision_id, run_id, persona_id, packet, interpretation, tom,
            key_prefix="validation_",
        )
        vdoc["validation_scope"] = vcol
        vdoc["canonical"] = False
        write_receipts = [store_and_reread(vdoc, vcol, base_url)]
        # Also prove the edge descriptors persist as documents in the validation collection.
        vedges = build_graph_edges(vdoc, interpretation, tom, vcol, vcol, vcol)
        for e in vedges:
            ed = dict(e["document"])
            ed["canonical"] = False
            ed["validation_scope"] = vcol
            write_receipts.append(store_and_reread(ed, vcol, base_url))
        validation_proof = {
            "collection": vcol,
            "canonical": False,
            "documents_written": len(write_receipts),
            "all_exact_reread_match": all(r["exact_reread_match"] for r in write_receipts),
            "receipts": write_receipts,
        }

    dry_run = not allowed
    if dry_run:
        status = "DRY_RUN_PERSISTENCE_PLAN"
    elif canonical_dream_memory_written:
        status = "LIVE_CANONICAL_PERSISTENCE"
    else:
        # Canonical write was permitted and attempted but staging / publish /
        # commit-manifest verification did not all pass. Fail closed.
        status = "BLOCKED_CANONICAL_PERSISTENCE_INCOMPLETE"
    if validation_proof:
        status += "_WITH_VALIDATION_WRITE"

    receipt = {
        "schema": "persona_dream.dream_persistence_receipt.v1",
        "status": status,
        "dream_id": dream_id,
        "revision_id": revision_id,
        "run_id": run_id,
        "persona_id": persona_id,
        "owner": "memory",
        "transport": "memory_http_api",
        "direct_arango_writes_allowed": False,
        "direct_qdrant_writes_allowed": False,
        "return_id": return_id,
        "canonical_write_requested": bool(allow_canonical_write),
        "canonical_write_allowed": allowed,
        "canonical_write_blockers": blockers,
        "canonical_writes_performed": canonical_writes_performed,
        "canonical_dream_memory_written": canonical_dream_memory_written,
        "commit_manifest_key": ((canonical_write_proof or {}).get("commit_manifest") or {}).get("key"),
        "idempotency_key": (canonical_write_proof or {}).get("idempotency_key"),
        "acceptance_basis": {
            "acceptance_receipt_path": str(acceptance_receipt_path) if acceptance_receipt_path else None,
            "acceptance_receipt_sha256": canonical_sha(acceptance_receipt) if acceptance_receipt else None,
            "certifies_return_for_canonical_write": acceptance_certifies,
            "acceptance_reasons": acceptance_reasons,
        },
        "canonical_plan": canonical_plan,
        "canonical_write_proof": canonical_write_proof,
        "validation_write_proof": validation_proof,
        "relationship_vocabulary": ["derived_from", "observed_in_scene", "supports_interpretation"],
        "mocked": False,
        "generated_at": utc_now(),
    }
    return receipt


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--observation", type=Path, required=True)
    p.add_argument("--interpretation", type=Path, required=True)
    p.add_argument("--tom", type=Path, required=True)
    p.add_argument("--dream-id", required=True)
    p.add_argument("--revision-id", required=True)
    p.add_argument("--run-id", required=True)
    p.add_argument("--persona-id", default="embry")
    p.add_argument("--dry-run", action="store_true", default=True, help="Default. Plan only, zero canonical writes.")
    p.add_argument("--allow-canonical-write", action="store_true",
                   help="Required for a canonical write; still hard-fails on a superseded return.")
    p.add_argument("--return-id", default=None, help="Non-superseded return id required for a canonical write.")
    p.add_argument("--acceptance-receipt", type=Path, default=None,
                   help="Agent-level acceptance receipt (ACCEPTED_AGENT_LEVEL) that certifies this "
                        "return and permits overriding a DEGRADED observation status, fail-closed.")
    p.add_argument("--superseded-return-ids", default=None,
                   help="Comma-separated return ids that are superseded and must never be written.")
    p.add_argument("--validation-collection", default=None,
                   help=f"Real write proof into a non-canonical collection (e.g. {VALIDATION_COLLECTION}).")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    superseded = (
        {s.strip() for s in args.superseded_return_ids.split(",") if s.strip()}
        if args.superseded_return_ids else None
    )
    result = run_phase15(
        args.observation, args.interpretation, args.tom, args.dream_id, args.revision_id,
        args.run_id, args.persona_id, allow_canonical_write=args.allow_canonical_write,
        return_id=args.return_id, validation_collection=args.validation_collection,
        acceptance_receipt_path=args.acceptance_receipt, superseded_return_ids=superseded,
    )

    # Hard-fail if a canonical write was requested but blocked by supersession.
    if args.allow_canonical_write and not result["canonical_write_allowed"]:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.output, result)
        raise SystemExit(
            "BLOCKED_CANONICAL_WRITE_ON_SUPERSEDED_RETURN: " + ",".join(result["canonical_write_blockers"])
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)

    # Hard-fail if a canonical write was permitted+attempted but did not fully
    # verify (staging / publish / commit-manifest reread). Exit 0 must NEVER be
    # returned on a semantically incomplete canonical result (Defect 2).
    if args.allow_canonical_write and result["canonical_write_allowed"] and not result["canonical_dream_memory_written"]:
        if args.json:
            print(json.dumps({"status": result["status"], "canonical_dream_memory_written": False}, indent=2))
        raise SystemExit("BLOCKED_CANONICAL_PERSISTENCE_INCOMPLETE: " + result["status"])

    if args.json:
        summary = {
            "status": result["status"],
            "canonical_write_allowed": result["canonical_write_allowed"],
            "canonical_writes_performed": result["canonical_writes_performed"],
            "canonical_dream_memory_written": result["canonical_dream_memory_written"],
            "validation_write": bool(result["validation_write_proof"]),
            "output": str(args.output),
        }
        if result["canonical_write_proof"]:
            summary["canonical_all_match"] = result["canonical_write_proof"]["all_exact_reread_match"]
            summary["canonical_node_keys"] = result["canonical_write_proof"]["node_keys"]
            summary["canonical_edge_keys"] = result["canonical_write_proof"]["edge_keys"]
            summary["canonical_watch_vertex_keys"] = result["canonical_write_proof"].get("watch_vertex_keys", [])
            summary["idempotency_key"] = result["canonical_write_proof"].get("idempotency_key")
        if result["validation_write_proof"]:
            summary["validation_all_match"] = result["validation_write_proof"]["all_exact_reread_match"]
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
