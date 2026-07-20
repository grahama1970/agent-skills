"""Prepare resumable qualified-Horus-clone audio assets for audio E2E campaigns.

This producer calls the live local Orpheus service for every asset. It never
creates listener transcripts, speaker-identity evidence, or personal-memory
permission. The resulting files are explicit acoustic inputs for the existing
managed listener campaign.
"""

from __future__ import annotations

from array import array
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import tempfile
from typing import Any
from urllib.parse import urljoin
import wave

import httpx

from .asr_comparison import (
    ASR_COMPARISON_POLICY,
    ASR_COMPARISON_POLICY_SHA256,
    compare_asr_text,
    normalized_tokens,
)
from .case_compiler import (
    SPOKEN_TEXT_NORMALIZATION,
    SPOKEN_TEXT_NORMALIZATION_SHA256,
    TONE_PROSODY_MAP,
    TONE_PROSODY_MAP_SHA256,
    apply_tone_tags,
    sha256_value,
    spoken_text as derive_spoken_text,
    synthesis_text_for_family,
)


CAMPAIGN_MANIFEST_SCHEMA = "embry.audio_e2e_campaign_manifest.v1"
CLONE_CONTRACT_SCHEMA = "embry.audio_e2e.clone_source_contract.v1"
ASSET_MANIFEST_SCHEMA = "embry.audio_e2e_audio_assets.v1"
BINDING_SCHEMA = "embry.audio_e2e.orpheus_inference_binding.v1"
SOURCE_CONTRACT = "qualified_horus_clone"
GENERATION_POLICY_SCHEMA = "embry.audio_e2e.orpheus_generation_policy.v1"
QUALIFICATION_POLICY_SCHEMA = "embry.audio_e2e.asr_qualification_policy.v1"
QUALIFICATION_RECEIPT_SCHEMA = "embry.audio_e2e.asr_qualification_receipt.v1"
CANDIDATE_RECEIPT_SCHEMA = "embry.audio_e2e.orpheus_asr_candidate.v1"
UTTERANCE_BOUNDARY_POLICY_SCHEMA = (
    "embry.audio_e2e.utterance_boundary_policy.v1"
)
UTTERANCE_BOUNDARY_RECEIPT_SCHEMA = (
    "embry.audio_e2e.utterance_boundary_receipt.v1"
)
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



def request_wer(expected_text: str, actual_text: str) -> float:
    return float(compare_asr_text(
        expected_text,
        actual_text,
        strip_expected_wake=False,
    )["comparison_wer"])


def _utterance_boundary_policy(
    max_internal_silence_seconds: float,
) -> dict[str, Any]:
    """Build the managed-listener-compatible internal-silence policy.

    The live listener finalizes after its configured post-speech silence. This
    analyzer uses 20 ms PCM RMS frames, enters speech at -42 dBFS, and leaves
    speech only after 200 ms below -45 dBFS. The 3 dB release hysteresis and
    100 ms minimum speech run prevent ordinary word gaps or isolated noise
    spikes from being treated as separate clauses.
    """

    max_internal_silence_seconds = float(max_internal_silence_seconds)
    if max_internal_silence_seconds <= 0.0:
        raise ValueError("max_internal_silence_seconds_out_of_range")
    return {
        "schema": UTTERANCE_BOUNDARY_POLICY_SCHEMA,
        "algorithm": "pcm_rms_hysteresis_v1",
        "max_internal_silence_seconds": max_internal_silence_seconds,
        "comparison": "strictly_less_than",
        "frame_duration_milliseconds": 20.0,
        "speech_threshold_dbfs": -42.0,
        "speech_release_threshold_dbfs": -45.0,
        "speech_hysteresis_db": 3.0,
        "minimum_speech_duration_seconds": 0.10,
        "minimum_silence_duration_seconds": 0.20,
        "leading_trailing_silence_ignored": True,
    }


def _pcm_rms_dbfs(frame: bytes, sample_width: int) -> float:
    if sample_width not in {1, 2, 3, 4}:
        raise ValueError(f"wav_sample_width_unsupported:{sample_width}")
    if not frame:
        return -120.0

    square_sum = 0.0
    sample_count = len(frame) // sample_width
    if sample_count == 0:
        return -120.0

    if sample_width == 1:
        for value in frame:
            sample = value - 128
            square_sum += float(sample * sample)
        full_scale = 127.0
    else:
        usable_bytes = sample_count * sample_width
        for offset in range(0, usable_bytes, sample_width):
            sample = int.from_bytes(
                frame[offset : offset + sample_width],
                byteorder="little",
                signed=True,
            )
            square_sum += float(sample * sample)
        full_scale = float((1 << (sample_width * 8 - 1)) - 1)

    rms = math.sqrt(square_sum / sample_count)
    if rms <= 0.0:
        return -120.0
    return max(-120.0, 20.0 * math.log10(rms / full_scale))


def _float_pcm_rms_dbfs(frame: bytes, sample_width: int) -> float:
    format_code = {4: "<f", 8: "<d"}.get(sample_width)
    if format_code is None:
        raise ValueError(f"wav_float_sample_width_unsupported:{sample_width}")
    usable_bytes = len(frame) - (len(frame) % sample_width)
    if usable_bytes == 0:
        return -120.0
    sample_count = usable_bytes // sample_width
    square_sum = sum(
        float(value) * float(value)
        for (value,) in struct.iter_unpack(format_code, frame[:usable_bytes])
    )
    rms = math.sqrt(square_sum / sample_count)
    if rms <= 0.0:
        return -120.0
    return max(-120.0, 20.0 * math.log10(rms))


def _read_ieee_float_wav(
    audio_path: Path,
    frame_duration_seconds: float,
) -> tuple[int, int, int, int, list[float]]:
    data = audio_path.read_bytes()
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("wav_riff_contract_invalid")
    fmt_chunk: bytes | None = None
    audio_data: bytes | None = None
    offset = 12
    while offset + 8 <= len(data):
        chunk_id = data[offset : offset + 4]
        chunk_size = struct.unpack_from("<I", data, offset + 4)[0]
        chunk_start = offset + 8
        chunk_end = chunk_start + chunk_size
        if chunk_end > len(data):
            raise ValueError("wav_chunk_truncated")
        if chunk_id == b"fmt ":
            fmt_chunk = data[chunk_start:chunk_end]
        elif chunk_id == b"data":
            audio_data = data[chunk_start:chunk_end]
        offset = chunk_end + (chunk_size & 1)
    if fmt_chunk is None or audio_data is None or len(fmt_chunk) < 16:
        raise ValueError("wav_required_chunk_missing")
    format_tag, channels, sample_rate, _, block_align, bits_per_sample = (
        struct.unpack_from("<HHIIHH", fmt_chunk)
    )
    if format_tag != 3:
        raise ValueError(f"wav_format_unsupported:{format_tag}")
    sample_width = bits_per_sample // 8
    if channels < 1 or sample_rate < 1 or block_align != channels * sample_width:
        raise ValueError("wav_audio_contract_invalid")
    total_frames = len(audio_data) // block_align
    frame_samples = max(1, int(round(sample_rate * frame_duration_seconds)))
    frame_bytes = frame_samples * block_align
    levels = [
        _float_pcm_rms_dbfs(audio_data[start : start + frame_bytes], sample_width)
        for start in range(0, total_frames * block_align, frame_bytes)
    ]
    return channels, sample_width, sample_rate, total_frames, levels


def analyze_internal_silence(
    audio_path: Path,
    boundary_policy: dict[str, Any],
) -> dict[str, Any]:
    """Measure silence only when bounded by confirmed speech on both sides."""

    audio_path = Path(audio_path).resolve()
    frame_duration_seconds = (
        float(boundary_policy["frame_duration_milliseconds"]) / 1000.0
    )
    try:
        with wave.open(str(audio_path), "rb") as stream:
            if stream.getcomptype() != "NONE":
                raise ValueError(
                    f"wav_compression_unsupported:{stream.getcomptype()}"
                )
            channels = int(stream.getnchannels())
            sample_width = int(stream.getsampwidth())
            sample_rate = int(stream.getframerate())
            total_frames = int(stream.getnframes())
            if channels < 1 or sample_rate < 1 or total_frames < 1:
                raise ValueError("wav_audio_contract_invalid")

            analysis_frame_samples = max(
                1, int(round(sample_rate * frame_duration_seconds))
            )
            levels: list[float] = []
            while True:
                raw = stream.readframes(analysis_frame_samples)
                if not raw:
                    break
                levels.append(_pcm_rms_dbfs(raw, sample_width))
    except wave.Error as exc:
        if "unknown format: 3" not in str(exc):
            raise
        # Orpheus emits IEEE-float WAVs, which Python's wave module rejects.
        channels, sample_width, sample_rate, total_frames, levels = (
            _read_ieee_float_wav(audio_path, frame_duration_seconds)
        )

    enter_threshold = float(boundary_policy["speech_threshold_dbfs"])
    release_threshold = float(
        boundary_policy["speech_release_threshold_dbfs"]
    )
    minimum_speech_frames = max(
        1,
        int(
            math.ceil(
                float(boundary_policy["minimum_speech_duration_seconds"])
                / frame_duration_seconds
            )
        ),
    )
    minimum_silence_frames = max(
        1,
        int(
            math.ceil(
                float(boundary_policy["minimum_silence_duration_seconds"])
                / frame_duration_seconds
            )
        ),
    )

    speech_segments_frames: list[tuple[int, int]] = []
    in_speech = False
    speech_candidate_start: int | None = None
    silence_candidate_start: int | None = None
    segment_start: int | None = None

    for index, level in enumerate(levels):
        if not in_speech:
            if level >= enter_threshold:
                if speech_candidate_start is None:
                    speech_candidate_start = index
                if index - speech_candidate_start + 1 >= minimum_speech_frames:
                    in_speech = True
                    segment_start = speech_candidate_start
                    speech_candidate_start = None
                    silence_candidate_start = None
            else:
                speech_candidate_start = None
            continue

        if level < release_threshold:
            if silence_candidate_start is None:
                silence_candidate_start = index
            if index - silence_candidate_start + 1 >= minimum_silence_frames:
                if segment_start is None:
                    raise RuntimeError("utterance_boundary_segment_state_invalid")
                speech_segments_frames.append(
                    (segment_start, silence_candidate_start)
                )
                in_speech = False
                segment_start = None
                speech_candidate_start = None
                silence_candidate_start = None
        else:
            silence_candidate_start = None

    if in_speech and segment_start is not None:
        segment_end = (
            silence_candidate_start
            if silence_candidate_start is not None
            else len(levels)
        )
        if segment_end - segment_start >= minimum_speech_frames:
            speech_segments_frames.append((segment_start, segment_end))

    speech_segments: list[dict[str, float]] = []
    for start_frame, end_frame in speech_segments_frames:
        start_seconds = start_frame * frame_duration_seconds
        end_seconds = min(
            total_frames / sample_rate,
            end_frame * frame_duration_seconds,
        )
        speech_segments.append(
            {
                "start_seconds": round(start_seconds, 6),
                "end_seconds": round(end_seconds, 6),
                "duration_seconds": round(
                    max(0.0, end_seconds - start_seconds), 6
                ),
            }
        )

    internal_silences: list[dict[str, float]] = []
    for left, right in zip(speech_segments, speech_segments[1:]):
        start_seconds = float(left["end_seconds"])
        end_seconds = float(right["start_seconds"])
        duration_seconds = max(0.0, end_seconds - start_seconds)
        internal_silences.append(
            {
                "start_seconds": round(start_seconds, 6),
                "end_seconds": round(end_seconds, 6),
                "duration_seconds": round(duration_seconds, 6),
            }
        )

    longest = max(
        (item["duration_seconds"] for item in internal_silences),
        default=0.0,
    )
    limit = float(boundary_policy["max_internal_silence_seconds"])
    accepted = longest < limit
    return {
        "schema": UTTERANCE_BOUNDARY_RECEIPT_SCHEMA,
        "status": "PASS",
        "policy": boundary_policy,
        "audio": locator(audio_path),
        "wav": {
            "sample_rate_hz": sample_rate,
            "channels": channels,
            "sample_width_bytes": sample_width,
            "frame_count": total_frames,
            "duration_seconds": round(total_frames / sample_rate, 6),
        },
        "analysis_frame_count": len(levels),
        "speech_segment_count": len(speech_segments),
        "speech_segments": speech_segments,
        "internal_silence_count": len(internal_silences),
        "internal_silences": internal_silences,
        "longest_internal_silence_seconds": round(longest, 6),
        "max_internal_silence_seconds": limit,
        "accepted": accepted,
        "rejection_reason": (
            None
            if accepted
            else "internal_silence_exceeds_listener_boundary"
        ),
    }


def detect_generation_truncation(boundary: dict[str, Any]) -> dict[str, Any]:
    """Audio-side detection of a generation cut off mid-utterance.

    The deployed Orpheus inference server (``/app/inference_server.py``, baked
    into the ``orpheus-infer`` image -- not a mounted, patchable local source)
    hard-caps ``max_new_tokens`` at 1200 and its synthesis receipt does NOT
    surface ``finish_reason``/``stop_reason``/generated-token counts. Per the
    oracle's stated fallback, truncation is therefore detected from the audio
    itself rather than inferred after Whisper.

    A stop-token-terminated Orpheus utterance decays into >= the boundary
    policy's ``minimum_silence_duration_seconds`` of trailing near-silence. A
    generation cut off at the token budget instead ends WHILE still voiced: its
    final speech segment is force-closed at the end of the file, leaving little
    or no trailing silence. That is the signature we reject as infrastructure
    failure (``tts_generation_truncated``) BEFORE spending a quality candidate
    slot on it -- an incomplete generation is not an unsuccessful pronunciation
    sample.
    """
    policy = boundary.get("policy") or {}
    min_trailing = float(policy.get("minimum_silence_duration_seconds", 0.20))
    wav = boundary.get("wav") or {}
    duration_seconds = float(wav.get("duration_seconds") or 0.0)
    segments = boundary.get("speech_segments") or []
    last_speech_end = (
        max(float(seg["end_seconds"]) for seg in segments) if segments else 0.0
    )
    trailing_silence_seconds = round(max(0.0, duration_seconds - last_speech_end), 6)
    ends_voiced = bool(segments) and trailing_silence_seconds < min_trailing
    return {
        "schema": "embry.audio_e2e.generation_truncation.v1",
        "detector": "audio_trailing_silence_v1",
        "server_finish_reason_available": False,
        "server_token_counts_available": False,
        "audio_duration_seconds": round(duration_seconds, 6),
        "speech_segment_count": len(segments),
        "last_speech_end_seconds": round(last_speech_end, 6),
        "trailing_silence_seconds": trailing_silence_seconds,
        "minimum_trailing_silence_seconds": min_trailing,
        "maximum_internal_silence_seconds": float(
            boundary.get("longest_internal_silence_seconds") or 0.0
        ),
        "ends_voiced": ends_voiced,
        "truncated": ends_voiced,
    }


_CLAUSE_BOUNDARY_RE = re.compile(r"[^.!?;,]*[.!?;,]+|\S[^.!?;,]*$")


def split_into_clauses(text: str) -> list[str]:
    """Split a sentence into clauses on punctuation WITHOUT changing any words.

    Used by the clause-concatenation fallback: when a full sentence keeps
    truncating at the generation budget, each clause is synthesized separately
    and the audio is rejoined. The lexical content is identical to the original
    sentence (only whitespace at the split points differs), so the WER
    comparison text is unchanged and provenance records
    ``source_text_unchanged: true``.
    """
    parts = [part.strip() for part in _CLAUSE_BOUNDARY_RE.findall(text)]
    clauses = [part for part in parts if part]
    return clauses or ([text.strip()] if text.strip() else [])


def _decode_pcm16_mono_wav(wav_bytes: bytes) -> tuple[int, "array[int]"]:
    with wave.open(io.BytesIO(wav_bytes), "rb") as stream:
        if stream.getcomptype() != "NONE":
            raise ValueError("clause_concat_requires_pcm_wav")
        if stream.getnchannels() != 1 or stream.getsampwidth() != 2:
            raise ValueError("clause_concat_requires_mono_pcm16")
        sample_rate = int(stream.getframerate())
        frames = stream.readframes(stream.getnframes())
    samples = array("h")
    samples.frombytes(frames)
    return sample_rate, samples


def _encode_pcm16_mono_wav(sample_rate: int, samples: "array[int]") -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(sample_rate)
        stream.writeframes(samples.tobytes())
    return buffer.getvalue()


def crossfade_join_pcm16(
    clause_wavs: list[bytes], *, crossfade_ms: float
) -> bytes:
    """Linear-crossfade concatenate mono PCM16 clause WAVs into one WAV.

    A short (150-250 ms) crossfade at each join removes the click of a hard cut
    while staying comfortably below the locked 2.0 s internal-silence ceiling.
    """
    if not 150.0 <= float(crossfade_ms) <= 250.0:
        raise ValueError(f"clause_concat_crossfade_out_of_range:{crossfade_ms}")
    if not clause_wavs:
        raise ValueError("clause_concat_no_clauses")
    sample_rate, out = _decode_pcm16_mono_wav(clause_wavs[0])
    fade = max(1, int(round(sample_rate * float(crossfade_ms) / 1000.0)))
    for wav_bytes in clause_wavs[1:]:
        rate, nxt = _decode_pcm16_mono_wav(wav_bytes)
        if rate != sample_rate:
            raise ValueError("clause_concat_sample_rate_mismatch")
        overlap = min(fade, len(out), len(nxt))
        if overlap <= 0:
            out.extend(nxt)
            continue
        base = len(out) - overlap
        for i in range(overlap):
            weight = (i + 1) / (overlap + 1)
            mixed = out[base + i] * (1.0 - weight) + nxt[i] * weight
            out[base + i] = int(max(-32768, min(32767, round(mixed))))
        out.extend(nxt[overlap:])
    return _encode_pcm16_mono_wav(sample_rate, out)


def assemble_clause_concatenation(
    clause_wavs: list[bytes], *, crossfade_ms: float = 200.0
) -> tuple[bytes, dict[str, Any]]:
    """Join per-clause WAVs and return the audio plus assembly provenance."""
    joined = crossfade_join_pcm16(clause_wavs, crossfade_ms=crossfade_ms)
    provenance = {
        "schema": "embry.audio_e2e.clause_concatenation.v1",
        "asset_assembly": "clause_concatenation",
        "source_text_unchanged": True,
        "clause_count": len(clause_wavs),
        "crossfade_ms": float(crossfade_ms),
        "join_method": "linear_crossfade_pcm16_v1",
    }
    return joined, provenance


def qualification_rejection_reasons(
    *,
    wer: float,
    boundary: dict[str, Any],
    qualification_policy: dict[str, Any],
    truncation: dict[str, Any] | None = None,
) -> list[str]:
    reasons: list[str] = []
    # Infrastructure failure first: a truncated generation is rejected before it
    # can consume a quality candidate slot (see qualify_turn_asset).
    if truncation is not None and bool(truncation.get("truncated")):
        reasons.append("tts_generation_truncated")
    if wer > float(qualification_policy["max_request_wer"]):
        reasons.append("wer_exceeds_threshold")
    if not bool(boundary.get("accepted")):
        reasons.append("internal_silence_exceeds_listener_boundary")
    return reasons


def build_qualification_policy(
    *,
    model: str,
    device: str,
    compute_type: str,
    max_request_wer: float,
    max_candidates: int,
    max_internal_silence_seconds: float,
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
    value = {
        "schema": QUALIFICATION_POLICY_SCHEMA,
        "model": model,
        "device": device,
        "compute_type": compute_type,
        "language": "en",
        "beam_size": 5,
        "vad_filter": True,
        "max_request_wer": max_request_wer,
        "max_candidates": max_candidates,
        "normalization": "lowercase_ascii_alnum_emotion_tag_stripped_tokens_v2",
        "wer_algorithm": "token_levenshtein_v1",
        "initial_prompt_used": False,
        "utterance_boundary": _utterance_boundary_policy(
            max_internal_silence_seconds
        ),
    }
    value["identity_sha256"] = sha256_bytes(canonical_json(value))
    return value


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

    def transcribe(
        self,
        audio_path: Path,
        *,
        receipt_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
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
            "policy": dict(receipt_policy or self.policy),
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
    # Scale the decode budget with prompt length: slow-prosody tags (<yawn>)
    # stretch seconds-per-word, and the server's default budget truncated long
    # sentences mid-utterance. Bounds follow the SynthesizeRequest schema.
    #
    # VERIFIED DEPLOYED CEILING (2026-07-19): the orpheus-infer image bakes
    # /app/inference_server.py with ``max_new_tokens: int | None = Field(..., le=1200)``
    # -- the server rejects any request above 1200 with HTTP 422, and its
    # synthesis receipt exposes no finish_reason/stop_reason/token counts. The
    # oracle's "raise to ~1800" is therefore NOT available client-side without
    # rebuilding that image; raising the cap here would only produce 422s. The
    # in-repo, durable lever for sentences that still exhaust 1200 tokens is the
    # clause-concatenation fallback (see assemble_clause_concatenation) plus the
    # audio-side truncation detector (see detect_generation_truncation), which
    # rejects a truncated candidate as infrastructure failure without spending a
    # quality slot.
    max_new_tokens = min(1200, max(400, 40 * len(prompt.split())))
    return {
        "prompt": prompt,
        "speaker": generation_policy["speaker"],
        "load_in_4bit": generation_policy["load_in_4bit"],
        "min_duration_sec": generation_policy["min_duration_sec"],
        "max_new_tokens": max_new_tokens,
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
    declared_policy = value.get("spoken_text_normalization")
    expected_policy = {
        **SPOKEN_TEXT_NORMALIZATION,
        "sha256": SPOKEN_TEXT_NORMALIZATION_SHA256,
    }
    if declared_policy != expected_policy:
        raise ValueError("campaign_spoken_text_normalization_policy_invalid")
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
        if case.get("spoken_text_normalization_sha256") != SPOKEN_TEXT_NORMALIZATION_SHA256:
            raise ValueError(f"campaign_case_spoken_text_policy_mismatch:{case_id}")
        contract_material = {
            key: item for key, item in case.items() if key != "contract_sha256"
        }
        if case.get("contract_sha256") != sha256_value(contract_material):
            raise ValueError(f"campaign_case_contract_hash_mismatch:{case_id}")
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
            display_text = str(turn.get("display_text") or "")
            utterance = str(turn.get("utterance") or "")
            if not display_text or display_text != utterance:
                raise ValueError(f"campaign_turn_canonical_text_mismatch:{turn_id}")
            if turn.get("utterance_sha256") != sha256_value(utterance):
                raise ValueError(f"campaign_turn_utterance_hash_mismatch:{turn_id}")
            if turn.get("display_text_sha256") != sha256_value(display_text):
                raise ValueError(f"campaign_turn_display_text_hash_mismatch:{turn_id}")
            if turn.get("spoken_text_normalization_sha256") != SPOKEN_TEXT_NORMALIZATION_SHA256:
                raise ValueError(f"campaign_turn_spoken_text_policy_mismatch:{turn_id}")
            derived_spoken_text = derive_spoken_text(display_text)
            if spoken_text != derived_spoken_text:
                raise ValueError(f"campaign_turn_spoken_text_derivation_mismatch:{turn_id}")
            tone_family = str(turn.get("tone_family") or "")
            if tone_family not in TONE_PROSODY_MAP["families"]:
                raise ValueError(
                    f"campaign_turn_tone_family_invalid:{turn_id}:{tone_family}"
                )
            if turn.get("tone_prosody_map_sha256") != TONE_PROSODY_MAP_SHA256:
                raise ValueError(
                    f"campaign_turn_tone_prosody_map_mismatch:{turn_id}"
                )
            minimum_tag_count = int(
                turn.get("minimum_inline_emotion_tag_count", 1) or 1
            )
            family_tags = list(
                TONE_PROSODY_MAP["families"][tone_family]["orpheus_tags"]
            )
            declared_tags = turn.get("inline_emotion_tags")
            if not isinstance(declared_tags, list) or declared_tags != family_tags:
                raise ValueError(
                    f"campaign_turn_inline_emotion_tags_mismatch:{turn_id}"
                )
            if len(declared_tags) < minimum_tag_count:
                raise ValueError(
                    f"campaign_turn_inline_emotion_tag_count_below_minimum:{turn_id}"
                )
            synthesis_spoken_text = str(turn.get("synthesis_spoken_text") or "")
            if not synthesis_spoken_text:
                raise ValueError(
                    f"campaign_turn_synthesis_spoken_text_missing:{turn_id}"
                )
            derived_synthesis_spoken_text = synthesis_text_for_family(
                derived_spoken_text,
                tone_family,
                str(case.get("folder_id") or ""),
                minimum_tag_count=minimum_tag_count,
            )
            if synthesis_spoken_text != derived_synthesis_spoken_text:
                raise ValueError(
                    f"campaign_turn_synthesis_spoken_text_derivation_mismatch:{turn_id}"
                )
            if turn.get("synthesis_spoken_text_sha256") != sha256_value(
                synthesis_spoken_text
            ):
                raise ValueError(
                    f"campaign_turn_synthesis_spoken_text_hash_mismatch:{turn_id}"
                )
            spoken_hash = declared_spoken_hash(turn, spoken_text)
            # The synthesized (and therefore ASR-compared) query carries the
            # tone tags; the WER normalizer strips them so comparison remains
            # against the plain words only.
            query = strip_leading_wake_phrase(synthesis_spoken_text)
            normalized_turns.append(
                {
                    "case_id": case_id,
                    "turn_id": turn_id,
                    "spoken_text": spoken_text,
                    "synthesis_spoken_text": synthesis_spoken_text,
                    "tone_family": tone_family,
                    "inline_emotion_tags": list(declared_tags),
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


def archive_conflict(asset_dir: Path, archive_root: Path) -> Path | None:
    if not asset_dir.exists():
        return None
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
    return target


def _binding_wer(binding: dict[str, Any], *, binding_path: Path) -> float:
    try:
        value = float((binding.get("qualification") or {})["wer"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AssetConflictError(
            f"accepted_binding_wer_missing:{binding_path}"
        ) from exc
    if not 0.0 <= value <= 1.0:
        raise AssetConflictError(
            f"accepted_binding_wer_out_of_range:{binding_path}:{value}"
        )
    return value


def _runtime_stability_regeneration_receipt(
    *,
    case_id: str,
    turn_id: str,
    threshold: float,
    archived_dir: Path,
    old_binding_path: Path,
    old_binding: dict[str, Any],
    new_bundle: dict[str, Any],
    runtime_policy: dict[str, Any],
    reason: str = "accepted_asset_wer_above_campaign_runtime_stability_ceiling",
    require_old_above_threshold: bool = True,
) -> dict[str, Any]:
    archived_binding = archived_dir / old_binding_path.name
    new_binding_path = verify_locator(
        new_bundle["inference_receipt"], label="runtime_stability_new_binding"
    )
    new_binding = read_json(new_binding_path)
    old_wer = _binding_wer(old_binding, binding_path=archived_binding)
    new_wer = _binding_wer(new_binding, binding_path=new_binding_path)
    if (require_old_above_threshold and old_wer <= threshold) or new_wer > threshold:
        raise RuntimeError(
            f"runtime_stability_regeneration_gate_failed:{turn_id}:"
            f"{old_wer}:{new_wer}:{threshold}"
        )
    value = {
        "schema": "embry.audio_e2e.runtime_stability_regeneration.v1",
        "status": "PASS",
        "live": True,
        "mocked": False,
        "case_id": case_id,
        "turn_id": turn_id,
        "reason": reason,
        "runtime_stability_policy": runtime_policy,
        "old": {
            "wer": old_wer,
            "audio": old_binding["audio"],
            "binding": locator(archived_binding),
            "request_id": old_binding["request_id"],
        },
        "new": {
            "wer": new_wer,
            "audio": new_binding["audio"],
            "binding": locator(new_binding_path),
            "request_id": new_binding["request_id"],
        },
        "provider_called": True,
        "failed_gates": [],
    }
    receipt_path = new_binding_path.parent / "runtime-stability-regeneration.json"
    atomic_write_json(receipt_path, value)
    return locator(receipt_path)


def _compatible_existing_qualification_policy(
    existing: Any,
    base: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(existing, dict):
        return None
    try:
        existing_max = float(existing["max_request_wer"])
    except (KeyError, TypeError, ValueError):
        return None
    if not 0.0 <= existing_max <= float(base["max_request_wer"]):
        return None
    expected = build_qualification_policy(
        model=base["model"],
        device=base["device"],
        compute_type=base["compute_type"],
        max_request_wer=existing_max,
        max_candidates=base["max_candidates"],
        max_internal_silence_seconds=base["utterance_boundary"][
            "max_internal_silence_seconds"
        ],
    )
    return existing if existing == expected else None



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
    comparison = compare_asr_text(
        prompt,
        transcript,
        strip_expected_wake=False,
    )
    stored_comparison = value.get("asr_comparison")
    computed_wer = float(
        comparison["comparison_wer"]
        if stored_comparison is not None
        else comparison["raw_wer"]
    )
    if stored_comparison is not None:
        if stored_comparison != comparison:
            raise AssetConflictError("candidate_asr_comparison_mismatch")
        if abs(float(value.get("raw_wer", -1.0)) - comparison["raw_wer"]) > 1e-12:
            raise AssetConflictError("candidate_asr_raw_wer_mismatch")
        if abs(
            float(value.get("comparison_wer", -1.0))
            - comparison["comparison_wer"]
        ) > 1e-12:
            raise AssetConflictError("candidate_asr_comparison_wer_mismatch")
    try:
        stored_wer = float(value["wer"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AssetConflictError("candidate_asr_wer_missing") from exc
    if abs(stored_wer - computed_wer) > 1e-12:
        raise AssetConflictError("candidate_asr_wer_mismatch")

    boundary = analyze_internal_silence(
        audio_path,
        qualification_policy["utterance_boundary"],
    )
    if value.get("utterance_boundary") != boundary:
        raise AssetConflictError(
            "candidate_asr_utterance_boundary_mismatch"
        )
    recomputed_truncation = detect_generation_truncation(boundary)
    stored_truncation = value.get("generation_truncation")
    if stored_truncation is not None:
        # Receipt written with truncation telemetry: it must reproduce exactly.
        if stored_truncation != recomputed_truncation:
            raise AssetConflictError("candidate_asr_generation_truncation_mismatch")
        truncation_for_reasons: dict[str, Any] | None = recomputed_truncation
    else:
        # Legacy receipt written before truncation telemetry existed: reproduce
        # its original classification (truncation was not a factor) so already
        # qualified assets are never retroactively invalidated on resume.
        truncation_for_reasons = None
    reasons = qualification_rejection_reasons(
        wer=computed_wer,
        boundary=boundary,
        qualification_policy=qualification_policy,
        truncation=truncation_for_reasons,
    )
    accepted = not reasons
    if value.get("rejection_reasons") != reasons:
        raise AssetConflictError(
            "candidate_asr_rejection_reasons_mismatch"
        )
    if value.get("rejection_reason") != (reasons[0] if reasons else None):
        raise AssetConflictError(
            "candidate_asr_rejection_reason_mismatch"
        )
    if value.get("accepted") is not accepted:
        raise AssetConflictError("candidate_asr_acceptance_mismatch")
    value["computed_wer"] = computed_wer
    value["computed_utterance_boundary"] = boundary
    value["computed_generation_truncation"] = recomputed_truncation
    value["computed_rejection_reasons"] = reasons
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
    comparison_policy = receipt.get("asr_comparison_policy")
    if comparison_policy is not None and comparison_policy != {
        **ASR_COMPARISON_POLICY,
        "sha256": ASR_COMPARISON_POLICY_SHA256,
    }:
        raise AssetConflictError("candidate_asr_comparison_policy_mismatch")
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
    boundary = asr["computed_utterance_boundary"]
    reasons = list(asr["computed_rejection_reasons"])
    try:
        stored_wer = float(receipt["wer"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AssetConflictError("candidate_wer_missing") from exc
    if abs(stored_wer - computed_wer) > 1e-12:
        raise AssetConflictError("candidate_wer_mismatch")
    if receipt.get("transcript") != asr.get("transcript"):
        raise AssetConflictError("candidate_transcript_mismatch")
    if receipt.get("utterance_boundary") != boundary:
        raise AssetConflictError("candidate_utterance_boundary_mismatch")
    if receipt.get("rejection_reasons") != reasons:
        raise AssetConflictError("candidate_rejection_reasons_mismatch")
    if receipt.get("rejection_reason") != (reasons[0] if reasons else None):
        raise AssetConflictError("candidate_rejection_reason_mismatch")
    longest_internal_silence = float(
        boundary["longest_internal_silence_seconds"]
    )
    try:
        stored_internal_silence = float(
            receipt["longest_internal_silence_seconds"]
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise AssetConflictError(
            "candidate_internal_silence_missing"
        ) from exc
    if abs(stored_internal_silence - longest_internal_silence) > 1e-12:
        raise AssetConflictError(
            "candidate_internal_silence_mismatch"
        )
    accepted = not reasons
    if accepted != (status == "ACCEPTED"):
        raise AssetConflictError("candidate_acceptance_mismatch")
    return {
        "status": status,
        "candidate_index": candidate_index,
        "wer": computed_wer,
        "raw_wer": float(asr.get("raw_wer", computed_wer)),
        "comparison_wer": float(asr.get("comparison_wer", computed_wer)),
        "asr_comparison": asr.get("asr_comparison"),
        "longest_internal_silence_seconds": longest_internal_silence,
        "utterance_boundary": boundary,
        "rejection_reasons": reasons,
        "rejection_reason": reasons[0] if reasons else None,
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


def _qualification_policy_archive_id(value: Any) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()[:16]


def _archive_qualification_artifact(
    *,
    path: Path,
    asset_dir: Path,
    archive_root: Path,
    case_id: str,
    turn_id: str,
    prior_policy: Any,
) -> None:
    if not path.exists():
        return
    if not path.is_file():
        raise AssetConflictError(
            f"qualification_artifact_not_file:{path}"
        )
    relative = path.relative_to(asset_dir)
    target = (
        archive_root
        / "qualification-policy"
        / safe_component(case_id)
        / safe_component(turn_id)
        / _qualification_policy_archive_id(prior_policy)
        / relative
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if not target.is_file() or sha256_file(target) != sha256_file(path):
            raise AssetConflictError(
                f"qualification_archive_conflict:{target}"
            )
        path.unlink()
        return
    shutil.move(str(path), str(target))


def _validate_candidate_provider_artifacts_for_requalification(
    *,
    candidate_dir: Path,
    prompt: str,
    contract_locator: dict[str, str],
    checkpoint_id: str,
    checkpoint_sha256: str,
    case_id: str,
    turn_id: str,
    planned_spoken_text_sha256: str,
    generation_policy: dict[str, Any],
) -> Any:
    paths = _candidate_paths(candidate_dir)
    for key in ("audio", "response", "original"):
        if not paths[key].is_file():
            raise AssetConflictError(
                f"candidate_provider_artifact_missing:{candidate_dir}:{key}"
            )
    validate_wav_envelope(paths["audio"].read_bytes())
    response = read_json(paths["response"])
    _, request_id = _validated_synthesis_payload(response)
    validate_original_inference_receipt(
        read_json(paths["original"]),
        prompt=prompt,
        request_id=request_id,
        generation_policy=generation_policy,
    )

    receipt_path = paths["receipt"]
    if not receipt_path.is_file():
        return None
    receipt = read_json(receipt_path)
    required = {
        "schema": CANDIDATE_RECEIPT_SCHEMA,
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
        "request": request_for_prompt(prompt, generation_policy),
    }
    for key, expected in required.items():
        if receipt.get(key) != expected:
            raise AssetConflictError(
                "candidate_provider_receipt_conflict:"
                f"{candidate_dir}:{key}:"
                f"{receipt.get(key)!r}:{expected!r}"
            )
    checkpoint = receipt.get("checkpoint") or {}
    if checkpoint.get("id") != checkpoint_id:
        raise AssetConflictError(
            "candidate_provider_checkpoint_id_mismatch"
        )
    if normalize_sha256(
        checkpoint.get("sha256"),
        label="candidate_provider_checkpoint",
    ) != checkpoint_sha256:
        raise AssetConflictError(
            "candidate_provider_checkpoint_hash_mismatch"
        )
    if receipt.get("audio") != locator(paths["audio"]):
        raise AssetConflictError(
            "candidate_provider_audio_locator_mismatch"
        )
    if receipt.get("synthesis_response") != locator(paths["response"]):
        raise AssetConflictError(
            "candidate_provider_response_locator_mismatch"
        )
    if receipt.get("original_inference_receipt") != locator(
        paths["original"]
    ):
        raise AssetConflictError(
            "candidate_provider_original_locator_mismatch"
        )
    if normalize_sha256(
        receipt.get("generated_audio_sha256"),
        label="candidate_provider_audio",
    ) != sha256_file(paths["audio"]):
        raise AssetConflictError(
            "candidate_provider_audio_hash_mismatch"
        )
    if str(receipt.get("request_id") or "") != request_id:
        raise AssetConflictError(
            "candidate_provider_request_id_mismatch"
        )
    return receipt.get("qualification_policy")


def migrate_qualification_policy_conflicts(
    *,
    asset_dir: Path,
    archive_root: Path,
    prompt: str,
    contract_locator: dict[str, str],
    checkpoint_id: str,
    checkpoint_sha256: str,
    case_id: str,
    turn_id: str,
    planned_spoken_text_sha256: str,
    generation_policy: dict[str, Any],
    qualification_policy: dict[str, Any],
) -> bool:
    """Archive only derived qualification state and retain provider assets."""

    if not asset_dir.exists():
        return False
    migrated = False
    candidate_migrated = False
    binding_path = asset_dir / "binding-receipt.json"
    binding = read_json(binding_path) if binding_path.is_file() else None
    binding_prior_policy = (
        binding.get("qualification_policy")
        if isinstance(binding, dict)
        else None
    )

    candidates_root = asset_dir / "candidates"
    if candidates_root.is_dir():
        for candidate_dir in sorted(candidates_root.iterdir()):
            if not candidate_dir.is_dir() or not re.fullmatch(
                r"candidate-\d{3}", candidate_dir.name
            ):
                continue
            paths = _candidate_paths(candidate_dir)
            if not any(path.exists() for path in paths.values()):
                continue
            # Response-only and provider-only crash states have no derived
            # qualification policy to migrate; complete_candidate resumes them.
            if not paths["asr"].exists() and not paths["receipt"].exists():
                continue
            prior_policy = _validate_candidate_provider_artifacts_for_requalification(
                candidate_dir=candidate_dir,
                prompt=prompt,
                contract_locator=contract_locator,
                checkpoint_id=checkpoint_id,
                checkpoint_sha256=checkpoint_sha256,
                case_id=case_id,
                turn_id=turn_id,
                planned_spoken_text_sha256=planned_spoken_text_sha256,
                generation_policy=generation_policy,
            )
            if prior_policy == qualification_policy:
                continue
            for derived in (paths["asr"], paths["receipt"]):
                _archive_qualification_artifact(
                    path=derived,
                    asset_dir=asset_dir,
                    archive_root=archive_root,
                    case_id=case_id,
                    turn_id=turn_id,
                    prior_policy=prior_policy,
                )
            migrated = True
            candidate_migrated = True

    if binding_path.is_file() and (
        binding_prior_policy != qualification_policy
        or candidate_migrated
    ):
        _archive_qualification_artifact(
            path=binding_path,
            asset_dir=asset_dir,
            archive_root=archive_root,
            case_id=case_id,
            turn_id=turn_id,
            prior_policy=binding_prior_policy,
        )
        migrated = True

    exhaustion_path = asset_dir / "qualification-exhausted.json"
    if exhaustion_path.is_file():
        exhaustion = read_json(exhaustion_path)
        prior_policy = exhaustion.get("qualification_policy")
        if prior_policy != qualification_policy:
            _archive_qualification_artifact(
                path=exhaustion_path,
                asset_dir=asset_dir,
                archive_root=archive_root,
                case_id=case_id,
                turn_id=turn_id,
                prior_policy=prior_policy,
            )
            migrated = True
    return migrated


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
        asr = qualifier.transcribe(
            paths["audio"], receipt_policy=qualification_policy
        )
        asr["expected_text"] = prompt
        asr["expected_text_sha256"] = sha256_text(prompt)
        asr["normalized_expected_text"] = " ".join(
            normalized_tokens(prompt)
        )
        comparison = compare_asr_text(
            prompt,
            str(asr.get("transcript") or ""),
            strip_expected_wake=False,
        )
        asr["raw_wer"] = comparison["raw_wer"]
        asr["comparison_wer"] = comparison["comparison_wer"]
        asr["wer"] = comparison["comparison_wer"]
        asr["asr_comparison"] = comparison
        boundary = analyze_internal_silence(
            paths["audio"],
            qualification_policy["utterance_boundary"],
        )
        asr["utterance_boundary"] = boundary
        truncation = detect_generation_truncation(boundary)
        asr["generation_truncation"] = truncation
        reasons = qualification_rejection_reasons(
            wer=float(asr["wer"]),
            boundary=boundary,
            qualification_policy=qualification_policy,
            truncation=truncation,
        )
        asr["rejection_reasons"] = reasons
        asr["rejection_reason"] = reasons[0] if reasons else None
        asr["accepted"] = not reasons
        atomic_write_json(paths["asr"], asr)
        asr["computed_wer"] = float(asr["wer"])
        asr["computed_utterance_boundary"] = boundary
        asr["computed_generation_truncation"] = truncation
        asr["computed_rejection_reasons"] = reasons

    computed_wer = float(asr["computed_wer"])
    boundary = asr["computed_utterance_boundary"]
    truncation = asr.get("computed_generation_truncation")
    if truncation is None:
        # Resumed asr receipt written before truncation telemetry existed:
        # derive it from the persisted boundary for the candidate receipt only.
        truncation = detect_generation_truncation(boundary)
    # ``computed_rejection_reasons`` is authoritative: the fresh-write path and
    # _validate_asr_receipt already fold in truncation (respecting legacy
    # receipts), so we never re-prepend it here.
    reasons = list(asr["computed_rejection_reasons"])
    accepted = not reasons
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
        "asr_comparison_policy": {
            **ASR_COMPARISON_POLICY,
            "sha256": ASR_COMPARISON_POLICY_SHA256,
        },
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
        "raw_wer": float(asr.get("raw_wer", computed_wer)),
        "comparison_wer": float(asr.get("comparison_wer", computed_wer)),
        "asr_comparison": asr.get("asr_comparison"),
        "max_request_wer": qualification_policy["max_request_wer"],
        "utterance_boundary": boundary,
        "longest_internal_silence_seconds": boundary[
            "longest_internal_silence_seconds"
        ],
        "max_internal_silence_seconds": qualification_policy[
            "utterance_boundary"
        ]["max_internal_silence_seconds"],
        "generation_truncation": truncation,
        "rejection_reasons": reasons,
        "rejection_reason": reasons[0] if reasons else None,
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
        "asr_comparison_policy": {
            **ASR_COMPARISON_POLICY,
            "sha256": ASR_COMPARISON_POLICY_SHA256,
        },
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
            "raw_wer": accepted["raw_wer"],
            "comparison_wer": accepted["comparison_wer"],
            "asr_comparison": accepted["asr_comparison"],
            "max_request_wer": qualification_policy["max_request_wer"],
            "asr_model": qualification_policy["model"],
            "asr_device": qualification_policy["device"],
            "asr_compute_type": qualification_policy["compute_type"],
            "asr_receipt": accepted["asr"],
            "utterance_boundary": accepted["utterance_boundary"],
            "longest_internal_silence_seconds": accepted[
                "longest_internal_silence_seconds"
            ],
            "max_internal_silence_seconds": qualification_policy[
                "utterance_boundary"
            ]["max_internal_silence_seconds"],
            "rejection_reasons": [],
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
    comparison_policy = binding.get("asr_comparison_policy")
    if comparison_policy is not None and comparison_policy != {
        **ASR_COMPARISON_POLICY,
        "sha256": ASR_COMPARISON_POLICY_SHA256,
    }:
        raise AssetConflictError("accepted_binding_asr_comparison_policy_mismatch")
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
    boundary_limit = qualification_policy["utterance_boundary"][
        "max_internal_silence_seconds"
    ]
    if candidate["longest_internal_silence_seconds"] >= boundary_limit:
        raise AssetConflictError(
            "accepted_binding_internal_silence_exceeds_threshold"
        )
    if qualification.get("utterance_boundary") != candidate[
        "utterance_boundary"
    ]:
        raise AssetConflictError(
            "accepted_binding_utterance_boundary_mismatch"
        )
    if abs(
        float(
            qualification.get(
                "longest_internal_silence_seconds", -1.0
            )
        )
        - candidate["longest_internal_silence_seconds"]
    ) > 1e-12:
        raise AssetConflictError(
            "accepted_binding_internal_silence_mismatch"
        )
    if qualification.get("rejection_reasons") != []:
        raise AssetConflictError(
            "accepted_binding_rejection_reasons_not_empty"
        )
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


# A truncated generation (server cut the audio at the token budget mid-word) is
# an infrastructure failure, not an unsuccessful pronunciation sample, so it must
# not consume one of the ``max_candidates`` quality slots. These extra attempts
# are granted, bounded, on top of the quality budget.
TRUNCATION_RETRY_BUDGET = 3


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
    max_candidates = int(qualification_policy["max_candidates"])
    hard_cap = max_candidates + TRUNCATION_RETRY_BUDGET
    quality_slots_consumed = 0
    truncated_candidate_count = 0
    candidate_index = 0
    while quality_slots_consumed < max_candidates and candidate_index < hard_cap:
        candidate_index += 1
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
        generation_truncated = (
            "tts_generation_truncated" in candidate["rejection_reasons"]
        )
        print(
            json.dumps(
                {
                    "status": (
                        "CANDIDATE_ACCEPTED"
                        if candidate["status"] == "ACCEPTED"
                        else "CANDIDATE_TRUNCATED"
                        if generation_truncated
                        else "CANDIDATE_REJECTED"
                    ),
                    "case_id": case_id,
                    "turn_id": turn_id,
                    "candidate_index": candidate_index,
                    "quality_slots_consumed": quality_slots_consumed,
                    "generation_truncated": generation_truncated,
                    "transcript": candidate["transcript"],
                    "wer": candidate["wer"],
                    "max_request_wer": qualification_policy[
                        "max_request_wer"
                    ],
                    "longest_internal_silence_seconds": candidate[
                        "longest_internal_silence_seconds"
                    ],
                    "max_internal_silence_seconds": qualification_policy[
                        "utterance_boundary"
                    ]["max_internal_silence_seconds"],
                    "rejection_reasons": candidate[
                        "rejection_reasons"
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
        # Every rejected candidate is recorded for provenance, but a truncated
        # generation is an infrastructure failure that must NOT consume one of
        # the quality candidate slots (oracle Class A). It instead draws from the
        # bounded TRUNCATION_RETRY_BUDGET via the hard cap on candidate_index.
        rejected_receipts.append(candidate["receipt"])
        if generation_truncated:
            truncated_candidate_count += 1
        else:
            quality_slots_consumed += 1

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
        "quality_slots_consumed": quality_slots_consumed,
        "truncated_candidate_count": truncated_candidate_count,
        "truncation_retry_budget": TRUNCATION_RETRY_BUDGET,
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
    policy_migrated = False
    if regenerate_conflicts:
        try:
            policy_migrated = migrate_qualification_policy_conflicts(
                asset_dir=asset_dir,
                archive_root=archive_root,
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
        except (AssetConflictError, ValueError, FileNotFoundError):
            archive_conflict(asset_dir, archive_root)
            asset_dir.mkdir(parents=True, exist_ok=True)

    try:
        bundle, action = _prepare_one_asset_once(
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
        if policy_migrated and action in {
            "QUALIFIED_FROM_RESUME",
            "REUSED",
        }:
            action = "REQUALIFIED_FROM_IMMUTABLE_PROVIDER"
        return bundle, action
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
    campaign_runtime_stability_max_wer: float | None = None,
    max_candidates: int = 5,
    max_internal_silence_seconds: float = 2.0,
    regenerate_conflicts: bool = False,
    regenerate_marginal_assets: bool = False,
    regenerate_turn_ids: tuple[str, ...] = (),
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
        max_internal_silence_seconds=(
            max_internal_silence_seconds
        ),
    )
    requested_regeneration_turn_ids = {
        str(value).strip() for value in regenerate_turn_ids if str(value).strip()
    }
    if (
        regenerate_marginal_assets or requested_regeneration_turn_ids
    ) and campaign_runtime_stability_max_wer is None:
        raise ValueError(
            "campaign_runtime_stability_max_wer_required_for_marginal_regeneration"
        )
    runtime_stability_policy: dict[str, Any] | None = None
    runtime_qualification_policy: dict[str, Any] | None = None
    if campaign_runtime_stability_max_wer is not None:
        stability_max_wer = float(campaign_runtime_stability_max_wer)
        if not 0.0 <= stability_max_wer <= max_request_wer:
            raise ValueError("campaign_runtime_stability_max_wer_out_of_range")
        runtime_stability_policy = {
            "schema": "embry.audio_e2e.runtime_stability_policy.v1",
            "selection": (
                "explicit_turn_ids"
                if requested_regeneration_turn_ids
                else "existing_binding_qualification_wer_strictly_greater_than"
            ),
            "selected_turn_ids": sorted(requested_regeneration_turn_ids),
            "max_request_wer": stability_max_wer,
            "base_max_request_wer": float(max_request_wer),
            "max_candidates": int(max_candidates),
        }
        runtime_stability_policy["identity_sha256"] = sha256_bytes(
            canonical_json(runtime_stability_policy)
        )
        runtime_qualification_policy = build_qualification_policy(
            model=qualification_model,
            device=qualification_device,
            compute_type=qualification_compute_type,
            max_request_wer=stability_max_wer,
            max_candidates=max_candidates,
            max_internal_silence_seconds=max_internal_silence_seconds,
        )

    manifest = read_json(manifest_path)
    cases = validate_campaign_manifest(manifest)
    manifest_turn_ids = {
        turn["turn_id"] for case in cases for turn in case["turns"]
    }
    unknown_regeneration_turn_ids = (
        requested_regeneration_turn_ids - manifest_turn_ids
    )
    if unknown_regeneration_turn_ids:
        raise ValueError(
            "regenerate_turn_id_unknown:"
            + ",".join(sorted(unknown_regeneration_turn_ids))
        )
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
    per_turn_qualification_policy: dict[str, dict[str, Any]] = {}
    runtime_regeneration_receipts: list[dict[str, str]] = []

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
                asset_dir = (
                    output_dir
                    / "cases"
                    / safe_component(case_id)
                    / "turns"
                    / safe_component(turn_id)
                )
                turn_qualification_policy = qualification_policy
                marginal_archive: tuple[Path, Path, dict[str, Any]] | None = None
                binding_path = asset_dir / "binding-receipt.json"
                exact_regeneration_selected = (
                    turn_id in requested_regeneration_turn_ids
                )
                runtime_archive_parent = (
                    archive_root
                    / "runtime-stability"
                    / safe_component(asset_dir.name)
                )
                if runtime_qualification_policy is not None and binding_path.is_file():
                    existing_binding = read_json(binding_path)
                    existing_wer = _binding_wer(
                        existing_binding, binding_path=binding_path
                    )
                    if exact_regeneration_selected and (
                        existing_binding.get("qualification_policy")
                        == runtime_qualification_policy
                    ):
                        turn_qualification_policy = runtime_qualification_policy
                    elif exact_regeneration_selected or (
                        regenerate_marginal_assets
                        and existing_wer
                        > runtime_qualification_policy["max_request_wer"]
                    ):
                        old_binding = existing_binding
                        old_binding_name = binding_path.name
                        archived_dir = archive_conflict(
                            asset_dir,
                            archive_root / "runtime-stability",
                        )
                        if archived_dir is None:
                            raise RuntimeError(
                                f"marginal_asset_archive_missing:{case_id}:{turn_id}"
                            )
                        marginal_archive = (
                            archived_dir,
                            archived_dir / old_binding_name,
                            old_binding,
                        )
                        turn_qualification_policy = runtime_qualification_policy
                    else:
                        compatible_policy = (
                            _compatible_existing_qualification_policy(
                                existing_binding.get("qualification_policy"),
                                qualification_policy,
                            )
                        )
                        if compatible_policy is not None:
                            turn_qualification_policy = compatible_policy
                elif runtime_qualification_policy is not None and (
                    exact_regeneration_selected or regenerate_marginal_assets
                ):
                    archived_runtime_bindings = sorted(
                        runtime_archive_parent.glob("*/binding-receipt.json")
                    )
                    if len(archived_runtime_bindings) > 1:
                        raise RuntimeError(
                            "multiple_runtime_stability_archives:"
                            f"{case_id}:{turn_id}"
                        )
                    if archived_runtime_bindings:
                        archived_binding_path = archived_runtime_bindings[0]
                        marginal_archive = (
                            archived_binding_path.parent,
                            archived_binding_path,
                            read_json(archived_binding_path),
                        )
                        turn_qualification_policy = runtime_qualification_policy
                per_turn_qualification_policy[turn_id] = turn_qualification_policy
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
                    asset_dir=asset_dir,
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
                    qualification_policy=turn_qualification_policy,
                    regenerate_conflicts=(
                        regenerate_conflicts
                        or (marginal_archive is not None and asset_dir.exists())
                    ),
                )
                if marginal_archive is not None:
                    archived_dir, archived_binding, old_binding = marginal_archive
                    runtime_regeneration_receipts.append(
                        _runtime_stability_regeneration_receipt(
                            case_id=case_id,
                            turn_id=turn_id,
                            threshold=runtime_qualification_policy["max_request_wer"],
                            archived_dir=archived_dir,
                            old_binding_path=archived_binding,
                            old_binding=old_binding,
                            new_bundle=bundle,
                            runtime_policy=runtime_stability_policy,
                            reason=(
                                "managed_listener_runtime_transcript_failed"
                                if exact_regeneration_selected
                                else "accepted_asset_wer_above_campaign_"
                                "runtime_stability_ceiling"
                            ),
                            require_old_above_threshold=(
                                not exact_regeneration_selected
                            ),
                        )
                    )
                    action = "REGENERATED_FOR_RUNTIME_STABILITY"
                else:
                    existing_regeneration_receipt = (
                        asset_dir / "runtime-stability-regeneration.json"
                    )
                    if existing_regeneration_receipt.is_file():
                        runtime_regeneration_receipts.append(
                            locator(existing_regeneration_receipt)
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
                            "qualification_policy": turn_qualification_policy,
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
    accepted_internal_silences: list[float] = []
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
            turn_qualification_policy = per_turn_qualification_policy[turn["turn_id"]]
            if binding.get("qualification_policy") != turn_qualification_policy:
                raise RuntimeError(
                    "prepared_binding_qualification_policy_mismatch:"
                    f"{turn['turn_id']}"
                )
            qualification = binding.get("qualification") or {}
            wer = float(qualification.get("wer", 2.0))
            if wer > turn_qualification_policy["max_request_wer"]:
                raise RuntimeError(
                    "prepared_binding_wer_exceeds_threshold:"
                    f"{turn['turn_id']}:{wer}"
                )
            boundary = qualification.get("utterance_boundary") or {}
            try:
                internal_silence = float(
                    qualification[
                        "longest_internal_silence_seconds"
                    ]
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise RuntimeError(
                    "prepared_binding_internal_silence_missing:"
                    f"{turn['turn_id']}"
                ) from exc
            if boundary.get("accepted") is not True:
                raise RuntimeError(
                    "prepared_binding_utterance_boundary_not_accepted:"
                    f"{turn['turn_id']}"
                )
            boundary_limit = turn_qualification_policy[
                "utterance_boundary"
            ]["max_internal_silence_seconds"]
            if internal_silence >= boundary_limit:
                raise RuntimeError(
                    "prepared_binding_internal_silence_exceeds_threshold:"
                    f"{turn['turn_id']}:{internal_silence}:"
                    f"{boundary_limit}"
                )
            accepted_wers.append(wer)
            accepted_internal_silences.append(internal_silence)
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
        "runtime_stability_policy": runtime_stability_policy,
        "runtime_stability_regeneration_receipts": runtime_regeneration_receipts,
        "asr_comparison_policy": {
            **ASR_COMPARISON_POLICY,
            "sha256": ASR_COMPARISON_POLICY_SHA256,
        },
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
            "runtime_stability_regenerated_asset_count": len(
                runtime_regeneration_receipts
            ),
            "utterance_boundary_qualified_query_asset_count": len(
                accepted_internal_silences
            ),
            "max_accepted_request_wer": max(accepted_wers, default=0.0),
            "max_accepted_internal_silence_seconds": max(
                accepted_internal_silences,
                default=0.0,
            ),
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
