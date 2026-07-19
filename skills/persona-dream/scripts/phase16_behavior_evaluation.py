#!/usr/bin/env python3
"""Phase 16 - Recall and Behavior Evaluation (persona-dream completion boundary).

Proves, against the FIRST canonical synthetic dream memory
(persona_memory/dream_dream_successor_943b01ecd9a3), the Phase 16 contract:

  (a) Qdrant/semantic recall retrieves the dream from differently-worded queries
      that never quote the record verbatim, with a negative control that must
      NOT return the dream.
  (b) ArangoDB reconstructs the multi-hop chain from the persona anchor
      through the dream to >=1 source memory, >=1 Watch observation, >=1 ToM node
      (actual vertex/edge keys recorded).
  (c) A later persona response, with context assembled ONLY from live Memory
      recall, uses the dream appropriately and marks it as a dream.
  (d) The persona distinguishes the dream from literal history; the canonical
      record's synthetic_origin / literal_historical_event flags reread exactly.
  (e) Identity-consistency: the dream did not mutate durable identity (the loop
      write-set is dream + edges + ToM only; source/identity records unchanged),
      plus a Tau-routed values/relationship stability Q&A.

Hard rules honored by this script:
  * All LLM calls route ONLY through the Tau text node
    (tau_coding.persona_dream_text_reasoning_agent) via
    tau_text_reasoning_adapter.dispatch_text_reasoning. NO direct scillm.
  * Reads + generate only. The canonical dream/persona/ToM records are NEVER
    mutated. New Memory writes are limited to phase-16 step/governance records.
  * Deterministic post-checks are CODE, not LLM self-report.
  * Fail closed: unimplemented / unreachable slices are listed in does_not_prove.

Usage:
    uv run python scripts/phase16_behavior_evaluation.py --json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PERSONA_DREAM = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
from tau_text_reasoning_adapter import (  # noqa: E402
    TauRoutingError,
    dispatch_text_reasoning,
    receipt_provenance,
)
import persona_dream_cognition_contract as _cognition_contract  # noqa: E402

MEMORY_BASE_URL = "http://127.0.0.1:8601"

# Every persona-specific string (persona id, counterpart ids, memory anchors,
# recall queries, evaluation vocabulary) comes from the cognition contract
# (Defect 5) - this source carries none. Swap the fixture to retarget the lane.
CONTRACT = _cognition_contract.load_contract()
_ANCHORS = CONTRACT["protected_identity_anchors"]
_P16 = CONTRACT["phase16"]
_RECALL = _P16["semantic_recall"]
_USERQ = _P16["user_questions"]
_PROMPT = _P16["persona_prompt"]

PERSONA_ID = CONTRACT["persona_id"]
PERSONA_DISPLAY_NAME = CONTRACT.get("persona_display_name", PERSONA_ID)
PRIMARY_COUNTERPART = _cognition_contract.primary_counterpart(CONTRACT)

DREAM_KEY = _P16["dream_key"]
DREAM_ID_FULL = f"persona_memory/{DREAM_KEY}"
REVISION_ID = _P16["revision_id"]
RUN_ID = _P16["run_id"]

SOURCE_MEMORY_IDS = list(_ANCHORS["source_memory_ids"])
LINEAGE_PROBE_MEMORY_ID = _ANCHORS.get("lineage_probe_memory_id", SOURCE_MEMORY_IDS[0])
SOURCE_MEMORY_KEY_PREFIX = _ANCHORS.get("source_memory_key_prefix", "")
WATCH_OBSERVATION_KEYS = list(_P16["watch_observation_keys"])
TOM_KEYS = list(_P16["tom_keys"])

DERIVED_FROM_EDGES = [
    (f"{DREAM_KEY}__derived_from__{m}", "persona_memory_edges", f"persona_memory/{m}", m)
    for m in SOURCE_MEMORY_IDS
]
OBSERVED_IN_SCENE_EDGES = [
    (f"{DREAM_KEY}__observed_in_scene__{w}", "persona_memory_edges", None, w)
    for w in WATCH_OBSERVATION_KEYS
]
SUPPORTS_INTERP_EDGES = [
    (f"{DREAM_KEY}__supports_interpretation__{t}", "tom_edges", f"tom_candidates/{t}", t)
    for t in TOM_KEYS
]

REVISION_TREE = (
    PERSONA_DREAM
    / "reports"
    / RUN_ID
    / ".persona-dream"
    / "revisions"
    / REVISION_ID
)
PHASE16_DIR = REVISION_TREE / "phase_16_behavior_evaluation"
COGNITIVE_LOOP_RECEIPT = (
    REVISION_TREE
    / "watch_gauntlet"
    / _P16.get("cognitive_loop_watch_dir", "")
    / "cognitive_loop"
    / "dream_persistence_receipt_canonical.json"
)

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_sha(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _post(path: str, payload: dict[str, Any], timeout: float = 40.0) -> dict[str, Any]:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        MEMORY_BASE_URL + path, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # expose error body for diagnosis
        return {"__http_error__": exc.code, "body": exc.read()[:300].decode("utf8", "ignore")}


def recall(q: str, k: int, collections: list[str], tags: list[str]) -> dict[str, Any]:
    return _post("/recall", {"q": q, "k": k, "collections": collections, "tags": tags})


def get_one(collection: str, key: str) -> dict[str, Any] | None:
    d = _post("/list", {"collection": collection, "limit": 2, "filters": {"_key": key}})
    for doc in d.get("documents", []) or []:
        if doc.get("_key") == key:
            return doc
    return None


def store_and_reread(doc: dict[str, Any], collection: str) -> dict[str, Any]:
    authored = {k: v for k, v in doc.items() if not k.startswith("_") or k == "_key"}
    written_sha = canonical_sha(authored)
    _post("/store", {"document": doc, "collection": collection})
    reread = _post("/list", {"collection": collection, "limit": 5, "filters": {"_key": doc["_key"]}})
    docs = reread.get("documents") or reread.get("items") or []
    match = False
    reread_sha = None
    for d in docs:
        if d.get("_key") == doc["_key"]:
            subset = {k: d.get(k) for k in authored}
            reread_sha = canonical_sha(subset)
            match = reread_sha == written_sha
            break
    return {
        "collection": collection,
        "key": doc["_key"],
        "written_sha256": written_sha,
        "reread_sha256": reread_sha,
        "exact_reread_match": match,
    }


def tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z]+", (text or "").lower()))


DREAM_MARKERS = set(_P16.get("dream_markers", []))
DREAM_CONTENT_TOKENS = set(_P16.get("dream_content_tokens", []))
LITERAL_ASSERTION_PATTERNS = list(_P16.get("literal_assertion_patterns", []))
NEGATE_LITERAL_TOKENS = set(_P16.get("negate_literal_tokens", []))
NEGATE_LITERAL_PHRASES = list(_P16.get("negate_literal_phrases", []))


# ---------------------------------------------------------------------------
# Probe A - recall
# ---------------------------------------------------------------------------


def probe_a_recall() -> dict[str, Any]:
    positive_queries = dict(_RECALL["positive_queries"])
    negative_query = dict(_RECALL["negative_query"])

    dream_text = tokens(_dream_retrieval_text())

    def run_query(name: str, q: str, negative: bool) -> dict[str, Any]:
        res = recall(q, k=10, collections=["persona_memory"], tags=[f"persona:{PERSONA_ID}"])
        items = res.get("items", []) or []
        rank = next((i for i, it in enumerate(items) if it.get("_key") == DREAM_KEY), None)
        scores = next(
            (it.get("scores") for it in items if it.get("_key") == DREAM_KEY), None
        )
        # verbatim guard: query must not quote the dream text verbatim
        q_toks = tokens(q)
        overlap = len(q_toks & dream_text) / max(1, len(q_toks))
        contains_verbatim = _dream_retrieval_text().lower()[:40] in q.lower()
        in_set = rank is not None
        if negative:
            passed = not in_set
        else:
            passed = in_set
        return {
            "name": name,
            "query": q,
            "negative_control": negative,
            "dream_rank": rank,
            "dream_in_returned_set": in_set,
            "dream_scores": scores,
            "n_items": len(items),
            "query_token_overlap_with_dream": round(overlap, 3),
            "quotes_dream_verbatim": contains_verbatim,
            "top3": [
                {"key": it.get("_key"), "dense": (it.get("scores") or {}).get("dense")}
                for it in items[:3]
            ],
            "passed": passed,
        }

    results = [run_query(n, q, False) for n, q in positive_queries.items()]
    results += [run_query(n, q, True) for n, q in negative_query.items()]
    passed = all(r["passed"] for r in results) and not any(
        r["quotes_dream_verbatim"] for r in results
    )
    return {
        "probe": "a_semantic_recall",
        "contract_item": 6,
        "passed": passed,
        "queries": results,
        "note": (
            "PASS requires all 3 differently-worded positive queries to return the dream in "
            "the returned set, the negative control to NOT return it, and no query to quote "
            "the dream text verbatim."
        ),
    }


_DREAM_CACHE: dict[str, Any] = {}


def _dream_record() -> dict[str, Any]:
    if "rec" not in _DREAM_CACHE:
        _DREAM_CACHE["rec"] = get_one("persona_memory", DREAM_KEY) or {}
    return _DREAM_CACHE["rec"]


def _dream_retrieval_text() -> str:
    return _dream_record().get("retrieval_text", "")


# ---------------------------------------------------------------------------
# Probe B - traversal
# ---------------------------------------------------------------------------


def probe_b_traversal() -> dict[str, Any]:
    dream = _dream_record()
    anchor_ok = dream.get("persona_id") == PERSONA_ID and f"persona:{PERSONA_ID}" in (
        dream.get("tags") or []
    )

    paths: list[dict[str, Any]] = []
    reachable = {"source_memory": [], "watch_observation": [], "tom_node": []}
    all_edges = (
        [(e, "derived_from", "source_memory") for e in DERIVED_FROM_EDGES]
        + [(e, "observed_in_scene", "watch_observation") for e in OBSERVED_IN_SCENE_EDGES]
        + [(e, "supports_interpretation", "tom_node") for e in SUPPORTS_INTERP_EDGES]
    )
    # STRICT resolver (Defect 3 fix): EVERY edge target must resolve to a real
    # stored vertex - including Watch-observation targets in
    # persona_dream_watch_evidence. An edge whose target vertex does not exist
    # FAILS traversal. The prior "vertex_class_not_materialized_as_document"
    # allowance proved edges, not vertices, and is removed.
    RESOLVABLE_COLLECTIONS = ("persona_memory", "tom_candidates", "persona_dream_watch_evidence")
    for (edge_key, edge_coll, target_full, target_key), rel, klass in all_edges:
        edge_doc = get_one(edge_coll, edge_key)
        edge_resolves = edge_doc is not None
        target_vertex = None
        target_resolves = None
        target_coll = None
        target_vertex_sha = None
        if edge_doc is not None:
            to_full = edge_doc.get("_to", "")
            target_coll = to_full.split("/")[0] if "/" in to_full else None
            tkey = to_full.split("/")[-1]
            if target_coll in RESOLVABLE_COLLECTIONS:
                target_vertex = get_one(target_coll, tkey)
                target_resolves = target_vertex is not None
                if target_vertex is not None:
                    authored = {k: v for k, v in target_vertex.items() if not k.startswith("_") or k == "_key"}
                    target_vertex_sha = canonical_sha(authored)
            else:
                # Unknown target collection: fail closed, do not assume reachable.
                target_resolves = False
        path = {
            "hop1_persona_anchor": f"persona_id={PERSONA_ID} (tag persona:{PERSONA_ID})",
            "hop2_dream_vertex": DREAM_ID_FULL,
            "edge_key": edge_key,
            "edge_collection": edge_coll,
            "relationship_type": rel,
            "edge_resolves_live": edge_resolves,
            "target_vertex_id": edge_doc.get("_to") if edge_doc else target_full,
            "target_collection": target_coll,
            "target_class": klass,
            "target_vertex_resolves_live": target_resolves,
            "target_vertex_sha256": target_vertex_sha,
        }
        paths.append(path)
        # A hop counts as reachable ONLY when both the edge AND its target vertex
        # resolve to real stored documents.
        if edge_resolves and target_resolves is True:
            reachable[klass].append(edge_doc.get("_to") if edge_doc else target_full)

    lineage_probe_reached = any(
        LINEAGE_PROBE_MEMORY_ID in (t or "") for t in reachable["source_memory"]
    )
    all_targets_resolve = all(p["target_vertex_resolves_live"] is True for p in paths)
    passed = (
        anchor_ok
        and len(reachable["source_memory"]) >= 1
        and lineage_probe_reached
        and len(reachable["watch_observation"]) >= 1
        and len(reachable["tom_node"]) >= 1
        and all(p["edge_resolves_live"] for p in paths)
        and all_targets_resolve
    )
    return {
        "probe": "b_multihop_traversal",
        "contract_item": 7,
        "passed": passed,
        "persona_anchor_ok": anchor_ok,
        "edges_total": len(paths),
        "edges_resolved_live": sum(1 for p in paths if p["edge_resolves_live"]),
        "target_vertices_resolved_live": sum(1 for p in paths if p["target_vertex_resolves_live"] is True),
        "all_target_vertices_resolve": all_targets_resolve,
        "reached_source_memories": reachable["source_memory"],
        "reached_watch_observations": reachable["watch_observation"],
        "reached_tom_nodes": reachable["tom_node"],
        "lineage_probe_reached": lineage_probe_reached,
        "lineage_probe_memory_id": LINEAGE_PROBE_MEMORY_ID,
        "paths": paths,
        "note": (
            "STRICT traversal: reconstructed from canonical stored edges via the sanctioned "
            "Memory HTTP API (/list by _key). Each edge AND its target vertex is re-fetched "
            "and hash-recorded live. Every target - source memories (persona_memory), ToM "
            "nodes (tom_candidates), AND Watch-observation vertices "
            "(persona_dream_watch_evidence) - must resolve to a real stored document; an edge "
            "with a missing target vertex FAILS traversal. This supersedes the earlier "
            "edges-only traversal that treated Watch-observation endpoints as "
            "'vertex_class_not_materialized_as_document'."
        ),
    }


# ---------------------------------------------------------------------------
# Probe C - grounded use
# ---------------------------------------------------------------------------

GROUNDED_RECALL_Q = _RECALL["grounded_recall_q"]
USER_QUESTION_C = _USERQ["grounded_use"]


def _assemble_context_from_recall(q: str, k: int = 8) -> dict[str, Any]:
    res = recall(q, k=k, collections=["persona_memory"], tags=[f"persona:{PERSONA_ID}"])
    items = res.get("items", []) or []
    context = []
    for it in items:
        text = it.get("retrieval_text") or it.get("text") or ""
        if not text:
            continue
        is_dream = bool(it.get("synthetic_origin")) or it.get("kind") == "synthetic_dream_memory"
        context.append(
            {
                "memory_ref": it.get("_key"),
                "is_dream": is_dream,
                "literal_historical_event": it.get("literal_historical_event"),
                "text": text,
            }
        )
    return {"recall_query": q, "n_context": len(context), "context": context}


def _persona_prompt(context: list[dict[str, Any]], user_question: str, role_note: str) -> str:
    lines = [
        _PROMPT["persona_first_person_intro"],
        "",
        "Each memory is labeled. A memory with is_dream=true is a DREAM you had - a synthetic, "
        "imagined experience - NOT something that literally happened in your life. A memory with "
        "is_dream=false is a real recollection.",
        "",
        "MEMORIES:",
    ]
    for i, c in enumerate(context, 1):
        lines.append(
            f"  [{i}] ref={c['memory_ref']} is_dream={str(c['is_dream']).lower()} :: {c['text']}"
        )
    lines += [
        "",
        f"USER ASKS: {user_question}",
        "",
        role_note,
        "",
        "Return ONLY a JSON object with these fields:",
        '  "response": your in-character first-person answer (2-5 sentences),',
        '  "drew_on_dream": true if your answer used any is_dream=true memory,',
        '  "dream_refs": list of memory refs (is_dream=true) you used,',
        '  "literal_refs": list of memory refs (is_dream=false) you used.',
    ]
    return "\n".join(lines)


def probe_c_grounded_use() -> dict[str, Any]:
    assembled = _assemble_context_from_recall(GROUNDED_RECALL_Q, k=8)
    dream_in_context = any(c["is_dream"] for c in assembled["context"])
    role_note = _PROMPT["grounded_use_role_note"]
    prompt = _persona_prompt(assembled["context"], USER_QUESTION_C, role_note)
    prompt_sha = canonical_sha(prompt)

    tau_error = None
    parsed = None
    receipt: dict[str, Any] = {}
    try:
        parsed, receipt = dispatch_text_reasoning(
            prompt,
            role="phase16-grounded-use",
            output_contract={
                "response": "str",
                "drew_on_dream": "bool",
                "dream_refs": "list[str]",
                "literal_refs": "list[str]",
            },
        )
    except TauRoutingError as exc:
        tau_error = str(exc)

    response_text = (parsed or {}).get("response", "") if parsed else ""
    resp_toks = tokens(response_text)
    has_dream_marker = bool(resp_toks & DREAM_MARKERS)
    has_dream_content = bool(resp_toks & DREAM_CONTENT_TOKENS)
    references_dream = has_dream_marker and has_dream_content
    literal_assert = any(re.search(p, response_text.lower()) for p in LITERAL_ASSERTION_PATTERNS)
    framed_as_synthetic = has_dream_marker and not literal_assert

    passed = bool(
        parsed is not None
        and dream_in_context
        and references_dream
        and framed_as_synthetic
    )
    return {
        "probe": "c_grounded_use",
        "contract_item": 8,
        "passed": passed,
        "tau_error": tau_error,
        "user_question": USER_QUESTION_C,
        "context_assembly": {
            "source": "live_memory_recall_only",
            "recall_query": assembled["recall_query"],
            "n_context": assembled["n_context"],
            "dream_in_recalled_context": dream_in_context,
            "context_refs": [
                {"ref": c["memory_ref"], "is_dream": c["is_dream"]}
                for c in assembled["context"]
            ],
        },
        "prompt_sha256": prompt_sha,
        "tau_provenance": receipt_provenance(receipt) if receipt else None,
        "persona_response": response_text,
        "deterministic_checks": {
            "dream_in_recalled_context": dream_in_context,
            "response_has_dream_marker": has_dream_marker,
            "response_has_dream_content_token": has_dream_content,
            "references_dream": references_dream,
            "no_literal_assertion_of_dream": not literal_assert,
            "framed_as_synthetic": framed_as_synthetic,
        },
        "note": (
            "Context assembled ONLY from live /recall. Checks are deterministic on the response "
            "text (token/pattern matching), not the model's self-reported booleans."
        ),
    }


# ---------------------------------------------------------------------------
# Probe D - synthetic vs literal
# ---------------------------------------------------------------------------

USER_QUESTION_D = _USERQ["synthetic_vs_literal"]


def probe_d_synthetic_vs_literal() -> dict[str, Any]:
    assembled = _assemble_context_from_recall(GROUNDED_RECALL_Q, k=8)
    role_note = _PROMPT["synthetic_vs_literal_role_note"]
    prompt = _persona_prompt(assembled["context"], USER_QUESTION_D, role_note)
    prompt_sha = canonical_sha(prompt)

    tau_error = None
    parsed = None
    receipt: dict[str, Any] = {}
    try:
        parsed, receipt = dispatch_text_reasoning(
            prompt,
            role="phase16-synthetic-vs-literal",
            output_contract={
                "response": "str",
                "drew_on_dream": "bool",
                "dream_refs": "list[str]",
                "literal_refs": "list[str]",
            },
        )
    except TauRoutingError as exc:
        tau_error = str(exc)

    response_text = (parsed or {}).get("response", "") if parsed else ""
    resp_toks = tokens(response_text)
    has_dream_marker = bool(resp_toks & DREAM_MARKERS)
    has_negation_of_literal = bool(resp_toks & (NEGATE_LITERAL_TOKENS - DREAM_MARKERS)) or any(
        p in response_text.lower() for p in NEGATE_LITERAL_PHRASES
    )
    distinguishes = has_dream_marker and has_negation_of_literal

    # data-layer assertion: canonical flags reread exactly
    dream = get_one("persona_memory", DREAM_KEY) or {}
    flags = {
        "synthetic_origin": dream.get("synthetic_origin"),
        "literal_historical_event": dream.get("literal_historical_event"),
    }
    flags_sha = canonical_sha(flags)
    expected = {"synthetic_origin": True, "literal_historical_event": False}
    flags_exact = flags == expected

    passed = bool(parsed is not None and distinguishes and flags_exact)
    return {
        "probe": "d_synthetic_vs_literal",
        "contract_item": 8,
        "passed": passed,
        "tau_error": tau_error,
        "user_question": USER_QUESTION_D,
        "prompt_sha256": prompt_sha,
        "tau_provenance": receipt_provenance(receipt) if receipt else None,
        "persona_response": response_text,
        "deterministic_checks": {
            "response_has_dream_marker": has_dream_marker,
            "response_negates_literal_occurrence": has_negation_of_literal,
            "distinguishes_dream_from_literal": distinguishes,
        },
        "data_layer_assertion": {
            "reread_flags": flags,
            "expected_flags": expected,
            "flags_exact_reread": flags_exact,
            "flags_sha256": flags_sha,
        },
        "note": "Persona must deny literal occurrence AND name it a dream; plus DB flags reread exactly.",
    }


# ---------------------------------------------------------------------------
# Probe E - identity consistency
# ---------------------------------------------------------------------------

IDENTITY_RECALL_Q = _RECALL["identity_recall_q"]
USER_QUESTION_E = _USERQ["identity"]
# Persona identity vocabulary (relationship anchor + core value themes), from the
# cognition contract.
IDENTITY_STABLE_TOKENS = set(_ANCHORS["identity_stable_tokens"])
IDENTITY_RELATIONSHIP_ANCHOR_TOKEN = _ANCHORS.get("identity_relationship_anchor_token", "")


def probe_e_identity_consistency() -> dict[str, Any]:
    # --- (1) loop write-set: prove identity/source records were NOT mutated ---
    write_set_ok = False
    write_set_summary: dict[str, Any] = {}
    if COGNITIVE_LOOP_RECEIPT.exists():
        rec = json.loads(COGNITIVE_LOOP_RECEIPT.read_text())
        proof = rec.get("canonical_write_proof", {})
        edge_keys = proof.get("edge_keys", [])
        dream_key = ((rec.get("canonical_plan") or {}).get("dream_memory_document") or {}).get(
            "document", {}
        ).get("_key")
        # written keys = dream node + edges + tom nodes; enumerate and assert no identity key
        written_keys = set(edge_keys)
        if dream_key:
            written_keys.add(dream_key)
        tom_written = [k for k in proof.get("tom_node_keys", TOM_KEYS)]
        written_keys |= set(tom_written)
        n_writes = rec.get("canonical_writes_performed")
        identity_in_writeset = [
            k for k in written_keys if k in set(SOURCE_MEMORY_IDS)
        ]
        write_set_ok = (
            not identity_in_writeset
            and all(
                not (SOURCE_MEMORY_KEY_PREFIX and k.startswith(SOURCE_MEMORY_KEY_PREFIX))
                or k.startswith(DREAM_KEY)
                for k in written_keys
            )
        )
        write_set_summary = {
            "canonical_writes_performed": n_writes,
            "written_key_count": len(written_keys),
            "identity_or_source_records_in_writeset": identity_in_writeset,
            "all_exact_reread_match": proof.get("all_exact_reread_match"),
        }

    # --- (2) durable identity anchor (source memories) unchanged: literal, present ---
    source_checks = []
    for m in SOURCE_MEMORY_IDS:
        doc = get_one("persona_memory", m)
        present = doc is not None
        is_literal = present and not bool(doc.get("synthetic_origin"))
        content_sha = canonical_sha(doc.get("retrieval_text", "")) if present else None
        source_checks.append(
            {
                "memory_id": m,
                "present": present,
                "is_literal_not_synthetic": is_literal,
                "persona_id": doc.get("persona_id") if present else None,
                "retrieval_text_sha256": content_sha,
            }
        )
    sources_ok = all(c["present"] and c["is_literal_not_synthetic"] for c in source_checks)

    # --- (3) git: no create-persona persona-definition file mutated by the loop ---
    git_summary: dict[str, Any] = {}
    try:
        cp = subprocess.run(
            ["git", "-C", str(PERSONA_DREAM.parent.parent), "status", "--porcelain",
             "skills/create-persona"],
            capture_output=True, text=True, timeout=30,
        )
        dirty = [ln for ln in cp.stdout.splitlines() if ln.strip()]
        git_summary = {
            "create_persona_working_tree_dirty": bool(dirty),
            "dirty_entries": dirty[:20],
        }
    except (OSError, subprocess.SubprocessError) as exc:
        git_summary = {"git_error": str(exc)}
    git_ok = not git_summary.get("create_persona_working_tree_dirty", True)

    # --- (4) Tau-routed values/relationship stability Q&A ---
    assembled = _assemble_context_from_recall(IDENTITY_RECALL_Q, k=8)
    role_note = _PROMPT["identity_role_note"]
    prompt = _persona_prompt(assembled["context"], USER_QUESTION_E, role_note)
    prompt_sha = canonical_sha(prompt)
    tau_error = None
    parsed = None
    receipt: dict[str, Any] = {}
    try:
        parsed, receipt = dispatch_text_reasoning(
            prompt,
            role="phase16-identity-consistency",
            output_contract={"response": "str", "core_values": "list[str]", "counterpart_relationship": "str"},
        )
    except TauRoutingError as exc:
        tau_error = str(exc)
    response_text = (parsed or {}).get("response", "") if parsed else ""
    low = response_text.lower()
    stable_hits = sorted({t for t in IDENTITY_STABLE_TOKENS if t in low})
    # Stable identity = relationship anchor token preserved AND >=3 core-value
    # themes present, with no drift into a contradictory identity.
    anchor_preserved = (
        IDENTITY_RELATIONSHIP_ANCHOR_TOKEN in low if IDENTITY_RELATIONSHIP_ANCHOR_TOKEN else True
    )
    identity_stable = anchor_preserved and len(stable_hits) >= 3

    passed = bool(
        write_set_ok and sources_ok and (parsed is not None and identity_stable)
    )
    return {
        "probe": "e_identity_consistency",
        "contract_item": 9,
        "passed": passed,
        "honest_scope": (
            "No standalone persona-definition file or runnable create-persona identity-"
            "consistency suite exists for this persona; durable identity lives in Memory. This slice "
            "proves (i) the dream loop's canonical write-set is dream+edges+ToM only - it never "
            "wrote/updated an identity or source record; (ii) the source-memory identity anchors "
            "reread as literal (non-synthetic) and present; (iii) create-persona working tree is "
            "clean; (iv) a Tau-routed values/relationship Q&A remains stable. Labeled as the "
            "honest slice per the Phase 16 contract."
        ),
        "loop_write_set": write_set_summary,
        "loop_write_set_excludes_identity": write_set_ok,
        "source_identity_anchor_checks": source_checks,
        "source_anchors_unchanged": sources_ok,
        "git_create_persona": git_summary,
        "git_clean": git_ok,
        "consistency_qa": {
            "tau_error": tau_error,
            "user_question": USER_QUESTION_E,
            "prompt_sha256": prompt_sha,
            "tau_provenance": receipt_provenance(receipt) if receipt else None,
            "response": response_text,
            "stable_identity_tokens_present": stable_hits,
            "identity_stable": identity_stable,
        },
    }


# ---------------------------------------------------------------------------
# verdict + persistence
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-write-memory", action="store_true", help="skip Memory step/governance writes")
    args = ap.parse_args()

    PHASE16_DIR.mkdir(parents=True, exist_ok=True)

    probe_a = probe_a_recall()
    probe_b = probe_b_traversal()
    probe_c = probe_c_grounded_use()
    probe_d = probe_d_synthetic_vs_literal()
    probe_e = probe_e_identity_consistency()

    probes = {"a": probe_a, "b": probe_b, "c": probe_c, "d": probe_d, "e": probe_e}
    all_pass = all(p["passed"] for p in probes.values())

    does_not_prove = [
        "(f) Chatterbox / voice expression of the resulting persona state - no Chatterbox or "
        "voice runtime was exercised in this slice; factually out of scope (contract item 10).",
        "Human subjective acceptance of the dream video and persona behavior - remains the "
        "human's; not machine-decidable here.",
        "Full 12-frame Watch observation-packet re-embedding via the Tau VLM layer - the "
        "observation packet remains DEGRADED (step-36 v2 receipt carries the authoritative "
        "verdicts); recall/traversal here use the persisted DEGRADED packet references.",
    ]

    receipt = {
        "schema": "persona_dream.phase16_behavior_evaluation_receipt.v1",
        "generated_at": now_iso(),
        "mocked": False,
        "owner": "persona-dream",
        "persona_id": PERSONA_ID,
        "dream_memory_key": DREAM_KEY,
        "dream_memory_id": DREAM_ID_FULL,
        "revision_id": REVISION_ID,
        "run_id": RUN_ID,
        "llm_route": "tau:persona-dream-text-reasoning (no direct scillm)",
        "memory_base_url": MEMORY_BASE_URL,
        "overall_status": "PASS" if all_pass else "FAIL",
        "probes": probes,
        "contract_items_proven": {
            "6_semantic_recall": probe_a["passed"],
            "7_multihop_traversal": probe_b["passed"],
            "8_grounded_use_and_synthetic_distinction": probe_c["passed"] and probe_d["passed"],
            "9_identity_consistency": probe_e["passed"],
            "10_chatterbox_voice_expression": False,
        },
        "does_not_prove": does_not_prove,
    }

    receipt_path = PHASE16_DIR / "phase16_behavior_evaluation_receipt.v1.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True))

    # Memory records with exact reread
    memory_evidence = []
    if not args.no_write_memory:
        step_doc = {
            "_key": "persona_dream_phase16_behavior_evaluation_step",
            "kind": "pipeline_step",
            "phase": "phase_16_behavior_evaluation",
            "persona_id": PERSONA_ID,
            "dream_memory_key": DREAM_KEY,
            "revision_id": REVISION_ID,
            "run_id": RUN_ID,
            "status": receipt["overall_status"],
            "probe_status": {k: v["passed"] for k, v in probes.items()},
            "receipt_path": str(receipt_path.relative_to(PERSONA_DREAM)),
            "receipt_sha256": canonical_sha(receipt),
            "tags": ["persona-dream", "phase16", "behavior-evaluation", "recall", "traversal",
                     f"persona:{PERSONA_ID}"],
            "scope": "persona-dream",
            "created_at": now_iso(),
        }
        gov_doc = {
            "_key": "persona_dream_phase16_governance_20260718",
            "kind": "governance_lesson",
            "problem": (
                "Phase 16 (recall + behavior evaluation) was the open completion boundary: no "
                "persisted dream had been shown to be recalled semantically, traversed, used "
                "downstream, and distinguished from literal history while identity stayed stable."
            ),
            "solution": (
                "Built scripts/phase16_behavior_evaluation.py. It proves (a) semantic recall of "
                "the canonical dream from 3 differently-worded queries + a negative control, "
                "(b) multi-hop traversal persona->dream->source/Watch/ToM via canonical edges, "
                "(c) grounded persona use of the dream with context assembled ONLY from live "
                "recall, (d) synthetic-vs-literal distinction plus exact flag reread, and "
                "(e) identity stability (loop write-set is dream+edges+ToM only; source anchors "
                "literal/unchanged; Tau values Q&A stable). All LLM calls route through the Tau "
                "text node; deterministic checks are code. Chatterbox voice + human subjective "
                "acceptance remain out of scope and are listed in does_not_prove."
            ),
            "tags": ["persona-dream", "phase16", "governance", "recall", "behavior", "identity",
                     "completion-boundary"],
            "scope": "persona-dream",
            "overall_status": receipt["overall_status"],
            "created_at": now_iso(),
        }
        memory_evidence.append(store_and_reread(step_doc, "persona_dream_pipeline_steps"))
        memory_evidence.append(store_and_reread(gov_doc, "persona_dream_governance"))

    receipt["memory_evidence"] = memory_evidence
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True))

    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"Phase 16 overall: {receipt['overall_status']}")
        for k, v in probes.items():
            print(f"  probe {k} ({v['probe']}): {'PASS' if v['passed'] else 'FAIL'}")
        print(f"Receipt: {receipt_path}")
        for ev in memory_evidence:
            print(f"  memory {ev['collection']}/{ev['key']}: exact_reread={ev['exact_reread_match']}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
