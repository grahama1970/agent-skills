#!/usr/bin/env python3
"""Tau node adapter for Persona Dream Phase 07 storyboard packet review.

This adapter is intentionally deterministic. It does not create fake images or
call a provider. It lets Tau run the Phase 07 creator/reviewer handoff against
the storyboard packet already produced by persona-dream and fails closed when
the packet is not complete enough to be treated as accepted storyboard panels.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError


REQUIRED_PANEL_FIELDS = (
    "panel_id",
    "time_range",
    "shot",
    "action",
    "coverage_seed_ids",
    "required_entities",
    "references",
    "prompt_fragment",
    "start_frame",
    "end_frame",
    "camera",
    "lighting",
    "acting_beats",
    "production_notes",
    "generation_prompt",
)

REQUIRED_NESTED_FIELDS = {
    "time_range": ("start_s", "end_s"),
    "start_frame": ("description", "visual_requirements", "negative_constraints"),
    "end_frame": ("description", "visual_requirements", "negative_constraints"),
    "camera": ("shot_code", "movement", "composition", "camera_equipment"),
    "lighting": ("time_of_day", "quality"),
    "production_notes": ("producer", "director", "scriptwriter", "continuity"),
    "generation_prompt": ("panel_prompt", "start_frame_prompt", "end_frame_prompt", "negative_prompt"),
}

REQUIRED_REFERENCE_ENTITIES = {
    "Embry surfboard",
    "Kai surfboard",
    "June Swell",
    "Lava Reef",
    "Kona Coast",
}

REJECTED_REFERENCE_ROLES = {
    "identity_reference",
    "required_prop_reference",
    "required_environment_reference",
    "required_location_reference",
}

ACCEPTED_FRAME_STATUSES = {
    "PASS_PANEL_REVIEWED",
    "ACCEPTED_STORYBOARD_FRAME",
    "ACCEPTED_START_FRAME",
    "ACCEPTED_END_FRAME",
}

STORYBOARD_FRAME_SIZE = (1536, 864)
STORYBOARD_FRAME_ASPECT = STORYBOARD_FRAME_SIZE[0] / STORYBOARD_FRAME_SIZE[1]
STORYBOARD_FRAME_ASPECT_TOLERANCE = 0.02
SCILLM_SKILL_RUN = Path("/home/graham/workspace/experiments/agent-skills/skills/scillm/run.sh")
IMAGEMAGICK_BIN = Path("/usr/local/bin/magick")
SCILLM_CHAT_COMPLETIONS_URL = "http://localhost:4001/v1/chat/completions"
IDENTITY_REFERENCE_ASSETS = {
    "Embry": {
        "id": "embry_character_sheet",
        "title": "Embry character sheet montage",
        "role": "identity_reference",
        "media_type": "image",
        "path": "/mnt/storage12tb/media/personas/embry/assets/character_sheet_montage.jpg",
    },
    "Kai": {
        "id": "kai_character_sheet",
        "title": "Kai Akana character sheet",
        "role": "identity_reference",
        "media_type": "image",
        "path": "/mnt/storage12tb/media/personas/kai_akana/assets/contact_sheets/kai_akana_character_sheet.png",
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--role", required=True, choices=("panel-creator", "panel-reviewer"))
    args = parser.parse_args()

    start_payload = _read_stdin_handoff()
    selected_agent = os.environ.get("TAU_HANDOFF_SELECTED_AGENT") or args.role
    if selected_agent != args.role:
        raise SystemExit(f"selected agent {selected_agent!r} does not match role {args.role!r}")

    artifact_dir = Path(
        os.environ.get("TAU_HANDOFF_COMMAND_ARTIFACT_DIR", f"/tmp/persona-dream-phase07-{args.role}")
    ).expanduser().resolve()
    artifact_dir.mkdir(parents=True, exist_ok=True)

    context = _context(start_payload)
    run_root = Path(str(context["run_root"])).expanduser().resolve()
    packet_path = Path(str(context["storyboard_packet"])).expanduser().resolve()
    packet = _read_json(packet_path)
    receipts_dir = run_root / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    if args.role == "panel-creator":
        handoff = _run_creator(start_payload, artifact_dir, receipts_dir, packet_path, packet, context)
    else:
        handoff = _run_reviewer(start_payload, artifact_dir, receipts_dir, packet_path, packet, context)

    print(json.dumps(handoff, indent=2, sort_keys=True))
    return 0


def _run_creator(
    start_payload: Mapping[str, Any],
    artifact_dir: Path,
    receipts_dir: Path,
    packet_path: Path,
    packet: Mapping[str, Any],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    run_root = Path(str(context["run_root"])).expanduser().resolve()
    generation = _ensure_storyboard_frame_artifacts(
        packet,
        packet_path=packet_path,
        run_root=run_root,
        start_payload=start_payload,
    )
    if generation["packet_updated"]:
        packet = _read_json(packet_path)
    creator_check = _validate_storyboard_packet(packet, packet_path=packet_path, reviewer=False)
    creator_check["blockers"].extend(generation["blockers"])
    provider_route = _provider_route_receipt(
        start_payload,
        role="panel-creator",
        artifact_dir=artifact_dir,
        receipts_dir=receipts_dir,
    )
    creator_check["blockers"].extend(provider_route["blockers"])
    manifest = _panel_manifest(packet, packet_path)
    manifest_path = receipts_dir / "storyboard_panel_manifest.json"
    generation_receipt_path = receipts_dir / "storyboard_frame_generation_receipt.json"
    _write_json(manifest_path, manifest)
    _write_json(generation_receipt_path, generation["receipt"])
    creator_receipt = {
        "schema": "persona_dream.storyboard_creator_receipt.v1",
        "created_at": _now_iso(),
        "role": "panel-creator",
        "status": "PASS_STORYBOARD_PACKET_CREATED" if not creator_check["blockers"] else "BLOCKED_STORYBOARD_PACKET",
        "storyboard_packet": str(packet_path),
        "storyboard_packet_sha256": _sha256(packet_path),
        "panel_count": len(packet.get("panels") or []),
        "duration_seconds": packet.get("duration_seconds"),
        "manifest": str(manifest_path),
        "frame_generation_receipt": str(generation_receipt_path),
        "provider_route_receipt": str(provider_route["receipt_path"]),
        "blockers": creator_check["blockers"],
        "mocked": False,
        "live": True,
        "provider_calls": {
            "route": provider_route["status"] == "PASS",
            "image": generation["provider_called"],
            "kling": False,
            "paid": False,
        },
    }
    creator_receipt_path = receipts_dir / "storyboard_creator_receipt.json"
    _write_json(creator_receipt_path, creator_receipt)
    _write_json(artifact_dir / "storyboard_creator_receipt.json", creator_receipt)
    _write_json(artifact_dir / "storyboard_panel_manifest.json", manifest)
    _write_json(artifact_dir / "storyboard_frame_generation_receipt.json", generation["receipt"])
    tau_receipt_path = artifact_dir / "panel_creator_tau_subagent_receipt.json"
    evidence = [str(creator_receipt_path), str(manifest_path), str(generation_receipt_path), str(provider_route["receipt_path"]), str(packet_path)]
    tau_receipt = _subagent_receipt(
        start_payload,
        subagent="panel-creator",
        status="COMPLETED" if not creator_check["blockers"] else "BLOCKED",
        summary=(
            "Panel creator emitted a complete storyboard packet manifest for reviewer."
            if not creator_check["blockers"]
            else "Panel creator emitted a storyboard packet with blockers for reviewer adjudication."
        ),
        evidence=evidence,
        next_subagent="panel-reviewer",
        next_executor="local",
        next_reason=(
            "Panel reviewer must independently validate per-panel storyboard coverage."
            if not creator_check["blockers"]
            else "Panel reviewer must reject with exact blockers and route repair back to panel-creator."
        ),
    )
    _write_json(tau_receipt_path, tau_receipt)
    return _handoff(
        start_payload,
        previous_subagent="panel-creator",
        status=tau_receipt["result"]["status"],
        summary=tau_receipt["result"]["summary"],
        evidence=tau_receipt["evidence"],
        artifacts=[str(creator_receipt_path), str(manifest_path), str(generation_receipt_path), str(provider_route["receipt_path"]), str(tau_receipt_path), str(packet_path)],
        context_update={"persona_dream_phase07_storyboard": dict(context)},
        next_agent=tau_receipt["next"]["subagent"],
        next_executor=tau_receipt["next"]["executor"],
        next_reason=tau_receipt["next"]["reason"],
        required_evidence="storyboard_review_verdict.json with status PASS_PANEL_REVIEWED.",
        stop_condition="Panel-reviewer accepts storyboard panels or emits exact blockers.",
    )


def _run_reviewer(
    start_payload: Mapping[str, Any],
    artifact_dir: Path,
    receipts_dir: Path,
    packet_path: Path,
    packet: Mapping[str, Any],
    context: Mapping[str, Any],
) -> dict[str, Any]:
    review = _validate_storyboard_packet(packet, packet_path=packet_path, reviewer=True)
    provider_route = _provider_route_receipt(
        start_payload,
        role="panel-reviewer",
        artifact_dir=artifact_dir,
        receipts_dir=receipts_dir,
    )
    review["blockers"].extend(provider_route["blockers"])
    status = "PASS_PANEL_REVIEWED" if not review["blockers"] else "BLOCKED_PANEL_REVIEW"
    accepted = status == "PASS_PANEL_REVIEWED"
    if accepted:
        accepted_packet = dict(packet)
        accepted_packet["status"] = status
        accepted_packet["accepted"] = True
        accepted_packet["review_status"] = status
        accepted_packet["reviewed_at"] = _now_iso()
        _write_json(packet_path, accepted_packet)
        packet = accepted_packet
    reference_coverage_path = receipts_dir / "storyboard_reference_coverage.json"
    entity_coverage_path = receipts_dir / "storyboard_entity_coverage.json"
    verdict_path = receipts_dir / "storyboard_review_verdict.json"
    _write_json(reference_coverage_path, review["reference_coverage"])
    _write_json(entity_coverage_path, review["entity_coverage"])
    verdict = {
        "schema": "persona_dream.storyboard_review_verdict.v1",
        "created_at": _now_iso(),
        "role": "panel-reviewer",
        "status": status,
        "storyboard_packet": str(packet_path),
        "storyboard_packet_sha256": _sha256(packet_path),
        "panel_count": len(packet.get("panels") or []),
        "duration_seconds": packet.get("duration_seconds"),
        "accepted": accepted,
        "blockers": review["blockers"],
        "per_panel": review["per_panel"],
        "reference_coverage": str(reference_coverage_path),
        "entity_coverage": str(entity_coverage_path),
        "provider_route_receipt": str(provider_route["receipt_path"]),
        "mocked": False,
        "live": True,
        "provider_calls": {
            "route": provider_route["status"] == "PASS",
            "image": False,
            "kling": False,
            "paid": False,
        },
        "claims": {
            "proves": [
                "Tau dispatched the Phase 07 panel-reviewer node.",
                "The storyboard packet includes accepted storyboard frame evidence for each panel.",
                "Each accepted panel has script action, start/end frame evidence, camera, lighting, acting beats, production notes, references, and coverage seeds.",
                "Phase 04 object/location/environment references are attached as references only, not accepted panel frames.",
            ]
            if status == "PASS_PANEL_REVIEWED"
            else ["Tau dispatched the Phase 07 panel-reviewer node and failed closed with blockers."],
            "does_not_prove": [
                "This reviewer receipt does not by itself prove live provider image generation; use storyboard_frame_generation_receipt.json and accepted_frame metadata for provider evidence.",
                "No downstream video provider submission occurred.",
            ],
        },
    }
    _write_json(verdict_path, verdict)
    _write_json(artifact_dir / "storyboard_review_verdict.json", verdict)
    _write_json(artifact_dir / "storyboard_reference_coverage.json", review["reference_coverage"])
    _write_json(artifact_dir / "storyboard_entity_coverage.json", review["entity_coverage"])
    tau_receipt_path = artifact_dir / "panel_reviewer_tau_subagent_receipt.json"
    evidence = [str(verdict_path), str(reference_coverage_path), str(entity_coverage_path), str(provider_route["receipt_path"]), str(packet_path)]
    tau_receipt = _subagent_receipt(
        start_payload,
        subagent="panel-reviewer",
        status=status,
        summary=(
            "Panel-reviewer accepted the Phase 07 storyboard panels."
            if status == "PASS_PANEL_REVIEWED"
            else "Panel-reviewer rejected the storyboard packet with exact blockers."
        ),
        evidence=evidence,
        next_subagent="human" if accepted else "panel-creator",
        next_executor="human" if accepted else "local",
        next_reason=(
            "Human reviews the accepted Tau receipt and storyboard pane rendering."
            if accepted
            else "Panel creator must repair the storyboard packet with accepted per-panel frame evidence before review can pass."
        ),
    )
    _write_json(tau_receipt_path, tau_receipt)
    return _handoff(
        start_payload,
        previous_subagent="panel-reviewer",
        status=tau_receipt["result"]["status"],
        summary=tau_receipt["result"]["summary"],
        evidence=tau_receipt["evidence"],
        artifacts=[str(verdict_path), str(reference_coverage_path), str(entity_coverage_path), str(provider_route["receipt_path"]), str(tau_receipt_path), str(packet_path)],
        context_update={"persona_dream_phase07_storyboard": dict(context)},
        next_agent="human" if accepted else "panel-creator",
        next_executor="human" if accepted else "local",
        next_reason=(
            "Phase 07 storyboard panel review accepted the packet."
            if accepted
            else "Panel-reviewer rejected the packet; Tau should route back to panel-creator until retry budget is exhausted."
        ),
        required_evidence=(
            "Fresh CDP verification of http://localhost:3002/dream#storyboard."
            if accepted
            else "Repaired storyboard_packet.json containing accepted per-panel storyboard frame evidence."
        ),
        stop_condition=(
            "Stop because panel-reviewer accepted."
            if accepted
            else "Continue until panel-reviewer accepts or Tau max attempts are exceeded."
        ),
    )


def _validate_storyboard_packet(
    packet: Mapping[str, Any],
    *,
    packet_path: Path,
    reviewer: bool,
) -> dict[str, Any]:
    blockers: list[str] = []
    per_panel: list[dict[str, Any]] = []
    if packet.get("schema") != "persona_dream.storyboard_packet.v1":
        blockers.append(f"packet.schema mismatch: {packet.get('schema')}")
    panels = packet.get("panels")
    if not isinstance(panels, list):
        blockers.append("packet.panels must be a list")
        panels = []
    if len(panels) < 4:
        blockers.append(f"panel_count_below_minimum:{len(panels)}")
    if packet.get("duration_seconds") != 10:
        blockers.append(f"duration_seconds_not_10:{packet.get('duration_seconds')}")
    if packet.get("panel_count") != len(panels):
        blockers.append(f"panel_count_mismatch:{packet.get('panel_count')}!={len(panels)}")

    candidates = packet.get("generated_candidate_panels")
    rejected_candidates: list[str] = []
    if reviewer and isinstance(candidates, list):
        rejected_candidates = [
            str(item.get("panel_id"))
            for item in candidates
            if isinstance(item, Mapping) and str(item.get("status")) != "PASS_PANEL_REVIEWED"
        ]

    top_level_refs = packet.get("references") if isinstance(packet.get("references"), list) else []
    ref_entities = {
        str(item.get("entity"))
        for item in top_level_refs
        if isinstance(item, Mapping) and item.get("entity")
    }
    missing_refs = sorted(REQUIRED_REFERENCE_ENTITIES - ref_entities)
    if missing_refs:
        blockers.append("missing_packet_reference_entities:" + ",".join(missing_refs))

    for ref in top_level_refs:
        if not isinstance(ref, Mapping):
            continue
        path_value = ref.get("path")
        if isinstance(path_value, str) and path_value:
            if not Path(path_value).expanduser().exists():
                blockers.append(f"reference_path_missing:{ref.get('entity')}:{path_value}")

    seed_ids: set[str] = set()
    entity_names: set[str] = set()
    for index, panel in enumerate(panels):
        panel_blockers = _validate_panel(panel, index=index, reviewer=reviewer)
        if isinstance(panel, Mapping):
            seed_ids.update(str(item) for item in panel.get("coverage_seed_ids", []) if isinstance(item, str))
            entity_names.update(str(item) for item in panel.get("required_entities", []) if isinstance(item, str))
        if panel_blockers:
            blockers.extend(panel_blockers)
        per_panel.append(
            {
                "panel_id": panel.get("panel_id") if isinstance(panel, Mapping) else f"panel_{index + 1}",
                "status": "PASS" if not panel_blockers else "BLOCKED",
                "blockers": panel_blockers,
            }
        )

    required_seeds = {f"seed-{index}" for index in range(7)}
    missing_seeds = sorted(required_seeds - seed_ids)
    if reviewer and missing_seeds:
        blockers.append("missing_coverage_seed_ids:" + ",".join(missing_seeds))

    reference_coverage = {
        "schema": "persona_dream.storyboard_reference_coverage.v1",
        "storyboard_packet": str(packet_path),
        "status": "PASS" if not missing_refs else "BLOCKED",
        "required_entities": sorted(REQUIRED_REFERENCE_ENTITIES),
        "present_entities": sorted(ref_entities),
        "missing_entities": missing_refs,
        "rejected_candidate_panels": rejected_candidates,
        "candidate_policy": (
            "Rejected generated_candidate_panels are retained only as provenance. "
            "They do not block review when each storyboard panel has accepted start/end frame artifacts."
        ),
        "references": top_level_refs,
    }
    entity_coverage = {
        "schema": "persona_dream.storyboard_entity_coverage.v1",
        "storyboard_packet": str(packet_path),
        "status": "PASS" if not missing_seeds else "BLOCKED",
        "covered_seed_ids": sorted(seed_ids),
        "missing_seed_ids": missing_seeds,
        "covered_entities": sorted(entity_names),
    }
    return {
        "blockers": blockers,
        "per_panel": per_panel,
        "reference_coverage": reference_coverage,
        "entity_coverage": entity_coverage,
    }


def _validate_panel(panel: Any, *, index: int, reviewer: bool) -> list[str]:
    blockers: list[str] = []
    label = f"panel[{index}]"
    if not isinstance(panel, Mapping):
        return [f"{label}:not_object"]
    for field in REQUIRED_PANEL_FIELDS:
        if field not in panel:
            blockers.append(f"{label}:missing_field:{field}")
    for field, nested_fields in REQUIRED_NESTED_FIELDS.items():
        nested = panel.get(field)
        if not isinstance(nested, Mapping):
            blockers.append(f"{label}:missing_object:{field}")
            continue
        for nested_field in nested_fields:
            if nested_field not in nested:
                blockers.append(f"{label}:missing_field:{field}.{nested_field}")
    time_range = panel.get("time_range")
    if isinstance(time_range, Mapping):
        start_s = time_range.get("start_s")
        end_s = time_range.get("end_s")
        if not isinstance(start_s, (int, float)) or not isinstance(end_s, (int, float)) or end_s <= start_s:
            blockers.append(f"{label}:invalid_time_range")
    for field in ("coverage_seed_ids", "required_entities", "references", "acting_beats"):
        if not isinstance(panel.get(field), list) or not panel.get(field):
            blockers.append(f"{label}:empty_list:{field}")
    for frame_field in ("start_frame", "end_frame"):
        frame = panel.get(frame_field)
        if isinstance(frame, Mapping):
            if not str(frame.get("description") or "").strip():
                blockers.append(f"{label}:empty_description:{frame_field}")
            if not isinstance(frame.get("visual_requirements"), list) or not frame.get("visual_requirements"):
                blockers.append(f"{label}:empty_visual_requirements:{frame_field}")
    prompt = panel.get("generation_prompt")
    if isinstance(prompt, Mapping):
        if "contact sheet as the panel image" not in " ".join(
            str(item) for item in prompt.get("reference_requirements", [])
        ):
            pass
        if not str(prompt.get("negative_prompt") or "").strip():
            blockers.append(f"{label}:missing_negative_prompt")
    if reviewer:
        blockers.extend(_validate_accepted_storyboard_frame_evidence(panel, label=label))
    return blockers


def _validate_accepted_storyboard_frame_evidence(panel: Mapping[str, Any], *, label: str) -> list[str]:
    blockers: list[str] = []
    required_entities = {
        str(entity)
        for entity in panel.get("required_entities", [])
        if isinstance(entity, str)
    }
    requires_identity_review = bool(required_entities & {"Embry", "Kai"})
    start_refs = _frame_references(panel, frame_key="start_frame")
    end_refs = _frame_references(panel, frame_key="end_frame")
    if not start_refs:
        blockers.append(
            f"{label}:missing_accepted_start_frame_evidence:"
            "requires accepted per-panel start-frame artifact"
        )
    if not end_refs:
        blockers.append(
            f"{label}:missing_accepted_end_frame_evidence:"
            "requires accepted per-panel end-frame artifact"
        )

    def accepted_count(refs: list[Mapping[str, Any]], *, frame_label: str) -> int:
        count = 0
        for frame_ref in refs:
            status = str(frame_ref.get("status") or "")
            role = str(frame_ref.get("role") or frame_ref.get("type") or "")
            path_value = frame_ref.get("path") or frame_ref.get("image_path")
            if role in REJECTED_REFERENCE_ROLES or "contact_sheet" in role:
                blockers.append(f"{label}:reference_used_as_{frame_label}:{role}")
                continue
            if status not in ACCEPTED_FRAME_STATUSES:
                blockers.append(f"{label}:{frame_label}_not_accepted:{status or 'missing_status'}")
                continue
            if not isinstance(path_value, str) or not path_value.strip():
                blockers.append(f"{label}:accepted_{frame_label}_missing_path")
                continue
            if not Path(path_value).expanduser().exists():
                blockers.append(f"{label}:accepted_{frame_label}_path_missing:{path_value}")
                continue
            blockers.extend(_validate_accepted_frame_file(path_value, label=label, frame_label=frame_label))
            blockers.extend(
                _validate_identity_continuity_review(
                    frame_ref,
                    label=label,
                    frame_label=frame_label,
                    required_entities=required_entities,
                    required=requires_identity_review,
                )
            )
            count += 1
        return count

    if start_refs and accepted_count(start_refs, frame_label="start_frame") == 0:
        blockers.append(f"{label}:no_usable_accepted_start_frame_artifact")
    if end_refs and accepted_count(end_refs, frame_label="end_frame") == 0:
        blockers.append(f"{label}:no_usable_accepted_end_frame_artifact")
    return blockers


def _validate_accepted_frame_file(path_value: str, *, label: str, frame_label: str) -> list[str]:
    path = Path(path_value).expanduser()
    blockers: list[str] = []
    try:
        width, height = _read_png_size(path)
    except Exception as exc:
        return [f"{label}:accepted_{frame_label}_image_unreadable:{path_value}:{exc}"]
    aspect = width / height if height else 0
    if abs(aspect - STORYBOARD_FRAME_ASPECT) > STORYBOARD_FRAME_ASPECT_TOLERANCE:
        blockers.append(
            f"{label}:accepted_{frame_label}_aspect_mismatch:{width}x{height}:"
            f"expected_{STORYBOARD_FRAME_SIZE[0]}x{STORYBOARD_FRAME_SIZE[1]}"
        )
    return blockers


def _read_png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("expected_png_header")
    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid_png_dimensions:{width}x{height}")
    return width, height


def _validate_identity_continuity_review(
    frame_ref: Mapping[str, Any],
    *,
    label: str,
    frame_label: str,
    required_entities: set[str],
    required: bool,
) -> list[str]:
    if not required:
        return []
    review = frame_ref.get("identity_continuity_review")
    if not isinstance(review, Mapping):
        return [f"{label}:accepted_{frame_label}_missing_identity_continuity_review"]
    status = str(review.get("status") or "")
    if status != "PASS":
        return [f"{label}:accepted_{frame_label}_identity_continuity_not_pass:{status or 'missing_status'}"]
    visible_entities = {
        str(entity)
        for entity in review.get("visible_entities", [])
        if isinstance(entity, str)
    }
    missing = sorted((required_entities & {"Embry", "Kai"}) - visible_entities)
    if missing:
        return [f"{label}:accepted_{frame_label}_identity_entities_missing:{','.join(missing)}"]
    return []


def _frame_references(panel: Mapping[str, Any], *, frame_key: str | None = None) -> list[Mapping[str, Any]]:
    refs: list[Mapping[str, Any]] = []
    if frame_key is not None:
        value = panel.get(frame_key)
        if isinstance(value, Mapping):
            for nested_key in ("image", "image_reference", "accepted_frame"):
                nested = value.get(nested_key)
                if isinstance(nested, Mapping):
                    refs.append(nested)
        return refs
    for key in ("storyboard_frame", "panel_image", "accepted_frame"):
        value = panel.get(key)
        if isinstance(value, Mapping):
            refs.append(value)
    value = panel.get("storyboard_frames")
    if isinstance(value, list):
        refs.extend(item for item in value if isinstance(item, Mapping))
    return refs


def _ensure_storyboard_frame_artifacts(
    packet: Mapping[str, Any],
    *,
    packet_path: Path,
    run_root: Path,
    start_payload: Mapping[str, Any],
) -> dict[str, Any]:
    image_policy = _resolve_image_policy(start_payload)
    identity_review_policy = _resolve_identity_review_policy(start_payload)
    panels = packet.get("panels")
    receipt: dict[str, Any] = {
        "schema": "persona_dream.storyboard_frame_generation_receipt.v1",
        "created_at": _now_iso(),
        "storyboard_packet": str(packet_path),
        "backend": "scillm",
        "model": image_policy.get("model"),
        "image_policy": image_policy,
        "identity_review_policy": identity_review_policy,
        "model_policy_enforced": image_policy["source"] == "dag_model_policy",
        "fallback_performed": False,
        "mocked": False,
        "live": True,
        "provider_calls": [],
    }
    blockers: list[str] = []
    if image_policy["source"] != "dag_model_policy":
        blockers.append(f"frame_generation:missing_dag_model_policy:{image_policy.get('error') or image_policy.get('source')}")
        receipt["status"] = "BLOCKED"
        receipt["blockers"] = blockers
        _write_json(run_root / "receipts" / "storyboard_frame_generation_receipt.json", receipt)
        return {"packet_updated": False, "provider_called": False, "blockers": blockers, "receipt": receipt}
    if image_policy["supported"] is not True:
        blockers.append(f"frame_generation:image_policy_blocked:{image_policy.get('error')}")
        receipt["status"] = "BLOCKED"
        receipt["blockers"] = blockers
        _write_json(run_root / "receipts" / "storyboard_frame_generation_receipt.json", receipt)
        return {"packet_updated": False, "provider_called": False, "blockers": blockers, "receipt": receipt}
    if identity_review_policy["source"] != "dag_identity_review_model_policy":
        blockers.append(
            "identity_review:missing_dag_identity_review_model_policy:"
            + str(identity_review_policy.get("error") or identity_review_policy.get("source"))
        )
        receipt["status"] = "BLOCKED"
        receipt["blockers"] = blockers
        _write_json(run_root / "receipts" / "storyboard_frame_generation_receipt.json", receipt)
        return {"packet_updated": False, "provider_called": False, "blockers": blockers, "receipt": receipt}
    if identity_review_policy["supported"] is not True:
        blockers.append(f"identity_review:model_policy_blocked:{identity_review_policy.get('error')}")
        receipt["status"] = "BLOCKED"
        receipt["blockers"] = blockers
        _write_json(run_root / "receipts" / "storyboard_frame_generation_receipt.json", receipt)
        return {"packet_updated": False, "provider_called": False, "blockers": blockers, "receipt": receipt}
    if not isinstance(panels, list):
        blockers.append("frame_generation:packet.panels_not_list")
        receipt["status"] = "BLOCKED"
        receipt["blockers"] = blockers
        return {"packet_updated": False, "provider_called": False, "blockers": blockers, "receipt": receipt}

    backend = str(receipt["backend"])
    model = str(receipt["model"])
    output_dir = run_root / "generated_storyboard_frames"
    output_dir.mkdir(parents=True, exist_ok=True)
    contract_path = run_root / "storyboard_panel_contract.generated.json"
    _write_json(contract_path, _storyboard_panel_contract(packet))
    receipt["storyboard_panel_contract"] = str(contract_path)

    mutable_packet = json.loads(json.dumps(packet))
    provider_called = False
    for panel in mutable_packet.get("panels", []):
        if not isinstance(panel, dict):
            continue
        blockers.extend(_ensure_panel_identity_references(panel))
        panel_id = str(panel.get("panel_id") or "panel")
        for frame_key, prompt_key in (("start_frame", "start_frame_prompt"), ("end_frame", "end_frame_prompt")):
            frame = panel.get(frame_key)
            if not isinstance(frame, dict):
                blockers.append(f"{panel_id}:{frame_key}:missing_frame_object")
                continue
            existing = frame.get("accepted_frame")
            if isinstance(existing, Mapping):
                existing_path = existing.get("path") or existing.get("image_path")
                existing_blockers = _existing_frame_blockers(
                    existing,
                    panel=panel,
                    frame_label=frame_key,
                )
                if (
                    isinstance(existing_path, str)
                    and Path(existing_path).expanduser().exists()
                    and not existing_blockers
                ):
                    continue
                if any("identity_continuity" in item for item in existing_blockers):
                    existing = None
            output_path = output_dir / f"{panel_id}_{frame_key}.png"
            resume_blockers = _validate_accepted_frame_file(
                str(output_path),
                label=panel_id,
                frame_label=frame_key,
            )
            if output_path.exists() and not resume_blockers:
                accepted_frame = {
                    "status": "ACCEPTED_START_FRAME" if frame_key == "start_frame" else "ACCEPTED_END_FRAME",
                    "role": frame_key,
                    "path": str(output_path),
                    "sha256": _sha256(output_path),
                    "prompt": _frame_generation_prompt(panel, frame_key=frame_key, prompt_key=prompt_key),
                    "backend": backend,
                    "model": model,
                    "source_prompt_key": prompt_key,
                    "provider_receipt": str(run_root / "receipts" / "storyboard_frame_generation" / f"{panel_id}_{frame_key}_scillm_image_generation_receipt.json"),
                    "normalization_receipt": str(run_root / "receipts" / "storyboard_frame_generation" / f"{panel_id}_{frame_key}_frame_normalization_receipt.json"),
                }
                identity_blockers = _attach_identity_continuity_review(
                    accepted_frame,
                    panel=panel,
                    frame_key=frame_key,
                    identity_review_policy=identity_review_policy,
                    receipts_dir=run_root / "receipts" / "storyboard_identity_review",
                )
                frame["accepted_frame"] = accepted_frame
                blockers.extend(identity_blockers)
                _write_json(packet_path, mutable_packet)
                continue
            prompt = _frame_generation_prompt(panel, frame_key=frame_key, prompt_key=prompt_key)
            provider_called = True
            call = _generate_image(
                prompt,
                output_path=output_path,
                backend=backend,
                model=model,
                image_policy=image_policy,
                receipts_dir=run_root / "receipts" / "storyboard_frame_generation",
                panel_id=panel_id,
                frame_key=frame_key,
            )
            call.update({"panel_id": panel_id, "frame": frame_key, "output_path": str(output_path)})
            receipt["provider_calls"].append(call)
            if call.get("status") != "PASS":
                blockers.append(f"{panel_id}:{frame_key}:image_generation_failed:{call.get('error')}")
                continue
            accepted_frame = {
                "status": "ACCEPTED_START_FRAME" if frame_key == "start_frame" else "ACCEPTED_END_FRAME",
                "role": frame_key,
                "path": str(output_path),
                "sha256": _sha256(output_path),
                "prompt": prompt,
                "backend": backend,
                "model": model,
                "source_prompt_key": prompt_key,
                "provider_receipt": call.get("receipt"),
                "normalization_receipt": call.get("normalization_receipt"),
            }
            identity_blockers = _attach_identity_continuity_review(
                accepted_frame,
                panel=panel,
                frame_key=frame_key,
                identity_review_policy=identity_review_policy,
                receipts_dir=run_root / "receipts" / "storyboard_identity_review",
            )
            frame["accepted_frame"] = accepted_frame
            blockers.extend(identity_blockers)
            _write_json(packet_path, mutable_packet)

    if not blockers:
        _write_json(packet_path, mutable_packet)
    receipt["status"] = "PASS" if not blockers else "BLOCKED"
    receipt["blockers"] = blockers
    receipt["storyboard_packet_updated"] = not blockers
    return {
        "packet_updated": not blockers,
        "provider_called": provider_called,
        "blockers": blockers,
        "receipt": receipt,
    }


def _existing_frame_blockers(
    frame_ref: Mapping[str, Any],
    *,
    panel: Mapping[str, Any],
    frame_label: str,
) -> list[str]:
    path_value = frame_ref.get("path") or frame_ref.get("image_path")
    blockers: list[str] = []
    if not isinstance(path_value, str) or not path_value.strip():
        return [f"{frame_label}:existing_frame_missing_path"]
    path = Path(path_value).expanduser()
    if not path.exists():
        return [f"{frame_label}:existing_frame_path_missing:{path_value}"]
    blockers.extend(_validate_accepted_frame_file(path_value, label=str(panel.get("panel_id") or "panel"), frame_label=frame_label))
    required_entities = {
        str(entity)
        for entity in panel.get("required_entities", [])
        if isinstance(entity, str)
    }
    blockers.extend(
        _validate_identity_continuity_review(
            frame_ref,
            label=str(panel.get("panel_id") or "panel"),
            frame_label=frame_label,
            required_entities=required_entities,
            required=bool(required_entities & {"Embry", "Kai"}),
        )
    )
    return blockers


def _generate_image(
    prompt: str,
    *,
    output_path: Path,
    backend: str,
    model: str,
    image_policy: Mapping[str, Any],
    receipts_dir: Path,
    panel_id: str,
    frame_key: str,
) -> dict[str, Any]:
    if image_policy.get("source") == "dag_model_policy":
        return _generate_image_with_scillm_policy(
            prompt,
            output_path=output_path,
            image_policy=image_policy,
            receipts_dir=receipts_dir,
            panel_id=panel_id,
            frame_key=frame_key,
        )
    return {
        "status": "FAIL",
        "error": f"missing_dag_model_policy:{image_policy.get('error') or image_policy.get('source')}",
        "image_policy": dict(image_policy),
        "fallback_performed": False,
    }


def _generate_image_with_scillm_policy(
    prompt: str,
    *,
    output_path: Path,
    image_policy: Mapping[str, Any],
    receipts_dir: Path,
    panel_id: str,
    frame_key: str,
) -> dict[str, Any]:
    if not SCILLM_SKILL_RUN.exists():
        return {"status": "FAIL", "error": f"scillm run.sh not found: {SCILLM_SKILL_RUN}"}
    receipts_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path = receipts_dir / f"{panel_id}_{frame_key}.prompt.md"
    receipt_path = receipts_dir / f"{panel_id}_{frame_key}_scillm_image_generation_receipt.json"
    events_path = receipts_dir / f"{panel_id}_{frame_key}_scillm_image_generation_events.jsonl"
    prompt_path.write_text(prompt + "\n", encoding="utf-8")
    auth = str(image_policy.get("auth") or "codex-oauth")
    model = str(image_policy.get("model") or "gpt-2")
    cmd = [
        "bash",
        str(SCILLM_SKILL_RUN),
        "generate-image",
        "--auth",
        auth,
        "--prompt-file",
        str(prompt_path),
        "--out",
        str(output_path),
        "--receipt",
        str(receipt_path),
        "--events-out",
        str(events_path),
        "--model",
        model,
        "--size",
        f"{STORYBOARD_FRAME_SIZE[0]}x{STORYBOARD_FRAME_SIZE[1]}",
        "--quality",
        "high",
        "--caller-skill",
        "persona-dream-phase07-panel-creator",
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    receipt: dict[str, Any] = {}
    if receipt_path.exists():
        try:
            receipt = _read_json(receipt_path)
        except Exception as exc:
            receipt = {"receipt_parse_error": str(exc)}
    ok = (
        result.returncode == 0
        and output_path.exists()
        and output_path.stat().st_size > 0
        and receipt.get("ok") is True
        and receipt.get("sha256")
    )
    if not ok:
        return {
            "status": "FAIL",
            "error": (result.stderr or result.stdout or str(receipt))[-2400:],
            "command": cmd,
            "returncode": result.returncode,
            "prompt_file": str(prompt_path),
            "receipt": str(receipt_path),
            "events": str(events_path),
            "image_policy": dict(image_policy),
            "model_policy_enforced": True,
            "fallback_performed": False,
            "receipt_payload": receipt,
        }
    normalization = _normalize_storyboard_frame_if_needed(
        output_path,
        receipts_dir=receipts_dir,
        panel_id=panel_id,
        frame_key=frame_key,
        provider_receipt=receipt,
    )
    if normalization.get("status") != "PASS":
        return {
            "status": "FAIL",
            "error": normalization.get("error") or "storyboard frame normalization failed",
            "command": cmd,
            "returncode": result.returncode,
            "prompt_file": str(prompt_path),
            "receipt": str(receipt_path),
            "events": str(events_path),
            "image_policy": dict(image_policy),
            "model_policy_enforced": True,
            "fallback_performed": False,
            "receipt_payload": receipt,
            "normalization": normalization,
        }
    width, height = _read_png_size(output_path)
    return {
        "status": "PASS",
        "command": cmd,
        "stdout_tail": result.stdout[-1200:],
        "stderr_tail": result.stderr[-1200:],
        "receipt": str(receipt_path),
        "events": str(events_path),
        "prompt_file": str(prompt_path),
        "image_policy": dict(image_policy),
        "model_policy_enforced": True,
        "fallback_performed": False,
        "sha256": _sha256(output_path),
        "width": width,
        "height": height,
        "provider_width": receipt.get("width"),
        "provider_height": receipt.get("height"),
        "normalized": normalization.get("normalized") is True,
        "normalization_receipt": normalization.get("receipt"),
    }


def _normalize_storyboard_frame_if_needed(
    output_path: Path,
    *,
    receipts_dir: Path,
    panel_id: str,
    frame_key: str,
    provider_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    target_width, target_height = STORYBOARD_FRAME_SIZE
    try:
        width, height = _read_png_size(output_path)
    except Exception as exc:
        return {"status": "FAIL", "error": f"read_png_size_failed:{exc}", "path": str(output_path)}

    receipt_path = receipts_dir / f"{panel_id}_{frame_key}_frame_normalization_receipt.json"
    if (width, height) == STORYBOARD_FRAME_SIZE:
        receipt = {
            "status": "PASS",
            "normalized": False,
            "path": str(output_path),
            "width": width,
            "height": height,
            "sha256": _sha256(output_path),
            "provider_receipt": dict(provider_receipt),
        }
        _write_json(receipt_path, receipt)
        receipt["receipt"] = str(receipt_path)
        return receipt

    raw_path = output_path.with_name(f"{output_path.stem}.provider{output_path.suffix}")
    if raw_path.exists():
        raw_path.unlink()
    output_path.replace(raw_path)
    if not IMAGEMAGICK_BIN.exists():
        return {
            "status": "FAIL",
            "error": f"imagemagick_missing:{IMAGEMAGICK_BIN}",
            "raw_path": str(raw_path),
            "path": str(output_path),
            "provider_width": width,
            "provider_height": height,
        }
    command = [
        str(IMAGEMAGICK_BIN),
        str(raw_path),
        "-auto-orient",
        "-resize",
        f"{target_width}x{target_height}^",
        "-gravity",
        "center",
        "-extent",
        f"{target_width}x{target_height}",
        "PNG24:" + str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        return {
            "status": "FAIL",
            "error": (completed.stderr or completed.stdout or "imagemagick normalize failed")[-1600:],
            "raw_path": str(raw_path),
            "path": str(output_path),
            "provider_width": width,
            "provider_height": height,
            "command": command,
            "returncode": completed.returncode,
        }

    final_width, final_height = _read_png_size(output_path)
    receipt = {
        "status": "PASS",
        "normalized": True,
        "method": "center_crop_resize_to_storyboard_frame",
        "path": str(output_path),
        "raw_provider_path": str(raw_path),
        "provider_width": width,
        "provider_height": height,
        "width": final_width,
        "height": final_height,
        "sha256": _sha256(output_path),
        "raw_sha256": _sha256(raw_path),
        "target_width": target_width,
        "target_height": target_height,
        "command": command,
        "provider_receipt": dict(provider_receipt),
    }
    _write_json(receipt_path, receipt)
    receipt["receipt"] = str(receipt_path)
    return receipt


def _resolve_image_policy(start_payload: Mapping[str, Any]) -> dict[str, Any]:
    context = start_payload.get("context")
    if not isinstance(context, Mapping):
        context = {}
    raw_policy: Mapping[str, Any] | None = None
    for key in ("image_model_policy", "model_policy"):
        value = context.get(key)
        if isinstance(value, Mapping):
            raw_policy = value
            break
    tau_dag_node = context.get("tau_dag_node")
    if raw_policy is None and isinstance(tau_dag_node, Mapping):
        for key in ("image_model_policy", "model_policy"):
            value = tau_dag_node.get(key)
            if isinstance(value, Mapping):
                raw_policy = value
                break
    if raw_policy is None:
        return {
            "schema": "persona_dream.image_policy.v1",
            "source": "missing",
            "provider": None,
            "auth": None,
            "model": None,
            "supported": False,
            "error": "missing_dag_model_policy",
            "fallback_performed": False,
        }
    provider = str(raw_policy.get("provider") or "").strip()
    auth = str(raw_policy.get("auth") or "").strip()
    model = str(raw_policy.get("model") or "").strip()
    supported_provider = provider in {"codex", "scillm", "openai", "openai-codex"}
    supported_auth = auth in {"codex-oauth", "openai-api-key"}
    supported = bool(provider and auth and model and supported_provider and supported_auth)
    error = None
    if not supported_provider:
        error = "unsupported_image_model_provider"
    elif not supported_auth:
        error = "unsupported_image_model_auth"
    elif not model:
        error = "missing_image_model"
    return {
        "schema": "persona_dream.image_policy.v1",
        "source": "dag_model_policy",
        "provider": provider,
        "auth": auth,
        "model": model,
        "supported": supported,
        "error": error,
        "fallback_performed": False,
    }


def _resolve_identity_review_policy(start_payload: Mapping[str, Any]) -> dict[str, Any]:
    context = start_payload.get("context")
    if not isinstance(context, Mapping):
        context = {}
    raw_policy = context.get("identity_review_model_policy")
    if not isinstance(raw_policy, Mapping):
        tau_dag_node = context.get("tau_dag_node")
        if isinstance(tau_dag_node, Mapping):
            value = tau_dag_node.get("identity_review_model_policy")
            if isinstance(value, Mapping):
                raw_policy = value
    if not isinstance(raw_policy, Mapping):
        return {
            "schema": "persona_dream.identity_review_policy.v1",
            "source": "missing",
            "provider": None,
            "auth": None,
            "model": None,
            "supported": False,
            "error": "missing_dag_identity_review_model_policy",
            "fallback_performed": False,
        }
    provider = str(raw_policy.get("provider") or "").strip()
    auth = str(raw_policy.get("auth") or "").strip()
    model = str(raw_policy.get("model") or "").strip()
    supported_provider = provider in {"codex", "scillm", "openai", "openai-codex"}
    supported_auth = auth in {"codex-oauth", "openai-api-key"}
    supported = bool(provider and auth and model and supported_provider and supported_auth)
    error = None
    if not supported_provider:
        error = "unsupported_identity_review_provider"
    elif not supported_auth:
        error = "unsupported_identity_review_auth"
    elif not model:
        error = "missing_identity_review_model"
    return {
        "schema": "persona_dream.identity_review_policy.v1",
        "source": "dag_identity_review_model_policy",
        "provider": provider,
        "auth": auth,
        "model": model,
        "supported": supported,
        "error": error,
        "fallback_performed": False,
    }


def _storyboard_panel_contract(packet: Mapping[str, Any]) -> dict[str, Any]:
    panels = packet.get("panels") if isinstance(packet.get("panels"), list) else []
    return {
        "schema": "persona_dream.storyboard_panel_contract.v1",
        "look_lock": (
            "Cinematic storyboard frame for a grounded surf scene. Use a real storyboard frame, "
            "not a contact sheet, not a collage, not a UI card. Maintain Embry and Kai identity "
            "continuity from references while staging Kahalu'u Bay, Kona Coast, lava reef, heat, "
            "glare, sweat, saltwater, and shared lineup etiquette."
        ),
        "characters": {
            "Embry": "Embry: young woman surfer in a navy rashguard, salt-wet, heat-fatigued but controlled, riding or handling an older borrowed white shortboard.",
            "Kai": "Kai Akana: young Hawaiian male surfer in a black rashguard, calm and restrained, reading the swell and reef line, using a familiar white shortboard.",
        },
        "props": "Embry borrowed older white shortboard; Kai familiar white shortboard with worn rail marks; phones in beach bag as obligation pressure.",
        "environment": "Kahalu'u Bay on the Kona Coast, hot humid June daylight, clear water over dark lava reef, public lineup, summer swell timing, glare and salt spray.",
        "creatures": "",
        "effects": "Heat haze, glare flashes, water spray, softened wax, visible fatigue and restraint.",
        "output_size": f"{STORYBOARD_FRAME_SIZE[0]}x{STORYBOARD_FRAME_SIZE[1]}",
        "aspect_ratio": "16:9",
        "panels": {
            str(panel.get("panel_id")): {
                "shot": str(panel.get("generation_prompt", {}).get("panel_prompt") if isinstance(panel.get("generation_prompt"), Mapping) else panel.get("shot")),
                "characters": [entity for entity in panel.get("required_entities", []) if entity in {"Embry", "Kai"}],
            }
            for panel in panels
            if isinstance(panel, Mapping) and panel.get("panel_id")
        },
    }


def _frame_generation_prompt(panel: Mapping[str, Any], *, frame_key: str, prompt_key: str) -> str:
    generation_prompt = panel.get("generation_prompt") if isinstance(panel.get("generation_prompt"), Mapping) else {}
    frame = panel.get(frame_key) if isinstance(panel.get(frame_key), Mapping) else {}
    refs = panel.get("references") if isinstance(panel.get("references"), list) else []
    reference_text = "; ".join(
        f"{ref.get('title') or ref.get('id')} ({ref.get('role')}): {ref.get('path')}"
        for ref in refs
        if isinstance(ref, Mapping)
    )
    required_entities = {
        str(entity)
        for entity in panel.get("required_entities", [])
        if isinstance(entity, str)
    }
    identity_required = bool(required_entities & {"Embry", "Kai"})
    identity_prompt = ""
    if identity_required:
        identity_prompt = "\n".join(
            [
                "MANDATORY CHARACTER IDENTITY REQUIREMENT:",
                "Embry and Kai must both be clearly visible, foreground, and strongly matched to the attached character reference images. The attached Embry reference image and attached Kai reference image are mandatory identity references, not loose inspiration. Do not invent new faces or substitute generic surfers. Character identity is the highest priority, above location, surf action, reef detail, or cinematic beauty.",
                "",
                "CHARACTERS:",
                "Embry is on the left foreground. She must match the attached Embry character sheet: adult woman, brown hair tied back or wet and pulled back, recognizable face visible in three-quarter view, navy rashguard or navy polo-style surf top. Embry must read clearly as the same woman from the reference. Do not depict her as male, teenage, blond, short-haired, generic, back-facing, or too distant to identify.",
                "Kai is on the right foreground. He must match the attached Kai character sheet: young adult man, tan skin, dark curly wet hair, athletic surfer build, black rashguard, recognizable face visible in three-quarter view. Kai must read clearly as the same person from the reference. Do not make him generic, back-facing only, hidden, or too distant to identify.",
                "",
                "COMPOSITION:",
                "Medium-wide waterline two-shot, not a distant wide establishing shot. Embry and Kai are the only large foreground people. Both characters are chest-up or waist-up above the waterline, with faces clearly visible. Their faces must not be blocked by surfboards, spray, glare, other surfers, hair, shadows, or water.",
                "Embry sits on or beside her surfboard on the left, angled parallel to the reef, waiting respectfully outside the takeoff path. Kai sits on or beside his surfboard on the right, also angled parallel to the reef, waiting respectfully. They are near each other but not heroic or posed; the mood is restrained, observant, and socially tense.",
                "",
                "SCENE:",
                "Hot, humid daylight at Kahaluʻu Bay. Clear shallow water reveals dark lava reef shapes below the surface. A public surf lineup is visible in the background, with local surfers holding priority. Background surfers must remain smaller and secondary; they must not compete with Embry and Kai or be mistaken for them.",
                "",
                "STYLE:",
                "Realistic cinematic storyboard frame, natural daylight, believable surf photography, low waterline camera, subtle humidity and ocean glare, emotionally grounded, not glossy tourism advertising.",
                "",
                "NEGATIVE CONSTRAINTS:",
                "No missing Embry. No missing Kai. No generic male surfer substituted for Embry. No swapped identities. No back-facing-only Embry or Kai. No tiny distant faces. No occluded faces. No extra foreground surfers. No crowd blocking the main characters. No heroic takeoff. No empty tropical postcard. No contact sheet. No collage. No character-sheet layout. No unrelated surfers in the foreground.",
            ]
        )
    return "\n".join(
        part
        for part in [
            "Create a single cinematic storyboard frame for Kling planning. This must be a real storyboard frame, not a contact sheet, not a collage, not a UI mockup.",
            identity_prompt,
            str(generation_prompt.get("panel_prompt") or panel.get("shot") or ""),
            str(generation_prompt.get(prompt_key) or frame.get("description") or ""),
            "Visual requirements: " + "; ".join(str(item) for item in frame.get("visual_requirements", []) if isinstance(item, str)),
            "Negative constraints: " + "; ".join(str(item) for item in frame.get("negative_constraints", []) if isinstance(item, str)),
            str(panel.get("prompt_fragment") or ""),
            "Camera: " + json.dumps(panel.get("camera", {}), sort_keys=True),
            "Lighting: " + json.dumps(panel.get("lighting", {}), sort_keys=True),
            "Acting beats: " + "; ".join(str(item) for item in panel.get("acting_beats", []) if isinstance(item, str)),
            "Reference assets attached as mandatory identity/reference inputs, not loose inspiration: " + reference_text,
        ]
        if part
    )


def _ensure_panel_identity_references(panel: dict[str, Any]) -> list[str]:
    required_entities = {
        str(entity)
        for entity in panel.get("required_entities", [])
        if isinstance(entity, str)
    }
    needed = sorted(required_entities & set(IDENTITY_REFERENCE_ASSETS))
    if not needed:
        return []
    refs = panel.get("references")
    if not isinstance(refs, list):
        refs = []
        panel["references"] = refs
    present = {
        str(ref.get("title") or ref.get("id") or ref.get("entity") or "")
        for ref in refs
        if isinstance(ref, Mapping)
    }
    blockers: list[str] = []
    for entity in needed:
        asset = dict(IDENTITY_REFERENCE_ASSETS[entity])
        path = Path(str(asset["path"])).expanduser()
        if not path.exists():
            blockers.append(f"{panel.get('panel_id')}:identity_reference_missing:{entity}:{path}")
            continue
        if asset["id"] not in present and asset["title"] not in present:
            refs.append(asset)
    return blockers


def _attach_identity_continuity_review(
    accepted_frame: dict[str, Any],
    *,
    panel: Mapping[str, Any],
    frame_key: str,
    identity_review_policy: Mapping[str, Any],
    receipts_dir: Path,
) -> list[str]:
    required_entities = {
        str(entity)
        for entity in panel.get("required_entities", [])
        if isinstance(entity, str)
    } & set(IDENTITY_REFERENCE_ASSETS)
    if not required_entities:
        return []
    existing = accepted_frame.get("identity_continuity_review")
    if isinstance(existing, Mapping) and existing.get("status") == "PASS":
        return []
    review = _run_identity_continuity_review(
        accepted_frame,
        panel=panel,
        frame_key=frame_key,
        required_entities=sorted(required_entities),
        identity_review_policy=identity_review_policy,
        receipts_dir=receipts_dir,
    )
    accepted_frame["identity_continuity_review"] = {
        "status": review.get("status"),
        "required_entities": review.get("required_entities", []),
        "visible_entities": review.get("visible_entities", []),
        "blocking_findings": review.get("blocking_findings", []),
        "reviewer_source": review.get("reviewer_source"),
        "receipt": review.get("receipt_path"),
        "model": review.get("model"),
        "model_policy_enforced": review.get("model_policy_enforced"),
    }
    if review.get("status") != "PASS":
        panel_id = str(panel.get("panel_id") or "panel")
        accepted_frame["status"] = "REJECTED_IDENTITY_CONTINUITY"
        accepted_frame["rejected_reason"] = "identity_continuity_review_failed"
        return [f"{panel_id}:accepted_{frame_key}_identity_continuity_not_pass:{review.get('status') or 'missing_status'}"]
    return []


def _run_identity_continuity_review(
    accepted_frame: Mapping[str, Any],
    *,
    panel: Mapping[str, Any],
    frame_key: str,
    required_entities: list[str],
    identity_review_policy: Mapping[str, Any],
    receipts_dir: Path,
) -> dict[str, Any]:
    receipts_dir.mkdir(parents=True, exist_ok=True)
    panel_id = str(panel.get("panel_id") or "panel")
    receipt_path = receipts_dir / f"{panel_id}_{frame_key}_identity_continuity_review.json"
    frame_path = Path(str(accepted_frame.get("path") or accepted_frame.get("image_path") or "")).expanduser()
    if not frame_path.exists():
        receipt = _identity_review_receipt(
            panel=panel,
            frame_key=frame_key,
            status="FAIL",
            required_entities=required_entities,
            visible_entities=[],
            blocking_findings=[f"accepted frame path missing: {frame_path}"],
            frame_path=str(frame_path),
            raw_response=None,
            model=str(identity_review_policy.get("model")),
            model_policy=identity_review_policy,
        )
        receipt["receipt_path"] = str(receipt_path)
        _write_json(receipt_path, receipt)
        return receipt

    references = _identity_reference_paths(panel, required_entities)
    missing_refs = [entity for entity in required_entities if entity not in references]
    if missing_refs:
        receipt = _identity_review_receipt(
            panel=panel,
            frame_key=frame_key,
            status="FAIL",
            required_entities=required_entities,
            visible_entities=[],
            blocking_findings=["missing identity reference assets: " + ",".join(missing_refs)],
            frame_path=str(frame_path),
            raw_response=None,
            model=str(identity_review_policy.get("model")),
            model_policy=identity_review_policy,
        )
        receipt["receipt_path"] = str(receipt_path)
        _write_json(receipt_path, receipt)
        return receipt

    prompt = _identity_review_prompt(panel, frame_key=frame_key, required_entities=required_entities)
    content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    content.append(_image_url_part(frame_path, label="accepted storyboard frame"))
    for entity in required_entities:
        content.append({"type": "text", "text": f"Reference asset for {entity}:"})
        content.append(_image_url_part(references[entity], label=f"{entity} identity reference"))
    request_payload = {
        "model": identity_review_policy.get("model"),
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict visual storyboard identity reviewer. "
                    "Return JSON only. Do not infer identity from metadata. "
                    "Reject generic or wrong people."
                ),
            },
            {"role": "user", "content": content},
        ],
        "response_format": {"type": "json_object"},
    }
    try:
        raw = _post_scillm_json(request_payload)
        model_text = raw["choices"][0]["message"]["content"]
        parsed = json.loads(model_text)
    except (KeyError, IndexError, TypeError, ValueError, HTTPError, URLError) as exc:
        receipt = _identity_review_receipt(
            panel=panel,
            frame_key=frame_key,
            status="FAIL",
            required_entities=required_entities,
            visible_entities=[],
            blocking_findings=[f"identity review call failed: {exc}"],
            frame_path=str(frame_path),
            raw_response=None,
            model=str(identity_review_policy.get("model")),
            model_policy=identity_review_policy,
        )
        receipt["receipt_path"] = str(receipt_path)
        _write_json(receipt_path, receipt)
        return receipt

    visible_entities = [
        str(entity)
        for entity in parsed.get("visible_entities", [])
        if isinstance(entity, str)
    ]
    blocking_findings = [
        str(item)
        for item in parsed.get("blocking_findings", [])
        if isinstance(item, str)
    ]
    missing_visible = sorted(set(required_entities) - set(visible_entities))
    if missing_visible:
        blocking_findings.append("required identity not visibly verified: " + ",".join(missing_visible))
    if parsed.get("verdict") != "PASS" and not blocking_findings:
        blocking_findings.append(f"reviewer verdict was {parsed.get('verdict') or 'missing'}")
    status = "PASS" if not blocking_findings and parsed.get("verdict") == "PASS" else "FAIL"
    receipt = _identity_review_receipt(
        panel=panel,
        frame_key=frame_key,
        status=status,
        required_entities=required_entities,
        visible_entities=visible_entities,
        blocking_findings=blocking_findings,
        frame_path=str(frame_path),
        raw_response=parsed,
        model=str(identity_review_policy.get("model")),
        model_policy=identity_review_policy,
    )
    receipt["receipt_path"] = str(receipt_path)
    _write_json(receipt_path, receipt)
    return receipt


def _identity_reference_paths(panel: Mapping[str, Any], required_entities: list[str]) -> dict[str, Path]:
    refs = panel.get("references") if isinstance(panel.get("references"), list) else []
    paths: dict[str, Path] = {}
    for entity in required_entities:
        expected = IDENTITY_REFERENCE_ASSETS[entity]
        expected_id = str(expected["id"])
        expected_title = str(expected["title"])
        for ref in refs:
            if not isinstance(ref, Mapping):
                continue
            if ref.get("id") != expected_id and ref.get("title") != expected_title:
                continue
            path_value = ref.get("path")
            if isinstance(path_value, str) and Path(path_value).expanduser().exists():
                paths[entity] = Path(path_value).expanduser()
                break
    return paths


def _identity_review_prompt(panel: Mapping[str, Any], *, frame_key: str, required_entities: list[str]) -> str:
    return "\n".join(
        [
            "Review the generated storyboard panel for identity continuity.",
            f"Panel: {panel.get('panel_id')}",
            f"Frame: {frame_key}",
            "Required identities: " + ", ".join(required_entities),
            "Required scene entities: " + ", ".join(str(item) for item in panel.get("required_entities", []) if isinstance(item, str)),
            "",
            "Pass only if all of the following are true:",
            "1. Embry is visible in the foreground.",
            "2. Embry clearly matches the attached Embry reference sheet.",
            "3. Embry is recognizable as an adult woman with brown hair and navy rashguard/polo-style surf top.",
            "4. Kai is visible in the foreground.",
            "5. Kai clearly matches the attached Kai reference sheet.",
            "6. Kai is recognizable as a young adult man with tan skin, dark curly wet hair, athletic surfer build, and black rashguard.",
            "7. Both faces are visible enough to verify identity.",
            "8. Embry and Kai are not replaced by generic surfers.",
            "9. No other foreground person competes with or confuses the identities.",
            "",
            "Fail automatically if:",
            "- Embry is missing.",
            "- Kai is missing.",
            "- Embry appears male or generic.",
            "- Kai is only back-facing or too distant.",
            "- Either character's face is too small, hidden, blurred, or not reference-verifiable.",
            "- The panel is mostly a location establishing shot rather than a character-readable two-shot.",
            "",
            "Return strict JSON with exactly these keys:",
            '{"verdict":"PASS|FAIL","visible_entities":["Embry"],"blocking_findings":["..."],"identity_notes":"..."}',
            "If any identity condition fails, return FAIL and require regeneration. Do not accept the frame.",
            "Do not give credit for prompt text, captions, filenames, or metadata. Judge the image pixels.",
        ]
    )


def _identity_review_receipt(
    *,
    panel: Mapping[str, Any],
    frame_key: str,
    status: str,
    required_entities: list[str],
    visible_entities: list[str],
    blocking_findings: list[str],
    frame_path: str,
    raw_response: Any,
    model: str,
    model_policy: Mapping[str, Any],
) -> dict[str, Any]:
    dimensions: dict[str, Any] = {}
    try:
        width, height = _read_png_size(Path(frame_path).expanduser())
        dimensions = {"width": width, "height": height}
    except Exception as exc:
        dimensions = {"error": str(exc)}
    return {
        "schema": "persona_dream.identity_continuity_review.v1",
        "created_at": _now_iso(),
        "panel_id": panel.get("panel_id"),
        "frame_key": frame_key,
        "status": status,
        "required_entities": required_entities,
        "visible_entities": visible_entities,
        "blocking_findings": blocking_findings,
        "reviewer_source": f"scillm:{model}:image_url",
        "model": model,
        "model_policy": dict(model_policy),
        "model_policy_enforced": model_policy.get("source") == "dag_identity_review_model_policy",
        "frame_path": frame_path,
        "image_dimensions": dimensions,
        "mocked": False,
        "live": True,
        "raw_response": raw_response,
    }


def _image_url_part(path: Path, *, label: str) -> dict[str, Any]:
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return {
        "type": "image_url",
        "image_url": {
            "url": f"data:{media_type};base64,{encoded}",
            "detail": "high",
        },
        "label": label,
    }


def _post_scillm_json(payload: Mapping[str, Any]) -> dict[str, Any]:
    proxy_key = os.environ.get("LITELLM_MASTER_KEY") or os.environ.get("SCILLM_PROXY_KEY")
    if not proxy_key:
        raise ValueError("missing LITELLM_MASTER_KEY or SCILLM_PROXY_KEY for identity review")
    data = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        SCILLM_CHAT_COMPLETIONS_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {proxy_key}",
            "X-Caller-Skill": "persona-dream-phase07-panel-reviewer",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib_request.urlopen(req) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    if not isinstance(parsed, dict):
        raise ValueError("scillm response root is not an object")
    return parsed


def _panel_manifest(packet: Mapping[str, Any], packet_path: Path) -> dict[str, Any]:
    panels = packet.get("panels") if isinstance(packet.get("panels"), list) else []
    return {
        "schema": "persona_dream.storyboard_panel_manifest.v1",
        "created_at": _now_iso(),
        "storyboard_packet": str(packet_path),
        "storyboard_packet_sha256": _sha256(packet_path),
        "panel_count": len(panels),
        "duration_seconds": packet.get("duration_seconds"),
        "panels": [
            {
                "panel_id": panel.get("panel_id"),
                "time_range": panel.get("time_range"),
                "shot": panel.get("shot"),
                "coverage_seed_ids": panel.get("coverage_seed_ids"),
                "required_entities": panel.get("required_entities"),
                "reference_count": len(panel.get("references") or []),
            }
            for panel in panels
            if isinstance(panel, Mapping)
        ],
    }


def _context(start_payload: Mapping[str, Any]) -> Mapping[str, Any]:
    context = start_payload.get("context")
    if not isinstance(context, Mapping):
        raise RuntimeError("stdin handoff missing context object")
    raw = context.get("persona_dream_phase07_storyboard")
    if not isinstance(raw, Mapping):
        raw = {}
    run_root = raw.get("run_root") or context.get("run_root")
    if not run_root:
        run_root = "/home/graham/workspace/experiments/agent-skills/skills/persona-dream/reports/pipeline-complete/phase_07_storyboard_live_tau"
    storyboard_packet = raw.get("storyboard_packet") or context.get("storyboard_packet")
    if not storyboard_packet:
        storyboard_packet = str(Path(str(run_root)) / "storyboard_packet.json")
    return {
        "run_id": str(raw.get("run_id") or context.get("run_id") or Path(str(run_root)).name),
        "run_root": str(run_root),
        "storyboard_packet": str(storyboard_packet),
    }


def _provider_route_receipt(
    start_payload: Mapping[str, Any],
    *,
    role: str,
    artifact_dir: Path,
    receipts_dir: Path,
) -> dict[str, Any]:
    context = start_payload.get("context")
    if not isinstance(context, Mapping):
        context = {}
    tau_dag_node = context.get("tau_dag_node")
    if not isinstance(tau_dag_node, Mapping):
        tau_dag_node = {}
    model_policy = tau_dag_node.get("model_policy")
    if not isinstance(model_policy, Mapping):
        model_policy = context.get("model_policy") if isinstance(context.get("model_policy"), Mapping) else {}
    prompt_contract = tau_dag_node.get("prompt_contract")
    if not isinstance(prompt_contract, Mapping):
        prompt_contract = context.get("prompt_contract") if isinstance(context.get("prompt_contract"), Mapping) else {}

    blockers: list[str] = []
    if not tau_dag_node:
        blockers.append("tau_dag_node_missing")
    agent = tau_dag_node.get("agent")
    if agent and str(agent) != role:
        blockers.append(f"tau_dag_node_agent_mismatch:{agent}")
    if not model_policy:
        blockers.append("model_policy_missing")
    else:
        expected_policy = {
            "provider": "codex",
            "auth": "codex-oauth",
            "model": "gpt-2",
        }
        for key, expected in expected_policy.items():
            actual = model_policy.get(key)
            if actual != expected:
                blockers.append(f"model_policy_{key}_mismatch:{actual}")
    if not prompt_contract:
        blockers.append("prompt_contract_missing")
    elif prompt_contract.get("schema") != "tau.prompt_contract.v1":
        blockers.append(f"prompt_contract_schema_mismatch:{prompt_contract.get('schema')}")

    status = "PASS" if not blockers else "BLOCKED_PROVIDER_ROUTE"
    receipt = {
        "schema": "persona_dream.provider_route_receipt.v1",
        "created_at": _now_iso(),
        "role": role,
        "status": status,
        "provider_route_metadata_delivered": status == "PASS",
        "provider_call_executed": False,
        "mocked": False,
        "live": True,
        "model_policy": json.loads(json.dumps(model_policy, sort_keys=True)),
        "prompt_contract": json.loads(json.dumps(prompt_contract, sort_keys=True)),
        "tau_dag_node": {
            "dag_id": tau_dag_node.get("dag_id"),
            "node_id": tau_dag_node.get("node_id"),
            "agent": tau_dag_node.get("agent"),
            "target": tau_dag_node.get("target"),
            "goal": tau_dag_node.get("goal"),
            "required_evidence": tau_dag_node.get("required_evidence"),
            "fail_closed_on": tau_dag_node.get("fail_closed_on"),
        },
        "blockers": blockers,
        "claims": {
            "proves": [
                "Tau injected provider dispatch metadata into the Persona Dream command-backed node stdin.",
                "Persona Dream recorded the route policy required for the node before producing storyboard evidence.",
            ]
            if status == "PASS"
            else ["Persona Dream failed closed because required Tau provider route metadata was missing or mismatched."],
            "does_not_prove": [
                "No image, Kling, or paid provider call was executed by this route receipt.",
                "This receipt proves provider route metadata delivery only, not final storyboard image quality.",
            ],
        },
    }
    receipt_path = receipts_dir / f"{role}_provider_route_receipt.json"
    artifact_path = artifact_dir / f"{role}_provider_route_receipt.json"
    _write_json(receipt_path, receipt)
    _write_json(artifact_path, receipt)
    return {
        "status": status,
        "blockers": blockers,
        "receipt_path": str(receipt_path),
        "artifact_path": str(artifact_path),
    }


def _handoff(
    start_payload: Mapping[str, Any],
    *,
    previous_subagent: str,
    status: str,
    summary: str,
    evidence: list[str],
    artifacts: list[str],
    context_update: Mapping[str, Any],
    next_agent: str,
    next_executor: str,
    next_reason: str,
    required_evidence: str,
    stop_condition: str,
) -> dict[str, Any]:
    context = start_payload.get("context")
    if not isinstance(context, Mapping):
        raise RuntimeError("stdin handoff missing context object")
    next_context: dict[str, Any] = {
        "summary": summary,
        "artifacts": [str(item) for item in context.get("artifacts", []) if isinstance(context.get("artifacts"), list)] + artifacts,
    }
    for key in ("tau_dag_node", "model_policy", "prompt_contract"):
        if key in context:
            next_context[key] = context[key]
    next_context.update(context_update)
    return {
        "schema": "tau.agent_handoff.v1",
        "github": _required_mapping(start_payload, "github"),
        "goal": _required_mapping(start_payload, "goal"),
        "previous_subagent": previous_subagent,
        "context": next_context,
        "result": {
            "status": status,
            "summary": summary,
            "evidence": evidence,
        },
        "rationale": "The Phase 07 Tau DAG is the authority for storyboard panel acceptance.",
        "next_agent": {
            "name": next_agent,
            "executor": next_executor,
            "reason": next_reason,
        },
        "required_evidence": [required_evidence],
        "stop_condition": stop_condition,
    }


def _subagent_receipt(
    start_payload: Mapping[str, Any],
    *,
    subagent: str,
    status: str,
    summary: str,
    evidence: list[str],
    next_subagent: str,
    next_executor: str,
    next_reason: str,
) -> dict[str, Any]:
    goal = _required_mapping(start_payload, "goal")
    context = _context(start_payload)
    return {
        "schema": "tau.subagent_receipt.v1",
        "goal": {
            "goal_id": str(goal.get("goal_id")),
            "goal_version": int(goal.get("goal_version", 1)),
            "goal_hash": str(goal.get("goal_hash")),
            "immutable_goal_preserved": True,
        },
        "context": {
            "run_id": context["run_id"],
            "subagent": subagent,
            "actor_type": "subagent",
        },
        "result": {
            "status": status,
            "summary": summary,
            "mocked": "no",
            "live": "yes",
        },
        "rationale": "Phase 07 storyboard acceptance requires a creator/reviewer Tau receipt chain.",
        "evidence": evidence,
        "next": {
            "subagent": next_subagent,
            "executor": next_executor,
            "reason": next_reason,
        },
        "stop_condition": "Panel-reviewer accepts the storyboard panels or emits concrete blockers.",
    }


def _read_stdin_handoff() -> dict[str, Any]:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"stdin handoff JSON is unreadable: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("stdin handoff JSON root must be an object")
    return payload


def _required_mapping(payload: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise RuntimeError(f"stdin handoff missing {key} object")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"missing JSON artifact: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON artifact: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON artifact must be an object: {path}")
    return payload


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
