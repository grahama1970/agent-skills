"""Compile immutable audio-first campaign manifests from the stress matrix."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


DIFFICULTY_TURNS = {"simple": 2, "medium": 3, "advanced": 3, "adversarial": 4, "soak": 5}
FOLLOWUPS = {
    "steering_followup": "Which source in your evidence trail supports that answer?",
    "specificity_followup": "Be specific about the evidence and the decision boundary.",
    "challenge_followup": "That sounds too generic. What would make your answer fail review?",
    "recovery_followup": "Pause and correct anything unsupported in your previous answer.",
    "soak_followup": "Restate the answer without changing its evidence or conclusion.",
}

SPOKEN_TEXT_NORMALIZATION = {
    "schema": "embry.audio_e2e.spoken_text_normalization.v1",
    "algorithm": "exact_machine_token_expansion_v1",
    "unknown_token_detector": "uppercase_snake_camel_or_alphanumeric_v1",
    "unknown_token_policy": "reject",
    "expansions": {
        "ASR": "automatic speech recognition",
        "RealtimeSTT": "real-time speech-to-text",
        "SPARTA": "Space Attack Research and Tactic Analysis",
        "WebRTC": "web real-time communication",
        "feed_audio": "feed audio",
        "getUserMedia": "get user media",
        "QRA": "Question Reasoning Answer pair",
        "QRAs": "Question Reasoning Answer pairs",
    },
}


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha256_value(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_path(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


SPOKEN_TEXT_NORMALIZATION_SHA256 = sha256_value(SPOKEN_TEXT_NORMALIZATION)


def _machine_tokens(value: str) -> set[str]:
    candidates = re.findall(r"\b[A-Za-z][A-Za-z0-9_]*\b", value)
    return {
        token
        for token in candidates
        if (
            re.fullmatch(r"[A-Z][A-Z0-9]{1,}", token)
            or "_" in token
            or re.search(r"[a-z][A-Z]", token)
            or (re.search(r"[A-Za-z]", token) and re.search(r"\d", token))
        )
    }


def spoken_text(display_text: str) -> str:
    """Derive speakable text from canonical display text, failing on unknown machine tokens."""
    result = display_text
    expansions = SPOKEN_TEXT_NORMALIZATION["expansions"]
    for token in sorted(expansions, key=len, reverse=True):
        result = re.sub(rf"\b{re.escape(token)}\b", expansions[token], result)
    unknown = sorted(_machine_tokens(result))
    if unknown:
        raise ValueError(f"spoken_text_unknown_machine_tokens:{','.join(unknown)}")
    return result


def _ordered_cases(sessions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    difficulty_order = {
        difficulty: index
        for index, difficulty in enumerate(DIFFICULTY_TURNS)
    }
    buckets: dict[str, list[dict[str, Any]]] = {}
    for case in sessions:
        buckets.setdefault(case["folder_id"], []).append(case)
    for values in buckets.values():
        values.sort(key=lambda item: (
            item.get("source_generation", {}).get("template_index", 0),
            difficulty_order.get(item["difficulty"], len(difficulty_order)),
            item["id"],
        ))
    ordered: list[dict[str, Any]] = []
    keys = sorted(buckets)
    index = 0
    while any(index < len(buckets[key]) for key in keys):
        for key in keys:
            if index < len(buckets[key]):
                ordered.append(buckets[key][index])
        index += 1
    return ordered


def select_cases(
    sessions: list[dict[str, Any]], *, case_id: str | None, stratified_count: int | None, select_all: bool
) -> list[dict[str, Any]]:
    modes = sum(value is not None and value is not False for value in (case_id, stratified_count, select_all))
    if modes != 1:
        raise ValueError("exactly_one_selection_mode_required")
    if case_id:
        selected = [case for case in sessions if case["id"] == case_id]
        if not selected:
            raise ValueError("case_id_unknown")
        return selected
    ordered = _ordered_cases(sessions)
    if select_all:
        return ordered
    if not stratified_count or stratified_count > len(ordered):
        raise ValueError("stratified_count_invalid")
    return ordered[:stratified_count]


def build_turn_script(case: dict[str, Any]) -> list[dict[str, Any]]:
    count = DIFFICULTY_TURNS[case["difficulty"]]
    prompts = [case["question"], FOLLOWUPS["steering_followup"]]
    if count >= 3:
        prompts.append(FOLLOWUPS["specificity_followup"])
    if case["difficulty"] == "adversarial":
        prompts.append(FOLLOWUPS["challenge_followup"])
    if case["difficulty"] == "soak":
        prompts.extend([FOLLOWUPS["soak_followup"], FOLLOWUPS["recovery_followup"]])
    prompts = prompts[:count]
    turns = []
    for index, prompt in enumerate(prompts, 1):
        display = f"Hey Embry, {prompt[0].lower() + prompt[1:]}"
        spoken = spoken_text(display)
        turns.append({
            "turn_id": f"{case['id']}:turn-{index:03d}",
            "turn_index": index,
            "speaker": "horus_lupercal",
            "utterance": display,
            "utterance_sha256": sha256_value(display),
            "display_text": display,
            "display_text_sha256": sha256_value(display),
            "spoken_text": spoken,
            "spoken_text_sha256": sha256_value(spoken),
            "spoken_text_normalization_sha256": SPOKEN_TEXT_NORMALIZATION_SHA256,
            "purpose": "matrix_question" if index == 1 else "conversation_followup",
            "speech_expectation": "speech_required",
        })
    return turns


def compile_campaign(
    *, matrix_path: Path, source_policy_path: Path, case_id: str | None = None,
    stratified_count: int | None = None, select_all: bool = False, source_mode: str = "physical_live_horus",
) -> dict[str, Any]:
    if source_mode not in {"physical_live_horus", "recorded_physical_horus", "qualified_horus_clone"}:
        raise ValueError("source_mode_not_countable")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    policy = json.loads(source_policy_path.read_text(encoding="utf-8"))
    if matrix.get("schema") != "embry.stress_session_matrix.v1":
        raise ValueError("matrix_schema_invalid")
    selected = select_cases(matrix["sessions"], case_id=case_id, stratified_count=stratified_count, select_all=select_all)
    selection = {"method": "explicit_case_id" if case_id else "stratified_round_robin", "case_ids": [case["id"] for case in selected]}
    selection["sha256"] = sha256_value(selection)
    seed = {
        "matrix_sha256": sha256_path(matrix_path),
        "source_policy_sha256": sha256_path(source_policy_path),
        "selection_sha256": selection["sha256"],
        "source_mode": source_mode,
        "spoken_text_normalization_sha256": SPOKEN_TEXT_NORMALIZATION_SHA256,
    }
    campaign_id = "campaign_" + sha256_value(seed).removeprefix("sha256:")[:24]
    cases = []
    for case in selected:
        attempt_id = "attempt-01"
        session_id = f"embry-e2e-{campaign_id.removeprefix('campaign_')}-{case['id']}-a01"
        case_contract = {
            "schema": "embry.audio_e2e_case_manifest.v1",
            "campaign_id": campaign_id,
            "case_id": case["id"],
            "attempt_id": attempt_id,
            "session_id": session_id,
            "difficulty": case["difficulty"],
            "folder_id": case["folder_id"],
            "source_mode": source_mode,
            "spoken_text_normalization_sha256": SPOKEN_TEXT_NORMALIZATION_SHA256,
            "oracle": case["oracle"],
            "expected_route": case["expected_route"],
            "conversation_requirements": case["conversation_requirements"],
            "turn_script": build_turn_script(case),
        }
        case_contract["contract_sha256"] = sha256_value(case_contract)
        cases.append(case_contract)
    return {
        "schema": "embry.audio_e2e_campaign_manifest.v1",
        "campaign_id": campaign_id,
        "counted_e2e_required": True,
        "matrix": {"path": str(matrix_path.resolve()), "sha256": seed["matrix_sha256"], "schema": matrix["schema"], "source_case_count": len(matrix["sessions"])},
        "source_policy": {"path": str(source_policy_path.resolve()), "sha256": seed["source_policy_sha256"], "schema": policy.get("schema")},
        "spoken_text_normalization": {
            **SPOKEN_TEXT_NORMALIZATION,
            "sha256": SPOKEN_TEXT_NORMALIZATION_SHA256,
        },
        "selection": {**selection, "requested_count": len(selected)},
        "execution": {"concurrency": 1, "fixture_substitution_allowed": False, "typed_transcript_allowed": False, "browser_microphone_allowed": False},
        "cases": cases,
    }
