"""Annealing schedule logic for dynamic threshold management.

Brandon's annealing schedule adjusts quality thresholds based on corpus size,
similar to simulated annealing in optimization: lenient early, strict late.
"""

from config import ANNEALING_SCHEDULE


def get_annealing_thresholds(qra_count: int) -> dict:
    """Get dynamic thresholds based on corpus size (annealing schedule).

    Brandon decides the thresholds based on where we are in the training process.
    Like annealing in model training - start loose, tighten as we converge.

    Args:
        qra_count: Current number of QRAs in the corpus

    Returns:
        Dictionary with current thresholds and phase info
    """
    for (min_qras, max_qras), thresholds in ANNEALING_SCHEDULE.items():
        if min_qras <= qra_count < max_qras:
            return {
                **thresholds,
                "qra_count": qra_count,
                "phase_range": f"{min_qras:,}-{max_qras:,}" if max_qras != float('inf') else f"{min_qras:,}+",
            }

    # Fallback to strictest
    return {
        **ANNEALING_SCHEDULE[(100000, float('inf'))],
        "qra_count": qra_count,
        "phase_range": "100,000+",
    }


def should_continue_generation(qra_count: int, assessment: dict) -> dict:
    """Brandon decides: should we continue generating, or stop and fix?

    This is the convergence decision - like knowing when to stop annealing.

    Args:
        qra_count: Current QRA count
        assessment: Results from Brandon assessment

    Returns:
        Dictionary with decision and reasoning
    """
    thresholds = get_annealing_thresholds(qra_count)

    anchoring_pct = assessment.get("anchoring_issue_pct", 0)
    generic_pct = assessment.get("all_generic_pct", 0)

    # Check against dynamic thresholds
    anchoring_ok = anchoring_pct <= thresholds["anchoring_fail_pct"]
    generic_ok = generic_pct <= thresholds["generic_fail_pct"]

    if anchoring_ok and generic_ok:
        return {
            "decision": "CONTINUE",
            "phase": thresholds["phase_name"],
            "thresholds": thresholds,
            "brandon_says": f"Quality is acceptable for {thresholds['phase_name']} phase. Keep generating.",
            "metrics": {
                "anchoring_pct": anchoring_pct,
                "anchoring_threshold": thresholds["anchoring_fail_pct"],
                "generic_pct": generic_pct,
                "generic_threshold": thresholds["generic_fail_pct"],
            }
        }
    elif not anchoring_ok:
        return {
            "decision": "STOP_AND_FIX",
            "phase": thresholds["phase_name"],
            "thresholds": thresholds,
            "brandon_says": f"Anchoring issues ({anchoring_pct}%) exceed {thresholds['phase_name']} threshold ({thresholds['anchoring_fail_pct']}%). Fix before continuing!",
            "fix_priority": "ANCHORING",
            "metrics": {
                "anchoring_pct": anchoring_pct,
                "anchoring_threshold": thresholds["anchoring_fail_pct"],
                "generic_pct": generic_pct,
                "generic_threshold": thresholds["generic_fail_pct"],
            }
        }
    else:
        return {
            "decision": "STOP_AND_FIX",
            "phase": thresholds["phase_name"],
            "thresholds": thresholds,
            "brandon_says": f"Generic content ({generic_pct}%) exceeds {thresholds['phase_name']} threshold ({thresholds['generic_fail_pct']}%). Add more space terminology!",
            "fix_priority": "GENERIC_CONTENT",
            "metrics": {
                "anchoring_pct": anchoring_pct,
                "anchoring_threshold": thresholds["anchoring_fail_pct"],
                "generic_pct": generic_pct,
                "generic_threshold": thresholds["generic_fail_pct"],
            }
        }
