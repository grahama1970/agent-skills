"""Evidence Case Builder — 5-gate deterministic pre-validation pipeline.

Before Brandon (or any persona) answers a question, this pipeline converts it
into a database-driven evidence case that proves whether the question is
answerable.  All database queries go through /memory (anti-silo rule).

Gates 2-4 are purely deterministic.  Only Gate 1 (entity extraction via
IntentMapper) and Gate 5 (lean4 formalization) touch an LLM.

Usage:
    from evidence_case import build_evidence_case
    result = build_evidence_case("What countermeasures protect SV-MA-3 from CWE-287?")
    print(result.classification)  # ANSWERABLE | INVALID_IDS | NO_COVERAGE | ...
"""
from __future__ import annotations
# --- dotenv (MUST be before any os.getenv / os.environ) ---
import sys
from pathlib import Path as _Path

def _resolve_skills_dir() -> _Path:
    p = _Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if parent.name == "skills":
            return parent
    return p.parents[1]

_SKILLS_DIR = _resolve_skills_dir()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env() -> None:
        return

_load_env()


import os

import json
import subprocess
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from config import F36_CATEGORIES, F36_DATALAKE_ROOT

from evidence_case_models import (
    HUB_THRESHOLD,
    DatalakeConnection,
    EntityInfo,
    EvidenceCase,
    GateResult,
    RelationshipPath,
    _memory_cmd,
    _memory_count,
    _memory_recall,
    _memory_trace,
    _SAFE_ENTITY_CHARS,
    _sanitize_entity_id,
    classify as _classify,
    log_shadow as _log_shadow,
)

# ---------------------------------------------------------------------------
# Skill paths for subprocess composition (anti-silo: all queries via /memory)
# ---------------------------------------------------------------------------
SKILLS_DIR = Path(__file__).resolve().parents[1]  # .pi/skills/
# Memory accessed via httpx Unix socket (see _memory_cmd)
_LEAN4_RUN = SKILLS_DIR / "lean4-prove" / "run.sh"



# ---------------------------------------------------------------------------
# Gate 1: Extract entities (via /memory intent)
# ---------------------------------------------------------------------------

def _gate1_extract_entities(question: str) -> tuple[GateResult, dict]:
    """Extract entities from the question using /memory intent.

    Uses IntentMapper: entity pre-scan (regex) -> classifier -> LLM fallback.
    """
    t0 = time.monotonic()

    try:
        # Short timeout — ArangoDB fallback is fast and reliable
        query_spec = _memory_cmd(["intent", "--q", question], timeout=10)
        if isinstance(query_spec, list):
            query_spec = query_spec[0] if query_spec else {}
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError,
            FileNotFoundError, ValueError) as exc:
        logger.warning(f"memory intent failed ({exc}), falling back to ArangoDB lookup")
        query_spec = _db_entity_extract(question)

    entities = query_spec.get("entities", [])
    keywords = query_spec.get("keywords", [])
    action = query_spec.get("action", "QUERY")

    elapsed = (time.monotonic() - t0) * 1000
    has_signal = bool(entities) or bool(keywords)

    return GateResult(
        gate=1,
        name="Extract entities",
        passed=has_signal,
        time_ms=elapsed,
        details={
            "entities": entities,
            "f36_categories": query_spec.get("f36_categories", []),
            "keywords": keywords,
            "action": action,
            "frameworks": query_spec.get("frameworks", []),
        },
    ), query_spec


def _db_entity_extract(question: str) -> dict:
    """Fallback entity extraction using ArangoDB semantic search.

    Uses /memory recall with scope=sparta to find matching SPARTA QRAs,
    extracts control IDs from their titles, filters to only those that
    appear in the question text, then verifies each against sparta_controls.

    F36 category detection uses /memory count against datalake_chunks
    (recall only searches lessons, not datalake collections).
    """
    entities = []
    f36_categories = []
    q_upper = question.upper()

    # --- Entity extraction: recall searches ALL collections ---
    # /memory recall with no scope queries lessons + all supplemental sources
    # (sparta_controls, sparta_qra, datalake_chunks via global_access=True).
    # sparta_controls results include control_id directly.
    try:
        results = _memory_recall(question, k=20)
        seen = set()
        for item in results:
            # Supplemental sources (sparta_controls, sparta_qra) return control_id
            cid = item.get("control_id", "")
            if not cid:
                # Lessons have control IDs in titles: "What is SV-MA-3: ..."
                title = item.get("title", "")
                if title.startswith("What is "):
                    rest = title[8:]
                    cid = rest.split(":")[0].strip()
                    if "," in cid:
                        cid = cid.split(",")[0].strip()
            if not cid or cid in seen:
                continue
            seen.add(cid)
            # Only keep IDs that appear in the question text
            if cid.upper() not in q_upper:
                continue
            # Verify against sparta_controls collection
            try:
                cnt = _memory_count(
                    "sparta_controls",
                    f'doc.control_id == "{_sanitize_entity_id(cid)}"',
                )
                if cnt > 0:
                    entities.append(cid)
            except (ValueError, Exception):
                continue
    except Exception as exc:
        logger.warning(f"ArangoDB entity recall failed ({exc})")

    # --- F36 category detection ---
    # datalake_chunks (2.2M docs) IS searched by recall via the
    # datalake_chunks_search view (global_access=True). Results include
    # bridge_tags and taxonomy fields. Check recall results for datalake
    # source items that indicate F36 categories.
    for item in results:
        if item.get("source") == "datalake_chunks" or item.get("type") == "datalake_content":
            tags = item.get("bridge_tags", [])
            for tag in tags:
                if tag in F36_CATEGORIES and tag not in f36_categories:
                    f36_categories.append(tag)

    return {
        "action": "QUERY" if entities or f36_categories else "CLARIFY",
        "entities": entities,
        "f36_categories": f36_categories,
        "keywords": [],
        "frameworks": [],
    }


# ---------------------------------------------------------------------------
# Gate 2: Verify existence (via /memory count + /memory recall)
# ---------------------------------------------------------------------------

def _gate2_verify_existence(entities: list[str]) -> tuple[GateResult, list[EntityInfo]]:
    """Verify each entity exists in sparta_controls and count its QRAs.

    Uses /memory count with filter expressions (anti-silo: no direct AQL).
    """
    t0 = time.monotonic()
    entity_infos = []
    all_valid = True

    for eid in entities:
        # Check if entity is actually an F36 category
        if eid in F36_CATEGORIES:
            info = EntityInfo(entity_id=eid)
            info.exists = (F36_DATALAKE_ROOT / eid).exists()
            info.control_name = f"F36 Category: {eid}"
            # For now, we don't count QRAs for F36 categories directly here,
            # we just confirm the category exists in the datalake.
            entity_infos.append(info)
            if not info.exists:
                all_valid = False
            continue

        info = EntityInfo(entity_id=eid)

        try:
            safe_id = _sanitize_entity_id(eid)

            # Check control existence via /memory count
            ctrl_count = _memory_count(
                "sparta_controls",
                f'doc.control_id == "{safe_id}"',
            )
            info.exists = ctrl_count > 0

            if info.exists:
                # Get control name via recall (returns docs with metadata)
                docs = _memory_recall(eid, collections="sparta_controls", k=1)
                if docs:
                    doc = docs[0]
                    info.control_name = doc.get("name") or doc.get("control_name")

                # Count QRAs via /memory count
                qra_count = _memory_count(
                    "sparta_qra",
                    f'doc.control_id == "{safe_id}"',
                )
                info.qra_count = qra_count

                # Get avg grounding from recall results
                if qra_count > 0:
                    qra_docs = _memory_recall(eid, collections="sparta_qras", k=20)
                    grounding_scores = [
                        d.get("grounding_score", 0)
                        for d in qra_docs
                        if d.get("grounding_score")
                    ]
                    if grounding_scores:
                        info.avg_grounding = sum(grounding_scores) / len(grounding_scores)
            else:
                all_valid = False
                # Suggest similar IDs: recall with the entity as query
                prefix = eid.split("-")[0] + "-" if "-" in eid else eid[:3]
                try:
                    similar = _memory_recall(prefix, collections="sparta_controls", k=5)
                    info.suggestions = [
                        d.get("control_id", "")
                        for d in similar
                        if d.get("control_id")
                    ][:5]
                except (RuntimeError, subprocess.TimeoutExpired,
                        json.JSONDecodeError):
                    pass

        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError,
                FileNotFoundError, ValueError) as exc:
            logger.warning(f"Existence check failed for {eid}: {exc}")
            all_valid = False

        entity_infos.append(info)

    elapsed = (time.monotonic() - t0) * 1000

    return GateResult(
        gate=2,
        name="Verify existence",
        passed=all_valid,
        time_ms=elapsed,
        details={
            "valid": [e.entity_id for e in entity_infos if e.exists],
            "invalid": [e.entity_id for e in entity_infos if not e.exists],
        },
    ), entity_infos


# ---------------------------------------------------------------------------
# Gate 2b: Verify datalake-SPARTA connection via /memory recall
# ---------------------------------------------------------------------------

def _gate2b_verify_datalake_connection(
    question: str,
    entities: list[str],
) -> tuple[GateResult, list[DatalakeConnection]]:
    """Measure taxonomy overlap between datalake and SPARTA via /memory recall.

    Uses /memory recall (BM25 + semantic + multihop graph traversal) with the
    original question. The source field on each item tells us if it came from
    datalake_chunks vs sparta_qra vs lessons. This is datalake-agnostic — works
    for F36, Boeing, any future client whose data has been ingested into /memory.
    """
    t0 = time.monotonic()
    connections: list[DatalakeConnection] = []

    try:
        # Single /memory recall with the question — let BM25+semantic do the work
        items = _memory_recall(question, k=20)
    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError,
            FileNotFoundError, ValueError) as exc:
        logger.warning(f"Datalake connection recall failed: {exc}")
        elapsed = (time.monotonic() - t0) * 1000
        return GateResult(
            gate=6,
            name="Datalake connection",
            passed=False,
            time_ms=elapsed,
            details={"error": str(exc)[:200]},
        ), connections

    # Separate datalake items from SPARTA items by _source field
    # Actual values: _source="datalake_chunks", _source="sparta_qras" (plural)
    datalake_items: list[dict] = []
    sparta_items: list[dict] = []
    for item in items:
        source = item.get("_source", "")
        if source == "datalake_chunks":
            datalake_items.append(item)
        elif source == "sparta_qras":
            sparta_items.append(item)

    if not datalake_items:
        # No datalake content found — not a failure, just no glue needed
        elapsed = (time.monotonic() - t0) * 1000
        return GateResult(
            gate=6,
            name="Datalake connection",
            passed=True,
            time_ms=elapsed,
            details={"reason": "no_datalake_items", "total_items": len(items)},
        ), connections

    # Group datalake items by category
    category_items: dict[str, list[dict]] = defaultdict(list)
    for item in datalake_items:
        cat = item.get("asset_type") or item.get("category") or "uncategorized"
        category_items[cat].append(item)

    # Collect SPARTA-side bridge tags once (shared across all categories)
    sparta_bridge_tags: dict[str, list[float]] = defaultdict(list)
    for si in sparta_items:
        for tag in si.get("conceptual_tags", []):
            sparta_bridge_tags[tag].append(1.0)
        for tag in si.get("bridge_attributes", []):
            sparta_bridge_tags[tag].append(1.0)
    # Also recall SPARTA entities directly for richer bridge coverage
    for eid in entities[:5]:
        try:
            eid_items = _memory_recall(eid, collections="sparta_qras", k=5)
            for si in eid_items:
                for tag in si.get("conceptual_tags", []):
                    sparta_bridge_tags[tag].append(1.0)
                for tag in si.get("bridge_attributes", []):
                    sparta_bridge_tags[tag].append(1.0)
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
    sparta_bridges_avg = {
        tag: sum(vals) / len(vals) for tag, vals in sparta_bridge_tags.items()
    }

    # Build DatalakeConnection per category
    for cat, cat_items in category_items.items():
        conn = DatalakeConnection(category=cat)
        conn.item_count = len(cat_items)

        graph_scores = []
        combined_scores = []
        dl_bridge_tags: dict[str, list[float]] = defaultdict(list)
        control_ids: set[str] = set()

        for item in cat_items:
            scores = item.get("scores", {})
            g_score = float(scores.get("graph", 0.0))
            if g_score:
                graph_scores.append(g_score)

            # BM25 scores may be raw (not normalized) for supplemental sources
            bm25_raw = float(scores.get("bm25", 0.0))
            bm25 = min(1.0, bm25_raw) if bm25_raw <= 1.0 else min(1.0, bm25_raw / 30.0)
            graph_val = float(scores.get("graph", 0.0))
            combined = bm25 * 0.6 + graph_val * 0.4
            if combined:
                combined_scores.append(combined)

            # Datalake bridge tags
            for tag in item.get("bridge_tags", []):
                dl_bridge_tags[tag].append(combined or 0.5)
            for tag in item.get("bridge_attributes", []):
                dl_bridge_tags[tag].append(combined or 0.5)

            # Referenced SPARTA controls
            for ref in item.get("referenced_controls", []):
                rcid = ref.get("control_id", "")
                if rcid and _SAFE_ENTITY_RE.match(rcid):
                    control_ids.add(rcid)
            cid = item.get("control_id", "")
            if cid and _SAFE_ENTITY_RE.match(cid):
                control_ids.add(cid)

        conn.avg_graph_score = (
            sum(graph_scores) / len(graph_scores) if graph_scores else 0.0
        )
        conn.recall_confidence = (
            sum(combined_scores) / len(combined_scores) if combined_scores else 0.0
        )
        conn.datalake_bridges = {
            tag: sum(vals) / len(vals) for tag, vals in dl_bridge_tags.items()
        }
        conn.sparta_bridges = sparta_bridges_avg
        conn.connected_controls = sorted(control_ids)

        # Intersection: tags on BOTH datalake and SPARTA sides
        shared_tags = set(conn.datalake_bridges) & set(conn.sparta_bridges)
        conn.shared_bridges = {
            tag: (conn.datalake_bridges[tag] + conn.sparta_bridges[tag]) / 2
            for tag in shared_tags
        }

        connections.append(conn)

    # Gate passes if:
    # - Any category has a graph connection or shared taxonomy bridges, OR
    # - Datalake items lack bridge tags (not yet taxonomy-enriched — can't measure)
    any_connected = any(
        c.avg_graph_score > 0 or c.connected_controls or c.shared_bridges
        for c in connections
    )
    any_has_tags = any(c.datalake_bridges for c in connections)
    elapsed = (time.monotonic() - t0) * 1000

    return GateResult(
        gate=6,
        name="Datalake connection",
        # Pass if connected, OR if datalake items aren't taxonomy-enriched yet
        passed=any_connected or not any_has_tags,
        time_ms=elapsed,
        details={
            "datalake_items": len(datalake_items),
            "sparta_items": len(sparta_items),
            "categories_found": list(category_items.keys()),
            "categories_connected": sum(
                1 for c in connections
                if c.avg_graph_score > 0 or c.connected_controls
            ),
            "avg_graph_score": round(
                sum(c.avg_graph_score for c in connections) / len(connections), 3
            ) if connections else 0.0,
        },
    ), connections


# ---------------------------------------------------------------------------
# Gate 3: Check relationships (via /memory trace + /memory count)
# ---------------------------------------------------------------------------

def _gate3_check_relationships(
    entity_infos: list[EntityInfo],
) -> tuple[GateResult, list[RelationshipPath], list[list[str]]]:
    """Check graph relationships between valid entities.

    Uses /memory count on sparta_relationships for direct lookups, and
    /memory trace for multi-hop graph traversal.
    """
    t0 = time.monotonic()
    valid = [e for e in entity_infos if e.exists]
    paths: list[RelationshipPath] = []

    if len(valid) < 2:
        components = [[e.entity_id for e in valid]] if valid else []
        elapsed = (time.monotonic() - t0) * 1000
        return GateResult(
            gate=3,
            name="Check relations",
            passed=True,
            time_ms=elapsed,
            details={"paths": 0, "components": len(components)},
        ), paths, components

    # Build adjacency for connected components
    adjacency: dict[str, set[str]] = defaultdict(set)

    # Check all entity pairs
    for i, a in enumerate(valid):
        for b in valid[i + 1:]:
            path = _find_path(a.entity_id, b.entity_id)
            paths.append(path)
            if path.found:
                adjacency[a.entity_id].add(b.entity_id)
                adjacency[b.entity_id].add(a.entity_id)

    components = _connected_components([e.entity_id for e in valid], adjacency)

    elapsed = (time.monotonic() - t0) * 1000
    found_count = sum(1 for p in paths if p.found)

    return GateResult(
        gate=3,
        name="Check relations",
        passed=True,  # Gate 3 always passes — provides data for Gate 4
        time_ms=elapsed,
        details={
            "paths_found": found_count,
            "paths_total": len(paths),
            "components": len(components),
        },
    ), paths, components


def _find_path(source: str, target: str) -> RelationshipPath:
    """Find path between two entities in sparta_relationships (1-2 hops).

    Uses /memory count for direct edge check, /memory trace for 2-hop.
    """
    path = RelationshipPath(source=source, target=target)

    try:
        safe_src = _sanitize_entity_id(source)
        safe_tgt = _sanitize_entity_id(target)

        # Direct (1-hop): check both directions via /memory count
        direct_fwd = _memory_count(
            "sparta_relationships",
            f'doc.source_control_id == "{safe_src}" AND doc.target_control_id == "{safe_tgt}"',
        )
        direct_rev = _memory_count(
            "sparta_relationships",
            f'doc.source_control_id == "{safe_tgt}" AND doc.target_control_id == "{safe_src}"',
        )
        if direct_fwd > 0 or direct_rev > 0:
            path.found = True
            path.hops = 1
            return path

        # 2-hop: use /memory trace which does multi-hop BFS
        trace = _memory_trace(f"{source} {target}", mode="fast", k=20)
        edges = trace.get("edges", trace.get("graph", {}).get("edges", []))
        nodes_in_trace = set()
        for edge in edges:
            src = edge.get("source", edge.get("from", ""))
            tgt = edge.get("target", edge.get("to", ""))
            nodes_in_trace.add(src)
            nodes_in_trace.add(tgt)

        # Check if both source and target appear in the trace graph
        source_found = any(source in n for n in nodes_in_trace)
        target_found = any(target in n for n in nodes_in_trace)

        if source_found and target_found:
            # Find intermediate node(s)
            intermediates = []
            for edge in edges:
                e_src = edge.get("source", edge.get("from", ""))
                e_tgt = edge.get("target", edge.get("to", ""))
                for nid in (e_src, e_tgt):
                    if nid and source not in nid and target not in nid:
                        # Sanitize intermediate node ID before filter
                        try:
                            safe_nid = _sanitize_entity_id(nid)
                        except ValueError:
                            continue
                        # Check it's not a hub
                        hub_count = _memory_count(
                            "sparta_relationships",
                            f'doc.source_control_id == "{safe_nid}" OR doc.target_control_id == "{safe_nid}"',
                        )
                        if hub_count < HUB_THRESHOLD:
                            intermediates.append(nid)
                            break
                if intermediates:
                    break

            path.found = True
            path.hops = 2
            path.via = intermediates[:1]
            return path

    except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError,
            FileNotFoundError, ValueError) as exc:
        logger.warning(f"Relationship check failed {source}->{target}: {exc}")

    return path


def _connected_components(
    nodes: list[str], adjacency: dict[str, set[str]]
) -> list[list[str]]:
    """Find connected components using BFS."""
    visited: set[str] = set()
    components: list[list[str]] = []

    for node in nodes:
        if node in visited:
            continue
        component = []
        queue = deque([node])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(component)

    return components


# ---------------------------------------------------------------------------
# Gate 4: Decompose request (graph-driven, NOT string splitting)
# ---------------------------------------------------------------------------

def _gate4_decompose(
    question: str,
    components: list[list[str]],
    entity_infos: list[EntityInfo],
) -> tuple[GateResult, list[str]]:
    """Decompose question based on connected components from Gate 3.

    - 1 component -> no decomposition needed
    - N components -> one sub-question per component
    - 0 components -> trigger clarify
    """
    t0 = time.monotonic()
    sub_questions: list[str] = []

    if len(components) == 0:
        elapsed = (time.monotonic() - t0) * 1000
        return GateResult(
            gate=4,
            name="Decompose",
            passed=False,
            time_ms=elapsed,
            details={"reason": "no_valid_entities"},
        ), sub_questions

    if len(components) == 1:
        elapsed = (time.monotonic() - t0) * 1000
        return GateResult(
            gate=4,
            name="Decompose",
            passed=True,
            time_ms=elapsed,
            details={"reason": "single_component", "entities": components[0]},
        ), sub_questions

    # Multiple components — decompose
    entity_names = {e.entity_id: e.control_name or e.entity_id for e in entity_infos}

    for comp in components:
        if len(comp) == 1:
            name = entity_names.get(comp[0], comp[0])
            if comp[0] in F36_CATEGORIES:
                sub_questions.append(f"What SPARTA controls map to the F36 ({name}) context?")
            else:
                sub_questions.append(f"What is known about {comp[0]} ({name})?")
        else:
            ids = ", ".join(comp)
            sub_questions.append(
                f"How do {ids} relate in the context of: {question[:120]}"
            )

    # Add cross-component relationship question
    if len(components) == 2:
        c1_ids = ", ".join(components[0])
        c2_ids = ", ".join(components[1])
        sub_questions.append(f"How do {c1_ids} relate to {c2_ids}?")

    elapsed = (time.monotonic() - t0) * 1000
    return GateResult(
        gate=4,
        name="Decompose",
        passed=True,
        time_ms=elapsed,
        details={
            "reason": "decomposed",
            "components": len(components),
            "sub_questions": len(sub_questions),
        },
    ), sub_questions


# ---------------------------------------------------------------------------
# Gate 5: Formalize + check existing QRAs
# ---------------------------------------------------------------------------

def _gate5_formalize(entity_infos: list[EntityInfo], question: str) -> GateResult:
    """Aggregate QRA stats for all valid controls, try lean4 formalization."""
    t0 = time.monotonic()

    valid = [e for e in entity_infos if e.exists]
    total_qras = sum(e.qra_count for e in valid)
    grounding_scores = [e.avg_grounding for e in valid if e.avg_grounding > 0]
    avg_grounding = (
        sum(grounding_scores) / len(grounding_scores) if grounding_scores else 0.0
    )

    # Try lean4-prove (non-blocking, best-effort)
    lean4_ok = False
    try:
        result = subprocess.run(
            [str(_LEAN4_RUN), "-r", question[:200]],
            capture_output=True, text=True, timeout=30,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        if result.returncode == 0:
            lean4_data = json.loads(result.stdout.strip())
            lean4_ok = lean4_data.get("success", False)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        pass  # lean4 is optional

    elapsed = (time.monotonic() - t0) * 1000

    return GateResult(
        gate=5,
        name="Formalize + QRAs",
        passed=total_qras > 0,
        time_ms=elapsed,
        details={
            "total_qras": total_qras,
            "avg_grounding": round(avg_grounding, 3),
            "lean4_verifiable": lean4_ok,
        },
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def build_evidence_case(
    question: str,
    *,
    recursive: bool = True,
    max_depth: int = 2,
    _depth: int = 0,
) -> EvidenceCase:
    """Build a complete evidence case for a question.

    Runs 5 deterministic gates (all DB access via /memory):
    1. Extract entities (/memory intent -> IntentMapper)
    2. Verify existence (/memory count on sparta_controls)
    3. Check relationships (/memory count + trace on sparta_relationships)
    4. Decompose (connected components from Gate 3)
    5. Formalize + count QRAs (aggregated from Gate 2)

    Returns an EvidenceCase with classification and all gate results.
    """
    t_start = time.monotonic()
    case = EvidenceCase(question=question)

    # Gate 1: Extract entities
    gate1, query_spec = _gate1_extract_entities(question)
    case.gates.append(gate1)
    case.query_spec = query_spec
    entities = query_spec.get("entities", [])
    f36_categories = query_spec.get("f36_categories", [])
    case.f36_categories = f36_categories
    
    # Combine SPARTA entities and F36 categories for unified gate processing
    all_entities = entities + f36_categories

    if not gate1.passed:
        case.classification = "NEEDS_CLARIFICATION"
        case.total_time_ms = (time.monotonic() - t_start) * 1000
        _log_shadow(case)
        return case

    # Gate 2: Verify existence
    gate2, entity_infos = _gate2_verify_existence(all_entities)
    case.gates.append(gate2)
    case.entities = entity_infos

    if not gate2.passed:
        case.classification = "INVALID_IDS"
        case.total_time_ms = (time.monotonic() - t_start) * 1000
        _log_shadow(case)
        return case

    # Gate 6: Verify datalake-SPARTA taxonomy connection via /memory recall
    # Always runs — /memory recall determines if datalake content is relevant
    datalake_gate, datalake_connections = _gate2b_verify_datalake_connection(
        question, entities,
    )
    case.gates.append(datalake_gate)
    case.datalake_connections = datalake_connections
    # Populate f36_categories from what /memory recall actually found
    if datalake_connections:
        case.f36_categories = [c.category for c in datalake_connections]

    # NOTE: Datalake connection failure is informational, not a hard stop.
    # A pure SPARTA question (valid entities, QRAs exist) should always
    # proceed through Gates 3-5. DATALAKE_NOT_CONNECTED only applies if
    # the question *requires* datalake context and it's missing.

    # Gate 3: Check relationships
    gate3, paths, components = _gate3_check_relationships(entity_infos)
    case.gates.append(gate3)
    case.relationships = paths
    case.components = components

    # Gate 4: Decompose
    gate4, sub_questions = _gate4_decompose(question, components, entity_infos)
    case.gates.append(gate4)

    # Handle decomposition recursively
    if sub_questions and recursive and _depth < max_depth:
        for sq in sub_questions:
            sub_case = build_evidence_case(
                sq, recursive=True, max_depth=max_depth, _depth=_depth + 1,
            )
            case.sub_cases.append(sub_case)

    # Gate 5: Formalize + QRA stats
    gate5 = _gate5_formalize(entity_infos, question)
    case.gates.append(gate5)
    case.total_qras = gate5.details.get("total_qras", 0)
    case.avg_grounding = gate5.details.get("avg_grounding", 0.0)
    case.lean4_verifiable = gate5.details.get("lean4_verifiable", False)

    # Classify
    case.classification = _classify(
        gate1, gate2, gate3, gate4, gate5, components, case.sub_cases,
        f36_categories=case.f36_categories,
        datalake_gate=datalake_gate,
    )
    case.total_time_ms = (time.monotonic() - t_start) * 1000

    _log_shadow(case)
    return case




