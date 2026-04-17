"""Mermaid conversation flow diagram generation.

Produces Mermaid flowchart markup with inline grading metadata for
visual conversation flow analysis. Renders in GitHub, VS Code preview,
or Mermaid Live.
"""
from __future__ import annotations

from collections import Counter
from typing import Optional


def _mermaid_escape(text: str, max_len: int = 60) -> str:
    """Escape user-supplied text for Mermaid node labels.

    Mermaid treats [ ] { } ( ) < > " as special characters inside node labels.
    Use Mermaid HTML-entity syntax (#nn;) to prevent parse errors.
    """
    text = text.replace("\n", " ")
    # Escape # first to avoid double-encoding
    text = text.replace("#", "#35;")
    text = text.replace('"', "#34;")
    text = text.replace("[", "#91;").replace("]", "#93;")
    text = text.replace("{", "#123;").replace("}", "#125;")
    text = text.replace("(", "#40;").replace(")", "#41;")
    text = text.replace("<", "#60;").replace(">", "#62;")
    if len(text) > max_len:
        text = text[:max_len - 3] + "..."
    return text


def _grade_emoji(grade: str) -> str:
    """Grade to visual indicator (no emoji — uses text markers)."""
    return {"A+": "A+", "A": "A", "B": "B", "C": "C", "F": "F"}.get(grade, "?")


def _eval_marker(evaluation: str) -> str:
    """Persona evaluation to compact marker."""
    return {
        "satisfactory": "OK",
        "incomplete": "INCMPL",
        "wrong": "WRONG",
        "flaw_caught": "CAUGHT",
        "flaw_missed": "MISSED",
    }.get(evaluation, "?")


def _session_summary(
    session: dict,
    shadow_entry: Optional[dict] = None,
    delta_entry: Optional[dict] = None,
) -> str:
    """Generate a markdown summary block for a session (above the Mermaid chart)."""
    persona = session.get("persona", "?")
    seed = session.get("seed_question", {})
    diff = seed.get("difficulty", "?")
    target = seed.get("target_control", "?")
    grade_data = session.get("grade", {}) or {}
    final_grade = grade_data.get("grade", "?")
    final_composite = grade_data.get("composite", 0)
    resolution = session.get("resolution", "?")
    turns = session.get("turns", [])

    # Metrics
    num_turns = len(turns)
    persona_evals = []
    qra_total = 0
    for t in turns:
        meta = t.get("metadata", {})
        if t.get("role") == "persona":
            ev = meta.get("evaluation", "")
            if ev:
                persona_evals.append(ev)
        else:
            sg = meta.get("self_grade_final", {}) or {}
            raw_qra = sg.get("qra_count", 0)
            qra_total += int(raw_qra) if isinstance(raw_qra, (int, float)) else 0

    lines = []
    lines.append(f"**Persona:** {persona} | **Difficulty:** {diff} | **Target:** {target or 'None'}")
    lines.append(f"**Grade:** {final_grade} ({final_composite:.0%}) | **Resolution:** {resolution} | **Turns:** {num_turns}")

    # Dimension scores
    scores = grade_data.get("scores", {})
    if scores:
        dims = " | ".join(f"{k}: {float(v):.0%}" for k, v in sorted(scores.items()))
        lines.append(f"**Dimensions:** {dims}")

    # Persona evaluations
    if persona_evals:
        lines.append(f"**Persona evals:** {', '.join(persona_evals)} | **QRAs cited:** {qra_total}")

    # Teacher comparison
    if shadow_entry:
        local_g = shadow_entry.get("local_grade", "?")
        teacher_g = shadow_entry.get("teacher_grade", "?")
        agreed = shadow_entry.get("agreed", False)
        lines.append(f"**Student:** {local_g} | **Teacher:** {teacher_g} | **{'AGREE' if agreed else 'DISAGREE'}**")

    # Delta
    if delta_entry:
        first = delta_entry.get("first_composite", 0)
        final_c = delta_entry.get("final_composite", 0)
        delta = delta_entry.get("delta", 0)
        lines.append(f"**Improvement:** {first:.0%} -> {final_c:.0%} ({delta:+.0%})")

    # Lessons learned / next steps
    lessons = _derive_lessons(session, scores, persona_evals, resolution)
    if lessons:
        lines.append("")
        lines.append("**Lessons / Next Steps:**")
        for lesson in lessons:
            lines.append(f"- {lesson}")

    return "\n".join(lines)


def _derive_lessons(
    session: dict,
    scores: dict,
    persona_evals: list[str],
    resolution: str,
) -> list[str]:
    """Derive actionable lessons and next-step improvements from session data."""
    lessons = []
    grade_data = session.get("grade", {}) or {}
    final_grade = grade_data.get("grade", "?")
    composite = float(grade_data.get("composite", 0) or 0)
    turns = session.get("turns", [])
    seed = session.get("seed_question", {})
    diff = seed.get("difficulty", "?")
    target = seed.get("target_control")

    # Check for wrong-control retrieval
    system_turns = [t for t in turns if t.get("role") != "persona"]
    for t in system_turns:
        content = t.get("content", "")
        if target and target not in content and "REC-" in content:
            lessons.append(f"WRONG CONTROL: Asked about {target} but retrieved unrelated QRA. Fix: improve ArangoSearch query specificity for control_id matching.")
            break

    # Check for stuck loops (same response repeated)
    system_contents = [t.get("content", "")[:100] for t in system_turns]
    if len(system_contents) >= 2 and system_contents[0] == system_contents[1]:
        lessons.append("STUCK LOOP: Same response repeated after persona pushback. Fix: conversation_sim should detect duplicate responses and force retrieval strategy change.")

    # Unnecessary clarification on direct questions
    if diff in ("simple", "medium"):
        for t in system_turns:
            if t.get("action") == "CLARIFY" and target:
                lessons.append(f"OVER-CLARIFY: SPARTA clarified on a {diff} question that had a clear target control. Fix: adjust ambiguity classifier threshold or add control-ID detection bypass.")
                break

    # Low dimension scores
    for dim, score in sorted(scores.items()):
        score_f = float(score)
        if score_f <= 0.3:
            if dim == "error_detection":
                lessons.append(f"CRITICAL: error_detection={score_f:.0%}. SPARTA failed to detect an issue the persona flagged. Fix: add validation layer before response.")
            elif dim == "qra_citation_accuracy":
                lessons.append(f"LOW CITATION: qra_citation_accuracy={score_f:.0%}. Responses lack grounding in QRA corpus. Fix: check ArangoSearch view and embedding quality.")
            elif dim == "initial_response_quality":
                lessons.append(f"WEAK FIRST RESPONSE: initial_response_quality={score_f:.0%}. Fix: improve QRA retrieval ranking or NLG synthesis prompt.")
            else:
                lessons.append(f"LOW SCORE: {dim}={score_f:.0%}. Needs investigation.")

    # Resolution-based lessons
    if resolution == "no_coverage":
        lessons.append(f"NO COVERAGE: Target control {target or '?'} has no matching QRAs. Fix: run gap-filler for this control or verify it exists in sparta_controls collection.")

    # Persona caught a flaw — positive signal
    if "flaw_caught" in persona_evals:
        lessons.append("POSITIVE: Persona correctly caught a flaw. Error detection pipeline working.")

    # Perfect score
    if final_grade in ("A+", "A") and composite >= 0.95:
        lessons.append("EXEMPLAR: This session demonstrates ideal handling. Consider as training example.")

    # Regression (delta went negative)
    for t in turns:
        meta = t.get("metadata", {})
        sg = meta.get("self_grade_final", {}) or {}
        if sg and float(sg.get("composite", 0) or 0) > composite:
            lessons.append("REGRESSION: Self-grading loop made the score worse. Fix: investigate self-grading iteration logic.")
            break

    return lessons


def session_to_mermaid(
    session: dict,
    shadow_entry: Optional[dict] = None,
    delta_entry: Optional[dict] = None,
) -> str:
    """Generate a Mermaid flowchart for a single conversation session.

    All user-supplied text is escaped via _mermaid_escape.
    Structural labels use only safe characters (no raw [ ] { } < > in labels).
    """
    lines: list[str] = []
    seed = session.get("seed_question", {})
    diff = seed.get("difficulty", "?")
    target = seed.get("target_control", "?")
    grade_data = session.get("grade", {}) or {}
    final_grade = grade_data.get("grade", "?")
    final_composite = grade_data.get("composite", 0)
    resolution = session.get("resolution", "?")

    persona = session.get("persona", "unknown")
    lines.append("flowchart TD")
    lines.append(f'    SEED["{_mermaid_escape(persona)} asks about {_mermaid_escape(str(target))}<br/>difficulty: {diff}"]')

    turns = session.get("turns", [])
    prev_node = "SEED"

    for i, turn in enumerate(turns):
        node_id = f"T{i}"
        speaker = turn.get("speaker", "?")
        role = turn.get("role", "?")
        action = turn.get("action", "?")
        content = turn.get("content", "")
        meta = turn.get("metadata", {})

        if role == "persona":
            evaluation = meta.get("evaluation", "")
            outer_round = meta.get("outer_round", "")

            label_parts = [f"{_mermaid_escape(speaker)} {_mermaid_escape(action)}"]
            label_parts.append(f"{_mermaid_escape(content, 300)}")
            if evaluation:
                label_parts.append(f"Eval: {_eval_marker(evaluation)}")
            if outer_round:
                label_parts.append(f"Round {outer_round}")

            label = "<br/>".join(label_parts)
            lines.append(f'    {node_id}["{label}"]')

        else:
            sg = meta.get("self_grade_final", {})
            grade = sg.get("grade", "?") if sg else "?"
            comp = float(sg.get("composite", 0) or 0) if sg else 0
            raw_iters = sg.get("iteration", 0) if sg else 0
            iters = int(raw_iters) + 1 if isinstance(raw_iters, (int, float)) else 1
            raw_qra = sg.get("qra_count", 0) if sg else 0
            qra_count = int(raw_qra) if isinstance(raw_qra, (int, float)) else 0
            issues = sg.get("issues", []) if sg else []
            outer_round = meta.get("outer_round", "")

            label_parts = [f"SPARTA {_mermaid_escape(action)}"]
            label_parts.append(f"{_mermaid_escape(content, 300)}")
            label_parts.append(f"Grade: {_grade_emoji(grade)} {comp:.0%}")
            label_parts.append(f"QRAs: {qra_count} / Iters: {iters}")
            if issues:
                iss_str = ", ".join(_mermaid_escape(str(x), 60) for x in issues[:3])
                label_parts.append(f"Issues: {iss_str}")
            if outer_round:
                label_parts.append(f"Round {outer_round}")

            label = "<br/>".join(label_parts)
            lines.append(f'    {node_id}["{label}"]')

        # Edge label with composite delta annotation for regression tracking
        edge_label = action
        if role != "persona":
            meta = turn.get("metadata", {})
            sg = meta.get("self_grade_final", {})
            comp = float(sg.get("composite", 0) or 0) if sg else 0
            outer_round = meta.get("outer_round", 0)
            if comp > 0 and outer_round:
                edge_label = f"{action} | {comp:.0%}"
        lines.append(f"    {prev_node} -->|{edge_label}| {node_id}")
        prev_node = node_id

    # Final grade node — use stadium shape (safe)
    score_dims = grade_data.get("scores", {})
    dim_str = "<br/>".join(f"{d}: {float(v):.0%}" for d, v in sorted(score_dims.items()))

    final_parts = [f"GRADE: {final_grade} {final_composite:.0%}"]
    final_parts.append(f"Resolution: {resolution}")
    if dim_str:
        final_parts.append(dim_str)
    if shadow_entry:
        local_g = shadow_entry.get("local_grade", "?")
        teacher_g = shadow_entry.get("teacher_grade", "?")
        agreed = shadow_entry.get("agreed", False)
        final_parts.append(f"Student: {local_g} / Teacher: {teacher_g} / {'AGREE' if agreed else 'DISAGREE'}")
    if delta_entry:
        first = delta_entry.get("first_composite", 0)
        final_c = delta_entry.get("final_composite", 0)
        final_parts.append(f"Delta: {first:.0%} -> {final_c:.0%}")

    final_label = "<br/>".join(final_parts)
    lines.append(f'    FINAL(["{final_label}"])')
    lines.append(f"    {prev_node} --> FINAL")

    # Styling
    lines.append("")
    lines.append("    %% Styling")

    # Edge (link) styles: green for improvement, red for regression
    prev_comp = 0.0
    link_idx = 0  # Mermaid link indices are 0-based in order of appearance
    for i, turn in enumerate(turns):
        role = turn.get("role", "?")
        if role != "persona":
            meta = turn.get("metadata", {})
            sg = meta.get("self_grade_final", {})
            comp = float(sg.get("composite", 0) or 0) if sg else 0
            if comp > 0 and prev_comp > 0:
                delta = comp - prev_comp
                if delta > 0.02:
                    lines.append(f"    linkStyle {link_idx} stroke:#66bb6a,stroke-width:3px")
                elif delta < -0.02:
                    lines.append(f"    linkStyle {link_idx} stroke:#ef5350,stroke-width:3px")
            if comp > 0:
                prev_comp = comp
        link_idx += 1  # Each edge adds a link

    for i, turn in enumerate(turns):
        role = turn.get("role", "?")
        if role == "persona":
            lines.append(f"    style T{i} fill:#1a3a5c,stroke:#4fc3f7,color:#e0e0e0")
        else:
            meta = turn.get("metadata", {})
            sg = meta.get("self_grade_final", {})
            grade = sg.get("grade", "?") if sg else "?"
            if grade in ("A+", "A"):
                lines.append(f"    style T{i} fill:#1b5e20,stroke:#66bb6a,color:#e0e0e0")
            elif grade == "B":
                lines.append(f"    style T{i} fill:#4a3800,stroke:#ffb300,color:#e0e0e0")
            elif grade == "C":
                lines.append(f"    style T{i} fill:#4a2000,stroke:#ff8f00,color:#e0e0e0")
            else:
                lines.append(f"    style T{i} fill:#5a1a1a,stroke:#ef5350,color:#e0e0e0")

    grade_fill = {
        "A+": "#1b5e20", "A": "#1b5e20",
        "B": "#4a3800", "C": "#4a2000", "F": "#5a1a1a",
    }.get(final_grade, "#333333")
    grade_stroke = {
        "A+": "#66bb6a", "A": "#66bb6a",
        "B": "#ffb300", "C": "#ff8f00", "F": "#ef5350",
    }.get(final_grade, "#888888")
    lines.append(f"    style FINAL fill:{grade_fill},stroke:{grade_stroke},color:#e0e0e0")
    lines.append("    style SEED fill:#0d1b2a,stroke:#778da9,color:#e0e0e0")

    return "\n".join(lines)


def sessions_to_mermaid_batch(
    sessions: list[dict],
    shadow_index: dict[str, dict],
    delta_index: dict[str, dict],
) -> str:
    """Generate markdown with Mermaid diagrams + summary/metrics for all sessions."""
    parts: list[str] = []

    # Batch-level metrics header
    grade_counts: Counter = Counter()
    diff_counts: Counter = Counter()
    resolution_counts: Counter = Counter()
    composites = []
    for s in sessions:
        gd = s.get("grade", {}) or {}
        grade_counts[gd.get("grade", "?")] += 1
        sd = s.get("seed_question", {})
        diff_counts[sd.get("difficulty", "?")] += 1
        resolution_counts[s.get("resolution", "?")] += 1
        composites.append(float(gd.get("composite", 0) or 0))

    avg_comp = sum(composites) / len(composites) if composites else 0
    pass_count = sum(grade_counts.get(g, 0) for g in ("A+", "A", "B"))
    pass_rate = pass_count / len(sessions) if sessions else 0

    parts.append("# Conversation Flow Report")
    parts.append("")
    parts.append(f"**{len(sessions)} sessions** | Pass rate: {pass_rate:.0%} | Avg composite: {avg_comp:.0%}")
    parts.append("")
    grade_str = " | ".join(f"{g}: {grade_counts.get(g, 0)}" for g in ("A+", "A", "B", "C", "F"))
    parts.append(f"**Grades:** {grade_str}")
    diff_str = " | ".join(f"{d}: {diff_counts.get(d, 0)}" for d in ("simple", "medium", "complex", "ambiguous", "flawed"))
    parts.append(f"**Difficulty:** {diff_str}")
    res_str = " | ".join(f"{r}: {resolution_counts.get(r, 0)}" for r in sorted(resolution_counts))
    parts.append(f"**Resolution:** {res_str}")
    parts.append("")
    parts.append("---")
    parts.append("")

    for i, s in enumerate(sessions, 1):
        sid = s.get("session_id", "unknown")
        persona = s.get("persona", "?")
        seed = s.get("seed_question", {})
        diff = seed.get("difficulty", "?")
        grade_data = s.get("grade", {}) or {}
        grade = grade_data.get("grade", "?")
        shadow = shadow_index.get(sid)
        delta = delta_index.get(sid)

        parts.append(f"## Session {i}: {persona} ({diff}) — Grade {grade}")
        parts.append(f"*ID: {sid}*")
        parts.append("")
        # Summary block with metrics
        parts.append(_session_summary(s, shadow_entry=shadow, delta_entry=delta))
        parts.append("")
        parts.append("```mermaid")
        parts.append(session_to_mermaid(s, shadow_entry=shadow, delta_entry=delta))
        parts.append("```")
        parts.append("")
        parts.append("---")
        parts.append("")

    return "\n".join(parts)
