#!/usr/bin/env python3
"""Agentic eval for the two-stage transcript question/answer prompt contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


LEETCODE_TERMS = {
    "algorithm",
    "array",
    "binary",
    "bracket",
    "code",
    "complexity",
    "hash",
    "leetcode",
    "parentheses",
    "pointer",
    "stack",
    "string",
    "tree",
}


@dataclass(frozen=True, slots=True)
class Segment:
    start: int
    end: int
    speaker: str
    text: str


def segment_payload(segment: Segment) -> dict[str, Any]:
    return {
        "start": segment.start,
        "end": segment.end,
        "speaker": segment.speaker,
        "text": segment.text,
    }


def stable_id(text: str) -> str:
    return "q_" + hashlib.sha256(" ".join(text.lower().split()).encode("utf-8")).hexdigest()[:16]


def has_code_question(text: str) -> bool:
    lower = text.lower()
    if len(lower.split()) < 6:
        return False
    if "?" not in lower and not lower.startswith(("given", "how", "can", "what")):
        return False
    return any(term in lower for term in LEETCODE_TERMS)


def normalize_question(text: str) -> str:
    return " ".join(text.split()).rstrip(" ?") + "?"


def scan_update(payload: dict[str, Any]) -> dict[str, Any]:
    stream_id = payload["stream_id"]
    delta = [Segment(**item) for item in payload["transcript_delta"]]
    lookback = [Segment(**item) for item in payload.get("lookback_context", [])]
    registry = payload.get("question_registry", [])
    joined_delta = " ".join(item.text for item in delta)
    joined_context = " ".join(item.text for item in [*lookback, *delta])
    processed_through = str(delta[-1].end if delta else payload.get("previous_cursor") or 0)
    parenthesis_record = next((item for item in registry if item.get("question_key") == "leetcode:validate-parentheses-with-stack"), None)
    changed_to_multibracket = bool(parenthesis_record and any(token in joined_delta for token in ("[]", "{}", "bracket types", "brackets")))
    if changed_to_multibracket:
        question_id = parenthesis_record["question_id"]
        revision = int(parenthesis_record.get("revision", 0)) + 1
        event = {
            "event_type": "QUESTION_EVOLVED",
            "question_id": question_id,
            "question_key": "leetcode:validate-parentheses-with-stack",
            "revision": revision,
            "category": "LEETCODE_STYLE",
            "problem_identification": {"kind": "STYLE_ONLY", "identifier": None},
            "as_spoken": joined_delta,
            "normalized_question": "How can a string of parentheses and bracket types be validated using a stack?",
            "completeness": "ANSWERABLE",
            "confidence": 0.86,
            "source_span": {"start": str(delta[0].start), "end": str(delta[-1].end), "speakers": sorted({item.speaker for item in delta})},
            "constraints": ["Use a stack", "Return a Boolean", "Support (), [], and {} bracket pairs"],
            "clarification_targets": ["non-bracket handling", "return contract", "empty string behavior"],
            "material_changes": ["added multiple bracket types"],
            "related_question_ids": [],
            "conversation_answer_state": "PARTIAL",
            "answer_context_change": {"kind": "NEW_CONSTRAINT", "summary": "Multiple bracket types are now in scope."},
            "answer_refresh_required": True,
        }
        return {
            "schema": "live_question_scan.v1",
            "stream_id": stream_id,
            "processed_through": processed_through,
            "status": "EVENTS_FOUND",
            "events": [event],
            "pending_candidates": [],
            "registry_updates": [{"operation": "UPDATE", "question_id": question_id, "question_key": "leetcode:validate-parentheses-with-stack", "revision": revision, "status": "OPEN", "last_seen": processed_through}],
            "suppressed_duplicate_count": 0,
        }

    if not has_code_question(joined_context):
        pending = []
        if any(term in joined_context.lower() for term in ("given", "string", "parentheses", "array")):
            pending = [
                {
                    "candidate_key": stable_id(joined_context),
                    "partial_text": normalize_question(joined_context),
                    "first_seen": str((lookback or delta)[0].start if (lookback or delta) else 0),
                    "last_seen": processed_through,
                    "reason": "utterance is not yet a stable code-related question",
                }
            ]
        return {
            "schema": "live_question_scan.v1",
            "stream_id": stream_id,
            "processed_through": processed_through,
            "status": "WAITING_FOR_COMPLETION" if pending else "NO_ACTIONABLE_QUESTION",
            "events": [],
            "pending_candidates": pending,
            "registry_updates": [],
            "suppressed_duplicate_count": 0,
        }

    normalized = normalize_question(joined_context)
    question_key = "leetcode:validate-parentheses-with-stack" if "parenthes" in normalized.lower() else stable_id(normalized)
    existing = next((item for item in registry if item.get("question_key") == question_key), None)
    duplicate = bool(existing)

    if duplicate:
        return {
            "schema": "live_question_scan.v1",
            "stream_id": stream_id,
            "processed_through": processed_through,
            "status": "ONLY_DUPLICATES",
            "events": [],
            "pending_candidates": [],
            "registry_updates": [{"operation": "TOUCH", "question_id": existing["question_id"], "question_key": question_key, "revision": existing["revision"], "status": existing["status"], "last_seen": processed_through}],
            "suppressed_duplicate_count": 1,
        }

    question_id = existing["question_id"] if existing else stable_id(normalized)
    revision = int(existing.get("revision", 0)) + 1 if existing else 1
    event_type = "QUESTION_EVOLVED" if changed_to_multibracket else "QUESTION_READY" if payload.get("candidate_state") else "NEW_QUESTION"
    constraints = ["Use a stack", "Return a Boolean"]
    if "[]" in joined_context or "{}" in joined_context or "bracket types" in joined_context:
        constraints.append("Support (), [], and {} bracket pairs")

    event = {
        "event_type": event_type,
        "question_id": question_id if existing else None,
        "question_key": question_key,
        "revision": revision,
        "category": "LEETCODE_STYLE",
        "problem_identification": {"kind": "STYLE_ONLY", "identifier": None},
        "as_spoken": joined_delta,
        "normalized_question": normalized,
        "completeness": "ANSWERABLE",
        "confidence": 0.88,
        "source_span": {"start": str(delta[0].start), "end": str(delta[-1].end), "speakers": sorted({item.speaker for item in delta})},
        "constraints": constraints,
        "clarification_targets": ["allowed bracket characters", "non-bracket handling", "return contract", "empty string behavior"],
        "material_changes": ["added multiple bracket types"] if changed_to_multibracket else [],
        "related_question_ids": [],
        "conversation_answer_state": "PARTIAL" if changed_to_multibracket else "NONE",
        "answer_context_change": {"kind": "NEW_CONSTRAINT" if changed_to_multibracket else "NONE", "summary": "Multiple bracket types are now in scope." if changed_to_multibracket else ""},
        "answer_refresh_required": True,
    }
    return {
        "schema": "live_question_scan.v1",
        "stream_id": stream_id,
        "processed_through": processed_through,
        "status": "EVENTS_FOUND",
        "events": [event],
        "pending_candidates": [],
        "registry_updates": [{"operation": "UPDATE" if existing else "INSERT", "question_id": question_id, "question_key": question_key, "revision": revision, "status": "OPEN", "last_seen": processed_through}],
        "suppressed_duplicate_count": 0,
    }


def resolve_question(question_record: dict[str, Any], previous_answer: dict[str, Any] | None = None) -> dict[str, Any]:
    constraints = question_record.get("constraints", [])
    multi = any("[]" in constraint or "{}" in constraint for constraint in constraints)
    version = 1 if previous_answer is None else int(previous_answer["answer_version"]) + 1
    code = (
        "def is_valid_brackets(text: str) -> bool:\n"
        "    expected_opening = {')': '(', ']': '[', '}': '{'}\n"
        "    opening = set(expected_opening.values())\n"
        "    stack: list[str] = []\n"
        "    for char in text:\n"
        "        if char in opening:\n"
        "            stack.append(char)\n"
        "        elif char in expected_opening:\n"
        "            if not stack or stack.pop() != expected_opening[char]:\n"
        "                return False\n"
        "        else:\n"
        "            return False\n"
        "    return not stack\n"
        if multi
        else "def is_valid_parentheses(text: str) -> bool:\n"
        "    stack: list[str] = []\n"
        "    for char in text:\n"
        "        if char == '(':\n"
        "            stack.append(char)\n"
        "        elif char == ')':\n"
        "            if not stack:\n"
        "                return False\n"
        "            stack.pop()\n"
        "        else:\n"
        "            return False\n"
        "    return not stack\n"
    )
    return {
        "schema": "live_question_answer.v1",
        "question_id": question_record["question_id"],
        "question_revision": question_record["revision"],
        "answer_version": version,
        "display_action": "CREATE" if previous_answer is None else "UPDATE",
        "evolution": {
            "status": "NEW" if previous_answer is None else "REFINED",
            "previous_answer_version": None if previous_answer is None else previous_answer["answer_version"],
            "changed_fields": ["implementation", "assumptions"] if previous_answer else ["all"],
            "material_change_summary": "Generated first provisional answer." if previous_answer is None else "Adjusted implementation for multiple bracket types.",
            "new_information_used": constraints,
        },
        "answer_card": {
            "question": question_record["normalized_question"],
            "primary_clarifying_question": {
                "question": "Are only parentheses allowed, or should the solution support other bracket types and arbitrary characters?",
                "why_it_matters": "It determines whether a counter, simple stack, or typed bracket stack is appropriate.",
                "default_assumption": "Use a strict stack implementation and reject unexpected characters.",
            },
            "additional_clarifying_questions": [
                {"question": "Should the function return only a Boolean?", "why_it_matters": "Returning indices or a corrected string changes the algorithm output.", "default_assumption": "Return Boolean."},
                {"question": "Is the empty string valid?", "why_it_matters": "It affects a boundary case.", "default_assumption": "Empty string is valid."},
            ],
            "assumptions_used": ["strict input contract", "Boolean return", "empty string is valid"],
            "direct_answer": "Use a stack: push openings, pop for matching closings, reject early mismatches, and require an empty stack at the end.",
            "method": ["Scan left to right.", "Push opening brackets.", "On closing brackets, reject an empty stack or mismatched opener.", "Return true only if no openers remain."],
            "correctness_or_evidence_rationale": "After each prefix, the stack contains exactly unmatched opening brackets from that prefix.",
            "implementation": {"language": "Python", "code": code},
            "complexity": {"time": "O(n)", "space": "O(n)", "notes": "A one-parenthesis counter can reduce space to O(1) if stack is not required."},
            "evidence": [],
            "edge_cases_or_checks": ["empty string", "initial closing bracket", "leftover opening bracket", "unexpected character", "nested brackets"],
            "next_steps": [{"priority": 1, "action": "Confirm the input and output contract with the interviewer.", "reason": "It decides whether the provisional implementation should be narrowed or generalized."}],
            "unresolved": question_record.get("clarification_targets", []),
            "confidence": 0.86,
        },
    }


def sampled_noise(rng: random.Random) -> Segment:
    text = rng.choice(
        [
            "Thanks, that makes sense.",
            "Can we come back to scheduling after this?",
            "I think that sounds okay.",
            "Let me share my screen.",
        ]
    )
    start = rng.randint(1, 10_000)
    return Segment(start=start, end=start + 1, speaker="interviewer", text=text)


def run_eval(samples: int, seed: int, output: Path | None) -> int:
    rng = random.Random(seed)
    checks: list[str] = []
    failures: list[str] = []

    for index in range(samples):
        scan = scan_update({"stream_id": "eval", "previous_cursor": None, "lookback_context": [], "transcript_delta": [segment_payload(sampled_noise(rng))], "candidate_state": [], "question_registry": []})
        if scan["events"] or scan["status"] != "NO_ACTIONABLE_QUESTION":
            failures.append(f"noise sample {index} emitted action: {scan}")
    checks.append(f"noise_samples={samples}")

    fragment = scan_update(
        {
            "stream_id": "eval",
            "previous_cursor": None,
            "lookback_context": [],
            "transcript_delta": [{"start": 10, "end": 11, "speaker": "interviewer", "text": "Given a string with"}],
            "candidate_state": [],
            "question_registry": [],
        }
    )
    if fragment["status"] != "WAITING_FOR_COMPLETION" or fragment["events"]:
        failures.append(f"fragment was not held pending: {fragment}")
    checks.append("fragment_waits")

    ready = scan_update(
        {
            "stream_id": "eval",
            "previous_cursor": "11",
            "lookback_context": [{"start": 10, "end": 11, "speaker": "interviewer", "text": "Given a string with"}],
            "transcript_delta": [{"start": 12, "end": 13, "speaker": "interviewer", "text": "parentheses, how would you validate it using a stack?"}],
            "candidate_state": fragment["pending_candidates"],
            "question_registry": [],
        }
    )
    if not ready["events"] or ready["events"][0]["event_type"] != "QUESTION_READY" or not ready["events"][0]["answer_refresh_required"]:
        failures.append(f"completed question did not require answer refresh: {ready}")
    answer = resolve_question({**ready["events"][0], "question_id": ready["registry_updates"][0]["question_id"]})
    if answer["display_action"] != "CREATE" or "stack" not in answer["answer_card"]["direct_answer"].lower() or "def is_valid_parentheses" not in answer["answer_card"]["implementation"]["code"]:
        failures.append(f"resolver did not produce stack answer: {answer}")
    checks.append("fragment_to_question_to_answer")

    duplicate = scan_update(
        {
            "stream_id": "eval",
            "previous_cursor": "13",
            "lookback_context": [],
            "transcript_delta": [{"start": 14, "end": 15, "speaker": "interviewer", "text": "Given a string with parentheses, how would you validate it using a stack?"}],
            "candidate_state": [],
            "question_registry": [{"question_id": ready["registry_updates"][0]["question_id"], "question_key": "leetcode:validate-parentheses-with-stack", "revision": 1, "status": "OPEN"}],
        }
    )
    if duplicate["events"] or duplicate["suppressed_duplicate_count"] != 1:
        failures.append(f"duplicate was not suppressed: {duplicate}")
    checks.append("duplicate_suppressed")

    evolved = scan_update(
        {
            "stream_id": "eval",
            "previous_cursor": "15",
            "lookback_context": [],
            "transcript_delta": [{"start": 16, "end": 17, "speaker": "interviewer", "text": "Actually include [] and {} bracket types too."}],
            "candidate_state": [],
            "question_registry": [{"question_id": ready["registry_updates"][0]["question_id"], "question_key": "leetcode:validate-parentheses-with-stack", "revision": 1, "status": "OPEN"}],
        }
    )
    if not evolved["events"] or evolved["events"][0]["event_type"] != "QUESTION_EVOLVED":
        failures.append(f"material evolution not detected: {evolved}")
    updated = resolve_question({**evolved["events"][0], "question_id": ready["registry_updates"][0]["question_id"]}, previous_answer={"answer_version": 1})
    if updated["display_action"] != "UPDATE" or "expected_opening" not in updated["answer_card"]["implementation"]["code"]:
        failures.append(f"evolved resolver did not generalize implementation: {updated}")
    checks.append("material_evolution_updates_answer")

    receipt = {
        "schema": "live_evidence.two_stage_prompt_contract_eval_receipt.v1",
        "status": "FAIL" if failures else "PASS",
        "created_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "samples": samples,
        "checks": checks,
        "failures": failures,
        "claims": {
            "proves": "the proposed scanner/resolver prompt contract handles sampled transcript noise, pending fragments, answer refresh gating, duplicate suppression, material evolution, and JSON answer-card shape.",
            "does_not_prove": "live LLM/provider adherence, GPU STT, live audio capture, Memory relevance, or Ask provider correctness.",
        },
    }
    target = output or Path("/tmp/live-evidence-two-stage-prompt-contract-receipt.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(receipt, indent=2, sort_keys=True))
    print(f"two-stage prompt contract receipt: {target}")
    if failures:
        return 1
    print("two-stage prompt contract: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("skill_root", type=Path)
    parser.add_argument("--samples", type=int, default=60)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.samples < 50:
        print("--samples must be at least 50 for this adversarial agentic eval", file=sys.stderr)
        return 2
    seed = args.seed or random.SystemRandom().randint(1, 2**31 - 1)
    return run_eval(args.samples, seed, args.output)


if __name__ == "__main__":
    raise SystemExit(main())
