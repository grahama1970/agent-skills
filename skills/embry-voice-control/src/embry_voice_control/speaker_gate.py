"""Fail-closed resemblyzer speaker gate for the live Embry voice turn.

This module verifies that one captured turn utterance belongs to the enrolled
physical Horus profile before any personal memory is unlocked.  It mirrors the
proven enrollment logic in
``chatterbox/scripts/prove_physical_horus_enrollment.py``:

    profile = normalized(mean(normalized(embed(sample)) for sample in enrollment))

For a live turn the gate embeds the captured utterance, scores it against the
Horus profile (cosine similarity of L2-normalized embeddings, i.e. inner
product), and scores it against the enrolled impostor references.  The turn is
accepted only when BOTH gates pass:

    horus_confidence >= threshold            (default 0.75)
    horus_confidence - best_impostor >= min_margin   (default 0.08)

Any other outcome fails CLOSED: ``speaker_identity_proven`` and
``allow_personal_memory`` are ``False`` and a ``rejection_reason`` is recorded.

``resemblyzer`` and ``numpy`` are imported lazily so this module (and the pure
journal emitters that consume its decision) import and unit-test without the
heavyweight speaker-embedding dependency.  The integration container MUST
provide ``resemblyzer`` and ``numpy`` at runtime.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from loguru import logger

DEFAULT_THRESHOLD = 0.75
DEFAULT_MIN_MARGIN = 0.08
SPEAKER_ID = "horus_lupercal"


def _lazy_encoder(device: str) -> tuple[Any, Any, Any]:
    """Import resemblyzer/numpy lazily and return (encoder, preprocess_wav, np)."""
    try:
        import numpy as np
        from resemblyzer import VoiceEncoder, preprocess_wav
    except ImportError as exc:  # pragma: no cover - exercised only without the dep
        raise RuntimeError(
            "speaker_gate_requires_resemblyzer_and_numpy"
        ) from exc
    return VoiceEncoder(device=device), preprocess_wav, np


def _normalized(vector: Any, np: Any) -> Any:
    norm = float(np.linalg.norm(vector))
    if norm == 0:
        raise ValueError("zero_norm_embedding")
    return vector / norm


def _embed(encoder: Any, preprocess_wav: Any, np: Any, path: Path) -> Any:
    return _normalized(encoder.embed_utterance(preprocess_wav(path)), np)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sample_paths(items: list[dict[str, Any]]) -> list[Path]:
    paths: list[Path] = []
    for item in items:
        raw = item.get("path") or (item.get("audio") or {}).get("path")
        if not raw:
            raise ValueError("enrollment_sample_path_missing")
        paths.append(Path(str(raw)))
    return paths


def build_profile_from_enrollment(
    enrollment_receipt: dict[str, Any],
    *,
    device: str = "cpu",
) -> tuple[Any, str]:
    """Recompute the Horus profile from enrollment samples and verify its hash.

    Returns ``(profile_vector, profile_sha256_hex)``.  Raises if the recomputed
    profile hash does not match the enrolled ``profile_sha256`` recorded in the
    receipt, so a tampered or drifted enrollment cannot silently pass.
    """
    encoder, preprocess_wav, np = _lazy_encoder(device)
    samples = _sample_paths(list(enrollment_receipt.get("enrollment_samples") or []))
    if len(samples) < 3:
        raise ValueError("enrollment_requires_three_samples")
    missing = [str(path) for path in samples if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"enrollment_samples_missing:{missing}")
    embeddings = [_embed(encoder, preprocess_wav, np, path) for path in samples]
    profile = _normalized(np.mean(np.stack(embeddings), axis=0), np)
    profile_hash = hashlib.sha256(profile.astype("float32").tobytes()).hexdigest()
    expected = str(enrollment_receipt.get("profile_sha256") or "").removeprefix("sha256:")
    if expected and profile_hash != expected:
        raise ValueError(f"profile_hash_mismatch:{expected}:{profile_hash}")
    return profile, profile_hash


def verify_turn_speaker(
    *,
    candidate_wav: Path,
    enrollment_receipt: dict[str, Any],
    threshold: float = DEFAULT_THRESHOLD,
    min_margin: float = DEFAULT_MIN_MARGIN,
    device: str = "cpu",
) -> dict[str, Any]:
    """Verify one captured turn utterance against the enrolled Horus profile.

    Fails CLOSED: the returned decision only sets ``accepted``,
    ``speaker_identity_proven`` and ``allow_personal_memory`` to ``True`` when
    the confidence clears the threshold AND the margin over the nearest impostor
    reference clears ``min_margin``.
    """
    candidate_wav = Path(candidate_wav)
    if not candidate_wav.is_file():
        raise FileNotFoundError(f"candidate_wav_missing:{candidate_wav}")
    encoder, preprocess_wav, np = _lazy_encoder(device)

    samples = _sample_paths(list(enrollment_receipt.get("enrollment_samples") or []))
    if len(samples) < 3:
        raise ValueError("enrollment_requires_three_samples")
    profile = _normalized(
        np.mean(np.stack([_embed(encoder, preprocess_wav, np, path) for path in samples]), axis=0),
        np,
    )
    profile_hash = hashlib.sha256(profile.astype("float32").tobytes()).hexdigest()
    expected = str(enrollment_receipt.get("profile_sha256") or "").removeprefix("sha256:")
    if expected and profile_hash != expected:
        raise ValueError(f"profile_hash_mismatch:{expected}:{profile_hash}")

    candidate = _embed(encoder, preprocess_wav, np, candidate_wav)
    horus_confidence = round(float(np.inner(profile, candidate)), 6)

    impostor_candidates: list[dict[str, Any]] = []
    for impostor in enrollment_receipt.get("impostors") or []:
        raw = (impostor.get("audio") or {}).get("path") or impostor.get("path")
        if not raw:
            continue
        path = Path(str(raw))
        if not path.is_file():
            raise FileNotFoundError(f"impostor_reference_missing:{path}")
        reference = _embed(encoder, preprocess_wav, np, path)
        impostor_candidates.append({
            "speaker_id": f"impostor:{impostor.get('role', 'unknown')}",
            "confidence": round(float(np.inner(reference, candidate)), 6),
        })

    best_impostor = max((item["confidence"] for item in impostor_candidates), default=0.0)
    observed_margin = round(horus_confidence - best_impostor, 6)

    reasons: list[str] = []
    if horus_confidence < threshold:
        reasons.append("confidence_below_threshold")
    if observed_margin < min_margin:
        reasons.append("ambiguity_margin_below_minimum")
    accepted = not reasons

    candidates = [{"speaker_id": SPEAKER_ID, "confidence": horus_confidence}, *impostor_candidates]
    decision = {
        "accepted": accepted,
        "speaker_id": SPEAKER_ID,
        "profile_hash": expected or profile_hash,
        "score": horus_confidence,
        "confidence": horus_confidence,
        "threshold": float(threshold),
        "observed_margin": observed_margin,
        "min_margin": float(min_margin),
        "best_impostor_confidence": round(best_impostor, 6),
        "candidates": candidates,
        "speaker_identity_proven": accepted,
        "allow_personal_memory": accepted,
        "fresh_physical_human_speech": True,
        "source_identity": "physical_horus_identity" if accepted else "unresolved_speaker",
        "voice_persona": SPEAKER_ID,
        "engine": "resemblyzer_voice_encoder",
        "candidate_audio_sha256": _sha256_file(candidate_wav),
        "rejection_reason": None if accepted else ",".join(reasons),
    }
    if accepted:
        logger.info("speaker gate ACCEPTED horus confidence={} margin={}", horus_confidence, observed_margin)
    else:
        logger.warning(
            "speaker gate FAILED CLOSED confidence={} margin={} reasons={}",
            horus_confidence, observed_margin, decision["rejection_reason"],
        )
    return decision
