#!/usr/bin/env python3
"""Run one transparent serial while-loop controller pass.

The runner is intentionally conservative. It validates the run root, records
the active loop and first blocker, and stops before any unapproved external
side effect. Local repair handlers can be added later one phase at a time.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path
from typing import Any

from apply_provider_media_public_probe import apply_provider_media_public_probe
from pipeline_loop_status import build_pipeline_loop_status
from stage_provider_media_local_asset import stage_provider_media_local_asset
from validate_storyboard_panel_receipt import validate_storyboard_panel_receipt
from validate_visual_review_receipt import validate_visual_review_receipt
from write_panel_source_receipt import derive_panel_source_receipt
from write_panel_repair_work_order import build_panel_repair_work_order
from write_provider_media_publication_work_order import build_provider_media_publication_work_order
from write_dream_packet_work_order import build_dream_packet_work_order
from write_one_scene_kling_review_packet import install_one_scene_kling_review_packet
from write_story_contract_work_order import build_story_contract_work_order
from write_storyboard_panel_work_order import build_storyboard_panel_work_order


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _iteration_summary(
    loop_status: dict[str, Any],
    iteration: int,
    repair_action: dict[str, Any] | None = None,
) -> dict[str, Any]:
    active_loop = loop_status.get("active_loop")
    validation = loop_status.get("validation") if isinstance(loop_status.get("validation"), dict) else {}
    first_blocker = validation.get("first_blocker") if isinstance(validation, dict) else None
    summary = {
        "iteration": iteration,
        "status": loop_status.get("status"),
        "active_loop": active_loop,
        "first_blocker": first_blocker,
        "phase_count": len(validation.get("phases", [])) if isinstance(validation.get("phases"), list) else 0,
        "stop_condition": loop_status.get("stop_condition"),
    }
    if repair_action is not None:
        summary["repair_action"] = repair_action
    return summary


def _phase_path(loop_status: dict[str, Any], phase: str) -> Path | None:
    validation = loop_status.get("validation")
    phases = validation.get("phases") if isinstance(validation, dict) else None
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    if not isinstance(phases, list) or not isinstance(run_root_value, str):
        return None
    run_root = Path(run_root_value)
    for item in phases:
        if not isinstance(item, dict) or item.get("phase") != phase:
            continue
        path_value = item.get("path")
        if not isinstance(path_value, str) or not path_value or "|" in path_value or "*" in path_value:
            return None
        path = Path(path_value)
        return path if path.is_absolute() else run_root / path
    return None


def _local_staging_output_path(work_order_path: Path) -> Path:
    if work_order_path.name.endswith("_publication_request.json"):
        return work_order_path.with_name(work_order_path.name.replace("_publication_request.json", "_local_staging_receipt.json"))
    return work_order_path.with_name("provider_media_local_staging_receipt.json")


def _repair_provider_media_local_staging(
    *,
    loop_status: dict[str, Any],
    repo_root: Path,
    generated_at: str | None,
) -> dict[str, Any]:
    work_order_path = _phase_path(loop_status, "provider_media_publication_work_order")
    if work_order_path is None:
        return {
            "status": "BLOCKED",
            "phase": "provider_media_local_staging",
            "reason": "missing_publication_work_order_path",
            "external_action_required": False,
        }

    output_path = _local_staging_output_path(work_order_path)
    try:
        receipt = stage_provider_media_local_asset(
            work_order_path=work_order_path,
            repo_root=repo_root,
            created_at=generated_at,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "phase": "provider_media_local_staging",
            "reason": str(exc),
            "work_order": str(work_order_path),
            "external_action_required": False,
        }

    return {
        "status": "WROTE_PROVIDER_MEDIA_LOCAL_STAGING_RECEIPT",
        "phase": "provider_media_local_staging",
        "work_order": str(work_order_path),
        "output": str(output_path),
        "staged_asset_path": receipt.get("staged_asset_path"),
        "staged_sha256": receipt.get("staged_sha256"),
        "does_not_authorize": receipt.get("does_not_authorize"),
        "external_action_required": False,
    }


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _repair_one_scene_kling_review_packet(
    *,
    loop_status: dict[str, Any],
    generated_at: str | None,
) -> dict[str, Any]:
    validation = loop_status.get("validation")
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    active_loop = loop_status.get("active_loop")
    phase = active_loop.get("phase") if isinstance(active_loop, dict) else "kling_scene_packet"
    panel_source_path = _phase_path(loop_status, "panel_source_receipt")
    panel_repair_gate_path = _phase_path(loop_status, "panel_repair_gate")
    if not isinstance(run_root_value, str):
        return {
            "status": "BLOCKED",
            "phase": phase,
            "reason": "missing_run_root",
            "external_action_required": False,
        }
    if panel_source_path is None:
        return {
            "status": "BLOCKED",
            "phase": phase,
            "reason": "missing_panel_source_receipt_path",
            "external_action_required": False,
        }
    if panel_repair_gate_path is None:
        return {
            "status": "BLOCKED",
            "phase": phase,
            "reason": "missing_panel_repair_gate_path",
            "external_action_required": False,
        }

    try:
        install_result = install_one_scene_kling_review_packet(
            run_root=Path(run_root_value),
            panel_source_receipt=panel_source_path,
            panel_repair_gate_receipt=panel_repair_gate_path,
            created_at=generated_at,
        )
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "phase": phase,
            "reason": str(exc),
            "panel_source_receipt": str(panel_source_path),
            "panel_repair_gate_receipt": str(panel_repair_gate_path),
            "external_action_required": False,
        }

    return {
        "status": "INSTALLED_ONE_SCENE_KLING_REVIEW_PACKET",
        "phase": phase,
        "outputs": install_result.get("outputs"),
        "panel_source_receipt": str(panel_source_path),
        "panel_repair_gate_receipt": str(panel_repair_gate_path),
        "external_action_required": False,
        "live": install_result.get("live"),
        "mocked": install_result.get("mocked"),
        "unverified": install_result.get("unverified"),
    }


def _repair_provider_media_publication_work_order(
    *,
    loop_status: dict[str, Any],
    generated_at: str | None,
) -> dict[str, Any]:
    validation = loop_status.get("validation")
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    if not isinstance(run_root_value, str):
        return {
            "status": "BLOCKED",
            "phase": "provider_media_publication_work_order",
            "reason": "missing_run_root",
            "external_action_required": False,
        }
    run_root = Path(run_root_value)
    panel_repair_gate_path = _phase_path(loop_status, "panel_repair_gate")
    provider_media_probe_path = _phase_path(loop_status, "provider_media_public_probe")
    if panel_repair_gate_path is None:
        return {
            "status": "BLOCKED",
            "phase": "provider_media_publication_work_order",
            "reason": "missing_panel_repair_gate_path",
            "external_action_required": False,
        }
    if provider_media_probe_path is None:
        return {
            "status": "BLOCKED",
            "phase": "provider_media_publication_work_order",
            "reason": "missing_provider_media_probe_path",
            "external_action_required": False,
        }

    try:
        repair_receipt = _read_json(panel_repair_gate_path)
        panel_id = repair_receipt.get("panel_id") if isinstance(repair_receipt, dict) else None
        if not isinstance(panel_id, str) or not panel_id:
            panel_id = "panel_01"
        work_order = build_provider_media_publication_work_order(
            run_root=run_root,
            panel_id=panel_id,
            panel_repair_gate_receipt=panel_repair_gate_path,
            provider_media_probe_receipt=provider_media_probe_path,
            created_at=generated_at,
        )
        output_path = (
            run_root
            / "storyboard/panel_repair_gate/provider_media_publication_work_orders"
            / f"{panel_id}_publication_request.json"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "phase": "provider_media_publication_work_order",
            "reason": str(exc),
            "panel_repair_gate_receipt": str(panel_repair_gate_path),
            "provider_media_probe_receipt": str(provider_media_probe_path),
            "external_action_required": False,
        }

    return {
        "status": "WROTE_PROVIDER_MEDIA_PUBLICATION_WORK_ORDER",
        "phase": "provider_media_publication_work_order",
        "output": str(output_path),
        "panel_id": panel_id,
        "proposed_url": work_order.get("proposed_publication", {}).get("proposed_url")
        if isinstance(work_order.get("proposed_publication"), dict)
        else None,
        "authorization_required": work_order.get("authorization_required"),
        "external_action_required": False,
    }


def _panel_source_output_path(loop_status: dict[str, Any]) -> Path | None:
    validation = loop_status.get("validation")
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    if not isinstance(run_root_value, str):
        return None
    existing = _phase_path(loop_status, "panel_source_receipt")
    if existing is not None:
        return existing
    return Path(run_root_value) / "receipts/panel_source_receipt.json"


def _repair_panel_source_receipt(loop_status: dict[str, Any]) -> dict[str, Any]:
    panel_repair_gate_path = _phase_path(loop_status, "panel_repair_gate")
    provider_media_probe_path = _phase_path(loop_status, "provider_media_public_probe")
    output_path = _panel_source_output_path(loop_status)
    if panel_repair_gate_path is None:
        return {
            "status": "BLOCKED",
            "phase": "panel_source_receipt",
            "reason": "missing_panel_repair_gate_path",
            "external_action_required": False,
        }
    if output_path is None:
        return {
            "status": "BLOCKED",
            "phase": "panel_source_receipt",
            "reason": "missing_panel_source_output_path",
            "external_action_required": False,
        }

    probe_application: dict[str, Any] | None = None
    try:
        receipt = derive_panel_source_receipt(panel_repair_gate_path, output=output_path)
        if receipt.get("status") != "PASS_PANEL_SOURCE" and provider_media_probe_path is not None:
            probe_application = apply_provider_media_public_probe(
                panel_repair_gate_receipt=panel_repair_gate_path,
                provider_media_probe_receipt=provider_media_probe_path,
                output=panel_repair_gate_path,
            )
            if probe_application.get("status") == "APPLIED_PROVIDER_MEDIA_PUBLIC_PROBE":
                receipt = derive_panel_source_receipt(panel_repair_gate_path, output=output_path)
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "phase": "panel_source_receipt",
            "reason": str(exc),
            "panel_repair_gate_receipt": str(panel_repair_gate_path),
            "external_action_required": False,
        }

    if receipt.get("status") != "PASS_PANEL_SOURCE":
        blockers = receipt.get("blockers") if isinstance(receipt.get("blockers"), list) else []
        return {
            "status": "BLOCKED",
            "phase": "panel_source_receipt",
            "reason": "panel_source_not_pass:" + ",".join(str(blocker) for blocker in blockers),
            "output": str(output_path),
            "panel_repair_gate_receipt": str(panel_repair_gate_path),
            "provider_media_probe_application": probe_application,
            "external_action_required": False,
        }

    status = "WROTE_PANEL_SOURCE_RECEIPT"
    if probe_application and probe_application.get("status") == "APPLIED_PROVIDER_MEDIA_PUBLIC_PROBE":
        status = "APPLIED_PROVIDER_MEDIA_PUBLIC_PROBE_AND_WROTE_PANEL_SOURCE_RECEIPT"
    return {
        "status": status,
        "phase": "panel_source_receipt",
        "output": str(output_path),
        "panel_source_status": receipt.get("status"),
        "final_panel_eligible": receipt.get("final_panel_eligible"),
        "photoreal_status": receipt.get("photoreal_status"),
        "nano_banana_fallback_used": receipt.get("nano_banana_fallback_used"),
        "blockers": receipt.get("blockers"),
        "provider_media_probe_application": probe_application,
        "external_action_required": False,
    }


def _panel_repair_work_order_output_path(panel_repair_gate_path: Path, *, panel_id: str) -> Path:
    if "panel_repair_gate" in panel_repair_gate_path.parts:
        return panel_repair_gate_path.with_name(f"{panel_id}_request.json")
    return panel_repair_gate_path.parent / "panel_repair_work_order.json"


def _panel_repair_gate_work_order_output_path(loop_status: dict[str, Any]) -> Path | None:
    return _work_order_output_path(loop_status, "panel_repair_work_order.json")


def _repair_panel_repair_gate_work_order(
    *,
    loop_status: dict[str, Any],
    generated_at: str | None,
) -> dict[str, Any]:
    validation = loop_status.get("validation")
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    panel_repair_gate_path = _phase_path(loop_status, "panel_repair_gate")
    if not isinstance(run_root_value, str):
        return {
            "status": "BLOCKED",
            "phase": "panel_repair_gate",
            "reason": "missing_run_root",
            "external_action_required": False,
        }
    if panel_repair_gate_path is None:
        storyboard_panel_path = _phase_path(loop_status, "storyboard_panel")
        output_path = _panel_repair_gate_work_order_output_path(loop_status)
        if storyboard_panel_path is None:
            return {
                "status": "BLOCKED",
                "phase": "panel_repair_gate",
                "reason": "missing_storyboard_panel_path",
                "external_action_required": False,
            }
        if output_path is None:
            return {
                "status": "BLOCKED",
                "phase": "panel_repair_gate",
                "reason": "missing_panel_repair_work_order_output_path",
                "external_action_required": False,
            }
        try:
            work_order = build_panel_repair_work_order(
                run_root=Path(run_root_value),
                panel_id="panel_01",
                storyboard_panel_receipt=storyboard_panel_path,
                created_at=generated_at,
            )
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except Exception as exc:
            return {
                "status": "BLOCKED",
                "phase": "panel_repair_gate",
                "reason": str(exc),
                "storyboard_panel_receipt": str(storyboard_panel_path),
                "external_action_required": False,
            }
        return {
            "status": "WROTE_PANEL_REPAIR_WORK_ORDER",
            "phase": "panel_repair_gate",
            "output": str(output_path),
            "panel_id": work_order.get("panel_id"),
            "owner_subagent": work_order.get("owner_subagent"),
            "delegated_subagents": work_order.get("delegated_subagents"),
            "final_gate_status": work_order.get("final_gate_validation", {}).get("status")
            if isinstance(work_order.get("final_gate_validation"), dict)
            else None,
            "final_gate_errors": work_order.get("final_gate_validation", {}).get("errors")
            if isinstance(work_order.get("final_gate_validation"), dict)
            else None,
            "external_action_required": False,
            "stop_after_action": True,
            "unverified": "panel subagent execution, live image generation, independent visual review, provider media hosting, Kling submission",
        }

    try:
        repair_receipt = _read_json(panel_repair_gate_path)
        panel_id = repair_receipt.get("panel_id") if isinstance(repair_receipt, dict) else None
        if not isinstance(panel_id, str) or not panel_id.strip():
            panel_id = "panel_01"
        output_path = _panel_repair_work_order_output_path(panel_repair_gate_path, panel_id=panel_id)
        work_order = build_panel_repair_work_order(
            run_root=Path(run_root_value),
            panel_id=panel_id,
            panel_repair_gate_receipt=panel_repair_gate_path,
            created_at=generated_at,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "phase": "panel_repair_gate",
            "reason": str(exc),
            "panel_repair_gate_receipt": str(panel_repair_gate_path),
            "external_action_required": False,
        }

    return {
        "status": "WROTE_PANEL_REPAIR_WORK_ORDER",
        "phase": "panel_repair_gate",
        "output": str(output_path),
        "panel_id": panel_id,
        "owner_subagent": work_order.get("owner_subagent"),
        "delegated_subagents": work_order.get("delegated_subagents"),
        "final_gate_status": work_order.get("final_gate_validation", {}).get("status")
        if isinstance(work_order.get("final_gate_validation"), dict)
        else None,
        "final_gate_errors": work_order.get("final_gate_validation", {}).get("errors")
        if isinstance(work_order.get("final_gate_validation"), dict)
        else None,
        "external_action_required": False,
        "stop_after_action": True,
        "unverified": "panel repair subagent execution, image generation, visual rereview, provider media hosting, Kling execution",
    }


def _resolve_artifact(value: str, *, base_dir: Path, run_root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    candidate = base_dir / path
    if candidate.exists():
        return candidate
    return run_root / path


def _visual_review_output_path(loop_status: dict[str, Any]) -> Path | None:
    validation = loop_status.get("validation")
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    if not isinstance(run_root_value, str):
        return None
    existing = _phase_path(loop_status, "visual_review_receipt")
    if existing is not None:
        return existing
    return Path(run_root_value) / "receipts/visual_review_receipt.json"


def _storyboard_panel_output_path(loop_status: dict[str, Any]) -> Path | None:
    validation = loop_status.get("validation")
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    if not isinstance(run_root_value, str):
        return None
    existing = _phase_path(loop_status, "storyboard_panel")
    if existing is not None:
        return existing
    return Path(run_root_value) / "receipts/storyboard_panel_receipt.json"


def _story_contract_work_order_output_path(loop_status: dict[str, Any]) -> Path | None:
    validation = loop_status.get("validation")
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    if not isinstance(run_root_value, str):
        return None
    return Path(run_root_value) / "receipts/story_contract_work_order.json"


def _work_order_output_path(loop_status: dict[str, Any], filename: str) -> Path | None:
    validation = loop_status.get("validation")
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    if not isinstance(run_root_value, str):
        return None
    return Path(run_root_value) / "receipts" / filename


def _repair_dream_packet_work_order(
    *,
    loop_status: dict[str, Any],
    generated_at: str | None,
) -> dict[str, Any]:
    validation = loop_status.get("validation")
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    first_blocker = validation.get("first_blocker") if isinstance(validation, dict) else None
    output_path = _work_order_output_path(loop_status, "dream_packet_work_order.json")
    if not isinstance(run_root_value, str):
        return {
            "status": "BLOCKED",
            "phase": "dream_packet",
            "reason": "missing_run_root",
            "external_action_required": False,
        }
    if output_path is None:
        return {
            "status": "BLOCKED",
            "phase": "dream_packet",
            "reason": "missing_dream_packet_work_order_output_path",
            "external_action_required": False,
        }

    dream_packet_path = _phase_path(loop_status, "dream_packet")
    try:
        work_order = build_dream_packet_work_order(
            run_root=Path(run_root_value),
            dream_packet=dream_packet_path,
            blocker=first_blocker if isinstance(first_blocker, dict) else None,
            created_at=generated_at,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "phase": "dream_packet",
            "reason": str(exc),
            "external_action_required": False,
        }

    return {
        "status": "WROTE_DREAM_PACKET_WORK_ORDER",
        "phase": "dream_packet",
        "output": str(output_path),
        "owner_subagent": work_order.get("owner_subagent"),
        "packet_exists": work_order.get("current_packet", {}).get("exists")
        if isinstance(work_order.get("current_packet"), dict)
        else None,
        "blocker": work_order.get("blocking_validation", {}).get("first_blocker")
        if isinstance(work_order.get("blocking_validation"), dict)
        else None,
        "external_action_required": False,
        "stop_after_action": True,
        "unverified": "live memory recall, residue grounding, dreamer subagent execution, contact sheet generation, story/panel/provider/Kling readiness",
    }


def _repair_story_contract_work_order(
    *,
    loop_status: dict[str, Any],
    generated_at: str | None,
) -> dict[str, Any]:
    validation = loop_status.get("validation")
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    first_blocker = validation.get("first_blocker") if isinstance(validation, dict) else None
    story_contract_path = _phase_path(loop_status, "story_contract")
    output_path = _story_contract_work_order_output_path(loop_status)
    if not isinstance(run_root_value, str):
        return {
            "status": "BLOCKED",
            "phase": "story_contract",
            "reason": "missing_run_root",
            "external_action_required": False,
        }
    if output_path is None:
        return {
            "status": "BLOCKED",
            "phase": "story_contract",
            "reason": "missing_story_contract_work_order_output_path",
            "external_action_required": False,
        }

    try:
        work_order = build_story_contract_work_order(
            run_root=Path(run_root_value),
            story_contract=story_contract_path,
            blocker=first_blocker if isinstance(first_blocker, dict) else None,
            created_at=generated_at,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "phase": "story_contract",
            "reason": str(exc),
            "story_contract": str(story_contract_path),
            "external_action_required": False,
        }

    return {
        "status": "WROTE_STORY_CONTRACT_WORK_ORDER",
        "phase": "story_contract",
        "output": str(output_path),
        "story_contract": str(story_contract_path),
        "owner_subagent": work_order.get("owner_subagent"),
        "current_status": work_order.get("current_contract", {}).get("status")
        if isinstance(work_order.get("current_contract"), dict)
        else None,
        "blocker": work_order.get("blocking_validation", {}).get("first_blocker")
        if isinstance(work_order.get("blocking_validation"), dict)
        else None,
        "external_action_required": False,
        "stop_after_action": True,
        "unverified": "semantic story acceptance, dreamer subagent execution, downstream regeneration, panel/provider/Kling readiness",
    }


def _repair_storyboard_panel(loop_status: dict[str, Any]) -> dict[str, Any]:
    validation = loop_status.get("validation")
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    first_blocker = validation.get("first_blocker") if isinstance(validation, dict) else None
    panel_repair_gate_path = _phase_path(loop_status, "panel_repair_gate")
    output_path = _storyboard_panel_output_path(loop_status)
    if not isinstance(run_root_value, str):
        return {
            "status": "BLOCKED",
            "phase": "storyboard_panel",
            "reason": "missing_run_root",
            "external_action_required": False,
        }
    if panel_repair_gate_path is None:
        work_order_output = _work_order_output_path(loop_status, "storyboard_panel_work_order.json")
        if work_order_output is None:
            return {
                "status": "BLOCKED",
                "phase": "storyboard_panel",
                "reason": "missing_storyboard_panel_work_order_output_path",
                "external_action_required": False,
            }
        try:
            work_order = build_storyboard_panel_work_order(
                run_root=Path(run_root_value),
                story_contract=_phase_path(loop_status, "story_contract"),
                blocker=first_blocker if isinstance(first_blocker, dict) else None,
            )
            work_order_output.parent.mkdir(parents=True, exist_ok=True)
            work_order_output.write_text(json.dumps(work_order, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except Exception as exc:
            return {
                "status": "BLOCKED",
                "phase": "storyboard_panel",
                "reason": str(exc),
                "external_action_required": False,
            }
        return {
            "status": "WROTE_STORYBOARD_PANEL_WORK_ORDER",
            "phase": "storyboard_panel",
            "output": str(work_order_output),
            "owner_subagent": work_order.get("owner_subagent"),
            "blocker": work_order.get("blocking_validation", {}).get("first_blocker")
            if isinstance(work_order.get("blocking_validation"), dict)
            else None,
            "external_action_required": False,
            "stop_after_action": True,
            "unverified": "storyboard subagent execution, live panel generation, visual review, provider/Kling execution",
        }
    if output_path is None:
        return {
            "status": "BLOCKED",
            "phase": "storyboard_panel",
            "reason": "missing_storyboard_panel_output_path",
            "external_action_required": False,
        }

    run_root = Path(run_root_value)
    try:
        repair_receipt = _read_json(panel_repair_gate_path)
        storyboard_value = repair_receipt.get("storyboard_panel_receipt") if isinstance(repair_receipt, dict) else None
        if not isinstance(storyboard_value, str) or not storyboard_value.strip():
            raise ValueError("panel repair gate missing storyboard_panel_receipt")
        source_path = _resolve_artifact(
            storyboard_value,
            base_dir=panel_repair_gate_path.parent,
            run_root=run_root,
        )
        validation_result = validate_storyboard_panel_receipt(source_path, run_root=run_root)
        blocker = validation_result.get("first_blocker")
        if blocker:
            raise ValueError(f"storyboard_panel_receipt_not_pass:{blocker.get('reason')}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.resolve() != output_path.resolve():
            shutil.copyfile(source_path, output_path)
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "phase": "storyboard_panel",
            "reason": str(exc),
            "panel_repair_gate_receipt": str(panel_repair_gate_path),
            "external_action_required": False,
        }

    return {
        "status": "INSTALLED_STORYBOARD_PANEL_RECEIPT",
        "phase": "storyboard_panel",
        "source": str(source_path),
        "output": str(output_path),
        "validation_status": "PASS_STORYBOARD_PANEL",
        "external_action_required": False,
        "unverified": "new panel subagent generation, live visual semantics, provider/Kling execution",
    }


def _repair_visual_review_receipt(loop_status: dict[str, Any]) -> dict[str, Any]:
    validation = loop_status.get("validation")
    run_root_value = validation.get("run_root") if isinstance(validation, dict) else None
    panel_repair_gate_path = _phase_path(loop_status, "panel_repair_gate")
    output_path = _visual_review_output_path(loop_status)
    if not isinstance(run_root_value, str):
        return {
            "status": "BLOCKED",
            "phase": "visual_review_receipt",
            "reason": "missing_run_root",
            "external_action_required": False,
        }
    if panel_repair_gate_path is None:
        return {
            "status": "BLOCKED",
            "phase": "visual_review_receipt",
            "reason": "missing_panel_repair_gate_path",
            "external_action_required": False,
        }
    if output_path is None:
        return {
            "status": "BLOCKED",
            "phase": "visual_review_receipt",
            "reason": "missing_visual_review_output_path",
            "external_action_required": False,
        }

    run_root = Path(run_root_value)
    try:
        repair_receipt = _read_json(panel_repair_gate_path)
        visual_value = repair_receipt.get("visual_review_receipt") if isinstance(repair_receipt, dict) else None
        if not isinstance(visual_value, str) or not visual_value.strip():
            raise ValueError("panel repair gate missing visual_review_receipt")
        source_path = _resolve_artifact(
            visual_value,
            base_dir=panel_repair_gate_path.parent,
            run_root=run_root,
        )
        validation_result = validate_visual_review_receipt(source_path, run_root=run_root)
        blocker = validation_result.get("first_blocker")
        if blocker:
            raise ValueError(f"visual_review_receipt_not_pass:{blocker.get('reason')}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.resolve() != output_path.resolve():
            shutil.copyfile(source_path, output_path)
    except Exception as exc:
        return {
            "status": "BLOCKED",
            "phase": "visual_review_receipt",
            "reason": str(exc),
            "panel_repair_gate_receipt": str(panel_repair_gate_path),
            "external_action_required": False,
        }

    return {
        "status": "INSTALLED_VISUAL_REVIEW_RECEIPT",
        "phase": "visual_review_receipt",
        "source": str(source_path),
        "output": str(output_path),
        "validation_status": "PASS_VISUAL_REVIEW",
        "external_action_required": False,
        "unverified": "new live VLM/WebGPT review, actual image semantics beyond the supplied receipt",
    }


def _run_local_repair_handler(
    *,
    loop_status: dict[str, Any],
    repo_root: Path,
    generated_at: str | None,
) -> dict[str, Any]:
    active_loop = loop_status.get("active_loop")
    phase = active_loop.get("phase") if isinstance(active_loop, dict) else None
    if phase in {"kling_scene_packet", "local_provider_media_lock"}:
        return _repair_one_scene_kling_review_packet(
            loop_status=loop_status,
            generated_at=generated_at,
        )
    if phase == "storyboard_panel":
        return _repair_storyboard_panel(loop_status)
    if phase == "story_contract":
        return _repair_story_contract_work_order(
            loop_status=loop_status,
            generated_at=generated_at,
        )
    if phase == "dream_packet":
        return _repair_dream_packet_work_order(
            loop_status=loop_status,
            generated_at=generated_at,
        )
    if phase == "visual_review_receipt":
        return _repair_visual_review_receipt(loop_status)
    if phase == "panel_source_receipt":
        return _repair_panel_source_receipt(loop_status)
    if phase == "panel_repair_gate":
        return _repair_panel_repair_gate_work_order(
            loop_status=loop_status,
            generated_at=generated_at,
        )
    if phase == "provider_media_publication_work_order":
        return _repair_provider_media_publication_work_order(
            loop_status=loop_status,
            generated_at=generated_at,
        )
    if phase == "provider_media_local_staging":
        return _repair_provider_media_local_staging(
            loop_status=loop_status,
            repo_root=repo_root,
            generated_at=generated_at,
        )
    return {
        "status": "BLOCKED",
        "phase": phase,
        "reason": "local_repair_handler_not_implemented",
        "external_action_required": False,
    }


def build_pipeline_loop_run(
    *,
    run_root: Path,
    direction: str = "backward",
    max_iterations: int = 1,
    repo_root: Path | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    if max_iterations < 1:
        raise ValueError("max_iterations must be >= 1")

    iterations: list[dict[str, Any]] = []
    final_status: dict[str, Any] | None = None
    stop_reason = "max_iterations_reached"
    repo_root = (repo_root or Path(__file__).resolve().parents[3]).resolve()

    for index in range(1, max_iterations + 1):
        loop_status = build_pipeline_loop_status(run_root=run_root, direction=direction)
        final_status = loop_status

        active_loop = loop_status.get("active_loop")
        if loop_status.get("status") == "ALL_SERIAL_LOOPS_ACCEPTED":
            iterations.append(_iteration_summary(loop_status, index))
            stop_reason = "all_serial_loops_accepted"
            break
        if not isinstance(active_loop, dict):
            iterations.append(_iteration_summary(loop_status, index))
            stop_reason = "missing_active_loop"
            break
        if active_loop.get("external_action_required") is True:
            iterations.append(_iteration_summary(loop_status, index))
            stop_reason = "external_action_required"
            break

        repair_action = _run_local_repair_handler(
            loop_status=loop_status,
            repo_root=repo_root,
            generated_at=generated_at,
        )
        iterations.append(_iteration_summary(loop_status, index, repair_action))
        if repair_action.get("status") == "BLOCKED":
            if repair_action.get("reason") == "local_repair_handler_not_implemented":
                stop_reason = "local_repair_handler_not_implemented"
            else:
                stop_reason = "local_repair_blocked"
            break
        if repair_action.get("stop_after_action") is True:
            stop_reason = "work_order_written"
            break

    active_loop = final_status.get("active_loop") if isinstance(final_status, dict) else None
    result_status = "ACCEPTED" if stop_reason == "all_serial_loops_accepted" else "BLOCKED"
    return {
        "schema": "persona_dream.pipeline_loop_run.v1",
        "generated_at": generated_at or _now_iso(),
        "run_root": str(run_root),
        "direction": direction,
        "status": result_status,
        "stop_reason": stop_reason,
        "active_loop": active_loop,
        "iterations": iterations,
        "policy": {
            "kling_call_allowed": False,
            "public_upload_allowed_without_explicit_authorization": False,
            "nano_banana_final_panel_allowed": False,
            "implicit_local_repair_allowed": False,
        },
        "next_action": (active_loop or {}).get("default_repair") if isinstance(active_loop, dict) else None,
        "mocked": final_status.get("mocked") if isinstance(final_status, dict) else "unknown",
        "live": "no",
        "exercised": "serial while-loop controller pass, run-root validation, first-blocker loop mapping, fail-closed stop selection, local receipt installation handlers when applicable",
        "unverified": "external publication, live panel subagent generation/review, paid Kling submission",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("--direction", choices=["forward", "backward"], default="backward")
    parser.add_argument("--max-iterations", type=int, default=1)
    parser.add_argument("--repo-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--generated-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        result = build_pipeline_loop_run(
            run_root=args.run_root,
            direction=args.direction,
            max_iterations=args.max_iterations,
            repo_root=args.repo_root,
            generated_at=args.generated_at,
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except Exception as exc:
        result = {
            "schema": "persona_dream.pipeline_loop_run.v1",
            "status": "BLOCKED",
            "stop_reason": "schema_or_parse",
            "active_loop": {
                "loop": "pipeline_loop_run",
                "phase": "schema_or_parse",
                "blocker": str(exc),
            },
            "live": "no",
        }

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        loop = result.get("active_loop") or {}
        print(f"{result['status']} {result.get('stop_reason')} {loop.get('loop', '')}".strip())
    return 0 if result["status"] != "BLOCKED" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
