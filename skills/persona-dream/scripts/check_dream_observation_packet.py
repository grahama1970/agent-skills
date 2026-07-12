#!/usr/bin/env python3
"""Validate one Persona Dream observation packet and its evidence boundaries."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from write_dream_observation_packet import read_object, validate_packet


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    packet = read_object(args.packet)
    errors = validate_packet(packet)
    if packet.get("fixture_backed") is True:
        for key in ("provider_returned", "persona_watched_provider_dream", "psychological_interpretation_performed"):
            if packet.get(key) is not False:
                errors.append(f"fixture packet requires {key}=false")
    receipt = {
        "schema": "persona_dream.dream_observation_packet_check_receipt.v1",
        "status": "PASS_DREAM_OBSERVATION_CONTRACT_FIXTURE" if not errors else "BLOCKED_DREAM_OBSERVATION_CONTRACT",
        "packet": str(args.packet.resolve()),
        "errors": errors,
        "mocked": "no",
        "live": "yes",
        "provider_live": "no",
        "actual_provider_call_attempts": 0,
    }
    print(json.dumps(receipt, indent=2, sort_keys=True) if args.json else receipt["status"])
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
