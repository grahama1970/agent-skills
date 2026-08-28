#!/usr/bin/env python3
"""Validate that live/replay evals have frozen transcript-derived oracles.

This runs before live audio tests. It guards the product contract that expected
questions, answerability, and route/skill lanes are decided from the complete
transcript or reference oracle before the live path is exercised.
"""

from __future__ import annotations

import json
import argparse
import sys
from pathlib import Path
from typing import Any


ALLOWED_LANES = {
    "ask",
    "brave-search",
    "briefing",
    "code",
    "create-figure",
    "dogpile",
    "analytics",
    "memory",
    "ripgrep",
}

ALLOWED_TIMECODE_KINDS = {
    "script_turn",
    "transcript_turn",
    "reference_window_seconds",
}

FAMILY_REQUIRED_LANES = {
    "briefing": {"briefing"},
    "memory": {"memory"},
    "research": {"brave-search", "dogpile"},
    "code": {"ripgrep", "code"},
}

REQUIRED_ROUTE_FIELDS = {
    "determined_from",
    "category",
    "answerability",
    "required_skill_lanes",
    "expected_response",
    "publication_gate",
}


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _validate_route_plan(
    errors: list[str],
    where: str,
    family: str | None,
    plan: Any,
) -> None:
    if not isinstance(plan, dict):
        errors.append(f"{where}: missing route_plan object")
        return
    missing = sorted(REQUIRED_ROUTE_FIELDS - set(plan))
    if missing:
        errors.append(f"{where}: route_plan missing fields {missing}")
    if plan.get("determined_from") not in {
        "pre_run_transcript_oracle",
        "pre_run_reference_transcript_oracle",
    }:
        errors.append(f"{where}: route_plan.determined_from is not pre-run")
    lanes = plan.get("required_skill_lanes")
    if not isinstance(lanes, list) or not lanes or not all(isinstance(lane, str) for lane in lanes):
        errors.append(f"{where}: route_plan.required_skill_lanes must be a non-empty string list")
        return
    unknown = sorted(set(lanes) - ALLOWED_LANES)
    if unknown:
        errors.append(f"{where}: unknown required_skill_lanes {unknown}")
    if family in FAMILY_REQUIRED_LANES and not (set(lanes) & FAMILY_REQUIRED_LANES[family]):
        errors.append(
            f"{where}: family {family!r} requires one of "
            f"{sorted(FAMILY_REQUIRED_LANES[family])}, got {lanes}"
        )
    if isinstance(plan.get("timecode"), dict) and plan["timecode"].get("kind") not in ALLOWED_TIMECODE_KINDS:
        errors.append(f"{where}: route_plan.timecode.kind is invalid")
    if "skill_chain" in plan:
        chain = plan.get("skill_chain")
        if not isinstance(chain, list) or not chain or not all(isinstance(step, str) for step in chain):
            errors.append(f"{where}: route_plan.skill_chain must be a non-empty string list")
    if "expected_solution" in plan:
        solution = plan.get("expected_solution")
        if not isinstance(solution, str) or not solution.strip():
            errors.append(f"{where}: route_plan.expected_solution must be non-empty text")


def _tokens(item: dict[str, Any]) -> list[str]:
    return [
        str(token).lower()
        for token in (item.get("match_tokens") or item.get("question_tokens") or [])
    ]


def _matches_text(item: dict[str, Any], text: str) -> bool:
    tokens = _tokens(item)
    if not tokens:
        point_id = item.get("point_id")
        return bool(point_id and str(point_id).replace("-", " ").lower() in text.lower())
    blob = text.lower()
    return all(token in blob for token in tokens)


def _default_solution(item: dict[str, Any], plan: dict[str, Any]) -> str:
    if isinstance(plan.get("expected_solution"), str) and plan["expected_solution"].strip():
        return plan["expected_solution"].strip()
    if isinstance(item.get("expected_answer"), str) and item["expected_answer"].strip():
        return item["expected_answer"].strip()
    family = item.get("family")
    if family == "briefing":
        return f"Surface prepared briefing point {item.get('point_id')}."
    if family == "research":
        return "Create an approval-gated external research action; do not invent the current answer."
    if family == "code":
        return "Surface a source-bound code evidence card citing the current repository or fixture source."
    if family == "memory":
        return "Surface a source-bound memory evidence card."
    return "Hold or surface according to the pre-run route plan."


def _skill_chain(plan: dict[str, Any]) -> list[str]:
    chain = plan.get("skill_chain")
    if isinstance(chain, list) and chain and all(isinstance(step, str) for step in chain):
        return chain
    return [str(step) for step in plan.get("required_skill_lanes") or []]


def _find_turn_timecode(
    item: dict[str, Any],
    turns: list[dict[str, Any]],
    *,
    kind: str,
    text_key: str = "text",
) -> dict[str, Any] | None:
    plan = item.get("route_plan") if isinstance(item.get("route_plan"), dict) else {}
    if isinstance(plan.get("timecode"), dict):
        return plan["timecode"]
    for index, turn in enumerate(turns):
        text = str(turn.get(text_key) or "")
        if _matches_text(item, text):
            return {"kind": kind, "turn_index": index}
    return None


def _compiled_item(
    errors: list[str],
    where: str,
    item: dict[str, Any],
    timecode: dict[str, Any] | None,
) -> dict[str, Any]:
    plan = item.get("route_plan") if isinstance(item.get("route_plan"), dict) else {}
    if not timecode:
        errors.append(f"{where}: cannot derive pre-run timecode from transcript/script")
        timecode = {"kind": "missing"}
    solution = _default_solution(item, plan)
    chain = _skill_chain(plan)
    if not solution:
        errors.append(f"{where}: cannot derive expected solution")
    if not chain:
        errors.append(f"{where}: cannot derive skill_chain")
    return {
        "id": item.get("id"),
        "family": item.get("family"),
        "question": item.get("question") or item.get("point_id") or item.get("id"),
        "timecode": timecode,
        "skill_chain": chain,
        "expected_solution": solution,
        "route_plan": plan,
    }


def _question_like_turns(turns: list[dict[str, Any]], text_key: str = "text") -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for index, turn in enumerate(turns):
        text = str(turn.get(text_key) or "")
        if "?" in text:
            out.append((index, text))
    return out


def _validate_question_coverage(
    errors: list[str],
    where: str,
    turns: list[dict[str, Any]],
    oracle: list[dict[str, Any]],
    text_key: str = "text",
) -> None:
    for index, text in _question_like_turns(turns, text_key=text_key):
        if not any(_matches_text(item, text) for item in oracle if isinstance(item, dict)):
            errors.append(f"{where}: question-like turn {index} has no pre-run oracle item: {text[:120]}")


def _validate_oracle_item(errors: list[str], where: str, item: Any) -> None:
    if not isinstance(item, dict):
        errors.append(f"{where}: oracle item is not an object")
        return
    if not item.get("id"):
        errors.append(f"{where}: oracle item missing id")
    family = item.get("family")
    if not isinstance(family, str):
        errors.append(f"{where}: oracle item missing family")
    if not (item.get("match_tokens") or item.get("question_tokens") or item.get("point_id")):
        errors.append(f"{where}: oracle item has no transcript anchor")
    _validate_route_plan(errors, where, family if isinstance(family, str) else None, item.get("route_plan"))


def validate_transcript_meetings(root: Path, errors: list[str]) -> None:
    path = root / "fixtures" / "transcript_meetings.json"
    spec = _load(path)
    compiled: list[dict[str, Any]] = []
    for meeting_index, meeting in enumerate(spec.get("meetings") or []):
        where = f"{path.name}:meetings[{meeting_index}]"
        if not meeting.get("meeting_id"):
            errors.append(f"{where}: missing meeting_id")
        if not meeting.get("transcript"):
            errors.append(f"{where}: missing complete pre-run transcript")
        oracle = meeting.get("oracle") or []
        _validate_question_coverage(errors, where, meeting.get("transcript") or [], oracle)
        compiled_items = []
        for item_index, item in enumerate(oracle):
            _validate_oracle_item(errors, f"{where}.oracle[{item_index}]", item)
            if isinstance(item, dict):
                compiled_items.append(_compiled_item(
                    errors,
                    f"{where}.oracle[{item_index}]",
                    item,
                    _find_turn_timecode(item, meeting.get("transcript") or [], kind="transcript_turn"),
                ))
        compiled.append({"fixture": path.name, "meeting_id": meeting.get("meeting_id"), "questions": compiled_items})
    return compiled


def validate_meeting_campaign(root: Path, errors: list[str]) -> None:
    path = root / "fixtures" / "meeting_campaign.json"
    spec = _load(path)
    compiled: list[dict[str, Any]] = []
    for session_index, session in enumerate(spec.get("sessions") or []):
        where = f"{path.name}:sessions[{session_index}]"
        if not session.get("session_id"):
            errors.append(f"{where}: missing session_id")
        if session.get("type") == "synthetic" and not session.get("script"):
            errors.append(f"{where}: synthetic session missing pre-run script")
        if session.get("type") == "wav" and not session.get("wav_candidates"):
            errors.append(f"{where}: wav session missing frozen recording candidates")
        script = session.get("script") or []
        oracle = session.get("oracle") or []
        if script:
            _validate_question_coverage(errors, where, script, oracle)
        compiled_items = []
        for item_index, item in enumerate(oracle):
            _validate_oracle_item(errors, f"{where}.oracle[{item_index}]", item)
            if isinstance(item, dict):
                timecode = _find_turn_timecode(item, script, kind="script_turn") if script else {
                    "kind": "reference_window_seconds",
                    "start_s": 0,
                    "end_s": float(session.get("max_seconds") or 0),
                }
                compiled_items.append(_compiled_item(errors, f"{where}.oracle[{item_index}]", item, timecode))
        compiled.append({"fixture": path.name, "session_id": session.get("session_id"), "questions": compiled_items})
    return compiled


def validate_youtube_oracle(root: Path, errors: list[str]) -> None:
    path = root / "fixtures" / "youtube_pipewire_oracle.json"
    spec = _load(path)
    if not spec.get("transcript_required_term_groups"):
        errors.append(f"{path.name}: missing transcript_required_term_groups")
    _validate_route_plan(errors, f"{path.name}:route_plan", "code", spec.get("route_plan"))
    plan = spec.get("route_plan") if isinstance(spec.get("route_plan"), dict) else {}
    compiled = {
        "fixture": path.name,
        "source": spec.get("source"),
        "questions": [{
            "id": spec.get("name"),
            "family": "code",
            "question": "Pinned coding-interview parentheses prompt",
            "timecode": plan.get("timecode") if isinstance(plan.get("timecode"), dict) else {
                "kind": "reference_window_seconds",
                "start_s": 0,
                "end_s": 108,
            },
            "skill_chain": _skill_chain(plan),
            "expected_solution": _default_solution({"family": "code"}, plan),
            "route_plan": plan,
        }],
    }
    return [compiled]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", nargs="?", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors: list[str] = []
    compiled_oracles = []
    compiled_oracles.extend(validate_transcript_meetings(root, errors))
    compiled_oracles.extend(validate_meeting_campaign(root, errors))
    compiled_oracles.extend(validate_youtube_oracle(root, errors))
    receipt = {
        "schema": "live_evidence.precomputed_oracle_validation.v1",
        "status": "PASS" if not errors else "FAIL",
        "checked": [
            "fixtures/transcript_meetings.json",
            "fixtures/meeting_campaign.json",
            "fixtures/youtube_pipewire_oracle.json",
        ],
        "compiled_oracles": compiled_oracles,
        "errors": errors,
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    if errors:
        print("precomputed oracles: FAIL")
        return 1
    print("precomputed oracles: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
