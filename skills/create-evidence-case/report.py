"""Report generation for evidence cases (v5: split into report + report_sections).

Composers and batch renderers live here. Individual section renderers
are in report_sections.py.

Inputs: Evidence case dict from runner.run() or agent-assembled data.
Outputs: Markdown report + figure_data.json.
Failures: /create-figure subprocess is best-effort — degrades gracefully.
"""
from __future__ import annotations
import os

import json
import subprocess
from pathlib import Path
from typing import Any

# Re-export section renderers so `from report import render_proof_result` still works.
from report_sections import (  # noqa: F401
    render_decomposition_mermaid,
    render_formalization_table,
    render_per_component_resolution,
    render_cross_component_mermaid,
    render_decision_transparency,
    render_grounding_evidence,
    render_execution_flow_mermaid,
    render_clarify_output,
    render_proof_result,
    render_metrics_table,
    synthesize_answer_narrative,
    build_meaningful_sub_claims,
    _build_caveats,
    _build_human_checks,
    _grade_evidence_confidence,
)
from report_decision import (  # noqa: F401
    render_decision_chain,
    render_semantic_step_details,
    render_plausibility_step_details,
)


SKILLS_DIR = Path(__file__).resolve().parent.parent
CREATE_FIGURE_SKILL = SKILLS_DIR / "create-figure" / "run.sh"


# ---------------------------------------------------------------------------
# Ground truth rendering
# ---------------------------------------------------------------------------

def render_ground_truth_sources(ground_truth_sources: dict) -> str:
    """Render technique_knowledge ground truth as a markdown table."""
    if not ground_truth_sources:
        return ""
    lines = ["### Ground Truth Sources", ""]
    lines.append("| Control | Tactic | URLs | Context Excerpt |")
    lines.append("|---------|--------|------|-----------------|")
    for cid, info in sorted(ground_truth_sources.items()):
        tactic = info.get("tactic", "—") or "—"
        urls = info.get("url_sources", [])
        urls_str = ", ".join(f"[link]({u})" for u in urls[:3]) if urls else "—"
        ctx = (info.get("technique_context", "") or "")[:120]
        ctx_escaped = ctx.replace("|", "\\|").replace("\n", " ")
        if ctx_escaped:
            ctx_escaped = f'"{ctx_escaped}"'
        else:
            ctx_escaped = "—"
        lines.append(f"| {cid} | {tactic} | {urls_str} | {ctx_escaped} |")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_to_label(score: float) -> str:
    """Map confidence score to human-readable label."""
    if score >= 0.9:
        return "exact"
    if score >= 0.8:
        return "strong"
    if score >= 0.7:
        return "moderate"
    if score >= 0.5:
        return "keyword"
    return "weak"


def _has_any_failure(gate_trace: list[dict]) -> bool:
    """Check whether any gate in the trace failed."""
    return any(not g.get("passed") for g in gate_trace)


# ---------------------------------------------------------------------------
# Full combined report (v5: 8 sections, not 16)
# ---------------------------------------------------------------------------

def render_full_report(case: dict) -> str:
    """Combine sections into a report. v5: 8 sections, not 16.

    Round 2 restructure per Gemini brutal review:
    1. Verdict banner + "Why This Verdict?" table
    2. Question with NVIS sentence markup (inline chips)
    3. Grounding Evidence table (RESOLVED/UNRESOLVED)
    4. Execution Flow (FAILURES ONLY — omit all-green)
    5. Gates summary (collapsed <details>)
    6. Lean4 proof summary (collapsed, one-liner + expand)
    7. Answer narrative (merged from answer + per-component)
    8. Sign-off block

    Sections cut from default view (available in <details> blocks):
    - Decomposition diagram -> collapsed
    - Formalization table -> collapsed
    - Metrics -> only on threshold breach
    - Cross-component diagram -> collapsed
    - Sub-claims -> merged into answer
    - Evidence chain -> collapsed
    """
    lines: list[str] = []
    claim = case.get("claim", {})
    verdict = case.get("verdict", {})
    gate_trace = case.get("gate_trace", [])
    evidence = case.get("evidence", [])
    decomposition = case.get("decomposition")
    component_results = case.get("component_results")
    entities = case.get("entities")
    clarify_result = case.get("clarify_result")
    lean4_result = case.get("lean4_result")

    question = claim.get("text", "?")
    state = verdict.get("state", "unknown")
    grade = verdict.get("grade", "?")
    case_id = claim.get("id", "?")
    control_ids = claim.get("control_ids", [])

    # -- S1. Verdict Banner + Why --
    lines.append(f"# Evidence Case: {case_id}")
    lines.append("")

    verdict_label = {"satisfied": "YES", "inconclusive": "MAYBE",
                     "not_satisfied": "NO"}.get(state, "?")
    verdict_icon = {"satisfied": "✓", "inconclusive": "?",
                    "not_satisfied": "✗"}.get(state, "?")
    if state == "satisfied":
        summary = f"This question **can be answered** with grade {grade} confidence."
    elif state == "inconclusive":
        summary = "Evidence is **inconclusive** — components don't fully bridge."
    else:
        summary = "This question **cannot be answered** with available evidence."

    lines.append(f"## {verdict_icon} Answerable: {verdict_label}")
    lines.append("")
    lines.append(summary)
    lines.append("")

    # Decision chain — scannable yes/no table with LLM rationale
    decision_chain = render_decision_chain(case)
    if decision_chain:
        lines.append(decision_chain)

    transparency = render_decision_transparency(case)
    if transparency:
        lines.append(transparency)

    # -- S2. Question with entity context --
    lines.append(f"> **Question:** {question}")
    lines.append("")
    if control_ids:
        lines.append(f"**Controls:** {', '.join(control_ids[:20])}"
                      + (f" (+{len(control_ids)-20} more)"
                         if len(control_ids) > 20 else ""))
        lines.append("")

    # -- S3. Grounding Evidence --
    grounding_evidence = None
    for step in gate_trace:
        if step.get("gate") == "step_2_recall":
            grounding_evidence = step.get("data", {}).get("grounding_evidence")
            break
    grounding_section = render_grounding_evidence(entities, grounding_evidence)
    if grounding_section:
        lines.append(grounding_section)

    # Ground truth from technique_knowledge (if available)
    gt_sources = (grounding_evidence or {}).get("ground_truth_sources", {})
    gt_section = render_ground_truth_sources(gt_sources)
    if gt_section:
        lines.append(gt_section)

    # -- S4. Execution Flow (FAILURES ONLY) --
    if gate_trace and _has_any_failure(gate_trace):
        lines.append("## Execution Flow")
        lines.append("")
        lines.append(render_execution_flow_mermaid(gate_trace))
        lines.append("")
        lines.extend(_render_step_details(gate_trace))

    # -- S5. Gates Summary (collapsed) --
    if gate_trace:
        gates_passed = sum(1 for g in gate_trace if g.get("passed"))
        gates_total = len(gate_trace)
        gate_icons = []
        for g in gate_trace:
            gid = g.get("gate", "?")
            icon = "✓" if g.get("passed") else "✗"
            gate_icons.append(f"{icon} {gid}")
        lines.append(
            f"<details><summary>Gates ({gates_passed}/{gates_total} passed): "
            f"{' | '.join(gate_icons)}</summary>")
        lines.append("")
        lines.extend(_render_step_details(gate_trace))
        lines.append("</details>")
        lines.append("")

    # -- S6. Lean4 Proof (one-liner + collapsed detail) --
    if lean4_result:
        proof_data = (lean4_result.get("proof_data", {})
                      if isinstance(lean4_result.get("proof_data"), dict) else {})
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
            proof_icon, proof_label = "—", "BLOCKED"
        elif skipped:
            proof_icon, proof_label = "—", "SKIPPED"
        elif success:
            proof_icon, proof_label = "✓", "PROVED"
        else:
            proof_icon, proof_label = "✗", "FAILED"

        lines.append(f"**Formal Verification:** {proof_icon} {proof_label}")
        lines.append("")

        full_proof = render_proof_result(lean4_result)
        if full_proof:
            lines.append("<details><summary>Proof details</summary>")
            lines.append("")
            lines.append(full_proof)
            lines.append("</details>")
            lines.append("")

    # -- S7. Answer Narrative (merged) --
    lines.append("## Answer")
    lines.append("")
    if state in ("satisfied", "inconclusive"):
        answer_narrative = synthesize_answer_narrative(case)
        lines.append(answer_narrative)
    else:
        lines.append("This question cannot be answered with available evidence.")
    lines.append("")

    # Per-component resolution (collapsed for drill-down)
    if component_results:
        lines.append("<details><summary>Per-Component Resolution</summary>")
        lines.append("")
        lines.append(render_per_component_resolution(component_results))
        lines.append("</details>")
        lines.append("")

    # Evidence chain (collapsed)
    if evidence:
        lines.append(
            "<details><summary>Evidence Chain ({} items)</summary>".format(len(evidence)))
        lines.append("")
        lines.append("| # | Control | Score | Match | Technique | Question |")
        lines.append("|---|---------|-------|-------|-----------|----------|")
        for i, e in enumerate(evidence, 1):
            conf = e.get("confidence", 0)
            e_cids = e.get("control_ids", [])
            result = e.get("result", {})
            technique = (result.get("technique", "—")
                         if isinstance(result, dict) else "—")
            q_text = (result.get("question", "—")[:60]
                      if isinstance(result, dict) else "—")
            cids_str = ", ".join(e_cids[:3]) if e_cids else "—"
            label = _score_to_label(conf)
            lines.append(
                f"| {i} | {cids_str} | {conf:.2f} | {label} "
                f"| {technique} | {q_text} |")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # Clarify, cross-component, decomposition — all collapsed
    clarify_section = render_clarify_output(clarify_result)
    if clarify_section:
        lines.append("<details><summary>Entity Clarification</summary>")
        lines.append("")
        lines.append(clarify_section)
        lines.append("</details>")
        lines.append("")

    cross_mermaid = render_cross_component_mermaid(
        component_results, entities, state)
    if cross_mermaid:
        lines.append("<details><summary>Cross-Component Relationships</summary>")
        lines.append("")
        lines.append(cross_mermaid)
        lines.append("</details>")
        lines.append("")

    decomp_mermaid = render_decomposition_mermaid(decomposition)
    if decomp_mermaid:
        lines.append("<details><summary>Sentence Decomposition</summary>")
        lines.append("")
        lines.append(decomp_mermaid)
        lines.append("")
        formalization = render_formalization_table(decomposition)
        if formalization:
            lines.append(formalization)
        lines.append("</details>")
        lines.append("")

    # -- S8. Sign-off --
    lines.append("---")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Case ID | {case_id} |")
    lines.append(f"| Verdict | {verdict_icon} {state.upper()} (Grade {grade}) |")
    lines.append(f"| Controls | {len(control_ids)} |")
    lines.append(f"| Evidence items | {len(evidence)} |")
    lines.append(
        f"| Gates | {sum(1 for g in gate_trace if g.get('passed'))}"
        f"/{len(gate_trace)} |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Batch summary — sortable landing page for 50+ question reports
# ---------------------------------------------------------------------------

def render_batch_summary(
    cases: list[dict], run_id: str = "", corpus_version: str = "",
) -> str:
    """Render a batch summary landing page.

    One line per question, sortable, with flags and unresolved terms.
    This is what Brandon sees first — he drills into individual cases.
    """
    lines: list[str] = []

    # --- Header ---
    lines.append("# Evidence Case Batch Report")
    lines.append("")
    if run_id:
        lines.append(f"**Run:** {run_id}")
    if corpus_version:
        lines.append(f"**Corpus:** {corpus_version}")
    lines.append(f"**Questions:** {len(cases)}")
    lines.append("")

    # --- Aggregate stats ---
    satisfied = sum(
        1 for c in cases
        if c.get("verdict", {}).get("state") == "satisfied")
    not_satisfied = sum(
        1 for c in cases
        if c.get("verdict", {}).get("state") == "not_satisfied")
    inconclusive = sum(
        1 for c in cases
        if c.get("verdict", {}).get("state") == "inconclusive")

    # Classify real vs adversarial
    real_cases = [c for c in cases
                  if not c.get("claim", {}).get("id", "").startswith("A")]
    adv_cases = [c for c in cases
                 if c.get("claim", {}).get("id", "").startswith("A")]

    # Count expected-vs-actual mismatches
    false_positives = []
    false_negatives = []
    for c in cases:
        expected = c.get(
            "expected_verdict",
            c.get("claim", {}).get("expected_verdict"))
        actual = c.get("verdict", {}).get("state")
        cid = c.get("claim", {}).get("id", "?")
        if expected == "not_satisfied" and actual == "satisfied":
            false_positives.append(cid)
        elif expected == "satisfied" and actual == "not_satisfied":
            false_negatives.append(cid)

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| ✓ Satisfied | {satisfied} |")
    lines.append(f"| ✗ Not Satisfied | {not_satisfied} |")
    lines.append(f"| ? Inconclusive | {inconclusive} |")
    if real_cases:
        real_correct = sum(
            1 for c in real_cases
            if c.get("verdict", {}).get("state") == c.get(
                "expected_verdict",
                c.get("claim", {}).get(
                    "expected_verdict",
                    c.get("verdict", {}).get("state"))))
        lines.append(
            f"| Real accuracy | {real_correct}/{len(real_cases)} "
            f"({100*real_correct/len(real_cases):.0f}%) |")
    if adv_cases:
        adv_correct = sum(
            1 for c in adv_cases
            if c.get("verdict", {}).get("state") == c.get(
                "expected_verdict",
                c.get("claim", {}).get("expected_verdict", "not_satisfied")))
        lines.append(
            f"| Adversarial accuracy | {adv_correct}/{len(adv_cases)} "
            f"({100*adv_correct/len(adv_cases):.0f}%) |")
    if false_positives:
        lines.append(
            f"| **False Positives** | **{len(false_positives)}**: "
            f"{', '.join(false_positives)} |")
    if false_negatives:
        lines.append(
            f"| **False Negatives** | **{len(false_negatives)}**: "
            f"{', '.join(false_negatives)} |")
    lines.append("")

    # --- Per-question table ---
    lines.append("## Questions")
    lines.append("")
    lines.append("| # | Verdict | Grade | Flags | Unresolved | Question |")
    lines.append("|---|---------|-------|-------|------------|----------|")

    for c in cases:
        cid = c.get("claim", {}).get("id", "?")
        c_state = c.get("verdict", {}).get("state", "?")
        c_grade = c.get("verdict", {}).get("grade", "?")
        c_question = c.get("claim", {}).get("text", "?")[:60]

        icon = {"satisfied": "✓", "inconclusive": "?",
                "not_satisfied": "✗"}.get(c_state, "?")

        expected = c.get(
            "expected_verdict",
            c.get("claim", {}).get("expected_verdict"))
        is_fp = expected == "not_satisfied" and c_state == "satisfied"
        is_fn = expected == "satisfied" and c_state == "not_satisfied"

        if is_fp:
            icon = "⚠ FALSE POS"
        elif is_fn:
            icon = "⚠ FALSE NEG"

        flags = []
        c_gate_trace = c.get("gate_trace", [])
        c_entities = c.get("entities", {})
        unresolved = (c_entities.get("unresolved_terms", [])
                      if isinstance(c_entities, dict) else [])
        fab_ids = [u.get("term", "") for u in unresolved
                   if isinstance(u, dict) and u.get("type") == "id_like"]

        if fab_ids:
            flags.append("fabricated_id")
        qra_count = 0
        for step in c_gate_trace:
            if step.get("gate") == "step_2_recall":
                qra_count = step.get("data", {}).get("qra_count", 0)
                break
        if 0 < qra_count < 5:
            flags.append("thin_evidence")
        if is_fp:
            flags.append("grounding_failure")

        flags_str = ", ".join(flags) if flags else ""
        unresolved_str = ", ".join(fab_ids) if fab_ids else ""

        lines.append(
            f"| {cid} | {icon} {c_state} | {c_grade} "
            f"| {flags_str} | {unresolved_str} | {c_question} |")

    lines.append("")

    # --- Sign-off ---
    lines.append("---")
    lines.append("")
    lines.append("| Reviewer | Date | Disposition |")
    lines.append("|----------|------|-------------|")
    lines.append("| | | |")
    lines.append("")

    return "\n".join(lines)


def _render_step_details(gate_trace: list[dict]) -> list[str]:
    """Render step-by-step details for the execution trace."""
    lines: list[str] = []
    lines.append("### Step Details")
    lines.append("")

    step_names = {
        "step_1_topic": "Step 1: On-topic Check",
        "step_2_recall": "Step 2: Per-Component Recall",
        "step_3_technique_bridge": "Step 3: Same-Technique Check",
        "step_4_clarify": "Step 4: Entity Clarification",
        "step_4_decompose": "Step 4: Decompose Claims",
        "step_5_lean4": "Step 5: Formal Verification",
        "gate_1_topic": "Gate 1: On-topic?",
        "gate_2_recall": "Gate 2: Recall Techniques",
        "gate_3_coverage": "Gate 3: Technique Coverage",
        "gate_4_decompose": "Gate 4: Decompose Claims",
    }

    for g in gate_trace:
        gate_id = g.get("gate", "unknown")
        passed = g.get("passed", False)
        detail = g.get("detail", "")
        data = g.get("data", {})

        name = step_names.get(gate_id, gate_id)
        icon = "PASS" if passed else "FAIL"

        lines.append(f"#### {name}: {icon}")
        lines.append("")
        lines.append(f"**Result:** {detail}")
        lines.append("")

        if gate_id == "step_2_recall" and passed:
            qra_count = data.get("qra_count", 0)
            lines.append(f"**QRAs recalled:** {qra_count}")
            tech_groups = data.get("technique_groups", {})
            if tech_groups:
                lines.append(
                    f"**Technique groups:** "
                    f"{', '.join(f'{k}({v})' for k, v in tech_groups.items())}")
            lines.append("")

        elif gate_id == "step_3_technique_bridge":
            bridge = data.get("bridge_found", False)
            tech_names = data.get("technique_names", [])
            overlap = data.get("overlap", [])
            pairs = data.get("related_pairs_count", 0)
            lines.append(f"**Bridge found:** {'Yes' if bridge else 'No'}")
            if tech_names:
                lines.append(
                    f"**Techniques:** {', '.join(tech_names[:5])}")
            if overlap:
                lines.append(
                    f"**Entity overlap:** "
                    f"{', '.join(str(o) for o in overlap[:5])}")
            lines.append(f"**Related pairs:** {pairs}")
            lines.append("")

        elif gate_id == "step_4_clarify":
            clarify = data.get("clarify", {})
            if isinstance(clarify, dict):
                conf = clarify.get("confidence")
                if conf is not None:
                    lines.append(f"**Confidence:** {conf}")
                needs = clarify.get("needs_clarification")
                if needs is not None:
                    lines.append(
                        f"**Needs clarification:** "
                        f"{'Yes' if needs else 'No'}")
            lines.append("")

        elif gate_id in (
            "step_5b_plausibility",
            "step_6_plausibility",
        ):
            lines.extend(render_plausibility_step_details(g))

        elif gate_id == "step_5_lean4":
            prediction = data.get("prediction", "unknown")
            lines.append(f"**Provability:** {prediction}")
            if isinstance(data.get("provable_confidence"), (int, float)):
                lines.append(
                    f"**Confidence:** "
                    f"{data.get('provable_confidence', 0.0):.0%}")
            lines.append(
                f"**Proof attempted:** "
                f"{'Yes' if data.get('proof_attempted') else 'No'}")
            if data.get("proof_skipped"):
                lines.append("**Proof skipped:** Yes")
            if data.get("gate_blocked"):
                lines.append("**Gate blocked:** Yes")
            if data.get("reason"):
                lines.append(f"**Reason:** {data.get('reason')}")
            lines.append("")

    return lines


# ---------------------------------------------------------------------------
# Legacy compatibility — render_markdown_report wraps render_full_report
# ---------------------------------------------------------------------------

def render_markdown_report(case: dict) -> str:
    """Render evidence case as markdown. Delegates to render_full_report."""
    return render_full_report(case)


# ---------------------------------------------------------------------------
# Mermaid flow diagram (legacy compat)
# ---------------------------------------------------------------------------

def build_mermaid_tree(case: dict) -> str:
    """Build a Mermaid graph showing the execution flow (legacy compat)."""
    lines = ["graph TD"]
    claim = case.get("claim", {})
    gate_trace = case.get("gate_trace", [])
    verdict = case.get("verdict", {})

    claim_text = claim.get("text", "?")[:40].replace('"', "'")
    lines.append(f'  Q["{claim_text}"]')

    prev_id = "Q"
    for g in gate_trace:
        gate_id = g.get("gate", "unknown").replace(".", "_")
        passed = g.get("passed", False)
        detail = g.get("detail", "")[:50].replace('"', "'")

        if passed:
            lines.append(f'  {gate_id}["{gate_id}<br/>{detail}"]:::pass')
        else:
            lines.append(f'  {gate_id}["{gate_id}<br/>{detail}"]:::fail')

        lines.append(f"  {prev_id} --> {gate_id}")
        prev_id = gate_id

    if verdict:
        vid = "verdict"
        vstate = verdict.get("state", "?").upper()
        vgrade = verdict.get("grade", "?")
        lines.append(f'  {vid}["{vstate}<br/>Grade {vgrade}"]:::verdict')
        lines.append(f"  {prev_id} --> {vid}")

    lines.append("  classDef pass fill:#9f9,stroke:#090")
    lines.append("  classDef fail fill:#f66,stroke:#900")
    lines.append("  classDef verdict fill:#ff9,stroke:#990")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Figure data for /create-figure
# ---------------------------------------------------------------------------

def build_figure_data(case: dict) -> dict:
    """Build dashboard-ready metrics from an evidence case."""
    gate_trace = case.get("gate_trace", [])
    evidence = case.get("evidence", [])
    verdict = case.get("verdict", {})
    gates_passed = case.get("gates_passed", 0)
    gates_total = case.get("gates_total", 5)

    bar_metrics = {}
    for g in gate_trace:
        gate_id = g.get("gate", "unknown")
        bar_metrics[gate_id] = 1.0 if g.get("passed") else 0.0

    radar = {
        "axes": ["steps_passed", "controls_found", "qras_found",
                 "technique_bridge", "evidence"],
        "values": [
            round(gates_passed / max(gates_total, 1), 2),
            round(min(1.0, len(
                case.get("claim", {}).get("control_ids", [])) / 10), 2),
            round(min(1.0, len(evidence) / 5), 2),
            1.0 if any(
                g.get("gate") == "step_3_technique_bridge" and g.get("passed")
                for g in gate_trace) else 0.0,
            round(min(1.0, len(evidence) / 5), 2),
        ],
    }

    state = verdict.get("state", "inconclusive")
    pie = {"satisfied": 0, "inconclusive": 0, "not_satisfied": 0}
    if state in pie:
        pie[state] = 1

    mermaid_code = build_mermaid_tree(case)

    headers = ["Step", "Passed", "Detail"]
    rows = [
        [g.get("gate", "?"),
         "YES" if g.get("passed") else "NO",
         g.get("detail", "")[:60]]
        for g in gate_trace
    ]

    return {
        "bar": {"metrics": bar_metrics},
        "radar": radar,
        "pie": pie,
        "mermaid": {"code": mermaid_code},
        "table": {"headers": headers, "rows": rows},
    }


# ---------------------------------------------------------------------------
# /create-figure integration (best-effort)
# ---------------------------------------------------------------------------

def invoke_create_figure(case: dict, output_dir: Path) -> list[Path]:
    """Invoke /create-figure for charts. Best-effort."""
    output_dir.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []

    if not CREATE_FIGURE_SKILL.exists():
        return created

    figure_data = build_figure_data(case)

    for chart_type, key, title, filename in [
        ("metrics", "bar", "Step Pass/Fail", "step_results.png"),
        ("radar", "radar", "Evidence Quality Profile", "quality_radar.png"),
    ]:
        chart_path = output_dir / filename
        try:
            data_input = json.dumps(
                figure_data[key]["metrics"] if key == "bar"
                else figure_data[key])
            subprocess.run(
                [str(CREATE_FIGURE_SKILL), chart_type,
                 "--title", title, "--data", data_input,
                 "--output", str(chart_path)],
                capture_output=True, text=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            if chart_path.exists():
                created.append(chart_path)
        except (subprocess.TimeoutExpired, OSError):
            pass

    return created


# ---------------------------------------------------------------------------
# Top-level report generator
# ---------------------------------------------------------------------------

def generate_report(case: dict, output_dir: Path) -> Path:
    """Generate full report: report.md + figure_data.json + optional figures."""
    output_dir.mkdir(parents=True, exist_ok=True)

    report_path = output_dir / "report.md"
    report_path.write_text(render_full_report(case))

    figure_data_path = output_dir / "figure_data.json"
    figure_data_path.write_text(
        json.dumps(build_figure_data(case), indent=2, default=str))

    invoke_create_figure(case, output_dir)

    return report_path
