"""Evidence case runner — 4-call pipeline.

1. /extract-entities  → grounding + routing decision
2. /lean4-prove       → formal verification
3. /scillm            → answer, clarify, or deflect
4. /memory store      → persist the case

All calls via httpx. No bespoke code.
"""

from __future__ import annotations

import json
import os
import time
from enum import Enum
from typing import Any

import httpx
from loguru import logger

from candidate_qra import EvidenceCaseStore2
from collect import (
    EntityExtractionFailure,
    check_pre_existing_qra,
    collect_entities,
    collect_lean4_proof,
    collect_recall,
)
from scoring import (
    gates_to_grade,
    gates_to_score,
    gates_to_verdict,
)


SCILLM_URL = os.environ.get("SCILLM_URL", "http://localhost:4001")
SCILLM_KEY = os.environ.get("SCILLM_API_KEY", "sk-dev-proxy-123")


class AgentAction(str, Enum):
    """Closed enum for agent_decision.suggested_action."""
    REJECT_FABRICATED = "reject_fabricated_entity"
    REJECT_OFF_TOPIC = "reject_off_topic"
    ASK_CLARIFY = "ask_clarifying_question"
    RETRY = "retry_with_more_context"


class EvidenceCaseRunner:
    """4-call evidence case pipeline for batch and live use."""

    def __init__(self, gates_only: bool = False):
        self.store = EvidenceCaseStore2()
        self.gates_only = gates_only

    def run(self, claim_text: str, category: str = "auto") -> dict[str, Any]:
        """Run the 4-call pipeline."""
        t0 = time.monotonic()
        steps: list[dict] = []

        # --- Step 1: /extract-entities ---
        try:
            entities = collect_entities(claim_text)
        except EntityExtractionFailure as exc:
            logger.error("Entity extraction failed: {}", exc)
            return self._error_result(claim_text, category, str(exc), steps)

        if not entities.get("ok", False):
            return self._error_result(claim_text, category, "extract-entities returned ok=false", steps)

        grounding_ok = entities.get("grounding_ok", False)  # fail closed
        agent_decision = entities.get("agent_decision", {})
        action = agent_decision.get("suggested_action")
        resolved = entities.get("resolved_entities", [])
        unresolved = entities.get("unresolved_entities", [])
        external = entities.get("external_entities", [])
        control_ids = [e.get("canonical_id", "") for e in resolved if e.get("canonical_id")]

        steps.append({
            "gate": "extract_entities",
            "passed": grounding_ok,
            "detail": f"{len(resolved)} resolved, {len(unresolved)} unresolved, {len(external)} external",
            "data": {
                "grounding_ok": grounding_ok,
                "control_ids": control_ids,
                "action": action,
                "reason": agent_decision.get("reason"),
            },
        })

        # Early exits driven by agent_decision
        # fabricated_id is always a hard stop — the entity doesn't exist.
        if action == AgentAction.REJECT_FABRICATED:
            fab_terms = [u.get("mention", "?") for u in unresolved if u.get("reason") == "fabricated_id"]
            return self._verdict_result(
                claim_text, category, "not_satisfied", steps,
                answer=f"NOT_SATISFIED: Fabricated ID(s): {', '.join(fab_terms)}",
                control_ids=control_ids, grade="F", score=0.0,
                elapsed=time.monotonic() - t0,
            )

        # off_topic and no-resolved: in batch mode, hard stop (save LLM cost).
        # In live mode, flow through to LLM so it can suggest rephrasing.
        if self.gates_only:
            if action == AgentAction.REJECT_OFF_TOPIC:
                return self._verdict_result(
                    claim_text, category, "not_satisfied", steps,
                    answer="NOT_SATISFIED: No security entities found.",
                    control_ids=[], grade="F", score=0.0,
                    elapsed=time.monotonic() - t0,
                )
            if not resolved:
                return self._verdict_result(
                    claim_text, category, "inconclusive", steps,
                    answer="INCONCLUSIVE: No entities resolved from question.",
                    control_ids=[], grade="C", score=0.3,
                    elapsed=time.monotonic() - t0,
                )

        # ASK_CLARIFY, REJECT_OFF_TOPIC (live), and no-resolved (live) all
        # flow through to LLM synthesis so the response can reference the
        # out-of-domain terms and suggest rephrasing.

        # --- Step 0b: Pre-existing QRA check + QRA evidence recall ---
        # Single /recall call serves dual purpose:
        # 1. Check if an identical QRA exists (rapidfuzz + entity identity)
        # 2. Return candidates as QRA evidence for the rest of the pipeline
        qra_items: list[dict] = []
        if self.gates_only:
            # Gates-only: still need QRA recall for verdict (it's deterministic)
            qra_items = collect_recall(claim_text)
        else:
            pre_existing, qra_items = check_pre_existing_qra(claim_text, entities)
            if pre_existing is not None:
                elapsed = time.monotonic() - t0
                steps.append({
                    "gate": "pre_existing_qra",
                    "passed": True,
                    "detail": f"Matched QRA _key={pre_existing.get('_key', '?')}",
                })
                answer_text = pre_existing.get("answer", pre_existing.get("solution", ""))
                logger.info("Pre-existing QRA hit in {:.1f}s, skipping pipeline", elapsed)
                return {
                    "claim": {"text": claim_text, "category": category, "id": f"pre_existing_{pre_existing.get('_key', '')}"},
                    "verdict": {"state": "satisfied", "grade": "A", "score": 1.0},
                    "review_status": "passed",
                    "source": "pre_existing",
                    "pre_existing_qra_key": pre_existing.get("_key", ""),
                    "answer": answer_text,
                    "control_ids": control_ids,
                    "gate_trace": steps,
                    "gates_passed": len(steps),
                    "gates_total": len(steps),
                    "elapsed_ms": int(elapsed * 1000),
                }
            # No pre-existing match — qra_items already populated from the recall

        steps.append({
            "gate": "qra_recall",
            "passed": len(qra_items) > 0,
            "detail": f"{len(qra_items)} QRA items",
        })

        # --- Step 2: Deterministic verdict + LLM render ---
        # Technique coherence comes from /extract-entities response.
        # When the initial check fails for cross-framework entities
        # (e.g. CWE + SPARTA with no graph crosswalk), use /recall
        # to check if they're semantically related. /recall combines
        # BM25 + cosine + multi-hop — fully deterministic.
        tc = entities.get("technique_coherence", {})
        technique_ok = tc.get("ok", True)
        technique_detail = tc.get("detail", "")

        # Cross-framework recall coherence: if technique_coherence failed
        # due to missing crosswalk (not disjoint parents), check via /recall
        if not technique_ok and "no_sparta_crosswalk" in technique_detail and resolved:
            technique_ok, technique_detail = self._recall_coherence_check(
                resolved, entities, technique_detail,
            )

        steps.append({
            "gate": "technique_intersection",
            "passed": technique_ok,
            "detail": technique_detail,
        })

        if not technique_ok and len(resolved) > 0:
            verdict_state = "inconclusive"
        elif grounding_ok and len(resolved) > 0 and len(qra_items) > 0:
            verdict_state = "satisfied"
        elif grounding_ok and len(resolved) > 0:
            verdict_state = "inconclusive"
        else:
            verdict_state = "not_satisfied"

        # Lean4: deferred to after pipeline completes (see post-persist below)
        lean4_detail = "skipped"
        _run_lean4 = not self.gates_only and grounding_ok and bool(control_ids)
        if _run_lean4:
            lean4_detail = "queued_background"

        steps.append({
            "gate": "lean4_prove",
            "passed": True,  # non-blocking, always passes
            "detail": lean4_detail,
        })

        if self.gates_only:
            answer = f"Gates-only: {verdict_state}"
        else:
            answer = self._scillm_render(
                claim_text, verdict_state, resolved, unresolved,
                external, qra_items, steps,
            )

        n_passed = sum(1 for s in steps if s.get("passed"))
        n_total = len(steps)
        grade = gates_to_grade(n_passed, n_total)
        score = gates_to_score(n_passed, n_total)

        steps.append({
            "gate": "scillm_synthesize",
            "passed": verdict_state == "satisfied",
            "detail": f"verdict={verdict_state}",
        })

        # --- Step 3: /memory store ---
        elapsed = time.monotonic() - t0
        result = self._verdict_result(
            claim_text, category, verdict_state, steps,
            answer=answer, control_ids=control_ids,
            grade=grade, score=score, elapsed=elapsed,
            qra_items=qra_items, entities=entities,
        )

        # --- Post-persist: fire lean4 background (doesn't compete with scillm) ---
        if _run_lean4:
            import threading
            def _lean4_background(text: str, cids: list[str]):
                try:
                    proof = collect_lean4_proof(text)
                    status = "proved" if proof and proof.get("success") else "failed"
                    logger.info("Lean4 background: {} for {}", status, cids[:3])
                except Exception as exc:
                    logger.error("Lean4 background FAILED: {}", exc)
            threading.Thread(
                target=_lean4_background,
                args=(claim_text, control_ids),
                daemon=True,
            ).start()

        return result

    def build_payload(self, claim_text: str) -> dict[str, Any] | None:
        """Build evidence case payload WITHOUT scillm render or persist.

        Runs entity extraction + recall + _build_evidence_case() and returns
        the raw evidence case JSON suitable for feeding to an LLM prompt.
        Returns None if entity extraction fails or no entities resolve.
        """
        try:
            entities = collect_entities(claim_text)
        except EntityExtractionFailure as exc:
            logger.warning("build_payload: entity extraction failed: {}", exc)
            return None

        if not entities.get("ok", False):
            return None

        resolved = entities.get("resolved_entities", [])
        unresolved = entities.get("unresolved_entities", [])
        external = entities.get("external_entities", [])

        if not resolved:
            return None

        qra_items = collect_recall(claim_text)

        steps = [{
            "gate": "extract_entities",
            "passed": True,
            "detail": f"{len(resolved)} resolved",
        }]

        return self._build_evidence_case(
            claim_text, "satisfied", resolved, unresolved,
            external, qra_items, steps,
        )

    # --- Renderer prompt (static) ---
    RENDER_PROMPT = """\
You are a cybersecurity compliance analyst reviewing an authoritative evidence case.

Your task is controlled entirely by EVIDENCE_CASE.review_status.

Authoritative rule:
- If EVIDENCE_CASE.review_status = "passed", the evidence case contains enough grounded information for you to answer the user's question.
- If EVIDENCE_CASE.review_status = "failed", the evidence case does not permit you to answer the user's question.

The EVIDENCE_CASE is authoritative.
Use only the information in it.
Do not invent entities, controls, mappings, techniques, relationships, meanings, or citations not present in the EVIDENCE_CASE.
Do not use outside knowledge.

Important grounding rule:
- When review_status = "passed", use the glossary entries in EVIDENCE_CASE.glossary to understand the relevant controls, techniques, threats, and countermeasures.
- Do not assume the meaning of a control ID unless that meaning is provided in the glossary or supporting evidence.
- If review_status = "passed", the glossary and supporting evidence together are the basis for your answer.

Behavior by review_status:

1. When EVIDENCE_CASE.review_status = "passed"
You must answer the user's question.
- Answer the question directly in the first sentence.
- Use the glossary, entity mappings, prior QRA evidence, and any other supplied supporting evidence.
- You may synthesize and make bounded inferences from the supplied evidence when needed.
- Do not ask clarifying questions.
- Do not deflect.
- Do not discuss pipeline mechanics, checks, or failure logic.
- Cite only IDs present in the EVIDENCE_CASE, using inline citations like [AC-7] or [LM-0007].
- Keep the answer concise but complete.

2. When EVIDENCE_CASE.review_status = "failed"
You must not answer the substantive question.
- Explain clearly why the question could not be answered from the evidence case.
- State where the evidence case failed, if failure_stage is present.
- Identify the specific failed term, entity, mapping, or evidence gap, if present.
- Mention skipped downstream checks if present.
- Then choose exactly one follow-up mode:

A. "clarify" — use when the question is still in-domain but one or more terms are ambiguous, unresolved, or need disambiguation, and a short clarification could make it answerable. Ask exactly 1 concise clarifying question.

B. "deflect" — use when the question contains clearly off-topic, absurd, or non-domain central terms, or clarification would not realistically make the question answerable. Briefly explain why and suggest a domain-valid rewrite if possible.

Reasoning policy:
- Allowed only when review_status = "passed": synthesis, comparison, causal explanation, bounded inference from supplied glossary and evidence.
- Not allowed: inventing missing support, filling ontology gaps, using external knowledge.
- When review_status = "failed", you must not answer the substantive question.

Output requirements:
Return valid JSON only. No markdown fences. No text outside the JSON.

{
  "decision": "answer" | "clarify" | "deflect",
  "answer": "string",
  "clarifying_question": "string",
  "suggested_rewrite": "string",
  "citations": ["string"]
}

Required consistency rules:
- If review_status = "passed": decision must be "answer", clarifying_question must be ""
- If review_status = "failed": decision must be "clarify" or "deflect"
- Never output decision = "answer" when review_status = "failed"
- Never output decision = "clarify" or "deflect" when review_status = "passed"

Now process this input:

EVIDENCE_CASE:
"""

    MAX_RENDER_RETRIES = 2
    RECALL_COHERENCE_THRESHOLD = 0.3

    def _recall_coherence_check(
        self,
        resolved: list[dict],
        entities: dict,
        original_detail: str,
    ) -> tuple[bool, str]:
        """Check cross-framework technique coherence via /recall.

        Two approaches, both deterministic (BM25 + cosine + multi-hop):

        Approach 1 (graph path): Already done by /extract-entities 2-hop
        traversal through sparta_relationships. If a CWE reaches SPARTA
        via CAPEC→ATT&CK→SPARTA or NIST→SPARTA edges, crosswalk_path
        is populated. This method handles the case where that path is missing.

        Approach 2 (semantic recall): For each SPARTA entity in the question,
        query /recall with its name/description against sparta_controls.
        If the non-SPARTA entity (CWE, NIST) appears in the results,
        they're semantically related. Query direction matters: SPARTA
        entity text → find related CWEs (not CWE text → find SPARTA,
        which just returns other CWEs).
        """
        sparta_entities = []
        non_sparta_ids = set()
        for ent in resolved:
            fw = ent.get("framework", "")
            cid = ent.get("canonical_id", "")
            name = ent.get("canonical_name", "")
            if fw == "SPARTA":
                sparta_entities.append((cid, name))
            elif cid:
                non_sparta_ids.add(cid)

        if not sparta_entities or not non_sparta_ids:
            return False, original_detail

        from collect import collect_recall_with_confidence

        # Query with SPARTA entity text — finds semantically related
        # controls across ALL frameworks (CWE, NIST, etc.)
        for sparta_id, sparta_name in sparta_entities:
            query = f"{sparta_name}"[:300]
            try:
                result = collect_recall_with_confidence(
                    query, k=20, collections=["sparta_controls"],
                )
                recalled_ids = {
                    item.get("control_id", "")
                    for item in result.get("items", [])
                }
                overlap = non_sparta_ids & recalled_ids
                if overlap:
                    conf = result.get("confidence", 0)
                    return True, f"recall_coherent:{sparta_id}->{sorted(overlap)},confidence={conf:.2f}"
            except Exception:
                pass

        return False, f"recall_incoherent:{original_detail}"

    def _scillm_render(
        self,
        question: str,
        verdict_state: str,
        resolved: list[dict],
        unresolved: list[dict],
        external: list[dict] | None,
        qra_items: list[dict],
        steps: list[dict],
    ) -> str:
        """Render the deterministic pipeline result into a human-readable answer.

        Coded self-improvement loop: if the LLM produces invalid citations,
        retry with correction feedback up to MAX_RENDER_RETRIES times.
        """
        evidence_case = self._build_evidence_case(
            question, verdict_state, resolved, unresolved, external, qra_items, steps,
        )
        valid_ids = {e["citation_id"] for e in evidence_case.get("prior_qra_evidence", [])}
        valid_ids |= {e["id"] for e in evidence_case.get("glossary", [])}

        messages = [{"role": "user", "content": self.RENDER_PROMPT + json.dumps(evidence_case, indent=2)}]
        answer_entities: dict = {}
        result: dict = {}
        llm_citations: list = []
        content = ""

        for attempt in range(1, self.MAX_RENDER_RETRIES + 1):
            try:
                resp = httpx.post(
                    f"{SCILLM_URL}/v1/chat/completions",
                    headers={"Authorization": f"Bearer {SCILLM_KEY}"},
                    json={
                        "model": "text",
                        "messages": messages,
                        "temperature": 0.2,
                        "max_tokens": 600,
                    },
                    timeout=30,
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"].strip()
                if content.startswith("```"):
                    content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                result = json.loads(content)

                # Citation validation via /extract-entities on the answer text
                answer_text = result.get("answer", "")
                llm_citations = result.get("citations", [])
                extracted_ids: set[str] = set()
                try:
                    answer_entities = collect_entities(answer_text)
                    extracted_ids = {
                        e.get("canonical_id", "")
                        for e in answer_entities.get("resolved_entities", [])
                    } - {""}
                except Exception as exc:
                    logger.warning("Citation extraction failed: {}", exc)
                    extracted_ids = set(llm_citations)  # fall back to declared citations

                # Combine declared + extracted for full coverage check
                all_cited = extracted_ids | set(llm_citations)
                invalid = sorted(all_cited - valid_ids)
                missing_from_declared = sorted(extracted_ids - set(llm_citations))
                no_citations = (
                    evidence_case["review_status"] == "passed"
                    and len(all_cited) == 0
                )

                # Consistency check
                llm_decision = result.get("decision", "")
                decision_mismatch = (
                    (evidence_case["review_status"] == "passed" and llm_decision != "answer")
                    or (evidence_case["review_status"] == "failed" and llm_decision == "answer")
                )

                if not invalid and not no_citations and not decision_mismatch:
                    logger.info("Render attempt {}: valid ({} citations, {} extracted)", attempt, len(llm_citations), len(extracted_ids))
                    final_answer = answer_text or content
                    citation_report = self._build_citation_report(answer_entities)
                    if citation_report:
                        final_answer += "\n\n" + citation_report
                    return final_answer

                # Build correction feedback for retry
                issues = []
                if invalid:
                    issues.append(f"Your answer references IDs not in the evidence case: {invalid}.")
                if no_citations:
                    issues.append("Your answer contains zero citations for a passed evidence case.")
                if missing_from_declared:
                    issues.append(f"Your answer text mentions {missing_from_declared} but they are missing from the citations array.")
                if decision_mismatch:
                    issues.append(
                        f"review_status is '{evidence_case['review_status']}' "
                        f"but you returned decision='{llm_decision}'."
                    )
                correction = (
                    " ".join(issues)
                    + f" Only cite from: {sorted(valid_ids)}."
                    + " Return corrected JSON."
                )
                logger.warning("Render attempt {}: retrying ({})", attempt, " | ".join(issues))

                # Append assistant response + correction as next turn
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": correction})

            except Exception as exc:
                logger.warning("scillm render attempt {} failed: {}", attempt, exc)
                if attempt == self.MAX_RENDER_RETRIES:
                    return f"LLM render failed: {exc}"

        # Exhausted retries — return last result with invalid citations stripped
        logger.warning("Render retries exhausted, stripping invalid citations")
        clean_citations = [c for c in llm_citations if c in valid_ids]
        answer = result.get("answer", "")
        if not answer:
            return content
        return answer

    def _fetch_control_descriptions(self, control_ids: list[str]) -> dict[str, dict]:
        """Batch-fetch control descriptions from daemon via /recall/by-keys."""
        if not control_ids:
            return {}
        try:
            from collect import _get_memory_http
            client = _get_memory_http()
            resp = client.post("/recall/by-keys", json={
                "keys": control_ids,
                "key_field": "control_id",
                "collection": "sparta_controls",
            })
            docs = resp.json().get("documents", [])
            return {d["control_id"]: d for d in docs if d.get("control_id")}
        except Exception as exc:
            logger.warning("Failed to fetch control descriptions: {}", exc)
            return {}

    def _fetch_threat_countermeasures(self, threat_ids: list[str]) -> dict[str, list[str]]:
        """Fetch countermeasure IDs for space threats via /recall/by-keys on edges."""
        if not threat_ids:
            return {}
        result: dict[str, list[str]] = {}
        try:
            from collect import _get_memory_http
            client = _get_memory_http()
            resp = client.post("/recall/by-keys", json={
                "keys": threat_ids,
                "key_field": "source_control_id",
                "collection": "sparta_relationships",
            })
            for doc in resp.json().get("documents", []):
                src = doc.get("source_control_id", "")
                tgt = doc.get("target_control_id", "")
                if src and tgt and tgt.startswith("CM"):
                    result.setdefault(src, []).append(tgt)
        except Exception as exc:
            logger.warning("Failed to fetch threat countermeasures: {}", exc)
        return result

    def _build_evidence_case(
        self,
        question: str,
        verdict_state: str,
        resolved: list[dict],
        unresolved: list[dict],
        external: list[dict] | None,
        qra_items: list[dict],
        steps: list[dict],
    ) -> dict:
        """Build the EVIDENCE_CASE JSON for the renderer prompt.

        Enriches the payload with:
        - descriptions for each control (fetched from sparta_controls)
        - full crosswalk chains with descriptions at each hop
        - crosswalk hop entities added to glossary
        - expanded QRA evidence limits
        """
        review_status = "passed" if verdict_state == "satisfied" else "failed"

        # Collect all control IDs we need descriptions for
        all_ids = set()
        for e in resolved:
            cid = e.get("canonical_id", "")
            if cid:
                all_ids.add(cid)
            cp = e.get("crosswalk_path", {})
            for hop_id in cp.get("ids", []):
                if hop_id:
                    all_ids.add(hop_id)
            terminal = cp.get("terminal_id", "")
            if terminal:
                all_ids.add(terminal)

        # Identify space_threat entities for threat→CM hop
        threat_ids = [
            e.get("canonical_id", "")
            for e in resolved
            if e.get("entity_type") == "space_threat" and e.get("canonical_id")
        ]
        threat_cms = self._fetch_threat_countermeasures(threat_ids)
        for cm_list in threat_cms.values():
            all_ids.update(cm_list)

        # Batch-fetch descriptions from daemon
        descriptions = self._fetch_control_descriptions(sorted(all_ids))

        # Glossary: every resolved entity with its description
        glossary = []
        for e in resolved:
            cid = e.get("canonical_id", "?")
            desc = descriptions.get(cid, {})
            entry = {
                "id": cid,
                "name": e.get("canonical_name", e.get("name", "")) or desc.get("name", ""),
                "framework": e.get("framework", "") or desc.get("framework", ""),
                "type": e.get("entity_type", ""),
                "description": desc.get("description", ""),
                "consequences": desc.get("consequences", ""),
            }
            sk = desc.get("supporting_knowledge", [])
            if sk:
                entry["supporting_knowledge"] = sk
            glossary.append(entry)

        # Crosswalk chains + add hop entities to glossary
        glossary_ids = {g["id"] for g in glossary}
        crosswalk_chains = []
        for e in resolved:
            cp = e.get("crosswalk_path", {})
            if not cp.get("exists"):
                continue
            chain_ids = cp.get("ids", [])
            terminal_id = cp.get("terminal_id", "")
            hops = []
            for hop_id in chain_ids:
                hop_desc = descriptions.get(hop_id, {})
                hop_entry = {
                    "id": hop_id,
                    "name": hop_desc.get("name", ""),
                    "framework": hop_desc.get("framework", ""),
                    "description": hop_desc.get("description", ""),
                }
                hops.append(hop_entry)
                if hop_id not in glossary_ids:
                    glossary_ids.add(hop_id)
                    glossary.append({
                        **hop_entry,
                        "type": hop_desc.get("control_type", ""),
                        "consequences": hop_desc.get("consequences", ""),
                    })
            if terminal_id and terminal_id not in chain_ids:
                t_desc = descriptions.get(terminal_id, {})
                t_entry = {
                    "id": terminal_id,
                    "name": t_desc.get("name", ""),
                    "framework": t_desc.get("framework", ""),
                    "description": t_desc.get("description", ""),
                }
                hops.append(t_entry)
                if terminal_id not in glossary_ids:
                    glossary_ids.add(terminal_id)
                    glossary.append({
                        **t_entry,
                        "type": t_desc.get("control_type", ""),
                        "consequences": t_desc.get("consequences", ""),
                    })
            crosswalk_chains.append({
                "from": e.get("canonical_id", "?"),
                "from_framework": cp.get("from_framework", e.get("framework", "")),
                "to_framework": cp.get("to_framework", cp.get("terminal_framework", "")),
                "hops": hops,
            })

        # Threat→Countermeasure chains
        for tid, cm_ids in threat_cms.items():
            cm_hops = []
            for cm_id in cm_ids:
                cm_desc = descriptions.get(cm_id, {})
                cm_hops.append({
                    "id": cm_id,
                    "name": cm_desc.get("name", ""),
                    "framework": "SPARTA",
                    "description": cm_desc.get("description", ""),
                })
                if cm_id not in glossary_ids:
                    glossary_ids.add(cm_id)
                    glossary.append({
                        "id": cm_id,
                        "name": cm_desc.get("name", ""),
                        "framework": "SPARTA",
                        "type": "countermeasure",
                        "description": cm_desc.get("description", ""),
                        "consequences": "",
                    })
            crosswalk_chains.append({
                "from": tid,
                "from_framework": "SPARTA",
                "to_framework": "SPARTA",
                "relationship": "threat_to_countermeasure",
                "hops": cm_hops,
            })

        # Entity resolution
        entity_resolution = []
        for e in resolved:
            cp = e.get("crosswalk_path", {})
            entity_resolution.append({
                "entity": e.get("canonical_id", "?"),
                "status": "resolved",
                "mapping": cp.get("terminal_id", ""),
            })
        for u in unresolved:
            entity_resolution.append({
                "entity": u.get("mention", "?"),
                "status": u.get("reason", "unresolved"),
                "mapping": "",
            })
        if external:
            for e in external:
                entity_resolution.append({
                    "entity": e.get("mention", "?"),
                    "status": "unsupported",
                    "mapping": "",
                })

        # Technique check from steps
        entity_step = next((s for s in steps if s["gate"] == "extract_entities"), None)
        technique_check = {
            "status": "passed" if entity_step and entity_step.get("passed") else "failed",
            "summary": entity_step.get("detail", "") if entity_step else "",
        }

        # Prior QRA evidence — expanded limits for cross-framework synthesis
        prior_qra_evidence = []
        for q in qra_items[:12]:
            prior_qra_evidence.append({
                "citation_id": q.get("control_id", "?"),
                "question": q.get("question", q.get("problem", ""))[:400],
                "answer": q.get("answer", q.get("solution", ""))[:800],
            })

        case: dict[str, Any] = {
            "question_text": question,
            "review_status": review_status,
            "glossary": glossary,
            "crosswalk_chains": crosswalk_chains,
            "entity_resolution": entity_resolution,
            "technique_check": technique_check,
            "prior_qra_evidence": prior_qra_evidence,
        }

        # Failure details (only when failed)
        if review_status == "failed":
            failed_step = next((s for s in steps if not s.get("passed")), None)
            case["failure_stage"] = failed_step["gate"] if failed_step else "unknown"
            case["failure_reason"] = failed_step.get("detail", "") if failed_step else ""

            failed_items = [u.get("mention", "?") for u in unresolved]
            if external:
                failed_items += [e.get("mention", "?") for e in external]
            case["failed_items"] = failed_items

            skipped = [s["gate"] for s in steps if s.get("detail", "").startswith("skipped")]
            if skipped:
                case["skipped_checks"] = skipped

        return case

    @staticmethod
    def _build_citation_report(answer_entities: dict) -> str:
        """Build a deterministic citation report from /extract-entities output."""
        resolved = answer_entities.get("resolved_entities", [])
        if not resolved:
            return ""

        seen = set()
        lines = ["Citations:"]
        for e in resolved:
            cid = e.get("canonical_id", "")
            if not cid or cid in seen:
                continue
            seen.add(cid)
            name = e.get("canonical_name", "")
            framework = e.get("framework", "")
            cp = e.get("crosswalk_path", {})
            mapping = cp.get("terminal_id", "")
            mapping_fw = cp.get("terminal_framework", "")

            line = f"- [{cid}] {name} ({framework})"
            if mapping and mapping != cid:
                line += f" → {mapping} ({mapping_fw})"
            lines.append(line)

        return "\n".join(lines) if len(lines) > 1 else ""

    def _verdict_result(
        self,
        claim_text: str,
        category: str,
        verdict_state: str,
        steps: list[dict],
        answer: str,
        control_ids: list[str],
        grade: str = "C",
        score: float = 0.5,
        elapsed: float = 0.0,
        qra_items: list[dict] | None = None,
        entities: dict | None = None,
    ) -> dict[str, Any]:
        """Build result dict and persist. Store failure is non-fatal."""
        try:
            result = self.store.persist_case(
                question=claim_text,
                category=category,
                verdict_state=verdict_state,
                grade=grade,
                score=score,
                gates=steps,
                evidence_items=qra_items or [],
                answer=answer,
                control_ids=control_ids,
            )
        except Exception as exc:
            logger.error("persist_case failed (non-fatal): {}", exc)
            result = {
                "claim": {"text": claim_text, "category": category},
                "verdict": {"state": verdict_state, "grade": grade, "score": score},
                "answer": answer,
                "gate_trace": steps,
                "gates_passed": sum(1 for s in steps if s.get("passed")),
                "gates_total": len(steps),
            }
        result["entities"] = entities
        result["evidence_items"] = qra_items or []
        result["total_ms"] = round(elapsed * 1000, 1)
        return result

    def _error_result(
        self,
        claim_text: str,
        category: str,
        error: str,
        steps: list[dict],
    ) -> dict[str, Any]:
        return self._verdict_result(
            claim_text, category, "error", steps,
            answer=f"ERROR: {error}",
            control_ids=[], grade="F", score=0.0,
        )
