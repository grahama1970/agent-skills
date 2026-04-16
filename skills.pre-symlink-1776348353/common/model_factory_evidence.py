"""Promotion evidence case builder for ModelFactory.

Calls /create-evidence-case to build a formal audit trail for every
model promotion decision. Non-blocking enrichment — if the skill is
unavailable, promotion proceeds as before.

Optionally verifies via /lean4-prove (gated by LEAN4_VERIFY_PROMOTION env var).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

from loguru import logger

EVIDENCE_RUN = Path.home() / ".pi" / "skills" / "create-evidence-case" / "run.sh"
LEAN4_RUN = Path.home() / ".pi" / "skills" / "lean4-prove" / "run.sh"


def build_promotion_evidence(
    task_name: str,
    model_entry: Dict[str, Any],
    agreement_rate: float,
    sample_count: int,
    wilson_lb: Optional[float] = None,
) -> Optional[Path]:
    """Build formal evidence case for a promotion decision.

    Calls /create-evidence-case with the claim:
    "Model {task_name} should be promoted because: agreement_rate={rate},
     sample_count={n}, wilson_lb={lb}"

    Optionally verifies via /lean4-prove (gated by LEAN4_VERIFY_PROMOTION env var).

    Returns: Path to evidence case JSON, or None if building failed.
    """
    if not EVIDENCE_RUN.exists():
        return None

    claim = (
        f"Model {task_name} ({model_entry.get('model_type', 'unknown')}) "
        f"should be promoted to production. "
        f"Shadow agreement rate: {agreement_rate:.3f}. "
        f"Sample count: {sample_count}. "
    )
    if wilson_lb is not None:
        claim += f"Wilson lower bound: {wilson_lb:.3f} (gate: >= 0.85). "
    claim += (
        f"Training data provenance: "
        f"{model_entry.get('training_samples', 'unknown')} samples."
    )

    try:
        result = subprocess.run(
            [str(EVIDENCE_RUN), "create", claim, "--json", "--quiet"],
            capture_output=True, text=True, timeout=60,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if result.returncode != 0:
            return None

        evidence = json.loads(result.stdout)

        # Save evidence case alongside model
        model_path = model_entry.get("model_path") or model_entry.get("gpt_model_path", "/tmp")
        evidence_dir = Path(model_path).parent / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        evidence_path = evidence_dir / f"promotion_evidence_{task_name}.json"
        evidence_path.write_text(json.dumps(evidence, indent=2))

        # Optional lean4 verification
        if os.environ.get("LEAN4_VERIFY_PROMOTION", "").lower() in ("1", "true"):
            _lean4_verify_promotion(evidence, evidence_path)

        return evidence_path
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        logger.warning(f"Promotion evidence case failed for {task_name}: {e}")
        return None


def log_non_promotion_evidence(
    task_name: str,
    decision: str,
    agreement_rate: float,
    sample_count: int,
    reason: str,
) -> None:
    """Log negative evidence for non-promotion decisions (retrain/plateau).

    This creates a lightweight record for future analysis without calling
    /create-evidence-case (which is reserved for affirmative claims).
    """
    logger.info(
        f"Non-promotion decision for {task_name}: "
        f"decision={decision}, agreement={agreement_rate:.3f}, "
        f"samples={sample_count}, reason={reason}"
    )


def _lean4_verify_promotion(
    evidence: Dict[str, Any],
    evidence_path: Path,
) -> None:
    """Attempt formal verification of promotion claim via /lean4-prove."""
    if not LEAN4_RUN.exists():
        return

    claim_text = evidence.get("claim", "")
    try:
        result = subprocess.run(
            [str(LEAN4_RUN), "verify", claim_text, "--json"],
            capture_output=True, text=True, timeout=120,
            env={k: v for k, v in os.environ.items() if k != "VIRTUAL_ENV"},
        )
        if result.returncode == 0:
            verification = json.loads(result.stdout)
            evidence["lean4_verification"] = verification
            evidence_path.write_text(json.dumps(evidence, indent=2))
            logger.info(f"Lean4 verification added to {evidence_path}")
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception) as e:
        logger.warning(f"Lean4 verification failed (non-fatal): {e}")
