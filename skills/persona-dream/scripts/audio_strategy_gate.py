#!/usr/bin/env python3
"""Fail-closed audio strategy coherence for Persona Dream video runs."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

VOICE_HANDOFF_SCHEMA = "persona_dream.voice_handoff_plan.v1"
VOICE_HANDOFF_RELATIVE = Path("phase_11_submit_return/preflight/voice_handoff_plan.json")
ALLOWED_STRATEGIES = {"post_mux", "kling_native", "kling_custom_voice"}
ACTION_DESCRIPTION_MARKERS = ("action description", "stage direction", "narration only")
NEAR_SILENT_DNA_MARKERS = ("near-silent", "near silent", "at most one")


@dataclass(frozen=True)
class SpokenLine:
    speaker: str
    text: str
    start_s: float | None = None
    end_s: float | None = None


@dataclass(frozen=True)
class AudioStrategyAssessment:
    classification: str
    spoken_lines: tuple[SpokenLine, ...]
    dialogue_style: str | None
    delivery_mode: str | None
    voice_handoff_present: bool
    voice_handoff_valid: bool
    voice_handoff_path: str | None = None
    validation_errors: tuple[str, ...] = field(default_factory=tuple)
    blockers: tuple[str, ...] = field(default_factory=tuple)

    @property
    def requires_audible_delivery(self) -> bool:
        return self.classification in {"NEAR_SILENT_VOICED", "VOICED"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "classification": self.classification,
            "spoken_lines": [line.__dict__ for line in self.spoken_lines],
            "dialogue_style": self.dialogue_style,
            "delivery_mode": self.delivery_mode,
            "voice_handoff_present": self.voice_handoff_present,
            "voice_handoff_valid": self.voice_handoff_valid,
            "voice_handoff_path": self.voice_handoff_path,
            "validation_errors": list(self.validation_errors),
            "requires_audible_delivery": self.requires_audible_delivery,
            "blockers": list(self.blockers),
        }


def _read_json(path: Path) -> Any:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _dialogue_style(script_dna: Mapping[str, Any] | None) -> str | None:
    if not isinstance(script_dna, Mapping):
        return None
    payload = script_dna.get("script_dna")
    if isinstance(payload, Mapping) and payload.get("dialogue_style"):
        return str(payload["dialogue_style"])
    if script_dna.get("dialogue_style"):
        return str(script_dna["dialogue_style"])
    return None


def _maybe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _spoken_lines(transcript: Any) -> list[SpokenLine]:
    if not isinstance(transcript, list):
        return []
    spoken: list[SpokenLine] = []
    for entry in transcript:
        if not isinstance(entry, Mapping):
            continue
        speaker = entry.get("speaker")
        text = str(entry.get("text") or entry.get("line") or "").strip()
        direction = str(entry.get("voice_direction") or "").strip().casefold()
        if not speaker or not text or any(marker in direction for marker in ACTION_DESCRIPTION_MARKERS):
            continue
        spoken.append(
            SpokenLine(
                speaker=str(speaker),
                text=text,
                start_s=_maybe_float(entry.get("start_s") if "start_s" in entry else entry.get("time_start_s")),
                end_s=_maybe_float(entry.get("end_s") if "end_s" in entry else entry.get("time_end_s")),
            )
        )
    return spoken


def classify_audio_strategy(*, timed_transcript: Any, script_dna: Mapping[str, Any] | None = None) -> str:
    spoken = _spoken_lines(timed_transcript)
    style = (_dialogue_style(script_dna) or "").casefold()
    if not spoken:
        return "SILENT"
    if len(spoken) == 1 and any(marker in style for marker in NEAR_SILENT_DNA_MARKERS):
        return "NEAR_SILENT_VOICED"
    return "VOICED"


def _resolve_revision_file(revision_root: Path, relative: Any) -> Path | None:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        return None
    candidate = (revision_root / relative).resolve()
    try:
        candidate.relative_to(revision_root.resolve())
    except ValueError:
        return None
    return candidate


def _verify_file(path: Path | None, expected_sha: Any, error_prefix: str) -> list[str]:
    if path is None or not path.is_file():
        return [f"{error_prefix}_MISSING"]
    if not isinstance(expected_sha, str) or _sha256_file(path) != expected_sha:
        return [f"{error_prefix}_HASH_MISMATCH"]
    return []


def _validate_voice_handoff_plan(
    revision_root: Path,
    plan: Mapping[str, Any],
    spoken: Sequence[SpokenLine],
) -> list[str]:
    errors: list[str] = []
    if plan.get("schema") != VOICE_HANDOFF_SCHEMA:
        errors.append("VOICE_HANDOFF_SCHEMA_INVALID")
    if plan.get("revision_id") != revision_root.name:
        errors.append("VOICE_HANDOFF_REVISION_MISMATCH")
    if plan.get("strategy") not in ALLOWED_STRATEGIES:
        errors.append("VOICE_HANDOFF_STRATEGY_INVALID")

    provider_request = plan.get("provider_request")
    if not isinstance(provider_request, Mapping):
        errors.append("VOICE_HANDOFF_PROVIDER_REQUEST_BINDING_MISSING")
    else:
        request_sha = provider_request.get("request_body_sha256")
        expected_audio = plan.get("strategy") != "post_mux"
        if provider_request.get("generate_audio") is not expected_audio:
            errors.append("VOICE_HANDOFF_PROVIDER_AUDIO_MODE_MISMATCH")
        canonical_path = revision_root / "phase_11_submit_return/canonical/phase11_live_request.v1.json"
        canonical = _read_json(canonical_path)
        # A voiced-run voice handoff plan must be bound to the compiled canonical
        # request body hash. That hash is only available AFTER compile, but the
        # audio-strategy gate blocks compile until a plan exists (ordering cycle).
        # The deferred binding mode lets the plan declare request_binding.status =
        # "PENDING_COMPILE" so bootstrap+compile can run; it is accepted ONLY while
        # the canonical does not yet exist. Once the canonical is compiled the plan
        # MUST be rebound to the real hash (rebind_voice_handoff_binding.py) or it is
        # stale and this gate fails closed. Legacy plans omit request_binding and are
        # validated as fully BOUND, exactly as before.
        request_binding = plan.get("request_binding")
        binding_status = (
            str(request_binding.get("status"))
            if isinstance(request_binding, Mapping) and request_binding.get("status")
            else "BOUND"
        )
        if binding_status == "PENDING_COMPILE":
            if isinstance(canonical, Mapping):
                errors.append("VOICE_HANDOFF_PENDING_BINDING_STALE_CANONICAL_PRESENT")
        elif binding_status == "BOUND":
            if not isinstance(request_sha, str) or not request_sha.startswith("sha256:") or len(request_sha) != 71:
                errors.append("VOICE_HANDOFF_PROVIDER_REQUEST_HASH_INVALID")
            if isinstance(canonical, Mapping):
                bindings = canonical.get("approval_bindings")
                canonical_sha = bindings.get("request_body_sha256") if isinstance(bindings, Mapping) else None
                if canonical_sha != request_sha:
                    errors.append("VOICE_HANDOFF_PROVIDER_REQUEST_HASH_MISMATCH")
        else:
            errors.append("VOICE_HANDOFF_REQUEST_BINDING_STATUS_INVALID")

    transcript = plan.get("timed_transcript")
    if not isinstance(transcript, Mapping):
        errors.append("VOICE_HANDOFF_TRANSCRIPT_BINDING_MISSING")
    else:
        transcript_path = _resolve_revision_file(revision_root, transcript.get("revision_relative_path"))
        errors.extend(_verify_file(transcript_path, transcript.get("sha256"), "VOICE_HANDOFF_TRANSCRIPT"))

    planned_lines = plan.get("lines")
    expected_lines = [
        {"speaker": line.speaker, "text": line.text, "start_s": line.start_s, "end_s": line.end_s}
        for line in spoken
    ]
    observed_lines = []
    if isinstance(planned_lines, list):
        observed_lines = [
            {
                "speaker": item.get("speaker"),
                "text": item.get("text"),
                "start_s": _maybe_float(item.get("start_s")),
                "end_s": _maybe_float(item.get("end_s")),
            }
            for item in planned_lines
            if isinstance(item, Mapping)
        ]
    if observed_lines != expected_lines:
        errors.append("VOICE_HANDOFF_LINES_DO_NOT_MATCH_TRANSCRIPT")

    bindings = plan.get("voice_bindings")
    if not isinstance(bindings, Mapping):
        errors.append("VOICE_HANDOFF_VOICE_BINDINGS_MISSING")
    else:
        for speaker in sorted({line.speaker for line in spoken}):
            binding = bindings.get(speaker)
            if not isinstance(binding, Mapping):
                errors.append(f"VOICE_HANDOFF_SPEAKER_BINDING_MISSING:{speaker}")
                continue
            receipt_path = _resolve_revision_file(revision_root, binding.get("source_receipt_relative_path"))
            errors.extend(_verify_file(receipt_path, binding.get("source_receipt_sha256"), f"VOICE_HANDOFF_SOURCE_RECEIPT:{speaker}"))
            reference = binding.get("conditioning_reference")
            if not isinstance(reference, Mapping):
                errors.append(f"VOICE_HANDOFF_REFERENCE_MISSING:{speaker}")
                continue
            reference_path = Path(str(reference.get("path") or "")).expanduser()
            errors.extend(_verify_file(reference_path, reference.get("sha256"), f"VOICE_HANDOFF_REFERENCE:{speaker}"))

    ambience = plan.get("ambient_beds")
    if not isinstance(ambience, list) or not ambience:
        errors.append("VOICE_HANDOFF_AMBIENT_BED_MISSING")
    else:
        for index, item in enumerate(ambience):
            if not isinstance(item, Mapping):
                errors.append(f"VOICE_HANDOFF_AMBIENT_BED_INVALID:{index}")
                continue
            errors.extend(
                _verify_file(
                    Path(str(item.get("path") or "")).expanduser(),
                    item.get("sha256"),
                    f"VOICE_HANDOFF_AMBIENT_BED:{index}",
                )
            )
    return sorted(set(errors))


def _load_voice_handoff_plan(
    revision_root: Path, spoken: Sequence[SpokenLine]
) -> tuple[bool, bool, Path | None, Mapping[str, Any] | None, tuple[str, ...]]:
    paths = [
        revision_root / VOICE_HANDOFF_RELATIVE,
        revision_root / "voice_handoff_plan.json",
        revision_root / "phase_06_script/voice_handoff_plan.json",
    ]
    for path in paths:
        payload = _read_json(path)
        if isinstance(payload, Mapping):
            errors = tuple(_validate_voice_handoff_plan(revision_root, payload, spoken))
            return True, not errors, path, payload, errors
    return False, False, None, None, ()


def assess_revision_audio_strategy(revision_root: Path) -> AudioStrategyAssessment:
    transcript = _read_json(revision_root / "phase_06_script/timed_transcript.json")
    script_dna = _read_json(revision_root / "phase_03_crew/script_dna_selection.json")
    classification = classify_audio_strategy(timed_transcript=transcript, script_dna=script_dna)
    spoken = tuple(_spoken_lines(transcript))
    present, valid, path, plan, errors = _load_voice_handoff_plan(revision_root, spoken)
    strategy = str(plan.get("strategy")) if isinstance(plan, Mapping) and plan.get("strategy") else None
    return AudioStrategyAssessment(
        classification=classification,
        spoken_lines=spoken,
        dialogue_style=_dialogue_style(script_dna if isinstance(script_dna, Mapping) else None),
        delivery_mode=strategy,
        voice_handoff_present=present,
        voice_handoff_valid=valid,
        voice_handoff_path=str(path) if path else None,
        validation_errors=errors,
    )


def _request_strips_dialogue(prompts: Sequence[Mapping[str, Any]] | None) -> bool:
    if not isinstance(prompts, Sequence):
        return False
    return any(
        isinstance(item, Mapping)
        and (
            "no spoken dialogue" in str(item.get("prompt") or "").casefold()
            or "no lip movement" in str(item.get("prompt") or "").casefold()
        )
        for item in prompts
    )


def blockers_for_kling_request(
    assessment: AudioStrategyAssessment,
    *,
    generate_audio: bool,
    multi_prompt: Sequence[Mapping[str, Any]] | None = None,
    voice_ids: Sequence[str] | None = None,
) -> list[str]:
    if not assessment.requires_audible_delivery:
        return []
    if not assessment.voice_handoff_present:
        return ["BLOCKED_VOICED_RUN_AUDIO_STRATEGY_NOT_DECLARED"]
    if not assessment.voice_handoff_valid:
        return ["BLOCKED_VOICED_RUN_HANDOFF_INVALID", *assessment.validation_errors]

    strategy = assessment.delivery_mode
    strips_dialogue = _request_strips_dialogue(multi_prompt)
    if strategy == "post_mux":
        return ["BLOCKED_POST_MUX_REQUIRES_SILENT_KLING"] if generate_audio else []
    if strategy == "kling_native":
        blockers = []
        if not generate_audio:
            blockers.append("BLOCKED_KLING_NATIVE_REQUIRES_GENERATE_AUDIO")
        if strips_dialogue:
            blockers.append("BLOCKED_VOICED_RUN_DIALOGUE_STRIPPED")
        return blockers
    if strategy == "kling_custom_voice":
        blockers = []
        if not generate_audio:
            blockers.append("BLOCKED_KLING_CUSTOM_VOICE_REQUIRES_GENERATE_AUDIO")
        if strips_dialogue:
            blockers.append("BLOCKED_VOICED_RUN_DIALOGUE_STRIPPED")
        if not voice_ids:
            blockers.append("BLOCKED_KLING_CUSTOM_VOICE_ID_MISSING")
        joined = " ".join(str(item.get("prompt") or "") for item in (multi_prompt or []) if isinstance(item, Mapping))
        if "<<<voice_1>>>" not in joined:
            blockers.append("BLOCKED_KLING_CUSTOM_VOICE_TOKEN_MISSING")
        return blockers
    return ["BLOCKED_VOICED_RUN_AUDIO_STRATEGY_INVALID"]


def blockers_for_provider_return(
    assessment: AudioStrategyAssessment,
    *,
    mp4_has_audio_stream: bool,
    mux_receipt_present: bool = False,
) -> list[str]:
    if not assessment.requires_audible_delivery:
        return []
    if assessment.delivery_mode == "post_mux":
        return [] if mp4_has_audio_stream and mux_receipt_present else ["BLOCKED_VOICED_RUN_AWAITING_AUDIO_MUX"]
    return [] if mp4_has_audio_stream else ["BLOCKED_VOICED_RUN_MUTE_RETURN"]


def assess_and_block_kling_request(
    revision_root: Path,
    *,
    generate_audio: bool,
    multi_prompt: Sequence[Mapping[str, Any]] | None = None,
    voice_ids: Sequence[str] | None = None,
) -> AudioStrategyAssessment:
    assessment = assess_revision_audio_strategy(revision_root)
    blockers = blockers_for_kling_request(
        assessment,
        generate_audio=generate_audio,
        multi_prompt=multi_prompt,
        voice_ids=voice_ids,
    )
    if not blockers:
        return assessment
    return AudioStrategyAssessment(
        classification=assessment.classification,
        spoken_lines=assessment.spoken_lines,
        dialogue_style=assessment.dialogue_style,
        delivery_mode=assessment.delivery_mode,
        voice_handoff_present=assessment.voice_handoff_present,
        voice_handoff_valid=assessment.voice_handoff_valid,
        voice_handoff_path=assessment.voice_handoff_path,
        validation_errors=assessment.validation_errors,
        blockers=tuple(blockers),
    )
