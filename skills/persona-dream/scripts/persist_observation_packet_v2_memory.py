#!/usr/bin/env python3
"""Persist the governance record for the v2 observation packet build through the
$memory HTTP contract, with write + exact reread proof.

GOVERNANCE record (persona_dream_governance collection) - not canonical dream
memory. Records the single accepted successor observation packet, its supersedes
hash, and the one-packet-one-authority rule. Reads the final packet to derive the
authoritative hashes/stats so the record cannot drift from the artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MEMORY_BASE_URL = "http://127.0.0.1:8601"
COLLECTION = "persona_dream_governance"


def canonical_sha(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(MEMORY_BASE_URL + path, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20.0) as resp:
        return json.loads(resp.read())


def store_and_reread(doc: dict[str, Any], collection: str) -> dict[str, Any]:
    authored = {k: v for k, v in doc.items() if not k.startswith("_") or k == "_key"}
    written_sha = canonical_sha(authored)
    _post("/store", {"document": doc, "collection": collection})
    reread = _post("/list", {"collection": collection, "limit": 5, "filters": {"_key": doc["_key"]}})
    docs = reread.get("documents") or reread.get("items") or []
    match, reread_sha = False, None
    for d in docs:
        if d.get("_key") == doc["_key"]:
            subset = {k: d.get(k) for k in authored}
            reread_sha = canonical_sha(subset)
            match = reread_sha == written_sha
            break
    return {"collection": collection, "key": doc["_key"], "written_sha256": written_sha,
            "reread_sha256": reread_sha, "exact_reread_match": match}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--packet", type=Path, required=True)
    args = ap.parse_args()

    packet_path = args.packet
    packet = json.loads(packet_path.read_text())
    packet_sha = sha256_file(packet_path)
    now = datetime.now(timezone.utc).isoformat()

    vef = packet.get("visible_entities_per_frame", {})
    vc = packet.get("vertex_consistency", {})
    outcomes = sorted({v.get("outcome") for v in vc.get("vertices", [])})

    doc = {
        "_key": "persona_dream_observation_packet_v2_20260719",
        "kind": "governance_lesson",
        "problem": (
            "Two incompatible phase-12 observation notions existed (scene-driven "
            "watch_gauntlet_observation_packet.v1 vs fixed-lane dream_observation_packet.v1), and the accepted "
            "successor return's packet was DEGRADED: no per-frame VLM entities (vlm-chutes 401), no transcript "
            "(pre-mux silent video). Identity/audio verdicts lived scattered across step-36/37/38 receipts."
        ),
        "solution": (
            "Authored dream_observation_packet.v2.schema.json: an evidence-only, typed-optional-module packet "
            "(source identity, provider lineage, sampled_frames [variable count], scene_cuts, transcript, "
            "nonverbal_audio, visible_entities_per_frame, absences, identity_evidence, speaker_visibility, "
            "continuity_adjudications, coverage_gaps, acceptance_context, vertex_consistency). No silent-video "
            "assumption, no fixed frame count, psychological interpretation FORBIDDEN (const false + deterministic "
            "psychology filter). build_observation_packet_v2.py assembled the ONE ACCEPTED successor packet: "
            f"{vef.get('module_status')} per-frame visible entities over {len(vef.get('frames', []))} frames via the "
            "Tau panel-reviewer VLM route (tau_vlm_review_adapter; docker:scillm-proxy; NO direct scillm), full-clip "
            "local Whisper large-v3-turbo transcript, and the authoritative step-36 ArcFace/adjudication + step-37/38 "
            "receipts folded by reference+hash. It supersedes the DEGRADED v1 (retained, by hash). All 7 materialized "
            f"persona_dream_watch_evidence vertices are representable in the modules (outcomes: {outcomes}); enrichment "
            "beyond a vertex is recorded as additive delta, NOT a rewrite of the read-only canonical vertex."
        ),
        "rule": "ONE PACKET, ONE AUTHORITY: exactly one ACCEPTED successor observation packet per return; the prior packet is marked superseded by hash and never deleted; canonical watch-evidence vertices are read-only.",
        "packet_path": str(packet_path.relative_to(packet_path.parents[7]) if len(packet_path.parents) > 7 else packet_path),
        "packet_sha256": packet_sha,
        "packet_status": packet.get("packet_status"),
        "supersedes_sha256": packet.get("supersedes", {}).get("prior_packet_sha256"),
        "per_frame_vlm_count": len(vef.get("frames", [])),
        "psychology_rejected": len(vef.get("rejected_by_psychology_filter", [])),
        "transcript_segments": len(packet.get("transcript", {}).get("segments", [])),
        "tau_receipt_count": len(packet.get("tau_receipts", [])),
        "vertex_consistency_outcomes": outcomes,
        "tags": ["persona-dream", "observation-packet-v2", "governance", "evidence-only", "tau-vlm-route",
                 "whisper-transcript", "supersession", "watch-evidence-vertices", "one-packet-one-authority"],
        "scope": "persona-dream",
        "created_at": now,
    }

    proof = store_and_reread(doc, COLLECTION)
    out = {"schema": "persona_dream.observation_packet_v2_memory_governance.v1",
           "all_exact_reread_match": proof["exact_reread_match"], "proof": proof, "generated_at": now}
    print(json.dumps(out, indent=2))
    return 0 if proof["exact_reread_match"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
