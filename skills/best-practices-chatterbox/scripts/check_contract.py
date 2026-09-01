#!/usr/bin/env python3
"""Validate the Chatterbox best-practices guidance contract."""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"


@dataclass(frozen=True, slots=True)
class Requirement:
    key: str
    needle: str
    reason: str


REQUIREMENTS = [
    Requirement("frontmatter_name", "name: best-practices-chatterbox", "skill has canonical name"),
    Requirement("python_compliance", "best-practices-python", "skill declares Python compliance"),
    Requirement("skills_compliance", "best-practices-skills", "skill declares skill compliance"),
    Requirement("memory_route", "$memory recall", "agents must ground text in memory context"),
    Requirement("analyzer_route", "analyze-chatterbox-emotions", "agents must run voice-quality analysis"),
    Requirement("spaced_ellipsis", "bottle rocket ... a room", "skill documents spaced ellipsis pause syntax"),
    Requirement("collect_herself", "[sniff] [sniff] ... give me a second", "skill documents collect-herself cue"),
    Requirement("render_chunks", "render_chunks", "skill requires caller-owned chunks"),
    Requirement("pause_after_ms", "pause_after_ms", "skill requires exact silence field"),
    Requirement("intensity", "\"intensity\": 0.72", "skill shows intensity in JSON"),
    Requirement("turbo_boundary", "Turbo ignores `exaggeration` and `cfg_weight`", "skill states local Turbo knob boundary"),
    Requirement("preprocess_cli", "./run.sh preprocess", "skill documents deterministic text preprocessing"),
    Requirement("pause_token", "[pause:750ms]", "skill documents explicit pause tokens"),
    Requirement("ssml_conversion", "<break time=\"800ms\"/>", "skill documents bounded SSML conversion"),
    Requirement("sweep_plan", "./run.sh sweep-plan", "skill documents backend-aware parameter sweeps"),
    Requirement("reference_gate", "./run.sh check-reference", "skill documents reference-audio validation"),
    Requirement("streaming_boundary", "Streaming boundary", "skill states service-layer streaming boundary"),
]


def evaluate(text: str) -> dict:
    checks = {req.key: req.needle in text for req in REQUIREMENTS}
    missing = [req.key for req in REQUIREMENTS if not checks[req.key]]
    return {
        "schema": "best_practices_chatterbox.contract_check.v1",
        "skill": "best-practices-chatterbox",
        "path": str(SKILL),
        "checks": checks,
        "missing": missing,
        "pass": not missing,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path)
    ap.add_argument("--expect-fail", action="store_true", help="invert result for adversarial fixture probes")
    args = ap.parse_args()
    text = SKILL.read_text(encoding="utf-8") if SKILL.is_file() else ""
    result = evaluate(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.expect_fail:
        print("PASS_EXPECT_FAIL_PROBE" if result["pass"] else "EXPECTED_FAILURE_DETECTED")
        return 1 if result["pass"] else 0
    print(json.dumps(result, indent=2, sort_keys=True))
    print("PASS_BEST_PRACTICES_CHATTERBOX_CONTRACT" if result["pass"] else "FAIL_BEST_PRACTICES_CHATTERBOX_CONTRACT")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
