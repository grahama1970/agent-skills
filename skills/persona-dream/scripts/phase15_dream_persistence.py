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
import copy
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
# Accepted phase-13 interpretation vertices (the epistemic ladder middle rung).
# Defect 4 fix: materialize interpretations as first-class vertices so the
# observation -> interpretation -> tom ladder resolves to real documents.
INTERPRETATION_COLLECTION = "persona_dream_interpretations"

# --------------------------------------------------------------------------- #
# Key namespacing (Defect 2: freeze-old / namespace-new).                      #
# dream-004's existing raw-key records are FROZEN; every NEW canonical write    #
# uses a namespaced key so the two schemes never collide and lineage is legible #
# in the key itself. Colons are valid ArangoDB _key characters.                 #
#   dream node : dream:<persona_id>:<dream_id>                                   #
#   watch      : dream:<persona_id>:<dream_id>:watch:<observation_id>           #
#   interp     : dream:<persona_id>:<dream_id>:interpretation:<interpretation_id>#
#   tom        : dream:<persona_id>:<dream_id>:tom:<candidate_id>               #
# --------------------------------------------------------------------------- #
def ns_prefix(persona_id: str, dream_id: str) -> str:
    return f"dream:{persona_id}:{dream_id}"


def ns_dream_key(persona_id: str, dream_id: str) -> str:
    return ns_prefix(persona_id, dream_id)


def ns_watch_key(persona_id: str, dream_id: str, observation_id: str) -> str:
    return f"{ns_prefix(persona_id, dream_id)}:watch:{observation_id}"


def ns_interpretation_key(persona_id: str, dream_id: str, interpretation_id: str) -> str:
    return f"{ns_prefix(persona_id, dream_id)}:interpretation:{interpretation_id}"


def ns_tom_key(persona_id: str, dream_id: str, candidate_id: str) -> str:
    return f"{ns_prefix(persona_id, dream_id)}:tom:{candidate_id}"
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
# Causal-family / lineage fields (Defect 6, schema-shaping).                   #
# Every NEW write-set record carries these fields, derived from the residue    #
# source ids in the dream lineage. The GMO agent consumes this field contract; #
# persona-dream only WRITES the fields (no GMO-side filtering here).           #
# visibility_state stays "pending"; activation flips the commit manifest only. #
# --------------------------------------------------------------------------- #
def causal_family_id(persona_id: str, dream_id: str, root_event_ids: list[str]) -> str:
    material = json.dumps(
        {"persona_id": persona_id, "dream_id": dream_id, "root_event_ids": sorted(root_event_ids)},
        sort_keys=True, separators=(",", ":"),
    ).encode()
    return f"cf_{hashlib.sha256(material).hexdigest()[:16]}"


def build_causal_family_fields(
    persona_id: str,
    dream_id: str,
    root_event_ids: list[str],
    commit_id: str,
    *,
    derivation_depth: int = 1,
    synthetic_depth: int = 1,
) -> dict[str, Any]:
    """Lineage fields shared with the Graph Memory Operator. root_event_ids are
    the residue source-memory ids the dream derives from; a synthetic dream sits
    one derivation hop above those real events (derivation_depth=1) and is one
    synthetic layer deep (synthetic_depth=1). independent_evidence_count is the
    count of distinct root events. visibility_state is 'pending' until the commit
    manifest activates."""
    roots = sorted({str(r) for r in root_event_ids if r})
    return {
        "root_event_ids": roots,
        "causal_family_id": causal_family_id(persona_id, dream_id, roots),
        "synthetic_depth": synthetic_depth,
        "derivation_depth": derivation_depth,
        "independent_evidence_count": len(roots),
        "commit_id": commit_id,
        "visibility_state": "pending",
    }


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
    dream_key: str | None = None,
    causal_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    accepted = interpretation.get("accepted_interpretations", [])
    tom_candidates = tom.get("accepted_tom_candidates", [])
    retrieval_text = " ".join(c.get("statement", "") for c in accepted).strip() or (
        f"Synthetic dream of {persona_id} derived from the grounded source-memory residue."
    )
    doc = {
        "_key": dream_key or f"{key_prefix}dream_{dream_id}",
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
        "created_at": deterministic_created_at(interpretation, packet),
    }
    if causal_fields:
        doc.update(causal_fields)
    return doc


def deterministic_created_at(interpretation: dict[str, Any], packet: dict[str, Any]) -> str:
    """Canonical payloads must be a pure function of immutable inputs so an
    identical retry authors a byte-identical document (webgpt review 2026-07-19:
    utc_now() here made every replay read as drift and quarantined the valid
    prior commit). Derive from the phase-13 artifact's own timestamp, else the
    observation packet's; fail closed rather than fall back to wall clock."""
    for source in (
        interpretation.get("created_at"),
        interpretation.get("generated_at"),
        packet.get("created_at"),
        packet.get("generated_at"),
        packet.get("observed_at"),
    ):
        if source:
            return str(source)
    raise ValueError(
        "deterministic_created_at: neither interpretation nor packet carries a "
        "created_at/generated_at; refusing volatile wall-clock in canonical payload"
    )


def build_graph_edges(
    dream_doc: dict[str, Any],
    interpretation: dict[str, Any],
    tom: dict[str, Any],
    dream_collection: str,
    edge_collection: str,
    tom_edge_collection: str,
    causal_fields: dict[str, Any] | None = None,
    namespaced_targets: bool = True,
) -> list[dict[str, Any]]:
    """Dream-level relationship edges (README vocabulary). Targets point at
    NAMESPACED vertices (Defect 2) except the frozen persona_memory source
    anchors, which keep their raw keys. The epistemic-ladder edges
    (observation -> interpretation -> tom) are added by build_ladder_edges."""
    persona_id = dream_doc.get("persona_id", "")
    dream_id = dream_doc.get("dream_id", "")
    dream_ref = f"{dream_collection}/{dream_doc['_key']}"
    cf = causal_fields or {}
    edges: list[dict[str, Any]] = []

    def _watch_target(obs_id: str) -> str:
        key = ns_watch_key(persona_id, dream_id, obs_id) if namespaced_targets else obs_id
        return f"{WATCH_EVIDENCE_COLLECTION}/{key}"

    def _tom_target(cid: str) -> str:
        key = ns_tom_key(persona_id, dream_id, cid) if namespaced_targets else str(cid)
        return f"{TOM_CANDIDATE_COLLECTION}/{key}"

    # dream --derived_from--> source memory (FROZEN raw anchor keys)
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
                **cf,
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
                "_to": _watch_target(obs_id),
                "relationship_type": "observed_in_scene",
                "watch_observation_id": obs_id,
                "synthetic_origin": True,
                **cf,
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
                "_to": _tom_target(cid),
                "relationship_type": "supports_interpretation",
                "tom_state_type": c.get("tom_state_type"),
                "confidence": c.get("confidence"),
                "emotional_intensity": c.get("emotional_intensity"),
                "synthetic_origin": True,
                "literal_historical_event": False,
                **cf,
            },
        })
    return edges


# --------------------------------------------------------------------------- #
# Interpretation vertices + epistemic-ladder edges (Defect 4).                 #
# --------------------------------------------------------------------------- #
def build_interpretation_vertices(
    interpretation: dict[str, Any],
    persona_id: str,
    dream_id: str,
    causal_fields: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Materialize each accepted phase-13 interpretation as a first-class vertex
    (namespaced key). Carries the full statement, confidence, uncertainty, the
    renderer (alternative) explanation, and the observation + source-memory
    citation ids - the middle rung of the observation -> interpretation -> tom
    epistemic ladder."""
    cf = causal_fields or {}
    vertices: list[dict[str, Any]] = []
    for c in interpretation.get("accepted_interpretations", []):
        interp_id = c.get("interpretation_id")
        if not interp_id:
            continue
        doc = {
            "_key": ns_interpretation_key(persona_id, dream_id, interp_id),
            "kind": "persona_dream_interpretation",
            "persona_id": persona_id,
            "dream_id": dream_id,
            "interpretation_id": interp_id,
            "tom_state_type": c.get("tom_state_type"),
            "subject": c.get("subject"),
            "target": c.get("target"),
            "statement": c.get("statement"),
            "confidence": c.get("confidence"),
            "uncertainty": c.get("uncertainty"),
            "emotional_intensity": c.get("emotional_intensity"),
            "renderer_alternative": c.get("alternative_explanation"),
            "favored_explanation": c.get("favored_explanation"),
            "cites_renderer_review": c.get("cites_renderer_review"),
            "observation_refs": list(c.get("observation_refs", [])),
            "source_memory_refs": list(c.get("source_memory_refs", [])),
            "synthetic_origin": True,
            "literal_historical_event": False,
            **cf,
        }
        vertices.append(doc)
    return vertices


def build_ladder_edges(
    interpretation: dict[str, Any],
    tom: dict[str, Any],
    persona_id: str,
    dream_id: str,
    causal_fields: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """The epistemic ladder (Defect 4): observation --grounds_interpretation-->
    interpretation --supports_interpretation--> tom. Preserves (does not replace)
    the dream-level edges built by build_graph_edges. Every endpoint is a
    namespaced vertex."""
    cf = causal_fields or {}
    edges: list[dict[str, Any]] = []
    interp_by_id = {c.get("interpretation_id"): c for c in interpretation.get("accepted_interpretations", [])}

    # observation --grounds_interpretation--> interpretation
    for interp_id, c in interp_by_id.items():
        if not interp_id:
            continue
        interp_ref = f"{INTERPRETATION_COLLECTION}/{ns_interpretation_key(persona_id, dream_id, interp_id)}"
        for obs_id in sorted(set(c.get("observation_refs", []))):
            watch_ref = f"{WATCH_EVIDENCE_COLLECTION}/{ns_watch_key(persona_id, dream_id, obs_id)}"
            edges.append({
                "collection": CANONICAL_EDGE_COLLECTION,
                "document": {
                    "_key": f"{ns_watch_key(persona_id, dream_id, obs_id)}__grounds_interpretation__{interp_id}",
                    "_from": watch_ref,
                    "_to": interp_ref,
                    "relationship_type": "grounds_interpretation",
                    "watch_observation_id": obs_id,
                    "interpretation_id": interp_id,
                    "synthetic_origin": True,
                    **cf,
                },
            })

    # interpretation --supports_interpretation--> tom candidate
    for cand in tom.get("accepted_tom_candidates", []):
        cid = cand.get("candidate_id")
        parent = cand.get("parent_interpretation_id")
        if not cid or not parent or parent not in interp_by_id:
            continue
        interp_ref = f"{INTERPRETATION_COLLECTION}/{ns_interpretation_key(persona_id, dream_id, parent)}"
        tom_ref = f"{TOM_CANDIDATE_COLLECTION}/{ns_tom_key(persona_id, dream_id, cid)}"
        edges.append({
            "collection": CANONICAL_TOM_EDGE_COLLECTION,
            "document": {
                "_key": f"{ns_interpretation_key(persona_id, dream_id, parent)}__supports_interpretation__{cid}",
                "_from": interp_ref,
                "_to": tom_ref,
                "relationship_type": "supports_interpretation",
                "interpretation_id": parent,
                "tom_candidate_id": cid,
                "tom_state_type": cand.get("tom_state_type"),
                "confidence": cand.get("confidence"),
                "synthetic_origin": True,
                "literal_historical_event": False,
                **cf,
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
    persona_id: str = "",
    causal_fields: dict[str, Any] | None = None,
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

        vertex = {
            "_key": ns_watch_key(persona_id, dream_id, obs_id),
            "kind": "persona_dream_watch_evidence",
            "persona_id": persona_id,
            "dream_id": dream_id,
            "observation_id": obs_id,
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
        }
        if causal_fields:
            vertex.update(causal_fields)
        vertices.append(vertex)
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
        {"collection": collection, "limit": 5, "filters": _reread_filters(document)},
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


def _reread_filters(document: dict[str, Any]) -> dict[str, Any]:
    """Reread filter for a just-written record. Including visibility_state
    engages GMO's documented admin bypass of the dream-class listing gate AND
    asserts the expected state (live fault proof 2026-07-19: without this the
    writer's own reread cannot see its pending records)."""
    f: dict[str, Any] = {"_key": document["_key"]}
    if document.get("visibility_state") is not None:
        f["visibility_state"] = document["visibility_state"]
    return f


def compute_idempotency_key(
    dream_id: str,
    return_id: str | None,
    packet: dict[str, Any],
    phase13_sha: str,
    phase14_sha: str,
    canonical_plan_sha256: str | None = None,
) -> str:
    """Deterministic write-set identity: same dream + return + phase13 + phase14
    always yields the same key, so a rerun is detectable and resumable.
    canonical_plan_sha256 binds the key to the COMPLETE deterministic write-set
    payload (webgpt review 2026-07-19: a key over a subset of inputs is
    semantically collision-prone). Optional only for legacy callers whose
    manifests predate the binding; persist_canonical always passes it."""
    material = {
        "dream_id": dream_id,
        "return_id": return_id,
        "return_video_sha256": packet.get("source_video_sha256"),
        "phase13_sha256": phase13_sha,
        "phase14_sha256": phase14_sha,
    }
    if canonical_plan_sha256:
        material["canonical_plan_sha256"] = canonical_plan_sha256
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_write_set(
    dream_doc: dict[str, Any],
    interpretation: dict[str, Any],
    tom: dict[str, Any],
    watch_vertices: list[dict[str, Any]],
    interpretation_vertices: list[dict[str, Any]] | None = None,
    causal_fields: dict[str, Any] | None = None,
    include_dream_node: bool = True,
    extra_edges: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Ordered, deterministic canonical write-set: dream node, ToM nodes, Watch
    evidence vertices, interpretation vertices (Defect 4), then every graph edge
    (dream-level edges + the observation->interpretation->tom ladder). Each entry
    is {collection, document, kind}. All NEW records use namespaced keys and
    carry the causal-family fields (Defect 2 + Defect 6)."""
    persona_id = dream_doc.get("persona_id", "")
    dream_id = dream_doc.get("dream_id", "")
    interpretation_vertices = interpretation_vertices or []
    ws: list[dict[str, Any]] = []
    if include_dream_node:
        # Revision bundles (GOAL_V2 P0.2) reference the existing dream-event
        # node without rewriting it: one dream event per media hash, versioned
        # derived evidence (PROV wasRevisionOf design).
        ws.append({"collection": CANONICAL_DREAM_COLLECTION, "document": dream_doc, "kind": "dream_node"})
    for cand in tom.get("accepted_tom_candidates", []):
        cid = cand.get("candidate_id")
        if not cid:
            continue
        cand_doc = {
            **cand,
            "_key": ns_tom_key(persona_id, dream_id, cid),
            "candidate_id": cid,
            "synthetic_origin": True,
            "literal_historical_event": False,
        }
        if causal_fields:
            cand_doc.update(causal_fields)
        ws.append({"collection": TOM_CANDIDATE_COLLECTION, "document": cand_doc, "kind": "tom_node"})
    for v in interpretation_vertices:
        ws.append({"collection": INTERPRETATION_COLLECTION, "document": v, "kind": "interpretation_vertex"})
    for v in watch_vertices:
        ws.append({"collection": WATCH_EVIDENCE_COLLECTION, "document": v, "kind": "watch_vertex"})
    if include_dream_node:
        # Dream-level fact edges belong to the founding lineage; a revision
        # bundle (include_dream_node=False) carries only versioned cognition
        # (ladder + supersedes edges) and must not rewrite v1 fact edges.
        for e in build_graph_edges(
            dream_doc, interpretation, tom,
            CANONICAL_DREAM_COLLECTION, CANONICAL_EDGE_COLLECTION, CANONICAL_TOM_EDGE_COLLECTION,
            causal_fields=causal_fields,
        ):
            ws.append({"collection": e["collection"], "document": e["document"], "kind": "edge"})
    for e in build_ladder_edges(interpretation, tom, persona_id, dream_id, causal_fields=causal_fields):
        ws.append({"collection": e["collection"], "document": e["document"], "kind": "edge"})
    for e in (extra_edges or []):
        ws.append({"collection": e["collection"], "document": e["document"], "kind": e.get("kind", "edge")})
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
        {"collection": STAGING_COLLECTION, "limit": 3, "filters": _reread_filters(staged_doc)},
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
    # active ONLY when every publication reread matched (webgpt review
    # 2026-07-19: an unconditional active flag lets a partial write set become
    # visible through the sole visibility authority). A failed set writes a
    # quarantined, inactive manifest — a terminal readable state, never active.
    manifest_active = bool(all_published and staging_all_match and record_index)
    manifest_doc = {
        "_key": f"commit_{idempotency_key}",
        "kind": "persona_dream_commit_manifest",
        "schema": "persona_dream.canonical_commit_manifest.v1",
        "idempotency_key": idempotency_key,
        "dream_id": dream_id,
        "return_id": return_id,
        "phase13_sha256": phase13_sha,
        "phase14_sha256": phase14_sha,
        "active": manifest_active,
        "quarantined": not manifest_active,
        "quarantine_reason": None if manifest_active else "PUBLICATION_REREAD_MISMATCH",
        "retroactive_commit": bool(retroactive),
        "justification": justification,
        "staging_all_exact_reread_match": staging_all_match,
        "published_all_exact_reread_match": all_published,
        "record_count": len(record_index),
        "record_index": record_index,
        "committed_at": utc_now(),
    }
    receipt = store_and_reread(manifest_doc, COMMIT_MANIFEST_COLLECTION, base_url)
    if manifest_active and not receipt["exact_reread_match"]:
        # The manifest's own reread failed: it must not remain stored active
        # (webgpt re-assess 2026-07-19). Compensating inactive write, then
        # report inactive regardless of the compensation outcome.
        manifest_active = False
        compensator = {
            **manifest_doc,
            "active": False,
            "quarantined": True,
            "quarantine_reason": "MANIFEST_REREAD_MISMATCH",
            "quarantined_at": utc_now(),
        }
        # The compensating inactive write must itself be exactly reread before
        # the operation terminates (webgpt round-3); its outcome is reported,
        # and active stays False regardless.
        compensation = store_and_reread(compensator, COMMIT_MANIFEST_COLLECTION, base_url)
        compensation_reread_match = bool(compensation["exact_reread_match"])
    else:
        compensation_reread_match = None
    return {
        "key": manifest_doc["_key"],
        "active": manifest_active,
        "compensation_reread_match": compensation_reread_match,
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


def validate_edge_closure(
    write_set: list[dict[str, Any]], base_url: str
) -> list[str]:
    """GOAL_V3.2 reliability gate (round-1 review hardening): every edge must
    carry BOTH endpoints with valid 'collection/key' syntax; endpoints must
    resolve to VERTICES (never another edge) that are inside this write set or
    already stored with visibility active/legacy (pending/quarantined external
    endpoints block). Malformed references return deterministic unresolved
    entries, never raise."""
    in_set: dict[str, dict[str, Any]] = {
        f"{e['collection']}/{e['document']['_key']}": e["document"] for e in write_set
    }
    unresolved: list[str] = []
    def is_edge_entry(entry: dict[str, Any]) -> bool:
        d = entry["document"]
        return (entry.get("kind") == "edge" or "edge" in str(entry.get("collection", ""))
                or d.get("_from") is not None or d.get("_to") is not None)

    edge_keys = {f"{e['collection']}/{e['document']['_key']}"
                 for e in write_set if is_edge_entry(e)}
    for e in write_set:
        doc = e["document"]
        if not is_edge_entry(e):
            continue  # vertex by declared kind AND shape
        frm, to = doc.get("_from"), doc.get("_to")
        if not frm or not to:
            unresolved.append(f"{doc.get('_key')}->missing-endpoint")
            continue
        for endpoint in (frm, to):
            if not isinstance(endpoint, str) or endpoint.count("/") != 1                     or not all(endpoint.split("/", 1)):
                unresolved.append(f"{doc.get('_key')}->malformed:{endpoint!r}")
                continue
            if endpoint in edge_keys:
                unresolved.append(f"{doc.get('_key')}->edge-endpoint-is-edge:{endpoint}")
                continue
            if endpoint in in_set:
                continue
            coll, key = endpoint.split("/", 1)
            found_doc = None
            try:
                # unfiltered lookup, then EXPLICIT state check — acceptability
                # is never inferred from lookup visibility (round-2 review)
                got = _http_post(f"{base_url}/list",
                                 {"collection": coll,
                                  "filters": {"_key": key, "visibility_state": "active"}})
                docs = got.get("documents") or []
                if not docs:
                    got = _http_post(f"{base_url}/list",
                                     {"collection": coll, "filters": {"_key": key}})
                    docs = [d for d in (got.get("documents") or [])
                            if d.get("visibility_state") in (None, "active")]
                found_doc = docs[0] if docs else None
            except Exception:
                found_doc = None
            if found_doc is None:
                unresolved.append(f"{doc.get('_key')}->{endpoint}")
            elif found_doc.get("_from") or found_doc.get("_to"):
                unresolved.append(f"{doc.get('_key')}->edge-endpoint-is-edge:{endpoint}")
    return unresolved


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
    interpretation_vertices: list[dict[str, Any]] | None = None,
    causal_fields: dict[str, Any] | None = None,
    retroactive: bool = False,
    justification: str | None = None,
    include_dream_node: bool = True,
    extra_edges: list[dict[str, Any]] | None = None,
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
    write_set = build_write_set(
        dream_doc, interpretation, tom, watch_vertices,
        interpretation_vertices=interpretation_vertices, causal_fields=causal_fields,
        include_dream_node=include_dream_node, extra_edges=extra_edges,
    )
    # Deep-copy every document so stamping NEVER mutates caller-held dicts
    # (webgpt round-3: the returned plan embedded live references that were
    # mutated after their hashes were recorded).
    write_set = [{**e, "document": copy.deepcopy(e["document"])} for e in write_set]
    unresolved_endpoints = validate_edge_closure(write_set, base_url)
    if unresolved_endpoints:
        return {
            "status": "BLOCKED_EDGE_ENDPOINT_UNRESOLVED",
            "all_exact_reread_match": False,
            "commit_manifest": None,
            "unresolved_endpoints": unresolved_endpoints[:20],
            "detail": "write set would create dangling citation edges; "
                      "supply the missing vertices (e.g. build_watch_evidence_vertices)",
        }
    expected_count = len(write_set)
    # SINGLE TRANSACTION IDENTITY (webgpt re-assess 2026-07-19): derive the
    # plan-bound key over the commit-id-less write set, THEN stamp the derived
    # commit id into every record, so records' commit_id == manifest _key ==
    # proof key. The plan hash excludes the commit_id field itself (it is a
    # function of the plan, not part of it).
    canonical_plan_sha256 = canonical_sha(
        [
            _normalize_numbers({k: v for k, v in e["document"].items() if k != "commit_id"})
            for e in write_set
        ]
    )
    idempotency_key = compute_idempotency_key(
        dream_id, return_id, packet, phase13_sha, phase14_sha,
        canonical_plan_sha256=canonical_plan_sha256,
    )
    final_commit_id = f"commit_{idempotency_key}"
    for e in write_set:
        e["document"]["commit_id"] = final_commit_id
    # Post-stamp contract assertion: every canonical record carries the final
    # bound identity + visibility contract (legacy-null bypass hardening).
    if not retroactive:
        naked = [
            e["document"].get("_key")
            for e in write_set
            if e["document"].get("commit_id") != final_commit_id
            or not e["document"].get("visibility_state")
        ]
        if naked:
            raise ValueError(
                f"canonical write-set records missing bound commit_id/visibility_state: {naked[:5]}"
            )
    # THE immutable final-stamped snapshot: sole source for the returned plan,
    # staging, publication, proof, and manifest (webgpt round-3 gate).
    final_write_set_snapshot = [
        {
            "collection": e["collection"],
            "kind": e["kind"],
            "key": e["document"].get("_key"),
            "document": copy.deepcopy(e["document"]),
            "payload_sha256": authored_sha(e["document"]),
        }
        for e in write_set
    ]

    # --- Detect on rerun: resume WITHOUT re-staging/re-publishing ----------
    prior = existing_commit_manifest(idempotency_key, base_url)
    resumed = False
    quarantine: dict[str, Any] | None = None
    if prior is not None:
        # Re-verify every published record still rereads exactly.
        reverify = []
        for entry in write_set:
            r = store_and_reread_check_only(entry["document"], entry["collection"], base_url)
            reverify.append(r)
        # ACTIVE_MANIFEST_REPLAY_VALIDATION (webgpt round-4): resume only when
        # the prior manifest's complete binding matches the final stamped
        # snapshot — identity, phase hashes, state, count, and full
        # (collection, key, payload_sha256) index.
        expected_index = {
            (s["collection"], s["key"]): s["payload_sha256"]
            for s in final_write_set_snapshot
        }
        prior_index = {
            (r.get("collection"), r.get("key")): r.get("payload_sha256")
            for r in (prior.get("record_index") or [])
        }
        manifest_binding_valid = (
            prior.get("idempotency_key") == idempotency_key
            and prior.get("phase13_sha256") == phase13_sha
            and prior.get("phase14_sha256") == phase14_sha
            and prior.get("active") is True
            and not prior.get("quarantined")
            and prior.get("record_count") == expected_count
            and prior_index == expected_index
        )
        if (
            manifest_binding_valid
            and all(r["exact_reread_match"] for r in reverify)
            and len(reverify) == expected_count
        ):
            # Identical retry: the committed write set is intact. Return the
            # existing commit untouched (webgpt review 2026-07-19: replay must
            # resolve to the existing active commit, never quarantine it, and
            # must not rewrite records).
            return {
                "idempotency_key": idempotency_key,
                "final_commit_id": final_commit_id,
                "canonical_plan_sha256": canonical_plan_sha256,
                "final_write_set_snapshot": final_write_set_snapshot,
                "records_written": 0,
                "expected_record_count": expected_count,
                "all_exact_reread_match": True,
                "staging_all_exact_reread_match": True,
                "publish_all_exact_reread_match": True,
                "resumed_from_prior_commit": True,
                "quarantine": None,
                "node_keys": [], "edge_keys": [], "watch_vertex_keys": [],
                "interpretation_vertex_keys": [], "tom_node_keys": [],
                "node_receipts": [], "edge_receipts": [],
                "watch_vertex_receipts": [], "interpretation_vertex_receipts": [],
                "staging_proof": {"resumed": True, "reverified_count": len(reverify)},
                "commit_manifest": {
                    "key": f"commit_{idempotency_key}",
                    "active": bool(prior.get("active")),
                    "resumed": True,
                    "published_all_exact_reread_match": bool(
                        prior.get("published_all_exact_reread_match")
                    ),
                    "exact_reread_match": True,
                    "prior_manifest": prior,
                },
            }
        else:
            missing = [r["key"] for r in reverify if not r["exact_reread_match"]]
            quarantine = {
                "idempotency_key": idempotency_key,
                "reason": (
                    "PRIOR_MANIFEST_BINDING_MISMATCH"
                    if not manifest_binding_valid
                    else "PRIOR_MANIFEST_WITH_INCOMPLETE_OR_DRIFTED_RECORDS"
                ),
                "manifest_binding_valid": manifest_binding_valid,
                "unverified_keys": missing,
            }
            # Verified inactive quarantine (webgpt round-4): the quarantining
            # write is itself exactly reread.
            quarantine_doc = {
                "_key": f"commit_{idempotency_key}",
                **prior,
                "active": False,
                "quarantined": True,
                "quarantine": quarantine,
                "quarantined_at": utc_now(),
            }
            q_receipt = store_and_reread(quarantine_doc, COMMIT_MANIFEST_COLLECTION, base_url)
            quarantine["quarantine_reread_match"] = bool(q_receipt["exact_reread_match"])

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
    interpretation_receipts: list[dict[str, Any]] = []
    commit_manifest: dict[str, Any] | None = None
    all_publish_receipts: list[dict[str, Any]] = []

    # --- Publish (only if staging fully verified and not quarantined) ------
    if staging_all_match and quarantine is None:
        # Conditional publication (webgpt round-3): never overwrite a record
        # owned by a DIFFERENT commit. Absent or same-commit records only.
        foreign: list[dict[str, Any]] = []
        for entry in write_set:
            key = entry["document"].get("_key")
            docs = []
            for vs in ("pending", "active", "quarantined"):
                existing = _http_post(
                    f"{base_url.rstrip('/')}/list",
                    {"collection": entry["collection"], "limit": 2,
                     "filters": {"_key": key, "visibility_state": vs}},
                )
                docs += existing.get("documents") or existing.get("items") or []
            # Legacy-null records are visible without the bypass:
            existing = _http_post(
                f"{base_url.rstrip('/')}/list",
                {"collection": entry["collection"], "limit": 2, "filters": {"_key": key}},
            )
            docs += [
                d for d in (existing.get("documents") or existing.get("items") or [])
                if d.get("_key") not in {x.get("_key") for x in docs}
            ]
            for d in docs:
                if d.get("commit_id") != final_commit_id:
                    foreign.append(
                        {"collection": entry["collection"], "key": key,
                         "owner_commit_id": d.get("commit_id")}
                    )
        if foreign:
            quarantine = {
                "idempotency_key": idempotency_key,
                "reason": "FOREIGN_COMMIT_OWNERSHIP",
                "foreign_records": foreign[:10],
            }
    if staging_all_match and quarantine is None:
        for entry in write_set:
            r = store_and_reread(entry["document"], entry["collection"], base_url)
            all_publish_receipts.append({**r, "record_kind": entry["kind"]})
            if entry["kind"] == "edge":
                edge_receipts.append(r)
            elif entry["kind"] == "watch_vertex":
                watch_receipts.append(r)
            elif entry["kind"] == "interpretation_vertex":
                interpretation_receipts.append(r)
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
        "final_commit_id": final_commit_id,
        "canonical_plan_sha256": canonical_plan_sha256,
        "final_write_set_snapshot": final_write_set_snapshot,
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
        "interpretation_vertex_keys": [r["key"] for r in interpretation_receipts],
        "tom_node_keys": [
            ns_tom_key(dream_doc.get("persona_id", ""), dream_id, c.get("candidate_id"))
            for c in tom.get("accepted_tom_candidates", []) if c.get("candidate_id")
        ],
        "node_receipts": node_receipts,
        "edge_receipts": edge_receipts,
        "watch_vertex_receipts": watch_receipts,
        "interpretation_vertex_receipts": interpretation_receipts,
        "staging_proof": staging_proof,
        "commit_manifest": commit_manifest,
    }


def store_and_reread_check_only(document: dict[str, Any], collection: str, base_url: str) -> dict[str, Any]:
    """Reread-and-verify WITHOUT writing (used on rerun detection)."""
    written_sha = authored_sha(document)
    reread = _http_post(
        f"{base_url.rstrip('/')}/list",
        {"collection": collection, "limit": 5, "filters": _reread_filters(document)},
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

    # Causal-family / lineage fields (Defect 6): root events are the residue
    # source-memory ids the dream derives from. commit_id is NOT stamped here —
    # persist_canonical is the sole transaction-identity authority and stamps
    # the final plan-bound commit id into every record (webgpt re-assess
    # 2026-07-19: a K0 stamped pre-derivation while the manifest publishes
    # under plan-bound K1 breaks key propagation).
    root_event_ids = sorted({
        str(b.get("source_id")) for b in interpretation.get("source_memory_bindings", []) if b.get("source_id")
    })
    causal_fields = build_causal_family_fields(persona_id, dream_id, root_event_ids, None)

    # tau step-36 adjudication receipt hash for Watch-evidence provenance.
    adjudication_receipt_sha256 = None
    if acceptance_receipt is not None:
        adjudication_receipt_sha256 = canonical_sha(acceptance_receipt)

    # Canonical plan (dry-run) - exact would-write payloads + hashes, zero writes.
    # NEW records use namespaced keys (Defect 2) and carry causal_fields (Defect 6).
    canonical_doc = build_dream_memory_document(
        dream_id, revision_id, run_id, persona_id, packet, interpretation, tom,
        dream_key=ns_dream_key(persona_id, dream_id), causal_fields=causal_fields,
    )
    interpretation_vertices = build_interpretation_vertices(
        interpretation, persona_id, dream_id, causal_fields=causal_fields
    )
    canonical_edges = build_graph_edges(
        canonical_doc, interpretation, tom,
        CANONICAL_DREAM_COLLECTION, CANONICAL_EDGE_COLLECTION, CANONICAL_TOM_EDGE_COLLECTION,
        causal_fields=causal_fields,
    )
    ladder_edges = build_ladder_edges(
        interpretation, tom, persona_id, dream_id, causal_fields=causal_fields
    )
    watch_vertices = build_watch_evidence_vertices(
        packet, interpretation, dream_id, return_id, adjudication_receipt_sha256,
        persona_id=persona_id, causal_fields=causal_fields,
    )
    canonical_plan = {
        "dream_memory_document": {
            "collection": CANONICAL_DREAM_COLLECTION,
            "document": canonical_doc,
            "payload_sha256": canonical_sha(canonical_doc),
        },
        "interpretation_vertices": [
            {"collection": INTERPRETATION_COLLECTION, "document": v, "payload_sha256": canonical_sha(v)}
            for v in interpretation_vertices
        ],
        "watch_evidence_vertices": [
            {"collection": WATCH_EVIDENCE_COLLECTION, "document": v, "payload_sha256": canonical_sha(v)}
            for v in watch_vertices
        ],
        "graph_edges": [
            {"collection": e["collection"], "document": e["document"], "payload_sha256": canonical_sha(e["document"])}
            for e in (canonical_edges + ladder_edges)
        ],
        "key_namespace_policy": {
            "policy": "freeze-old/namespace-new",
            "dream_key": canonical_doc["_key"],
            "namespace_prefix": ns_prefix(persona_id, dream_id),
            "legacy_raw_keys_frozen": True,
        },
        "causal_family_fields": causal_fields,
        "transaction_identity": "BOUND_AT_PERSIST",
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
            interpretation_vertices=interpretation_vertices, causal_fields=causal_fields,
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
        # FINAL_TRANSACTION_SNAPSHOT_INTEGRITY (webgpt round-3): the returned
        # plan is derived from the ONE final-stamped snapshot that was staged,
        # published, and indexed by the manifest — never from pre-stamp dicts.
        snapshot = canonical_write_proof.get("final_write_set_snapshot") or []
        if snapshot:
            canonical_plan = {
                "schema": "persona_dream.canonical_persistence_plan.v2",
                "transaction_identity": canonical_write_proof.get("final_commit_id"),
                "idempotency_key": canonical_write_proof.get("idempotency_key"),
                "canonical_plan_sha256": canonical_write_proof.get("canonical_plan_sha256"),
                "records": [
                    {
                        "collection": s["collection"],
                        "kind": s["kind"],
                        "key": s["key"],
                        "document": s["document"],
                        "payload_sha256": s["payload_sha256"],
                    }
                    for s in snapshot
                ],
                "causal_family_fields": {
                    **causal_fields,
                    "commit_id": canonical_write_proof.get("final_commit_id"),
                },
                "phase13_sha256": phase13_sha,
                "phase14_sha256": phase14_sha,
            }
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
