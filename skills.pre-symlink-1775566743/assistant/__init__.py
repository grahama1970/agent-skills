"""Assistant gateway package — re-exports public API from submodules."""

from .gateway import (  # noqa: F401
    AssistantRouter, ClassifyResult, GatewayResult,
    classify, dispatch, load_registry, validate,
    METRICS_FILE, REGISTRY_PATH, SHADOW_FILE,
)
from .models import ModelCache, cache  # noqa: F401
from .cli import app  # noqa: F401
from common.cascade import TierResult  # noqa: F401
