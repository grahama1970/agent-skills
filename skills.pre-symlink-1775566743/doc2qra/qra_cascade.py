"""CascadeRunner integration for doc2qra skill.

Provides the Shadow-LEGO self-improvement loop that routes QRA
extraction through gateway (Tier 1.5) in shadow mode, then
escalates to scillm batch (Tier 2 teacher) for agreement tracking
and eventual promotion.
"""

from __future__ import annotations

from typing import Any, Dict, List

from .config import DEFAULT_CONCURRENCY, preflight_budget_check
from .qra_gateway import extract_qra_gateway
from .utils import log


def _bucket_grade(qra_count: int, sections_with_qa: int, total_sections: int) -> str:
    """Bucket QRA extraction results into categorical grades for shadow comparison.

    Shadow agreement compares grades as strings. Using raw counts (e.g., "16_qras")
    means local and teacher will almost never agree on exact numbers -- 0% agreement
    that's a grading artifact, not a quality signal.

    Two-axis grade: coverage (which sections) + density (QRAs per section):
      Coverage: FULL (>=80%) | PARTIAL (>=30%) | SPARSE (<30%)
      Density:  RICH (>=3/sec) | ADEQUATE (>=1/sec) | THIN (<1/sec)

    Combined: "FULL_ADEQUATE", "FULL_RICH", etc.

    This captures the real quality gap (gateway: ~1 QRA/section -> ADEQUATE,
    teacher: ~10 QRA/section -> RICH) while being coarse enough that small
    count variations don't cause false disagreements.
    """
    if qra_count == 0:
        return "EMPTY"

    total = max(total_sections, 1)
    coverage = sections_with_qa / total
    density = qra_count / total

    cov_label = "FULL" if coverage >= 0.8 else "PARTIAL" if coverage >= 0.3 else "SPARSE"
    den_label = "RICH" if density >= 3.0 else "ADEQUATE" if density >= 1.0 else "THIN"

    return f"{cov_label}_{den_label}"


def build_qra_cascade(shadow_file=None, metrics_file=None):
    """Build a CascadeRunner for QRA extraction with self-improvement loop.

    Tier 1.5 (gateway) runs in shadow_mode: extracts QRAs, records result,
    escalates to Tier 2 (scillm teacher). Shadow entries track agreement.
    When agreement_rate >= 90%, gateway can be promoted (shadow_mode=False).
    Lazy/low-quality QRAs get caught by disagreement tracking in shadow.jsonl.

    Args:
        shadow_file: Path for shadow comparison log (default ~/.pi/doc2qra/shadow.jsonl)
        metrics_file: Path for metrics log (default ~/.pi/doc2qra/metrics.jsonl)

    Returns:
        CascadeRunner instance, or None if cascade module unavailable
    """
    import asyncio
    from pathlib import Path

    try:
        from common.cascade import CascadeRunner, TierDef, TierResult
    except ImportError:
        return None  # cascade module not available

    # Import here to avoid circular dependency
    from .qra_batch import extract_qra_batch

    default_shadow = Path("~/.pi/doc2qra/shadow.jsonl")
    default_metrics = Path("~/.pi/doc2qra/metrics.jsonl")

    def _tier_gateway(input_data, task="", scope="", **kw):
        """Tier 1.5: /assistant gateway (shadow mode -- records + escalates)."""
        from .qra_gateway import is_gateway_available as _is_gw

        if not _is_gw():
            return None

        sections = input_data["sections"]
        source = input_data.get("source", "")
        all_qa = extract_qra_gateway(sections, source)

        if not all_qa:
            return None

        # Confidence = fraction of sections that produced QRAs
        section_count = max(len(sections), 1)
        sections_with_qa = len(set(q.get("section_idx", -1) for q in all_qa if q.get("section_idx") is not None))
        confidence = min(1.0, sections_with_qa / section_count)

        return TierResult(
            result={"items": all_qa, "grade": _bucket_grade(len(all_qa), sections_with_qa, section_count)},
            confidence=confidence,
        )

    def _tier_scillm(input_data, task="", scope="", **kw):
        """Tier 2: scillm batch extraction (teacher for shadow comparison)."""
        sections = input_data["sections"]
        source = input_data.get("source", "")
        estimated = len(sections) + 1
        config = preflight_budget_check(estimated)
        if not config.get("api_key"):
            return None
        context = kw.get("context")
        concurrency = kw.get("concurrency", DEFAULT_CONCURRENCY)

        try:
            all_qa = asyncio.run(
                extract_qra_batch(sections, source=source, concurrency=concurrency, context=context)
            )
        except Exception as e:
            log(f"scillm batch tier failed: {e}", style="red")
            return None

        if not all_qa:
            return None

        section_count = max(len(sections), 1)
        sections_with_qa = len(set(q.get("section_idx", -1) for q in all_qa if q.get("section_idx") is not None))
        confidence = min(1.0, sections_with_qa / section_count)

        return TierResult(
            result={"items": all_qa, "grade": _bucket_grade(len(all_qa), sections_with_qa, section_count)},
            confidence=confidence,
        )

    return CascadeRunner(
        tiers=[
            TierDef(
                tier=1.5, name="gateway", fn=_tier_gateway,
                threshold=0.3,
                shadow_mode=True,  # Self-improvement: record but escalate to teacher
            ),
            TierDef(
                tier=2, name="scillm", fn=_tier_scillm,
                threshold=0.0,
                is_teacher=True,  # Authoritative for shadow comparison
            ),
        ],
        shadow_file=shadow_file or default_shadow,
        metrics_file=metrics_file or default_metrics,
    )
