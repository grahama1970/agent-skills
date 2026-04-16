"""SPARTA system response — Brandon's 2-tier retrieval pipeline.

Contains the main _sparta_answer() function that orchestrates Tier 1 fast
lookup, episodic check, clarify logic, query planning, /memory recall,
entity filtering, bridge reranking, and labeled synthesis.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from loguru import logger

from sparta_stress_test.retrieval import (
    _build_clarify_response,
    _build_no_coverage_response,
    _call_scillm,
    _execute_skill_chain,
    _extract_entity_ids,
    _get_db,
    _labeled_synthesize,
    _plan_query_strategy,
    _rerank_by_bridge_overlap,
    _steer_control_only,
    _steer_unknown_entity,
    _suggest_skill,
    _tier1_lookup,
    _validate_entities_with_parents,
    _HAS_QUALITY_UTILS,
)
from sparta_stress_test.grading import _recall_episodic_context


def _sparta_answer(
    question_text: str,
    target_control: Optional[str] = None,
    exclude_keys: Optional[List[str]] = None,
    difficulty: str = "medium",
    expected_action: str = "QUERY",
) -> Dict:
    """Brandon's 2-tier retrieval with conversation steering.

    Tier 1 (fast, every turn): Exact control_id lookup + classification.
      Routes: SKILL_INVOKE, SKILL_SUGGEST, CONTROL_ONLY, UNKNOWN_ENTITY -> short-circuit
    Tier 2 (deep, only if HAS_QRAS or NO_ENTITIES): Full /memory recall.

    Step 0:  Tier 1 fast lookup (ControlCatalog, QRA counts, graph neighbors)
    Step 0a: Episodic check -- "Have I answered this before?"
    Step 0b: /memory clarify -- "Is this ambiguous?"
    Step 1:  Extract + validate entities
    Step 2:  Brandon plans which AQL calls + skills to compose
    Step 3:  Execute via /memory recall
    Step 4:  Labeled synthesis with provenance tags

    Returns dict with: answered, answer_text, qra_count, techniques,
    countermeasures, source_keys, lanes_used, query_plan.
    """
    try:
        db = _get_db()
        _exclude = list(exclude_keys or [])

        # -- Tier 1: Fast exact lookup (runs BEFORE any LLM call) --
        tier1 = _tier1_lookup(question_text, target_control, db)
        logger.debug(
            f"Tier 1: {tier1.classification} "
            f"valid={tier1.valid_entities[:3]} "
            f"qra_counts={tier1.qra_counts} "
            f"unknown={tier1.unknown_entities[:3]}"
        )

        # Short-circuit routes -- no LLM needed
        if tier1.classification == "SKILL_INVOKE":
            return _execute_skill_chain(tier1.skill_refs, question_text)

        if tier1.classification == "SKILL_SUGGEST":
            return _suggest_skill(tier1.skill_refs, question_text)

        if tier1.classification == "UNKNOWN_ENTITY":
            return _steer_unknown_entity(tier1, question_text)

        if tier1.classification == "CONTROL_ONLY":
            return _steer_control_only(tier1, question_text, db)

        # For HAS_QRAS, NO_ENTITIES, AMBIGUOUS -> continue to Tier 2 deep recall

        # -- Step 0a: Episodic check -- "Have I answered this before?" --
        episodic_context = _recall_episodic_context(question_text)

        # -- Step 0b: /memory clarify -- "Is this ambiguous?" --
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
        # evidence instead of blunt entity-skip. Rich coverage = answer directly,
        # sparse coverage = keep clarification, middle = respect original decision.
        evidence = clarify.get("evidence", {})
        richness = evidence.get("richness_score", 0.0)

        if tier1.valid_entities or target_control:
            if richness >= 0.4:
                # Rich coverage → answer directly
                clarify["needs_clarification"] = False
                logger.debug(
                    f"Skipping clarify -- richness={richness:.2f}, "
                    f"entities={tier1.valid_entities[:3] or [target_control]}"
                )
            elif richness < 0.2 and clarify.get("needs_clarification"):
                # Sparse → keep clarification
                logger.debug(
                    f"Keeping clarify -- sparse richness={richness:.2f}"
                )
            else:
                # Middle ground or no evidence yet (richness=0 from fallback) →
                # default to answering if entities found (backward compat)
                clarify["needs_clarification"] = False
                logger.debug(
                    f"Skipping clarify -- entities found, richness={richness:.2f}"
                )

        # Guard 2: if all SPARTA collections are empty, low_recall_confidence
        # will fire on every query. Skip that trigger when corpus is empty.
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

        # -- Step 1: Extract + validate entities (Tier 1 pre-validated) --
        # Tier 1 already validated entities via ControlCatalog. Merge with
        # clarify intent entities for completeness.
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

        # -- Step 2: Brandon plans which AQL calls + skills to compose --
        # /scillm decides, /assistant shadows, classifiers learn.
        bridges = clarify.get("taxonomy", {}).get("merged_bridges", [])
        query_plan = _plan_query_strategy(question_text, entities, bridges, episodic_context)
        strategy = query_plan.get("strategy", ["QRA_LOOKUP", "BM25_SEARCH"])

        # If planner says clarify, honor it
        if query_plan.get("needs_clarify"):
            return _build_clarify_response(clarify, question_text, target_control, db)

        # -- Step 3: Retrieve via /memory (the ONLY retrieval layer) --
        # /memory recall handles BM25, semantic embedding, graph traversal,
        # and RecallSource routing (sparta_qras + sparta_controls) in one call.
        # No bespoke AQL -- /memory IS the universal retrieval layer.
        qras = []
        lanes_used = []
        related_controls = []

        # EPISODIC_REUSE -- if Brandon answered this before, start with that
        if "EPISODIC_REUSE" in strategy and episodic_context:
            lanes_used.append("episodic_reuse")

        # Build query with entity context for /memory
        recall_query = question_text
        if entities:
            recall_query = f"{' '.join(entities[:3])}: {question_text}"

        try:
            from graph_memory.api import MemoryClient
            _mc = MemoryClient(scope="sparta", k=10)
            # Use target_control as the primary entity for recall -- not the
            # accumulated entities from follow-up text (which includes all
            # control IDs Brandon mentioned, diluting the search).
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

                if item.get("source") == "sparta_controls":
                    # Controls provide context, not answers
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
                        "grounding_score": item.get("scores", {}).get("bm25", 0.3),
                        "sparta_techniques": [],
                        "sparta_countermeasures": [],
                        "conceptual_tags": [],
                        "_source": "memory_control",
                        "control_type": item.get("control_type", ""),
                        "source_framework": item.get("source_framework", ""),
                        "referencing_chunks": item.get("referencing_chunks", []),
                    })
                else:
                    # QRA or lesson -- blessed answer content
                    qras.append({
                        "_key": item_key,
                        "question": item.get("question", item.get("problem", item.get("title", ""))),
                        "answer": item.get("answer", item.get("solution", item.get("content", ""))),
                        "control_id": item.get("control_id", ""),
                        "grounding_score": item.get("grounding_score", item.get("scores", {}).get("bm25", 0.5)),
                        "sparta_techniques": item.get("sparta_techniques", []),
                        "sparta_countermeasures": item.get("sparta_countermeasures", []),
                        "conceptual_tags": item.get("conceptual_tags", []),
                        "_source": item.get("source", "memory_recall"),
                    })

            if qras:
                lanes_used.append("memory_recall")
        except Exception as e:
            logger.warning(f"/memory recall failed: {e}")

        # No results from any lane -> honest no-coverage response
        if not qras:
            return _build_no_coverage_response(
                question_text, target_control, entities, related_controls, db,
            )

        # -- Step 3.5a: Post-retrieval entity filter --
        # Prioritize QRAs that mention the controls the persona asked about.
        # Use target_control (not accumulated entities from follow-up text)
        # to avoid dilution from control IDs mentioned in Brandon's answers.
        filter_entities = [target_control] if target_control else entities[:3] if entities else []
        if filter_entities:
            entity_set = {e.upper() for e in filter_entities}

            def _entity_coverage(q: Dict) -> int:
                """Count how many question entities appear in this QRA."""
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
                # Sort by coverage DESC -- QRAs mentioning MORE controls first
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

        # -- Step 3.5b: Rerank QRAs by taxonomy bridge overlap --
        # QRAs whose conceptual_tags intersect the question's bridges
        # float to top -- blessed answers aligned to the question's domain.
        if bridges:
            qras = _rerank_by_bridge_overlap(qras, bridges)
            lanes_used.append("bridge_rerank")

        # -- Step 4: Labeled synthesis --
        # Pass up to 5 QRAs (not 3) -- the corpus has rich implementation
        # details that personas need to see. Truncating to 3 loses the
        # specific mechanisms (digital signatures, crypto verification, etc.)
        # that make answers complete.
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

        combined = _labeled_synthesize(
            question_text, target_control, qras[:synth_limit], related_controls, entities,
        )

        # --- POST-ANSWER HALLUCINATION GATE (every turn, deterministic) ---
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
                    combined = _labeled_synthesize(
                        question_text, target_control, clean_qras,
                        related_controls, entities,
                    )

        # Prepend episodic context if Brandon answered this before
        if episodic_context and "episodic_reuse" in lanes_used:
            combined = f"[EPISODIC] I've addressed a similar question before:\n{episodic_context[:300]}\n\n{combined}"

        result = {
            "answered": True,
            "answer_text": combined,
            "qra_count": len(qras),
            "action": "QUERY",
            "sparta_techniques": all_techniques,
            "sparta_countermeasures": all_cms,
            "source_keys": [q["_key"] for q in qras[:3]],
            "related_controls": related_controls,
            "lanes_used": lanes_used,
            "query_plan": query_plan,
            "quality": {},
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
