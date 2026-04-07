"""Rendering functions for review-conversation.

Rich terminal rendering, markdown export, and plain-text brief output.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from models import composite_bar, grade_style

console = Console()


# ---------------------------------------------------------------------------
# Rich rendering: single turn
# ---------------------------------------------------------------------------


def render_turn(turn: dict, show_metadata: bool = True) -> None:
    """Render a single conversation turn with Rich."""
    num = turn.get("turn_number", "?")
    speaker = turn.get("speaker", "unknown")
    role = turn.get("role", "")
    action = turn.get("action", "")
    content = turn.get("content", "")
    meta = turn.get("metadata", {})
    ts = turn.get("timestamp", "")

    if role == "persona":
        speaker_style = "bold cyan"
        border_style = "cyan"
    else:
        speaker_style = "bold magenta"
        border_style = "magenta"

    action_colors = {
        "QUERY": "blue",
        "CLARIFY": "yellow",
        "FOLLOW_UP": "green",
        "NO_MATCH": "red",
        "ANSWER": "white",
    }
    action_style = action_colors.get(action, "white")

    header = Text()
    header.append(f"Turn {num}", style="bold")
    header.append(" | ", style="dim")
    header.append(speaker, style=speaker_style)
    header.append(" | ", style="dim")
    header.append(action, style=f"bold {action_style}")
    if ts:
        try:
            dt = datetime.fromisoformat(ts)
            header.append(f"  ({dt.strftime('%H:%M:%S')})", style="dim")
        except ValueError:
            pass

    console.print(Panel(content, title=header, border_style=border_style, padding=(0, 1)))

    if not show_metadata or not meta:
        return

    sg = meta.get("self_grade_final")
    if sg:
        grade = str(sg.get("grade", "?"))
        comp = float(sg.get("composite", 0) or 0)
        _raw_iters = sg.get("iteration", 0)
        iters = int(_raw_iters) if isinstance(_raw_iters, (int, float)) else 0
        _raw_qra = sg.get("qra_count", 0)
        qra_count = int(_raw_qra) if isinstance(_raw_qra, (int, float)) else 0
        issues = sg.get("issues", [])
        rationale = sg.get("rationale", "")

        grade_text = Text()
        grade_text.append("  Self-Grade: ", style="dim")
        grade_text.append(grade, style=grade_style(grade))
        grade_text.append(f" ({comp:.2f})", style="dim")
        grade_text.append(f"  iterations={iters + 1}", style="dim")
        grade_text.append(f"  QRAs={qra_count}", style="dim")
        if issues:
            grade_text.append(f"  issues={issues}", style="dim red")
        console.print(grade_text)
        if rationale:
            console.print(f"  Rationale: {rationale[:200]}", style="dim italic")

    evaluation = meta.get("evaluation")
    reasoning = meta.get("reasoning")
    if evaluation:
        eval_colors = {
            "satisfactory": "green",
            "incomplete": "yellow",
            "wrong": "red",
            "flaw_caught": "bold green",
            "flaw_missed": "bold red",
        }
        eval_style = eval_colors.get(evaluation, "white")
        eval_text = Text()
        eval_text.append("  Evaluation: ", style="dim")
        eval_text.append(evaluation.upper(), style=eval_style)
        console.print(eval_text)
        if reasoning:
            console.print(f"  Reasoning: {reasoning[:300]}", style="dim italic")

    qra_count = meta.get("qra_count")
    if qra_count is not None and qra_count > 0:
        console.print(f"  QRAs cited: {qra_count}", style="dim")

    console.print()


# ---------------------------------------------------------------------------
# Rich rendering: session grade
# ---------------------------------------------------------------------------


def render_session_grade(session: dict) -> None:
    """Render the session-level grade with dimension breakdown."""
    grade_data = session.get("grade")
    if not grade_data:
        console.print("[dim]No session grade available[/dim]")
        return

    grade = grade_data.get("grade", "?")
    composite_val = grade_data.get("composite", 0)
    scores = grade_data.get("scores", {})
    rationale = grade_data.get("rationale", "")
    tier = grade_data.get("tier", "?")
    source = grade_data.get("source", "?")
    citations_verified = grade_data.get("qra_citations_verified", 0)
    citations_total = grade_data.get("qra_citations_total", 0)

    header = Text()
    header.append("Session Grade: ", style="bold")
    header.append(grade, style=grade_style(grade))
    header.append(f"  composite={composite_val:.2f}", style="dim")
    header.append(f"  tier={tier}", style="dim")
    header.append(f"  source={source}", style="dim")
    console.print(header)

    if citations_total > 0:
        ratio = citations_verified / citations_total
        cit_style = "green" if ratio >= 0.7 else "yellow" if ratio >= 0.4 else "red"
        console.print(
            f"  QRA Citations: {citations_verified}/{citations_total} verified",
            style=cit_style,
        )

    if scores:
        table = Table(show_header=True, header_style="bold", padding=(0, 1))
        table.add_column("Dimension", style="cyan")
        table.add_column("Score", justify="right")
        table.add_column("Bar", min_width=22)

        for dim, score in sorted(scores.items()):
            score_val = float(score) if score else 0.0
            bar_style = "green" if score_val >= 0.8 else "yellow" if score_val >= 0.6 else "red"
            table.add_row(
                dim,
                f"{score_val:.2f}",
                Text(composite_bar(score_val), style=bar_style),
            )
        console.print(table)

    # Lean4 reasoning errors (if available)
    lean4_taxonomy = grade_data.get("lean4_error_taxonomy", {})
    if lean4_taxonomy:
        console.print()
        console.print("  [bold dim]Lean4 Reasoning Errors:[/bold dim]")
        for error_type, count in sorted(lean4_taxonomy.items(), key=lambda x: -x[1]):
            desc = {
                "fact_hallucination": "fabricated facts",
                "invalid_deduction": "flawed logic",
                "insufficient_premise": "missing premises",
                "semantic_misinterpretation": "confused causality",
                "information_omission": "ignored evidence",
                "rule_misapplication": "wrong rule applied",
            }.get(error_type, error_type)
            console.print(f"    {error_type}: {count} ({desc})", style="red")

    if rationale:
        console.print(f"\n  Rationale: {rationale[:500]}", style="dim italic")

    reasoning_sound = grade_data.get("reasoning_sound")
    taxonomy_correct = grade_data.get("taxonomy_correct")
    if reasoning_sound is not None:
        flag = "yes" if reasoning_sound else "NO"
        console.print(f"  Reasoning sound: {flag}", style="dim")
    if taxonomy_correct is not None:
        flag = "yes" if taxonomy_correct else "NO"
        console.print(f"  Taxonomy correct: {flag}", style="dim")


# ---------------------------------------------------------------------------
# Rich rendering: teacher comparison
# ---------------------------------------------------------------------------


def render_teacher_comparison(
    session: dict, shadow_entry: Optional[dict], delta_entry: Optional[dict]
) -> None:
    """Render student-vs-teacher comparison if shadow data exists."""
    if not shadow_entry:
        console.print("[dim]No teacher grade available for this session[/dim]")
        return

    console.print()
    console.print("[bold]Student vs Teacher Comparison[/bold]")

    table = Table(show_header=True, header_style="bold", padding=(0, 1))
    table.add_column("", style="bold")
    table.add_column("Student (Self-Grade)", justify="center")
    table.add_column("Teacher (External)", justify="center")

    local_grade = shadow_entry.get("local_grade", "?")
    teacher_grade = shadow_entry.get("teacher_grade", "?")
    local_conf = shadow_entry.get("local_confidence", 0)
    teacher_conf = shadow_entry.get("teacher_confidence", 0)
    agreed = shadow_entry.get("agreed", False)

    table.add_row(
        "Grade",
        Text(local_grade, style=grade_style(local_grade)),
        Text(teacher_grade, style=grade_style(teacher_grade)),
    )
    table.add_row("Confidence", f"{local_conf:.2f}", f"{teacher_conf:.2f}")

    student_model = shadow_entry.get("student_model", "?")
    teacher_model = shadow_entry.get("teacher_model", "?")
    table.add_row("Model", student_model, teacher_model)

    console.print(table)

    if agreed:
        console.print("  Agreement: [bold green]AGREE[/bold green]")
    else:
        console.print("  Agreement: [bold red]DISAGREE[/bold red]")

    qra_count = shadow_entry.get("qra_citation_count", 0)
    qra_verified = shadow_entry.get("qra_citations_verified", 0)
    qra_grounding = shadow_entry.get("qra_grounding_avg", 0)
    if qra_count > 0 or qra_verified > 0:
        console.print(
            f"  Citations: count={qra_count} verified={qra_verified} "
            f"grounding_avg={qra_grounding:.2f}",
            style="dim",
        )

    if delta_entry:
        first = delta_entry.get("first_composite", 0)
        final = delta_entry.get("final_composite", 0)
        delta = delta_entry.get("delta", 0)
        outer = delta_entry.get("outer_rounds", 0)
        inner = delta_entry.get("inner_iterations", 0)
        persona_eval = delta_entry.get("persona_evaluation", "?")
        target_met = delta_entry.get("target_met", False)

        console.print()
        console.print("[bold]Improvement Delta[/bold]")
        console.print(f"  First: {first:.2f} -> Final: {final:.2f} (delta={delta:+.2f})")
        console.print(f"  Rounds: outer={outer} inner={inner}")
        console.print(f"  Persona eval: {persona_eval}")
        met_style = "green" if target_met else "red"
        console.print(f"  Target met: {target_met}", style=met_style)


# ---------------------------------------------------------------------------
# Rich rendering: full session
# ---------------------------------------------------------------------------


def render_session(
    session: dict,
    shadow_entry: Optional[dict] = None,
    delta_entry: Optional[dict] = None,
    show_metadata: bool = True,
    show_teacher: bool = True,
) -> None:
    """Render a complete session with all turns and grades."""
    sid = session.get("session_id", "unknown")
    persona = session.get("persona", "unknown")
    status = session.get("status", "?")
    resolution = session.get("resolution", "?")
    adversarial = session.get("adversarial", False)
    seed = session.get("seed_question", {})

    console.rule(f"[bold]Session: {sid}[/bold]")
    console.print()

    meta_text = Text()
    meta_text.append("Persona: ", style="dim")
    meta_text.append(persona, style="bold cyan")
    meta_text.append("  Status: ", style="dim")
    meta_text.append(status, style="bold")
    meta_text.append("  Resolution: ", style="dim")
    meta_text.append(resolution, style="bold")
    if adversarial:
        meta_text.append("  [ADVERSARIAL]", style="bold red")
    console.print(meta_text)

    if seed:
        diff = seed.get("difficulty", "?")
        action = seed.get("expected_action", "?")
        target = seed.get("target_control", "?")
        notes = seed.get("grading_notes", "")

        seed_text = Text()
        seed_text.append("Seed: ", style="dim")
        seed_text.append(f"difficulty={diff}", style="dim")
        seed_text.append(f"  action={action}", style="dim")
        seed_text.append(f"  target={target}", style="bold")
        if notes:
            seed_text.append(f"  notes=\"{notes}\"", style="dim italic")
        console.print(seed_text)

    console.print()

    for turn in session.get("turns", []):
        render_turn(turn, show_metadata=show_metadata)

    console.print()
    render_session_grade(session)

    if show_teacher:
        render_teacher_comparison(session, shadow_entry, delta_entry)

    console.print()


# ---------------------------------------------------------------------------
# Rich rendering: summary table
# ---------------------------------------------------------------------------


_AUDIT_STYLES = {
    "CLEAN": "green",
    "MENDACIOUS": "bold red",
    "LAZY": "yellow",
    "REGRESSED": "dark_orange",
}


def render_summary_table(
    sessions: list[dict],
    shadow_index: dict[str, dict],
    delta_index: dict[str, dict],
    audit_index: dict[str, dict] | None = None,
) -> None:
    """Render a summary table of all sessions."""
    has_audit = bool(audit_index)
    table = Table(
        title="Session Summary",
        show_header=True,
        header_style="bold",
        padding=(0, 1),
    )
    table.add_column("#", justify="right", style="dim")
    table.add_column("Session ID", max_width=30)
    table.add_column("Persona", style="cyan")
    table.add_column("Difficulty")
    table.add_column("Target")
    table.add_column("Turns", justify="right")
    table.add_column("Self", justify="center")
    table.add_column("Teacher", justify="center")
    table.add_column("Agree?", justify="center")
    if has_audit:
        table.add_column("Audit", justify="center")
    table.add_column("Resolution")

    for i, s in enumerate(sessions, 1):
        sid = s.get("session_id", "?")
        persona = s.get("persona", "?")
        seed = s.get("seed_question", {})
        diff = seed.get("difficulty", "?")
        target = seed.get("target_control", "?")
        turns = len(s.get("turns", []))

        grade_data = s.get("grade", {}) or {}
        self_grade = grade_data.get("grade", "-")
        self_style = grade_style(self_grade)

        shadow = shadow_index.get(sid)
        teacher_grade = "-"
        agreed_text = Text("-", style="dim")
        if shadow:
            teacher_grade = shadow.get("teacher_grade", "-")
            agreed = shadow.get("agreed", False)
            agreed_text = (
                Text("YES", style="bold green") if agreed
                else Text("NO", style="bold red")
            )

        resolution = s.get("resolution", "?")

        row: list[Any] = [
            str(i),
            sid[:28],
            persona,
            diff,
            target,
            str(turns),
            Text(self_grade, style=self_style),
            Text(teacher_grade, style=grade_style(teacher_grade)),
            agreed_text,
        ]

        if has_audit:
            audit_entry = audit_index.get(sid, {})
            audit_verdict = audit_entry.get("verdict", "-")
            audit_style = _AUDIT_STYLES.get(audit_verdict, "dim")
            reg_count = len(audit_entry.get("regressions", []))
            label = audit_verdict + (f"({reg_count})" if reg_count else "")
            row.append(Text(label, style=audit_style))

        row.append(resolution)
        table.add_row(*row)

    console.print(table)

    total = 0
    agreed_count = 0
    for s in sessions:
        sid = s.get("session_id", "")
        shadow = shadow_index.get(sid)
        if shadow:
            total += 1
            if shadow.get("agreed", False):
                agreed_count += 1

    if total > 0:
        rate = agreed_count / total
        rate_style = "green" if rate >= 0.6 else "yellow" if rate >= 0.4 else "red"
        console.print(
            f"\nAgreement Rate: {agreed_count}/{total} "
            f"({rate:.1%})",
            style=rate_style,
        )


# ---------------------------------------------------------------------------
# Markdown export
# ---------------------------------------------------------------------------


def session_to_markdown(
    session: dict,
    shadow_entry: Optional[dict] = None,
    delta_entry: Optional[dict] = None,
) -> str:
    """Convert a session to markdown for human annotation."""
    lines: list[str] = []
    sid = session.get("session_id", "unknown")
    persona = session.get("persona", "unknown")
    seed = session.get("seed_question", {})

    lines.append(f"# Session: {sid}")
    lines.append("")
    lines.append(f"**Persona:** {persona}")
    lines.append(f"**Difficulty:** {seed.get('difficulty', '?')}")
    lines.append(f"**Target Control:** {seed.get('target_control', '?')}")
    lines.append(f"**Expected Action:** {seed.get('expected_action', '?')}")
    lines.append(f"**Resolution:** {session.get('resolution', '?')}")
    if seed.get("grading_notes"):
        lines.append(f"**Notes:** {seed['grading_notes']}")
    lines.append("")
    lines.append("---")
    lines.append("")

    for turn in session.get("turns", []):
        speaker = turn.get("speaker", "?")
        action = turn.get("action", "?")
        content = turn.get("content", "")
        meta = turn.get("metadata", {})

        lines.append(f"### Turn {turn.get('turn_number', '?')}: {speaker} [{action}]")
        lines.append("")
        lines.append(f"> {content}")
        lines.append("")

        sg = meta.get("self_grade_final")
        if sg:
            lines.append(
                f"*Self-grade: {sg.get('grade', '?')} "
                f"({sg.get('composite', 0):.2f}) "
                f"iterations={sg.get('iteration', 0) + 1} "
                f"QRAs={sg.get('qra_count', 0)}*"
            )
            issues = sg.get("issues", [])
            if issues:
                lines.append(f"*Issues: {', '.join(issues)}*")
            lines.append("")

        evaluation = meta.get("evaluation")
        if evaluation:
            lines.append(f"**Persona Evaluation:** {evaluation.upper()}")
            reasoning = meta.get("reasoning", "")
            if reasoning:
                lines.append(f"*{reasoning}*")
            lines.append("")

    grade_data = session.get("grade", {}) or {}
    if grade_data:
        lines.append("---")
        lines.append("")
        lines.append("## Session Grade")
        lines.append("")
        lines.append(
            f"**Grade:** {grade_data.get('grade', '?')} "
            f"(composite={grade_data.get('composite', 0):.2f})"
        )
        scores = grade_data.get("scores", {})
        if scores:
            lines.append("")
            lines.append("| Dimension | Score |")
            lines.append("|-----------|-------|")
            for dim, score in sorted(scores.items()):
                lines.append(f"| {dim} | {float(score):.2f} |")
        lines.append("")

    if shadow_entry:
        lines.append("## Student vs Teacher")
        lines.append("")
        lines.append("| | Student | Teacher |")
        lines.append("|---|---------|---------|")
        lines.append(
            f"| Grade | {shadow_entry.get('local_grade', '?')} "
            f"| {shadow_entry.get('teacher_grade', '?')} |"
        )
        agreed = shadow_entry.get("agreed", False)
        lines.append(f"| Agreement | {'AGREE' if agreed else 'DISAGREE'} | |")
        lines.append("")

    if delta_entry:
        lines.append("## Improvement Delta")
        lines.append("")
        first = delta_entry.get("first_composite", 0)
        final = delta_entry.get("final_composite", 0)
        delta = delta_entry.get("delta", 0)
        lines.append(f"- First: {first:.2f} -> Final: {final:.2f} (delta={delta:+.2f})")
        lines.append(f"- Persona eval: {delta_entry.get('persona_evaluation', '?')}")
        lines.append(f"- Target met: {delta_entry.get('target_met', False)}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Brief: plain markdown (no Rich)
# ---------------------------------------------------------------------------


def brief_summary_table(
    sessions: list[dict],
    shadow_index: dict[str, dict],
) -> str:
    """Generate a plain markdown summary table (no Rich, pasteable in chat)."""
    lines: list[str] = []
    lines.append("| # | Persona | Difficulty | Target | Self | Teacher | Agree | Resolution |")
    lines.append("|---|---------|------------|--------|------|---------|-------|------------|")

    for i, s in enumerate(sessions, 1):
        persona = s.get("persona", "?")
        seed = s.get("seed_question", {})
        diff = seed.get("difficulty", "?")
        target = seed.get("target_control", "?")
        grade_data = s.get("grade", {}) or {}
        self_grade = grade_data.get("grade", "-")
        sid = s.get("session_id", "")
        shadow = shadow_index.get(sid)
        teacher_grade = shadow.get("teacher_grade", "-") if shadow else "-"
        agreed = shadow.get("agreed", False) if shadow else None
        agree_str = "YES" if agreed else ("NO" if agreed is not None else "-")
        resolution = s.get("resolution", "?")
        lines.append(
            f"| {i} | {persona} | {diff} | {target} | {self_grade} | "
            f"{teacher_grade} | {agree_str} | {resolution} |"
        )

    total = sum(1 for s in sessions if s.get("session_id", "") in shadow_index)
    agreed_count = sum(
        1 for s in sessions
        if shadow_index.get(s.get("session_id", ""), {}).get("agreed", False)
    )
    if total > 0:
        lines.append(f"\n**Agreement Rate:** {agreed_count}/{total} ({agreed_count/total:.1%})")

    return "\n".join(lines)


def brief_session(
    session: dict,
    shadow_entry: Optional[dict] = None,
    delta_entry: Optional[dict] = None,
) -> str:
    """Generate plain markdown for a single session (pasteable in chat)."""
    lines: list[str] = []
    sid = session.get("session_id", "unknown")
    persona = session.get("persona", "unknown")
    seed = session.get("seed_question", {})

    lines.append(f"### Session: {sid}")
    lines.append(f"**Persona:** {persona} | **Difficulty:** {seed.get('difficulty', '?')} "
                 f"| **Target:** {seed.get('target_control', '?')} "
                 f"| **Resolution:** {session.get('resolution', '?')}")
    lines.append("")

    for turn in session.get("turns", []):
        speaker = turn.get("speaker", "?")
        action = turn.get("action", "?")
        content = turn.get("content", "")
        meta = turn.get("metadata", {})
        truncated = content[:200] + "..." if len(content) > 200 else content
        lines.append(f"**Turn {turn.get('turn_number', '?')}** ({speaker} [{action}]): {truncated}")

        sg = meta.get("self_grade_final")
        if sg:
            _iter = sg.get('iteration', 0)
            _iter_str = str(int(_iter) + 1) if isinstance(_iter, (int, float)) else str(_iter)
            _qra = sg.get('qra_count', 0)
            _qra_str = str(int(_qra)) if isinstance(_qra, (int, float)) else str(_qra)
            lines.append(f"  > Self-grade: {sg.get('grade', '?')} ({float(sg.get('composite', 0) or 0):.2f}) "
                         f"iters={_iter_str} QRAs={_qra_str}")

        evaluation = meta.get("evaluation")
        if evaluation:
            lines.append(f"  > Persona eval: **{evaluation.upper()}**")
        lines.append("")

    grade_data = session.get("grade", {}) or {}
    if grade_data:
        scores = grade_data.get("scores", {})
        dims = " | ".join(f"{d}: {float(v):.2f}" for d, v in sorted(scores.items()))
        lines.append(f"**Grade:** {grade_data.get('grade', '?')} "
                     f"(composite={grade_data.get('composite', 0):.2f})")
        if dims:
            lines.append(f"Dimensions: {dims}")

    if shadow_entry:
        local_g = shadow_entry.get("local_grade", "?")
        teacher_g = shadow_entry.get("teacher_grade", "?")
        agreed = shadow_entry.get("agreed", False)
        lines.append(f"\n**Student:** {local_g} | **Teacher:** {teacher_g} "
                     f"| **Agreement:** {'AGREE' if agreed else 'DISAGREE'}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Data export: JSON for /create-figure
# ---------------------------------------------------------------------------


def build_radar_json(sessions: list[dict]) -> dict:
    """Build radar chart JSON for /create-figure radar command."""
    series: dict[str, dict[str, float]] = {}
    for i, s in enumerate(sessions, 1):
        grade_data = s.get("grade", {}) or {}
        scores = grade_data.get("scores", {})
        if not scores:
            continue
        label = f"#{i} {s.get('persona', '?')}"
        series[label] = {dim: float(val) for dim, val in sorted(scores.items())}
    return {"series": series}


def build_heatmap_json(sessions: list[dict]) -> dict:
    """Build heatmap JSON for /create-figure heatmap command."""
    counts: dict[str, Counter] = {}
    for s in sessions:
        seed = s.get("seed_question", {})
        diff = seed.get("difficulty", "unknown")
        grade_data = s.get("grade", {}) or {}
        grade = grade_data.get("grade", "?")
        if diff not in counts:
            counts[diff] = Counter()
        counts[diff][grade] += 1
    return {diff: dict(gc) for diff, gc in sorted(counts.items())}


def build_metrics_json(
    sessions: list[dict], shadow_index: dict[str, dict]
) -> dict:
    """Build metrics JSON for /create-figure metrics --type bar."""
    total = len(sessions)
    grade_counts: dict[str, int] = {}
    resolution_counts: dict[str, int] = {}
    agreed_count = 0
    disagreed_count = 0

    for s in sessions:
        grade_data = s.get("grade", {}) or {}
        g = grade_data.get("grade", "?")
        grade_counts[g] = grade_counts.get(g, 0) + 1

        res = s.get("resolution", "?")
        resolution_counts[res] = resolution_counts.get(res, 0) + 1

        sid = s.get("session_id", "")
        shadow = shadow_index.get(sid)
        if shadow:
            if shadow.get("agreed", False):
                agreed_count += 1
            else:
                disagreed_count += 1

    return {
        "grade_distribution": {"metrics": grade_counts},
        "resolution_distribution": {"metrics": resolution_counts},
        "agreement": {
            "metrics": {
                "agreed": agreed_count,
                "disagreed": disagreed_count,
                "no_teacher": total - agreed_count - disagreed_count,
            }
        },
    }
