"""Markdown rendering for evidence cases.

Produces mermaid diagrams, entity metrics tables, and gate summary tables.
Extracted from evidence_case.py to keep that module under 800 LOC.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evidence_case import DatalakeConnection, EvidenceCase


def render_markdown(case: EvidenceCase) -> str:
    """Render an EvidenceCase as a markdown report with mermaid diagram."""
    lines: list[str] = []
    lines.append(f'# Evidence Case: "{case.question[:120]}"')
    lines.append("")

    # Mermaid entity graph (with datalake subgraph if connections exist)
    if case.entities:
        lines.append("## Entity Graph")
        lines.append("")
        lines.append("```mermaid")
        lines.append("graph LR")

        # Draw datalake subgraph with taxonomy bridge tags
        if case.datalake_connections:
            lines.append('  subgraph Datalake["Datalake"]')
            for conn in case.datalake_connections:
                bridge_str = ", ".join(sorted(conn.shared_bridges.keys())[:3])
                label = conn.category
                if bridge_str:
                    label += f"<br/>{bridge_str}"
                safe_cat = conn.category.replace("-", "_")
                lines.append(f'    {safe_cat}["{label}"]:::f36')
            lines.append("  end")
        elif case.f36_categories:
            lines.append("  subgraph F36 Context")
            for cat in case.f36_categories:
                lines.append(f'    {cat}["{cat}"]:::f36')
            lines.append("  end")

        # SPARTA entity nodes
        sparta_entities = [
            e for e in case.entities
            if e.entity_id not in case.f36_categories
        ]
        if sparta_entities and case.datalake_connections:
            lines.append('  subgraph SPARTA')
            for e in sparta_entities:
                label = e.entity_id
                if e.exists:
                    label += f"<br/>{e.qra_count} QRAs"
                style = "" if e.exists else ":::invalid"
                safe_id = e.entity_id.replace("-", "_")
                lines.append(f'    {safe_id}["{label}"]{style}')
            lines.append("  end")
        else:
            for e in case.entities:
                if e.entity_id in case.f36_categories:
                    continue
                label = e.entity_id
                if e.exists:
                    label += f"\\n{e.qra_count} QRAs"
                style = "" if e.exists else ":::invalid"
                safe_id = e.entity_id.replace("-", "_")
                lines.append(f'  {safe_id}["{label}"]{style}')

        # Datalake-to-SPARTA edges showing shared taxonomy bridges
        for conn in case.datalake_connections:
            if conn.avg_graph_score > 0 or conn.connected_controls:
                safe_cat = conn.category.replace("-", "_")
                # Edge label: shared bridge tags + graph score
                shared_str = ", ".join(sorted(conn.shared_bridges.keys())[:2])
                label_parts = []
                if shared_str:
                    label_parts.append(shared_str)
                label_parts.append(f"graph={conn.avg_graph_score:.2f}")
                label = " | ".join(label_parts)
                for ctrl_id in conn.connected_controls[:5]:
                    safe_ctrl = ctrl_id.replace("-", "_")
                    lines.append(f"  {safe_cat} -->|{label}| {safe_ctrl}")

        # SPARTA-to-SPARTA relationship edges
        for rel in case.relationships:
            if rel.found:
                src = rel.source.replace("-", "_")
                tgt = rel.target.replace("-", "_")
                via_label = f"via {rel.via[0]}" if rel.via else f"{rel.hops}hop"
                lines.append(f"  {src} -->|{via_label}| {tgt}")

        lines.append("  classDef invalid fill:#f99,stroke:#c00")
        lines.append("  classDef f36 fill:#bbf,stroke:#33c")
        lines.append("```")
        lines.append("")

    # Datalake context table
    if case.datalake_connections:
        lines.append("## Datalake Context")
        lines.append("")
        lines.append(
            "| Category | Recall Conf | Avg Graph | Shared Bridges | Connected Controls |"
        )
        lines.append(
            "|----------|-------------|-----------|----------------|-------------------|"
        )
        for conn in case.datalake_connections:
            conf = f"{conn.recall_confidence:.2f}" if conn.recall_confidence else "-"
            graph = f"{conn.avg_graph_score:.2f}" if conn.avg_graph_score else "-"
            shared = ", ".join(
                f"{k} {v:.2f}" for k, v in sorted(
                    conn.shared_bridges.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:3]
            ) or "-"
            ctrls = str(len(conn.connected_controls)) if conn.connected_controls else "0"
            lines.append(
                f"| {conn.category} | {conf} | {graph} | {shared} | {ctrls} controls |"
            )
        lines.append("")

        # Taxonomy bridge detail: show both sides + intersection
        any_shared = any(conn.shared_bridges for conn in case.datalake_connections)
        if any_shared:
            lines.append("### Taxonomy Bridge Overlap")
            lines.append("")
            for conn in case.datalake_connections:
                if not conn.shared_bridges:
                    continue
                lines.append(f"**{conn.category}**")
                lines.append("")
                lines.append("| Bridge Tag | Datalake | SPARTA | Shared |")
                lines.append("|------------|----------|--------|--------|")
                all_tags = sorted(
                    set(conn.datalake_bridges) | set(conn.sparta_bridges),
                    key=lambda t: conn.shared_bridges.get(t, 0),
                    reverse=True,
                )
                for tag in all_tags:
                    dl = f"{conn.datalake_bridges[tag]:.2f}" if tag in conn.datalake_bridges else "-"
                    sp = f"{conn.sparta_bridges[tag]:.2f}" if tag in conn.sparta_bridges else "-"
                    sh = f"{conn.shared_bridges[tag]:.2f}" if tag in conn.shared_bridges else "-"
                    lines.append(f"| {tag} | {dl} | {sp} | {sh} |")
                lines.append("")

    # Entity metrics table
    if case.entities:
        lines.append("## Metrics")
        lines.append("")
        lines.append("| Entity | Exists | QRAs | Grounding | Path |")
        lines.append("|--------|--------|------|-----------|------|")
        for e in case.entities:
            exists = "Y" if e.exists else "N"
            qras = str(e.qra_count) if e.exists else "-"
            grounding = (
                f"{e.avg_grounding:.2f}"
                if e.exists and e.avg_grounding > 0
                else "-"
            )

            path_info = "-"
            for rel in case.relationships:
                if e.entity_id in (rel.source, rel.target) and rel.found:
                    path_info = f"Y {rel.hops}hop"
                    break
            
            # Formatting overrides for F36 datalake categories
            if e.entity_id in case.f36_categories:
                qras = "N/A"
                grounding = "N/A"
                path_info = "Context"

            lines.append(
                f"| {e.entity_id} | {exists} | {qras} | {grounding} | {path_info} |"
            )

        for e in case.entities:
            if not e.exists and e.suggestions:
                lines.append(
                    f"\n> **{e.entity_id}** not found. "
                    f"Did you mean: {', '.join(e.suggestions[:5])}?"
                )

        lines.append("")

    # Gates table
    lines.append("## Gates")
    lines.append("")
    lines.append("| # | Gate | Result | Time |")
    lines.append("|---|------|--------|------|")
    for g in case.gates:
        icon = "Y" if g.passed else "N"
        time_str = f"{g.time_ms:.0f}ms" if g.time_ms >= 1 else "<1ms"
        lines.append(f"| {g.gate} | {g.name} | {icon} | {time_str} |")
    lines.append("")

    # Sub-cases (from decomposition)
    if case.sub_cases:
        lines.append("## Sub-Cases (Decomposed)")
        lines.append("")
        for i, sc in enumerate(case.sub_cases, 1):
            lines.append(f"### Sub-Case {i}: {sc.classification}")
            lines.append(f"> {sc.question[:120]}")
            lines.append(
                f"> QRAs: {sc.total_qras} | Grounding: {sc.avg_grounding:.2f}"
            )
            lines.append("")

    # Classification
    total_time = f"{case.total_time_ms:.0f}ms"
    lines.append(f"**Classification: {case.classification}** ({total_time} total)")

    return "\n".join(lines)
