"""Individual section renderers for evidence case reports.

Split from report.py to stay under 800-line limit.
Each function renders one section of the evidence case report as markdown.
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# 1. Decomposition mermaid
# ---------------------------------------------------------------------------

def render_decomposition_mermaid(decomposition: dict | None) -> str:
    """Render Given/Then decomposition as a mermaid graph."""
    if not decomposition:
        return ""

    lines = ["```mermaid", "graph TD"]
    question = (decomposition.get("question") or "?")[:80].replace('"', "'")
    lines.append(f'  Q["{question}"]')

    given = decomposition.get("given_components", [])
    then = decomposition.get("then_components", [])

    for i, g in enumerate(given):
        gid = f"G{i}"
        label = str(g).replace('"', "'")
        lines.append(f'  {gid}["{label}"]:::given')
        lines.append(f"  Q --> {gid}")

    for i, t in enumerate(then):
        tid = f"T{i}"
        label = str(t).replace('"', "'")
        lines.append(f'  {tid}["{label}"]:::then')
        lines.append(f"  Q --> {tid}")

    lines.append("  classDef given fill:#bdf,stroke:#48a")
    lines.append("  classDef then fill:#fdb,stroke:#a84")
    lines.append("```")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. Formalization table (NO truncation)
# ---------------------------------------------------------------------------

def render_formalization_table(decomposition: dict | None) -> str:
    """Render component -> entity type -> query as markdown table."""
    if not decomposition:
        return ""

    queries = decomposition.get("component_queries", {})
    types = decomposition.get("component_entity_types", {})
    all_components = (
        decomposition.get("given_components", []) +
        decomposition.get("then_components", [])
    )

    lines = ["## Formalization", ""]
    lines.append("| Component | Entity Type | Query |")
    lines.append("|-----------|-------------|-------|")

    for comp in all_components:
        comp_str = str(comp)
        etype = types.get(comp_str, "—")
        query = queries.get(comp_str, comp_str)
        lines.append(f"| {comp_str} | {etype} | {query} |")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 3. Per-component resolution
# ---------------------------------------------------------------------------

def render_per_component_resolution(component_results: dict[str, list[dict]] | None) -> str:
    """Render per-component entity resolution tables."""
    if not component_results:
        return ""

    lines: list[str] = []
    for comp, results in component_results.items():
        lines.append(f"### {comp}")
        lines.append("")
        if not results:
            lines.append("_No results_")
            lines.append("")
            continue

        lines.append("| Control | Question | Score | Technique |")
        lines.append("|---------|----------|-------|-----------|")
        for r in results[:15]:
            cid = r.get("control_id", "—")
            q = r.get("question", "—")[:60]
            score = r.get("score", 0)
            score = float(score) if isinstance(score, (int, float)) else 0.0
            technique = r.get("technique", "—")
            lines.append(f"| {cid} | {q} | {score:.2f} | {technique} |")
        if len(results) > 15:
            lines.append(f"| ... | +{len(results) - 15} more | | |")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 4. Cross-component mermaid
# ---------------------------------------------------------------------------

def render_cross_component_mermaid(
    component_results: dict[str, list[dict]] | None,
    entities: dict | None,
    verdict_state: str = "",
) -> str:
    """Render cross-component relationship graph (shared controls + technique overlap)."""
    if not component_results or len(component_results) < 2:
        return ""

    comp_names = list(component_results.keys())

    comp_controls: dict[str, set[str]] = {}
    comp_techniques: dict[str, set[str]] = {}
    for comp, results in component_results.items():
        cids: set[str] = set()
        techs: set[str] = set()
        for r in results:
            if r.get("control_id"):
                cids.add(r["control_id"])
            if r.get("technique"):
                techs.add(r["technique"])
        comp_controls[comp] = cids
        comp_techniques[comp] = techs

    shared_controls: dict[tuple[str, str], set[str]] = {}
    shared_techniques: dict[tuple[str, str], set[str]] = {}
    for i, c1 in enumerate(comp_names):
        for c2 in comp_names[i + 1:]:
            overlap_cids = comp_controls.get(c1, set()) & comp_controls.get(c2, set())
            overlap_techs = comp_techniques.get(c1, set()) & comp_techniques.get(c2, set())
            if overlap_cids:
                shared_controls[(c1, c2)] = overlap_cids
            if overlap_techs:
                shared_techniques[(c1, c2)] = overlap_techs

    if not shared_controls and not shared_techniques:
        return ""

    lines = ["```mermaid", "graph LR"]

    safe_ids: dict[str, str] = {}
    for idx, comp in enumerate(comp_names):
        safe_id = f"C{idx}"
        safe_ids[comp] = safe_id
        label = comp[:40].replace('"', "'")
        lines.append(f'  {safe_id}["{label}"]')

    edge_idx = 0
    for (c1, c2), cids in shared_controls.items():
        cids_str = ", ".join(sorted(cids)[:3])
        if len(cids) > 3:
            cids_str += f" (+{len(cids)-3})"
        lines.append(f'  {safe_ids[c1]} -->|"controls: {cids_str}"| {safe_ids[c2]}')
        edge_idx += 1

    for (c1, c2), techs in shared_techniques.items():
        techs_str = ", ".join(sorted(techs)[:3])
        if len(techs) > 3:
            techs_str += f" (+{len(techs)-3})"
        lines.append(f'  {safe_ids[c1]} -.->|"techniques: {techs_str}"| {safe_ids[c2]}')
        edge_idx += 1

    related_pairs = []
    if isinstance(entities, dict):
        related_pairs = entities.get("related_pairs", [])
    for pair in related_pairs[:5]:
        src = pair.get("source", "")
        tgt = pair.get("target", "")
        method = pair.get("method", "relates_to")
        lines.append(f'  {src.replace("-","_")} ==>|"{method}"| {tgt.replace("-","_")}')

    lines.append("```")

    summary_parts = []
    total_shared = sum(len(v) for v in shared_controls.values())
    total_tech = sum(len(v) for v in shared_techniques.values())
    if total_shared:
        summary_parts.append(f"{total_shared} shared control(s)")
    if total_tech:
        summary_parts.append(f"{total_tech} shared technique(s)")
    if related_pairs:
        summary_parts.append(f"{len(related_pairs)} entity relationship(s)")

    lines.insert(0, f"**Cross-component links:** {', '.join(summary_parts)}\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 5. Decision transparency (why this verdict?)
# ---------------------------------------------------------------------------

def render_decision_transparency(case: dict) -> str:
    """Render the 'Why This Verdict?' table with caveats and human checks."""
    verdict = case.get("verdict", {})
    state = verdict.get("state", "unknown")
    grade = verdict.get("grade", "?")
    gate_trace = case.get("gate_trace", [])
    entities = case.get("entities", {})
    evidence = case.get("evidence", [])

    lines: list[str] = []
    lines.append("### Why This Verdict?")
    lines.append("")
    lines.append("| Factor | Value |")
    lines.append("|--------|-------|")

    gates_passed = sum(1 for g in gate_trace if g.get("passed"))
    gates_total = len(gate_trace)
    lines.append(f"| Gates passed | {gates_passed}/{gates_total} |")

    control_ids = case.get("claim", {}).get("control_ids", [])
    if control_ids:
        lines.append(f"| Controls found | {len(control_ids)} |")

    lines.append(f"| Evidence items | {len(evidence)} |")

    if isinstance(entities, dict):
        unresolved = entities.get("unresolved_terms", [])
        if unresolved:
            names = ", ".join(u.get("term", "?") for u in unresolved[:5] if isinstance(u, dict))
            lines.append(f"| Unresolved terms | {len(unresolved)}: {names} |")
        resolution_map = entities.get("resolution_map", {})
        resolved = sum(1 for v in resolution_map.values() if isinstance(v, dict) and v.get("exists"))
        if resolution_map:
            lines.append(f"| Grounding | {resolved}/{len(resolution_map)} resolved |")

    technique_bridge = False
    for g in gate_trace:
        if g.get("gate") == "step_3_technique_bridge":
            technique_bridge = g.get("passed", False)
            break
    lines.append(f"| Technique bridge | {'Yes' if technique_bridge else 'No'} |")

    lean4 = case.get("lean4_result", {})
    if lean4:
        proof_data = lean4.get("proof_data", {}) if isinstance(lean4.get("proof_data"), dict) else {}
        proved = bool(
            lean4.get("proof_success") or lean4.get("success")
            or lean4.get("verified") or proof_data.get("success")
            or proof_data.get("verified")
        )
        skipped = bool(lean4.get("proof_skipped"))
        blocked = bool(lean4.get("gate_blocked"))
        if blocked:
            lines.append("| Formal proof | BLOCKED |")
        elif skipped:
            lines.append("| Formal proof | SKIPPED |")
        elif proved:
            lines.append("| Formal proof | PROVED |")
        else:
            lines.append("| Formal proof | FAILED |")

    lines.append("")

    caveats = _build_caveats(gate_trace, entities, evidence, state, grade)
    if caveats:
        lines.append("**What Could Be Wrong:**")
        lines.append("")
        for c in caveats:
            lines.append(f"- {c}")
        lines.append("")

    checks = _build_human_checks(gate_trace, entities, evidence, state)
    if checks:
        lines.append("**What to Check:**")
        lines.append("")
        for c in checks:
            lines.append(f"- {c}")
        lines.append("")

    return "\n".join(lines)


def _build_caveats(
    gate_trace: list[dict],
    entities: dict | Any,
    evidence: list[dict],
    state: str,
    grade: str,
) -> list[str]:
    """Build list of caveats about the verdict."""
    caveats: list[str] = []

    if state == "satisfied" and grade in ("C", "D"):
        caveats.append(f"Grade is only {grade} — evidence is thin or low-confidence.")

    if isinstance(entities, dict):
        unresolved = entities.get("unresolved_terms", [])
        for u in unresolved:
            if not isinstance(u, dict):
                continue
            term = u.get("term", "?")
            utype = u.get("type", "")
            closest = u.get("closest_match", "")
            dist = u.get("distance", 1.0)
            if utype == "id_like":
                caveats.append(f"'{term}' looks like a control ID but doesn't exist in corpus"
                               + (f" (closest: {closest}, distance {dist:.2f})" if closest else ""))
            elif closest and dist < 0.3:
                caveats.append(f"'{term}' might be a misspelling of '{closest}' (distance {dist:.2f})")

    for g in gate_trace:
        if g.get("gate") == "step_3_technique_bridge" and not g.get("passed"):
            caveats.append("No technique bridge — components may be unrelated.")
        if g.get("gate") == "step_1_topic" and not g.get("passed"):
            caveats.append("Question may not be about SPARTA/space security.")

    if len(evidence) < 3 and state == "satisfied":
        caveats.append(f"Only {len(evidence)} evidence item(s) — consider adding more.")

    return caveats


def _build_human_checks(
    gate_trace: list[dict],
    entities: dict | Any,
    evidence: list[dict],
    state: str,
) -> list[str]:
    """Build list of things a human reviewer should check."""
    checks: list[str] = []

    if state == "satisfied":
        checks.append("Verify the evidence QRAs actually address the question (not just keyword match).")

    if isinstance(entities, dict):
        unresolved = entities.get("unresolved_terms", [])
        fab_count = sum(1 for u in unresolved
                        if isinstance(u, dict) and u.get("type") == "id_like")
        if fab_count > 0 and state == "satisfied":
            checks.append(f"{fab_count} term(s) look like control IDs but don't exist — is the question's premise valid?")

    for g in gate_trace:
        if g.get("gate") == "step_5_lean4":
            data = g.get("data", {})
            if data.get("gate_blocked") or data.get("proof_skipped"):
                checks.append("Formal proof was skipped/blocked — evidence chain not formally verified.")
            elif not g.get("passed"):
                checks.append("Formal proof FAILED — evidence chain may have logical gaps.")

    return checks


# ---------------------------------------------------------------------------
# 6. Grounding evidence
# ---------------------------------------------------------------------------

def render_grounding_evidence(entities: dict | None, grounding_evidence: dict | None = None) -> str:
    """Render grounding evidence table showing resolved vs unresolved entities."""
    if not entities:
        return ""

    resolution_map = entities.get("resolution_map", {})
    unresolved_terms = entities.get("unresolved_terms", [])

    if not resolution_map and not unresolved_terms:
        return ""

    lines: list[str] = ["## Grounding Evidence", ""]

    if resolution_map:
        lines.append("| Term | Status | Matched To | Evidence |")
        lines.append("|------|--------|-----------|----------|")
        for term, info in resolution_map.items():
            if not isinstance(info, dict):
                continue
            exists = info.get("exists", False)
            if exists:
                name = info.get("name", "—")
                qra_count = info.get("qra_count", 0)
                match_type = info.get("match_type", "exact")
                lines.append(f"| {term} | RESOLVED | {name} | {qra_count} QRAs ({match_type}) |")
            else:
                reason = info.get("reason", "unknown")
                closest = info.get("closest_match", "—")
                dist = info.get("distance", 1.0)
                if closest and closest != "—":
                    lines.append(f"| {term} | UNRESOLVED | closest: {closest} (dist={dist:.2f}) | {reason} |")
                else:
                    lines.append(f"| {term} | UNRESOLVED | — | {reason} |")
        lines.append("")

    if unresolved_terms:
        fab_ids = [u for u in unresolved_terms
                   if isinstance(u, dict) and u.get("type") == "id_like"]
        if fab_ids:
            names = ", ".join(u.get("term", "?") for u in fab_ids)
            lines.append(f"> **{len(fab_ids)} fabricated ID(s):** {names}")
            lines.append("")

    if grounding_evidence and isinstance(grounding_evidence, dict):
        resolved_count = grounding_evidence.get("resolved", 0)
        unresolved_id_count = grounding_evidence.get("unresolved_id_like", 0)
        ratio = grounding_evidence.get("ratio", 1.0)
        lines.append(f"**Grounding ratio:** {resolved_count} resolved / "
                      f"{resolved_count + unresolved_id_count} total "
                      f"({ratio:.0%})")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 7. Execution flow mermaid
# ---------------------------------------------------------------------------

def render_execution_flow_mermaid(steps: list[dict]) -> str:
    """Render execution steps as a mermaid flowchart."""
    if not steps:
        return ""

    lines = ["```mermaid", "graph TD"]
    prev_id = None
    for i, step in enumerate(steps):
        gate_id = step.get("gate", f"step_{i}").replace(".", "_")
        passed = step.get("passed", False)
        detail = step.get("detail", "")[:40].replace('"', "'")

        cls = "pass" if passed else "fail"
        lines.append(f'  {gate_id}["{gate_id}<br/>{detail}"]:::{cls}')
        if prev_id:
            lines.append(f"  {prev_id} --> {gate_id}")
        prev_id = gate_id

    lines.append("  classDef pass fill:#9f9,stroke:#090")
    lines.append("  classDef fail fill:#f66,stroke:#900")
    lines.append("```")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 8. /memory clarify output
# ---------------------------------------------------------------------------

def render_clarify_output(clarify_result: dict | None) -> str:
    """Render /memory clarify output."""
    if not clarify_result:
        return ""

    lines: list[str] = ["## Entity Clarification", ""]

    if isinstance(clarify_result, dict):
        intent = clarify_result.get("intent", {})
        if isinstance(intent, dict):
            top_intent = intent.get("label", "unknown")
            confidence = intent.get("confidence", 0)
            lines.append(f"**Intent:** {top_intent} ({confidence:.0%})")
            lines.append("")

        clarifications = clarify_result.get("clarifications", [])
        if clarifications:
            lines.append("| Entity | Status | Detail |")
            lines.append("|--------|--------|--------|")
            for c in clarifications[:10]:
                if not isinstance(c, dict):
                    continue
                entity = c.get("entity", "?")
                status = c.get("status", "?")
                detail = c.get("detail", "—")[:60]
                lines.append(f"| {entity} | {status} | {detail} |")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 9. /lean4-prove result
# ---------------------------------------------------------------------------

def render_proof_result(lean4_result: dict | None) -> str:
    """Render Lean4 formal verification results."""
    if not lean4_result:
        return ""

    lines: list[str] = ["## Formal Verification", ""]

    proof_data = lean4_result.get("proof_data", {}) if isinstance(lean4_result.get("proof_data"), dict) else {}
    success = bool(
        lean4_result.get("proof_success")
        or lean4_result.get("success")
        or lean4_result.get("verified")
        or proof_data.get("success")
        or proof_data.get("verified")
    )
    skipped = bool(lean4_result.get("proof_skipped"))
    blocked = bool(lean4_result.get("gate_blocked"))

    if blocked:
        lines.append("**Status:** BLOCKED — gate prerequisite not met")
        if lean4_result.get("reason"):
            lines.append(f"**Reason:** {lean4_result['reason']}")
        lines.append("")
        return "\n".join(lines)

    if skipped:
        lines.append("**Status:** SKIPPED")
        if lean4_result.get("reason"):
            lines.append(f"**Reason:** {lean4_result['reason']}")
        lines.append("")
        return "\n".join(lines)

    status = "PROVED" if success else "FAILED"
    lines.append(f"**Status:** {status}")
    lines.append("")

    if proof_data:
        if proof_data.get("lean_code") or proof_data.get("code"):
            lines.append("```lean4")
            lines.append(proof_data.get("lean_code") or proof_data.get("code", ""))
            lines.append("```")
            lines.append("")

        if proof_data.get("compiler_output"):
            lines.append("<details><summary>Compiler output</summary>")
            lines.append("")
            lines.append("```")
            lines.append(proof_data["compiler_output"])
            lines.append("```")
            lines.append("")
            lines.append("</details>")
            lines.append("")

        if proof_data.get("error_message") and not success:
            lines.append(f"**Error:** {proof_data['error_message']}")
            lines.append("")

    if lean4_result.get("provable_confidence") is not None:
        conf = lean4_result["provable_confidence"]
        lines.append(f"**Provability confidence:** {conf:.0%}")
        lines.append("")

    if lean4_result.get("prediction"):
        lines.append(f"**Prediction:** {lean4_result['prediction']}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 10. Metrics table
# ---------------------------------------------------------------------------

def render_metrics_table(case: dict) -> str:
    """Render case metrics as a table."""
    lines: list[str] = ["## Metrics", ""]

    verdict = case.get("verdict", {})
    gate_trace = case.get("gate_trace", [])
    evidence = case.get("evidence", [])
    control_ids = case.get("claim", {}).get("control_ids", [])

    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| State | {verdict.get('state', '?')} |")
    lines.append(f"| Grade | {verdict.get('grade', '?')} |")
    lines.append(f"| Controls | {len(control_ids)} |")
    lines.append(f"| Evidence items | {len(evidence)} |")

    gates_passed = sum(1 for g in gate_trace if g.get("passed"))
    lines.append(f"| Gates passed | {gates_passed}/{len(gate_trace)} |")

    if evidence:
        scores = [float(e.get("confidence", 0) or 0) for e in evidence
                  if isinstance(e.get("confidence", 0), (int, float))]
        if scores:
            avg = sum(scores) / len(scores)
            lines.append(f"| Avg confidence | {avg:.2f} |")
            lines.append(f"| Max confidence | {max(scores):.2f} |")

    timing = case.get("timing", {})
    if isinstance(timing, dict):
        total = timing.get("total_seconds", timing.get("total", 0))
        if total:
            lines.append(f"| Total time | {total:.1f}s |")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 11. Evidence confidence grading
# ---------------------------------------------------------------------------

def _grade_evidence_confidence(item: dict) -> float:
    """Grade an individual evidence item's confidence (0-1)."""
    score = item.get("confidence", 0)
    result = item.get("result", {})

    if not isinstance(result, dict):
        return score * 0.5

    has_technique = bool(result.get("technique"))
    has_control = bool(item.get("control_ids"))

    bonus = 0.0
    if has_technique:
        bonus += 0.1
    if has_control:
        bonus += 0.1

    return min(1.0, score + bonus)


# ---------------------------------------------------------------------------
# 12. Answer narrative synthesis
# ---------------------------------------------------------------------------

def synthesize_answer_narrative(case: dict) -> str:
    """Synthesize a human-readable answer from evidence."""
    verdict = case.get("verdict", {})
    state = verdict.get("state", "unknown")
    grade = verdict.get("grade", "?")
    evidence = case.get("evidence", [])
    gate_trace = case.get("gate_trace", [])
    entities = case.get("entities", {})
    claim = case.get("claim", {})
    question = claim.get("text", "")

    lines: list[str] = []

    if state == "not_satisfied":
        lines.append("The evidence is insufficient to answer this question.")
        lines.append("")

        for g in gate_trace:
            if not g.get("passed"):
                lines.append(f"- **{g.get('gate', '?')}** failed: {g.get('detail', '')}")
        lines.append("")
        return "\n".join(lines)

    technique_groups: dict[str, list[dict]] = {}
    for e in evidence:
        result = e.get("result", {})
        if not isinstance(result, dict):
            continue
        tech = result.get("technique", "General")
        technique_groups.setdefault(tech, []).append(e)

    if technique_groups:
        lines.append("The evidence supports this question through the following technique areas:")
        lines.append("")

        for tech, items in technique_groups.items():
            graded = [(e, _grade_evidence_confidence(e)) for e in items]
            graded.sort(key=lambda x: x[1], reverse=True)

            lines.append(f"**{tech}** ({len(items)} evidence item(s)):")
            lines.append("")
            for e, conf in graded[:3]:
                result = e.get("result", {})
                if isinstance(result, dict):
                    q = result.get("question", "")[:80]
                    cids = ", ".join(e.get("control_ids", [])[:3])
                    label = "exact" if conf >= 0.9 else "strong" if conf >= 0.8 else "moderate" if conf >= 0.7 else "keyword" if conf >= 0.5 else "weak"
                    lines.append(f"- [{label}] {q}")
                    if cids:
                        lines.append(f"  Controls: {cids}")
            if len(items) > 3:
                lines.append(f"- ... and {len(items) - 3} more")
            lines.append("")
    else:
        lines.append("Evidence found but no technique groupings available.")
        lines.append("")

    if state == "inconclusive":
        lines.append(f"**Note:** While evidence exists, the overall grade ({grade}) "
                      "indicates gaps in coverage or weak technique bridging.")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 13. Sub-claims builder
# ---------------------------------------------------------------------------

def build_meaningful_sub_claims(
    evidence: list[dict],
    gate_trace: list[dict],
    single_technique: bool = False,
) -> list[dict]:
    """Build sub-claims from evidence grouped by technique."""
    technique_groups: dict[str, list[dict]] = {}
    for e in evidence:
        result = e.get("result", {})
        if not isinstance(result, dict):
            continue
        tech = result.get("technique", "General")
        technique_groups.setdefault(tech, []).append(e)

    claims: list[dict] = []
    for tech, items in technique_groups.items():
        scores = [float(e.get("confidence", 0) or 0) for e in items
                  if isinstance(e.get("confidence", 0), (int, float))]
        avg_score = sum(scores) / len(scores) if scores else 0

        control_ids: list[str] = []
        for e in items:
            control_ids.extend(e.get("control_ids", []))
        unique_cids = sorted(set(control_ids))

        claims.append({
            "technique": tech,
            "evidence_count": len(items),
            "avg_confidence": round(avg_score, 3),
            "control_ids": unique_cids,
            "best_evidence": items[0] if items else {},
        })

    claims.sort(key=lambda c: c["avg_confidence"], reverse=True)
    return claims
