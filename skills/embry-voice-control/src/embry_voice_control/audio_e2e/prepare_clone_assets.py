"""Prepare resumable qualified-Horus-clone audio assets for audio E2E campaigns.

This producer calls the live local Orpheus service for every asset. It never
creates listener transcripts, speaker-identity evidence, or personal-memory
permission. The resulting files are explicit acoustic inputs for the existing
managed listener campaign.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any
from urllib.parse import urljoin

import httpx


CAMPAIGN_MANIFEST_SCHEMA = "embry.audio_e2e_campaign_manifest.v1"
CLONE_CONTRACT_SCHEMA = "embry.audio_e2e.clone_source_contract.v1"
ASSET_MANIFEST_SCHEMA = "embry.audio_e2e_audio_assets.v1"
BINDING_SCHEMA = "embry.audio_e2e.orpheus_inference_binding.v1"
SOURCE_CONTRACT = "qualified_horus_clone"
GENERATION_POLICY_SCHEMA = "embry.audio_e2e.orpheus_generation_policy.v1"
QUALIFICATION_POLICY_SCHEMA = "embry.audio_e2e.asr_qualification_policy.v1"
QUALIFICATION_RECEIPT_SCHEMA = "embry.audio_e2e.asr_qualification_receipt.v1"
CANDIDATE_RECEIPT_SCHEMA = "embry.audio_e2e.orpheus_asr_candidate.v1"
WAKE_PREFIX = re.compile(
    r"^\s*hey(?:[\s,;:!?.-]+)embry\b(?:[\s,;:!?.-]+)",
    re.IGNORECASE,
)
HASH_RE = re.compile(r"^(?:sha256:)?([0-9a-f]{64})$")


class AssetConflictError(RuntimeError):
    """An existing deterministic asset directory is incomplete or conflicting."""


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def normalize_sha256(value: Any, *, label: str) -> str:
    match = HASH_RE.fullmatch(str(value or "").strip().lower())
    if not match:
        raise ValueError(f"{label}_sha256_invalid")
    return "sha256:" + match.group(1)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"json_object_required:{path}")
    return value


def atomic_write_bytes(path: Path, value: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    atomic_write_bytes(
        path,
        json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n",
    )


def locator(path: Path) -> dict[str, str]:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return {"path": str(path), "sha256": sha256_file(path)}


def verify_locator(value: Any, *, label: str) -> Path:
    if not isinstance(value, dict):
        raise ValueError(f"{label}_locator_missing")
    path = Path(str(value.get("path") or "")).resolve()
    expected = normalize_sha256(value.get("sha256"), label=label)
    if not path.is_file():
        raise FileNotFoundError(f"{label}_missing:{path}")
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"{label}_hash_mismatch:{expected}:{actual}")
    return path


def json_contains_scalar(value: Any, expected: str) -> bool:
    expected_normalized = str(expected).removeprefix("sha256:")
    if isinstance(value, dict):
        return any(json_contains_scalar(item, expected) for item in value.values())
    if isinstance(value, list):
        return any(json_contains_scalar(item, expected) for item in value)
    if isinstance(value, str):
        return value.removeprefix("sha256:") == expected_normalized
    return False


def safe_component(value: str) -> str:
    original = str(value)
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", original).strip("._")
    if not safe:
        safe = "item"
    if safe != original:
        safe += "-" + hashlib.sha256(original.encode("utf-8")).hexdigest()[:10]
    return safe


def strip_leading_wake_phrase(spoken_text: str) -> str:
    match = WAKE_PREFIX.match(spoken_text)
    if match is None:
        raise ValueError(f"turn_spoken_text_missing_leading_hey_embry:{spoken_text!r}")
    query = spoken_text[match.end():].strip()
    if not query:
        raise ValueError("turn_query_empty_after_wake_strip")
    return query


def build_generation_policy(
    *,
    temperature: float,
    top_p: float,
    repetition_penalty: float,
) -> dict[str, Any]:
    temperature = float(temperature)
    top_p = float(top_p)
    repetition_penalty = float(repetition_penalty)
    if not 0.0 <= temperature <= 2.0:
        raise ValueError("orpheus_temperature_out_of_range")
    if not 0.0 < top_p <= 1.0:
        raise ValueError("orpheus_top_p_out_of_range")
    if not 0.0 < repetition_penalty <= 4.0:
        raise ValueError("orpheus_repetition_penalty_out_of_range")
    return {
        "schema": GENERATION_POLICY_SCHEMA,
        "preset": "precise",
        "speaker": "horus",
        "load_in_4bit": True,
        "min_duration_sec": 0.5,
        "temperature": temperature,
        "top_p": top_p,
        "repetition_penalty": repetition_penalty,
    }



def normalized_tokens(value: str) -> list[str]:
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).split()


def request_wer(expected_text: str, actual_text: str) -> float:
    expected = normalized_tokens(expected_text)
    actual = normalized_tokens(actual_text)
    previous = list(range(len(actual) + 1))
    for expected_token in expected:
        current = [previous[0] + 1]
        for index, actual_token in enumerate(actual, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[index] + 1,
                    previous[index - 1]
                    + int(expected_token != actual_token),
                )
            )
        previous = current
    return previous[-1] / max(1, len(expected))


def build_qualification_policy(
    *,
    model: str,
    device: str,
    compute_type: str,
    max_request_wer: float,
    max_candidates: int,
) -> dict[str, Any]:
    model = str(model).strip()
    device = str(device).strip()
    compute_type = str(compute_type).strip()
    max_request_wer = float(max_request_wer)
    max_candidates = int(max_candidates)
    if not model:
        raise ValueError("qualification_model_required")
    if not device:
        raise ValueError("qualification_device_required")
    if not compute_type:
        raise ValueError("qualification_compute_type_required")
    if not 0.0 <= max_request_wer <= 1.0:
        raise ValueError("max_request_wer_out_of_range")
    if max_candidates < 1 or max_candidates > 100:
        raise ValueError("max_candidates_out_of_range")
    return {
        "schema": QUALIFICATION_POLICY_SCHEMA,
        "model": model,
        "device": device,
        "compute_type": compute_type,
        "language": "en",
        "beam_size": 5,
        "vad_filter": True,
        "max_request_wer": max_request_wer,
        "max_candidates": max_candidates,
        "normalization": "lowercase_ascii_alnum_tokens_v1",
        "wer_algorithm": "token_levenshtein_v1",
        "initial_prompt_used": False,
    }


class QualificationTranscriber:
    """One process-local faster-whisper model used for all candidates."""

    def __init__(self, policy: dict[str, Any]) -> None:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster_whisper_required_for_clone_asset_qualification"
            ) from exc
        self.policy = dict(policy)
        self.model = WhisperModel(
            self.policy["model"],
            device=self.policy["device"],
            compute_type=self.policy["compute_type"],
        )

    def transcribe(self, audio_path: Path) -> dict[str, Any]:
        segments, info = self.model.transcribe(
            str(Path(audio_path).resolve()),
            language=self.policy["language"],
            beam_size=self.policy["beam_size"],
            vad_filter=self.policy["vad_filter"],
        )
        segment_receipts: list[dict[str, Any]] = []
        text_parts: list[str] = []
        for segment in segments:
            text = str(getattr(segment, "text", "") or "").strip()
            if text:
                text_parts.append(text)
            segment_receipts.append(
                {
                    "id": int(getattr(segment, "id", len(segment_receipts))),
                    "start": float(getattr(segment, "start", 0.0) or 0.0),
                    "end": float(getattr(segment, "end", 0.0) or 0.0),
                    "text": text,
                }
            )
        transcript = " ".join(text_parts).strip()
        return {
            "schema": QUALIFICATION_RECEIPT_SCHEMA,
            "status": "PASS",
            "live": True,
            "mocked": False,
            "authority_scope": "campaign_asset_listener_qualification_only",
            "typed_transcript_used": False,
            "initial_prompt_used": False,
            "policy": self.policy,
            "audio": locator(audio_path),
            "transcript": transcript,
            "normalized_transcript": " ".join(normalized_tokens(transcript)),
            "detected_language": str(getattr(info, "language", "") or ""),
            "detected_language_probability": float(
                getattr(info, "language_probability", 0.0) or 0.0
            ),
            "duration_seconds": float(getattr(info, "duration", 0.0) or 0.0),
            "segments": segment_receipts,
        }


def request_for_prompt(
    prompt: str, generation_policy: dict[str, Any]
) -> dict[str, Any]:
    return {
        "prompt": prompt,
        "speaker": generation_policy["speaker"],
        "load_in_4bit": generation_policy["load_in_4bit"],
        "min_duration_sec": generation_policy["min_duration_sec"],
        "temperature": generation_policy["temperature"],
        "top_p": generation_policy["top_p"],
        "repetition_penalty": generation_policy["repetition_penalty"],
    }


def _recorded_request_value(
    payload: dict[str, Any], key: str
) -> Any:
    if key == "min_duration_sec":
        requested = _nested(payload, ("requested_min_duration_sec",))
        if requested is not None:
            return requested
    return _nested(
        payload,
        (key,),
        ("request", key),
        ("request_payload", key),
        ("input", key),
        ("parameters", key),
        ("generation_parameters", key),
    )


def _values_equal(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool):
        return actual is expected
    if isinstance(expected, float):
        try:
            return abs(float(actual) - expected) <= 1e-9
        except (TypeError, ValueError):
            return False
    return actual == expected


def declared_spoken_hash(turn: dict[str, Any], spoken_text: str) -> str:
    declared = turn.get("spoken_text_sha256") or turn.get("utterance_sha256")
    expected = normalize_sha256(declared, label=f"turn:{turn.get('turn_id')}:spoken_text")
    # Campaign text hashes use case_compiler.sha256_value, which hashes the
    # canonical JSON string rather than the raw UTF-8 bytes.
    actual = sha256_bytes(canonical_json(spoken_text))
    if expected != actual:
        raise ValueError(
            f"turn_spoken_text_hash_mismatch:{turn.get('turn_id')}:{expected}:{actual}"
        )
    return expected


def validate_campaign_manifest(value: dict[str, Any]) -> list[dict[str, Any]]:
    if value.get("schema") != CAMPAIGN_MANIFEST_SCHEMA:
        raise ValueError("campaign_manifest_schema_invalid")
    execution = value.get("execution") or {}
    for key in (
        "typed_transcript_allowed",
        "fixture_substitution_allowed",
        "browser_microphone_allowed",
    ):
        if execution.get(key) is not False:
            raise ValueError(f"campaign_execution_boundary_invalid:{key}")
    cases = value.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("campaign_cases_missing")
    seen_cases: set[str] = set()
    seen_turns: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("campaign_case_invalid")
        case_id = str(case.get("case_id") or "")
        if not case_id or case_id in seen_cases:
            raise ValueError(f"campaign_case_id_invalid_or_duplicate:{case_id}")
        seen_cases.add(case_id)
        if case.get("source_mode") not in {"qualified_horus_clone", "qualified_horus_audio"}:
            raise ValueError(f"campaign_case_not_clone_mode:{case_id}")
        turns = case.get("turn_script")
        if not isinstance(turns, list) or not turns:
            raise ValueError(f"campaign_turn_script_missing:{case_id}")
        normalized_turns: list[dict[str, Any]] = []
        for turn in turns:
            if not isinstance(turn, dict):
                raise ValueError(f"campaign_turn_invalid:{case_id}")
            turn_id = str(turn.get("turn_id") or "")
            if not turn_id or turn_id in seen_turns:
                raise ValueError(f"campaign_turn_id_invalid_or_duplicate:{turn_id}")
            seen_turns.add(turn_id)
            spoken_text = str(turn.get("spoken_text") or turn.get("utterance") or "")
            if not spoken_text:
                raise ValueError(f"campaign_turn_spoken_text_missing:{turn_id}")
            spoken_hash = declared_spoken_hash(turn, spoken_text)
            query = strip_leading_wake_phrase(spoken_text)
            normalized_turns.append(
                {
                    "case_id": case_id,
                    "turn_id": turn_id,
                    "spoken_text": spoken_text,
                    "planned_spoken_text_sha256": spoken_hash,
                    "query": query,
                }
            )
        normalized.append({"case_id": case_id, "turns": normalized_turns})
    return normalized


def validate_source_contract(
    path: Path,
    *,
    checkpoint_id: str,
    checkpoint_sha256: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    value = read_json(path)
    if value.get("schema") != CLONE_CONTRACT_SCHEMA:
        raise ValueError("clone_source_contract_schema_invalid")
    required = {
        "status": "PASS",
        "live": True,
        "mocked": False,
        "source_contract": SOURCE_CONTRACT,
        "source_identity": SOURCE_CONTRACT,
        "voice_persona": "horus_lupercal",
        "fresh_physical_human_speech": False,
        "speaker_identity_proven": False,
        "allow_personal_memory": False,
        "memory_source_policy": "non_personal_persona_project_scope",
        "release_readiness_authority": False,
        "suite_ready": False,
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            raise ValueError(
                f"clone_source_contract_field_invalid:{key}:"
                f"{value.get(key)!r}:{expected!r}"
            )
    checkpoint = value.get("checkpoint") or {}
    if checkpoint.get("id") != checkpoint_id:
        raise ValueError("clone_source_contract_checkpoint_id_mismatch")
    if normalize_sha256(
        checkpoint.get("sha256"), label="clone_source_contract_checkpoint"
    ) != checkpoint_sha256:
        raise ValueError("clone_source_contract_checkpoint_hash_mismatch")
    training_locator = checkpoint.get("training_receipt")
    training_path = verify_locator(training_locator, label="clone_training_receipt")
    training = read_json(training_path)
    if not json_contains_scalar(training, checkpoint_id):
        raise ValueError("clone_training_receipt_checkpoint_id_missing")
    if not json_contains_scalar(training, checkpoint_sha256):
        raise ValueError("clone_training_receipt_checkpoint_hash_missing")
    persona = value.get("persona_provenance") or {}
    if persona.get("speaker_id") != "horus_lupercal":
        raise ValueError("clone_persona_provenance_not_horus")
    if persona.get("proves") != "voice_persona_provenance_only":
        raise ValueError("clone_persona_provenance_scope_invalid")
    enrollment_locator = persona.get("physical_enrollment_receipt")
    enrollment_path = verify_locator(
        enrollment_locator, label="clone_physical_enrollment_receipt"
    )
    enrollment = read_json(enrollment_path)
    profile_sha256 = normalize_sha256(
        persona.get("profile_sha256"), label="clone_persona_profile"
    )
    if not json_contains_scalar(enrollment, profile_sha256):
        raise ValueError("clone_persona_profile_hash_mismatch")
    return locator(path), value


def _nested(value: dict[str, Any], *paths: tuple[str, ...]) -> Any:
    for path in paths:
        current: Any = value
        for key in path:
            if not isinstance(current, dict) or key not in current:
                break
            current = current[key]
        else:
            if current not in (None, ""):
                return current
    return None


def original_receipt_payload(value: dict[str, Any]) -> dict[str, Any]:
    nested = value.get("receipt")
    if isinstance(nested, dict) and value.get("status") is None:
        return nested
    return value


def validate_original_inference_receipt(
    value: dict[str, Any],
    *,
    prompt: str,
    request_id: str,
    generation_policy: dict[str, Any] | None = None,
) -> None:
    payload = original_receipt_payload(value)
    status = _nested(payload, ("status",), ("result", "status"))
    if status != "PASS":
        raise ValueError(f"orpheus_original_receipt_not_pass:{status!r}")
    speaker = _nested(
        payload,
        ("speaker",),
        ("request", "speaker"),
        ("request_payload", "speaker"),
        ("input", "speaker"),
    )
    if speaker != "horus":
        raise ValueError(f"orpheus_original_receipt_not_horus:{speaker!r}")
    recorded_prompt = _nested(
        payload,
        ("prompt",),
        ("request", "prompt"),
        ("request_payload", "prompt"),
        ("input", "prompt"),
    )
    if recorded_prompt != prompt:
        raise ValueError(
            f"orpheus_original_receipt_prompt_mismatch:{recorded_prompt!r}:{prompt!r}"
        )
    recorded_request_id = _nested(
        payload,
        ("request_id",),
        ("request", "request_id"),
        ("result", "request_id"),
    )
    if recorded_request_id is not None and str(recorded_request_id) != request_id:
        raise ValueError("orpheus_original_receipt_request_id_mismatch")
    if payload.get("mocked") is True:
        raise ValueError("orpheus_original_receipt_mocked")
    if "live" in payload and payload.get("live") is not True:
        raise ValueError("orpheus_original_receipt_not_live")
    if generation_policy is not None:
        expected_request = request_for_prompt(prompt, generation_policy)
        for key, expected in expected_request.items():
            # The immutable Orpheus receipt does not record this loader flag;
            # the exact submitted request remains preserved in our binding.
            if key == "load_in_4bit":
                continue
            recorded = _recorded_request_value(payload, key)
            if not _values_equal(recorded, expected):
                raise ValueError(
                    "orpheus_original_receipt_request_policy_mismatch:"
                    f"{key}:{recorded!r}:{expected!r}"
                )


def locate_original_receipt(
    response: dict[str, Any],
    *,
    request_id: str,
    prompt: str,
    checkpoints_root: Path,
    generation_policy: dict[str, Any] | None = None,
) -> tuple[Path, dict[str, Any]]:
    receipt = response.get("receipt") or {}
    explicit = _nested(
        response,
        ("original_inference_receipt_path",),
        ("inference_receipt_path",),
        ("stable_receipt_path",),
        ("receipt_path",),
    ) or _nested(
        receipt,
        ("original_inference_receipt_path",),
        ("inference_receipt_path",),
        ("stable_receipt_path",),
        ("receipt_path",),
    )
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(str(explicit)).expanduser().resolve())
    stable_wav = _nested(
        receipt,
        ("stable_wav_path",),
        ("wav_path",),
    ) or _nested(
        response,
        ("stable_wav_path",),
        ("wav_path",),
    )
    if stable_wav:
        wav_path = Path(str(stable_wav)).expanduser().resolve()
        candidates.extend(
            [
                wav_path.with_suffix(".json"),
                wav_path.with_name(wav_path.stem + ".receipt.json"),
                wav_path.parent / f"{request_id}.json",
            ]
        )
        try:
            relative = wav_path.relative_to("/checkpoints")
        except ValueError:
            pass
        else:
            host_wav_path = checkpoints_root / relative
            candidates.extend(
                [
                    host_wav_path.with_suffix(".json"),
                    host_wav_path.with_name(host_wav_path.stem + ".receipt.json"),
                    host_wav_path.parent / f"{request_id}.json",
                ]
            )
    checked: list[str] = []
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        checked.append(str(candidate))
        if not candidate.is_file():
            continue
        value = read_json(candidate)
        try:
            validate_original_inference_receipt(
                value,
                prompt=prompt,
                request_id=request_id,
                generation_policy=generation_policy,
            )
        except ValueError:
            continue
        return candidate, value
    raise FileNotFoundError(
        "orpheus_original_inference_receipt_not_found_or_invalid:"
        + json.dumps(checked, sort_keys=True)
    )


def validate_qualified_wake_assets_manifest(
    path: Path,
    *,
    contract_locator: dict[str, str],
    checkpoint_id: str,
    checkpoint_sha256: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    path = Path(path).resolve()
    value = read_json(path)
    if value.get("schema") != ASSET_MANIFEST_SCHEMA:
        raise ValueError("qualified_wake_assets_manifest_schema_invalid")
    wake_bundle = value.get("wake_audio")
    if not isinstance(wake_bundle, dict):
        raise ValueError("qualified_wake_audio_missing")
    audio_path = verify_locator(
        wake_bundle.get("audio"), label="qualified_wake_audio"
    )
    binding_path = verify_locator(
        wake_bundle.get("inference_receipt"),
        label="qualified_wake_binding",
    )
    binding = read_json(binding_path)
    required = {
        "schema": BINDING_SCHEMA,
        "status": "PASS",
        "live": True,
        "mocked": False,
        "source_contract": SOURCE_CONTRACT,
        "fresh_physical_human_speech": False,
        "speaker_identity_proven": False,
        "release_readiness_authority": False,
        "suite_ready": False,
        "typed_transcript_used": False,
        "authority_scope": "campaign_intermediate_source_binding_only",
        "asset_role": "wake",
    }
    for key, expected in required.items():
        if binding.get(key) != expected:
            raise ValueError(
                "qualified_wake_binding_field_invalid:"
                f"{key}:{binding.get(key)!r}:{expected!r}"
            )
    if binding.get("allow_personal_memory") not in (None, False):
        raise ValueError("qualified_wake_binding_personal_memory_allowed")
    bound_contract = binding.get("source_contract_receipt")
    if bound_contract is not None and bound_contract != contract_locator:
        raise ValueError("qualified_wake_source_contract_mismatch")
    checkpoint = binding.get("checkpoint") or {}
    if checkpoint.get("id") != checkpoint_id:
        raise ValueError("qualified_wake_checkpoint_id_mismatch")
    if normalize_sha256(
        checkpoint.get("sha256"), label="qualified_wake_checkpoint"
    ) != checkpoint_sha256:
        raise ValueError("qualified_wake_checkpoint_hash_mismatch")
    generated_audio_sha256 = normalize_sha256(
        binding.get("generated_audio_sha256"),
        label="qualified_wake_generated_audio",
    )
    if generated_audio_sha256 != sha256_file(audio_path):
        raise ValueError("qualified_wake_audio_hash_mismatch")
    original_path = verify_locator(
        binding.get("original_inference_receipt"),
        label="qualified_wake_original_inference_receipt",
    )
    original = read_json(original_path)
    original_payload = original_receipt_payload(original)
    request = binding.get("request") or {}
    prompt = str(request.get("prompt") or original_payload.get("prompt") or "")
    if not prompt:
        raise ValueError("qualified_wake_prompt_missing")
    speaker = request.get("speaker") or original_payload.get("speaker")
    if speaker != "horus":
        raise ValueError("qualified_wake_request_not_horus")
    if normalize_sha256(
        binding.get("generated_prompt_sha256"),
        label="qualified_wake_prompt",
    ) != sha256_text(prompt):
        raise ValueError("qualified_wake_prompt_hash_mismatch")
    request_id = str(binding.get("request_id") or original_payload.get("request_id") or "")
    if not request_id:
        raise ValueError("qualified_wake_request_id_missing")
    validate_original_inference_receipt(
        original,
        prompt=prompt,
        request_id=request_id,
    )
    return locator(path), {
        "audio": locator(audio_path),
        "inference_receipt": locator(binding_path),
    }


def validate_wav_envelope(value: bytes) -> None:
    if len(value) <= 44:
        raise ValueError("orpheus_generated_audio_empty")
    if value[:4] not in {b"RIFF", b"RF64"} or value[8:12] != b"WAVE":
        raise ValueError("orpheus_generated_audio_not_wav")


def archive_conflict(asset_dir: Path, archive_root: Path) -> None:
    if not asset_dir.exists():
        return
    files = sorted(path for path in asset_dir.rglob("*") if path.is_file())
    inventory = [
        {"relative_path": str(path.relative_to(asset_dir)), "sha256": sha256_file(path)}
        for path in files
    ]
    archive_id = hashlib.sha256(canonical_json(inventory)).hexdigest()[:16]
    target = archive_root / safe_component(asset_dir.name) / archive_id
    if target.exists():
        raise AssetConflictError(f"asset_conflict_archive_exists:{target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(asset_dir), str(target))



def _candidate_paths(candidate_dir: Path) -> dict[str, Path]:
    return {
        "audio": candidate_dir / "audio.wav",
        "original": candidate_dir / "original-inference-receipt.json",
        "response": candidate_dir / "synthesis-response.json",
        "asr": candidate_dir / "qualification-asr.json",
        "receipt": candidate_dir / "candidate-receipt.json",
    }


def _validated_synthesis_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    receipt = payload.get("receipt")
    if not isinstance(receipt, dict):
        raise AssetConflictError("orpheus_synthesis_receipt_missing")
    if receipt.get("status") != "PASS":
        raise AssetConflictError(
            f"orpheus_synthesis_not_pass:{receipt.get('status')!r}"
        )
    if receipt.get("speaker") != "horus":
        raise AssetConflictError("orpheus_synthesis_not_horus")
    if receipt.get("mocked") is True or payload.get("mocked") is True:
        raise AssetConflictError("orpheus_synthesis_mocked")
    request_id = str(receipt.get("request_id") or "")
    if not request_id:
        raise AssetConflictError("orpheus_synthesis_request_id_missing")
    return receipt, request_id


def _validate_asr_receipt(
    *,
    path: Path,
    audio_path: Path,
    prompt: str,
    qualification_policy: dict[str, Any],
) -> dict[str, Any]:
    value = read_json(path)
    required = {
        "schema": QUALIFICATION_RECEIPT_SCHEMA,
        "status": "PASS",
        "live": True,
        "mocked": False,
        "authority_scope": "campaign_asset_listener_qualification_only",
        "typed_transcript_used": False,
        "initial_prompt_used": False,
        "policy": qualification_policy,
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            raise AssetConflictError(
                f"candidate_asr_receipt_conflict:{path}:{key}:"
                f"{value.get(key)!r}:{expected!r}"
            )
    verify_locator(value.get("audio"), label="candidate_asr_audio")
    if value["audio"] != locator(audio_path):
        raise AssetConflictError("candidate_asr_audio_locator_mismatch")
    if value.get("expected_text") != prompt:
        raise AssetConflictError("candidate_asr_expected_text_mismatch")
    if value.get("expected_text_sha256") != sha256_text(prompt):
        raise AssetConflictError("candidate_asr_expected_text_hash_mismatch")
    expected_tokens = " ".join(normalized_tokens(prompt))
    if value.get("normalized_expected_text") != expected_tokens:
        raise AssetConflictError("candidate_asr_normalized_expected_mismatch")
    transcript = str(value.get("transcript") or "")
    expected_normalized = " ".join(normalized_tokens(transcript))
    if value.get("normalized_transcript") != expected_normalized:
        raise AssetConflictError("candidate_asr_normalized_transcript_mismatch")
    computed_wer = request_wer(prompt, transcript)
    try:
        stored_wer = float(value["wer"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AssetConflictError("candidate_asr_wer_missing") from exc
    if abs(stored_wer - computed_wer) > 1e-12:
        raise AssetConflictError("candidate_asr_wer_mismatch")
    accepted = computed_wer <= qualification_policy["max_request_wer"]
    if value.get("accepted") is not accepted:
        raise AssetConflictError("candidate_asr_acceptance_mismatch")
    value["computed_wer"] = computed_wer
    return value


def validate_candidate(
    *,
    candidate_dir: Path,
    candidate_index: int,
    prompt: str,
    contract_locator: dict[str, str],
    checkpoint_id: str,
    checkpoint_sha256: str,
    case_id: str,
    turn_id: str,
    planned_spoken_text_sha256: str,
    generation_policy: dict[str, Any],
    qualification_policy: dict[str, Any],
) -> dict[str, Any]:
    paths = _candidate_paths(candidate_dir)
    existing_count = sum(path.exists() for path in paths.values())
    if existing_count == 0:
        raise FileNotFoundError("candidate_not_prepared")
    if existing_count != len(paths) or not all(
        path.is_file() for path in paths.values()
    ):
        raise AssetConflictError(f"candidate_partial:{candidate_dir}")
    receipt = read_json(paths["receipt"])
    status = receipt.get("status")
    if status not in {"ACCEPTED", "REJECTED"}:
        raise AssetConflictError("candidate_status_invalid")
    required = {
        "schema": CANDIDATE_RECEIPT_SCHEMA,
        "live": True,
        "mocked": False,
        "source_contract": SOURCE_CONTRACT,
        "fresh_physical_human_speech": False,
        "speaker_identity_proven": False,
        "allow_personal_memory": False,
        "release_readiness_authority": False,
        "suite_ready": False,
        "typed_transcript_used": False,
        "authority_scope": "campaign_intermediate_source_binding_only",
        "asset_role": "turn_query",
        "case_id": case_id,
        "turn_id": turn_id,
        "candidate_index": candidate_index,
        "generated_prompt_sha256": sha256_text(prompt),
        "planned_spoken_text_sha256": planned_spoken_text_sha256,
        "source_contract_receipt": contract_locator,
        "generation_policy": generation_policy,
        "qualification_policy": qualification_policy,
        "request": request_for_prompt(prompt, generation_policy),
    }
    for key, expected in required.items():
        if receipt.get(key) != expected:
            raise AssetConflictError(
                f"candidate_receipt_conflict:{paths['receipt']}:{key}:"
                f"{receipt.get(key)!r}:{expected!r}"
            )
    checkpoint = receipt.get("checkpoint") or {}
    if checkpoint.get("id") != checkpoint_id:
        raise AssetConflictError("candidate_checkpoint_id_mismatch")
    if normalize_sha256(
        checkpoint.get("sha256"), label="candidate_checkpoint"
    ) != checkpoint_sha256:
        raise AssetConflictError("candidate_checkpoint_hash_mismatch")
    for key, path_key, label in (
        ("audio", "audio", "candidate_audio"),
        ("synthesis_response", "response", "candidate_response"),
        (
            "original_inference_receipt",
            "original",
            "candidate_original_inference_receipt",
        ),
        ("asr_qualification_receipt", "asr", "candidate_asr_receipt"),
    ):
        verify_locator(receipt.get(key), label=label)
        if receipt[key] != locator(paths[path_key]):
            raise AssetConflictError(f"{label}_locator_mismatch")
    if normalize_sha256(
        receipt.get("generated_audio_sha256"), label="candidate_audio"
    ) != sha256_file(paths["audio"]):
        raise AssetConflictError("candidate_audio_hash_mismatch")
    response = read_json(paths["response"])
    _, response_request_id = _validated_synthesis_payload(response)
    if str(receipt.get("request_id") or "") != response_request_id:
        raise AssetConflictError("candidate_request_id_mismatch")
    validate_original_inference_receipt(
        read_json(paths["original"]),
        prompt=prompt,
        request_id=response_request_id,
        generation_policy=generation_policy,
    )
    asr = _validate_asr_receipt(
        path=paths["asr"],
        audio_path=paths["audio"],
        prompt=prompt,
        qualification_policy=qualification_policy,
    )
    computed_wer = float(asr["computed_wer"])
    try:
        stored_wer = float(receipt["wer"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AssetConflictError("candidate_wer_missing") from exc
    if abs(stored_wer - computed_wer) > 1e-12:
        raise AssetConflictError("candidate_wer_mismatch")
    if receipt.get("transcript") != asr.get("transcript"):
        raise AssetConflictError("candidate_transcript_mismatch")
    accepted = computed_wer <= qualification_policy["max_request_wer"]
    if accepted != (status == "ACCEPTED"):
        raise AssetConflictError("candidate_acceptance_mismatch")
    return {
        "status": status,
        "candidate_index": candidate_index,
        "wer": computed_wer,
        "transcript": str(asr.get("transcript") or ""),
        "normalized_transcript": str(
            asr.get("normalized_transcript") or ""
        ),
        "audio": locator(paths["audio"]),
        "response": locator(paths["response"]),
        "original": locator(paths["original"]),
        "asr": locator(paths["asr"]),
        "receipt": locator(paths["receipt"]),
        "request_id": response_request_id,
        "audio_source": receipt.get("audio_source"),
        "original_source": receipt.get(
            "original_inference_receipt_source"
        ),
    }


def validate_legacy_asset(
    *,
    asset_dir: Path,
    prompt: str,
    contract_locator: dict[str, str],
    checkpoint_id: str,
    checkpoint_sha256: str,
    case_id: str,
    turn_id: str,
    planned_spoken_text_sha256: str,
    generation_policy: dict[str, Any],
) -> None:
    audio_path = asset_dir / "audio.wav"
    original_path = asset_dir / "original-inference-receipt.json"
    response_path = asset_dir / "synthesis-response.json"
    binding_path = asset_dir / "binding-receipt.json"
    binding = read_json(binding_path)
    required = {
        "schema": BINDING_SCHEMA,
        "status": "PASS",
        "live": True,
        "mocked": False,
        "source_contract": SOURCE_CONTRACT,
        "fresh_physical_human_speech": False,
        "speaker_identity_proven": False,
        "allow_personal_memory": False,
        "release_readiness_authority": False,
        "suite_ready": False,
        "typed_transcript_used": False,
        "authority_scope": "campaign_intermediate_source_binding_only",
        "asset_role": "turn_query",
        "case_id": case_id,
        "turn_id": turn_id,
        "planned_spoken_text_sha256": planned_spoken_text_sha256,
        "generated_prompt_sha256": sha256_text(prompt),
        "source_contract_receipt": contract_locator,
        "generation_policy": generation_policy,
        "request": request_for_prompt(prompt, generation_policy),
    }
    for key, expected in required.items():
        if binding.get(key) != expected:
            raise AssetConflictError(
                f"legacy_asset_binding_conflict:{key}:"
                f"{binding.get(key)!r}:{expected!r}"
            )
    checkpoint = binding.get("checkpoint") or {}
    if checkpoint.get("id") != checkpoint_id:
        raise AssetConflictError("legacy_asset_checkpoint_id_mismatch")
    if normalize_sha256(
        checkpoint.get("sha256"), label="legacy_asset_checkpoint"
    ) != checkpoint_sha256:
        raise AssetConflictError("legacy_asset_checkpoint_hash_mismatch")
    if binding.get("audio") != locator(audio_path):
        raise AssetConflictError("legacy_asset_audio_locator_mismatch")
    if normalize_sha256(
        binding.get("generated_audio_sha256"), label="legacy_asset_audio"
    ) != sha256_file(audio_path):
        raise AssetConflictError("legacy_asset_audio_hash_mismatch")
    if binding.get("synthesis_response") != locator(response_path):
        raise AssetConflictError("legacy_asset_response_locator_mismatch")
    if binding.get("original_inference_receipt") != locator(original_path):
        raise AssetConflictError("legacy_asset_original_locator_mismatch")
    response = read_json(response_path)
    _, request_id = _validated_synthesis_payload(response)
    validate_original_inference_receipt(
        read_json(original_path),
        prompt=prompt,
        request_id=request_id,
        generation_policy=generation_policy,
    )


def migrate_legacy_asset(
    *,
    asset_dir: Path,
    prompt: str,
    contract_locator: dict[str, str],
    checkpoint_id: str,
    checkpoint_sha256: str,
    case_id: str,
    turn_id: str,
    planned_spoken_text_sha256: str,
    generation_policy: dict[str, Any],
) -> bool:
    legacy = {
        "audio": asset_dir / "audio.wav",
        "original": asset_dir / "original-inference-receipt.json",
        "response": asset_dir / "synthesis-response.json",
        "binding": asset_dir / "binding-receipt.json",
    }
    existing = {key for key, path in legacy.items() if path.exists()}
    if not existing:
        return False
    candidates_dir = asset_dir / "candidates"
    if candidates_dir.exists() and any(candidates_dir.iterdir()):
        raise AssetConflictError("legacy_and_candidate_assets_coexist")
    if existing == {"response"}:
        candidate_dir = candidates_dir / "candidate-001"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy["response"]), str(candidate_dir / "synthesis-response.json"))
        return True
    if existing != set(legacy):
        raise AssetConflictError(
            "legacy_asset_partial:" + ",".join(sorted(existing))
        )
    validate_legacy_asset(
        asset_dir=asset_dir,
        prompt=prompt,
        contract_locator=contract_locator,
        checkpoint_id=checkpoint_id,
        checkpoint_sha256=checkpoint_sha256,
        case_id=case_id,
        turn_id=turn_id,
        planned_spoken_text_sha256=planned_spoken_text_sha256,
        generation_policy=generation_policy,
    )
    candidate_dir = candidates_dir / "candidate-001"
    candidate_dir.mkdir(parents=True, exist_ok=True)
    shutil.move(str(legacy["audio"]), str(candidate_dir / "audio.wav"))
    shutil.move(
        str(legacy["original"]),
        str(candidate_dir / "original-inference-receipt.json"),
    )
    shutil.move(
        str(legacy["response"]),
        str(candidate_dir / "synthesis-response.json"),
    )
    shutil.move(
        str(legacy["binding"]),
        str(candidate_dir / "legacy-binding-receipt.json"),
    )
    return True


def _audio_from_payload(
    *,
    client: httpx.Client,
    orpheus_url: str,
    payload: dict[str, Any],
    request_id: str,
) -> tuple[bytes, dict[str, Any]]:
    receipt = payload.get("receipt") or {}
    stable_wav = receipt.get("stable_wav_path") or payload.get("wav_path")
    if stable_wav and Path(str(stable_wav)).expanduser().is_file():
        source_path = Path(str(stable_wav)).expanduser().resolve()
        return source_path.read_bytes(), {
            "kind": "stable_wav_path",
            "path": str(source_path),
        }
    download_url = str(payload.get("download_url") or "")
    if not download_url:
        download_url = f"/v1/audio/horus/{request_id}.wav"
    resolved_url = urljoin(orpheus_url.rstrip("/") + "/", download_url)
    response = client.get(resolved_url)
    response.raise_for_status()
    return response.content, {"kind": "download_url", "url": resolved_url}


def complete_candidate(
    *,
    client: httpx.Client,
    qualifier: QualificationTranscriber,
    orpheus_url: str,
    candidate_dir: Path,
    candidate_index: int,
    prompt: str,
    contract_locator: dict[str, str],
    checkpoint_id: str,
    checkpoint_sha256: str,
    orpheus_checkpoints_root: Path,
    case_id: str,
    turn_id: str,
    planned_spoken_text_sha256: str,
    generation_policy: dict[str, Any],
    qualification_policy: dict[str, Any],
) -> tuple[dict[str, Any], bool]:
    paths = _candidate_paths(candidate_dir)
    if paths["receipt"].is_file():
        return validate_candidate(
            candidate_dir=candidate_dir,
            candidate_index=candidate_index,
            prompt=prompt,
            contract_locator=contract_locator,
            checkpoint_id=checkpoint_id,
            checkpoint_sha256=checkpoint_sha256,
            case_id=case_id,
            turn_id=turn_id,
            planned_spoken_text_sha256=planned_spoken_text_sha256,
            generation_policy=generation_policy,
            qualification_policy=qualification_policy,
        ), False

    candidate_dir.mkdir(parents=True, exist_ok=True)
    request = request_for_prompt(prompt, generation_policy)
    provider_called = False
    if paths["response"].is_file():
        payload = read_json(paths["response"])
    else:
        unexpected = [
            path for key, path in paths.items()
            if key != "response" and path.exists()
        ]
        if unexpected:
            raise AssetConflictError(
                f"candidate_missing_response_with_artifacts:{candidate_dir}"
            )
        response = client.post(
            orpheus_url.rstrip("/") + "/v1/synthesize",
            json=request,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("orpheus_synthesis_response_not_object")
        atomic_write_json(paths["response"], payload)
        provider_called = True
    receipt, request_id = _validated_synthesis_payload(payload)

    original_source_path: Path | None = None
    if paths["original"].is_file():
        original_value = read_json(paths["original"])
        validate_original_inference_receipt(
            original_value,
            prompt=prompt,
            request_id=request_id,
            generation_policy=generation_policy,
        )
    else:
        try:
            original_source_path, original_value = locate_original_receipt(
                payload,
                request_id=request_id,
                prompt=prompt,
                checkpoints_root=orpheus_checkpoints_root,
                generation_policy=generation_policy,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "orpheus_original_inference_receipt_pending:"
                f"{case_id}:{turn_id}:candidate-{candidate_index:03d}"
            ) from exc
        atomic_write_bytes(paths["original"], original_source_path.read_bytes())
        if read_json(paths["original"]) != original_value:
            raise RuntimeError("original_inference_receipt_copy_mismatch")

    audio_source: dict[str, Any]
    if paths["audio"].is_file():
        audio_bytes = paths["audio"].read_bytes()
        audio_source = {
            "kind": "resumed_local_candidate",
            "path": str(paths["audio"].resolve()),
        }
    else:
        audio_bytes, audio_source = _audio_from_payload(
            client=client,
            orpheus_url=orpheus_url,
            payload=payload,
            request_id=request_id,
        )
        validate_wav_envelope(audio_bytes)
        atomic_write_bytes(paths["audio"], audio_bytes)
    validate_wav_envelope(audio_bytes)

    if paths["asr"].is_file():
        asr = _validate_asr_receipt(
            path=paths["asr"],
            audio_path=paths["audio"],
            prompt=prompt,
            qualification_policy=qualification_policy,
        )
    else:
        asr = qualifier.transcribe(paths["audio"])
        asr["expected_text"] = prompt
        asr["expected_text_sha256"] = sha256_text(prompt)
        asr["normalized_expected_text"] = " ".join(
            normalized_tokens(prompt)
        )
        asr["wer"] = request_wer(prompt, str(asr.get("transcript") or ""))
        asr["accepted"] = (
            asr["wer"] <= qualification_policy["max_request_wer"]
        )
        atomic_write_json(paths["asr"], asr)
        asr["computed_wer"] = float(asr["wer"])

    computed_wer = request_wer(prompt, str(asr.get("transcript") or ""))
    accepted = computed_wer <= qualification_policy["max_request_wer"]
    candidate_receipt = {
        "schema": CANDIDATE_RECEIPT_SCHEMA,
        "status": "ACCEPTED" if accepted else "REJECTED",
        "live": True,
        "mocked": False,
        "source_contract": SOURCE_CONTRACT,
        "source_contract_receipt": contract_locator,
        "fresh_physical_human_speech": False,
        "speaker_identity_proven": False,
        "allow_personal_memory": False,
        "release_readiness_authority": False,
        "suite_ready": False,
        "typed_transcript_used": False,
        "authority_scope": "campaign_intermediate_source_binding_only",
        "asset_role": "turn_query",
        "case_id": case_id,
        "turn_id": turn_id,
        "candidate_index": candidate_index,
        "planned_spoken_text_sha256": planned_spoken_text_sha256,
        "generated_prompt_sha256": sha256_text(prompt),
        "generated_audio_sha256": sha256_file(paths["audio"]),
        "checkpoint": {
            "id": checkpoint_id,
            "sha256": checkpoint_sha256,
        },
        "generation_policy": generation_policy,
        "qualification_policy": qualification_policy,
        "request": request,
        "request_id": request_id,
        "audio": locator(paths["audio"]),
        "audio_source": audio_source,
        "synthesis_response": locator(paths["response"]),
        "original_inference_receipt": locator(paths["original"]),
        "original_inference_receipt_source": (
            {
                "path": str(original_source_path),
                "sha256": sha256_file(original_source_path),
            }
            if original_source_path is not None
            else locator(paths["original"])
        ),
        "asr_qualification_receipt": locator(paths["asr"]),
        "transcript": str(asr.get("transcript") or ""),
        "normalized_transcript": " ".join(
            normalized_tokens(str(asr.get("transcript") or ""))
        ),
        "wer": computed_wer,
        "max_request_wer": qualification_policy["max_request_wer"],
    }
    if paths["receipt"].exists():
        raise AssetConflictError(
            f"candidate_receipt_would_be_overwritten:{paths['receipt']}"
        )
    atomic_write_json(paths["receipt"], candidate_receipt)
    return validate_candidate(
        candidate_dir=candidate_dir,
        candidate_index=candidate_index,
        prompt=prompt,
        contract_locator=contract_locator,
        checkpoint_id=checkpoint_id,
        checkpoint_sha256=checkpoint_sha256,
        case_id=case_id,
        turn_id=turn_id,
        planned_spoken_text_sha256=planned_spoken_text_sha256,
        generation_policy=generation_policy,
        qualification_policy=qualification_policy,
    ), provider_called


def _accepted_binding(
    *,
    asset_dir: Path,
    accepted: dict[str, Any],
    rejected_receipts: list[dict[str, str]],
    prompt: str,
    contract_locator: dict[str, str],
    checkpoint_id: str,
    checkpoint_sha256: str,
    case_id: str,
    turn_id: str,
    planned_spoken_text_sha256: str,
    generation_policy: dict[str, Any],
    qualification_policy: dict[str, Any],
) -> dict[str, Any]:
    binding_path = asset_dir / "binding-receipt.json"
    value = {
        "schema": BINDING_SCHEMA,
        "status": "PASS",
        "live": True,
        "mocked": False,
        "source_contract": SOURCE_CONTRACT,
        "source_contract_receipt": contract_locator,
        "fresh_physical_human_speech": False,
        "speaker_identity_proven": False,
        "allow_personal_memory": False,
        "release_readiness_authority": False,
        "suite_ready": False,
        "typed_transcript_used": False,
        "authority_scope": "campaign_intermediate_source_binding_only",
        "asset_role": "turn_query",
        "case_id": case_id,
        "turn_id": turn_id,
        "planned_spoken_text_sha256": planned_spoken_text_sha256,
        "generated_prompt_sha256": sha256_text(prompt),
        "generated_audio_sha256": accepted["audio"]["sha256"],
        "checkpoint": {
            "id": checkpoint_id,
            "sha256": checkpoint_sha256,
        },
        "generation_policy": generation_policy,
        "qualification_policy": qualification_policy,
        "request": request_for_prompt(prompt, generation_policy),
        "request_id": accepted["request_id"],
        "audio": accepted["audio"],
        "audio_source": accepted["audio_source"],
        "synthesis_response": accepted["response"],
        "original_inference_receipt": accepted["original"],
        "original_inference_receipt_source": accepted["original_source"],
        "accepted_candidate_index": accepted["candidate_index"],
        "accepted_candidate_receipt": accepted["receipt"],
        "rejected_candidate_receipts": rejected_receipts,
        "qualification": {
            "status": "PASS",
            "transcript": accepted["transcript"],
            "normalized_transcript": accepted["normalized_transcript"],
            "wer": accepted["wer"],
            "max_request_wer": qualification_policy["max_request_wer"],
            "asr_model": qualification_policy["model"],
            "asr_device": qualification_policy["device"],
            "asr_compute_type": qualification_policy["compute_type"],
            "asr_receipt": accepted["asr"],
        },
    }
    if binding_path.exists():
        raise AssetConflictError(
            f"accepted_binding_would_be_overwritten:{binding_path}"
        )
    atomic_write_json(binding_path, value)
    return {
        "audio": accepted["audio"],
        "inference_receipt": locator(binding_path),
    }


def validate_reusable_asset(
    *,
    asset_dir: Path,
    prompt: str,
    contract_locator: dict[str, str],
    checkpoint_id: str,
    checkpoint_sha256: str,
    case_id: str,
    turn_id: str,
    planned_spoken_text_sha256: str,
    generation_policy: dict[str, Any],
    qualification_policy: dict[str, Any],
) -> dict[str, Any]:
    binding_path = asset_dir / "binding-receipt.json"
    if not binding_path.exists():
        raise FileNotFoundError("accepted_binding_missing")
    if not binding_path.is_file():
        raise AssetConflictError("accepted_binding_not_file")
    binding = read_json(binding_path)
    required = {
        "schema": BINDING_SCHEMA,
        "status": "PASS",
        "live": True,
        "mocked": False,
        "source_contract": SOURCE_CONTRACT,
        "source_contract_receipt": contract_locator,
        "fresh_physical_human_speech": False,
        "speaker_identity_proven": False,
        "allow_personal_memory": False,
        "release_readiness_authority": False,
        "suite_ready": False,
        "typed_transcript_used": False,
        "authority_scope": "campaign_intermediate_source_binding_only",
        "asset_role": "turn_query",
        "case_id": case_id,
        "turn_id": turn_id,
        "planned_spoken_text_sha256": planned_spoken_text_sha256,
        "generated_prompt_sha256": sha256_text(prompt),
        "generation_policy": generation_policy,
        "qualification_policy": qualification_policy,
        "request": request_for_prompt(prompt, generation_policy),
    }
    for key, expected in required.items():
        if binding.get(key) != expected:
            raise AssetConflictError(
                f"accepted_binding_conflict:{binding_path}:{key}:"
                f"{binding.get(key)!r}:{expected!r}"
            )
    checkpoint = binding.get("checkpoint") or {}
    if checkpoint.get("id") != checkpoint_id:
        raise AssetConflictError("accepted_binding_checkpoint_id_mismatch")
    if normalize_sha256(
        checkpoint.get("sha256"), label="accepted_binding_checkpoint"
    ) != checkpoint_sha256:
        raise AssetConflictError("accepted_binding_checkpoint_hash_mismatch")
    try:
        accepted_index = int(binding["accepted_candidate_index"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AssetConflictError("accepted_candidate_index_invalid") from exc
    if not 1 <= accepted_index <= qualification_policy["max_candidates"]:
        raise AssetConflictError("accepted_candidate_index_out_of_range")
    candidate = validate_candidate(
        candidate_dir=(
            asset_dir / "candidates" / f"candidate-{accepted_index:03d}"
        ),
        candidate_index=accepted_index,
        prompt=prompt,
        contract_locator=contract_locator,
        checkpoint_id=checkpoint_id,
        checkpoint_sha256=checkpoint_sha256,
        case_id=case_id,
        turn_id=turn_id,
        planned_spoken_text_sha256=planned_spoken_text_sha256,
        generation_policy=generation_policy,
        qualification_policy=qualification_policy,
    )
    if candidate["status"] != "ACCEPTED":
        raise AssetConflictError("accepted_binding_candidate_not_accepted")
    if binding.get("audio") != candidate["audio"]:
        raise AssetConflictError("accepted_binding_audio_locator_mismatch")
    if binding.get("original_inference_receipt") != candidate["original"]:
        raise AssetConflictError("accepted_binding_original_locator_mismatch")
    if binding.get("synthesis_response") != candidate["response"]:
        raise AssetConflictError("accepted_binding_response_locator_mismatch")
    if binding.get("accepted_candidate_receipt") != candidate["receipt"]:
        raise AssetConflictError("accepted_binding_candidate_locator_mismatch")
    qualification = binding.get("qualification") or {}
    if abs(float(qualification.get("wer", -1.0)) - candidate["wer"]) > 1e-12:
        raise AssetConflictError("accepted_binding_wer_mismatch")
    if candidate["wer"] > qualification_policy["max_request_wer"]:
        raise AssetConflictError("accepted_binding_wer_exceeds_threshold")
    expected_rejected: list[dict[str, str]] = []
    for index in range(1, accepted_index):
        prior = validate_candidate(
            candidate_dir=(
                asset_dir / "candidates" / f"candidate-{index:03d}"
            ),
            candidate_index=index,
            prompt=prompt,
            contract_locator=contract_locator,
            checkpoint_id=checkpoint_id,
            checkpoint_sha256=checkpoint_sha256,
            case_id=case_id,
            turn_id=turn_id,
            planned_spoken_text_sha256=planned_spoken_text_sha256,
            generation_policy=generation_policy,
            qualification_policy=qualification_policy,
        )
        if prior["status"] != "REJECTED":
            raise AssetConflictError("accepted_binding_prior_candidate_not_rejected")
        expected_rejected.append(prior["receipt"])
    if binding.get("rejected_candidate_receipts") != expected_rejected:
        raise AssetConflictError("accepted_binding_rejected_candidate_mismatch")
    return {
        "audio": candidate["audio"],
        "inference_receipt": locator(binding_path),
    }


def _prepare_one_asset_once(
    *,
    client: httpx.Client,
    qualifier: QualificationTranscriber,
    orpheus_url: str,
    asset_dir: Path,
    contract_locator: dict[str, str],
    checkpoint_id: str,
    checkpoint_sha256: str,
    orpheus_checkpoints_root: Path,
    case_id: str,
    turn_id: str,
    prompt: str,
    planned_spoken_text_sha256: str,
    generation_policy: dict[str, Any],
    qualification_policy: dict[str, Any],
) -> tuple[dict[str, Any], str]:
    binding_path = asset_dir / "binding-receipt.json"
    if binding_path.is_file():
        existing_binding = read_json(binding_path)
        is_asr_qualified_binding = (
            "qualification_policy" in existing_binding
            or "accepted_candidate_index" in existing_binding
        )
        if is_asr_qualified_binding:
            return validate_reusable_asset(
                asset_dir=asset_dir,
                prompt=prompt,
                contract_locator=contract_locator,
                checkpoint_id=checkpoint_id,
                checkpoint_sha256=checkpoint_sha256,
                case_id=case_id,
                turn_id=turn_id,
                planned_spoken_text_sha256=planned_spoken_text_sha256,
                generation_policy=generation_policy,
                qualification_policy=qualification_policy,
            ), "REUSED"

    asset_dir.mkdir(parents=True, exist_ok=True)
    migrated = migrate_legacy_asset(
        asset_dir=asset_dir,
        prompt=prompt,
        contract_locator=contract_locator,
        checkpoint_id=checkpoint_id,
        checkpoint_sha256=checkpoint_sha256,
        case_id=case_id,
        turn_id=turn_id,
        planned_spoken_text_sha256=planned_spoken_text_sha256,
        generation_policy=generation_policy,
    )
    rejected_receipts: list[dict[str, str]] = []
    provider_calls = 0
    for candidate_index in range(1, qualification_policy["max_candidates"] + 1):
        candidate_dir = (
            asset_dir
            / "candidates"
            / f"candidate-{candidate_index:03d}"
        )
        candidate, provider_called = complete_candidate(
            client=client,
            qualifier=qualifier,
            orpheus_url=orpheus_url,
            candidate_dir=candidate_dir,
            candidate_index=candidate_index,
            prompt=prompt,
            contract_locator=contract_locator,
            checkpoint_id=checkpoint_id,
            checkpoint_sha256=checkpoint_sha256,
            orpheus_checkpoints_root=orpheus_checkpoints_root,
            case_id=case_id,
            turn_id=turn_id,
            planned_spoken_text_sha256=planned_spoken_text_sha256,
            generation_policy=generation_policy,
            qualification_policy=qualification_policy,
        )
        provider_calls += int(provider_called)
        print(
            json.dumps(
                {
                    "status": (
                        "CANDIDATE_ACCEPTED"
                        if candidate["status"] == "ACCEPTED"
                        else "CANDIDATE_REJECTED"
                    ),
                    "case_id": case_id,
                    "turn_id": turn_id,
                    "candidate_index": candidate_index,
                    "transcript": candidate["transcript"],
                    "wer": candidate["wer"],
                    "max_request_wer": qualification_policy[
                        "max_request_wer"
                    ],
                    "provider_called": provider_called,
                    "candidate_receipt": candidate["receipt"],
                },
                sort_keys=True,
            ),
            flush=True,
        )
        if candidate["status"] == "ACCEPTED":
            bundle = _accepted_binding(
                asset_dir=asset_dir,
                accepted=candidate,
                rejected_receipts=rejected_receipts,
                prompt=prompt,
                contract_locator=contract_locator,
                checkpoint_id=checkpoint_id,
                checkpoint_sha256=checkpoint_sha256,
                case_id=case_id,
                turn_id=turn_id,
                planned_spoken_text_sha256=planned_spoken_text_sha256,
                generation_policy=generation_policy,
                qualification_policy=qualification_policy,
            )
            return bundle, (
                "MIGRATED_AND_QUALIFIED"
                if migrated and provider_calls == 0
                else "GENERATED_AND_QUALIFIED"
                if provider_calls > 0
                else "QUALIFIED_FROM_RESUME"
            )
        rejected_receipts.append(candidate["receipt"])

    exhaustion = {
        "schema": "embry.audio_e2e.asr_qualification_exhausted.v1",
        "status": "FAIL",
        "live": True,
        "mocked": False,
        "case_id": case_id,
        "turn_id": turn_id,
        "generated_prompt_sha256": sha256_text(prompt),
        "generation_policy": generation_policy,
        "qualification_policy": qualification_policy,
        "candidate_receipts": rejected_receipts,
        "provider_calls_this_execution": provider_calls,
    }
    atomic_write_json(asset_dir / "qualification-exhausted.json", exhaustion)
    raise RuntimeError(
        "clone_asset_asr_qualification_exhausted:"
        f"{case_id}:{turn_id}:"
        f"{qualification_policy['max_candidates']}"
    )


def prepare_one_asset(
    *,
    client: httpx.Client,
    qualifier: QualificationTranscriber,
    orpheus_url: str,
    asset_dir: Path,
    archive_root: Path,
    prompt: str,
    contract_locator: dict[str, str],
    checkpoint_id: str,
    checkpoint_sha256: str,
    orpheus_checkpoints_root: Path,
    case_id: str,
    turn_id: str,
    planned_spoken_text_sha256: str,
    generation_policy: dict[str, Any],
    qualification_policy: dict[str, Any],
    regenerate_conflicts: bool,
) -> tuple[dict[str, Any], str]:
    try:
        return _prepare_one_asset_once(
            client=client,
            qualifier=qualifier,
            orpheus_url=orpheus_url,
            asset_dir=asset_dir,
            contract_locator=contract_locator,
            checkpoint_id=checkpoint_id,
            checkpoint_sha256=checkpoint_sha256,
            orpheus_checkpoints_root=orpheus_checkpoints_root,
            case_id=case_id,
            turn_id=turn_id,
            prompt=prompt,
            planned_spoken_text_sha256=planned_spoken_text_sha256,
            generation_policy=generation_policy,
            qualification_policy=qualification_policy,
        )
    except (AssetConflictError, ValueError, FileNotFoundError):
        if not regenerate_conflicts:
            raise
        archive_conflict(asset_dir, archive_root)
        asset_dir.mkdir(parents=True, exist_ok=True)
        return _prepare_one_asset_once(
            client=client,
            qualifier=qualifier,
            orpheus_url=orpheus_url,
            asset_dir=asset_dir,
            contract_locator=contract_locator,
            checkpoint_id=checkpoint_id,
            checkpoint_sha256=checkpoint_sha256,
            orpheus_checkpoints_root=orpheus_checkpoints_root,
            case_id=case_id,
            turn_id=turn_id,
            prompt=prompt,
            planned_spoken_text_sha256=planned_spoken_text_sha256,
            generation_policy=generation_policy,
            qualification_policy=qualification_policy,
        )


def prepare_clone_assets(
    *,
    manifest_path: Path,
    source_contract_path: Path,
    qualified_wake_assets_manifest_path: Path,
    orpheus_url: str,
    checkpoint_id: str,
    checkpoint_sha256: str,
    orpheus_checkpoints_root: Path,
    output_dir: Path,
    timeout_seconds: float = 300.0,
    temperature: float = 0.4,
    top_p: float = 0.4,
    repetition_penalty: float = 1.1,
    qualification_model: str = "small.en",
    qualification_device: str = "cpu",
    qualification_compute_type: str = "int8",
    max_request_wer: float = 0.25,
    max_candidates: int = 5,
    regenerate_conflicts: bool = False,
) -> dict[str, Any]:
    manifest_path = Path(manifest_path).resolve()
    source_contract_path = Path(source_contract_path).resolve()
    qualified_wake_assets_manifest_path = Path(
        qualified_wake_assets_manifest_path
    ).resolve()
    output_dir = Path(output_dir).resolve()
    orpheus_checkpoints_root = Path(orpheus_checkpoints_root).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_sha256 = normalize_sha256(
        checkpoint_sha256, label="checkpoint_inventory"
    )
    if not checkpoint_id.strip():
        raise ValueError("checkpoint_id_required")
    if not orpheus_url.startswith(("http://127.0.0.1", "http://localhost")):
        raise ValueError("orpheus_url_must_be_local")
    if not orpheus_checkpoints_root.is_dir():
        raise FileNotFoundError(
            f"orpheus_checkpoints_root_missing:{orpheus_checkpoints_root}"
        )
    generation_policy = build_generation_policy(
        temperature=temperature,
        top_p=top_p,
        repetition_penalty=repetition_penalty,
    )
    qualification_policy = build_qualification_policy(
        model=qualification_model,
        device=qualification_device,
        compute_type=qualification_compute_type,
        max_request_wer=max_request_wer,
        max_candidates=max_candidates,
    )

    manifest = read_json(manifest_path)
    cases = validate_campaign_manifest(manifest)
    contract_locator, contract = validate_source_contract(
        source_contract_path,
        checkpoint_id=checkpoint_id,
        checkpoint_sha256=checkpoint_sha256,
    )
    if contract["checkpoint"]["id"] != checkpoint_id:
        raise ValueError("checkpoint_contract_mismatch")
    qualified_wake_manifest_locator, wake_bundle = (
        validate_qualified_wake_assets_manifest(
            qualified_wake_assets_manifest_path,
            contract_locator=contract_locator,
            checkpoint_id=checkpoint_id,
            checkpoint_sha256=checkpoint_sha256,
        )
    )

    archive_root = output_dir / "conflict-archive"
    asset_manifest_path = output_dir / "qualified-horus-clone-assets.json"
    progress_index = 1
    expected_assets = 1 + sum(len(case["turns"]) for case in cases)
    result_cases: dict[str, Any] = {}

    print(
        json.dumps(
            {
                "status": "QUALIFIED_WAKE_REUSED",
                "asset": progress_index,
                "expected_assets": expected_assets,
                "asset_role": "wake",
                "qualified_wake_assets_manifest": (
                    qualified_wake_manifest_locator
                ),
                "audio_sha256": wake_bundle["audio"]["sha256"],
                "inference_receipt_sha256": wake_bundle[
                    "inference_receipt"
                ]["sha256"],
                "provider_called": False,
            },
            sort_keys=True,
        ),
        flush=True,
    )

    qualifier = QualificationTranscriber(qualification_policy)
    with httpx.Client(timeout=timeout_seconds, follow_redirects=True) as client:
        for case in cases:
            case_id = case["case_id"]
            turn_bundles: dict[str, Any] = {}
            for turn in case["turns"]:
                progress_index += 1
                turn_id = turn["turn_id"]
                prompt = turn["query"]
                print(
                    json.dumps(
                        {
                            "status": "PREPARING",
                            "asset": progress_index,
                            "expected_assets": expected_assets,
                            "asset_role": "turn_query",
                            "case_id": case_id,
                            "turn_id": turn_id,
                            "prompt_sha256": sha256_text(prompt),
                            "generation_policy": generation_policy,
                            "qualification_policy": qualification_policy,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
                bundle, action = prepare_one_asset(
                    client=client,
                    qualifier=qualifier,
                    orpheus_url=orpheus_url,
                    asset_dir=(
                        output_dir
                        / "cases"
                        / safe_component(case_id)
                        / "turns"
                        / safe_component(turn_id)
                    ),
                    archive_root=archive_root,
                    prompt=prompt,
                    contract_locator=contract_locator,
                    checkpoint_id=checkpoint_id,
                    checkpoint_sha256=checkpoint_sha256,
                    orpheus_checkpoints_root=orpheus_checkpoints_root,
                    case_id=case_id,
                    turn_id=turn_id,
                    planned_spoken_text_sha256=turn[
                        "planned_spoken_text_sha256"
                    ],
                    generation_policy=generation_policy,
                    qualification_policy=qualification_policy,
                    regenerate_conflicts=regenerate_conflicts,
                )
                turn_bundles[turn_id] = bundle
                print(
                    json.dumps(
                        {
                            "status": action,
                            "asset": progress_index,
                            "expected_assets": expected_assets,
                            "asset_role": "turn_query",
                            "case_id": case_id,
                            "turn_id": turn_id,
                            "audio_sha256": bundle["audio"]["sha256"],
                            "generation_policy": generation_policy,
                            "qualification_policy": qualification_policy,
                        },
                        sort_keys=True,
                    ),
                    flush=True,
                )
            result_cases[case_id] = {"turns": turn_bundles}

    turn_ids = [turn["turn_id"] for case in cases for turn in case["turns"]]
    turn_audio_hashes = [
        result_cases[case["case_id"]]["turns"][turn["turn_id"]]["audio"][
            "sha256"
        ]
        for case in cases
        for turn in case["turns"]
    ]
    turn_binding_hashes = [
        result_cases[case["case_id"]]["turns"][turn["turn_id"]][
            "inference_receipt"
        ]["sha256"]
        for case in cases
        for turn in case["turns"]
    ]
    original_hashes: list[str] = []
    request_ids: list[str] = []
    accepted_wers: list[float] = []
    accepted_candidate_indices: list[int] = []
    for case in cases:
        for turn in case["turns"]:
            binding_path = Path(
                result_cases[case["case_id"]]["turns"][turn["turn_id"]][
                    "inference_receipt"
                ]["path"]
            )
            binding = read_json(binding_path)
            if binding.get("generation_policy") != generation_policy:
                raise RuntimeError(
                    "prepared_binding_generation_policy_mismatch:"
                    f"{turn['turn_id']}"
                )
            if binding.get("qualification_policy") != qualification_policy:
                raise RuntimeError(
                    "prepared_binding_qualification_policy_mismatch:"
                    f"{turn['turn_id']}"
                )
            qualification = binding.get("qualification") or {}
            wer = float(qualification.get("wer", 2.0))
            if wer > qualification_policy["max_request_wer"]:
                raise RuntimeError(
                    "prepared_binding_wer_exceeds_threshold:"
                    f"{turn['turn_id']}:{wer}"
                )
            accepted_wers.append(wer)
            accepted_candidate_indices.append(
                int(binding["accepted_candidate_index"])
            )
            request_ids.append(str(binding["request_id"]))
            original_hashes.append(
                normalize_sha256(
                    binding["original_inference_receipt"]["sha256"],
                    label="original_inference_receipt",
                )
            )
    if len(turn_ids) != len(set(turn_ids)):
        raise RuntimeError("prepared_turn_ids_not_unique")
    if len(turn_audio_hashes) != len(set(turn_audio_hashes)):
        raise RuntimeError("prepared_turn_audio_hashes_not_unique")
    if len(turn_binding_hashes) != len(set(turn_binding_hashes)):
        raise RuntimeError("prepared_turn_binding_hashes_not_unique")
    if len(original_hashes) != len(set(original_hashes)):
        raise RuntimeError("prepared_original_receipt_hashes_not_unique")
    if len(request_ids) != len(set(request_ids)):
        raise RuntimeError("prepared_orpheus_request_ids_not_unique")

    aggregate = {
        "schema": ASSET_MANIFEST_SCHEMA,
        "status": "PASS",
        "live": True,
        "mocked": False,
        "source_contract": contract_locator,
        "campaign_manifest": locator(manifest_path),
        "qualified_wake_assets_manifest": (
            qualified_wake_manifest_locator
        ),
        "checkpoint": {
            "id": checkpoint_id,
            "sha256": checkpoint_sha256,
        },
        "generation_policy": generation_policy,
        "qualification_policy": qualification_policy,
        "fresh_physical_human_speech": False,
        "speaker_identity_proven": False,
        "allow_personal_memory": False,
        "release_readiness_authority": False,
        "suite_ready": False,
        "typed_transcript_used": False,
        "wake_audio": wake_bundle,
        "cases": result_cases,
        "counts": {
            "case_count": len(cases),
            "turn_count": len(turn_ids),
            "asset_count": expected_assets,
            "qualified_wake_asset_count": 1,
            "generated_query_asset_count": len(turn_ids),
            "asr_qualified_query_asset_count": len(accepted_wers),
            "max_accepted_request_wer": max(accepted_wers, default=0.0),
            "max_accepted_candidate_index": max(
                accepted_candidate_indices, default=0
            ),
            "unique_orpheus_request_id_count": len(set(request_ids)),
            "unique_turn_id_count": len(set(turn_ids)),
            "unique_turn_audio_sha256_count": len(set(turn_audio_hashes)),
            "unique_turn_binding_sha256_count": len(set(turn_binding_hashes)),
            "unique_original_inference_receipt_sha256_count": len(
                set(original_hashes)
            ),
        },
    }
    atomic_write_json(asset_manifest_path, aggregate)
    print(
        json.dumps(
            {
                "status": "PASS",
                "asset_manifest": str(asset_manifest_path),
                "asset_manifest_sha256": sha256_file(asset_manifest_path),
                "generation_policy": generation_policy,
                "qualification_policy": qualification_policy,
                **aggregate["counts"],
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return aggregate
