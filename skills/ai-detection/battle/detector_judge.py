"""Battle invariant judge for ai-detection: AI-authored code must stay flagged.

Battle pluggable-judge contract (battle.invariant_result.v1): expose
`judge(target_dir, params) -> {passed, violations, evidence}`. Red's objective is
to make this Judge FAIL (produce an evading, still-AI-authored file); Blue's is
to keep it passing. The scorekeeper reads this result, never an agent self-report.

Invariant: every released Python file under target_dir that is AI-authored must
score >= the detector's calibrated threshold. A file that drops below threshold
is a Red win (evasion) and is recorded as a violation.

Proof boundary: on a synthetic-trained model this measures raw score-vs-threshold
movement (MECHANISM ONLY) — it is not evasion of a qualified detector, authorship,
or efficacy. Fail-closed: any error (missing model, unimportable dependency,
unparseable file) is a FAILED invariant, never a silent pass.

params: {"model_path": str (required), "threshold": float|null, "glob": str}
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


def judge(target_dir: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    params = params or {}
    result: dict[str, Any] = {
        "schema": "battle.invariant_result.v1",
        "passed": False,
        "violations": [],
        "evidence": {
            "invariant": "ai_authored_code_stays_flagged",
            "proof_scope": "mechanism_only_score_vs_threshold",
            "does_not_prove": "qualified-detector evasion, authorship, or efficacy",
        },
    }
    try:
        from ai_detection.model import load_model, predict
    except Exception as exc:  # fail-closed: dependency not importable is a FAILED invariant
        result["violations"].append(f"ai_detection unavailable in judge environment: {exc}")
        return result

    model_path = params.get("model_path")
    if not model_path:
        result["violations"].append("params.model_path is required")
        return result
    try:
        model = load_model(Path(model_path))
    except Exception as exc:
        result["violations"].append(f"could not load model {model_path!r}: {exc}")
        return result

    threshold = params.get("threshold")
    if threshold is None:
        threshold = model.calibration.threshold
    result["evidence"]["threshold"] = float(threshold)

    files = sorted(Path(target_dir).glob(params.get("glob", "*.py")))
    if not files:
        result["violations"].append(f"no candidate files under {target_dir} (glob={params.get('glob', '*.py')})")
        return result

    scores: dict[str, float] = {}
    for path in files:
        try:
            score = predict(model, path.read_text(encoding="utf-8"))
        except Exception as exc:
            # An unscoreable released file is a violation, not a pass.
            result["violations"].append(f"{path.name}: unscoreable ({exc})")
            continue
        scores[path.name] = float(score)
        if score < threshold:
            result["violations"].append(
                f"{path.name}: evaded — score {score:.4f} < threshold {threshold:.4f}")
    result["evidence"]["scores"] = scores
    result["evidence"]["files"] = len(files)
    result["passed"] = len(result["violations"]) == 0
    return result
