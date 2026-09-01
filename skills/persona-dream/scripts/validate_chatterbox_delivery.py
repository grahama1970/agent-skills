#!/usr/bin/env python3
"""validate_chatterbox_delivery - scripts.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _ratio(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--run-root", required=True)
    parser.add_argument("--reuse-issue24-gates", action="store_true")
    parser.add_argument("--reuse-issue25-gates", action="store_true")
    parser.add_argument("--forbid-literal-tag-words", action="store_true")
    parser.add_argument("--live-artifacts", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    run_root = Path(args.run_root)
    metrics_path = run_root / "chatterbox_delivery.metrics.json"
    delivery_path = metrics_path if metrics_path.exists() else run_root / "chatterbox_delivery.json"
    failures: list[str] = []
    if not delivery_path.exists():
        failures.append("missing_chatterbox_delivery")
        delivery = {}
    else:
        delivery = json.loads(delivery_path.read_text(encoding="utf-8"))

    mapping = manifest["mood_to_chatterbox_mapping"]
    control_open = (delivery.get("control") or {}).get("opening_anchor") or {}
    treatment_open = (delivery.get("treatment") or {}).get("opening_anchor") or {}
    treatment_close = (delivery.get("treatment") or {}).get("closing_anchor") or {}
    control_close = (delivery.get("control") or {}).get("closing_anchor") or control_open

    duration_ratio = _ratio(float(treatment_open.get("duration_ms") or 0), float(control_open.get("duration_ms") or 0))
    speech_rate_ratio = _ratio(float(treatment_open.get("speech_rate_wps") or 0), float(control_open.get("speech_rate_wps") or 0))
    closing_ratio = _ratio(float(treatment_close.get("duration_ms") or 0), float(control_close.get("duration_ms") or 0))

    if duration_ratio < float(mapping["minimum_opening_duration_ratio"]):
        failures.append("opening_duration_ratio_too_low")
    if speech_rate_ratio > float(mapping["maximum_opening_speech_rate_ratio"]):
        failures.append("opening_speech_rate_ratio_too_high")
    low, high = mapping["closing_duration_ratio_range"]
    if not (float(low) <= closing_ratio <= float(high)):
        failures.append("closing_duration_not_returned_to_control")
    if args.forbid_literal_tag_words and int(treatment_open.get("literal_tag_token_count") or 0) != 0:
        failures.append("literal_native_tag_word_in_asr")
    if args.reuse_issue24_gates and not treatment_open.get("issue24_tag_event_pass"):
        failures.append("issue24_tag_event_gate_failed")
    if args.reuse_issue25_gates and not treatment_open.get("issue25_pace_effect_pass"):
        failures.append("issue25_pace_gate_failed")
    if "valence" in str(delivery.get("observed_effect_channels") or []):
        failures.append("valence_reported_as_observed_effect")

    receipt = {
        "schema": "persona_dream.chatterbox_delivery_validation.v1",
        "status": "PASS_CHATTERBOX_DELIVERY" if not failures else "FAIL_CHATTERBOX_DELIVERY",
        "run_root": args.run_root,
        "metrics": str(delivery_path),
        "duration_ratio": round(duration_ratio, 6),
        "speech_rate_ratio": round(speech_rate_ratio, 6),
        "closing_duration_ratio": round(closing_ratio, 6),
        "failures": failures,
        "mocked": False,
        "live": bool(args.live_artifacts),
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
