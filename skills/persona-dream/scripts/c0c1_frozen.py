#!/usr/bin/env python3
"""Frozen constants and shared validators for the C0/C1 experiment.

Used by BOTH admit_persona_state_delta.py and fold_persona_state.py so the
frozen capsule digest and the idempotency-key serialization have exactly one
definition. This module intentionally does NOT import the admission module:
the fold must stay independent of admission in-memory state.

The baseline digest is parent-frozen 2026-09-15. If the capsule legitimately
changes (a preregistration amendment), the digest below MUST be updated in the
same commit and the change recorded in the contract file.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

COLLECTION = "persona_memory"
DELTA_SCHEMA = "persona_dream.persona_state_delta.v1"

FROZEN_BASELINE_SHA256 = "d6cae5f4be44357d972489fe003e9c5adb620a1de08f6caa38ebb8dbe0b99ac8"


def baseline_file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_frozen_baseline(path: Path) -> str:
    """Hard-fail unless the capsule bytes are exactly the frozen ones."""
    digest = baseline_file_sha256(path)
    if digest != FROZEN_BASELINE_SHA256:
        raise SystemExit(
            f"BLOCKED_C0C1_CAPSULE_DIGEST: baseline sha256 {digest} != frozen "
            f"{FROZEN_BASELINE_SHA256}; the preregistered capsule was altered"
        )
    return digest


def load_verified_baseline(path: Path) -> tuple[dict[str, Any], str]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if payload.get("schema") != "persona_dream.c0c1_baseline.v1":
        raise SystemExit(f"BLOCKED_C0C1_CAPSULE_SCHEMA: {payload.get('schema')}")
    if not isinstance(payload.get("admission"), dict):
        raise SystemExit("BLOCKED_C0C1_CAPSULE_NO_ADMISSION")
    digest = verify_frozen_baseline(path)
    return payload, digest


def delta_idempotency_key(
    *,
    persona: str,
    axis: str,
    scope: dict[str, Any],
    canonical_ids: list[str],
    delta: float,
    baseline_version: str,
) -> str:
    """The ONE serialization of the idempotency key (admission and fold must
    agree byte-for-byte)."""
    return "sha256:" + hashlib.sha256(json.dumps({
        "persona": persona, "axis": axis, "scope": scope,
        "canonical_ids": sorted(set(canonical_ids)), "delta": delta,
        "baseline_version": baseline_version,
    }, sort_keys=True).encode()).hexdigest()


def validate_delta_doc(doc: dict[str, Any], baseline: dict[str, Any]) -> str | None:
    """Validate one accepted persona_state_delta record against the frozen
    capsule. Returns None when valid, else a violation string. NEVER repairs.

    Note: `before` chain-consistency (folded state == doc.before) is checked by
    the caller; this function checks properties intrinsic to the document."""
    axis = str(doc.get("axis") or "")
    admission = baseline.get("admission") or {}
    baseline_state = baseline.get("baseline_state") or {}
    if str(doc.get("schema") or "") != DELTA_SCHEMA:
        return f"schema {doc.get('schema')!r} != {DELTA_SCHEMA}"
    if str(doc.get("record_type") or "") != "persona_state_delta":
        return f"record_type {doc.get('record_type')!r}"
    if axis not in (admission.get("writable_axes") or []):
        return f"axis {axis!r} not writable"
    try:
        before = float(doc.get("before"))
        delta = float(doc.get("delta"))
        after = float(doc.get("after"))
    except (TypeError, ValueError):
        return "non-numeric before/delta/after"
    if not (math.isfinite(before) and math.isfinite(delta) and math.isfinite(after)):
        return "non-finite before/delta/after"
    baseline_value = float(baseline_state.get(axis, 0.0))
    max_delta = float(admission.get("max_delta_per_cycle", 0.10))
    max_abs = float(admission.get("max_abs_from_baseline", 0.25))
    if abs(after - (before + delta)) > 1e-9:
        return f"after {after} != before {before} + delta {delta}"
    if abs(delta) > max_delta + 1e-9:
        return f"|delta| {abs(delta)} exceeds per-cycle limit {max_delta}"
    if abs(after - baseline_value) > max_abs + 1e-9:
        return f"|after {after} - baseline {baseline_value}| exceeds cumulative limit {max_abs}"
    classes = sorted(str(c) for c in (doc.get("source_event_identity_classes") or []))
    if not classes or any(c != "canonical" for c in classes):
        return f"non-canonical identity classes {classes}"
    expected_key = delta_idempotency_key(
        persona=str(doc.get("persona_id") or ""), axis=axis,
        scope=doc.get("scope") if isinstance(doc.get("scope"), dict) else {},
        canonical_ids=[str(e) for e in (doc.get("source_event_ids") or [])],
        delta=delta, baseline_version=str(doc.get("baseline_version") or ""),
    )
    if str(doc.get("idempotency_key") or "") != expected_key:
        return f"idempotency_key mismatch: doc={doc.get('idempotency_key')} recomputed={expected_key}"
    return None
