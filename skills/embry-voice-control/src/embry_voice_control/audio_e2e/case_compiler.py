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


# --- Per-tone emotional prosody injection -----------------------------------
#
# The synthesized case-audio path renders the operator's spoken turns through
# the Orpheus ``horus_orpheus_lora_v2_identity_plus_emotions`` checkpoint. That
# LoRA was trained with a fixed inline emotion-tag vocabulary (8 paralinguistic
# tags); no other tags are honored by the checkpoint. Anything outside this set
# would be spoken literally instead of rendered as prosody, so the mapping below
# is confined to that trained vocabulary rather than the matrix's descriptive
# ``suggested_inline_emotion_tags`` (e.g. ``[measured]``), which Orpheus does
# not understand. The descriptive suggestions are retained per family only as an
# audit cross-reference.
#
# Each of the 9 matrix tone families is mapped to a deterministic (tag,
# placement) delivery so every family renders with a DISTINCT emotional prosody
# instead of tonally-neutral speech. With 8 tags for 9 families the single
# unavoidable tag reuse (``<sigh>``) is disambiguated by placement.
ORPHEUS_EMOTION_TAG_VOCABULARY = (
    "laugh",
    "chuckle",
    "sigh",
    "cough",
    "sniffle",
    "groan",
    "yawn",
    "gasp",
)

TONE_PROSODY_MAP = {
    "schema": "embry.audio_e2e.tone_prosody_map.v1",
    "render_backend": "orpheus_tts",
    "checkpoint": "horus_orpheus_lora_v2_identity_plus_emotions",
    "orpheus_emotion_tag_vocabulary": [
        f"<{tag}>" for tag in ORPHEUS_EMOTION_TAG_VOCABULARY
    ],
    "tag_injection": "inline_within_query_after_wake_phrase",
    "families": {
        "calm_precise": {
            "orpheus_tags": ["<sigh>"],
            "placement": "leading",
            "delivery": "measured_calm_exhale",
            "matrix_suggested_tags": ["[measured]", "[short pause]"],
        },
        "curious_searching": {
            "orpheus_tags": ["<gasp>"],
            "placement": "leading",
            "delivery": "bright_inquisitive_intake",
            "matrix_suggested_tags": ["[thinking]", "[brief pause]"],
        },
        "firm_boundary": {
            "orpheus_tags": ["<cough>"],
            "placement": "leading",
            "delivery": "assertive_throat_clear_boundary",
            "matrix_suggested_tags": ["[firm]", "[brief pause]"],
        },
        "memory_confident": {
            "orpheus_tags": ["<chuckle>"],
            "placement": "leading",
            "delivery": "warm_confident_recall",
            "matrix_suggested_tags": ["[warmly]", "[soft pause]"],
        },
        "careful_concerned": {
            "orpheus_tags": ["<sniffle>"],
            "placement": "leading",
            "delivery": "concerned_careful_breath",
            "matrix_suggested_tags": ["[listening]", "[steady pause]"],
        },
        "memory_uncertain": {
            "orpheus_tags": ["<groan>"],
            "placement": "leading",
            "delivery": "effortful_uncertain_recall",
            "matrix_suggested_tags": ["[careful]", "[small pause]"],
        },
        "serious_low_energy": {
            "orpheus_tags": ["<yawn>"],
            "placement": "leading",
            "delivery": "low_energy_serious_weight",
            "matrix_suggested_tags": ["[focused]", "[measured pause]"],
        },
        "dynamic_intent_selected": {
            "orpheus_tags": ["<laugh>"],
            "placement": "leading",
            "delivery": "expressive_dynamic_shift",
            "matrix_suggested_tags": ["[breath]", "[tone shift]"],
        },
        "identity_clarification": {
            "orpheus_tags": ["<sigh>"],
            "placement": "trailing",
            "delivery": "gentle_patient_clarifying_exhale",
            "matrix_suggested_tags": ["[gently]", "[questioning pause]"],
        },
    },
}
TONE_PROSODY_MAP_SHA256 = sha256_value(TONE_PROSODY_MAP)

_WAKE_PREFIX = re.compile(r"^\s*hey[\s,;:!?.\-]+embry\b[\s,;:!?.\-]+", re.IGNORECASE)


def tone_family_for_case(case: dict[str, Any]) -> str:
    """Return the required tone family for a matrix case, validated against the map."""
    requirements = case.get("conversation_requirements") or {}
    family = requirements.get("required_tone_family")
    if family not in TONE_PROSODY_MAP["families"]:
        raise ValueError(f"tone_family_unsupported:{family!r}")
    return str(family)


def apply_tone_tags(
    spoken_text_value: str, tone_family: str, *, minimum_tag_count: int = 1
) -> str:
    """Inject the family's Orpheus emotion tag(s) into the query, after the wake phrase.

    The wake phrase ("Hey Embry, ...") is preserved verbatim so wakeword
    detection is unaffected; tags are placed only inside the spoken query. The
    plain input text is never mutated for WER purposes -- this returns a
    synthesis-only variant. Tags are stripped again by the ASR WER normalizer.
    """
    family = TONE_PROSODY_MAP["families"].get(tone_family)
    if family is None:
        raise ValueError(f"tone_family_unsupported:{tone_family!r}")
    tags = list(family["orpheus_tags"])
    minimum_tag_count = int(minimum_tag_count)
    if len(tags) < minimum_tag_count:
        raise ValueError(
            "tone_family_tag_count_below_minimum:"
            f"{tone_family}:{len(tags)}:{minimum_tag_count}"
        )
    match = _WAKE_PREFIX.match(spoken_text_value)
    if match is None:
        raise ValueError("tone_injection_requires_leading_wake_phrase")
    prefix = spoken_text_value[: match.end()]
    query = spoken_text_value[match.end() :].strip()
    if not query:
        raise ValueError("tone_injection_query_empty")
    tag_str = " ".join(tags)
    placement = family["placement"]
    if placement == "leading":
        return f"{prefix}{tag_str} {query}"
    if placement == "trailing":
        return f"{prefix}{query} {tag_str}"
    raise ValueError(f"tone_placement_invalid:{placement}")


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
    tone_family = tone_family_for_case(case)
    family_map = TONE_PROSODY_MAP["families"][tone_family]
    requirements = case.get("conversation_requirements") or {}
    minimum_tag_count = int(requirements.get("minimum_inline_emotion_tag_count", 1) or 1)
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
        synthesis_spoken = apply_tone_tags(
            spoken, tone_family, minimum_tag_count=minimum_tag_count
        )
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
            "tone_family": tone_family,
            "tone_prosody_map_sha256": TONE_PROSODY_MAP_SHA256,
            "inline_emotion_tags": list(family_map["orpheus_tags"]),
            "inline_emotion_tag_count": len(family_map["orpheus_tags"]),
            "minimum_inline_emotion_tag_count": minimum_tag_count,
            "synthesis_spoken_text": synthesis_spoken,
            "synthesis_spoken_text_sha256": sha256_value(synthesis_spoken),
            "purpose": "matrix_question" if index == 1 else "conversation_followup",
            "speech_expectation": "speech_required",
        })
    return turns


def compile_campaign(
    *, matrix_path: Path, source_policy_path: Path, case_id: str | None = None,
    stratified_count: int | None = None, select_all: bool = False, source_mode: str = "physical_live_horus",
    attempt: int = 1,
) -> dict[str, Any]:
    if source_mode not in {"physical_live_horus", "recorded_physical_horus", "qualified_horus_clone"}:
        raise ValueError("source_mode_not_countable")
    if attempt < 1 or attempt > 99:
        raise ValueError("attempt_out_of_range")
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
        "tone_prosody_map_sha256": TONE_PROSODY_MAP_SHA256,
    }
    campaign_id = "campaign_" + sha256_value(seed).removeprefix("sha256:")[:24]
    cases = []
    for case in selected:
        attempt_id = f"attempt-{attempt:02d}"
        session_id = f"embry-e2e-{campaign_id.removeprefix('campaign_')}-{case['id']}-a{attempt:02d}"
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
        "tone_prosody_map": {
            **TONE_PROSODY_MAP,
            "sha256": TONE_PROSODY_MAP_SHA256,
        },
        "selection": {**selection, "requested_count": len(selected)},
        "execution": {"concurrency": 1, "fixture_substitution_allowed": False, "typed_transcript_allowed": False, "browser_microphone_allowed": False},
        "cases": cases,
    }
