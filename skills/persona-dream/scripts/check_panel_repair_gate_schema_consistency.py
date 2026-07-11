#!/usr/bin/env python3
"""Check panel repair schema includes validator provider-required fields."""

from __future__ import annotations

import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = SCRIPT_DIR.parent / "schemas" / "panel_repair_gate_receipt.schema.json"

REQUIRED_BY_VALIDATOR = {
    "provider_media_urls",
    "media_hashes",
    "callback_or_polling_plan",
    "cost_estimate",
    "provider_voice_ids",
    "external_task_id",
    "voice_id_status",
    "provider_mode",
    "provider_resolution",
    "provider_packet_status",
    "provider_eligibility",
}

STRING_MIN_LENGTH_FIELDS = {
    "run_id",
    "panel_id",
    "requirement_matrix",
    "script_coverage_receipt",
    "post_generation_script_coverage_receipt",
    "reference_receipt",
    "generation_receipt",
    "visual_review_receipt",
    "no_overlay_receipt",
    "callback_or_polling_plan",
    "external_task_id",
    "cost_estimate",
    "provider_resolution"
}

ARRAY_MIN_ITEMS_FIELDS = {
    "provider_media_urls"
}

OBJECT_FIELDS = {
    "media_hashes",
    "provider_voice_ids"
}


def main() -> int:
    schema = json.loads(SCHEMA_PATH.read_text())
    required = set(schema.get("required", []))
    properties = schema.get("properties", {})
    missing_required = sorted(REQUIRED_BY_VALIDATOR - required)
    missing_properties = sorted(required - set(properties))
    invalid_string_fields = sorted(
        field for field in STRING_MIN_LENGTH_FIELDS
        if field in properties
        and not (
            properties[field].get("type") == "string"
            and properties[field].get("minLength", 0) >= 1
        )
    )
    invalid_array_fields = sorted(
        field for field in ARRAY_MIN_ITEMS_FIELDS
        if field in properties
        and not (
            properties[field].get("type") == "array"
            and properties[field].get("minItems", 0) >= 1
        )
    )
    invalid_object_fields = sorted(
        field for field in OBJECT_FIELDS
        if field in properties and properties[field].get("type") != "object"
    )
    failures = {
        "missing_required": missing_required,
        "missing_properties": missing_properties,
        "invalid_string_fields": invalid_string_fields,
        "invalid_array_fields": invalid_array_fields,
        "invalid_object_fields": invalid_object_fields,
    }
    if any(failures.values()):
        print(json.dumps({"status": "FAIL", **failures}, indent=2))
        return 1
    print(json.dumps({"status": "PASS", "schema": str(SCHEMA_PATH)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
