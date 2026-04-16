#!/usr/bin/env python3
"""Shared GPT + classifier inference gateway for persona monitor tasks.

This file is a backward-compatible facade. The implementation has been
split into submodules:

  - models.py:   Model cache, lazy loading, tabular feature transform
  - gateway.py:  Core API (validate, classify, dispatch, AssistantRouter)
  - cli.py:      Typer CLI commands

4-tier cascade:
  Tier 0:   Heuristic (regex/keyword/schema)      free, microseconds
  Tier 0.5: Classifier (DistilBERT/MiniLM)        free, 5-25ms
  Tier 1.5: Shared GPT (Qwen3-0.6B GGUF)          free, ~200ms
  Tier 2:   scillm (DeepSeek V3.2 via Chutes)      $0.12/1K, 2-5s

Usage:
    from assistant import validate, classify

    result = validate({"question": "...", "answer": "..."}, task="qra-assessor")
    result = classify("satellite vulnerability assessment", task="bridge-tagger")

CLI:
    python assistant.py validate --task qra-assessor --input '{"question":"..."}'
    python assistant.py classify --task bridge-tagger --text "satellite vulnerability"
    python assistant.py status
    python assistant.py self-test
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the skills directory is on sys.path for common.cascade imports
SKILL_DIR = Path(__file__).resolve().parent
SKILLS_DIR = SKILL_DIR.parent
if str(SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(SKILLS_DIR))

# dotenv: load .env BEFORE any os.environ / os.getenv calls
try:
    from dotenv import find_dotenv, load_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
    _root_env = SKILLS_DIR.parent / ".env"
    if _root_env.exists():
        load_dotenv(_root_env, override=False)
except ImportError:
    pass  # python-dotenv not installed; rely on parent env

# Re-export everything from submodules for backward compatibility.
# Supports both package imports (from assistant.assistant import X) and
# direct execution (python assistant.py).
from common.cascade import TierResult, TierDef, CascadeRunner, ShadowEntry  # noqa: F401

try:
    # Package mode: imported as assistant.assistant
    from .models import (  # noqa: F401
        ModelCache,
        cache,
        get_gpt_router,
        get_classifier,
        build_tabular_features,
        CACHE_TTL_HOURS,
    )
    from .gateway import (  # noqa: F401
        AssistantRouter,
        ClassifyResult,
        GatewayResult,
        classify,
        dispatch,
        load_registry,
        validate,
        METRICS_FILE,
        METRICS_DIR,
        REGISTRY_PATH,
        SHADOW_FILE,
    )
    from .cli import app  # noqa: F401
except ImportError:
    # Direct execution mode: python assistant.py
    from models import (  # noqa: F401  # type: ignore[no-redef]
        ModelCache,
        cache,
        get_gpt_router,
        get_classifier,
        build_tabular_features,
        CACHE_TTL_HOURS,
    )
    from gateway import (  # noqa: F401  # type: ignore[no-redef]
        AssistantRouter,
        ClassifyResult,
        GatewayResult,
        classify,
        dispatch,
        load_registry,
        validate,
        METRICS_FILE,
        METRICS_DIR,
        REGISTRY_PATH,
        SHADOW_FILE,
    )
    from cli import app  # noqa: F401  # type: ignore[no-redef]

# Backward-compatible aliases for internal names that were module-level
_ModelCache = ModelCache
_cache = cache
_get_gpt_router = get_gpt_router
_get_classifier = get_classifier
_build_tabular_features = build_tabular_features


if __name__ == "__main__":
    app()
