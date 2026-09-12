"""Strict JSON helpers for Battle envelope files.

Reject duplicate object keys and JSON non-finite constants before normal decoding
can collapse them into ambiguous Python values.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: set[str] = set()
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError(f"duplicate JSON key: {key}")
        seen.add(key)
        out[key] = value
    return out


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")


def loads(text: str) -> Any:
    return json.loads(text, object_pairs_hook=_no_duplicates, parse_constant=_reject_constant)


def load_path(path: str | Path) -> Any:
    return loads(Path(path).read_text(encoding="utf-8"))


def finite_json_values(value: Any) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(finite_json_values(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and finite_json_values(item) for key, item in value.items())
    return True
