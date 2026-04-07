"""Backward-compat shim — real implementation in common/model_factory.py.

All existing imports from assistant.model_factory continue to work.
New consumers should import from common.model_factory directly.

Co-evolutionary feedback logging (Shadow-LEGO Task 10):
    Adds ``log_subgraph_feedback()`` and ``summarize_subgraph_feedback()``
    for tracking which classifier seeds produce the richest subgraphs.
    Data written to ``~/.pi/assistant/subgraph_feedback.jsonl``.

    Schema per JSONL line (SubgraphFeedbackEntry):
        timestamp           : ISO-8601 UTC timestamp
        classifier_name     : Registry key of the classifier that produced seeds
        seeds               : List of entity/seed strings sent to graph expansion
        classifier_confidence : Confidence score from the classifier (0.0-1.0)
        subgraph_qra_count  : Number of QRAs retrieved via classifier seeds
        avg_grounding       : Mean grounding score of classifier-seeded QRAs
        baseline_qra_count  : Number of QRAs retrieved via keyword baseline
        baseline_grounding  : Mean grounding score of keyword-baseline QRAs
        quality_delta       : subgraph avg_grounding - baseline_grounding
        count_delta         : subgraph qra_count - baseline qra_count
        richer              : True if classifier seeds outperformed baseline
        scope               : Optional scope tag (e.g. "brandon_bailey")
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Load the common module by spec to avoid circular import when
# sys.path contains the assistant directory.
_common_path = Path(__file__).resolve().parent.parent / "common" / "model_factory.py"
_spec = importlib.util.spec_from_file_location("_common_model_factory", _common_path)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

# Re-export all public names
ModelFactory = _mod.ModelFactory
ModelFactoryConfig = _mod.ModelFactoryConfig
TrainResult = _mod.TrainResult
EvalResult = _mod.EvalResult
SHADOW_AGREEMENT_PROMOTE = _mod.SHADOW_AGREEMENT_PROMOTE
SHADOW_AGREEMENT_RETRAIN = _mod.SHADOW_AGREEMENT_RETRAIN
SHADOW_AGREEMENT_PLATEAU = _mod.SHADOW_AGREEMENT_PLATEAU
MIN_SHADOW_SAMPLES = _mod.MIN_SHADOW_SAMPLES

# Backward compat: module-level REGISTRY_PATH
REGISTRY_PATH = _mod._default_assistant_config().registry_path


# ---------------------------------------------------------------------------
# Co-evolutionary feedback logging (Shadow-LEGO)
# Re-exported from common.subgraph_feedback for backward compatibility.
# ---------------------------------------------------------------------------

_skills_dir = str(Path(__file__).resolve().parent.parent)
if _skills_dir not in sys.path:
    sys.path.insert(0, _skills_dir)

from common.subgraph_feedback import (  # noqa: E402
    SubgraphFeedbackEntry,
    log_subgraph_feedback,
    summarize_subgraph_feedback,
)
from common.paths import SUBGRAPH_FEEDBACK_FILE  # noqa: E402
