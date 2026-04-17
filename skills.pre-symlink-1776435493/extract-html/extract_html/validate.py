"""validate - extract_html.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

import jsonschema
from loguru import logger


def validate_or_errors(schema: Dict[str, Any], instance: Any) -> tuple[bool, list[dict[str, Any]]]:
    """
    Validates instance against schema.
    Returns (True, []) if valid.
    Returns (False, [errors]) if invalid.
    """
    validator = jsonschema.Draft202012Validator(schema)
    errors = []
    
    for e in validator.iter_errors(instance):
        entry = {
            "message": e.message,
            "path": "".join(f"[{repr(p)}]" for p in e.path),
            "schema_path": "".join(f"[{repr(p)}]" for p in e.schema_path),
        }
        errors.append(entry)
        
    if not errors:
        return True, []
        
    return False, errors
