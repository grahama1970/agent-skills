"""Embry-themed Textual widgets for QRA review.

Widgets:
  StatsBar — Review progress counter
  QRACard — Left pane: question, answer, metadata
  AssessmentDetail — Assessment breakdown with [PASS]/[WARN]/[FAIL] labels

Design: P2 compliance — text labels always accompany color.
"""
from __future__ import annotations

from textual.widgets import Static


class StatsBar(Static):
    """Top bar showing review progress."""

    def update_stats(self, idx: int, total: int, stats: dict) -> None:
        a = stats.get("accepted", 0)
        r = stats.get("rejected", 0)
        e = stats.get("amended", 0)
        s = stats.get("skipped", 0)
        self.update(
            f" QRA {idx}/{total}  |  \u2713{a}  \u2717{r}  \u270e{e}  \u2500{s}"
        )


class QRACard(Static):
    """Left pane: displays QRA question, answer, and metadata."""

    DEFAULT_CSS = """
    QRACard {
        background: #171717;
        border: solid #333333;
        padding: 1;
        height: auto;
        max-height: 70%;
    }
    """

    def load(self, doc: dict) -> None:
        control = doc.get("control_id", "?")
        fw = doc.get("assessment_framework", "?")
        grade = doc.get("assessment_grade", "?")
        grounding = doc.get("grounding_score") or doc.get("assessment_grounding", 0)

        # Grade color + text label (P2: never color alone)
        if grade == "WARN":
            grade_markup = f"[#eab308][WARN][/#eab308]"
        elif grade == "FAIL":
            grade_markup = f"[#ef4444][FAIL][/#ef4444]"
        else:
            grade_markup = f"[#22c55e][PASS][/#22c55e]"

        question = doc.get("question", "")
        answer = doc.get("answer", "")
        reasoning = doc.get("reasoning", "")

        lines = [
            f"{grade_markup} {control}  {fw}",
            f"Grounding: {grounding:.3f}" if isinstance(grounding, (int, float)) else f"Grounding: {grounding}",
            "",
            f"[bold]Q:[/bold] {question}",
            "",
            f"[bold]A:[/bold] {answer[:600]}{'...' if len(answer) > 600 else ''}",
        ]
        if reasoning:
            lines.extend(["", f"[dim]R: {reasoning[:300]}{'...' if len(reasoning) > 300 else ''}[/dim]"])

        self.update("\n".join(lines))


class AssessmentDetail(Static):
    """Assessment breakdown with per-check PASS/WARN/FAIL labels."""

    DEFAULT_CSS = """
    AssessmentDetail {
        background: #262626;
        border: solid #333333;
        padding: 1;
        height: auto;
    }
    """

    def load(self, doc: dict) -> None:
        lines = ["\u2500\u2500 Assessment \u2500\u2500"]

        # Grounding
        grounding = doc.get("grounding_score") or doc.get("assessment_grounding", 0)
        grade = doc.get("assessment_grade", "WARN")
        lines.append(self._check_line(
            "Grounding",
            f"{grounding:.3f}" if isinstance(grounding, (int, float)) else str(grounding),
            "FAIL" if grade == "FAIL" else ("WARN" if grounding and grounding < 0.70 else "PASS"),
        ))

        # Space terms
        terms_ok = doc.get("assessment_space_terms_ok", False)
        lines.append(self._check_line("Space terms", "", "PASS" if terms_ok else "WARN"))

        # Anchoring
        anchor_ok = doc.get("assessment_anchoring_ok", False)
        lines.append(self._check_line("Anchoring", doc.get("control_id", ""), "PASS" if anchor_ok else "WARN"))

        # Taxonomy
        tax_ok = doc.get("assessment_taxonomy_ok", False)
        lines.append(self._check_line("Taxonomy", "", "PASS" if tax_ok else "WARN"))

        # Notes
        notes = doc.get("assessment_notes", [])
        if notes:
            lines.append("")
            for note in notes[:5]:
                lines.append(f"  [dim]\u2022 {note}[/dim]")

        self.update("\n".join(lines))

    @staticmethod
    def _check_line(label: str, detail: str, status: str) -> str:
        if status == "PASS":
            tag = "[#22c55e][PASS][/#22c55e]"
        elif status == "WARN":
            tag = "[#eab308][WARN][/#eab308]"
        else:
            tag = "[#ef4444][FAIL][/#ef4444]"
        suffix = f": {detail}" if detail else ""
        return f"{tag} {label}{suffix}"
