"""Annealing schedule for datalake extraction quality thresholds.

Margaret Chen's annealing schedule adjusts quality thresholds based on corpus
coverage, similar to simulated annealing: lenient early, strict late.

Mirrors Brandon Bailey's SPARTA annealing but uses the 7-dimension scoring
framework and corpus coverage percentage instead of QRA counts.
"""

# Annealing schedule keyed by (min_coverage_pct, max_coverage_pct)
# Coverage = total_pdfs / (target_per_sector * num_sectors)
ANNEALING_SCHEDULE = {
    # Phase 0: Bootstrap (0-20%)
    (0, 20): {
        "min_score": 0.70,
        "max_fail_ratio": 0.10,
        "max_critical_ratio": 0.02,
        "table_fidelity_min": 0.70,
        "section_alignment_min": 0.70,
        "phase_name": "Bootstrap",
        "margaret_says": "Let's see what we're working with before passing judgment.",
        "jennifer_says": "Establishing baseline. Need data before we can assess.",
    },
    # Phase 1: Early Growth (20-50%)
    (20, 50): {
        "min_score": 0.78,
        "max_fail_ratio": 0.05,
        "max_critical_ratio": 0.01,
        "table_fidelity_min": 0.78,
        "section_alignment_min": 0.78,
        "phase_name": "Early Growth",
        "margaret_says": "Time to raise the bar. We have enough data to know what good looks like.",
        "jennifer_says": "Defense docs are coming in. Tighten up on structural fidelity.",
    },
    # Phase 2: Mid Growth (50-75%)
    (50, 75): {
        "min_score": 0.85,
        "max_fail_ratio": 0.03,
        "max_critical_ratio": 0.005,
        "table_fidelity_min": 0.85,
        "section_alignment_min": 0.85,
        "phase_name": "Mid Growth",
        "margaret_says": "No more excuses for sloppy extraction. Every table, every equation.",
        "jennifer_says": "MIL-STD tables must be pixel-perfect. No dropped constraints.",
    },
    # Phase 3: Late Growth (75-90%)
    (75, 90): {
        "min_score": 0.88,
        "max_fail_ratio": 0.02,
        "max_critical_ratio": 0.002,
        "table_fidelity_min": 0.88,
        "section_alignment_min": 0.88,
        "phase_name": "Late Growth",
        "margaret_says": "Tightening the screws. This is where certification rigor kicks in.",
        "jennifer_says": "Every defense document must meet Grade A. No exceptions.",
    },
    # Phase 4: Refinement (90-95%)
    (90, 95): {
        "min_score": 0.90,
        "max_fail_ratio": 0.01,
        "max_critical_ratio": 0.001,
        "table_fidelity_min": 0.90,
        "section_alignment_min": 0.90,
        "phase_name": "Refinement",
        "margaret_says": "Almost there. Every detail matters. Every. Single. One.",
        "jennifer_says": "Final review pass. Cross-check everything against source.",
    },
    # Phase 5: Certification (95%+)
    (95, float("inf")): {
        "min_score": 0.95,
        "max_fail_ratio": 0.005,
        "max_critical_ratio": 0.0,
        "table_fidelity_min": 0.95,
        "section_alignment_min": 0.95,
        "phase_name": "Certification",
        "margaret_says": "This goes on the certification package. Zero tolerance.",
        "jennifer_says": "Production quality. Ship it or fix it.",
    },
}

# Target sectors and their PDF targets
TARGET_SECTORS = {
    "arxiv": 500,
    "dtic": 500,
    "faa": 500,
    "nasa": 500,
    "nist": 500,
    "ietf": 500,
    "industry": 500,
    "adversarial": 500,
    "edge_cases": 500,
}
TOTAL_TARGET = sum(TARGET_SECTORS.values())  # 4500

# Stratified sample monitoring thresholds
CATASTROPHIC_SCORE_THRESHOLD = 0.40    # Below this: restart everything
CATASTROPHIC_FAIL_PCT = 60.0           # >60% FAIL verdicts: restart
SPOT_FIX_WORST_COUNT = 10              # Return bottom N PDFs for targeted fix


def get_coverage_pct(sector_counts: dict) -> float:
    """Calculate overall coverage percentage."""
    if not sector_counts:
        return 0.0
    total_pdfs = sum(sector_counts.values())
    return min(100.0, 100.0 * total_pdfs / TOTAL_TARGET)


def get_annealing_thresholds(coverage_pct: float) -> dict:
    """Get dynamic thresholds based on corpus coverage (annealing schedule).

    Args:
        coverage_pct: Current coverage percentage (0-100+)

    Returns:
        Dictionary with current thresholds and phase info
    """
    for (min_cov, max_cov), thresholds in ANNEALING_SCHEDULE.items():
        if min_cov <= coverage_pct < max_cov:
            return {
                **thresholds,
                "coverage_pct": coverage_pct,
                "phase_range": f"{min_cov}%-{max_cov}%" if max_cov != float("inf") else f"{min_cov}%+",
            }

    # Fallback to strictest
    strictest = ANNEALING_SCHEDULE[(95, float("inf"))]
    return {
        **strictest,
        "coverage_pct": coverage_pct,
        "phase_range": "95%+",
    }


def should_continue_extraction(
    coverage_pct: float,
    avg_score: float | None,
    fail_ratio: float | None,
    critical_ratio: float | None = None,
    table_fidelity: float | None = None,
    section_alignment: float | None = None,
) -> dict:
    """Margaret + Jennifer decide: should we continue extracting, or stop and fix?

    Args:
        coverage_pct: Corpus coverage percentage
        avg_score: Rolling average quality score (0.0-1.0)
        fail_ratio: Ratio of FAIL verdicts (0.0-1.0)
        critical_ratio: Ratio of critical issues (0.0-1.0)
        table_fidelity: Table fidelity dimension score
        section_alignment: Section alignment dimension score

    Returns:
        Dictionary with decision and persona reasoning
    """
    thresholds = get_annealing_thresholds(coverage_pct)

    # If no scores yet (startup/bootstrap), continue
    if avg_score is None and fail_ratio is None:
        return {
            "decision": "CONTINUE",
            "phase": thresholds["phase_name"],
            "thresholds": thresholds,
            "margaret_says": "No scores yet. Keep extracting until we have data to assess.",
            "jennifer_says": "Need a baseline before we can make judgments.",
            "metrics": {},
        }

    issues = []
    metrics = {
        "avg_score": avg_score,
        "avg_score_threshold": thresholds["min_score"],
        "fail_ratio": fail_ratio,
        "fail_ratio_threshold": thresholds["max_fail_ratio"],
    }

    # Check overall score
    if avg_score is not None and avg_score < thresholds["min_score"]:
        issues.append(f"avg_score {avg_score:.3f} < {thresholds['min_score']}")

    # Check fail ratio
    if fail_ratio is not None and fail_ratio > thresholds["max_fail_ratio"]:
        issues.append(f"fail_ratio {fail_ratio:.3f} > {thresholds['max_fail_ratio']}")

    # Check critical ratio
    if critical_ratio is not None and critical_ratio > thresholds["max_critical_ratio"]:
        issues.append(f"critical_ratio {critical_ratio:.4f} > {thresholds['max_critical_ratio']}")
        metrics["critical_ratio"] = critical_ratio
        metrics["critical_ratio_threshold"] = thresholds["max_critical_ratio"]

    # Check dimension-specific thresholds
    if table_fidelity is not None and table_fidelity < thresholds["table_fidelity_min"]:
        issues.append(f"table_fidelity {table_fidelity:.3f} < {thresholds['table_fidelity_min']}")
        metrics["table_fidelity"] = table_fidelity

    if section_alignment is not None and section_alignment < thresholds["section_alignment_min"]:
        issues.append(f"section_alignment {section_alignment:.3f} < {thresholds['section_alignment_min']}")
        metrics["section_alignment"] = section_alignment

    if not issues:
        return {
            "decision": "CONTINUE",
            "phase": thresholds["phase_name"],
            "thresholds": thresholds,
            "margaret_says": thresholds["margaret_says"],
            "jennifer_says": thresholds["jennifer_says"],
            "metrics": metrics,
        }

    # Decide severity: STOP_AND_FIX vs ESCALATE
    # Critical issues or multiple failures = ESCALATE
    critical = any("critical" in i for i in issues)
    if critical or len(issues) >= 3:
        return {
            "decision": "ESCALATE",
            "phase": thresholds["phase_name"],
            "thresholds": thresholds,
            "issues": issues,
            "margaret_says": (
                f"Multiple quality failures in {thresholds['phase_name']} phase. "
                f"Issues: {'; '.join(issues)}. This needs immediate attention."
            ),
            "jennifer_says": (
                f"Escalating. {len(issues)} threshold violations. "
                "Cannot continue extraction until root cause is identified."
            ),
            "metrics": metrics,
        }

    return {
        "decision": "STOP_AND_FIX",
        "phase": thresholds["phase_name"],
        "thresholds": thresholds,
        "issues": issues,
        "margaret_says": (
            f"Quality below {thresholds['phase_name']} threshold. "
            f"Fix: {'; '.join(issues)}. Then resume."
        ),
        "jennifer_says": (
            f"Extraction paused. {issues[0]}. "
            "Diagnose and fix before continuing."
        ),
        "metrics": metrics,
    }


# ── Independent persona evaluation functions ──

MARGARET_WEIGHTS = {
    "table_fidelity": 0.30,
    "equation_fidelity": 0.25,
    "section_alignment": 0.25,
    "content_coverage": 0.10,
    "ordering_yx": 0.10,
}
MARGARET_AVIATION_SECTORS = {"faa", "nasa"}

JENNIFER_WEIGHTS = {
    "data_quality": 0.25,
    "table_fidelity": 0.25,
    "section_alignment": 0.20,
    "content_coverage": 0.15,
    "figure_fidelity": 0.15,
}
JENNIFER_DEFENSE_SECTORS = {"dtic", "nist", "defense"}

import os as _os
CORPUS_PREFIX = _os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb") + "/extractor_corpus/"


def _extract_sector(pdf_path: str) -> str:
    """Extract sector name from a corpus PDF path."""
    if pdf_path.startswith(CORPUS_PREFIX):
        rel = pdf_path[len(CORPUS_PREFIX):]
        return rel.split("/")[0] if "/" in rel else "unknown"
    return "external"


def _sector_failure_rate(recent_failed_pdfs: list[str], target_sectors: set[str]) -> float:
    """Fraction of recent failures that fall in target sectors."""
    if not recent_failed_pdfs:
        return 0.0
    sector_fails = sum(1 for p in recent_failed_pdfs
                       if _extract_sector(p) in target_sectors)
    return sector_fails / max(len(recent_failed_pdfs), 1)


def _weighted_score(dim_scores: dict, weights: dict) -> float:
    """Compute a weighted score from dimension scores and weight dict.

    Missing dimensions are ignored and their weight redistributed
    proportionally to present dimensions.
    """
    present = {k: v for k, v in weights.items() if k in dim_scores}
    if not present:
        return 0.0
    total_weight = sum(present.values())
    return sum(dim_scores[k] * (w / total_weight) for k, w in present.items())


def margaret_evaluates(
    coverage_pct: float,
    dim_scores: dict,
    fail_ratio: float,
    critical_ratio: float,
    run_metrics: dict,
    state: dict,
) -> dict:
    """Margaret Chen — DO-178C certification lens.

    Emphasizes table fidelity, equation fidelity, and section alignment.
    Extra penalty for failures in aviation sectors (FAA, NASA).
    Flags Lean4 dead-letter buildup.

    Returns:
        {"verdict": "PASS"|"WARN"|"FAIL", "weighted_score": float,
         "issues": [...], "says": str}
    """
    thresholds = get_annealing_thresholds(coverage_pct)
    min_score = thresholds["min_score"]
    phase = thresholds["phase_name"]

    score = _weighted_score(dim_scores, MARGARET_WEIGHTS)
    issues = []

    # Sector penalty
    recent_failed = run_metrics.get("recent_failed_pdfs", [])
    aviation_rate = _sector_failure_rate(recent_failed, MARGARET_AVIATION_SECTORS)
    if aviation_rate > 0.50:
        score -= 0.05
        issues.append(f"aviation_sector_failure_rate={aviation_rate:.0%} (>50%, -0.05 penalty)")

    # Lean4 dead-letter check
    dead_letters = run_metrics.get("memory_retry_dead_letter_count", 0)
    if dead_letters > 10:
        issues.append(f"lean4_dead_letters={dead_letters} (>10)")

    # Fail ratio check
    max_fail = thresholds["max_fail_ratio"]
    if fail_ratio > max_fail:
        issues.append(f"fail_ratio={fail_ratio:.3f} > {max_fail}")

    # Critical ratio check
    max_crit = thresholds["max_critical_ratio"]
    if critical_ratio > max_crit:
        issues.append(f"critical_ratio={critical_ratio:.4f} > {max_crit}")

    # Verdict
    if score >= min_score and not issues:
        verdict = "PASS"
        says = (
            f"[{phase}] Weighted score {score:.3f} meets {min_score}. "
            f"Table fidelity and equation fidelity look solid. Continue."
        )
    elif score < min_score:
        verdict = "FAIL"
        says = (
            f"[{phase}] Weighted score {score:.3f} below {min_score}. "
            f"Issues: {'; '.join(issues) if issues else 'score too low'}. "
            "Cannot certify at this quality level."
        )
    else:
        verdict = "WARN"
        says = (
            f"[{phase}] Weighted score {score:.3f} meets threshold but "
            f"issues detected: {'; '.join(issues)}. Monitor closely."
        )

    return {
        "verdict": verdict,
        "weighted_score": round(score, 4),
        "issues": issues,
        "says": says,
    }


def jennifer_evaluates(
    coverage_pct: float,
    dim_scores: dict,
    fail_ratio: float,
    critical_ratio: float,
    run_metrics: dict,
    state: dict,
) -> dict:
    """Jennifer Cheung — Defense/MIL-STD systems lens.

    Emphasizes data quality, table fidelity, and figure fidelity.
    Extra penalty for failures in defense sectors (DTIC, NIST, defense).
    Flags high missing-structural rate in defense docs.

    Returns:
        {"verdict": "PASS"|"WARN"|"FAIL", "weighted_score": float,
         "issues": [...], "says": str}
    """
    thresholds = get_annealing_thresholds(coverage_pct)
    min_score = thresholds["min_score"]
    phase = thresholds["phase_name"]

    score = _weighted_score(dim_scores, JENNIFER_WEIGHTS)
    issues = []

    # Sector penalty
    recent_failed = run_metrics.get("recent_failed_pdfs", [])
    defense_rate = _sector_failure_rate(recent_failed, JENNIFER_DEFENSE_SECTORS)
    if defense_rate > 0.50:
        score -= 0.05
        issues.append(f"defense_sector_failure_rate={defense_rate:.0%} (>50%, -0.05 penalty)")

    # Missing structural rate check for defense docs
    missing_structural = run_metrics.get("extraction_missing_structural_rate_pct", 0)
    if missing_structural > 5:
        issues.append(f"missing_structural_rate={missing_structural:.1f}% (>5%)")

    # Fail ratio check
    max_fail = thresholds["max_fail_ratio"]
    if fail_ratio > max_fail:
        issues.append(f"fail_ratio={fail_ratio:.3f} > {max_fail}")

    # Critical ratio check
    max_crit = thresholds["max_critical_ratio"]
    if critical_ratio > max_crit:
        issues.append(f"critical_ratio={critical_ratio:.4f} > {max_crit}")

    # Verdict
    if score >= min_score and not issues:
        verdict = "PASS"
        says = (
            f"[{phase}] Weighted score {score:.3f} meets {min_score}. "
            f"Data quality and structural integrity acceptable. Continue."
        )
    elif score < min_score:
        verdict = "FAIL"
        says = (
            f"[{phase}] Weighted score {score:.3f} below {min_score}. "
            f"Issues: {'; '.join(issues) if issues else 'score too low'}. "
            "Defense document fidelity is not production-ready."
        )
    else:
        verdict = "WARN"
        says = (
            f"[{phase}] Weighted score {score:.3f} meets threshold but "
            f"issues detected: {'; '.join(issues)}. Needs attention."
        )

    return {
        "verdict": verdict,
        "weighted_score": round(score, 4),
        "issues": issues,
        "says": says,
    }


# Verdict severity ordering for reconciliation
_SEVERITY = {"PASS": 0, "WARN": 1, "FAIL": 2}


def reconcile(margaret_result: dict, jennifer_result: dict) -> dict:
    """Reconcile two independent persona evaluations.

    Stricter verdict wins. Disagreement is surfaced as a diagnostic signal.

    Decision mapping:
        PASS + PASS  → CONTINUE
        WARN + PASS  → CONTINUE (with adjustments)
        WARN + WARN  → STOP_AND_FIX
        FAIL + any   → STOP_AND_FIX
        FAIL + FAIL  → ESCALATE

    Returns:
        {"decision": str, "consensus": bool, "margaret_verdict": str,
         "jennifer_verdict": str, "disagreement_reason": str|None,
         "research_queries": [...]}
    """
    mv = margaret_result["verdict"]
    jv = jennifer_result["verdict"]
    consensus = mv == jv

    # Stricter verdict wins
    if _SEVERITY.get(mv, 0) >= _SEVERITY.get(jv, 0):
        reconciled = mv
    else:
        reconciled = jv

    # Map to decision
    if reconciled == "PASS":
        decision = "CONTINUE"
    elif reconciled == "WARN":
        if mv == "WARN" and jv == "WARN":
            decision = "STOP_AND_FIX"
        else:
            decision = "CONTINUE"
    else:  # FAIL
        if mv == "FAIL" and jv == "FAIL":
            decision = "ESCALATE"
        else:
            decision = "STOP_AND_FIX"

    # Disagreement analysis
    disagreement_reason = None
    research_queries = []

    if not consensus:
        # Find which dimensions diverge
        m_issues = set(margaret_result.get("issues", []))
        j_issues = set(jennifer_result.get("issues", []))
        unique_m = m_issues - j_issues
        unique_j = j_issues - m_issues

        parts = []
        if unique_m:
            parts.append(f"Margaret flagged: {'; '.join(sorted(unique_m))}")
        if unique_j:
            parts.append(f"Jennifer flagged: {'; '.join(sorted(unique_j))}")
        if not parts:
            parts.append(
                f"Score divergence: Margaret={margaret_result['weighted_score']:.3f} "
                f"Jennifer={jennifer_result['weighted_score']:.3f}"
            )
        disagreement_reason = " | ".join(parts)

        # Generate targeted research queries from disagreement
        if any("aviation_sector" in i for i in m_issues):
            research_queries.append(
                "aviation document PDF extraction DO-178C table equation "
                "fidelity failure patterns FAA NASA"
            )
        if any("defense_sector" in i for i in j_issues):
            research_queries.append(
                "defense document PDF extraction structural integrity "
                "failure patterns MIL-STD DTIC NIST"
            )
        if any("missing_structural" in i for i in j_issues):
            research_queries.append(
                "PDF missing structural elements defense document "
                "extraction pipeline section hierarchy"
            )
        if any("dead_letter" in i for i in m_issues):
            research_queries.append(
                "Lean4 theorem prover dead letter queue "
                "formal verification pipeline retry failures"
            )

    return {
        "decision": decision,
        "consensus": consensus,
        "margaret_verdict": mv,
        "jennifer_verdict": jv,
        "disagreement_reason": disagreement_reason,
        "research_queries": research_queries[:3],
    }
