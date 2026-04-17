"""convergence — Deterministic coded self-improvement loop for pdf-lab tune-gt.

Follows best-practices-self-improvement-loop: the loop is in code, not
agent-directed.  Strategies are ordered and exhausted deterministically.
Results are written to disk after every iteration.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from .preset_store import store_preset


# ---------------------------------------------------------------------------
# Data structures (kept from original)
# ---------------------------------------------------------------------------

@dataclass
class Adjustment:
    """A single parameter adjustment applied during a strategy."""
    parameter: str
    current: Any
    suggested: Any
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "parameter": self.parameter,
            "current": self.current,
            "suggested": self.suggested,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Adjustment":
        return cls(
            parameter=d.get("parameter", ""),
            current=d.get("current"),
            suggested=d.get("suggested"),
            reason=d.get("reason", ""),
        )


@dataclass
class RoundResult:
    """Result of a single convergence round."""
    round_num: int
    max_rounds: int
    score: float
    target_score: float
    strategy_name: str
    overrides: Dict[str, Any]
    worst_category: str = ""
    worst_score: float = 0.0
    worst_detail: str = ""
    diagnosis: str = ""
    adjustments: List[Adjustment] = field(default_factory=list)
    visual_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "round": self.round_num,
            "score": round(self.score, 4),
            "visual_score": round(self.visual_score, 4),
            "target": self.target_score,
            "strategy": self.strategy_name,
            "worst_category": self.worst_category,
            "worst_score": round(self.worst_score, 4),
            "worst_detail": self.worst_detail,
            "diagnosis": self.diagnosis,
            "adjustments": [a.to_dict() for a in self.adjustments],
            "overrides": self.overrides,
        }


@dataclass
class ConvergenceResult:
    """Final result of the convergence loop."""
    fixture_id: str
    converged: bool
    rounds: int
    final_score: float
    target_score: float
    adjustments_applied: List[Adjustment]
    round_history: List[RoundResult]
    overrides_path: Optional[str] = None
    registry_path: Optional[str] = None
    preset_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "converged": self.converged,
            "rounds": self.rounds,
            "final_score": round(self.final_score, 4),
            "target_score": self.target_score,
            "adjustments_applied": [a.to_dict() for a in self.adjustments_applied],
            "round_history": [r.to_dict() for r in self.round_history],
            "overrides_path": self.overrides_path,
            "registry_path": self.registry_path,
            "preset_key": self.preset_key,
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_baseline_median(fixture_pdf: Path) -> float | None:
    """Extract median font size from page 0 spans."""
    import pdf_oxide

    try:
        doc = pdf_oxide.PdfDocument(str(fixture_pdf))
        spans = doc.extract_spans(0)
        sizes = [s["size"] for s in spans if isinstance(s.get("size"), (int, float)) and s["size"] > 0]
        if not sizes:
            return None
        sizes.sort()
        mid = len(sizes) // 2
        median = sizes[mid] if len(sizes) % 2 else (sizes[mid - 1] + sizes[mid]) / 2
        return round(median, 1)
    except Exception as e:
        logger.warning("Could not compute baseline median: {}", e)
        return None


def _write_audit(audit_path: Path, entry: Dict[str, Any]) -> None:
    """Append a round entry to the audit JSON array on disk."""
    existing: List[Dict[str, Any]] = []
    if audit_path.exists():
        try:
            existing = json.loads(audit_path.read_text())
        except (json.JSONDecodeError, ValueError):
            existing = []
    existing.append(entry)
    audit_path.write_text(json.dumps(existing, indent=2))


# ---------------------------------------------------------------------------
# Core convergence loop (deterministic, coded — Rule 1)
# ---------------------------------------------------------------------------

def run_convergence(
    fixture_pdf: Path,
    ground_truth: Path,
    *,
    max_rounds: int = 20,
    target_score: float = 0.90,
    visual_gate: bool = False,
) -> ConvergenceResult:
    """Deterministic self-improvement loop for PDF extraction tuning.

    1. Pre-flight: verify inputs and import pdf_oxide
    2. Compute baseline median font size from page 0 spans
    3. Generate ordered strategies from strategies.py
    4. For each strategy: extract -> score -> compare to gate -> next
    5. Write audit to disk after EVERY iteration (Rule 6)
    6. Return best result or halt with full audit trail (Rule 4)
    """
    from .compare import compare as run_compare
    from .strategies import generate_strategies

    # --- Pre-flight (Rule 5) ---
    if not fixture_pdf.exists():
        raise FileNotFoundError(f"Fixture PDF not found: {fixture_pdf}")
    if not ground_truth.exists():
        raise FileNotFoundError(f"Ground truth not found: {ground_truth}")
    try:
        import pdf_oxide  # noqa: F401
    except ImportError as e:
        raise RuntimeError("pdf_oxide not importable — build with maturin develop") from e

    gt = json.loads(ground_truth.read_text())
    fixture_id = gt.get("fixture_id", fixture_pdf.stem)
    audit_path = fixture_pdf.parent / "convergence_audit.json"

    # Clear stale audit from previous run
    if audit_path.exists():
        audit_path.unlink()

    # --- Baseline median ---
    baseline_median = _get_baseline_median(fixture_pdf)
    logger.info("Baseline median font size: {}", baseline_median)

    # --- Generate strategies (deterministic, ordered — Rule 3) ---
    strategies = generate_strategies(baseline_median)
    cap = min(len(strategies), max_rounds)
    logger.info("Running {} strategies (max_rounds={})", cap, max_rounds)

    round_history: List[RoundResult] = []
    best_score = -1.0
    best_overrides: Dict[str, Any] = {}
    best_strategy = "none"

    # --- Deterministic loop (Rule 1, Rule 2) ---
    for i, strategy in enumerate(strategies[:cap]):
        round_num = i + 1

        # Build overrides from strategy
        overrides: Dict[str, Any] = {}
        if strategy.get("body_font_size_override") is not None:
            overrides["body_font_size_override"] = strategy["body_font_size_override"]
        if strategy.get("header_ratio_override") is not None:
            overrides["header_ratio_override"] = strategy["header_ratio_override"]

        # TRY: extract and score
        t0 = time.monotonic()
        try:
            comparison = run_compare(fixture_pdf, ground_truth, overrides=overrides or None)
            score = comparison.get("overall_score", 0.0)
        except Exception as e:
            logger.error("Strategy {} failed: {}", strategy["name"], e)
            score = 0.0
            comparison = {}

        if visual_gate:
            from .visual_score import verify_document
            import pdf_oxide
            doc = pdf_oxide.PdfDocument(str(fixture_pdf))
            ext = doc.extract_document(**{k: v for k, v in overrides.items() if v is not None})
            verification = verify_document(fixture_pdf, ext, max_pages=3)
            v_score = verification.get("mean_score", 0.0)
            combined = score * 0.7 + v_score * 0.3
            logger.debug("Visual verification: mean={:.4f}, low_conf={}", v_score, len(verification.get("low_confidence", [])))
        else:
            combined = score
            v_score = 0.0
        elapsed = time.monotonic() - t0

        # Build adjustments list for this round
        adjustments = []
        for key in ("body_font_size_override", "header_ratio_override"):
            if key in overrides:
                adjustments.append(Adjustment(
                    parameter=key,
                    current=None,
                    suggested=overrides[key],
                    reason=strategy.get("description", ""),
                ))

        rr = RoundResult(
            round_num=round_num,
            max_rounds=cap,
            score=combined,
            target_score=target_score,
            strategy_name=strategy["name"],
            overrides=dict(overrides),
            adjustments=adjustments,
            visual_score=v_score,
        )
        round_history.append(rr)

        # WRITE to disk IMMEDIATELY (Rule 6)
        _write_audit(audit_path, {
            **rr.to_dict(),
            "elapsed_s": round(elapsed, 3),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Track best
        if combined > best_score:
            best_score = combined
            best_overrides = dict(overrides)
            best_strategy = strategy["name"]

        logger.info(
            "  [{}/{}] {} -> {:.4f} ({:.1f}s){}",
            round_num, cap, strategy["name"], combined, elapsed,
            " * BEST" if combined >= best_score else "",
        )

        # COMPARE TO GATE (Rule 2)
        if combined >= target_score:
            logger.info("CONVERGED at round {} with score {:.4f} (strategy: {})",
                        round_num, combined, strategy["name"])
            break
    else:
        logger.warning("Exhausted {} strategies without reaching target {:.2f} (best: {:.4f})",
                       cap, target_score, best_score)

    # --- Final outputs ---
    converged = best_score >= target_score
    overrides_path = fixture_pdf.parent / "tune_overrides.json"
    registry_path = fixture_pdf.parent / "fix_registry.json"

    # Write best overrides
    if best_overrides:
        overrides_path.write_text(json.dumps(best_overrides, indent=2))

    # Write fix registry (Rule 4: full audit trail)
    registry_path.write_text(json.dumps({
        "fixture_id": fixture_id,
        "converged": converged,
        "best_strategy": best_strategy,
        "rounds": len(round_history),
        "final_score": round(best_score, 4),
        "target_score": target_score,
        "overrides": best_overrides,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }, indent=2))

    # Store converged params as ArangoDB preset
    preset_key = None
    if converged:
        preset_key = store_preset(
            name=fixture_id,
            params=best_overrides,
            source_doc=str(fixture_pdf),
            score=best_score,
            audit={"total_rounds": len(round_history), "best_strategy": best_strategy},
        )
        if preset_key:
            logger.info("Stored preset: {}", preset_key)

    return ConvergenceResult(
        fixture_id=fixture_id,
        converged=converged,
        rounds=len(round_history),
        final_score=best_score,
        target_score=target_score,
        adjustments_applied=[a for rr in round_history for a in rr.adjustments],
        round_history=round_history,
        overrides_path=str(overrides_path) if best_overrides else None,
        registry_path=str(registry_path),
        preset_key=preset_key,
    )
