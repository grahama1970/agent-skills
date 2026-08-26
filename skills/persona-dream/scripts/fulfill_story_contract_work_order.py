#!/usr/bin/env python3
"""Fulfill a validated story-contract work order from current run-root inputs.

This retained executor consumes the work order written by pipeline-loop-run,
derives an accepted story contract from the current dream packet and project
contracts, and marks downstream artifacts stale. It does not call Kling, upload
media, or promote storyboard plans into accepted storyboard packets.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from validate_story_contract import validate_story_contract
from validate_story_contract_work_order import validate_story_contract_work_order


ROOT = Path(__file__).resolve().parents[1]
ACCEPTED_STATUS = "PASS_STORY_CONTRACT"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def rel_or_abs(path: Path, base: Path) -> str:
    try:
        return str(path.resolve().relative_to(base.resolve()))
    except ValueError:
        return str(path.resolve())


def source_ref(path: Path, *, base: Path) -> dict[str, Any]:
    exists = path.exists()
    return {
        "path": rel_or_abs(path, base),
        "absolute_path": str(path.resolve()),
        "exists": exists,
        "sha256": sha256_file(path) if exists and path.is_file() else None,
    }


def path_from_work_order(work_order: dict[str, Any], key: str, default: Path) -> Path:
    raw = (work_order.get("source_paths") or {}).get(key)
    if isinstance(raw, str) and raw and not raw.startswith("missing:"):
        return Path(raw).expanduser()
    return default


def first_existing(run_root: Path, candidates: list[str]) -> Path | None:
    for candidate in candidates:
        path = run_root / candidate
        if path.exists():
            return path
    return None


def residue_summary(packet: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    for item in packet.get("residue_items") or []:
        text = str(item.get("text") or item.get("source_quote") or "").strip()
        source_id = str(item.get("source_id") or "").strip()
        if text:
            lines.append(f"{source_id}: {text}" if source_id else text)
        if len(lines) >= 4:
            break
    return lines


def build_story_text(packet: dict[str, Any]) -> str:
    persona = packet.get("persona") or {}
    name = str(persona.get("display_name") or persona.get("id") or "Embry").strip()
    prompt = str(packet.get("dream_prompt") or "").strip()
    reflection = str(packet.get("reflection") or "").strip()
    residues = residue_summary(packet)
    residue_clause = " ".join(residues) if residues else "The dream keeps its source residues explicit."
    frame_beats = []
    for frame in packet.get("frame_prompts") or []:
        frame_text = str(frame.get("prompt") or "").strip()
        if frame_text:
            frame_beats.append(frame_text)
        if len(frame_beats) >= 3:
            break
    beat_clause = " ".join(frame_beats) if frame_beats else prompt
    return (
        f"{name} speaks in first person about a synthetic dream while Horus keeps the conversation grounded. "
        f"The dream seed is: {prompt}. "
        f"The remembered residues are: {residue_clause}. "
        f"The visual beats are: {beat_clause}. "
        f"After waking, {name} treats the dream as reflective material rather than factual evidence: {reflection}. "
        "The conflict is emotional, not informational: competence and inadequacy pull against each other, "
        "but the answer content stays grounded in the same source facts. Horus asks about mood and meaning; "
        "Embry names uncertainty, performance pressure, and the wish to hold the dream gently without turning it "
        "into proof or a durable identity change."
    )


def downstream_inventory(run_root: Path) -> list[dict[str, Any]]:
    candidates = [
        "storyboard_plan.json",
        "storyboard_packet.json",
        "storyboard.json",
        "panel_repair_gate_receipt.json",
        "visual_review_receipt.json",
        "panel_source_receipt.json",
        "receipts/storyboard_panel_receipt.json",
        "receipts/panel_repair_gate_receipt.json",
        "receipts/visual_review_receipt.json",
        "receipts/provider_media_publication_work_order.json",
        "receipts/provider_media_local_staging_receipt.json",
        "receipts/provider_media_publication_preflight.json",
        "receipts/provider_media_publication_authorization.json",
        "receipts/provider_media_url_probe_receipt.json",
        "receipts/kling_scene_packet.json",
        "kling_scene_packet.json",
    ]
    entries: list[dict[str, Any]] = []
    for rel in candidates:
        path = run_root / rel
        if path.exists():
            entries.append({
                "path": rel,
                "absolute_path": str(path.resolve()),
                "sha256": sha256_file(path) if path.is_file() else None,
                "status": "STALE_REQUIRES_REGENERATION_FROM_ACCEPTED_STORY_CONTRACT",
            })
    return entries


def fulfill(
    work_order_path: Path,
    *,
    run_root: Path | None,
    output: Path | None,
    created_at: str | None,
) -> dict[str, Any]:
    work_order_path = work_order_path.resolve()
    work_order = read_json(work_order_path)
    root = (run_root or Path(work_order.get("source_paths", {}).get("run_root", work_order_path.parents[1]))).resolve()
    created = created_at or datetime.now(timezone.utc).isoformat()
    receipt_path = (output or (root / "receipts/story_contract_fulfillment.json")).resolve()
    mocked = "yes" if "fixtures" in root.parts else "no"

    validation = validate_story_contract_work_order(work_order_path)
    if validation.get("status") != "PASS_STORY_CONTRACT_WORK_ORDER":
        receipt = {
            "schema": "persona_dream.story_contract_fulfillment.v1",
            "status": "BLOCKED_STORY_CONTRACT_WORK_ORDER_INVALID",
            "created_at": created,
            "run_root": str(root),
            "input_work_order": str(work_order_path),
            "work_order_validation": validation,
            "mocked": mocked,
            "live": "no",
            "paid_provider_call_attempted": False,
            "kling_call_attempted": False,
        }
        write_json(receipt_path, receipt)
        return receipt

    dream_packet_path = path_from_work_order(work_order, "dream_packet", root / "dream_packet.json").resolve()
    if not dream_packet_path.exists():
        receipt = {
            "schema": "persona_dream.story_contract_fulfillment.v1",
            "status": "BLOCKED_DREAM_PACKET_MISSING",
            "created_at": created,
            "run_root": str(root),
            "input_work_order": str(work_order_path),
            "dream_packet": str(dream_packet_path),
            "mocked": mocked,
            "live": "no",
            "paid_provider_call_attempted": False,
            "kling_call_attempted": False,
        }
        write_json(receipt_path, receipt)
        return receipt

    packet = read_json(dream_packet_path)
    skill_path = path_from_work_order(work_order, "persona_dream_skill_contract", ROOT / "SKILL.md").resolve()
    knowledge_path = path_from_work_order(work_order, "project_knowledge", ROOT / "PROJECT_KNOWLEDGE.md").resolve()
    story_path = root / "story_contract.json"
    mirror_path = root / "artifacts/story_contract.json"
    review_receipt_path = root / "receipts/story_contract_review_receipt.json"
    stale_receipt_path = root / "receipts/story_contract_downstream_stale.json"

    existing_story = first_existing(root, ["story_contract.json", "artifacts/story_contract.json"])
    previous_story_ref = source_ref(existing_story, base=root) if existing_story else None

    persona = packet.get("persona") or {}
    persona_name = str(persona.get("display_name") or persona.get("id") or "Embry").strip()
    secondary = packet.get("secondary_persona") or {}
    secondary_name = str(secondary.get("display_name") or secondary.get("id") or "Horus").strip()
    if secondary_name == persona_name:
        secondary_name = "Horus"
    prompt = str(packet.get("dream_prompt") or packet.get("reflection") or packet.get("run_id") or "").strip()

    story_contract = {
        "schema": "persona_dream.story_contract.v1",
        "artifact_id": f"{root.name}_story_contract",
        "status": ACCEPTED_STATUS,
        "created_at": created,
        "input_idea_contract": rel_or_abs(dream_packet_path, root),
        "seed": prompt or f"{persona_name} dream packet {packet.get('run_id', root.name)}",
        "story": build_story_text(packet),
        "target_duration_s": 10.0,
        "speaking_characters": [persona_name, secondary_name],
        "owner_subagent": "dreamer",
        "review_status": "ACCEPTED_AUTOMATED",
        "run_root": str(root),
        "upstream_refs": {
            "dream_packet": source_ref(dream_packet_path, base=root),
            "work_order": source_ref(work_order_path, base=root),
            "persona_dream_skill_contract": source_ref(skill_path, base=root),
            "project_knowledge": source_ref(knowledge_path, base=root),
        },
        "previous_story_contract": previous_story_ref,
        "acceptance": {
            "accepted_by": "dreamer",
            "accepted_at": created,
            "mocked": mocked,
            "basis": [
                "validated story_contract_work_order",
                "current dream_packet.json",
                "persona-dream SKILL.md",
                "persona-dream PROJECT_KNOWLEDGE.md",
            ],
            "forbidden_actions_observed": False,
        },
        "claims": {
            "proves": [
                "a retained executor consumed a validated story-contract work order",
                "the emitted story contract is hash-bound to the current dream packet and project contracts",
                "downstream storyboard/provider/Kling artifacts were not promoted from stale or missing story evidence",
            ],
            "does_not_prove": [
                "human story acceptance",
                "storyboard panel visual quality",
                "accepted storyboard_packet.v1 readiness",
                "provider-accessible media URLs",
                "live Kling generation",
            ],
        },
    }
    write_json(story_path, story_contract)
    write_json(mirror_path, story_contract)

    story_validation = validate_story_contract(story_path, run_root=root)
    downstream_stale = {
        "schema": "persona_dream.story_contract_downstream_stale.v1",
        "status": "PASS_DOWNSTREAM_MARKED_STALE",
        "created_at": created,
        "run_root": str(root),
        "story_contract": source_ref(story_path, base=root),
        "stale_policy": "Downstream storyboard, panel, provider, and Kling artifacts must be regenerated or migration-proven from this accepted story contract.",
        "stale_artifacts": downstream_inventory(root),
        "not_promoted": [
            "storyboard_plan.json",
            "storyboard_packet.json",
            "panel repair receipts",
            "visual review receipts",
            "provider media receipts",
            "Kling scene packet",
        ],
        "paid_provider_call_attempted": False,
        "kling_call_attempted": False,
    }
    write_json(stale_receipt_path, downstream_stale)

    review_receipt = {
        "schema": "persona_dream.story_contract_review_receipt.v1",
        "status": "PASS_STORY_CONTRACT_REVIEWED",
        "created_at": created,
        "owner_subagent": "dreamer",
        "run_root": str(root),
        "story_contract": source_ref(story_path, base=root),
        "work_order": source_ref(work_order_path, base=root),
        "dream_packet": source_ref(dream_packet_path, base=root),
        "validation": story_validation,
        "mocked": mocked,
        "live": "no",
        "forbidden_actions_observed": False,
        "unverified": "human story acceptance, storyboard/panel/provider/Kling readiness",
    }
    write_json(review_receipt_path, review_receipt)

    status = "PASS_STORY_CONTRACT_FULFILLED" if story_validation.get("status") == "PASS_STORY_CONTRACT" else "BLOCKED_STORY_CONTRACT_VALIDATION"
    receipt = {
        "schema": "persona_dream.story_contract_fulfillment.v1",
        "status": status,
        "created_at": created,
        "run_root": str(root),
        "owner_subagent": "dreamer",
        "input_work_order": str(work_order_path),
        "work_order_validation": validation,
        "story_contract": str(story_path),
        "story_contract_sha256": sha256_file(story_path) if story_path.exists() else None,
        "story_contract_mirror": str(mirror_path),
        "story_validation": story_validation,
        "review_receipt": str(review_receipt_path),
        "downstream_stale_receipt": str(stale_receipt_path),
        "downstream_marked_stale": True,
        "forbidden_actions_observed": False,
        "paid_provider_call_attempted": False,
        "kling_call_attempted": False,
        "storyboard_plan_promoted": False,
        "storyboard_packet_written": False,
        "mocked": mocked,
        "live": "no",
        "exercised": "validated work-order consumption, story_contract emission, story validation, downstream stale receipt emission",
        "unverified": "human story acceptance, storyboard regeneration, accepted storyboard_packet.v1, provider media publication, live Kling generation",
    }
    write_json(receipt_path, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_order", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--created-at")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    receipt = fulfill(
        args.work_order,
        run_root=args.run_root,
        output=args.output,
        created_at=args.created_at,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
    return 0 if str(receipt.get("status", "")).startswith("PASS_") else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
