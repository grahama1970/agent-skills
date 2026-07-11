#!/usr/bin/env python3
"""Validate persona-dream panel entity/environment interaction ledgers.

This is intentionally stricter than a prose review. If a panel mentions or
requires a character, prop, surface, creature, weather force, or environment
element, that element must have explicit interaction fields and a gate status.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REQUIRED_ELEMENT_FIELDS = (
    "id",
    "category",
    "mentioned_or_required",
    "environment_interaction",
    "motion_or_state_change",
    "material_or_body_response",
    "sound_or_silence",
    "script_evidence",
    "visual_support_status",
    "gate_status",
)

PASS_STATUSES = {"PASS"}


def _load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # pragma: no cover - CLI guard
        raise SystemExit(f"failed_to_read_json: {path}: {exc}") from exc


def validate(data: dict[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    panels = data.get("panels")
    if not isinstance(panels, list) or not panels:
        failures.append({"scope": "ledger", "reason": "missing_panels"})
        panels = []

    for panel in panels:
        panel_id = panel.get("panel")
        elements = panel.get("elements")
        if not isinstance(elements, list) or not elements:
            failures.append(
                {"panel": panel_id, "scope": "panel", "reason": "missing_elements"}
            )
            continue

        for element in elements:
            missing = [
                field
                for field in REQUIRED_ELEMENT_FIELDS
                if element.get(field) in (None, "", [], {})
            ]
            if missing:
                failures.append(
                    {
                        "panel": panel_id,
                        "element": element.get("id", "UNKNOWN"),
                        "reason": "missing_required_fields",
                        "fields": missing,
                    }
                )
            if element.get("gate_status") not in PASS_STATUSES:
                failures.append(
                    {
                        "panel": panel_id,
                        "element": element.get("id", "UNKNOWN"),
                        "reason": "element_gate_not_pass",
                        "gate_status": element.get("gate_status"),
                        "visual_support_status": element.get("visual_support_status"),
                    }
                )

        panel_status = panel.get("panel_gate_status")
        if panel_status not in PASS_STATUSES:
            failures.append(
                {
                    "panel": panel_id,
                    "scope": "panel",
                    "reason": "panel_gate_not_pass",
                    "panel_gate_status": panel_status,
                }
            )

    verdict = "PASS" if not failures else "FAIL"
    return {
        "schema": "persona_dream.panel_interaction_gate_receipt.v1",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "panel_count": len(panels),
        "failure_count": len(failures),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("ledger", type=Path)
    parser.add_argument("--receipt-out", type=Path)
    args = parser.parse_args()

    receipt = validate(_load_json(args.ledger))
    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    return 0 if receipt["verdict"] == "PASS" else 2


if __name__ == "__main__":
    sys.exit(main())
