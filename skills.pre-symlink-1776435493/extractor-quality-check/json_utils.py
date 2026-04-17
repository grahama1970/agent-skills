"""JSON parsing utilities for CLI output that may contain non-JSON text.

Provides safe JSON extraction with json_repair fallback, matching the pattern
used in the extractor pipeline's json_utils.parse_json.
"""
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

try:
    from json_repair import repair_json as _repair_json
    _HAS_JSON_REPAIR = True
except ImportError:
    _HAS_JSON_REPAIR = False


def parse_json_safe(raw: str) -> Any:
    """Parse JSON from CLI output that may have warnings/text before the JSON.

    Uses json_repair as fallback (same pattern as extractor json_utils.parse_json).
    """
    if not raw or not raw.strip():
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # Extract JSON object/array region
    match = re.search(r"(\{.*\}|\[.*\])", raw, re.DOTALL)
    if match:
        extracted = match.group(1)
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass
        if _HAS_JSON_REPAIR:
            try:
                repaired = _repair_json(extracted, return_objects=True)
                if isinstance(repaired, (dict, list)):
                    return repaired
            except Exception as e:
                logger.debug("extraction failed: {}", e)
    return None
