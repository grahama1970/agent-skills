#!/usr/bin/env python3
"""Scoped anchored-identity waiver for a character's END-frame identity check.

This is a DOCUMENTED DESIGN CORRECTION, not a gate weakening. It implements the
resolution that the step-38 composition delta itself already specified
(``step38_sb_003_composition_delta_proposal.v1.json``): for the sb_003 end frame,
Kai's ``identity_requirements.Kai.visibility.after.face_required = false`` with
``identity_anchored_by = sb_003.start_frame``. The prior lane C acceptance
criterion (a) verified Kai's face ON the end frame, which contradicted the delta's
own accepted design; those two gates are not pairwise satisfiable on the same
artifact. This module encodes the delta's design so the contradiction is resolved
by a machine-checkable, fail-closed rule rather than a silent relaxation.

A character's end-frame identity check may be WAIVED only when ALL of:
  (a) the panel's composition contract explicitly requires that character's face to
      be non-readable on that frame -- machine-checkable, bound to the contract by
      sha256 (face_required=false AND speaker_mouth_camera_readable_during_speech
      =false in the delta block that targets that contract hash);
  (b) the SAME panel's start frame passes the full augmented identity review
      (full-frame VLM PASS AND deterministic ArcFace embedding subgate PASS) for
      that character; the anchor cosine is recorded;
  (c) the start->end continuity review passes with EXPLICIT non-facial identity
      continuity checks for that character (wardrobe, build, hair, board, position
      logic) -- the reviewer must have run in non-facial mode for the character;
  (d) a waiver receipt is emitted naming the character, the frame, the contract
      hash, the anchor frame + its embedding cosine, and the continuity receipt.

DEFAULT IS FAIL-CLOSED. Absent an explicit contract requirement, no waiver is
granted and the full augmented identity check stands for every character. All
OTHER characters visible on the frame (e.g. Embry) always get the full augmented
identity check including the embedding subgate; the waiver never touches them.
Outside these four conditions the gates remain exactly as strict as before.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

WAIVER_SCHEMA = "persona_dream.anchored_identity_waiver.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Condition (a): the composition contract explicitly requires the character's
# face to be non-readable on this frame, bound to the contract sha256.
# --------------------------------------------------------------------------- #
def evaluate_contract_requirement(
    *,
    delta: Mapping[str, Any],
    character: str,
    delta_block_key: str,
    contract_target_key: str,
    observed_contract_sha256: str,
) -> dict[str, Any]:
    reasons: list[str] = []
    block = delta.get(delta_block_key) or {}
    vis = (block.get(f"identity_requirements.{character}.visibility") or {})
    after = vis.get("after") or {}
    face_required = after.get("face_required")
    mouth_readable = after.get("speaker_mouth_camera_readable_during_speech")
    anchored_by = after.get("identity_anchored_by")

    satisfied = True
    if face_required is not False:
        satisfied = False
        reasons.append(
            f"contract does not set {character} visibility.face_required=false "
            f"on this frame (got {face_required!r})"
        )
    if mouth_readable is not False:
        satisfied = False
        reasons.append(
            f"contract does not set {character} "
            f"speaker_mouth_camera_readable_during_speech=false (got {mouth_readable!r})"
        )
    if not anchored_by:
        satisfied = False
        reasons.append(f"contract does not name an identity_anchored_by frame for {character}")

    expected_sha = ((delta.get("targets") or {}).get(contract_target_key) or {}).get("sha256")
    hash_match = bool(expected_sha) and expected_sha == observed_contract_sha256
    if not hash_match:
        satisfied = False
        reasons.append(
            f"contract sha256 mismatch: delta targets {expected_sha!r} but observed "
            f"{observed_contract_sha256!r}"
        )
    return {
        "condition": "a_contract_requires_face_nonreadable",
        "satisfied": satisfied,
        "face_required": face_required,
        "speaker_mouth_camera_readable_during_speech": mouth_readable,
        "identity_anchored_by": anchored_by,
        "contract_sha256_observed": observed_contract_sha256,
        "contract_sha256_expected": expected_sha,
        "contract_hash_match": hash_match,
        "reasons": reasons,
    }


# --------------------------------------------------------------------------- #
# Condition (b): the start (anchor) frame passes the FULL augmented identity
# review (full-frame VLM PASS AND embedding subgate PASS) for the character.
# --------------------------------------------------------------------------- #
def evaluate_anchor_pass(
    *,
    character: str,
    start_frame_review: Mapping[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    status = start_frame_review.get("status")
    full_frame = start_frame_review.get("full_frame_status")
    subgate = start_frame_review.get("face_embedding_subgate") or {}
    subgate_status = subgate.get("status")
    entity_results = subgate.get("entity_results") or []
    ent = next((e for e in entity_results if e.get("entity") == character), None)
    anchor_cosine = ent.get("best_cosine") if ent else None
    ent_pass = bool(ent and ent.get("status") == "PASS")

    satisfied = True
    if status != "PASS":
        satisfied = False
        reasons.append(f"start-frame augmented identity review status is {status!r}, not PASS")
    if full_frame != "PASS":
        satisfied = False
        reasons.append(f"start-frame full-frame VLM status is {full_frame!r}, not PASS")
    if subgate_status != "PASS":
        satisfied = False
        reasons.append(f"start-frame embedding subgate status is {subgate_status!r}, not PASS")
    if not ent_pass:
        satisfied = False
        reasons.append(
            f"start-frame embedding subgate did not PASS for {character} "
            f"(entity result: {ent!r})"
        )
    return {
        "condition": "b_start_frame_full_augmented_identity_pass",
        "satisfied": satisfied,
        "anchor_frame_review_status": status,
        "anchor_full_frame_status": full_frame,
        "anchor_embedding_subgate_status": subgate_status,
        "anchor_embedding_cosine": anchor_cosine,
        "anchor_embedding_threshold": subgate.get("threshold"),
        "reasons": reasons,
    }


# --------------------------------------------------------------------------- #
# Condition (c): the start->end continuity review PASSED and ran EXPLICIT
# non-facial identity continuity checks for the character.
# --------------------------------------------------------------------------- #
def evaluate_continuity_pass(
    *,
    character: str,
    continuity_review: Mapping[str, Any],
) -> dict[str, Any]:
    reasons: list[str] = []
    status = continuity_review.get("status")
    non_facial_for = continuity_review.get("non_facial_identity_continuity_for") or []
    checks = continuity_review.get("non_facial_checks") or []

    satisfied = True
    if status != "PASS":
        satisfied = False
        reasons.append(f"start->end continuity status is {status!r}, not PASS")
    if character not in non_facial_for:
        satisfied = False
        reasons.append(
            f"continuity review did not run explicit non-facial identity continuity "
            f"for {character} (non_facial_identity_continuity_for={non_facial_for})"
        )
    required_axes = {"wardrobe", "build", "hair", "board", "position"}
    covered = {str(c).lower() for c in checks}
    missing_axes = sorted(required_axes - covered)
    if missing_axes:
        satisfied = False
        reasons.append(
            f"continuity review did not cover required non-facial axes {missing_axes} "
            f"for {character} (covered={sorted(covered)})"
        )
    return {
        "condition": "c_start_end_continuity_non_facial_pass",
        "satisfied": satisfied,
        "continuity_status": status,
        "non_facial_identity_continuity_for": list(non_facial_for),
        "non_facial_checks": list(checks),
        "reasons": reasons,
    }


# --------------------------------------------------------------------------- #
# Compose (a)+(b)+(c) and emit the waiver receipt (d).
# --------------------------------------------------------------------------- #
def evaluate_anchored_identity_waiver(
    *,
    character: str,
    frame_key: str,
    panel_id: str,
    delta: Mapping[str, Any],
    delta_block_key: str,
    contract_target_key: str,
    observed_contract_sha256: str,
    start_frame_review: Mapping[str, Any],
    continuity_review: Mapping[str, Any],
    anchor_frame_path: str | None = None,
    continuity_receipt_path: str | None = None,
) -> dict[str, Any]:
    cond_a = evaluate_contract_requirement(
        delta=delta,
        character=character,
        delta_block_key=delta_block_key,
        contract_target_key=contract_target_key,
        observed_contract_sha256=observed_contract_sha256,
    )
    cond_b = evaluate_anchor_pass(character=character, start_frame_review=start_frame_review)
    cond_c = evaluate_continuity_pass(character=character, continuity_review=continuity_review)

    conditions = [cond_a, cond_b, cond_c]
    granted = all(c["satisfied"] for c in conditions)
    denied_reasons: list[str] = []
    if not granted:
        for c in conditions:
            if not c["satisfied"]:
                denied_reasons.extend(f"{c['condition']}: {r}" for r in c["reasons"])

    receipt: dict[str, Any] = {
        "schema": WAIVER_SCHEMA,
        "created_at": _now(),
        "panel_id": panel_id,
        "character": character,
        "frame_key": frame_key,
        "granted": granted,
        "default_policy": "fail_closed: no explicit contract requirement -> no waiver",
        "scope_statement": (
            "This waiver ONLY waives the end-frame identity check for the named "
            "character under the delta's accepted design; every other character on "
            "the frame keeps the full augmented identity check (full-frame VLM + "
            "embedding subgate), and outside these four conditions all gates stay strict."
        ),
        "contract": {
            "sha256": observed_contract_sha256,
            "delta_block_key": delta_block_key,
            "contract_target_key": contract_target_key,
            "identity_anchored_by": cond_a.get("identity_anchored_by"),
        },
        "anchor_frame": {
            "path": anchor_frame_path,
            "embedding_cosine": cond_b.get("anchor_embedding_cosine"),
            "embedding_threshold": cond_b.get("anchor_embedding_threshold"),
        },
        "continuity_receipt": continuity_receipt_path,
        "conditions": {
            "a_contract_requires_face_nonreadable": cond_a,
            "b_start_frame_full_augmented_identity_pass": cond_b,
            "c_start_end_continuity_non_facial_pass": cond_c,
        },
        "denied_reasons": denied_reasons,
        "mocked": False,
        "live": True,
    }
    receipt["receipt_sha256"] = _sha256_text(
        json.dumps({k: v for k, v in receipt.items() if k != "created_at"}, sort_keys=True)
    )
    return receipt


def waiver_covers(waiver_receipt: Mapping[str, Any], character: str, frame_key: str) -> bool:
    """True iff a GRANTED waiver receipt covers this exact character+frame."""
    return bool(
        waiver_receipt.get("granted")
        and waiver_receipt.get("character") == character
        and waiver_receipt.get("frame_key") == frame_key
    )


def write_waiver_receipt(path: Path, receipt: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
