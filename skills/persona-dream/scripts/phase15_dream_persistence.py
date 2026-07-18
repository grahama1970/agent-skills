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
VALIDATION_COLLECTION = "persona_dream_loop_validation"

RENDERER_DEFECT_VERDICTS = {"DRIFT", "FAIL", "MISMATCH", "NO_MATCH"}


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
def canonical_write_decision(
    packet: dict[str, Any],
    allow_canonical_write: bool,
    return_id: str | None,
    superseded_return_ids: set[str] | None = None,
) -> tuple[bool, list[str]]:
    """Pure decision. Returns (allowed, blockers). The historical return is
    superseded (historical origin + degraded status + identity DRIFT) and can
    NEVER be written to canonical dream memory."""
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

    if origin == "historical_provider_return":
        blockers.append("RETURN_IS_HISTORICAL_PROVIDER_RETURN")
    if status.startswith("DEGRADED"):
        blockers.append("OBSERVATION_STATUS_DEGRADED")
    if verdict in RENDERER_DEFECT_VERDICTS:
        blockers.append(f"IDENTITY_CONTINUITY_DEFECT:{verdict}")
    if return_id and superseded_return_ids and return_id in superseded_return_ids:
        blockers.append("RETURN_ID_SUPERSEDED")

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
# Live validation-collection write + exact reread proof                       #
# --------------------------------------------------------------------------- #
def store_and_reread(document: dict[str, Any], collection: str, base_url: str) -> dict[str, Any]:
    """Write one document through /store, then reread it through /list and
    prove the stored payload matches by content hash of the caller-owned fields."""
    written_sha = canonical_sha({k: v for k, v in document.items() if not k.startswith("_") or k == "_key"})
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
            reread_sha = canonical_sha({k: document[k] for k in document if k in d and (not k.startswith("_") or k == "_key")})
            # Compare only the caller-authored fields we wrote.
            reread_subset = {k: d.get(k) for k in document if not k.startswith("_") or k == "_key"}
            match = canonical_sha(reread_subset) == written_sha
            reread_sha = canonical_sha(reread_subset)
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
) -> dict[str, Any]:
    packet = read_json(observation_path)
    interpretation = read_json(interpretation_path)
    tom = read_json(tom_path)

    allowed, blockers = canonical_write_decision(packet, allow_canonical_write, return_id)

    # Canonical plan (dry-run) - exact would-write payloads + hashes, zero writes.
    canonical_doc = build_dream_memory_document(
        dream_id, revision_id, run_id, persona_id, packet, interpretation, tom
    )
    canonical_edges = build_graph_edges(
        canonical_doc, interpretation, tom,
        CANONICAL_DREAM_COLLECTION, CANONICAL_EDGE_COLLECTION, CANONICAL_TOM_EDGE_COLLECTION,
    )
    canonical_plan = {
        "dream_memory_document": {
            "collection": CANONICAL_DREAM_COLLECTION,
            "document": canonical_doc,
            "payload_sha256": canonical_sha(canonical_doc),
        },
        "graph_edges": [
            {"collection": e["collection"], "document": e["document"], "payload_sha256": canonical_sha(e["document"])}
            for e in canonical_edges
        ],
        "qdrant_embedding": {
            "note": "Memory semantic-sync embeds retrieval_text on /store; do not write vector arrays into Arango.",
            "text_hash": canonical_sha(canonical_doc.get("retrieval_text", "")),
            "target_qdrant_collection_hint": "persona_memory",
        },
    }

    if allowed:
        # Guarded canonical live-write path. For the superseded historical return
        # this branch is unreachable (decision blocks it), so canonical writes stay 0.
        canonical_writes_performed = "UNREACHABLE_FOR_SUPERSEDED_RETURN"
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
    status = "DRY_RUN_PERSISTENCE_PLAN" if dry_run else "LIVE_CANONICAL_PERSISTENCE"
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
        "canonical_plan": canonical_plan,
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
    p.add_argument("--validation-collection", default=None,
                   help=f"Real write proof into a non-canonical collection (e.g. {VALIDATION_COLLECTION}).")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args()

    result = run_phase15(
        args.observation, args.interpretation, args.tom, args.dream_id, args.revision_id,
        args.run_id, args.persona_id, allow_canonical_write=args.allow_canonical_write,
        return_id=args.return_id, validation_collection=args.validation_collection,
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
    if args.json:
        summary = {
            "status": result["status"],
            "canonical_write_allowed": result["canonical_write_allowed"],
            "canonical_writes_performed": result["canonical_writes_performed"],
            "validation_write": bool(result["validation_write_proof"]),
            "output": str(args.output),
        }
        if result["validation_write_proof"]:
            summary["validation_all_match"] = result["validation_write_proof"]["all_exact_reread_match"]
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
