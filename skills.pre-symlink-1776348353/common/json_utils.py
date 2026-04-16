"""JSON extraction and repair utilities for LLM response parsing.

Self-contained version of extractor's json_utils — no external dependencies
beyond json_repair (pip install json-repair). Used by any skill that parses
JSON from LLM responses: VLM reviewers, evidence cases, classifiers, etc.

Usage:
    from common.json_utils import extract_json, clean_json_string, parse_json

    # Extract JSON from LLM response (handles markdown fences, prose, partial JSON)
    result = extract_json(llm_response_text)

    # Parse with repair (handles trailing commas, missing quotes, etc.)
    parsed = parse_json(messy_json_string)

    # Clean LLM output to dict (handles ```json fences, mixed prose+JSON)
    data = clean_json_string(llm_output, return_dict=True)
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Union

from loguru import logger

# Optional dependency — graceful degradation if not installed
try:
    from json_repair import repair_json as _repair_json
except ImportError:
    _repair_json = None
    logger.debug("json_repair not installed — repair fallback disabled")


class PathEncoder(json.JSONEncoder):
    """Convert Path objects to strings during JSON encoding."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, Path):
            return str(obj)
        return super().default(obj)


# ── Core extraction ──────────────────────────────────────────────────


def extract_json(text: str) -> dict | list | None:
    """3-level JSON extraction from LLM response text.

    Tries in order:
    1. Parse the whole text as JSON
    2. Extract from ```json ... ``` markdown fence
    3. Find outermost { ... } or [ ... ] brace pair

    Returns None if no valid JSON found.
    """
    text = text.strip()

    # Level 1: direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Level 2: markdown fence
    fence = re.search(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", text, re.DOTALL)
    if fence:
        try:
            return json.loads(fence.group(1))
        except (json.JSONDecodeError, ValueError):
            # Try repair on fenced content
            if _repair_json:
                try:
                    repaired = _repair_json(fence.group(1), return_objects=True)
                    if isinstance(repaired, (dict, list)):
                        return repaired
                except Exception:
                    pass

    # Level 3: outermost braces
    first_obj = text.find("{")
    last_obj = text.rfind("}")
    first_arr = text.find("[")
    last_arr = text.rfind("]")

    candidates = []
    if first_obj >= 0 and last_obj > first_obj:
        candidates.append(text[first_obj : last_obj + 1])
    if first_arr >= 0 and last_arr > first_arr:
        candidates.append(text[first_arr : last_arr + 1])

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, ValueError):
            if _repair_json:
                try:
                    repaired = _repair_json(candidate, return_objects=True)
                    if isinstance(repaired, (dict, list)):
                        return repaired
                except Exception:
                    pass

    return None


def parse_json(content: str) -> dict | list | str:
    """Parse a JSON string, repairing if needed.

    Returns parsed dict/list on success, or the original string if all
    parsing attempts fail.
    """
    try:
        return json.loads(content)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try regex extraction + repair
    try:
        json_match = re.search(r"(\[.*\]|\{.*\})", content, re.DOTALL)
        if json_match:
            content = json_match.group(1)
        if _repair_json:
            repaired = _repair_json(content, return_objects=True)
            if isinstance(repaired, (dict, list)):
                return repaired
            parsed = json.loads(repaired)
            return parsed
    except (json.JSONDecodeError, ValueError, Exception) as e:
        logger.debug("JSON repair failed: {}", e)

    return content


def clean_json_string(
    content: str | dict | list,
    return_dict: bool = False,
) -> str | dict | list:
    """Clean and parse a JSON string, dict, or list.

    Handles:
    - Already-parsed dicts/lists (pass through)
    - ```json ... ``` markdown fences
    - Mixed prose + JSON output from LLMs
    - Trailing commas, missing quotes (via json_repair)

    Args:
        content: Input to clean.
        return_dict: If True, return Python dict/list. If False, return JSON string.
    """
    if isinstance(content, (dict, list)):
        return content if return_dict else json.dumps(content)

    if not isinstance(content, str):
        return content

    if not return_dict:
        return content

    # Try markdown fence extraction first
    if "json" in content.lower():
        matches = re.findall(r"```(?:json)?\s*([\s\S]*?)```", content)
        if matches:
            json_content = matches[0].strip()
            try:
                return json.loads(json_content)
            except (json.JSONDecodeError, ValueError):
                parsed = parse_json(json_content)
                if isinstance(parsed, (dict, list)):
                    return parsed

    # General parse
    parsed = parse_json(content)
    if isinstance(parsed, str):
        try:
            return json.loads(parsed)
        except Exception:
            return parsed
    return parsed


# ── Helpers ──────────────────────────────────────────────────────────


def restrict_top_level_keys(obj: dict | list, allowed: set[str]) -> dict | list:
    """Return a copy of obj with only allowed top-level keys (if dict)."""
    if isinstance(obj, dict):
        return {k: v for k, v in obj.items() if k in allowed}
    return obj


def json_serialize(data: Any, handle_paths: bool = False, **kwargs: Any) -> str:
    """Serialize data to JSON string, optionally handling Path objects."""
    cls = PathEncoder if handle_paths else None
    return json.dumps(data, cls=cls, **kwargs)


# Strict JSON guard text for LLM prompts requiring exact JSON output.
STRICT_JSON_GUARD = (
    "Return exactly one JSON object. No markdown, no code fences, no prose,"
    " no comments, no trailing commas, and do not emit NaN/Infinity (use null)."
)
