#!/usr/bin/env python3
"""Execute the Watch row-text materialization read contract for one row.

Reads the planned channels (scene marker, SRT, Whisper, VLM) from the live
``watch_content`` document through the memory HTTP boundary, hashes each
materialized text, extracts entity/actor token spans without regex, and
cross-checks stored SRT text against the on-disk SRT cues for the segment
window. Produces executed receipts that unblock the text/scene corroboration
gate. It never promotes identity: a channel with zero entity spans is recorded
as NOT corroborating the candidate, which is a legitimate honest outcome.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

ARCH_DIR = Path(__file__).resolve().parents[1] / "docs" / "architecture"
DEFAULT_PLAN = (
    ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_row_text_materialization_receipt_plan"
    / "watch_row_text_materialization_receipt_plan.bad_santa_marcus.json"
)
DEFAULT_CORROBORATION_PLAN = (
    ARCH_DIR
    / "generated"
    / "bad_santa_marcus_0248_text_scene_corroboration_receipt_plan"
    / "watch_text_scene_corroboration_receipt_plan.bad_santa_marcus.json"
)
DEFAULT_OUT_DIR = ARCH_DIR / "generated" / "bad_santa_marcus_0248_row_text_receipts"

ENTITY_TOKENS = ("marcus", "mall-store elf")
ACTOR_TOKENS = ("tony cox",)


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise TypeError(f"expected JSON object: {path}")
    return data


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _find_token_spans(text: str, tokens: tuple[str, ...]) -> list[dict[str, Any]]:
    """Case-insensitive substring scan; no regex per repo extraction policy."""
    spans: list[dict[str, Any]] = []
    lowered = text.lower()
    for token in tokens:
        start = 0
        while True:
            index = lowered.find(token, start)
            if index == -1:
                break
            spans.append(
                {
                    "token": token,
                    "start": index,
                    "end": index + len(token),
                    "surface": text[index : index + len(token)],
                }
            )
            start = index + len(token)
    return spans


def _parse_srt_seconds(stamp: str) -> float:
    clock, _, millis = stamp.strip().partition(",")
    hours, minutes, seconds = clock.split(":")
    total = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
    return total + (int(millis) / 1000.0 if millis else 0.0)


def _srt_cues_in_window(
    srt_path: Path, start_seconds: float, end_seconds: float
) -> list[dict[str, Any]]:
    cues: list[dict[str, Any]] = []
    block_lines: list[str] = []

    def flush() -> None:
        timing_index = next(
            (i for i, line in enumerate(block_lines) if "-->" in line), None
        )
        if timing_index is None:
            block_lines.clear()
            return
        timing = block_lines[timing_index]
        start_raw, _, end_raw = timing.partition("-->")
        try:
            cue_start = _parse_srt_seconds(start_raw)
            cue_end = _parse_srt_seconds(end_raw)
        except (ValueError, IndexError):
            block_lines.clear()
            return
        if cue_start < end_seconds and cue_end > start_seconds:
            cues.append(
                {
                    "start_seconds": cue_start,
                    "end_seconds": cue_end,
                    "text": " ".join(
                        line.strip() for line in block_lines[timing_index + 1 :]
                    ).strip(),
                }
            )
        block_lines.clear()

    for raw in srt_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip("﻿").strip()
        if not line:
            flush()
        else:
            block_lines.append(line)
    flush()
    return cues


def _normalize_for_overlap(text: str) -> set[str]:
    cleaned = "".join(ch.lower() if ch.isalnum() or ch.isspace() else " " for ch in text)
    return {word for word in cleaned.split() if len(word) > 2}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute the Watch row-text materialization read contract."
    )
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument(
        "--corroboration-plan", type=Path, default=DEFAULT_CORROBORATION_PLAN
    )
    parser.add_argument("--memory-url", default="http://127.0.0.1:8601")
    parser.add_argument("--srt-path", type=Path, default=None,
                        help="Optional on-disk SRT for cross-check of stored srt_text")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()

    plan = _read_json(args.plan)
    corroboration_plan = _read_json(args.corroboration_plan)
    observation = plan["observation_context"]
    time_range = observation["time_range"]
    read_at = datetime.now(timezone.utc).isoformat()

    doc_ref = None
    for channel_plan in plan["required_channel_plans"]:
        for ref in channel_plan.get("source_refs", []):
            if ref.get("source_type") == "watch_content":
                doc_ref = ref["ref"]
                break
        if doc_ref:
            break
    if not doc_ref:
        print("no watch_content source ref in plan", file=sys.stderr)
        return 1
    doc_key = doc_ref.split("/", 1)[1]

    with httpx.Client(base_url=args.memory_url, timeout=httpx.Timeout(15.0)) as client:
        response = client.post(
            "/recall/by-keys",
            json={"collection": "watch_content", "keys": [doc_key]},
        )
        response.raise_for_status()
        documents = response.json().get("documents", [])
    if not documents:
        print(f"watch_content document not found: {doc_key}", file=sys.stderr)
        return 1
    document = documents[0]

    channel_receipts: list[dict[str, Any]] = []
    for channel_plan in plan["required_channel_plans"]:
        channel = channel_plan["channel"]
        field_used = None
        text = None
        for field in channel_plan["candidate_source_fields"]:
            value = document.get(field)
            if isinstance(value, str) and value.strip():
                field_used = field
                text = value
                break
        source_ref_resolution = None
        if not channel_plan.get("source_refs") and field_used:
            source_ref_resolution = {
                "resolved_from": "live_watch_content_document_field",
                "ref": doc_ref,
                "field": field_used,
                "note": "Plan had no source ref; field exists on the live row.",
            }
        receipt: dict[str, Any] = {
            "channel": channel,
            "source_ref": doc_ref,
            "field_used": field_used,
            "read_at": read_at,
            "materialized_text_present": bool(text),
            "materialized_text_hash": _sha256_text(text) if text else None,
            "materialized_text_chars": len(text) if text else 0,
            "materialized_text": text,
            "entity_spans": _find_token_spans(text, ENTITY_TOKENS) if text else [],
            "actor_spans": _find_token_spans(text, ACTOR_TOKENS) if text else [],
            "status": "MATERIALIZED" if text else "MATERIALIZED_EMPTY_EXPLICIT",
        }
        if source_ref_resolution:
            receipt["source_ref_resolution"] = source_ref_resolution
        channel_receipts.append(receipt)

    srt_cross_check = None
    if args.srt_path and args.srt_path.exists():
        cues = _srt_cues_in_window(
            args.srt_path,
            float(time_range["start_seconds"]),
            float(time_range["end_seconds"]),
        )
        disk_text = " ".join(cue["text"] for cue in cues)
        stored = next(
            (r for r in channel_receipts if r["channel"] == "srt_text"), None
        )
        stored_text = (stored or {}).get("materialized_text") or ""
        disk_words = _normalize_for_overlap(disk_text)
        stored_words = _normalize_for_overlap(stored_text)
        overlap = (
            len(disk_words & stored_words) / len(stored_words) if stored_words else 0.0
        )
        srt_cross_check = {
            "srt_path": str(args.srt_path),
            "window_cue_count": len(cues),
            "disk_window_text_hash": _sha256_text(disk_text) if disk_text else None,
            "stored_vs_disk_word_overlap": round(overlap, 4),
            "consistent": overlap >= 0.8,
        }

    materialized_channels = [
        r["channel"] for r in channel_receipts if r["materialized_text_present"]
    ]
    entity_span_total = sum(len(r["entity_spans"]) for r in channel_receipts)
    actor_span_total = sum(len(r["actor_spans"]) for r in channel_receipts)
    scene_or_vlm_corroborates = any(
        r["entity_spans"] or r["actor_spans"]
        for r in channel_receipts
        if r["channel"] in ("scene_marker_text", "vlm_description")
    )
    srt_or_whisper_corroborates = any(
        r["entity_spans"] or r["actor_spans"]
        for r in channel_receipts
        if r["channel"] in ("srt_text", "whisper_text")
    )
    text_corroborates_entity = scene_or_vlm_corroborates or srt_or_whisper_corroborates

    receipt_doc = {
        "schema": "watch.row_text_materialization_receipt.v1",
        "status": "MATERIALIZED",
        "source_plan": str(args.plan),
        "asset": plan["asset"],
        "observation_context": observation,
        "case_context": plan["case_context"],
        "read_boundary": {
            "path": "memory_http_recall_by_keys",
            "memory_url": args.memory_url,
            "collection": "watch_content",
            "document_key": doc_key,
            "read_at": read_at,
        },
        "channel_receipts": channel_receipts,
        "srt_disk_cross_check": srt_cross_check,
        "entity_span_extraction": {
            "entity_tokens": list(ENTITY_TOKENS),
            "actor_tokens": list(ACTOR_TOKENS),
            "method": "case_insensitive_substring_scan_no_regex",
            "entity_span_total": entity_span_total,
            "actor_span_total": actor_span_total,
        },
        "corroboration_result": {
            "scene_marker_or_vlm_corroborates_entity": scene_or_vlm_corroborates,
            "srt_or_whisper_corroborates_entity": srt_or_whisper_corroborates,
            "text_corroborates_entity": text_corroborates_entity,
            "verdict": (
                "TEXT_CORROBORATES_CANDIDATE"
                if text_corroborates_entity
                else "TEXT_DOES_NOT_CORROBORATE_CANDIDATE"
            ),
        },
        "counts": {
            "required_channel_count": len(plan["required_channel_plans"]),
            "materialized_text_channel_count": len(materialized_channels),
            "materialized_channels": materialized_channels,
        },
        "proof_scope": [
            "row_text_materialization_executed",
            "entity_span_extraction_executed",
            "srt_disk_cross_check" if srt_cross_check else "srt_disk_cross_check_skipped",
        ],
        "claims": {
            "proves": [
                "Row text channels were read through the memory HTTP boundary and hashed",
                "Entity/actor span extraction ran over every materialized channel",
                "Text corroboration outcome is recorded honestly, including absence",
            ],
            "does_not_prove": [
                "character identity",
                "crop/reference similarity",
                "$memory recall answer-path success",
                "real-time annotation tracking",
            ],
        },
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = args.out_dir / "watch_row_text_materialization_receipt.bad_santa_marcus.json"
    _write_json(receipt_path, receipt_doc)

    corroboration = json.loads(json.dumps(corroboration_plan))
    corroboration["schema"] = "watch.text_scene_corroboration_receipt.v1"
    corroboration["status"] = "TEXT_CORROBORATION_RUN"
    corroboration["source_plan"] = str(args.corroboration_plan)
    corroboration["row_text_materialization_receipt"] = str(receipt_path)
    corroboration["materialized_text_channels"] = materialized_channels
    corroboration["counts"]["materialized_text_channel_count"] = len(materialized_channels)
    for entity_plan in corroboration["entity_corroboration_plans"]:
        entity_plan["status"] = (
            "TEXT_CORROBORATED" if text_corroborates_entity else "TEXT_NOT_CORROBORATED"
        )
        blockers = [
            blocker
            for blocker in entity_plan["promotion_blockers"]
            if blocker
            not in ("ROW_TEXT_MATERIALIZATION_MISSING", "ENTITY_TOKEN_CORROBORATION_NOT_RUN")
        ]
        if not text_corroborates_entity:
            blockers.append("TEXT_CHANNELS_DO_NOT_MENTION_CANDIDATE")
        entity_plan["promotion_blockers"] = blockers
        for channel_state in entity_plan["text_channels"]:
            receipt = next(
                (
                    r
                    for r in channel_receipts
                    if r["channel"] == channel_state["channel"]
                    or (
                        channel_state["channel"] == "scene_marker_text"
                        and r["channel"] == "scene_marker_text"
                    )
                ),
                None,
            )
            if receipt is None:
                continue
            channel_state["status"] = receipt["status"]
            channel_state["text_hash"] = receipt["materialized_text_hash"]
            channel_state["contains_entity_token"] = bool(receipt["entity_spans"])
            channel_state["contains_actor_token"] = bool(receipt["actor_spans"])
    corroboration["proof_scope"] = [
        "text_scene_corroboration_executed",
        "identity_promotion_still_gated",
    ]
    corroboration_path = (
        args.out_dir / "watch_text_scene_corroboration_receipt.bad_santa_marcus.json"
    )
    _write_json(corroboration_path, corroboration)

    print(f"row text receipt: {receipt_path}")
    print(f"corroboration receipt: {corroboration_path}")
    print(
        f"materialized {len(materialized_channels)}/{len(plan['required_channel_plans'])} channels; "
        f"entity spans={entity_span_total} actor spans={actor_span_total}; "
        f"verdict={receipt_doc['corroboration_result']['verdict']}"
    )
    if srt_cross_check:
        print(
            f"srt disk cross-check: cues={srt_cross_check['window_cue_count']} "
            f"overlap={srt_cross_check['stored_vs_disk_word_overlap']} "
            f"consistent={srt_cross_check['consistent']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
