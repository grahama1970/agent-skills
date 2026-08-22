#!/usr/bin/env python3
"""Consume Chatterbox affect-validation registry entries without self-certifying.

Persona Dream may request and technically exercise a Chatterbox delivery tone,
but it does not own listener perception.  This module turns a render request,
response, and optional external registry into a narrow receipt field that
records exactly which rung has evidence.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

REGISTRY_SCHEMA = "chatterbox.affect_validation_registry.v1"
CONTRACT_SCHEMA = "persona_dream.chatterbox_affect_validation_consumer.v1"

DISPOSITIONS = {
    "VALIDATED",
    "VALIDATED_WITH_RANGE_LIMIT",
    "EXPERIMENTAL",
    "REJECTED",
    "REGISTRY_MISSING",
    "REGISTRY_MISMATCH",
}

CLAIM_LEVELS = {
    "REQUESTED_ONLY",
    "TECHNICALLY_APPLIED",
    "PERCEPTUALLY_VALIDATED_FOR_RECORDED_SCOPE",
}


def sha_obj(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest()


def sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def _profile_id(voice_delivery: dict[str, Any]) -> str:
    return str(
        voice_delivery.get("mapping_profile_id")
        or voice_delivery.get("profile_id")
        or voice_delivery.get("tone")
        or "unknown"
    )


def _profile_version(voice_delivery: dict[str, Any]) -> str:
    return str(
        voice_delivery.get("mapping_profile_version")
        or voice_delivery.get("profile_version")
        or voice_delivery.get("tone_mapping_version")
        or "unknown"
    )


def _requested_controls(voice_delivery: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "tone",
        "pace",
        "intensity",
        "valence",
        "emotion_realization",
        "required_engine",
    )
    return {key: voice_delivery[key] for key in keys if key in voice_delivery}


def _effective_controls(response: dict[str, Any]) -> dict[str, Any]:
    voice_delivery = response.get("voice_delivery") or {}
    cache_material = response.get("cache_material") or {}
    first_chunk = (response.get("chunks") or [{}])[0]
    return {
        "engine": response.get("engine") or response.get("chunk_engine") or response.get("asr_engine"),
        "requested_tone": response.get("requested_tone"),
        "normalized_tone": response.get("normalized_tone"),
        "tone_was_normalized": voice_delivery.get("tone_was_normalized"),
        "emotion_knobs": (
            response.get("emotion_knobs")
            or cache_material.get("emotion_knobs")
            or first_chunk.get("emotion_knobs")
        ),
        "affect_effect": response.get("affect_effect") or cache_material.get("affect_effect"),
    }


def _technical_application(effective_controls: dict[str, Any]) -> bool:
    effect = effective_controls.get("affect_effect")
    if isinstance(effect, dict) and effect.get("applied") is True:
        return True
    knobs = effective_controls.get("emotion_knobs")
    return isinstance(knobs, dict) and bool(knobs)


def _backend_id(response: dict[str, Any], health: dict[str, Any] | None) -> str:
    explicit = response.get("backend_id") or response.get("voice_backend")
    if explicit:
        return str(explicit)
    engine = str(response.get("engine") or response.get("chunk_engine") or "")
    if engine == "chatterbox_base":
        return "chatterbox_base_affect"
    if engine:
        return engine
    backends = (health or {}).get("voice_backends") or {}
    if "chatterbox_base_affect" in backends:
        return "chatterbox_base_affect"
    return "unknown"


def _backend_revision(backend_id: str, response: dict[str, Any], health: dict[str, Any] | None) -> str:
    backend = ((health or {}).get("voice_backends") or {}).get(backend_id) or {}
    return str(
        response.get("backend_revision")
        or backend.get("revision")
        or (health or {}).get("backend_revision")
        or (health or {}).get("model_revision")
        or (health or {}).get("engine_revision")
        or "unknown"
    )


def _capability_material(backend_id: str, health: dict[str, Any] | None) -> dict[str, Any]:
    health = health or {}
    return {
        "backend_id": backend_id,
        "voice_backend": (health.get("voice_backends") or {}).get(backend_id),
        "supported_backends": health.get("supported_backends"),
        "supported_params": health.get("supported_params"),
        "tone_calibration": health.get("tone_calibration"),
        "tag_handling": health.get("tag_handling"),
    }


def _range_match(requested: dict[str, Any], entry: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    ranges = entry.get("validated_ranges") or {}
    for key in ("intensity", "valence"):
        if key not in requested or key not in ranges:
            continue
        value = requested[key]
        bounds = ranges.get(key) or {}
        try:
            numeric = float(value)
            low = float(bounds.get("min"))
            high = float(bounds.get("max"))
        except (TypeError, ValueError):
            failures.append(f"{key}:non_numeric_range")
            continue
        if numeric < low or numeric > high:
            failures.append(f"{key}:outside_range")
    tones = entry.get("validated_tones")
    if tones is not None and requested.get("tone") not in set(tones):
        failures.append("tone:not_validated")
    return not failures, failures


def _entry_matches(entry: dict[str, Any], envelope: dict[str, Any]) -> tuple[bool, list[str]]:
    failures: list[str] = []
    for key in (
        "backend_id",
        "backend_revision",
        "backend_capability_digest",
        "mapping_profile_id",
        "mapping_profile_version",
        "speaker_scope",
        "language",
    ):
        if str(entry.get(key)) != str(envelope.get(key)):
            failures.append(key)
    range_ok, range_failures = _range_match(envelope["requested_controls"], entry)
    if not range_ok:
        failures.extend(range_failures)
    return not failures, failures


def _load_registry(path: Path | None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    if path is None:
        return None, {
            "schema": REGISTRY_SCHEMA,
            "path": None,
            "exists": False,
            "sha256": None,
            "load_status": "REGISTRY_MISSING",
        }
    if not path.is_file():
        return None, {
            "schema": REGISTRY_SCHEMA,
            "path": str(path),
            "exists": False,
            "sha256": None,
            "load_status": "REGISTRY_MISSING",
        }
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return None, {
            "schema": REGISTRY_SCHEMA,
            "path": str(path),
            "exists": True,
            "sha256": sha_file(path),
            "load_status": "REGISTRY_MISMATCH",
            "error": f"{type(exc).__name__}: {exc}",
        }
    return doc, {
        "schema": doc.get("schema"),
        "path": str(path),
        "exists": True,
        "sha256": sha_file(path),
        "load_status": "LOADED",
    }


def evaluate(
    *,
    voice_delivery: dict[str, Any],
    request_sha256: str,
    response_sha256: str,
    response: dict[str, Any],
    health: dict[str, Any] | None = None,
    registry_path: Path | None = None,
    speaker_scope: str = "embry_authorized_reference",
    language: str = "en",
) -> dict[str, Any]:
    """Return the claim-boundary contract for one Chatterbox render."""
    requested = _requested_controls(voice_delivery)
    effective = _effective_controls(response)
    backend_id = _backend_id(response, health)
    capability_digest = sha_obj(_capability_material(backend_id, health))
    envelope = {
        "backend_id": backend_id,
        "backend_revision": _backend_revision(backend_id, response, health),
        "backend_capability_digest": capability_digest,
        "voice_delivery": voice_delivery,
        "voice_delivery_sha256": sha_obj(voice_delivery),
        "mapping_profile_id": _profile_id(voice_delivery),
        "mapping_profile_version": _profile_version(voice_delivery),
        "speaker_scope": speaker_scope,
        "language": language,
        "requested_controls": requested,
        "effective_controls": effective,
        "render_plan": {
            "request_sha256": request_sha256,
            "response_sha256": response_sha256,
        },
    }
    registry, registry_source = _load_registry(registry_path)
    technically_applied = _technical_application(effective)
    disposition = "REGISTRY_MISSING"
    claim_level = "TECHNICALLY_APPLIED" if technically_applied else "REQUESTED_ONLY"
    match_result: dict[str, Any] = {
        "matched": False,
        "entry_id": None,
        "failure_reasons": ["registry_missing"],
    }

    if registry is not None:
        if registry.get("schema") != REGISTRY_SCHEMA:
            disposition = "REGISTRY_MISMATCH"
            match_result = {
                "matched": False,
                "entry_id": None,
                "failure_reasons": ["registry_schema"],
            }
        elif registry.get("registry_sha256") and registry.get("registry_sha256") != registry_source["sha256"]:
            disposition = "REGISTRY_MISMATCH"
            match_result = {
                "matched": False,
                "entry_id": None,
                "failure_reasons": ["registry_sha256"],
            }
        else:
            best_failures: list[str] = ["no_matching_entry"]
            for entry in registry.get("entries") or []:
                matched, failures = _entry_matches(entry, envelope)
                if not matched:
                    if failures:
                        best_failures = failures
                    continue
                entry_disposition = str(entry.get("validation_disposition") or "")
                if entry_disposition == "REJECTED":
                    disposition = "REJECTED"
                    claim_level = "REQUESTED_ONLY"
                elif entry_disposition in {"VALIDATED", "VALIDATED_WITH_RANGE_LIMIT"}:
                    disposition = entry_disposition
                    claim_level = "PERCEPTUALLY_VALIDATED_FOR_RECORDED_SCOPE"
                elif entry_disposition in DISPOSITIONS:
                    disposition = entry_disposition
                    claim_level = "TECHNICALLY_APPLIED" if technically_applied else "REQUESTED_ONLY"
                else:
                    disposition = "REGISTRY_MISMATCH"
                    claim_level = "TECHNICALLY_APPLIED" if technically_applied else "REQUESTED_ONLY"
                    failures = ["validation_disposition"]
                match_result = {
                    "matched": disposition in {"VALIDATED", "VALIDATED_WITH_RANGE_LIMIT", "REJECTED"},
                    "entry_id": entry.get("entry_id"),
                    "failure_reasons": failures,
                }
                break
            else:
                disposition = "EXPERIMENTAL" if technically_applied else "REGISTRY_MISMATCH"
                match_result = {
                    "matched": False,
                    "entry_id": None,
                    "failure_reasons": best_failures,
                }

    if disposition not in DISPOSITIONS:
        disposition = "REGISTRY_MISMATCH"
    if claim_level not in CLAIM_LEVELS:
        claim_level = "REQUESTED_ONLY"
    return {
        "schema": CONTRACT_SCHEMA,
        **envelope,
        "validation_registry": registry_source,
        "registry_backend_profile_range_match": match_result,
        "validation_disposition": disposition,
        "claim_level": claim_level,
        "perceptual_validation": (
            "MATCHED_HASH_BOUND_REGISTRY"
            if claim_level == "PERCEPTUALLY_VALIDATED_FOR_RECORDED_SCOPE"
            else "NOT_TESTED"
        ),
        "claim_boundary": {
            "persona_dream_authors_perceptual_verdict": False,
            "may_claim_perceived_emotion": claim_level == "PERCEPTUALLY_VALIDATED_FOR_RECORDED_SCOPE",
            "technical_application_observed": technically_applied,
        },
    }


def validate_receipt_claim_boundary(receipt: dict[str, Any]) -> list[str]:
    """Fail closed if a receipt claims perception without a registry match."""
    failures: list[str] = []
    rows: list[dict[str, Any]] = []
    if receipt.get("schema") == "persona_dream.session_mood_chatterbox_live_receipt.v1":
        rows = [row.get("affect_validation") or {} for row in receipt.get("render_results") or []]
    else:
        for stage in receipt.get("stages") or []:
            if stage.get("name") == "session_mood_live_chatterbox":
                rows.extend((turn.get("affect_validation") or {}) for turn in stage.get("turns") or [])
    for idx, row in enumerate(rows):
        if row.get("claim_level") != "PERCEPTUALLY_VALIDATED_FOR_RECORDED_SCOPE":
            continue
        if row.get("validation_disposition") not in {"VALIDATED", "VALIDATED_WITH_RANGE_LIMIT"}:
            failures.append(f"turn_{idx}:perceptual_claim_without_validated_disposition")
        if (row.get("registry_backend_profile_range_match") or {}).get("matched") is not True:
            failures.append(f"turn_{idx}:perceptual_claim_without_exact_registry_match")
        source = row.get("validation_registry") or {}
        if not source.get("sha256") or source.get("exists") is not True:
            failures.append(f"turn_{idx}:perceptual_claim_without_registry_hash")
    return failures
