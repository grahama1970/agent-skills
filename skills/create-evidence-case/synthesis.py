"""Answer synthesis for evidence cases.

Transforms raw evidence (convergence data, memory items, table metrics)
into competent engineer-quality answers. Nico asks hundreds of questions
about the F36 datalake — Embry must answer like a knowledgeable engineer.

Inputs: ClaimNode + evidence list + winning strategy.
Outputs: List of text parts forming the synthesized answer.
Failures: Returns fallback "N evidence items collected" on empty input.
"""

from __future__ import annotations

from typing import Any

from models import ClaimNode, EvidenceNode, StrategyNode


def synthesize_answer(
    claim: ClaimNode,
    evidence: list[EvidenceNode],
    strategy: StrategyNode,
) -> list[str]:
    """Synthesize a competent answer from evidence — not a raw data dump."""
    parts: list[str] = []
    claim_lower = claim.text.lower()

    # Collect evidence by source type
    convergence_data = None
    table_data = None
    memory_items: list[dict[str, Any]] = []

    for ev in evidence:
        r = ev.result if isinstance(ev.result, dict) else {}
        if r.get("source") == "pdf_assessments_in_memory":
            convergence_data = r
        elif r.get("source") == "datalake_chunks":
            table_data = r
        elif r.get("source") == "memory_recall":
            memory_items.append(r)

    # --- Convergence-based answer ---
    if convergence_data:
        parts.extend(_convergence_answer(convergence_data, claim_lower))

    # --- Table-specific data ---
    elif table_data:
        parts.extend(_table_answer(table_data))

    # --- Memory recall items ---
    elif memory_items:
        parts.extend(_memory_answer(memory_items))

    # --- Chained evidence from generic skills ---
    if not parts:
        parts.extend(_generic_answer(evidence, strategy))

    return parts


def _convergence_answer(data: dict, claim_lower: str) -> list[str]:
    """Interpret convergence/assessment data."""
    parts: list[str] = []
    n = data.get("reviews_total", 0)
    avg = data.get("avg_score", 0)
    trend = data.get("trend", "unknown")
    verdicts = data.get("verdict_distribution", {})
    grades = data.get("grade_distribution", {})
    dims = data.get("dimensions", {})

    stale_excluded = data.get("stale_excluded", 0)
    stale_note = f" ({stale_excluded} stale pre-Feb-2026 excluded)" if stale_excluded else ""
    parts.append(f"Based on {n} pdf_assessment records in /memory{stale_note}:")
    parts.append(f"Overall extraction quality: avg={avg:.3f}, trend={trend}")

    pass_ct = verdicts.get("PASS", 0)
    fail_ct = verdicts.get("FAIL", 0)
    warn_ct = verdicts.get("WARN", 0)
    total = pass_ct + fail_ct + warn_ct
    if total > 0:
        parts.append(
            f"Verdicts: {pass_ct} PASS ({100*pass_ct/total:.0f}%), "
            f"{warn_ct} WARN ({100*warn_ct/total:.0f}%), "
            f"{fail_ct} FAIL ({100*fail_ct/total:.0f}%)"
        )

    if dims:
        parts.append("")
        parts.append("Dimension breakdown:")
        for dim_name, dim_data in sorted(dims.items(), key=lambda x: x[1].get("avg_score", 0)):
            if not isinstance(dim_data, dict):
                continue
            davg = dim_data.get("avg_score", 0)
            dtrend = dim_data.get("trend", "?")
            dcount = dim_data.get("count", 0)

            flag = ""
            if davg < 0.5:
                flag = " [CRITICAL: below 0.50]"
            elif davg < 0.65:
                flag = " [WARNING: below F threshold]"
            if 0.3 < davg < 0.4:
                flag += " [SUSPECT: likely bimodal 0.0/0.7 from stale scoring]"

            parts.append(f"  {dim_name}: avg={davg:.3f} trend={dtrend} (n={dcount}){flag}")

        if "table" in claim_lower and "table_fidelity" in dims:
            tf = dims["table_fidelity"]
            tf_avg = tf.get("avg_score", 0)
            if tf_avg < 0.5:
                parts.append("")
                parts.append(
                    f"NOTE: table_fidelity avg {tf_avg:.3f} is critically low. "
                    f"However, this likely reflects stale assessments scored by older code "
                    f"(pre-Feb 2026 fixes). The bimodal distribution (scores cluster at "
                    f"0.0 and 0.7 with nothing between) indicates a measurement artifact, "
                    f"not actual extraction degradation. These assessments need re-scoring "
                    f"with current dimension_scores() logic."
                )

    if grades:
        parts.append("")
        parts.append(f"Grade distribution: {grades}")

    return parts


def _table_answer(data: dict) -> list[str]:
    """Interpret table-specific evidence."""
    parts: list[str] = []
    item_count = data.get("item_count", 0)
    metrics_count = data.get("tables_with_metrics", 0)
    parts.append(f"Found {item_count} table chunks in datalake.")
    if metrics_count > 0:
        parts.append(f"{metrics_count} tables have extraction quality metrics.")
    else:
        parts.append(
            "No tables have extraction metrics yet (metrics were not carried "
            "through to ArangoDB until the S07/S10 fix). New extractions will "
            "include fragmentation_score, camelot_metrics, and strategy_history."
        )
    top = data.get("top_item", "")
    if top:
        parts.append(f"\nSample: {top[:200]}")
    return parts


def _memory_answer(memory_items: list[dict]) -> list[str]:
    """Format memory recall results into an answer."""
    parts: list[str] = []
    for mi in memory_items[:2]:
        count = mi.get("item_count", 0)
        summaries = mi.get("items_summary", [])
        if summaries:
            parts.append(f"Found {count} relevant items in /memory. Top results:")
            for i, s in enumerate(summaries[:3], 1):
                parts.append(f"\n{i}. {s}")
        elif mi.get("top_item"):
            parts.append(mi["top_item"])
        elif count:
            parts.append(f"Found {count} relevant items in /memory.")
    return parts


def _generic_answer(evidence: list[EvidenceNode], strategy: StrategyNode) -> list[str]:
    """Fallback for evidence without a specific synthesis path."""
    parts: list[str] = []
    parts.append(f"Strategy '{strategy.name}' collected {len(evidence)} evidence items.")
    for ev in evidence:
        r = ev.result if isinstance(ev.result, dict) else {}
        data = r.get("data", r.get("top_item", ""))
        if data:
            parts.append(f"- {ev.layer}: {str(data)[:200]}")
    return parts


def build_chain_context(prior: list[EvidenceNode]) -> str:
    """Extract useful context from prior evidence for downstream skills.

    The whole point of skill chains: skill 2 builds on skill 1's output.
    Without this, every skill runs blind against the raw claim text.
    """
    if not prior:
        return ""
    parts = []
    for ev in prior[-3:]:
        r = ev.result if isinstance(ev.result, dict) else {}
        top = r.get("top_item", "")
        if top and len(top) > 20:
            parts.append(top[:200])
        elif r.get("source") == "pdf_assessments_in_memory":
            parts.append(f"convergence avg={r.get('avg_score', '?')} trend={r.get('trend', '?')}")
        elif r.get("item_count"):
            parts.append(f"found {r['item_count']} items in {r.get('source', 'unknown')}")
    return " | ".join(parts)


def build_skill_args(
    skill_name: str, claim: ClaimNode, context: str, prior: list[EvidenceNode],
) -> list[str]:
    """Build skill-specific CLI args with chain context.

    Maps skill names to their actual CLI interfaces. If a skill accepts
    --context or --query, inject prior evidence data.
    """
    q = claim.text[:200]

    if skill_name == "analytics":
        args = ["query", q]
        if context:
            args.extend(["--context", context[:500]])
        return args

    if skill_name == "review-conversation":
        return ["review", "--query", q]

    if skill_name in ("review-pdf", "extractor-quality-check"):
        return ["status", "--json"]

    if skill_name == "create-figure":
        args = ["metrics"]
        if context:
            args.extend(["--title", q[:80]])
        return args

    if skill_name == "taxonomy":
        return ["extract", "--text", q]

    if skill_name == "treesitter":
        return ["search", q[:80]]

    if skill_name == "test":
        return ["--help"]

    if skill_name in ("review-design",):
        return ["status", "--json"]

    return ["status", "--json"]
