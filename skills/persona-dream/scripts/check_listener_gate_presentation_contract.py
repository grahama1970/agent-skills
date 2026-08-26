#!/usr/bin/env python3
"""Regression guard for the Persona Dream human listener handoff."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STUDY_DIR = ROOT / "reports/goal_v5/continuity/blinded_listener_study"


def fail(message: str) -> None:
    print(f"LISTENER_GATE_PRESENTATION_CONTRACT_FAIL {message}", file=sys.stderr)
    raise SystemExit(1)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"missing_json={path.relative_to(ROOT)}")
    except json.JSONDecodeError as exc:
        fail(f"invalid_json={path.relative_to(ROOT)} error={exc}")


def require_text(path: Path, needles: list[str]) -> None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fail(f"missing_text={path.relative_to(ROOT)}")
    lowered = re.sub(r"\s+", " ", text.lower())
    missing = [needle for needle in needles if needle.lower() not in lowered]
    if missing:
        fail(
            "missing_skill_contract_phrases="
            + ",".join(missing)
            + f" path={path.relative_to(ROOT)}"
        )


def count_jsonl_rows(path: Path) -> int:
    if not path.exists():
        fail(f"missing_responses_file={path.relative_to(ROOT)}")
    rows = 0
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"invalid_response_jsonl line={line_no} error={exc}")
        rows += 1
    return rows


def main() -> int:
    require_text(
        ROOT / "SKILL.md",
        [
            "Human listener gate protocol",
            "agent-owned next action",
            "surface the existing rater packet",
            "four blinded WAV files",
            "responses_v2.jsonl",
            "WebGPT may review instructions",
            "diagnose broken artifacts",
            "cannot supply human listener responses",
        ],
    )

    status = read_json(ROOT / "CURRENT_STATUS.json")
    readiness = (
        status.get("continuity_state", {})
        .get("latest_blinded_listener_study_readiness", {})
    )
    analysis = (
        status.get("continuity_state", {})
        .get("latest_blinded_listener_study_analysis", {})
    )
    if readiness.get("status") != "PASS_BLINDED_LISTENER_STUDY_READY_FOR_HUMAN_RATERS":
        fail(f"unexpected_readiness_status={readiness.get('status')!r}")
    if readiness.get("rater_page") != (
        "skills/persona-dream/reports/goal_v5/continuity/"
        "blinded_listener_study/rater_page.html"
    ):
        fail(f"unexpected_rater_page={readiness.get('rater_page')!r}")
    if readiness.get("human_collection_permitted") is not True:
        fail("human_collection_permitted_not_true")
    if analysis.get("status") != "BLOCKED_BLINDED_LISTENER_STUDY_ANALYSIS":
        fail(f"unexpected_analysis_status={analysis.get('status')!r}")
    failed_gates = set(analysis.get("failed_gates") or [])
    expected_gates = {"human_responses_complete", "signed_human_interpretation_missing"}
    if not expected_gates.issubset(failed_gates):
        fail(f"analysis_missing_failed_gates={sorted(expected_gates - failed_gates)}")

    rater_page = STUDY_DIR / "rater_page.html"
    if not rater_page.is_file():
        fail(f"missing_rater_page={rater_page.relative_to(ROOT)}")
    stimuli = sorted((STUDY_DIR / "blinded_stimuli").glob("S*.wav"))
    stimulus_names = [path.name for path in stimuli]
    if stimulus_names != ["S01.wav", "S02.wav", "S03.wav", "S04.wav"]:
        fail(f"unexpected_stimuli={stimulus_names!r}")
    zero_byte = [path.name for path in stimuli if path.stat().st_size <= 0]
    if zero_byte:
        fail(f"zero_byte_stimuli={zero_byte!r}")

    response_rows = count_jsonl_rows(STUDY_DIR / "responses_v2.jsonl")
    signed = (STUDY_DIR / "SIGNED_INTERPRETATION.json").exists()

    print(
        "LISTENER_GATE_PRESENTATION_CONTRACT_OK "
        f"stimuli={len(stimuli)} responses={response_rows} "
        f"signed_interpretation={str(signed).lower()} "
        "next_action=present_rater_packet"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
