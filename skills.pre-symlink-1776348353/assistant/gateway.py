"""Core cascade gateway: validate(), classify(), dispatch(), and AssistantRouter.

Assembles tier functions from the model registry and runs them through
the CascadeRunner from common.cascade. Provides memory injection,
persona routing, result caching, and scillm escalation.
"""

from __future__ import annotations

import hashlib
import httpx
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent
SCILLM_URL = "http://localhost:4001"

if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))
from common.cascade import TierResult, TierDef, CascadeRunner

try:
    from .models import (
        ModelCache,
        cache as _cache,
        get_gpt_router,
        get_classifier,
        build_tabular_features,
        CACHE_TTL_HOURS,
    )
    from .task_prompts import TASK_PROMPTS as _TASK_PROMPTS
    from .routing import resolve_taxonomy_tagger, resolve_taxonomy_taggers
    from .classify_tiers import build_classify_tiers, run_classify_cascade
except ImportError:
    from models import (  # type: ignore[no-redef]
        ModelCache,
        cache as _cache,
        get_gpt_router,
        get_classifier,
        build_tabular_features,
        CACHE_TTL_HOURS,
    )
    from task_prompts import TASK_PROMPTS as _TASK_PROMPTS  # type: ignore[no-redef]
    from routing import resolve_taxonomy_tagger, resolve_taxonomy_taggers  # type: ignore[no-redef]
    from classify_tiers import build_classify_tiers, run_classify_cascade  # type: ignore[no-redef]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
METRICS_DIR = Path(os.environ.get("ASSISTANT_METRICS_DIR", str(Path.home() / ".pi" / "assistant")))
METRICS_FILE = METRICS_DIR / "metrics.jsonl"
SHADOW_FILE = METRICS_DIR / "shadow.jsonl"
REGISTRY_PATH = SKILL_DIR / "model_registry.json"


# ---------------------------------------------------------------------------
# Result aliases (backward compat)
# ---------------------------------------------------------------------------
GatewayResult = TierResult
ClassifyResult = TierResult


# ---------------------------------------------------------------------------
# Registry loader
# ---------------------------------------------------------------------------

def load_registry(path: Path = REGISTRY_PATH) -> Dict[str, Any]:
    """Load model registry from JSON."""
    if not path.exists():
        logger.warning(f"Registry not found at {path}, using empty registry")
        return {"validators": {}, "classifiers": {}}
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Memory integration (graceful degradation)
# ---------------------------------------------------------------------------

def _get_memory_client():
    """Lazy import of memory client. Returns None if unavailable."""
    try:
        sys.path.insert(0, str(SKILLS_DIR))
        from common.memory_client import MemoryClient
        return MemoryClient
    except ImportError:
        logger.debug("Memory client unavailable, memory injection disabled")
        return None


def _inject_memory_context(input_data: Dict[str, Any], scope: str, k: int = 3) -> str:
    """Recall from persona memory scope, format as system prompt prefix.

    Returns empty string if memory is unavailable or scope is empty.
    """
    if not scope:
        return ""

    ClientClass = _get_memory_client()
    if ClientClass is None:
        return ""

    try:
        client = ClientClass(scope=scope)
        summary = json.dumps(input_data, ensure_ascii=False)[:200]
        recall_result = client.recall(query=summary, k=k)
        if recall_result.found:
            return recall_result.to_context(max_items=k)
    except Exception as e:
        logger.debug(f"Memory injection failed for scope={scope}: {e}")

    return ""


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_key(input_data: Any, task: str, scope: str) -> str:
    """SHA1 of canonical input+task+scope."""
    canonical = json.dumps(
        {"input": input_data, "task": task, "scope": scope},
        sort_keys=True, ensure_ascii=False,
    )
    return hashlib.sha1(canonical.encode()).hexdigest()


def _check_cache(key: str, cache: ModelCache = _cache):
    """Return cached result or None."""
    if key in cache.results:
        result, expiry = cache.results[key]
        if time.time() < expiry:
            return result
        del cache.results[key]
    return None


def _store_cache(key: str, result, cache: ModelCache = _cache):
    """Store result in cache with TTL."""
    cache.results[key] = (result, time.time() + CACHE_TTL_HOURS * 3600)


# ---------------------------------------------------------------------------
# Metrics logging for cache hits
# ---------------------------------------------------------------------------

def _log_metric_cached(result: TierResult) -> None:
    """Log metric for cache hits (bypass CascadeRunner)."""
    try:
        METRICS_DIR.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "task": result.task,
            "scope": result.scope,
            "tier": result.tier,
            "source": result.source,
            "confidence": round(result.confidence, 4),
            "latency_ms": round(result.latency_ms, 2),
            "cached": True,
        }
        with open(METRICS_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as e:
        logger.debug("file write failed: {}", e)


# ---------------------------------------------------------------------------
# Multi-label helpers
# ---------------------------------------------------------------------------

def _multilabel_threshold(pipeline_out: list, cfg: dict) -> tuple:
    """Apply per-class thresholds to HF pipeline output. Returns (tags, probabilities, max_proba)."""
    thresholds = cfg.get("per_class_thresholds", {})
    default_thresh = cfg.get("confidence_threshold", 0.5)
    tags, probabilities = [], {}
    for item in pipeline_out:
        label, score = item["label"], item["score"]
        probabilities[label] = round(score, 4)
        if score >= thresholds.get(label, default_thresh):
            tags.append(label)
    return tags, probabilities, max(probabilities.values()) if probabilities else 0.0


# ---------------------------------------------------------------------------
# Prompt provenance (shadow mode — Task 3 of cascade v2 pivot)
# ---------------------------------------------------------------------------

# ENFORCE mode: reject unvalidated prompts. Flipped from shadow→enforce 2026-03-13.
_PROVENANCE_ENFORCE = True

def _check_prompt_provenance(task: str, prompt_content: str) -> bool:
    """Check if a task prompt has been validated via /prompt-lab.

    In shadow mode (_PROVENANCE_ENFORCE=False): logs warning, returns True.
    In enforce mode: returns False for unvalidated prompts.
    """
    if not prompt_content:
        return True  # No prompt to check

    try:
        sys.path.insert(0, str(SKILLS_DIR / "prompt-lab"))
        from provenance import verify_prompt_provenance

        result = verify_prompt_provenance(prompt_content)

        if result["verified"]:
            logger.debug(
                "Prompt provenance OK for task={} sha256={}… f1={}",
                task, result["sha256"][:16], result.get("eval_f1", "?"),
            )
            return True

        # Unvalidated prompt detected
        warning = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": "unvalidated_prompt",
            "task": task,
            "sha256": result["sha256"][:16],
            "reason": result.get("reason", "unknown"),
            "enforce": _PROVENANCE_ENFORCE,
        }
        logger.warning(
            "Unvalidated prompt for task={} sha256={}… (enforce={})",
            task, result["sha256"][:16], _PROVENANCE_ENFORCE,
        )

        # Log to shadow file
        try:
            METRICS_DIR.mkdir(parents=True, exist_ok=True)
            with open(SHADOW_FILE, "a") as f:
                f.write(json.dumps(warning) + "\n")
        except Exception:
            pass

        return not _PROVENANCE_ENFORCE

    except Exception as e:
        logger.debug("Provenance check unavailable: {}", e)
        return True  # Don't block if provenance system is down


# ---------------------------------------------------------------------------
# Scillm escalation (Tier 2)
# ---------------------------------------------------------------------------

def _scillm_escalate(input_text: str, task: str, system_context: str = "") -> Dict[str, Any]:
    """Escalate to scillm (tier 2) for authoritative answer via scillm HTTP proxy."""
    prompt_parts = []
    # Task-specific prompt (gives the LLM context on what to classify)
    task_prompt = _TASK_PROMPTS.get(task, "")
    if task_prompt:
        # Provenance gate: check if this prompt was validated via /prompt-lab
        if not _check_prompt_provenance(task, task_prompt):
            return {"error": f"Unvalidated prompt for task '{task}'. Run /prompt-lab eval first."}
        prompt_parts.append(task_prompt)
    if system_context:
        prompt_parts.append(system_context)
    prompt_parts.append(f"\nInput:\n{input_text}")
    if not task_prompt:
        prompt_parts.append("\nRespond with valid JSON.")
    prompt = "\n".join(prompt_parts)

    try:
        payload = {
            "model": "deepseek-ai/DeepSeek-V3",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 2048,
        }
        resp = httpx.post(
            f"{SCILLM_URL}/v1/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {os.environ.get('SCILLM_PROXY_KEY', 'sk-dev-proxy-123')}"},
            timeout=60.0,
        )
        resp.raise_for_status()
        output = resp.json()["choices"][0]["message"]["content"].strip()

        # Parse JSON output from scillm
        try:
            return json.loads(output)
        except (json.JSONDecodeError, TypeError):
            return {"raw": output}
    except httpx.HTTPStatusError as e:
        logger.debug(f"scillm HTTP error: {e.response.status_code}")
        return {"error": f"scillm HTTP {e.response.status_code}"}
    except httpx.TimeoutException:
        return {"error": "scillm timeout (60s)"}
    except Exception as e:
        logger.error(f"scillm escalation failed: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Dispatch: auto-select task from input shape
# ---------------------------------------------------------------------------

def dispatch(input_data: Dict[str, Any], scope: str = "", registry: Dict[str, Any] = None) -> str:
    """Decide which task-specific model to use based on input shape + scope.

    Returns task name string, or empty string if no match found.
    """
    if registry is None:
        registry = load_registry()

    input_keys = set(input_data.keys()) if isinstance(input_data, dict) else set()

    # Match validators by required_fields
    for task_name, cfg in registry.get("validators", {}).items():
        sig = cfg.get("input_signature", {})
        required = set(sig.get("required_fields", []))
        if required and required.issubset(input_keys):
            # If scope preference exists, prefer matching tasks
            preferred = cfg.get("preferred_scopes", [])
            if preferred and scope and scope in preferred:
                return task_name
            if not preferred or not scope:
                return task_name

    # Scope-based fallback for validators
    if scope:
        for task_name, cfg in registry.get("validators", {}).items():
            preferred = cfg.get("preferred_scopes", [])
            if scope in preferred:
                return task_name

    return ""


# ---------------------------------------------------------------------------
# Dynamic persona routing (Shadow-LEGO unified contract)
# ---------------------------------------------------------------------------

def _auto_select_persona(
    task: str, input_data: Any, scope: str
) -> Optional[str]:
    """Select best persona scope via bridge overlap if none provided.

    Returns a scope string or None if routing is unavailable.
    """
    if scope:
        return None  # caller already specified a scope
    try:
        from common.persona_router import route_personas_for_task

        data = input_data if isinstance(input_data, dict) else {"text": str(input_data)}
        matches = route_personas_for_task(task, data, top_k=1)
        if matches:
            logger.debug(
                f"Persona routed: {matches[0].name} "
                f"(overlap={matches[0].bridge_overlap})"
            )
            return matches[0].scope
    except Exception as e:
        logger.debug(f"Persona routing unavailable: {e}")
    return None


# ---------------------------------------------------------------------------
# Core API: validate()
# ---------------------------------------------------------------------------

def validate(
    input_data: Dict[str, Any],
    task: str = "",
    scope: str = "",
    confidence_threshold: float = 0.85,
    heuristic_fn: Optional[Callable] = None,
    persona_routing: bool = False,
) -> TierResult:
    """4-tier cascade: heuristic -> classifier -> GPT -> scillm.

    Uses CascadeRunner from common.cascade for the escalation loop,
    shadow mode, and metrics logging. Domain-specific tier functions
    are assembled here based on registry configuration.

    Args:
        input_data: Task-specific input dictionary.
        task: Task name (e.g. "qra-assessor"). Auto-dispatched if empty.
        scope: Persona memory scope for context injection.
        confidence_threshold: Minimum confidence to accept a tier's result.
        heuristic_fn: Optional tier-0 function(input_data) -> dict|None.
        persona_routing: If True and no scope given, auto-select persona.

    Returns:
        TierResult with result, confidence, tier, source, latency.
    """
    start = time.time()
    registry = load_registry()

    # Auto-select persona scope if routing enabled and no scope given
    if persona_routing and not scope:
        routed = _auto_select_persona(task, input_data, scope)
        if routed:
            scope = routed

    # Auto-dispatch if no task specified
    if not task:
        task = dispatch(input_data, scope, registry)
        if not task:
            logger.warning("Could not dispatch input to any task, falling to scillm")

    # Check cache
    ck = _cache_key(input_data, task, scope)
    cached = _check_cache(ck)
    if cached is not None:
        cached.cached = True
        cached.latency_ms = (time.time() - start) * 1000
        _log_metric_cached(cached)
        return cached

    input_text = json.dumps(input_data, ensure_ascii=False)
    shadow = bool(registry.get("validators", {}).get(task, {}).get("shadow_mode", False))

    # --- Build tier list ---
    tiers: List[TierDef] = []

    # Tier 0: Heuristic
    if heuristic_fn is not None:
        def _heuristic_tier(inp, **kw):
            r = heuristic_fn(inp)
            if r is None:
                return None
            return TierResult(result=r, confidence=1.0)
        tiers.append(TierDef(tier=0, name="heuristic", fn=_heuristic_tier))

    # Tier 0.5: Classifier
    classifier_info = get_classifier(task, registry)
    if classifier_info is not None:
        model, model_type, cfg = classifier_info
        cls_threshold = cfg.get("confidence_threshold", 0.75)

        def _classifier_tier(inp, **kw):
            input_sig = cfg.get("input_signature", {})
            sig_type = input_sig.get("type", "text")

            if model_type == "sklearn" and sig_type == "tabular":
                # Tabular sklearn: transform dict -> numeric feature vector
                feat_dict = json.loads(inp) if isinstance(inp, str) else inp
                if not isinstance(feat_dict, dict):
                    return None
                feature_row = build_tabular_features(feat_dict, input_sig)
                import numpy as np
                pred_raw = model.predict(np.array([feature_row]))[0]
                proba = float(max(model.predict_proba(np.array([feature_row]))[0])) if hasattr(model, "predict_proba") else 0.5
                # Decode label
                le = cfg.get("_label_encoder")
                pred = le.inverse_transform([pred_raw])[0] if le is not None else str(pred_raw)
            elif model_type == "sklearn":
                text = json.dumps(inp, ensure_ascii=False) if isinstance(inp, dict) else str(inp)
                pred = model.predict([text])[0]
                proba = float(max(model.predict_proba([text])[0])) if hasattr(model, "predict_proba") else 0.5
            elif model_type == "distilbert":
                text = json.dumps(inp, ensure_ascii=False) if isinstance(inp, dict) else str(inp)
                out = model(text[:512])[0]
                pred, proba = out["label"], out["score"]
            elif model_type == "distilbert-multilabel":
                text = json.dumps(inp, ensure_ascii=False) if isinstance(inp, dict) else str(inp)
                tags, _, proba = _multilabel_threshold(model(text[:512]), cfg)
                pred = ",".join(tags) if tags else ""
            else:
                return None
            return TierResult(
                result={"prediction": pred, "raw_confidence": proba},
                confidence=proba,
            )
        tiers.append(TierDef(
            tier=0.5, name="classifier", fn=_classifier_tier,
            threshold=cls_threshold, shadow_mode=shadow,
        ))

    # Tier 1.5: GPT (via create-gpt Router)
    # Sensei Cascade enforcement: every production classifier MUST have
    # an associated GPT rationale. Warn loudly if missing.
    gpt_router = get_gpt_router(task, registry)
    if gpt_router is None and classifier_info is not None and not shadow:
        logger.warning(
            f"SENSEI CASCADE GAP: classifier '{task}' is production "
            f"(shadow_mode=false) but has NO GPT rationale. "
            f"Cascade skips T1.5 → falls through to T2 scillm (expensive). "
            f"Train a rationale GPT via /create-gpt."
        )
    if gpt_router is not None:
        validator_cfg = registry.get("validators", {}).get(task, {})
        effective_threshold = validator_cfg.get("confidence_threshold", confidence_threshold)

        def _gpt_tier(inp, **kw):
            mem_ctx = _inject_memory_context(inp, kw.get("scope", ""))
            if mem_ctx and isinstance(inp, dict):
                inp["memory_context"] = mem_ctx
            tier_result = gpt_router.route(inp)
            r = tier_result.result if isinstance(tier_result.result, dict) else {"output": tier_result.result}
            return TierResult(result=r, confidence=tier_result.confidence, source=tier_result.source)
        tiers.append(TierDef(
            tier=1.5, name="gpt", fn=_gpt_tier,
            threshold=effective_threshold, shadow_mode=shadow,
        ))

    # Tier 2: scillm (authoritative teacher)
    def _scillm_tier(inp, **kw):
        text = json.dumps(inp, ensure_ascii=False) if isinstance(inp, dict) else str(inp)
        mem_ctx = _inject_memory_context(inp, kw.get("scope", "")) if kw.get("scope") else ""
        scillm_result = _scillm_escalate(text, kw.get("task", ""), system_context=mem_ctx)
        # Error from scillm → skip this tier (return None)
        if "error" in scillm_result:
            logger.error(f"scillm escalation failed: {scillm_result['error']}")
            return None
        return TierResult(result=scillm_result, confidence=1.0)
    tiers.append(TierDef(tier=2, name="scillm", fn=_scillm_tier, is_teacher=True))

    # --- Run cascade ---
    runner = CascadeRunner(
        tiers=tiers,
        shadow_file=SHADOW_FILE,
        metrics_file=METRICS_FILE,
    )
    result = runner.run(
        input_data, task=task, scope=scope,
        input_hash=ck,
    )
    _store_cache(ck, result)
    return result


# ---------------------------------------------------------------------------
# Core API: classify()
# Tier-building logic lives in classify_tiers.py (kept under 800-line limit).
# ---------------------------------------------------------------------------

def classify(
    text: str,
    task: str = "",
    scope: str = "",
    confidence_threshold: float = 0.80,
    heuristic_fn: Optional[Callable] = None,
    persona_routing: bool = False,
) -> TierResult:
    """3-tier cascade for classification with dual Heart/Mind support.

    For taxonomy-related tasks (mind-tagger, heart-tagger, tactical-tagger),
    BOTH dimensions are always run independently and their results merged into
    a single TierResult.  The result dict contains ``mind`` and ``heart`` keys
    with their respective tag lists.

    For non-taxonomy tasks, a single cascade is run (original behaviour).
    Tier-building is delegated to classify_tiers.build_classify_tiers().

    Args:
        text: Text to classify.
        task: Classifier task name. When empty or a taxonomy tagger task, both
              mind and heart taggers are run.
        scope: Persona memory scope for context injection.
        confidence_threshold: Minimum confidence to accept classifier result.
        heuristic_fn: Optional tier-0 function(text) -> str|None.
        persona_routing: If True and no scope given, auto-select persona.

    Returns:
        TierResult. For dual taxonomy runs, result dict has {"mind", "heart"}.
    """
    start = time.time()
    registry = load_registry()

    if persona_routing and not scope:
        routed = _auto_select_persona(task, {"text": text}, scope)
        if routed:
            scope = routed

    # Resolve which tasks to run. Taxonomy tasks always return both dimensions.
    tasks_to_run = resolve_taxonomy_taggers(scope, task, registry)

    def _run_one(t_task: str) -> TierResult:
        ck = _cache_key({"text": text}, t_task, scope)
        cached = _check_cache(ck)
        if cached is not None:
            cached.cached = True
            cached.latency_ms = (time.time() - start) * 1000
            _log_metric_cached(cached)
            return cached
        tiers, _shadow, _has_sc = build_classify_tiers(
            task=t_task,
            classifier_info=get_classifier(t_task, registry),
            task_prompts=_TASK_PROMPTS,
            scillm_fn=_scillm_escalate,
            memory_fn=_inject_memory_context,
            multilabel_threshold_fn=_multilabel_threshold,
            build_tabular_features_fn=build_tabular_features,
            confidence_threshold=confidence_threshold,
            heuristic_fn=heuristic_fn,
            shadow_file=SHADOW_FILE,
            metrics_file=METRICS_FILE,
        )
        return run_classify_cascade(
            text=text, task=t_task, scope=scope, tiers=tiers,
            cache_key=ck, shadow_file=SHADOW_FILE, metrics_file=METRICS_FILE,
            cache_fn=_check_cache, store_cache_fn=_store_cache,
        )

    if len(tasks_to_run) == 1:
        return _run_one(tasks_to_run[0])

    # Dual path: run mind-tagger and heart-tagger, merge into one TierResult.
    mind_result = _run_one(tasks_to_run[0])   # "mind-tagger"
    heart_result = _run_one(tasks_to_run[1])  # "heart-tagger"

    mind_tags = (mind_result.result or {}).get("tags", [])
    if not mind_tags and mind_result.prediction:
        mind_tags = [t for t in mind_result.prediction.split(",") if t]

    heart_tags = (heart_result.result or {}).get("tags", [])
    if not heart_tags and heart_result.prediction:
        heart_tags = [t for t in heart_result.prediction.split(",") if t]

    merged_confidence = (mind_result.confidence + heart_result.confidence) / 2
    merged_prediction = f"mind:{','.join(mind_tags)}|heart:{','.join(heart_tags)}"
    return TierResult(
        prediction=merged_prediction,
        confidence=merged_confidence,
        result={"mind": mind_tags, "heart": heart_tags},
        tier=max(mind_result.tier, heart_result.tier),
        source="dual-taxonomy",
        latency_ms=(time.time() - start) * 1000,
    )


# ---------------------------------------------------------------------------
# AssistantRouter: high-level orchestrator
# ---------------------------------------------------------------------------

class AssistantRouter:
    """Routes requests through the 4-tier cascade per task+scope.

    Composes Router (from create-gpt) for GPT inference and
    ConfidenceRouter (from create-classifier) for classifier inference,
    adding memory scope injection on top.
    """

    def __init__(self, registry_path: Path = REGISTRY_PATH):
        self._registry = load_registry(registry_path)

    def route(
        self,
        input_data: Dict[str, Any],
        task: str = "",
        scope: str = "",
        heuristic_fn: Optional[Callable] = None,
    ) -> GatewayResult:
        """Route input through the full cascade.

        If task is explicit, route directly to that model.
        If task is None/empty, dispatch() selects based on input shape.
        """
        return validate(
            input_data=input_data,
            task=task,
            scope=scope,
            heuristic_fn=heuristic_fn,
        )

    def route_classify(
        self,
        text: str,
        task: str = "",
        scope: str = "",
    ) -> ClassifyResult:
        """Route classification through the cascade."""
        return classify(text=text, task=task, scope=scope)

    def dispatch(self, input_data: Dict[str, Any], scope: str = "") -> str:
        """Auto-select task based on input shape + scope."""
        return dispatch(input_data, scope, self._registry)

    def status(self) -> Dict[str, Any]:
        """Return status of registered models and loaded state."""
        return {
            "validators": {
                task: {
                    "loaded": task in _cache.gpt_routers,
                    **cfg,
                }
                for task, cfg in self._registry.get("validators", {}).items()
            },
            "classifiers": {
                task: {
                    "loaded": task in _cache.classifiers,
                    **cfg,
                }
                for task, cfg in self._registry.get("classifiers", {}).items()
            },
            "cache_size": len(_cache.results),
            "metrics_file": str(METRICS_FILE),
        }
