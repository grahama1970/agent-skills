"""Diagnosis engine for conversation-lab sessions.

Classifies session issues (zero QRA citations, over-clarification,
self-grade regression, wrong answers with LogicGraph error taxonomy),
determines rerun eligibility, and builds structured diagnosis reports
consumed by /assess and the convergence loop.
"""
from __future__ import annotations

from collections import Counter

from loguru import logger


# ---------------------------------------------------------------------------
# LogicGraph error taxonomy (arXiv:2602.21044, Wu et al.)
# Maps reasoning failures to actionable /prompt-lab fix categories
# ---------------------------------------------------------------------------
LOGIC_GRAPH_ERROR_TAXONOMY = {
    "semantic_misinterpretation": "Model confused causality direction or negation",
    "information_omission": "Model ignored a critical piece of evidence",
    "fact_hallucination": "Model fabricated facts absent from context",
    "invalid_deduction": "Derivation is logically flawed even with correct premises",
    "insufficient_premise": "Conclusion drawn from subset of necessary conditions",
    "rule_misapplication": "Correct rule applied where preconditions aren't met",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_persona_evals(session: dict) -> list[str]:
    """Extract persona evaluation strings from session turns."""
    evals = []
    for turn in session.get("turns", []):
        if not isinstance(turn, dict):
            continue
        meta = turn.get("metadata", {})
        if isinstance(meta, dict) and meta.get("evaluation"):
            evals.append(meta["evaluation"])
    return evals


def classify_reasoning_error(session: dict) -> str | None:
    """Classify wrong_answer into LogicGraph error type using session metadata.

    Uses structured grade fields and Lean4 error taxonomy when available.
    Falls back to the dominant error type (insufficient_premise, 90% per LogicGraph).
    """
    grade = session.get("grade", {}) if isinstance(session.get("grade"), dict) else {}

    # Best signal: Lean4 compiler already classified the error
    lean4_taxonomy = grade.get("lean4_error_taxonomy", {})
    if lean4_taxonomy:
        return max(lean4_taxonomy, key=lean4_taxonomy.get, default=None)

    # Next: use structured grade signals (no string fishing)
    if grade.get("reasoning_sound") is False:
        if grade.get("error_type") in LOGIC_GRAPH_ERROR_TAXONOMY:
            return grade["error_type"]
        if grade.get("hallucinated_facts"):
            return "fact_hallucination"
        if grade.get("missing_evidence"):
            return "information_omission"
        return "insufficient_premise"

    # Persona said "wrong" but no structured grade
    return "insufficient_premise"


# ---------------------------------------------------------------------------
# Issue classification
# ---------------------------------------------------------------------------
def _extract_evidence_case_issues(audit_entry: dict) -> list[str]:
    """Extract issues from a /create-evidence-case tree attached to an audit.

    When /lie-detector cascade produces an evidence case (CAE tree), the
    winning strategy's score and verdict provide structured signal beyond
    the flat audit verdict.
    """
    issues = []
    trace = audit_entry.get("trace", {})
    if not isinstance(trace, dict):
        return issues
    evidence_case = trace.get("evidence_case")
    if not evidence_case or not isinstance(evidence_case, dict):
        return issues

    verdict = evidence_case.get("verdict", {})
    case_state = verdict.get("state", "")
    case_grade = verdict.get("grade", "")
    case_score = verdict.get("score", 0.0)

    if case_state == "not_satisfied":
        issues.append("evidence_case_not_satisfied")
    elif case_state == "inconclusive":
        issues.append("evidence_case_inconclusive")

    # Check if evidence is thin (few items or low confidence)
    evidence_items = evidence_case.get("evidence", [])
    if len(evidence_items) <= 1:
        issues.append("evidence_case_thin")

    strategies = evidence_case.get("strategies", [])
    winner = next((s for s in strategies if s.get("selected")), None)
    if winner and winner.get("score", 0) < 0.65:
        issues.append("evidence_case_low_strategy_score")

    return issues


def classify_issues(
    session: dict,
    audit_entry: dict | None = None,
) -> list[str]:
    """Classify issues for a single session.

    Args:
        audit_entry: Optional /lie-detector audit verdict for this session.
            If provided, audit-detected regressions are added as issues.
            When the audit includes an evidence_case tree (from
            /create-evidence-case), its structured verdict is also consumed.
    """
    issues = []
    grade = session.get("grade", {})
    composite = grade.get("composite", 0.0) if isinstance(grade, dict) else 0.0

    # /lie-detector audit verdicts (highest priority signal)
    if audit_entry:
        audit_verdict = audit_entry.get("verdict", "CLEAN")
        if audit_verdict == "MENDACIOUS":
            issues.append("audit_mendacious")
        elif audit_verdict == "LAZY":
            issues.append("audit_lazy")
        elif audit_verdict == "REGRESSED":
            issues.append("audit_regressed")
        # Also check for grade vs audit mismatch
        self_grade = grade.get("grade", "?") if isinstance(grade, dict) else "?"
        if self_grade in ("A+", "A") and audit_verdict in ("MENDACIOUS", "LAZY"):
            issues.append("audit_self_grade_mismatch")

        # Evidence case tree issues (from /create-evidence-case via cascade)
        issues.extend(_extract_evidence_case_issues(audit_entry))

    # Zero QRA citations
    qra_cited = grade.get("qra_citations_total", 0) if isinstance(grade, dict) else 0
    turns = session.get("turns", [])
    if qra_cited == 0:
        any_qras = any(
            t.get("metadata", {}).get("qra_count", 0) > 0
            for t in turns if isinstance(t, dict)
        )
        if not any_qras:
            issues.append("zero_qra_citations")

    # Over-clarification: CLARIFY action when question had a known control ID
    clarify_turns = [
        t for t in turns
        if isinstance(t, dict) and t.get("action") == "CLARIFY"
    ]
    target = session.get("seed_question", {}).get("target_control", "")
    if clarify_turns and target and target.startswith("SV-"):
        issues.append("over_clarification")

    # Self-grade regression: final composite lower than first
    delta = session.get("shadow_delta", {})
    first_comp = delta.get("first_composite", composite)
    final_comp = delta.get("final_composite", composite)
    if isinstance(first_comp, (int, float)) and isinstance(final_comp, (int, float)):
        if final_comp < first_comp - 0.05:
            issues.append("self_grade_regression")

    # Wrong answer -- with LogicGraph error taxonomy sub-classification
    persona_evals = get_persona_evals(session)
    if "wrong" in persona_evals:
        issues.append("wrong_answer")
        error_type = classify_reasoning_error(session)
        if error_type:
            issues.append(f"wrong_answer:{error_type}")

    # Incomplete coverage
    resolution = session.get("resolution", "")
    if resolution == "no_coverage":
        issues.append("coverage_gap")

    return issues


# ---------------------------------------------------------------------------
# Rerun eligibility
# ---------------------------------------------------------------------------
def is_rerun_eligible(
    session: dict, issues: list[str], *, systemic_issues: set[str] | None = None,
) -> tuple[bool, str]:
    """Determine if session should be rerun and why.

    Args:
        systemic_issues: Issue types affecting >50% of sessions. Re-running
            won't help these -- they need infrastructure fixes (e.g. missing
            ArangoSearch view, broken embedding service).
    """
    systemic = systemic_issues or set()

    # Audit verdicts override persona self-assessment (the agent can't excuse
    # its own lies — this is the core design principle of /lie-detector).
    # These checks MUST run before the satisfied gate.
    # When systemic (>50%), route to /prompt-lab or /assistant for retraining
    # instead of re-running individual sessions.
    audit_issues = {
        "audit_mendacious": "mendacious answer — /prompt-lab retrain grounding prompts",
        "audit_self_grade_mismatch": "self-grade conflicts with audit — /prompt-lab retrain grading",
        "audit_lazy": "lazy answer — /prompt-lab retrain answer depth",
        "audit_regressed": "quality regression — /prompt-lab retrain multi-turn consistency",
    }
    for audit_key, description in audit_issues.items():
        if audit_key in issues:
            if audit_key in systemic:
                return False, f"systemic: {description} (>50% sessions, needs retraining not rerun)"
            return True, f"lie-detector: {description} (overrides persona satisfied)"

    # Persona satisfaction gate — only trusted when no audit flags
    persona_evals = get_persona_evals(session)
    satisfied = "satisfactory" in persona_evals
    if satisfied:
        return False, ""

    resolution = session.get("resolution", "")
    grade_info = session.get("grade", {})
    composite = grade_info.get("composite", 0.0) if isinstance(grade_info, dict) else 0.0

    if "zero_qra_citations" in issues:
        if "zero_qra_citations" in systemic:
            return False, "systemic: zero QRAs across >50% sessions (infra fix needed)"
        return True, "persona unsatisfied + zero QRAs"
    if "over_clarification" in issues:
        return True, "unnecessary clarification on known control"
    if "self_grade_regression" in issues:
        return True, "self-grade regressed -- may improve with more rounds"
    if resolution == "partial":
        return True, "partial resolution -- more rounds may help"
    if composite < 0.80 and resolution != "no_coverage":
        return True, f"low composite ({composite:.2f}) with potential for improvement"

    return False, ""


# ---------------------------------------------------------------------------
# Full diagnosis builder
# ---------------------------------------------------------------------------
def build_diagnosis(
    sessions: list[dict],
    audit_index: dict[str, dict] | None = None,
) -> dict:
    """Build full structured diagnosis from sessions.

    Args:
        audit_index: Optional /lie-detector audit verdicts keyed by session_id.
            When provided, audit findings are integrated into issue classification
            and rerun prioritization.
    """
    total = len(sessions)
    if total == 0:
        return {"summary": {"total": 0}, "sessions": [], "systemic_issues": []}

    grades = Counter()
    resolutions = Counter()
    composites = []
    satisfied_count = 0
    all_issues: Counter = Counter()
    coverage_gap_controls: list[str] = []
    session_reports = []
    rerun_candidates = []
    turns_satisfied = []
    turns_unsatisfied = []

    # Pass 1: classify issues for all sessions to detect systemic patterns
    _audit = audit_index or {}
    per_session_issues: list[list[str]] = []
    for s in sessions:
        sid = s.get("session_id", "")
        per_session_issues.append(classify_issues(s, audit_entry=_audit.get(sid)))
        issues = per_session_issues[-1]
        for issue in issues:
            all_issues[issue] += 1
        if "coverage_gap" in issues:
            target = s.get("seed_question", {}).get("target_control", "")
            if target:
                coverage_gap_controls.append(target)

    # Issues affecting >50% of sessions are systemic -- re-running won't help
    systemic_issue_types = {
        issue for issue, count in all_issues.items()
        if count > total * 0.5
    }

    # Pass 2: build per-session reports with systemic context
    for s, issues in zip(sessions, per_session_issues):
        grade_info = s.get("grade", {})
        grade_letter = grade_info.get("grade", "?") if isinstance(grade_info, dict) else "?"
        composite = grade_info.get("composite", 0.0) if isinstance(grade_info, dict) else 0.0
        resolution = s.get("resolution", "unknown")

        grades[grade_letter] += 1
        resolutions[resolution] += 1
        composites.append(composite)

        persona_evals = get_persona_evals(s)
        # Persona eval is primary signal; grade threshold is fallback
        # when sessions lack multi-turn persona evaluations (e.g. simple runner).
        satisfied = (
            "satisfactory" in persona_evals
            or (not persona_evals and composite >= 0.78 and not issues)
        )
        if satisfied:
            satisfied_count += 1

        rerun_ok, rerun_reason = is_rerun_eligible(
            s, issues, systemic_issues=systemic_issue_types,
        )

        turn_count = len(s.get("turns", []))
        if satisfied:
            turns_satisfied.append(turn_count)
        else:
            turns_unsatisfied.append(turn_count)

        delta_info = s.get("shadow_delta", {})
        first_c = delta_info.get("first_composite", composite)
        final_c = delta_info.get("final_composite", composite)

        # Extract evidence case summary if present in audit trace
        sid = s.get("session_id", "unknown")
        evidence_case_summary = None
        audit_for_session = _audit.get(sid, {})
        ec_trace = audit_for_session.get("trace", {}) if isinstance(audit_for_session, dict) else {}
        if isinstance(ec_trace, dict) and "evidence_case" in ec_trace:
            ec = ec_trace["evidence_case"]
            ec_verdict = ec.get("verdict", {})
            ec_winner = next((st for st in ec.get("strategies", []) if st.get("selected")), None)
            evidence_case_summary = {
                "case_id": ec.get("claim", {}).get("id", ""),
                "state": ec_verdict.get("state", ""),
                "grade": ec_verdict.get("grade", ""),
                "score": ec_verdict.get("score", 0.0),
                "winning_strategy": ec_winner.get("name", "") if ec_winner else "",
                "evidence_count": len(ec.get("evidence", [])),
            }

        report = {
            "session_id": sid,
            "persona": s.get("persona", "unknown"),
            "target_control": s.get("seed_question", {}).get("target_control", ""),
            "difficulty": s.get("seed_question", {}).get("difficulty", "medium"),
            "grade": grade_letter,
            "composite": round(composite, 3),
            "resolution": resolution,
            "satisfied": satisfied,
            "turns": turn_count,
            "qras_cited": (
                grade_info.get("qra_citations_total", 0)
                if isinstance(grade_info, dict) else 0
            ),
            "persona_evals": persona_evals,
            "issues": issues,
            "delta": {
                "first": round(first_c, 3) if isinstance(first_c, (int, float)) else 0,
                "final": round(final_c, 3) if isinstance(final_c, (int, float)) else 0,
                "change": round(final_c - first_c, 3) if isinstance(first_c, (int, float)) and isinstance(final_c, (int, float)) else 0,
            },
            "rerun_eligible": rerun_ok,
            "rerun_reason": rerun_reason,
        }
        if evidence_case_summary:
            report["evidence_case"] = evidence_case_summary
        session_reports.append(report)
        if rerun_ok:
            rerun_candidates.append(s.get("session_id", "unknown"))

    avg_composite = sum(composites) / len(composites) if composites else 0
    avg_turns_sat = sum(turns_satisfied) / len(turns_satisfied) if turns_satisfied else 0
    avg_turns_unsat = sum(turns_unsatisfied) / len(turns_unsatisfied) if turns_unsatisfied else 0

    # Build systemic issues with severity, fix suggestions, and skill routing.
    # Systemic issues (>50% of sessions) need /prompt-lab or /assistant
    # retraining — re-running individual sessions won't help.
    systemic = []
    issue_meta = {
        # (severity, per-session fix, systemic skill route)
        "audit_mendacious": (
            "critical",
            "Answer graded A but lacks substance — fix grader or answer",
            "/prompt-lab retrain grounding prompts + /assistant validate grading",
        ),
        "audit_self_grade_mismatch": (
            "critical",
            "Self-grade contradicts audit — grading function may be broken",
            "/prompt-lab retrain self-grading prompts + /assistant audit grader",
        ),
        "audit_lazy": (
            "high",
            "Answer too short for question complexity — require minimum substance",
            "/prompt-lab retrain answer depth prompts",
        ),
        "audit_regressed": (
            "high",
            "Quality dropped between turns — investigate root cause",
            "/prompt-lab retrain multi-turn consistency",
        ),
        "zero_qra_citations": (
            "critical",
            "Check ArangoSearch view + embedding service",
            "/assistant validate retrieval pipeline",
        ),
        "over_clarification": (
            "high",
            "Tune ambiguity classifier for known control IDs",
            "/prompt-lab retrain ambiguity thresholds",
        ),
        "self_grade_regression": (
            "high",
            "Cap iteration at best-so-far composite",
            "/prompt-lab retrain self-assessment calibration",
        ),
        "wrong_answer": (
            "medium",
            "Verify QRA corpus accuracy for affected controls",
            "/assistant validate answer accuracy + /prompt-lab retrain reasoning",
        ),
        "coverage_gap": (
            "medium",
            "Run gap-filler for missing controls",
            "/assistant validate corpus coverage",
        ),
        "evidence_case_not_satisfied": (
            "high",
            "Evidence case verdict NOT_SATISFIED — claim lacks proof",
            "/create-evidence-case with wider MCTS + /prompt-lab retrain",
        ),
        "evidence_case_inconclusive": (
            "medium",
            "Evidence case inconclusive — strategies unable to resolve",
            "/create-evidence-case --strategies 3 for wider exploration",
        ),
        "evidence_case_thin": (
            "medium",
            "Evidence case has <=1 evidence item — needs deeper collection",
            "/create-evidence-case with more strategy turns",
        ),
        "evidence_case_low_strategy_score": (
            "high",
            "Winning strategy score < 0.65 — evidence quality insufficient",
            "/create-evidence-case + /recommend-skill-chain for better strategies",
        ),
    }
    for issue, count in all_issues.most_common():
        meta = issue_meta.get(issue, ("low", "Investigate", ""))
        severity, fix, skill_route = meta
        is_systemic = issue in systemic_issue_types
        entry: dict = {
            "issue": issue,
            "count": count,
            "severity": severity,
            "fix": fix,
            "is_systemic": is_systemic,
        }
        if is_systemic and skill_route:
            entry["systemic_route"] = skill_route
        if issue == "coverage_gap" and coverage_gap_controls:
            entry["controls"] = sorted(set(coverage_gap_controls))
        systemic.append(entry)

    return {
        "summary": {
            "total": total,
            "pass": grades.get("A", 0) + grades.get("B", 0),
            "warn": grades.get("C", 0),
            "fail": grades.get("F", 0),
            "avg_composite": round(avg_composite, 3),
            "satisfied_rate": round(satisfied_count / total, 3) if total else 0,
            "grades": dict(grades.most_common()),
            "resolutions": dict(resolutions.most_common()),
        },
        "systemic_issues": systemic,
        "sessions": session_reports,
        "rerun_candidates": rerun_candidates,
        "turn_stats": {
            "avg_turns_satisfied": round(avg_turns_sat, 1),
            "avg_turns_unsatisfied": round(avg_turns_unsat, 1),
            "optimal_turns_estimate": round((avg_turns_sat + avg_turns_unsat) / 2, 0)
            if (avg_turns_sat and avg_turns_unsat) else 4,
        },
    }
