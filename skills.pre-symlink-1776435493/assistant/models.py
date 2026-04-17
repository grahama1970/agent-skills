"""Model loading, caching, and feature transformation for the assistant gateway.

Handles lazy-loading of GPT routers (from create-gpt) and classifiers
(sklearn, DistilBERT, SetFit) with an in-memory cache. Also provides
tabular feature transformation for sklearn models that expect numeric
input vectors.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict

from loguru import logger

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent
CREATE_GPT_DIR = SKILLS_DIR / "create-gpt"

# ---------------------------------------------------------------------------
# Lazy model loading + caching (encapsulated state)
# ---------------------------------------------------------------------------

CACHE_TTL_HOURS = 24


@dataclass
class ModelCache:
    """Encapsulates mutable caches instead of module-level globals."""
    gpt_routers: Dict[str, Any] = field(default_factory=dict)
    classifiers: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, tuple] = field(default_factory=dict)  # key -> (result, expiry_ts)


# Singleton cache instance shared across the gateway
cache = ModelCache()


def get_gpt_router(task: str, registry: Dict[str, Any], _cache: ModelCache = cache):
    """Lazy-load GPT router from create-gpt infrastructure."""
    if task in _cache.gpt_routers:
        return _cache.gpt_routers[task]

    validator_cfg = registry.get("validators", {}).get(task)
    if not validator_cfg:
        return None

    try:
        sys.path.insert(0, str(CREATE_GPT_DIR / "scripts"))
        from router import Router, RouterConfig

        model_path_str = validator_cfg.get("gpt_model_path", "")
        model_path = Path(model_path_str).expanduser() if model_path_str else None

        config = RouterConfig(
            task_name=validator_cfg.get("task_spec", task),
            confidence_threshold=validator_cfg.get("confidence_threshold", 0.85),
            model_path=model_path,
        )
        router = Router(config)
        _cache.gpt_routers[task] = router
        logger.info(f"Loaded GPT router for task={task}")
        return router
    except Exception as e:
        logger.warning(f"Failed to load GPT router for task={task}: {e}")
        return None


def get_classifier(task: str, registry: Dict[str, Any], _cache: ModelCache = cache):
    """Lazy-load classifier from create-classifier infrastructure."""
    if task in _cache.classifiers:
        return _cache.classifiers[task]

    classifier_cfg = registry.get("classifiers", {}).get(task)
    if not classifier_cfg:
        return None

    model_path = Path(classifier_cfg.get("model_path", "")).expanduser()
    model_type = classifier_cfg.get("type", "sklearn")

    if not model_path.exists():
        logger.debug(f"Classifier model not found at {model_path} for task={task}")
        return None

    try:
        if model_type == "sklearn":
            import joblib
            model = joblib.load(model_path)
            # Load label encoder if specified
            le_path = classifier_cfg.get("label_encoder_path")
            if le_path:
                le_path = Path(le_path).expanduser()
                if le_path.exists():
                    classifier_cfg["_label_encoder"] = joblib.load(le_path)
                    logger.debug(f"Loaded label encoder for task={task}")
        elif model_type == "distilbert":
            from transformers import pipeline
            model = pipeline("text-classification", model=str(model_path))
        elif model_type == "distilbert-multilabel":
            from transformers import pipeline
            model = pipeline(
                "text-classification",
                model=str(model_path),
                top_k=None,  # Return all labels with scores
            )
        elif model_type == "setfit":
            from setfit import SetFitModel
            model = SetFitModel.from_pretrained(str(model_path))
        else:
            logger.warning(f"Unknown classifier type: {model_type}")
            return None

        _cache.classifiers[task] = (model, model_type, classifier_cfg)
        logger.info(f"Loaded classifier for task={task} (type={model_type})")
        return _cache.classifiers[task]
    except Exception as e:
        logger.debug(f"Failed to load classifier for task={task}: {e}")
        return None


# ---------------------------------------------------------------------------
# Tabular feature transform for sklearn models
# ---------------------------------------------------------------------------

def build_tabular_features(feat_dict: Dict[str, Any], input_sig: Dict) -> list:
    """Transform a dict of named features into a numeric vector for sklearn.

    Uses the input_signature from model_registry.json to:
    1. One-hot encode categorical fields (table_style, domain)
    2. Map feature_cols to numeric values with defaults
    3. Encode category as int
    """
    one_hot_maps = input_sig.get("one_hot_maps", {})
    feature_cols = input_sig.get("feature_cols", [])
    cat_values = input_sig.get("category_values", ["unknown"])
    defaults = input_sig.get("default_values", {})

    row: list = []

    # One-hot encode mapped fields first
    for field_name, categories in one_hot_maps.items():
        val = feat_dict.get(field_name, "unknown")
        for cat in categories:
            row.append(1 if val == cat else 0)

    # Remaining feature_cols (skip ones already one-hot encoded)
    one_hot_cols = set()
    for field_name, categories in one_hot_maps.items():
        for cat in categories:
            one_hot_cols.add(f"{field_name}_{cat}")

    for col in feature_cols:
        if col in one_hot_cols:
            continue
        # Check defaults using prefix matching
        default = 0
        for pattern, dval in defaults.items():
            if pattern.endswith("*") and col.startswith(pattern[:-1]):
                default = dval
                break
            elif col == pattern:
                default = dval
                break
        row.append(feat_dict.get(col, default))

    # Category encoding
    cat_val = feat_dict.get("category", "unknown")
    cat_encoder = {c: i for i, c in enumerate(cat_values)}
    row.append(cat_encoder.get(cat_val, 0))

    return row
