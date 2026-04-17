"""Report generation for evidence case lab.

Renders REPORT.md optimized for reviewer scan order:
1. Executive summary (2 lines)
2. Verdict table (one line per question, scannable)
3. Problems — only questions that need review, with mermaid + evidence
4. Appendix — full dossiers for all questions (process audit trail)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from diagnosis import DiagnosisResult

CORRECTIONS_LOG = Path(__file__).resolve().parent / "state" / "corrections.jsonl"


def write_report(diag: DiagnosisResult, results: list[dict], path: Path) -> None:
    """Write REPORT.md — structured for reviewer scan order."""
    s = diag.summary()
    lines: list[str] = [
        "# Evidence Case Lab Report",
        "",
        "> **What this report answers:** Can each question be answered by our corpus? "
        "Verdicts are `satisfied` (yes — evidence exists), `not_satisfied` (no — needs "
        "`/memory clarify`), or `inconclusive` (insufficient evidence to decide).",
        "",
    ]

    _render_executive_summary(lines, s, results)
    _render_verdict_table(lines, results)
    _render_problems(lines, diag, results)
    _render_corrections(lines)
    _render_appendix_dossiers(lines, results)

    path.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _esc(text: str) -> str:
    """Escape text for mermaid node labels."""
    return str(text).replace('"', "'").replace("<", "&lt;").replace(">", "&gt;")


def _safe_id(term: str) -> str:
    """Create a valid mermaid node ID from arbitrary text."""
    return "".join(c if c.isalnum() else "_" for c in term)


# ---------------------------------------------------------------------------
# 1. Executive summary — the first thing a reviewer reads
# ---------------------------------------------------------------------------

def _render_executive_summary(lines: list[str], s: dict, results: list[dict]) -> None:
    correct = s["correct"]
    total = s["total"]
    review = s["needs_human_review"]

    lines.append(f"**{correct}/{total} correct.** "
                 f"{'No issues.' if review == 0 else f'**{review} need review** (see below).'} "
                 f"FP rate: {s['fp_rate']:.0%}, FN rate: {s['fn_rate']:.0%}.")
    lines.append("")

    # Error breakdown by category — auditor needs this at a glance
    if review > 0:
        parts = []
        if s.get("grounding_failures"):
            parts.append(f"grounding failures: {s['grounding_failures']}")
        if s.get("false_positives"):
            parts.append(f"false positives: {s['false_positives']}")
        if s.get("false_negatives"):
            parts.append(f"false negatives: {s['false_negatives']}")
        if s.get("grounding_warnings"):
            parts.append(f"grounding warnings: {s['grounding_warnings']}")
        if s.get("technique_scatter"):
            parts.append(f"technique scatter: {s['technique_scatter']}")
        if parts:
            lines.append(f"Breakdown: {', '.join(parts)}.")
            lines.append("")

    timings = [r.get("total_ms", 0) for r in results if r.get("total_ms", 0) > 0]
    if timings:
        avg_ms = sum(timings) / len(timings)
        lines.append(f"Avg {avg_ms:.0f}ms/question, {sum(timings)/1000:.1f}s total wall time.")
        lines.append("")


# ---------------------------------------------------------------------------
# 2. Verdict table — scannable one-liner per question
# ---------------------------------------------------------------------------

def _render_verdict_table(lines: list[str], results: list[dict]) -> None:
    lines.extend([
        "## Verdicts",
        "",
        "| # | ID | Question (entity markup) | Expected | Actual | Verdict |",
        "|---|-----|--------------------------|----------|--------|---------|",
    ])
    for i, r in enumerate(results, 1):
        qid = r.get("id", "?")
        question = r.get("question", "?")
        expected = r.get("expected", "?")
        actual = r.get("actual_verdict", "?")
        ge = r.get("grounding_evidence", {})
        unresolved = ge.get("unresolved_id_like", 0) if isinstance(ge, dict) else 0

        if expected == actual or (expected == "not_satisfied" and actual == "inconclusive"):
            status = '<span style="color:#2ecc71">OK</span>'
        elif actual == "satisfied" and unresolved > 0:
            status = '<span style="color:#f39c12">**REVIEW**</span>'
        else:
            status = '<span style="color:#e74c3c">**WRONG**</span>'

        # Inline NVIS markup in verdict table — the primary scan surface
        markup = _inline_nvis(question, r.get("annotations", []))
        lines.append(f"| {i} | {qid} | {markup} | {expected} | {actual} | {status} |")
    lines.append("")


def _inline_nvis(question: str, annotations: list[dict]) -> str:
    """Apply NVIS color markup to a question. Wraps entire sentence in HTML for consistent baseline."""
    annotated = question
    if annotations:
        sorted_annots = sorted(annotations, key=lambda a: len(a.get("term", "")), reverse=True)
        for a in sorted_annots:
            term = a.get("term", "")
            level = a.get("level", "?")
            pre, post = NVIS_MARKUP.get(level, ("", ""))
            if term and (pre or post):
                annotated = re.sub(
                    re.escape(term), f"{pre}{term}{post}",
                    annotated, count=1, flags=re.IGNORECASE,
                )
    # Wrap entire sentence in <span> so all text uses HTML rendering (consistent baseline)
    return f"<span>{annotated.replace('|', '/')}</span>"


# ---------------------------------------------------------------------------
# 3. Problems — only questions that need review, with full evidence
# ---------------------------------------------------------------------------

def _render_problems(lines: list[str], diag: DiagnosisResult, results: list[dict]) -> None:
    problem_ids = _collect_problem_ids(diag)
    if not problem_ids:
        lines.extend(["## No Issues Found", "", "All verdicts match expectations.", ""])
        return

    lines.extend([f"## {len(problem_ids)} Question(s) Need Review", ""])

    problem_results = [r for r in results if r.get("id", "?") in problem_ids]
    for r in problem_results:
        _render_problem_dossier(lines, r, diag)


def _collect_problem_ids(diag: DiagnosisResult) -> set[str]:
    ids: set[str] = set()
    for bucket in (diag.grounding_warnings, diag.grounding_failures,
                   diag.false_positives, diag.false_negatives, diag.technique_scatter):
        for item in bucket:
            ids.add(item.get("id", "?"))
    return ids


def _render_problem_dossier(lines: list[str], r: dict, diag: DiagnosisResult) -> None:
    """Render a focused dossier for a problem question — evidence + mermaid."""
    qid = r.get("id", "?")
    question = r.get("question", "?")
    expected = r.get("expected", "?")
    actual = r.get("actual_verdict", "?")
    ge = r.get("grounding_evidence", {}) or {}
    res_map = ge.get("resolution_map", {}) if isinstance(ge, dict) else {}

    diag_entry = _find_diag_entry(qid, diag)
    root_cause = diag_entry.get("root_cause", "unknown") if diag_entry else "unknown"
    detail = diag_entry.get("detail", "") if diag_entry else ""

    lines.extend([
        f"### [{qid}] {question}",
        "",
        f"Expected **{expected}**, got **{actual}**. Root cause: `{root_cause}`.",
    ])
    if detail:
        lines.extend(["", f"> {detail}"])
    lines.append("")

    # Gate Scorecard — the FIRST thing a reviewer reads. One red row = instant attribution.
    _render_gate_scorecard(lines, r, res_map)

    # Sentence decomposition + entity evidence (merged — single table, no redundancy)
    _render_sentence_decomposition(lines, r, res_map)

    # Evidence items — only show when grounding passed (fabricated entities create false legitimacy)
    has_unresolved = any(
        isinstance(v, dict) and not v.get("exists")
        for v in res_map.values()
    ) if res_map else False
    evidence_items = r.get("evidence_items", []) or []
    if evidence_items and has_unresolved:
        lines.extend([
            "**Evidence QRAs** (grounding FAILED — these matched on keywords, not the claimed entity):",
            "",
            "| Control | Question | Score |",
            "|---------|----------|-------|",
        ])
        for e in evidence_items[:6]:
            cid = e.get("control_id", "?")
            eq = (e.get("question") or e.get("q") or "—").replace("|", "/")
            score = e.get("score", "")
            score_str = f"{score:.2f}" if isinstance(score, (int, float)) else "—"
            lines.append(f"| `{cid}` | {eq} | {score_str} |")
        lines.append("")
    elif evidence_items:
        lines.extend([
            "**Evidence QRAs:**",
            "",
            "| Control | Question | Score |",
            "|---------|----------|-------|",
        ])
        for e in evidence_items[:10]:
            cid = e.get("control_id", "?")
            eq = (e.get("question") or e.get("q") or "—").replace("|", "/")
            score = e.get("score", "")
            score_str = f"{score:.2f}" if isinstance(score, (int, float)) else "—"
            lines.append(f"| `{cid}` | {eq} | {score_str} |")
        if len(evidence_items) > 10:
            lines.append(f"| ... | +{len(evidence_items) - 10} more | |")
        lines.append("")

    # Grounding warnings
    warnings = ge.get("warnings", []) if isinstance(ge, dict) else []
    if warnings:
        for w in warnings:
            lines.append(f"- `{w.get('category', '?')}`: **{w.get('term', '?')}** "
                         f"— {w.get('detail', '')}")
        lines.append("")

    # Next Action — what the reviewer should do about this question
    if actual != expected and not (expected == "not_satisfied" and actual == "inconclusive"):
        corrected = "not_satisfied" if actual == "satisfied" else "satisfied"
        lines.append("**Next Action:**")
        lines.append("")
        if root_cause == "false_negative":
            # System said "can't answer" but corpus has the data — pipeline bug
            lines.append(f"Pipeline gap — corpus has evidence but recall failed. "
                         f"Run `/memory clarify` to identify missing bridge, "
                         f"then re-run this question.")
        elif root_cause == "grounding_failure":
            # System said "can answer" but entity is fabricated — hallucination
            lines.append(f"Fabricated entity — system hallucinated an answer "
                         f"from keyword matches. Correct the verdict:")
        elif root_cause == "false_positive":
            # System said "can answer" but question is out of scope
            lines.append(f"Out-of-scope question answered — system needs "
                         f"scope boundary. Run `/memory clarify` to teach the boundary, "
                         f"then re-run.")
        else:
            lines.append(f"Review the evidence above and correct if needed:")
        lines.extend([
            "",
            f"```",
            f'./run.sh correct {qid} {corrected} --reason "<why>"',
            f"```",
            "",
        ])

    lines.extend(["---", ""])


def _find_diag_entry(qid: str, diag: DiagnosisResult) -> dict | None:
    for bucket in (diag.grounding_warnings, diag.grounding_failures,
                   diag.false_positives, diag.false_negatives, diag.technique_scatter):
        for item in bucket:
            if item.get("id") == qid:
                return item
    return None


# ---------------------------------------------------------------------------
# 4a. Gate Scorecard — one table, one red row = instant failure attribution
# ---------------------------------------------------------------------------

def _render_gate_scorecard(lines: list[str], r: dict, res_map: dict) -> None:
    """Gate Scorecard: the auditor reads THIS first. One red row = failure point."""
    gate_trace = r.get("gate_trace", []) or []
    if not gate_trace and not res_map:
        return

    lines.extend([
        "**Gate Scorecard:**",
        "",
        "| Step | Gate | Result | Detail |",
        "|------|------|--------|--------|",
    ])

    # Grounding gate (synthesized from resolution_map)
    if res_map:
        unresolved = [t for t, v in res_map.items()
                      if isinstance(v, dict) and not v.get("exists")]
        resolved = [t for t, v in res_map.items()
                    if isinstance(v, dict) and v.get("exists")]
        if unresolved:
            names = ", ".join(unresolved[:3])
            lines.append(f'| Grounding | entity_resolution | <span style="color:#e74c3c">**FAIL**</span> | '
                         f"UNRESOLVED: {names} — not in 8,979 controls |")
        elif resolved:
            lines.append(f'| Grounding | entity_resolution | <span style="color:#2ecc71">PASS</span> | '
                         f"{len(resolved)} entity(s) resolved |")

    # Pipeline gates
    for g in gate_trace:
        gname = g.get("gate", "?")
        passed = g.get("passed", True)
        detail = (g.get("detail") or "").replace("|", "/")[:80]
        result = '<span style="color:#2ecc71">PASS</span>' if passed else '<span style="color:#e74c3c">**FAIL**</span>'
        step = gname.replace("step_", "Step ").replace("_", " ").title()
        lines.append(f"| {step} | {gname} | {result} | {detail} |")

    lines.extend(["", ""])


# ---------------------------------------------------------------------------
# 4b. Sentence markup — NVIS-colored per-term annotations
# ---------------------------------------------------------------------------

# NVIS markup: bold all entities, color only problems.
# Bold = "this is an extracted entity". Color = "this entity has a problem".
NVIS_MARKUP = {
    "RED": ('<span style="color:#e74c3c">', '</span>'),      # red — fabricated
    "AMBER": ('<span style="color:#e67e22">', '</span>'),    # orange — fuzzy/misspelling
    "YELLOW": ('<span style="color:#f39c12">', '</span>'),   # gold — uncertain/not found
    "GREEN": ('<span style="color:#2ecc71">', '</span>'),    # green — confirmed
}
NVIS_EMOJI = {"GREEN": "🟢", "AMBER": "🟠", "RED": "🔴", "YELLOW": "🟡"}


def _render_sentence_decomposition(lines: list[str], r: dict, res_map: dict) -> None:
    """Render decomposed sentence with NVIS colors + merged entity evidence table.

    One section replaces three: sentence markup, legend table, AND entity resolution.
    The annotated sentence shows WHAT was found; the table shows WHY each term
    got its color (resolution status, matched control, QRA count).
    """
    annotations = r.get("annotations", []) or []
    question = r.get("question", "")
    decomposition = r.get("decomposition", {}) or {}
    if not question:
        return

    lines.append("**Sentence Decomposition:**")
    lines.append("")

    # Given/Then
    given = decomposition.get("given_components", []) if isinstance(decomposition, dict) else []
    then = decomposition.get("then_components", []) if isinstance(decomposition, dict) else []
    if given:
        lines.append(f"> **Given:** {', '.join(given)}")
    if then:
        lines.append(f"> **Then:** {', '.join(then)}")
    if given or then:
        lines.append("")

    # Annotated sentence — color all entities, wrap in HTML for consistent baseline
    annotated = _inline_nvis(question, annotations)
    lines.extend([f"> {annotated}", ""])

    # Merged entity evidence table — annotations + resolution in one view
    if annotations or res_map:
        lines.extend([
            "**Entity Evidence:**",
            "",
            "| Term | Color | Status | Matched To | QRAs |",
            "|------|-------|--------|------------|------|",
        ])
        # Build from annotations (preferred — has color info)
        seen_terms: set[str] = set()
        for a in annotations:
            term = a.get("term", "?")
            level = a.get("level", "?")
            emoji = NVIS_EMOJI.get(level, "⚪")
            label = a.get("label", "")
            seen_terms.add(term)
            # Enrich with resolution_map data if available
            info = res_map.get(term, {}) if res_map else {}
            if isinstance(info, dict) and info.get("exists"):
                matched = info.get("name", "—")
                qras = info.get("qra_count", "?")
                lines.append(f"| {term} | {emoji} | {label} | {matched} | {qras} |")
            elif isinstance(info, dict) and not info.get("exists") and info.get("closest_match"):
                closest = info.get("closest_match", "—")
                dist = info.get("distance", "")
                d = f" ({dist:.2f})" if isinstance(dist, (int, float)) and dist else ""
                lines.append(f"| {term} | {emoji} | {label} | closest: `{closest}`{d} | 0 |")
            else:
                lines.append(f"| {term} | {emoji} | {label} | — | — |")

        # Add resolution_map entries not covered by annotations
        for term, info in (res_map or {}).items():
            if term in seen_terms or not isinstance(info, dict):
                continue
            if info.get("exists"):
                lines.append(f"| {term} | 🟢 | resolved | {info.get('name', '—')} "
                             f"| {info.get('qra_count', '?')} |")
            else:
                closest = info.get("closest_match", "—")
                dist = info.get("distance", "")
                d = f" ({dist:.2f})" if isinstance(dist, (int, float)) and dist else ""
                lines.append(f"| {term} | 🔴 | unresolved | closest: `{closest}`{d} | 0 |")
        lines.append("")


# ---------------------------------------------------------------------------
# 4c. Mermaid evidence tree — visual trace of the full pipeline
# ---------------------------------------------------------------------------

def _render_mermaid_tree(lines: list[str], r: dict) -> None:
    """CAE evidence tree tracing the full /create-evidence-case process.

    Every node shows REAL data from the pipeline — never counts or summaries.
    A reviewer reads this diagram alone and knows exactly what happened:

    1. Question (full text, never truncated)
    2. Sentence decomposition → Given / Then components
    3. Entity extraction via hybrid_search → each candidate term
    4. Per-entity resolution: matched control name + QRA count, or failure reason
    5. Technique bridge: do entities share a SPARTA technique?
    6. Each gate by name with pass/fail reasoning
    7. Verdict
    """
    qid = r.get("id", "?")
    question = _esc(r.get("question", "?"))
    actual = r.get("actual_verdict", "?")
    ge = r.get("grounding_evidence", {}) or {}
    entities = r.get("entities", {}) or {}
    gate_trace = r.get("gate_trace", []) or []
    res_map = ge.get("resolution_map", {}) if isinstance(ge, dict) else {}
    decomposition = r.get("decomposition", {}) or {}
    technique_groups = r.get("technique_groups", {}) or {}
    all_ids = entities.get("all_control_ids", []) if isinstance(entities, dict) else []
    phrases = entities.get("phrases", []) if isinstance(entities, dict) else []
    method = entities.get("method", "") if isinstance(entities, dict) else ""

    lines.append("```mermaid")
    lines.append("flowchart TD")

    # --- 1. Question: full text ---
    lines.append(f'    Q["{qid}: {question}"]')

    # --- 2. Sentence decomposition (Given/Then) ---
    given = decomposition.get("given_components", []) if isinstance(decomposition, dict) else []
    then = decomposition.get("then_components", []) if isinstance(decomposition, dict) else []
    if given or then:
        given_str = _esc(", ".join(given)) if given else "none"
        then_str = _esc(", ".join(then)) if then else "none"
        lines.append(f'    Q --> DEC["Step 1: Decompose<br/>'
                     f'Given: {given_str}<br/>Then: {then_str}"]')
        parent = "DEC"
    else:
        parent = "Q"

    # --- 3. Entity extraction ---
    ext_label = f"Step 2: Extract Entities via {method}" if method else "Step 2: Extract Entities"
    lines.append(f'    {parent} --> EXT["{ext_label}"]')

    # --- 3b. Each entity with resolution evidence ---
    entity_nids: list[str] = []
    for term, info in list(res_map.items())[:6]:
        nid = _safe_id(term)
        entity_nids.append(nid)
        safe = _esc(term)
        if isinstance(info, dict) and info.get("exists"):
            name = _esc(info.get("name") or "matched")
            qc = info.get("qra_count", 0)
            mt = info.get("match_type", "exact")
            lines.append(f'    EXT --> {nid}["{safe}<br/>{mt} match: {name}<br/>{qc} QRAs"]')
            lines.append(f"    style {nid} fill:#27ae60,stroke:#333,color:#fff")
        elif isinstance(info, dict):
            closest = info.get("closest_match")
            dist = info.get("distance")
            reason = info.get("reason", "")
            if closest and dist and isinstance(dist, (int, float)):
                detail = f"closest: {_esc(closest)} (distance {dist:.2f})"
            elif reason:
                detail = _esc(reason)
            else:
                detail = "not found in 8,979 controls"
            lines.append(f'    EXT --> {nid}["{safe}<br/>{detail}"]')
            lines.append(f"    style {nid} fill:#e74c3c,stroke:#333,color:#fff")

    # Fallback: no resolution data — show raw IDs + phrases
    if not entity_nids and (all_ids or phrases):
        for i, term in enumerate((all_ids + phrases)[:5]):
            nid = f"E{i}"
            entity_nids.append(nid)
            lines.append(f'    EXT --> {nid}["{_esc(str(term))}"]')
    if not entity_nids:
        lines.append('    EXT --> NOENT["no entities found in question"]')
        lines.append("    style NOENT fill:#f39c12,stroke:#333,color:#fff")
        entity_nids = ["NOENT"]

    # --- 4. Technique bridge ---
    if technique_groups:
        parts = [f"{k}: {v}" for k, v in list(technique_groups.items())[:4]]
        tech_label = _esc(", ".join(parts))
        lines.append(f'    {entity_nids[0]} --> TECH["Step 3: Technique Bridge<br/>{tech_label}"]')
        for en in entity_nids[1:]:
            lines.append(f"    {en} --> TECH")
        lines.append(f"    style TECH fill:#27ae60,stroke:#333,color:#fff")
        prev_nids = ["TECH"]
    else:
        prev_nids = entity_nids

    # --- 5. Named gates with reasoning ---
    for gi, g in enumerate(gate_trace):
        gname = g.get("gate", f"gate_{gi}")
        passed = g.get("passed", True)
        gnid = f"G{gi}"
        detail = _esc(g.get("detail") or "")

        label = f"{gname}: {'PASS' if passed else 'FAIL'}"
        if detail:
            label += f"<br/>{detail[:80]}"
        fill = "#27ae60" if passed else "#e74c3c"

        lines.append(f'    {prev_nids[0]} --> {gnid}["{label}"]')
        for pn in prev_nids[1:]:
            lines.append(f"    {pn} --> {gnid}")
        lines.append(f"    style {gnid} fill:{fill},stroke:#333,color:#fff")
        prev_nids = [gnid]

    # --- 6. Verdict ---
    lines.append(f'    {prev_nids[0]} --> V["{actual}"]')
    for pn in prev_nids[1:]:
        lines.append(f"    {pn} --> V")
    vfill = "#27ae60" if actual == "satisfied" else "#e74c3c" if actual == "not_satisfied" else "#f39c12"
    lines.append(f"    style V fill:{vfill},stroke:#333,stroke-width:3px,color:#fff")

    lines.extend(["```", ""])


# ---------------------------------------------------------------------------
# 5. Corrections history
# ---------------------------------------------------------------------------

def _render_corrections(lines: list[str]) -> None:
    if not CORRECTIONS_LOG.exists():
        return
    correction_lines = CORRECTIONS_LOG.read_text().strip().split("\n")
    corrections = [json.loads(line) for line in correction_lines if line.strip()]
    if not corrections:
        return
    lines.extend([
        "## Corrections",
        "",
        "| ID | Was | Now | Reason |",
        "|-----|-----|-----|--------|",
    ])
    for c in corrections[-20:]:
        lines.append(
            f"| {c.get('question_id', '?')} "
            f"| {c.get('original_verdict', '?')} "
            f"| {c.get('corrected_verdict', '?')} "
            f"| {(c.get('reason', '') or '')[:60]} |"
        )
    lines.append("")


# ---------------------------------------------------------------------------
# 6. Appendix — full dossiers for audit trail (all questions)
# ---------------------------------------------------------------------------

def _render_appendix_dossiers(lines: list[str], results: list[dict]) -> None:
    lines.extend([
        "---",
        "",
        "## Appendix: Full Process Dossiers",
        "",
        "<details>",
        "<summary>Expand to see step-by-step traces for all questions</summary>",
        "",
    ])
    for r in results:
        _render_full_dossier(lines, r)
    lines.extend(["</details>", ""])


def _render_full_dossier(lines: list[str], r: dict) -> None:
    """Complete step-by-step trace — for audit, not first-pass review."""
    qid = r.get("id", "?")
    question = r.get("question", "?")
    expected = r.get("expected", "?")
    actual = r.get("actual_verdict", "?")
    ms = r.get("total_ms", 0)
    asked_by = r.get("asked_by", r.get("source", "batch"))
    ge = r.get("grounding_evidence", {}) or {}
    entities = r.get("entities", {}) or {}
    decomposition = r.get("decomposition", {}) or {}
    gate_trace = r.get("gate_trace", []) or []
    evidence_items = r.get("evidence_items", []) or []
    component_results = r.get("component_results", {}) or {}
    lean4_result = r.get("lean4_result", {}) or {}
    technique_groups = r.get("technique_groups", {}) or {}
    res_map = ge.get("resolution_map", {}) if isinstance(ge, dict) else {}

    match = expected == actual or (expected == "not_satisfied" and actual == "inconclusive")
    icon = "OK" if match else "WRONG"

    lines.extend([
        f"### [{qid}] {question}",
        "",
        f"{icon} | asked by: {asked_by} | expected: {expected} "
        f"| actual: **{actual}** | {ms:.0f}ms",
        "",
    ])

    # Step 1: Decomposition
    given = decomposition.get("given_components", []) if isinstance(decomposition, dict) else []
    then = decomposition.get("then_components", []) if isinstance(decomposition, dict) else []
    if given or then:
        parts = []
        if given:
            parts.append(f"given: {', '.join(given)}")
        if then:
            parts.append(f"then: {', '.join(then)}")
        lines.append(f"**1. Decompose:** {'; '.join(parts)}")
        lines.append("")

    # Step 2: Entities
    all_ids = entities.get("all_control_ids", []) if isinstance(entities, dict) else []
    phrases = entities.get("phrases", []) if isinstance(entities, dict) else []
    method = entities.get("method", "?") if isinstance(entities, dict) else "?"
    id_str = f"`{', '.join(all_ids)}`" if all_ids else "(none)"
    phrase_str = f"{', '.join(phrases)}" if phrases else "(none)"
    lines.extend([f"**2. Entities** ({method}): IDs: {id_str}, phrases: {phrase_str}", ""])

    # Step 2b: Resolution
    if res_map:
        lines.append("**2b. Resolution:**")
        lines.append("")
        lines.extend([
            "| Term | Status | Match | QRAs |",
            "|------|--------|-------|------|",
        ])
        for term, info in res_map.items():
            if isinstance(info, dict) and info.get("exists"):
                lines.append(f"| `{term}` | RESOLVED | {info.get('name', '—')} "
                             f"| {info.get('qra_count', '?')} |")
            elif isinstance(info, dict):
                closest = info.get("closest_match", "—")
                dist = info.get("distance", "")
                d = f" ({dist:.2f})" if isinstance(dist, (int, float)) and dist else ""
                lines.append(f"| `{term}` | UNRESOLVED | closest: `{closest}`{d} | 0 |")
        lines.append("")

    # Step 3: Technique bridge
    if technique_groups:
        tech_str = ", ".join(
            f"{k}({v})" if isinstance(v, int) else f"{k}({len(v)})"
            for k, v in technique_groups.items()
        )
        lines.extend([f"**3. Techniques:** {tech_str}", ""])

    # Step 4: Recall
    if component_results:
        comp_str = ", ".join(
            f"{c}: {len(items)}" for c, items in component_results.items()
            if isinstance(items, list)
        )
        lines.extend([f"**4. Recall:** {comp_str} QRAs", ""])

    # Evidence items
    if evidence_items:
        ids = [e.get("control_id", "?") for e in evidence_items[:8]]
        lines.extend([f"**Evidence:** {len(evidence_items)} QRAs — {', '.join(ids)}", ""])

    # Step 5: Lean4
    if lean4_result:
        pred = lean4_result.get("prediction", "—")
        ok = lean4_result.get("proof_success", False)
        lines.extend([f"**5. Lean4:** {pred} ({'verified' if ok else 'not verified'})", ""])

    # Gates
    if gate_trace:
        gate_strs = []
        for g in gate_trace:
            p = "PASS" if g.get("passed") else "FAIL"
            gate_strs.append(f"{g.get('gate', '?')}: {p}")
        lines.extend([f"**Gates:** {' | '.join(gate_strs)}", ""])

    # Answer
    answer = r.get("answer", "")
    if answer:
        lines.extend([f"> {answer[:200]}", ""])

    lines.append("")
