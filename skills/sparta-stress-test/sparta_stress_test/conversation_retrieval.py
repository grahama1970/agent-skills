"""Retrieval layer for SPARTA conversation simulation.

Handles Tier 1 fast lookup, query planning, and the main _sparta_answer()
orchestration function. Entity extraction and NLG synthesis live in
conversation_synthesis.py. All retrieval goes through /memory -- no bespoke AQL.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger

from sparta_stress_test.conversation_models import (
    PI_MONO_SKILLS,
    SKILL_SLASH_PATTERN,
    Tier1Result,
    _HAS_ASSISTANT,
    _HAS_CONTROL_CATALOG,
    _HAS_EPISODIC,
    _HAS_QUALITY_UTILS,
    _call_scillm,
    _get_db,
)
from sparta_stress_test.conversation_prompts import QUERY_PLAN_PROMPT
from sparta_stress_test.conversation_steering import (
    _build_clarify_response,
    _build_no_coverage_response,
    _execute_skill_chain,
    _steer_control_only,
    _steer_unknown_entity,
    _suggest_skill,
)
from sparta_stress_test.conversation_synthesis import (
    _extract_entity_ids,
    _extract_keywords,
    _labeled_synthesize,
    _nlg_synthesize,
    _reasoning_synthesize,
    _rerank_by_bridge_overlap,
    _validate_entities_with_parents,
)

# Conditional imports mirrored from models
try:
    from assistant import classify as _assistant_classify
except ImportError:
    _assistant_classify = None

try:
    from graph_memory.agent import recall as _episodic_recall
except ImportError:
    _episodic_recall = None

# Module-level ControlCatalog singleton (loaded once, reused across turns)
_control_catalog: Optional[Any] = None
_catalog_loaded: bool = False


# --------------------------------------------------------------------------- #
# Tier 1: Fast exact lookup (runs BEFORE any LLM call, every turn)
# --------------------------------------------------------------------------- #


def _get_control_catalog(db) -> Any:
    """Lazy-load ControlCatalog singleton from /extract-controls."""
    global _control_catalog, _catalog_loaded
    if _catalog_loaded:
        return _control_catalog
    _catalog_loaded = True
    if not _HAS_CONTROL_CATALOG:
        logger.debug("ControlCatalog not available — /extract-controls not importable")
        return None
    try:
        from sparta_stress_test.conversation_models import ControlCatalog
        cat = ControlCatalog()
        n = cat.load_from_db(db)
        logger.info(f"ControlCatalog loaded: {n} controls")
        _control_catalog = cat
        return cat
    except Exception as e:
        logger.warning(f"ControlCatalog load failed: {e}")
        return None


def _detect_explicit_skills(text: str) -> List[str]:
    """Extract /skill-name commands from text. Zero ambiguity — direct dispatch."""
    return SKILL_SLASH_PATTERN.findall(text)


def _qra_count_for_entities(entity_ids: List[str], db) -> Dict[str, int]:
    """Fast AQL: count QRAs per entity. O(1) per entity via indexed lookup."""
    counts: Dict[str, int] = {}
    if not entity_ids:
        return counts
    try:
        cursor = db.aql.execute(
            """FOR cid IN @cids
                 LET cnt = LENGTH(
                   FOR doc IN sparta_qra
                     FILTER doc.control_id == cid
                     RETURN 1
                 )
                 RETURN {cid: cid, cnt: cnt}""",
            bind_vars={"cids": entity_ids},
        )
        for row in cursor:
            counts[row["cid"]] = row["cnt"]
    except Exception as e:
        logger.debug(f"QRA count query failed: {e}")
        for cid in entity_ids:
            try:
                cnt = db.aql.execute(
                    "RETURN LENGTH(FOR d IN sparta_qra FILTER d.control_id == @c RETURN 1)",
                    bind_vars={"c": cid},
                ).next()
                counts[cid] = cnt
            except Exception:
                counts[cid] = 0
    return counts


def _graph_neighbors_with_qras(entity_ids: List[str], db) -> List[str]:
    """Find controls connected to entity_ids via relationship graph that have QRAs."""
    neighbors: List[str] = []
    if not entity_ids:
        return neighbors
    try:
        cursor = db.aql.execute(
            """FOR cid IN @cids
                 FOR rel IN sparta_relationships
                   FILTER rel.source_control_id == cid OR rel.target_control_id == cid
                   FILTER rel.relationship_type IN ["related_to", "mitigates", "implements"]
                   LET neighbor = rel.source_control_id == cid ? rel.target_control_id : rel.source_control_id
                   LET has_qra = LENGTH(FOR q IN sparta_qra FILTER q.control_id == neighbor LIMIT 1 RETURN 1) > 0
                   FILTER has_qra
                   RETURN DISTINCT neighbor""",
            bind_vars={"cids": entity_ids[:5]},
        )
        neighbors = list(cursor)
    except Exception as e:
        logger.debug(f"Graph neighbor query failed: {e}")
    return neighbors[:10]


def _skill_suggest_via_memory(question_text: str) -> List[str]:
    """Use /memory recall against skill_descriptions to find matching skills."""
    try:
        from graph_memory.api import MemoryClient
        mc = MemoryClient(scope="sparta", k=5)
        result = mc.recall(
            q=question_text, k=5,
            collections=["skill_descriptions"],
        )
        skills = []
        for item in result.get("items", []):
            name = item.get("name") or item.get("skill_name") or ""
            if name and name not in skills:
                skills.append(name)
        return skills[:3]
    except Exception as e:
        logger.debug(f"Skill suggestion via /memory failed: {e}")
        return []


def _tier1_lookup(
    question_text: str,
    target_control: Optional[str] = None,
    db: Optional[Any] = None,
) -> Tier1Result:
    """Tier 1 fast classification -- runs BEFORE any LLM call, every turn.

    Uses ControlCatalog from /extract-controls for O(1) exact match + fuzzy.
    Returns classification + routing metadata for _sparta_answer().
    """
    if db is None:
        db = _get_db()

    # Step 0: Check for explicit /slash commands (highest priority)
    explicit_skills = _detect_explicit_skills(question_text)
    if explicit_skills:
        return Tier1Result(
            classification="SKILL_INVOKE",
            skill_refs=explicit_skills,
            skill_explicit=True,
        )

    # Step 1: Extract entity IDs from question text
    entities = _extract_entity_ids(question_text)
    if target_control and target_control not in entities:
        entities.insert(0, target_control)

    # Step 2: Validate entities via ControlCatalog (fast, in-memory)
    catalog = _get_control_catalog(db)
    valid_entities: List[str] = []
    unknown_entities: List[str] = []
    fuzzy_matches: Dict[str, List[str]] = {}

    if catalog and entities:
        for eid in entities:
            resolved = catalog.resolve(eid)
            if resolved:
                cid, _key, confidence, method = resolved
                valid_entities.append(cid)
            else:
                unknown_entities.append(eid)
                fuzzy = catalog.resolve(eid, threshold=70)
                if fuzzy:
                    fuzzy_matches[eid] = [fuzzy[0]]
    elif entities:
        if _HAS_QUALITY_UTILS:
            validity = _validate_entities_with_parents(entities, db)
            valid_entities = [e for e in entities if validity.get(e, True)]
            unknown_entities = [e for e in entities if not validity.get(e, True)]
        else:
            valid_entities = entities

    # Step 3: Count QRAs for valid entities
    qra_counts = _qra_count_for_entities(valid_entities, db) if valid_entities else {}

    # Step 4: If some entities have QRAs but others don't, get graph neighbors
    graph_neighbors: List[str] = []
    entities_without_qras = [e for e in valid_entities if qra_counts.get(e, 0) == 0]
    if entities_without_qras:
        graph_neighbors = _graph_neighbors_with_qras(entities_without_qras, db)

    # Step 5: Classify
    if not entities:
        skill_hits = _skill_suggest_via_memory(question_text)
        if skill_hits:
            return Tier1Result(
                classification="SKILL_SUGGEST",
                skill_refs=skill_hits,
                skill_explicit=False,
            )
        return Tier1Result(classification="NO_ENTITIES")

    if unknown_entities and not valid_entities:
        return Tier1Result(
            classification="UNKNOWN_ENTITY",
            unknown_entities=unknown_entities,
            fuzzy_matches=fuzzy_matches,
        )

    has_qras = any(qra_counts.get(e, 0) > 0 for e in valid_entities)
    if has_qras:
        steer_toward = None
        if entities_without_qras and graph_neighbors:
            steer_toward = graph_neighbors[0]
        return Tier1Result(
            classification="HAS_QRAS",
            valid_entities=valid_entities,
            qra_counts=qra_counts,
            unknown_entities=unknown_entities,
            fuzzy_matches=fuzzy_matches,
            graph_neighbors=graph_neighbors,
            steer_toward=steer_toward,
        )

    return Tier1Result(
        classification="CONTROL_ONLY",
        valid_entities=valid_entities,
        qra_counts=qra_counts,
        graph_neighbors=graph_neighbors,
        steer_toward=graph_neighbors[0] if graph_neighbors else None,
    )


# --------------------------------------------------------------------------- #
# Query planning
# --------------------------------------------------------------------------- #


def _plan_query_strategy(
    question: str,
    entities: List[str],
    bridges: List[str],
    episodic_context: str,
) -> Dict[str, Any]:
    """Brandon decides which AQL calls + skills to compose for this question.

    Uses /scillm for the decision. /assistant shadows every call so classifiers
    learn the pattern via Shadow-LEGO.
    """
    prompt = QUERY_PLAN_PROMPT.format(
        question=question[:500],
        entities=", ".join(entities[:10]) if entities else "(none)",
        bridges=", ".join(bridges[:6]) if bridges else "(none)",
        episodic_summary=episodic_context[:300] if episodic_context else "(no prior answers found)",
    )

    plan = None
    try:
        raw = _call_scillm(
            system="You are a query planner for SPARTA space systems cybersecurity. Return JSON only.",
            user_prompt=prompt,
            max_tokens=256,
        )
        plan = json.loads(raw)
    except Exception as e:
        logger.debug(f"Query planner /scillm call failed: {e}")

    if _HAS_ASSISTANT and _assistant_classify and plan:
        try:
            _assistant_classify(
                text=f"Q: {question[:300]}\nEntities: {', '.join(entities[:5])}\nBridges: {', '.join(bridges[:3])}",
                task="query_plan",
                scope="sparta",
                confidence_threshold=0.75,
            )
        except Exception:
            pass

    if not plan:
        plan = _plan_query_heuristic(question, entities, bridges, episodic_context)

    return plan


def _plan_query_heuristic(
    question: str,
    entities: List[str],
    bridges: List[str],
    episodic_context: str,
) -> Dict[str, Any]:
    """Deterministic fallback query planner -- no LLM needed."""
    q_lower = question.lower()
    strategy = []
    needs_graph = False
    needs_memory_recall = False
    reuse_episodic = False

    if episodic_context and len(episodic_context) > 100:
        strategy.append("EPISODIC_REUSE")
        reuse_episodic = True

    if entities:
        strategy.append("QRA_LOOKUP")

    if any(w in q_lower for w in (
        "related", "connected", "mapped", "attack chain", "path",
        "relationship", "linked", "associated", "impacts", "affects",
        "neighbor", "adjacent", "upstream", "downstream",
    )):
        strategy.append("GRAPH_TRAVERSAL")
        needs_graph = True

    if not entities or any(w in q_lower for w in (
        "overview", "summary", "explain", "describe", "what is",
        "how does", "why", "compare", "difference",
    )):
        strategy.append("MEMORY_RECALL")
        needs_memory_recall = True

    if "QRA_LOOKUP" not in strategy:
        strategy.append("BM25_SEARCH")

    if not strategy:
        strategy = ["QRA_LOOKUP", "BM25_SEARCH"]

    return {
        "strategy": strategy,
        "reasoning": "heuristic fallback",
        "primary_lane": strategy[0] if strategy else "QRA_LOOKUP",
        "needs_graph": needs_graph,
        "needs_memory_recall": needs_memory_recall,
        "reuse_episodic": reuse_episodic,
        "needs_clarify": False,
    }


# --------------------------------------------------------------------------- #
# Episodic recall helper
# --------------------------------------------------------------------------- #


def _recall_episodic_context(question: str, scope: str = "sparta") -> str:
    """Query episodic memory for similar past questions/responses.

    Returns a context string with prior answers that can inform re-retrieval.
    Fix 7: Only reuse sessions with grade A+/A/B (composite >= 0.75) to
    prevent C/F graded answers from poisoning current sessions.
    """
    if not _HAS_EPISODIC or not _episodic_recall:
        return ""

    try:
        result = _episodic_recall(q=question, scope=scope, k=6, depth=1)
        items = result.get("items", [])
        if not items:
            return ""

        context_parts = []
        for item in items:
            # Fix 7: Filter out low-quality prior sessions
            grade = item.get("grade", "")
            composite = item.get("composite", item.get("grounding_score", 0.0))
            # Skip items with known bad grades
            if grade in ("C", "F"):
                logger.debug(f"Episodic skip: grade={grade} title={item.get('title', '')[:50]}")
                continue
            # Skip items with low composite scores (if available)
            if isinstance(composite, (int, float)) and composite > 0 and composite < 0.75:
                logger.debug(f"Episodic skip: composite={composite:.2f} title={item.get('title', '')[:50]}")
                continue

            title = item.get("title", "")
            solution = item.get("solution", item.get("content", ""))
            if solution:
                context_parts.append(
                    f"[Prior: {title}] {solution[:300]}"
                )
            if len(context_parts) >= 3:
                break

        if context_parts:
            context = "\n".join(context_parts)
            logger.debug(
                f"Episodic context: {len(context_parts)} prior answers "
                f"({len(context)} chars) [quality-filtered]"
            )
            return context
    except Exception as e:
        logger.debug(f"Episodic recall failed: {e}")

    return ""


# --------------------------------------------------------------------------- #
# SPARTA system response (Turn 2 / Turn 4) -- Tier 1 gated
# --------------------------------------------------------------------------- #


def _sparta_answer(
    question_text: str,
    target_control: Optional[str] = None,
    exclude_keys: Optional[List[str]] = None,
    difficulty: str = "medium",
    expected_action: str = "QUERY",
) -> Dict:
    """Brandon's 2-tier retrieval with conversation steering.

    Tier 1 (fast, every turn): Exact control_id lookup + classification.
    Tier 2 (deep, only if HAS_QRAS or NO_ENTITIES): Full /memory recall.

    Returns dict with: answered, answer_text, qra_count, techniques,
    countermeasures, source_keys, lanes_used, query_plan.
    """
    try:
        db = _get_db()
        _exclude = list(exclude_keys or [])

        # -- Tier 1: Fast exact lookup --
        tier1 = _tier1_lookup(question_text, target_control, db)
        logger.debug(
            f"Tier 1: {tier1.classification} "
            f"valid={tier1.valid_entities[:3]} "
            f"qra_counts={tier1.qra_counts} "
            f"unknown={tier1.unknown_entities[:3]}"
        )

        # Short-circuit routes (only for explicit skill invocations)
        if tier1.classification == "SKILL_INVOKE":
            return _execute_skill_chain(tier1.skill_refs, question_text)
        # SKILL_SUGGEST and NO_ENTITIES: fall through to semantic recall
        # instead of short-circuiting. The question may not contain explicit
        # control IDs but semantic search can still find relevant QRAs.
        if tier1.classification == "UNKNOWN_ENTITY":
            return _steer_unknown_entity(tier1, question_text)
        if tier1.classification == "CONTROL_ONLY":
            return _steer_control_only(tier1, question_text, db)

        # -- Step 0a: Episodic check --
        episodic_context = _recall_episodic_context(question_text)

        # -- Step 0b: /memory clarify --
        clarify = None
        try:
            from graph_memory.agent_cli import _clarify_direct
            clarify = _clarify_direct(
                q=question_text, persona="brandon_bailey", scope="sparta", k=5,
            )
        except Exception as e:
            logger.debug(f"Clarify unavailable: {e}")
            clarify = {
                "needs_clarification": False,
                "intent": {"entities": []},
                "taxonomy": {"merged_bridges": []},
                "diagnostics": {},
            }

        # Guard 1 (evidence-aware): Use richness score from disambiguation
        # evidence instead of blunt entity-skip.
        evidence = clarify.get("evidence", {})
        richness = evidence.get("richness_score", 0.0)

        if tier1.valid_entities or target_control:
            if richness >= 0.4:
                clarify["needs_clarification"] = False
                logger.debug(
                    f"Skipping clarify -- richness={richness:.2f}, "
                    f"entities={tier1.valid_entities[:3] or [target_control]}"
                )
            elif richness < 0.2 and clarify.get("needs_clarification"):
                logger.debug(
                    f"Keeping clarify -- sparse richness={richness:.2f}"
                )
            else:
                clarify["needs_clarification"] = False
                logger.debug(
                    f"Skipping clarify -- entities found, richness={richness:.2f}"
                )

        # Guard 2: empty corpus guard
        diag = clarify.get("diagnostics", {})
        if diag.get("low_recall_confidence") is not None:
            try:
                qra_count_check = db.collection("sparta_qra").count()
                if qra_count_check == 0:
                    diag.pop("low_recall_confidence", None)
                    remaining_triggers = {k: v for k, v in diag.items() if v}
                    if not remaining_triggers:
                        clarify["needs_clarification"] = False
            except Exception:
                pass

        if clarify.get("needs_clarification"):
            return _build_clarify_response(clarify, question_text, target_control, db)

        # -- Step 1: Extract + validate entities --
        entities = list(tier1.valid_entities)
        clarify_entities = list(clarify.get("intent", {}).get("entities", []))
        entities = list(dict.fromkeys(entities + clarify_entities))
        if target_control and target_control not in entities:
            entities.insert(0, target_control)

        invalid_entities = list(tier1.unknown_entities)
        _corpus_has_data = True
        try:
            _corpus_has_data = db.collection("sparta_qra").count() > 0
        except Exception:
            pass

        # -- Step 2: Query planning --
        bridges = clarify.get("taxonomy", {}).get("merged_bridges", [])
        query_plan = _plan_query_strategy(question_text, entities, bridges, episodic_context)
        strategy = query_plan.get("strategy", ["QRA_LOOKUP", "BM25_SEARCH"])

        if query_plan.get("needs_clarify"):
            return _build_clarify_response(clarify, question_text, target_control, db)

        # -- Step 3: Retrieve via /memory --
        qras = []
        lanes_used = []
        related_controls = []

        if "EPISODIC_REUSE" in strategy and episodic_context:
            lanes_used.append("episodic_reuse")

        recall_query = question_text
        if entities:
            recall_query = f"{' '.join(entities[:3])}: {question_text}"

        try:
            from graph_memory.api import MemoryClient
            _mc = MemoryClient(scope="sparta", k=10)
            recall_entities = [target_control] if target_control else (entities[:3] if entities else None)
            # Expand collections when evidence shows relevant data exists
            recall_collections = ["sparta_qras", "sparta_controls"]
            if evidence.get("lean4_status", {}).get("proven", 0) > 0:
                recall_collections.append("lean4_autoformalization")
            if evidence.get("framework_coverage", {}):
                recall_collections.append("datalake_chunks")

            recall_result = _mc.recall(
                q=recall_query, k=10,
                collections=recall_collections,
                tags=bridges if bridges else None,
                entities=recall_entities,
            )
            for item in recall_result.get("items", []):
                item_key = item.get("_key", "")
                if not item_key or item_key in _exclude:
                    continue

                # Extract ALL /memory scores per QRA (not just BM25)
                _scores = item.get("scores", {})
                _retrieval_card = {
                    "bm25": round(_scores.get("bm25", 0.0), 3),
                    "dense": round(_scores.get("dense", 0.0), 3),
                    "graph": round(_scores.get("graph", 0.0), 3),
                    "freshness": round(_scores.get("freshness", 0.0), 3),
                    "composite": round(
                        sum(_scores.values()) / max(len(_scores), 1), 3
                    ) if _scores else 0.0,
                    "source_collection": item.get("source", "unknown"),
                    "graph_hops": item.get("graph_depth", 0),
                }

                if item.get("source") == "sparta_controls":
                    ctrl_id = item.get("control_id", "")
                    ctrl_desc = item.get("description", "")
                    ctrl_name = item.get("name", "")
                    if ctrl_id and ctrl_id not in related_controls:
                        related_controls.append(ctrl_id)
                    qras.append({
                        "_key": item_key,
                        "question": f"What is {ctrl_id}?" if ctrl_id else ctrl_name,
                        "answer": ctrl_desc or ctrl_name,
                        "control_id": ctrl_id,
                        "grounding_score": _scores.get("bm25", 0.3),
                        "sparta_techniques": [],
                        "sparta_countermeasures": [],
                        "conceptual_tags": [],
                        "_source": "memory_control",
                        "control_type": item.get("control_type", ""),
                        "source_framework": item.get("source_framework", ""),
                        "referencing_chunks": item.get("referencing_chunks", []),
                        "retrieval": _retrieval_card,
                    })
                else:
                    qras.append({
                        "_key": item_key,
                        "question": item.get("question", item.get("problem", item.get("title", ""))),
                        "answer": item.get("answer", item.get("solution", item.get("content", ""))),
                        "control_id": item.get("control_id", ""),
                        "grounding_score": item.get("grounding_score", _scores.get("bm25", 0.5)),
                        "sparta_techniques": item.get("sparta_techniques", []),
                        "sparta_countermeasures": item.get("sparta_countermeasures", []),
                        "conceptual_tags": item.get("conceptual_tags", []),
                        "_source": item.get("source", "memory_recall"),
                        "retrieval": _retrieval_card,
                    })

            if qras:
                lanes_used.append("memory_recall")
        except Exception as e:
            logger.warning(f"/memory recall failed: {e}")

        if not qras:
            return _build_no_coverage_response(
                question_text, target_control, entities, related_controls, db,
            )

        # -- Step 3.5a: Post-retrieval entity filter --
        filter_entities = [target_control] if target_control else entities[:3] if entities else []
        if filter_entities:
            entity_set = {e.upper() for e in filter_entities}

            def _entity_coverage(q: Dict) -> int:
                text = (
                    q.get("answer", "") + " " +
                    q.get("question", "") + " " +
                    q.get("control_id", "")
                ).upper()
                return sum(1 for e in entity_set if e in text)

            for q in qras:
                cov = _entity_coverage(q)
                if cov > 0:
                    q["_entity_matched"] = True
                    q["_entity_coverage"] = cov

            entity_matched = [q for q in qras if q.get("_entity_matched")]
            if entity_matched:
                entity_matched.sort(key=lambda q: -q.get("_entity_coverage", 0))
                matched_keys = {q["_key"] for q in entity_matched}
                rest = [q for q in qras if q["_key"] not in matched_keys]
                qras = entity_matched + rest
                lanes_used.append("entity_filter")
                logger.info(
                    f"Entity filter: {len(entity_matched)} matched "
                    f"{entity_set} (max_cov={entity_matched[0].get('_entity_coverage', 0)}), "
                    f"{len(rest)} supplementary"
                )

        # -- Step 3.5b: Rerank by bridge overlap --
        if bridges:
            qras = _rerank_by_bridge_overlap(qras, bridges)
            lanes_used.append("bridge_rerank")

        # -- Step 4: Labeled synthesis --
        synth_limit = 5
        all_techniques = []
        all_cms = []
        for qra in qras[:synth_limit]:
            for t in qra.get("sparta_techniques") or []:
                tid = t.get("id", "") if isinstance(t, dict) else str(t)
                if tid and tid not in all_techniques:
                    all_techniques.append(tid)
            for cm in qra.get("sparta_countermeasures") or []:
                cmid = cm.get("id", "") if isinstance(cm, dict) else str(cm)
                if cmid and cmid not in all_cms:
                    all_cms.append(cmid)

        labeled_evidence = _labeled_synthesize(
            question_text, target_control, qras[:synth_limit], related_controls, entities,
        )

        # -- Step 4b: LLM reasoning synthesis over labeled evidence --
        combined = _reasoning_synthesize(
            question=question_text,
            labeled_evidence=labeled_evidence,
            bridges=bridges or [],
            entities=entities,
            related_controls=related_controls,
        )
        if combined != labeled_evidence:
            lanes_used.append("llm_reasoning")

        # -- POST-ANSWER HALLUCINATION GATE --
        answer_hallucinated = []
        if _HAS_QUALITY_UTILS and _corpus_has_data:
            answer_entities = _extract_entity_ids(combined)
            if answer_entities:
                answer_validity = _validate_entities_with_parents(answer_entities, db)
                answer_hallucinated = [
                    e for e in answer_entities if not answer_validity.get(e, True)
                ]
                if answer_hallucinated:
                    logger.warning(
                        f"Answer contains non-existent entities: {answer_hallucinated}. "
                        f"Filtering QRAs and re-synthesizing."
                    )
                    clean_qras = [
                        q for q in qras[:3]
                        if q.get("control_id", "") not in answer_hallucinated
                    ]
                    clean_evidence = _labeled_synthesize(
                        question_text, target_control, clean_qras,
                        related_controls, entities,
                    )
                    combined = _reasoning_synthesize(
                        question=question_text,
                        labeled_evidence=clean_evidence,
                        bridges=bridges or [],
                        entities=entities,
                        related_controls=related_controls,
                    )

        if episodic_context and "episodic_reuse" in lanes_used:
            combined = f"[EPISODIC] I've addressed a similar question before:\n{episodic_context[:300]}\n\n{combined}"

        # Compute bridge overlap stats for process-aware grading
        bridge_overlap_count = 0
        bridge_tags_matched = []
        if bridges and qras:
            bridge_set = set(b.lower() for b in bridges)
            for q in qras[:10]:
                tags = q.get("conceptual_tags") or []
                overlap = bridge_set & set(t.lower() for t in tags)
                bridge_overlap_count += len(overlap)
                bridge_tags_matched.extend(overlap)
            bridge_tags_matched = list(dict.fromkeys(bridge_tags_matched))

        # Compute richness from retrieved QRAs when no entity IDs were extracted
        # (e.g., taxonomy gap questions that go through semantic search)
        if not evidence.get("richness_score") and qras:
            qra_cids = {q.get("control_id", "") for q in qras if q.get("control_id")}
            retrieved_richness = min(len(qras) / 10.0, 1.0) * 0.50
            retrieved_richness += min(len(qra_cids) / 5.0, 1.0) * 0.30
            retrieved_richness += min(len(related_controls) / 5.0, 1.0) * 0.20
            evidence = dict(evidence) if evidence else {}
            evidence["richness_score"] = min(retrieved_richness, 1.0)
            evidence["richness_source"] = "retrieved_qras"

        # Build per-QRA retrieval cards for traceability
        _retrieval_cards = []
        for q in qras[:synth_limit]:
            _card = {
                "qra_key": q["_key"],
                "control_id": q.get("control_id", ""),
                "question_preview": q.get("question", "")[:80],
                "retrieval": q.get("retrieval", {}),
                "bridge_overlap": 0,
                "label": "CONTROL-CONTEXT" if q.get("_source") == "memory_control" else "QRA-GROUNDED",
            }
            # Per-QRA bridge overlap
            if bridges:
                qtags = set(t.lower() for t in (q.get("conceptual_tags") or []))
                bset = set(b.lower() for b in bridges)
                _card["bridge_overlap"] = len(qtags & bset)
            # Determine label from answer text labels
            if q.get("_source") == "memory_control":
                _card["label"] = "CONTROL-CONTEXT"
            elif q.get("retrieval", {}).get("graph_hops", 0) > 0:
                _card["label"] = "GRAPH-INFERRED"
            else:
                _card["label"] = "QRA-GROUNDED"
            _retrieval_cards.append(_card)

        result = {
            "answered": True,
            "answer_text": combined,
            "qra_count": len(qras),
            "action": "QUERY",
            "sparta_techniques": all_techniques,
            "sparta_countermeasures": all_cms,
            "source_keys": [q["_key"] for q in qras[:10]],
            "related_controls": related_controls,
            "lanes_used": lanes_used,
            "query_plan": query_plan,
            "quality": {},
            # Process signals for grading
            "evidence": evidence,
            "bridge_overlap_count": bridge_overlap_count,
            "bridge_tags_matched": bridge_tags_matched[:10],
            # Per-QRA retrieval cards for traceability
            "retrieval_cards": _retrieval_cards,
        }
        if invalid_entities:
            result["invalid_entities"] = invalid_entities
        if answer_hallucinated:
            result["hallucinated_entities"] = answer_hallucinated
        return result

    except Exception as e:
        logger.warning(f"SPARTA answer lookup failed: {e}")
        return {
            "answered": False,
            "answer_text": f"System error during QRA lookup: {e}",
            "qra_count": 0,
            "action": "ERROR",
            "sparta_techniques": [],
            "sparta_countermeasures": [],
            "source_keys": [],
        }
