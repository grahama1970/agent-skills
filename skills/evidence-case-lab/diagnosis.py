"""Diagnosis module for evidence case lab.

Classifies results from batch runs into actionable categories.
The human expert reads these to course-correct the agent.

Key category: "grounding_warning" — SATISFIED verdicts where the grounding
evidence contradicts the verdict. These are the ones the human checks FIRST.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class DiagnosisResult:
    """Classified results from a batch run.

    Categories (in priority order for human review):
    1. grounding_warnings — SATISFIED but grounding evidence says maybe not
    2. false_positives — expected not_satisfied, got satisfied (no grounding signal)
    3. grounding_failures — expected not_satisfied, got satisfied WITH unresolved terms
    4. false_negatives — expected satisfied, got not_satisfied/inconclusive
    5. technique_scatter — technique bridge failed
    6. correct — verdict matches expectation
    """

    # SATISFIED verdicts with grounding warnings — THE section the human reads first
    # These are NOT necessarily wrong. The human decides.
    grounding_warnings: list[dict[str, Any]] = field(default_factory=list)

    # Expected not_satisfied but got satisfied — no grounding signal to explain it
    false_positives: list[dict[str, Any]] = field(default_factory=list)

    # Expected not_satisfied, got satisfied, AND unresolved ID-like terms present
    grounding_failures: list[dict[str, Any]] = field(default_factory=list)

    # Expected satisfied but got not_satisfied/inconclusive
    false_negatives: list[dict[str, Any]] = field(default_factory=list)

    # Technique bridge failed — many unrelated techniques
    technique_scatter: list[dict[str, Any]] = field(default_factory=list)

    # Verdict matches expectation
    correct: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (len(self.grounding_warnings) + len(self.false_positives) +
                len(self.false_negatives) + len(self.grounding_failures) +
                len(self.technique_scatter) + len(self.correct))

    @property
    def error_count(self) -> int:
        """Hard errors (verdict != expected). Grounding warnings are NOT counted
        as errors — the human decides if they're actually wrong."""
        return (len(self.false_positives) + len(self.false_negatives) +
                len(self.grounding_failures) + len(self.technique_scatter))

    @property
    def needs_human_review(self) -> int:
        """Items the human should look at: grounding warnings + all errors."""
        return len(self.grounding_warnings) + self.error_count

    def summary(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "correct": len(self.correct),
            "needs_human_review": self.needs_human_review,
            "grounding_warnings": len(self.grounding_warnings),
            "errors": self.error_count,
            "false_positives": len(self.false_positives),
            "false_negatives": len(self.false_negatives),
            "grounding_failures": len(self.grounding_failures),
            "technique_scatter": len(self.technique_scatter),
            "fp_rate": (len(self.false_positives) + len(self.grounding_failures)) / max(self.total, 1),
            "fn_rate": len(self.false_negatives) / max(self.total, 1),
        }


def diagnose_results(results: list[dict[str, Any]]) -> DiagnosisResult:
    """Classify each result into categories for human review.

    Each result dict should have:
    - question: str
    - expected: "satisfied" | "not_satisfied" | "inconclusive"
    - actual_verdict: str
    - grounding_evidence: dict (optional)
    - gate_trace: list[dict]
    """
    diag = DiagnosisResult()

    for r in results:
        expected = r.get("expected", "").lower()
        actual = (r.get("actual_verdict") or r.get("actual") or "").lower()
        grounding = r.get("grounding_evidence", {})
        question = r.get("question", "?")
        qid = r.get("id", "?")

        # Extract grounding signals
        unresolved_id_like = grounding.get("unresolved_id_like", 0) if isinstance(grounding, dict) else 0
        grounding_ratio = grounding.get("ratio", 1.0) if isinstance(grounding, dict) else 1.0
        unresolved_terms = grounding.get("unresolved_terms", []) if isinstance(grounding, dict) else []
        resolved_count = grounding.get("resolved", 0) if isinstance(grounding, dict) else 0
        misspelling_count = grounding.get("misspellings", 0) if isinstance(grounding, dict) else 0
        not_in_corpus_count = grounding.get("not_in_corpus", 0) if isinstance(grounding, dict) else 0
        no_technique_bridge = grounding.get("no_technique_bridge", False) if isinstance(grounding, dict) else False

        # Human-readable signal names — read from unresolved_terms (type field)
        # AND warnings (category field) since both may carry names
        warnings = grounding.get("warnings", []) if isinstance(grounding, dict) else []

        unresolved_names = [
            t.get("term", "?") for t in unresolved_terms
            if isinstance(t, dict) and t.get("type") == "id_like"
        ] or [
            w.get("term", "?") for w in warnings
            if isinstance(w, dict) and w.get("category") == "fabricated_id"
        ]
        misspelling_names = [
            f"{t['term']}→{t.get('suggestion', '?')}" for t in unresolved_terms
            if isinstance(t, dict) and t.get("type") == "misspelling"
        ] or [
            f"{w.get('term', '?')}→{w.get('detail', '?')}" for w in warnings
            if isinstance(w, dict) and w.get("category") == "misspelling"
        ]
        not_in_corpus_names = [
            t.get("term", "?") for t in unresolved_terms
            if isinstance(t, dict) and t.get("type") == "not_in_corpus"
        ] or [
            w.get("term", "?") for w in warnings
            if isinstance(w, dict) and w.get("category") == "not_in_corpus"
        ]

        # Total grounding signal count (any type of problem)
        total_grounding_signals = unresolved_id_like + misspelling_count + not_in_corpus_count + (1 if no_technique_bridge else 0)

        entry = {
            "id": qid,
            "question": question,
            "expected": expected,
            "actual": actual,
            "grounding_evidence": grounding,
            "unresolved_names": unresolved_names,
            "misspelling_names": misspelling_names,
            "not_in_corpus_names": not_in_corpus_names,
            "no_technique_bridge": no_technique_bridge,
            "grounding_ratio": grounding_ratio,
            "resolved_count": resolved_count,
        }

        # --- Classification ---

        if expected == "inconclusive" and actual in ("not_satisfied", "inconclusive"):
            # Expected needs-clarification, got needs-clarification → correct
            diag.correct.append(entry)

        elif expected == "inconclusive" and actual == "satisfied":
            # Expected needs-clarification but system said satisfied → false positive
            # (system answered a question it shouldn't have — the term isn't in corpus)
            entry["root_cause"] = "false_positive"
            entry["detail"] = "Expected inconclusive (needs /memory clarify) but got satisfied — system guessed an answer for terms not in SPARTA"
            diag.false_positives.append(entry)

        elif expected == "not_satisfied" and actual == "satisfied":
            # False positive — the critical error. Check ALL grounding signals.
            if total_grounding_signals > 0:
                details = []
                if unresolved_id_like > 0:
                    details.append(f"{unresolved_id_like} fabricated ID(s): {', '.join(unresolved_names)}")
                if misspelling_count > 0:
                    details.append(f"{misspelling_count} misspelling(s): {', '.join(misspelling_names)}")
                if not_in_corpus_count > 0:
                    details.append(f"{not_in_corpus_count} term(s) not in corpus: {', '.join(not_in_corpus_names)}")
                if no_technique_bridge:
                    details.append("entities don't share a technique — /memory clarify needed")
                entry["root_cause"] = "grounding_failure"
                entry["detail"] = "; ".join(details)
                diag.grounding_failures.append(entry)
            else:
                entry["root_cause"] = "false_positive"
                entry["detail"] = "Expected not_satisfied but got satisfied with no grounding signal"
                diag.false_positives.append(entry)

        elif expected == "satisfied" and actual in ("not_satisfied", "inconclusive"):
            entry["root_cause"] = "false_negative"
            entry["detail"] = f"Expected satisfied but got {actual}"
            diag.false_negatives.append(entry)

        elif actual == "satisfied" and total_grounding_signals > 0:
            # SATISFIED but grounding evidence says maybe not.
            # This is the KEY category — the human decides if it's actually wrong.
            details = []
            if unresolved_id_like > 0:
                details.append(f"{unresolved_id_like} fabricated ID(s): {', '.join(unresolved_names)}")
            if misspelling_count > 0:
                details.append(f"{misspelling_count} misspelling(s): {', '.join(misspelling_names)}")
            if not_in_corpus_count > 0:
                details.append(f"{not_in_corpus_count} not in corpus: {', '.join(not_in_corpus_names)}")
            if no_technique_bridge:
                details.append("entities don't share a technique — wrong context?")
            entry["root_cause"] = "grounding_warning"
            entry["detail"] = "Verdict is SATISFIED but: " + "; ".join(details)
            diag.grounding_warnings.append(entry)

        elif actual == "satisfied" and grounding_ratio < 1.0 and resolved_count > 0:
            # SATISFIED but not all candidates resolved — weaker warning
            entry["root_cause"] = "grounding_warning"
            entry["detail"] = (f"Verdict is SATISFIED but grounding ratio is "
                               f"{grounding_ratio:.0%} (not all terms resolved)")
            diag.grounding_warnings.append(entry)

        elif expected == actual:
            diag.correct.append(entry)

        elif actual == "inconclusive" and expected == "not_satisfied":
            # Inconclusive for adversarial is acceptable
            diag.correct.append(entry)

        else:
            # Check for technique scatter
            gate_trace = r.get("gate_trace", [])
            technique_step = next(
                (g for g in gate_trace if "technique" in g.get("gate", "")), None
            )
            if technique_step and not technique_step.get("passed"):
                entry["root_cause"] = "technique_scatter"
                entry["detail"] = technique_step.get("detail", "")
                diag.technique_scatter.append(entry)
            else:
                diag.correct.append(entry)

    return diag
