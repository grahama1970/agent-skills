#!/usr/bin/env python3
"""Persist and exactly reread Persona Dream audio steps 37 and 38."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import httpx

COLLECTION = "persona_dream_pipeline_steps"
PLAN_RELATIVE = "phase_11_submit_return/preflight/voice_handoff_plan.json"
RECEIPT_RELATIVE = "phase_11_submit_return/preflight/voice_handoff_memory_receipt.json"
SERVER_FIELDS = {
    "_id", "_rev", "qdrant_collection", "qdrant_point_id", "embedding_model",
    "embedding_version", "text_hash", "semantic_sync_state",
}


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def response_documents(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = payload.get("documents") or payload.get("items") or []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def contains_authored_value(observed: Any, expected: Any) -> bool:
    """Memory merges nested objects on upsert; prove every authored leaf survived."""
    if isinstance(expected, Mapping):
        return isinstance(observed, Mapping) and all(
            key in observed and contains_authored_value(observed[key], value)
            for key, value in expected.items()
        )
    return observed == expected


def canonical_record(
    existing: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    plan_sha: str,
    step_no: int,
    observed_at: str,
) -> dict[str, Any]:
    record = {key: value for key, value in existing.items() if key not in SERVER_FIELDS}
    request_sha = str((plan.get("provider_request") or {}).get("request_body_sha256") or "")
    transcript_sha = str((plan.get("timed_transcript") or {}).get("sha256") or "")
    if step_no == 37:
        rendered = all(
            isinstance(line, Mapping) and line.get("render_status") == "PASS_EXACT_LINE_RENDER"
            for line in plan.get("lines", [])
        )
        status = "PASS_EXACT_LINE_RENDER_READY_FOR_MUX" if rendered else "BLOCKED_AWAITING_EXACT_LINE_RENDER"
        blocker = None if rendered else "render the exact Kai transcript line with the bound voice reference, then produce render and evaluation receipts"
        proves = "the post-mux voice handoff and exact live Kai line render are hash-bound to the active revision, transcript, voice reference, ambient bed, and provider request" if rendered else "the post-mux voice handoff is hash-bound to the active revision, exact transcript, voice reference, ambient bed, and provider request"
        does_not_prove = "the rendered line has been mixed, muxed, or heard in a final video"
    else:
        status = "BLOCKED_AWAITING_ACTIVE_PROVIDER_RETURN_AND_AUDIO_MUX"
        blocker = "after the active repaired provider return exists, mix the exact line and ambient bed, FFmpeg mux them, and prove an audible audio stream"
        proves = "the final assembly requirements for the active post-mux strategy are durably recorded"
        does_not_prove = "the active request has returned media or that final audio assembly has run"
    record.update({
        "status": status,
        "disposition": "current_pending",
        "inputs": {
            "source_revision_id": str(plan.get("revision_id") or ""),
            "audio_strategy": "post_mux",
            "timed_transcript_sha256": transcript_sha,
            "request_body_sha256": request_sha,
        },
        "outputs": [PLAN_RELATIVE],
        "receipt_paths": [PLAN_RELATIVE],
        "artifact_hashes": {PLAN_RELATIVE: plan_sha},
        "request_hash": request_sha,
        "provider_task_id": None,
        "memory_write_method": "/upsert",
        "claims": {"proves": [proves], "does_not_prove": [does_not_prove]},
        "blocker": blocker,
        "observed_at": observed_at,
        "retrieval_text": (
            f"Persona Dream {plan.get('run_id')} {plan.get('revision_id')} step {step_no} "
            f"{record.get('step_name')} status {status} audio strategy post_mux"
        ),
        "tags": [
            "persona-dream",
            f"run:{plan.get('run_id')}",
            f"revision:{plan.get('revision_id')}",
            f"step:{step_no}",
            f"status:{status.lower()}",
            "audio-strategy:post-mux",
            "disposition:current-pending",
        ],
    })
    return record


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("revision_root", type=Path)
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    args = parser.parse_args()
    revision_root = args.revision_root.expanduser().resolve()
    plan_path = revision_root / PLAN_RELATIVE
    if not plan_path.is_file():
        raise SystemExit(f"voice handoff plan missing: {plan_path}")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    run_id = str(plan.get("run_id") or "")
    revision_id = str(plan.get("revision_id") or "")
    if revision_id != revision_root.name or not run_id:
        raise SystemExit("voice handoff plan run/revision binding invalid")

    observed_at = datetime.now(timezone.utc).isoformat()
    timeout = httpx.Timeout(30.0, connect=2.0)
    filters = {"run_id": run_id, "revision_id": revision_id}
    with httpx.Client(base_url=args.memory_base_url, timeout=timeout) as client:
        before_response = client.post("/list", json={"collection": COLLECTION, "limit": 100, "filters": filters})
        before_response.raise_for_status()
        before = response_documents(before_response.json())
        by_step = {int(item["step_no"]): item for item in before if "step_no" in item}
        if len(before) != 42 or 37 not in by_step or 38 not in by_step:
            raise SystemExit(f"expected 42 records including steps 37/38, found {len(before)}")

        plan_sha = sha256_file(plan_path)
        documents = [
            canonical_record(by_step[step_no], plan=plan, plan_sha=plan_sha, step_no=step_no, observed_at=observed_at)
            for step_no in (37, 38)
        ]
        write_response = client.post("/upsert", json={"collection": COLLECTION, "documents": documents})
        write_response.raise_for_status()

        reread_documents = []
        for expected in documents:
            response = client.post(
                "/list",
                json={"collection": COLLECTION, "limit": 2, "filters": {"_key": expected["_key"]}},
            )
            response.raise_for_status()
            observed = response_documents(response.json())
            if len(observed) != 1:
                raise SystemExit(f"exact reread count mismatch for {expected['_key']}: {len(observed)}")
            for field in ("_key", "status", "inputs", "outputs", "artifact_hashes", "request_hash", "blocker", "claims"):
                if not contains_authored_value(observed[0].get(field), expected.get(field)):
                    raise SystemExit(f"exact reread field mismatch for {expected['_key']}: {field}")
            reread_documents.append(observed[0])

    receipt = {
        "schema": "persona_dream.voice_handoff_memory_receipt.v1",
        "status": "PASS_EXACT_REREAD_STEPS_37_38",
        "collection": COLLECTION,
        "run_id": run_id,
        "revision_id": revision_id,
        "voice_handoff_plan_sha256": plan_sha,
        "record_count_before": len(before),
        "updated_step_numbers": [37, 38],
        "exact_reread_count": len(reread_documents),
        "exact_reread_keys": [item["_key"] for item in reread_documents],
        "semantic_sync_states": {item["_key"]: item.get("semantic_sync_state") for item in reread_documents},
        "mocked": False,
        "live": True,
        "observed_at": observed_at,
        "claims": {
            "proves": ["audio pipeline steps 37 and 38 are persisted under exact active run/revision keys and reread with their handoff hash"],
            "does_not_prove": [
                "provider return, audio mix, FFmpeg mux, or audible final output"
                if plan.get("status") == "PASS_EXACT_LINE_RENDER_READY_FOR_MUX"
                else "exact-line TTS rendering, provider return, audio mix, FFmpeg mux, or audible final output"
            ],
        },
    }
    receipt_path = revision_root / RECEIPT_RELATIVE
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"receipt_path": str(receipt_path), **receipt}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
