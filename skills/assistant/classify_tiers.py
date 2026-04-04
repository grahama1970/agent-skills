"""Classifier tier-building for the assistant gateway.

Extracted from gateway.py to keep that file under the 800-line limit.
Provides build_classify_tiers() which assembles the tier list for a
single classification task, and run_classify_cascade() which executes
it end-to-end.

Do NOT import graph_memory directly here.  All model loading goes
through the registry (models.py).  All LLM escalation goes through
scillm via gateway._scillm_escalate (passed as a callable).
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

from common.cascade import TierResult, TierDef, CascadeRunner


def build_classify_tiers(
    task: str,
    classifier_info: Optional[tuple],
    task_prompts: Dict[str, str],
    scillm_fn: Callable,
    memory_fn: Callable,
    multilabel_threshold_fn: Callable,
    build_tabular_features_fn: Callable,
    confidence_threshold: float,
    heuristic_fn: Optional[Callable],
    shadow_file: Any,
    metrics_file: Any,
) -> tuple:
    """Assemble the tier list for a single classification cascade.

    Returns (tiers, shadow, has_scillm) where:
    - tiers:      list[TierDef] ready to pass to CascadeRunner
    - shadow:     bool — whether shadow mode is active for this task
    - has_scillm: bool — whether a scillm tier was added
    """
    tiers: List[TierDef] = []
    shadow = False

    # Tier 0: Heuristic (optional, caller-supplied)
    if heuristic_fn is not None:
        def _heuristic_tier(inp, **kw):
            r = heuristic_fn(inp)
            if r is None:
                return None
            return TierResult(prediction=str(r), confidence=1.0)
        tiers.append(TierDef(tier=0, name="heuristic", fn=_heuristic_tier))

    # Tier 0.5: Classifier
    if classifier_info is not None:
        model, model_type, cfg = classifier_info
        cls_threshold = cfg.get("confidence_threshold", confidence_threshold)
        shadow = cfg.get("shadow_mode", False)

        def _classifier_tier(inp, **kw):  # noqa: C901 (complexity acceptable here)
            input_sig = cfg.get("input_signature", {})
            sig_type = input_sig.get("type", "text")

            if model_type == "sklearn" and sig_type == "tabular":
                feat_dict = json.loads(inp) if isinstance(inp, str) else inp
                if not isinstance(feat_dict, dict):
                    return None
                feature_row = build_tabular_features_fn(feat_dict, input_sig)
                import numpy as np
                pred_raw = model.predict(np.array([feature_row]))[0]
                proba_arr = model.predict_proba(np.array([feature_row]))[0] if hasattr(model, "predict_proba") else None
                proba = float(max(proba_arr)) if proba_arr is not None else 0.5
                le = cfg.get("_label_encoder")
                pred = le.inverse_transform([pred_raw])[0] if le is not None else str(pred_raw)
                probabilities = {}
                if proba_arr is not None and le is not None:
                    classes = le.inverse_transform(range(len(proba_arr)))
                    probabilities = {str(c): round(float(p), 4) for c, p in zip(classes, proba_arr)}
                return TierResult(prediction=str(pred), confidence=proba, probabilities=probabilities)

            t = str(inp)
            if model_type == "sklearn":
                if isinstance(model, dict) and model.get("multi_label"):
                    X = model["tfidf"].transform([t])
                    y_pred = model["clf"].predict(X)
                    tags = list(model["mlb"].inverse_transform(y_pred)[0])
                    probabilities = {}
                    if hasattr(model["clf"], "predict_proba"):
                        probs = model["clf"].predict_proba(X)
                        for i, cls_name in enumerate(model["mlb"].classes_):
                            probabilities[str(cls_name)] = round(float(probs[0][i]), 4)
                    avg_proba = float(max(probabilities.values())) if probabilities else 0.5
                    return TierResult(
                        prediction=",".join(tags) if tags else "",
                        confidence=avg_proba,
                        result={"tags": tags},
                        probabilities=probabilities,
                    )
                pred = model.predict([t])[0]
                proba = float(max(model.predict_proba([t])[0])) if hasattr(model, "predict_proba") else 0.5
                probabilities = {}
                if hasattr(model, "predict_proba") and hasattr(model, "classes_"):
                    probs = model.predict_proba([t])[0]
                    probabilities = {str(c): round(float(p), 4) for c, p in zip(model.classes_, probs)}
            elif model_type == "distilbert":
                out = model(t[:512])
                pred, proba = out[0]["label"], out[0]["score"]
                probabilities = {r["label"]: round(r["score"], 4) for r in out}
            elif model_type == "distilbert-multilabel":
                tags, probabilities, proba = multilabel_threshold_fn(model(t[:512]), cfg)
                pred = ",".join(tags) if tags else ""
                return TierResult(
                    prediction=pred, confidence=proba,
                    result={"tags": tags}, probabilities=probabilities,
                )
            elif model_type == "setfit":
                import numpy as np
                preds = model.predict([t])
                pred = str(preds[0])
                try:
                    proba_arr = model.predict_proba([t])
                    if hasattr(proba_arr, "numpy"):
                        proba_arr = proba_arr.numpy()
                    proba_arr = np.array(proba_arr[0])
                    proba = float(proba_arr.max())
                    labels_list = cfg.get("classes", [])
                    probabilities = {labels_list[i]: round(float(p), 4) for i, p in enumerate(proba_arr)} if labels_list else {}
                except Exception:
                    proba = 0.8
                    probabilities = {}
            else:
                return None
            return TierResult(prediction=str(pred), confidence=proba, probabilities=probabilities)

        tiers.append(TierDef(
            tier=0.5, name="classifier", fn=_classifier_tier,
            threshold=cls_threshold, shadow_mode=shadow,
        ))

    # Sensei Cascade enforcement: production classifiers without GPT rationale
    # Note: classify path currently skips T1.5 GPT entirely. This is the gap
    # that Sensei Cascade requires us to fill. Log warning for visibility.
    if classifier_info is not None and not shadow:
        from .models import get_gpt_router
        # Check if this task has a matching validator with gpt_model_path
        validator_cfg = {}
        try:
            from .models import _load_registry
            reg = _load_registry()
            validator_cfg = reg.get("validators", {}).get(task, {})
        except Exception:
            pass
        gpt_path = validator_cfg.get("gpt_model_path", "")
        if not gpt_path:
            logger.warning(
                f"SENSEI CASCADE GAP: classifier '{task}' is production "
                f"(shadow_mode=false) but has NO GPT rationale. "
                f"Cascade skips T1.5 → falls through to T2 scillm (expensive). "
                f"Train a rationale GPT via /create-gpt."
            )

    # Tier 2: scillm (authoritative teacher)
    has_task_prompt = task in task_prompts
    add_scillm = shadow or classifier_info is None or has_task_prompt

    if add_scillm:
        def _scillm_tier(inp, **kw):
            mem_ctx = memory_fn({"text": str(inp)}, kw.get("scope", "")) if kw.get("scope") else ""
            scillm_result = scillm_fn(str(inp), kw.get("task", ""), system_context=mem_ctx)
            if "error" in scillm_result:
                logger.error(f"scillm escalation failed: {scillm_result['error']}")
                return None
            result_dict = {}
            tags = scillm_result.get("tags")
            if isinstance(tags, list):
                result_dict["tags"] = tags
                prediction = ",".join(str(t) for t in tags)
            else:
                prediction = scillm_result.get("prediction", scillm_result.get("label", str(scillm_result)))
            return TierResult(prediction=str(prediction), result=result_dict, confidence=1.0)
        tiers.append(TierDef(tier=2, name="scillm", fn=_scillm_tier, is_teacher=True))

    return tiers, shadow, add_scillm


def run_classify_cascade(
    text: str,
    task: str,
    scope: str,
    tiers: list,
    cache_key: str,
    shadow_file: Any,
    metrics_file: Any,
    cache_fn: Callable,
    store_cache_fn: Callable,
) -> TierResult:
    """Run CascadeRunner for a single classification task and cache result."""
    runner = CascadeRunner(
        tiers=tiers,
        shadow_file=shadow_file,
        metrics_file=metrics_file,
    )
    result = runner.run(text, task=task, scope=scope, input_hash=cache_key)
    store_cache_fn(cache_key, result)
    return result
