"""Decision chain and LLM rationale renderers for evidence case reports.

Split from report_sections.py to stay under 800-line limit.
These renderers surface the explicit decision flow and LLM reasoning
so an auditor can scan the verdict logic in 2-5 seconds.
"""
from __future__ import annotations

from typing import Any


def render_decision_chain(case: dict) -> str:
    """Render a linear decision chain: the yes/no checks a human needs.

    Designed so an auditor can scan the chain in 2-5 seconds and see
    exactly WHERE the pipeline decided to answer vs clarify.
    """
    gate_trace = case.get("gate_trace", [])
    if not gate_trace:
        return ""

    gates: dict[str, dict] = {}
    for g in gate_trace:
        gates[g.get("gate", "")] = g

    lines: list[str] = ["## Decision Chain", ""]

    # Gate names must match collect.py's actual gate_trace output.
    # Some gates are mutually exclusive (step_4_clarify vs step_4_decompose).
    chain = [
        ("step_1_topic", "On-topic?"),
        ("step_2_recall", "QRAs found?"),
        ("step_2b_grounding", "Terms grounded?"),
        ("step_3_technique_bridge", "Same technique?"),
        ("step_4_clarify", "Clarify needed?"),
        ("step_4_decompose", "Decomposable?"),
        ("step_5_lean4", "Lean4 proof?"),
        ("step_5b_plausibility", "LLM: plausible?"),
        ("step_6_plausibility", "LLM: plausible?"),
    ]

    lines.append("| # | Check | Result | Detail |")
    lines.append("|---|-------|--------|--------|")

    last_failed = None
    seen_labels: set[str] = set()
    row_num = 0
    for gate_id, short_name in chain:
        g = gates.get(gate_id)
        if not g:
            continue
        # Deduplicate: step_5b and step_6 both render as "LLM: plausible?"
        if short_name in seen_labels:
            continue
        seen_labels.add(short_name)
        row_num += 1
        passed = g.get("passed", False)
        icon = "YES" if passed else "**NO**"
        detail = g.get("detail", "")[:80]
        lines.append(f"| {row_num} | {short_name} | {icon} | {detail} |")
        if not passed and last_failed is None:
            last_failed = (gate_id, short_name, detail)

    lines.append("")

    verdict = case.get("verdict", {})
    state = verdict.get("state", "unknown")

    if state == "satisfied":
        lines.append("**Outcome:** Answer the question (all checks passed)")
    elif last_failed:
        _, name, _ = last_failed
        lines.append(f"**Stopped at:** {name}")
        lines.append("")
        lines.append("**Outcome:** Route to `/memory clarify`")
    else:
        lines.append(f"**Outcome:** {state}")
    lines.append("")

    # Surface clarify rationale (step_4_clarify has nested clarify dict)
    clarify_gate = gates.get("step_4_clarify")
    if clarify_gate:
        clarify_section = _render_clarify_rationale(clarify_gate)
        if clarify_section:
            lines.append(clarify_section)

    # Surface plausibility rationale (step_5b or step_6 — whichever fired)
    plaus_gate = gates.get("step_5b_plausibility") or gates.get("step_6_plausibility")
    if plaus_gate:
        plaus_section = _render_llm_rationale(
            plaus_gate,
            "Plausibility",
            rationale_keys=["reason"],
            clarify_key="clarifying_questions",
        )
        if plaus_section:
            lines.append(plaus_section)

    return "\n".join(lines)


def _render_clarify_rationale(gate: dict | None) -> str:
    """Render /memory clarify rationale from step_4_clarify gate."""
    if not gate:
        return ""

    data = gate.get("data", {})
    if not isinstance(data, dict):
        return ""

    clarify = data.get("clarify", {})
    if not isinstance(clarify, dict):
        return ""

    lines: list[str] = []
    confidence = clarify.get("confidence")
    needs = clarify.get("needs_clarification")
    questions = clarify.get("clarify_questions", [])
    intent = clarify.get("intent", {})

    if confidence is not None or needs is not None:
        lines.append("### Clarify Analysis")
        lines.append("")
        if confidence is not None:
            lines.append(f"**Confidence:** {confidence}")
        if needs is not None:
            lines.append(
                f"**Needs clarification:** {'Yes' if needs else 'No'}"
            )
        if isinstance(intent, dict):
            action = intent.get("action", "")
            bridges = intent.get("bridges", [])
            if action:
                lines.append(f"**Intent action:** {action}")
            if bridges:
                lines.append(f"**Bridges:** {', '.join(str(b) for b in bridges)}")
        lines.append("")

    if isinstance(questions, list) and questions:
        lines.append("**Clarifying questions:**")
        lines.append("")
        for cq in questions[:5]:
            lines.append(f"- {cq}")
        lines.append("")

    return "\n".join(lines)


def _render_llm_rationale(
    gate: dict | None,
    label: str,
    rationale_keys: list[str],
    clarify_key: str,
) -> str:
    """Render LLM rationale from a gate's data dict."""
    if not gate:
        return ""

    data = gate.get("data", {})
    if not isinstance(data, dict):
        return ""

    # Find rationale from data dict or fall back to gate detail
    rationale = ""
    for key in rationale_keys:
        rationale = data.get(key, "")
        if rationale:
            break
    if not rationale:
        rationale = gate.get("detail", "")

    lines: list[str] = []

    if rationale:
        lines.append(f"### LLM Rationale ({label})")
        lines.append("")
        lines.append(f"> {rationale}")
        lines.append("")

    # Handle single clarifying question or list
    clarify_val = data.get(clarify_key)
    if isinstance(clarify_val, str) and clarify_val:
        lines.append(f"**Suggested clarification:** {clarify_val}")
        lines.append("")
    elif isinstance(clarify_val, list) and clarify_val:
        lines.append("**Suggested questions:**")
        lines.append("")
        for cq in clarify_val[:5]:
            lines.append(f"- {cq}")
        lines.append("")

    return "\n".join(lines)


def render_semantic_step_details(gate: dict) -> list[str]:
    """Render step_4_semantic_relation details for the step details section."""
    lines: list[str] = []
    data = gate.get("data", {})
    if not isinstance(data, dict):
        return lines

    related = data.get("related")
    answerable = data.get("answerable")
    rationale = data.get("rationale", "")
    clarify_q = data.get("clarifying_question", "")

    if related is not None:
        lines.append(f"**Controls related:** {'Yes' if related else 'No'}")
    if answerable is not None:
        lines.append(f"**Question answerable:** {'Yes' if answerable else 'No'}")
    if rationale:
        lines.append(f"**LLM rationale:** {rationale}")
    if clarify_q:
        lines.append(f"**Clarifying question:** {clarify_q}")

    bridge = data.get("bridge_evidence", {})
    if isinstance(bridge, dict):
        basis = bridge.get("bridge_basis", "")
        if basis:
            lines.append(f"**Bridge basis:** {basis}")
        tactic = bridge.get("shared_tactic", "")
        if tactic:
            lines.append(f"**Shared tactic:** {tactic}")
        pairs = bridge.get("related_pairs_count", 0)
        if pairs:
            lines.append(f"**Related pairs:** {pairs}")

    lines.append("")
    return lines


def render_plausibility_step_details(gate: dict) -> list[str]:
    """Render step_5b_plausibility details for the step details section."""
    lines: list[str] = []
    data = gate.get("data", {})
    if not isinstance(data, dict):
        return lines

    plausible = data.get("plausible")
    reason = data.get("reason", "")
    backend = data.get("backend", "")
    clarify_qs = data.get("clarifying_questions", [])

    if plausible is not None:
        lines.append(f"**Plausible:** {'Yes' if plausible else 'No'}")
    if reason:
        lines.append(f"**Reason:** {reason}")
    if backend:
        lines.append(f"**Backend:** {backend}")
    if clarify_qs:
        lines.append("**Clarifying questions:**")
        for cq in clarify_qs[:5]:
            lines.append(f"- {cq}")

    lines.append("")
    return lines
