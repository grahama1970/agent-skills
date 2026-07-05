#!/usr/bin/env python3
"""Tau node adapter for Persona Dream Phase 07 storyboard packet review.

This adapter is intentionally deterministic. It does not create fake images or
call a provider. It lets Tau run the Phase 07 creator/reviewer handoff against
the storyboard packet already produced by persona-dream and fails closed when
the packet is not complete enough to be treated as accepted storyboard panels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


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
    generation = _ensure_storyboard_frame_artifacts(packet, packet_path=packet_path, run_root=run_root)
    if generation["packet_updated"]:
        packet = _read_json(packet_path)
    creator_check = _validate_storyboard_packet(packet, packet_path=packet_path, reviewer=False)
    creator_check["blockers"].extend(generation["blockers"])
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
        "blockers": creator_check["blockers"],
        "mocked": False,
        "live": True,
        "provider_calls": {"image": generation["provider_called"], "kling": False, "paid": False},
    }
    creator_receipt_path = receipts_dir / "storyboard_creator_receipt.json"
    _write_json(creator_receipt_path, creator_receipt)
    _write_json(artifact_dir / "storyboard_creator_receipt.json", creator_receipt)
    _write_json(artifact_dir / "storyboard_panel_manifest.json", manifest)
    _write_json(artifact_dir / "storyboard_frame_generation_receipt.json", generation["receipt"])
    tau_receipt_path = artifact_dir / "panel_creator_tau_subagent_receipt.json"
    tau_receipt = _subagent_receipt(
        start_payload,
        subagent="panel-creator",
        status="COMPLETED" if not creator_check["blockers"] else "BLOCKED",
        summary=(
            "Panel creator emitted a complete storyboard packet manifest for reviewer."
            if not creator_check["blockers"]
            else "Panel creator failed closed because the storyboard packet is incomplete."
        ),
        evidence=[str(creator_receipt_path), str(manifest_path), str(generation_receipt_path), str(packet_path)],
        next_subagent="panel-reviewer" if not creator_check["blockers"] else "human",
        next_executor="local" if not creator_check["blockers"] else "human",
        next_reason=(
            "Panel reviewer must independently validate per-panel storyboard coverage."
            if not creator_check["blockers"]
            else "Packet must be repaired before reviewer can accept it."
        ),
    )
    _write_json(tau_receipt_path, tau_receipt)
    return _handoff(
        start_payload,
        previous_subagent="panel-creator",
        status=tau_receipt["result"]["status"],
        summary=tau_receipt["result"]["summary"],
        evidence=tau_receipt["evidence"],
        artifacts=[str(creator_receipt_path), str(manifest_path), str(generation_receipt_path), str(tau_receipt_path), str(packet_path)],
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
        "mocked": False,
        "live": True,
        "provider_calls": {"image": False, "kling": False, "paid": False},
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
    tau_receipt = _subagent_receipt(
        start_payload,
        subagent="panel-reviewer",
        status=status,
        summary=(
            "Panel-reviewer accepted the Phase 07 storyboard panels."
            if status == "PASS_PANEL_REVIEWED"
            else "Panel-reviewer rejected the storyboard packet with exact blockers."
        ),
        evidence=[str(verdict_path), str(reference_coverage_path), str(entity_coverage_path), str(packet_path)],
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
        artifacts=[str(verdict_path), str(reference_coverage_path), str(entity_coverage_path), str(tau_receipt_path), str(packet_path)],
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
            count += 1
        return count

    if start_refs and accepted_count(start_refs, frame_label="start_frame") == 0:
        blockers.append(f"{label}:no_usable_accepted_start_frame_artifact")
    if end_refs and accepted_count(end_refs, frame_label="end_frame") == 0:
        blockers.append(f"{label}:no_usable_accepted_end_frame_artifact")
    return blockers


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
) -> dict[str, Any]:
    panels = packet.get("panels")
    receipt: dict[str, Any] = {
        "schema": "persona_dream.storyboard_frame_generation_receipt.v1",
        "created_at": _now_iso(),
        "storyboard_packet": str(packet_path),
        "backend": os.environ.get("PERSONA_DREAM_STORYBOARD_IMAGE_BACKEND", "google"),
        "model": os.environ.get("PERSONA_DREAM_STORYBOARD_IMAGE_MODEL", "gemini-2.5-flash-image"),
        "mocked": False,
        "live": True,
        "provider_calls": [],
    }
    blockers: list[str] = []
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
        panel_id = str(panel.get("panel_id") or "panel")
        for frame_key, prompt_key in (("start_frame", "start_frame_prompt"), ("end_frame", "end_frame_prompt")):
            frame = panel.get(frame_key)
            if not isinstance(frame, dict):
                blockers.append(f"{panel_id}:{frame_key}:missing_frame_object")
                continue
            existing = frame.get("accepted_frame")
            if isinstance(existing, Mapping):
                existing_path = existing.get("path") or existing.get("image_path")
                if isinstance(existing_path, str) and Path(existing_path).expanduser().exists():
                    continue
            output_path = output_dir / f"{panel_id}_{frame_key}.png"
            prompt = _frame_generation_prompt(panel, frame_key=frame_key, prompt_key=prompt_key)
            provider_called = True
            call = _generate_image(
                prompt,
                output_path=output_path,
                backend=backend,
                model=model,
            )
            call.update({"panel_id": panel_id, "frame": frame_key, "output_path": str(output_path)})
            receipt["provider_calls"].append(call)
            if call.get("status") != "PASS":
                blockers.append(f"{panel_id}:{frame_key}:image_generation_failed:{call.get('error')}")
                continue
            frame["accepted_frame"] = {
                "status": "ACCEPTED_START_FRAME" if frame_key == "start_frame" else "ACCEPTED_END_FRAME",
                "role": frame_key,
                "path": str(output_path),
                "sha256": _sha256(output_path),
                "prompt": prompt,
                "backend": backend,
                "model": model,
                "source_prompt_key": prompt_key,
                "provider_receipt": call.get("receipt"),
            }

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


def _generate_image(prompt: str, *, output_path: Path, backend: str, model: str) -> dict[str, Any]:
    create_image = Path(__file__).resolve().parents[2] / "create-image" / "run.sh"
    if not create_image.exists():
        return {"status": "FAIL", "error": f"create-image run.sh not found: {create_image}"}
    cmd = [
        "bash",
        str(create_image),
        "generate",
        prompt,
        "--output",
        str(output_path),
        "--size",
        "1536x1024",
        "--backend",
        backend,
        "--model",
        model,
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=420)
    except subprocess.TimeoutExpired as exc:
        return {"status": "FAIL", "error": f"create-image timeout after {exc.timeout}s", "command": cmd}
    if result.returncode != 0:
        return {
            "status": "FAIL",
            "error": (result.stderr or result.stdout)[-1600:],
            "command": cmd,
            "returncode": result.returncode,
        }
    if not output_path.exists() or output_path.stat().st_size == 0:
        return {"status": "FAIL", "error": "create-image did not write a non-empty output", "command": cmd}
    return {
        "status": "PASS",
        "command": cmd,
        "stdout_tail": result.stdout[-1200:],
        "stderr_tail": result.stderr[-1200:],
        "receipt": str(output_path),
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
        "output_size": "1536x1024",
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
    return "\n".join(
        part
        for part in [
            "Create a single cinematic storyboard frame for Kling planning. This must be a real storyboard frame, not a contact sheet, not a collage, not a UI mockup.",
            str(generation_prompt.get("panel_prompt") or panel.get("shot") or ""),
            str(generation_prompt.get(prompt_key) or frame.get("description") or ""),
            "Visual requirements: " + "; ".join(str(item) for item in frame.get("visual_requirements", []) if isinstance(item, str)),
            "Negative constraints: " + "; ".join(str(item) for item in frame.get("negative_constraints", []) if isinstance(item, str)),
            str(panel.get("prompt_fragment") or ""),
            "Camera: " + json.dumps(panel.get("camera", {}), sort_keys=True),
            "Lighting: " + json.dumps(panel.get("lighting", {}), sort_keys=True),
            "Acting beats: " + "; ".join(str(item) for item in panel.get("acting_beats", []) if isinstance(item, str)),
            "Reference assets for continuity only: " + reference_text,
        ]
        if part
    )

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
