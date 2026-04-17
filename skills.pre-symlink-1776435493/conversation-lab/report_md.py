"""Markdown report generator for conversation-lab.

Produces human-readable conversation flow reports matching the format at
/tmp/conversation_flows_*.md — full transcripts with per-session metrics
and actionable next steps.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime


def _eval_label(evaluation: str) -> str:
    """Map evaluation to short label."""
    return {
        "satisfactory": "PASS",
        "flaw_caught": "CAUGHT",
        "flaw_missed": "MISSED",
        "incomplete": "WARN",
        "wrong": "FAIL",
    }.get(evaluation, evaluation.upper())


def _pct(value: float) -> str:
    return f"{round(value * 100)}%"


def build_report_md(sessions: list[dict], diagnosis: dict) -> str:
    """Build full markdown report from sessions and their diagnosis.

    Mirrors the format of /tmp/conversation_flows_feb26.md:
    - Summary header with counts
    - Summary table (all sessions)
    - Per-session detail with full conversation transcripts
    - Per-session next steps
    """
    lines: list[str] = []
    s = diagnosis["summary"]
    today = datetime.now().strftime("%b %d, %Y")

    # --- Header ---
    lines.append(f"# SPARTA Conversation Flow Report — {today}\n")
    lines.append(
        f"**{s['total']} sessions** | "
        f"PASS: {s['pass']} ({_pct(s['pass']/s['total'] if s['total'] else 0)}) | "
        f"WARN: {s['warn']} ({_pct(s['warn']/s['total'] if s['total'] else 0)}) | "
        f"FAIL: {s['fail']} ({_pct(s['fail']/s['total'] if s['total'] else 0)}) | "
        f"Avg composite: {_pct(s['avg_composite'])}"
    )
    lines.append("")

    # Grades
    grades = s.get("grades", {})
    grades_str = " | ".join(f"{k}: {v}" for k, v in sorted(grades.items()))
    lines.append(f"**Grades:** {grades_str}")

    # Difficulty distribution
    diff_counter: Counter = Counter()
    for sess in sessions:
        diff_counter[sess.get("seed_question", {}).get("difficulty", "medium")] += 1
    diff_str = " | ".join(f"{k}: {v}" for k, v in sorted(diff_counter.items()))
    lines.append(f"**Difficulty:** {diff_str}")

    # Resolution distribution
    res = s.get("resolutions", {})
    res_str = " | ".join(f"{k}: {v}" for k, v in sorted(res.items()))
    lines.append(f"**Resolution:** {res_str}")
    lines.append("")

    # --- Summary table ---
    lines.append("## Summary Table\n")
    lines.append(
        "| # | Persona | Difficulty | Target | Grade | Composite | Resolution | Turns | Evals | QRAs |"
    )
    lines.append(
        "|---|---------|------------|--------|-------|-----------|------------|-------|-------|------|"
    )

    session_reports = diagnosis.get("sessions", [])
    for i, sr in enumerate(session_reports, 1):
        evals_str = ",".join(_eval_label(e) for e in sr.get("persona_evals", []))
        lines.append(
            f"| {i} | {sr['persona']} | {sr['difficulty']} | "
            f"{sr['target_control'] or '—'} | {sr['grade']} | "
            f"{_pct(sr['composite'])} | {sr['resolution']} | "
            f"{sr['turns']} | {evals_str} | {sr['qras_cited']} |"
        )

    lines.append("")
    lines.append("---\n")

    # --- Per-session detail ---
    for i, sr in enumerate(session_reports, 1):
        sess = sessions[i - 1] if i - 1 < len(sessions) else {}
        lines.append(
            f"## Session {i}: {sr['persona']} ({sr['difficulty']}) "
            f"— Grade {sr['grade']} ({_pct(sr['composite'])})"
        )
        lines.append(f"*ID: {sr['session_id']}*\n")

        lines.append(
            f"**Target:** {sr['target_control'] or '—'} | "
            f"**Difficulty:** {sr['difficulty']} | "
            f"**Resolution:** {sr['resolution']} | "
            f"**Turns:** {sr['turns']}"
        )

        # Dimensions (from grade rubric)
        grade_info = sess.get("grade", {})
        if isinstance(grade_info, dict):
            dims = grade_info.get("dimensions", {})
            if dims:
                dim_str = " | ".join(
                    f"{k}: {_pct(v) if isinstance(v, float) else v}"
                    for k, v in sorted(dims.items())
                )
                lines.append(f"**Dimensions:** {dim_str}")

        # Persona evaluations
        evals_str = ", ".join(sr.get("persona_evals", []))
        lines.append(f"**Persona evaluations:** {evals_str}")

        # Improvement delta
        delta = sr.get("delta", {})
        if delta.get("first") != delta.get("final"):
            change = delta.get("change", 0)
            sign = "+" if change >= 0 else ""
            lines.append(
                f"**Improvement:** {_pct(delta['first'])} → "
                f"{_pct(delta['final'])} ({sign}{_pct(change)})"
            )

        # Grading rationale
        rationale = ""
        if isinstance(grade_info, dict):
            rationale = grade_info.get("rationale", "") or grade_info.get("reasoning", "")
        if rationale:
            lines.append(f"**Grading rationale:** {rationale}")

        lines.append("")

        # Conversation transcript
        turns = sess.get("turns", [])
        if turns:
            lines.append("### Conversation\n")
            for turn in turns:
                if not isinstance(turn, dict):
                    continue
                speaker = turn.get("speaker", "Unknown")
                action = turn.get("action", "")
                content = turn.get("content", "")
                meta = turn.get("metadata", {}) if isinstance(turn.get("metadata"), dict) else {}

                role = turn.get("role", "")
                if role == "persona":
                    outer = meta.get("outer_round", "")
                    round_str = f" (Round {outer})" if outer else ""
                    if action in ("QUERY", "FOLLOW_UP"):
                        lines.append(f"**{speaker}** [{action}]{round_str}\n")
                        lines.append(f"> {content}\n")
                    else:
                        # Evaluation turn
                        lines.append(f"**{speaker}** [{action}]{round_str}\n")
                    evaluation = meta.get("evaluation", "")
                    reasoning = meta.get("reasoning", "")
                    if evaluation:
                        lines.append(f"*Evaluation: **{_eval_label(evaluation)}***")
                    if reasoning:
                        lines.append(f"*Reasoning: {reasoning}*\n")
                elif role == "system":
                    grade_meta = meta.get("self_grade_final", {})
                    grade_letter = grade_meta.get("grade", "") if isinstance(grade_meta, dict) else ""
                    composite_val = grade_meta.get("composite", 0) if isinstance(grade_meta, dict) else 0
                    qra_count = meta.get("qra_count", 0)
                    iters = meta.get("self_grade_iterations", 0)
                    outer = meta.get("outer_round", "")

                    info_parts = []
                    if outer:
                        info_parts.append(f"Round {outer}")
                    if grade_letter:
                        info_parts.append(f"Self-grade: {grade_letter} {_pct(composite_val)}")
                    info_parts.append(f"QRAs: {qra_count}")
                    if iters:
                        info_parts.append(f"Iterations: {iters}")

                    lines.append(
                        f"**SPARTA** [{action}] ({' | '.join(info_parts)})\n"
                    )
                    lines.append(f"{content}\n")

        # Metrics summary
        lines.append("### Metrics\n")
        query_turns = [t for t in turns if isinstance(t, dict) and t.get("action") in ("QUERY",)]
        followup_turns = [t for t in turns if isinstance(t, dict) and t.get("action") == "FOLLOW_UP"]
        system_turns = [t for t in turns if isinstance(t, dict) and t.get("role") == "system"]
        clarify_turns = [t for t in system_turns if t.get("action") == "CLARIFY"]
        answer_turns = [t for t in system_turns if t.get("action") not in ("CLARIFY", "INTERVIEW")]

        lines.append(f"- Questions asked: {len(query_turns)} initial + {len(followup_turns)} follow-ups")
        lines.append(f"- SPARTA responses: {len(clarify_turns)} clarifications, {len(answer_turns)} answers")
        lines.append(f"- Total QRAs cited: {sr['qras_cited']}")
        lines.append(f"- Topics: {sr['target_control'] or '—'} ({sr['difficulty']})")
        eval_counts = Counter(sr.get("persona_evals", []))
        lines.append(f"- Persona verdict: {dict(eval_counts)}")
        lines.append("")

        # Next steps (actionable)
        issues = sr.get("issues", [])
        if issues:
            lines.append("### Next Steps\n")
            issue_actions = {
                "zero_qra_citations": "**ZERO CITATIONS**: No QRAs cited. Check ArangoSearch view, embedding service, and recall pipeline.",
                "over_clarification": f"**OVER-CLARIFY**: {len(clarify_turns)} clarification rounds on a {sr['difficulty']} question. Tune ambiguity classifier or add control-ID bypass.",
                "self_grade_regression": f"**REGRESSION**: Score degraded ({_pct(delta.get('first', 0))} → {_pct(delta.get('final', 0))}). Self-grading loop may be over-correcting.",
                "wrong_answer": "**WRONG ANSWER**: Persona flagged incorrect information. Verify QRA corpus accuracy for this control.",
                "coverage_gap": f"**COVERAGE GAP**: No coverage for {sr['target_control']}. Run gap-filler or check if control exists in corpus.",
            }
            for issue in issues:
                if issue in issue_actions:
                    lines.append(f"- {issue_actions[issue]}")
            if sr.get("rerun_eligible"):
                lines.append(f"- **RERUN CANDIDATE**: {sr.get('rerun_reason', 'eligible for convergence')}")
            lines.append("")

        lines.append("---\n")

    # --- Systemic issues summary at end ---
    systemic = diagnosis.get("systemic_issues", [])
    if systemic:
        lines.append("## Systemic Issues\n")
        for si in systemic:
            lines.append(
                f"- **{si['severity'].upper()}** {si['issue']} (×{si['count']}) — {si['fix']}"
            )
            if "controls" in si:
                lines.append(f"  Controls: {', '.join(si['controls'])}")
        lines.append("")

    # Convergence state if available
    lines.append("## Turn Statistics\n")
    ts = diagnosis.get("turn_stats", {})
    lines.append(f"- Avg turns (satisfied): {ts.get('avg_turns_satisfied', '—')}")
    lines.append(f"- Avg turns (unsatisfied): {ts.get('avg_turns_unsatisfied', '—')}")
    lines.append(f"- Optimal estimate: {ts.get('optimal_turns_estimate', '—')}")
    lines.append(f"- Rerun candidates: {len(diagnosis.get('rerun_candidates', []))}")
    lines.append("")

    return "\n".join(lines)
