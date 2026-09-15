#!/usr/bin/env python3
"""Create source-bound emotional triggers from live persona-memory recall."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

SCHEMA = "persona_dream.emotional_context.v1"
RECEIPT_SCHEMA = "persona_dream.memory_recall_emotional_trigger_receipt.v1"
COLLECTION = "persona_memory"


def _sha(value: Any) -> str:
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _one_line(value: Any, limit: int = 500) -> str:
    return " ".join(str(value or "").split())[:limit].rstrip()


def _emotions(doc: dict[str, Any]) -> list[str]:
    context = doc.get("emotional_context") if isinstance(doc.get("emotional_context"), dict) else {}
    values = context.get("emotions") or next(
        (value for key, value in context.items() if key.endswith("_emotions") and value),
        None,
    ) or doc.get("emotion") or []
    if isinstance(values, str):
        values = values.split(",")
    return list(dict.fromkeys(_one_line(value, 80).lower() for value in values if _one_line(value)))


def _intensity(doc: dict[str, Any]) -> float | None:
    context = doc.get("emotional_context") if isinstance(doc.get("emotional_context"), dict) else {}
    value = context.get("intensity", doc.get("emotional_intensity", doc.get("intensity_score")))
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(1.0, number / 5.0 if number > 1.0 else number)), 3)


def _matches_persona(doc: dict[str, Any], persona: str) -> bool:
    aliases = {persona, persona.replace("-", "_")}
    ids = {str(doc.get("persona_id") or ""), *(str(value) for value in doc.get("persona_ids") or [])}
    ids.update(str(tag).split(":", 1)[1] for tag in doc.get("tags") or [] if str(tag).startswith("persona:"))
    return bool(aliases & ids)


def _trigger(doc: dict[str, Any], *, query: str, recall_rank: int, recall_sha: str) -> dict[str, Any] | None:
    emotions = _emotions(doc)
    intensity = _intensity(doc)
    if not emotions or intensity is None:
        return None
    event = doc.get("event_context") if isinstance(doc.get("event_context"), dict) else {}
    context = doc.get("emotional_context") if isinstance(doc.get("emotional_context"), dict) else {}
    source_key = str(doc.get("_key") or "")
    source_ref = f"{COLLECTION}/{source_key}"
    immediate = _one_line(event.get("immediate_trigger") or doc.get("claim_text") or doc.get("summary"))
    if not source_key or not immediate:
        return None
    return {
        "trigger_id": f"recall-{source_key}",
        "trigger_text": immediate,
        "relationship_context": _one_line(doc.get("context_summary") or doc.get("tom_content")),
        "source_event_ids": [source_ref],
        "source_types": ["persona_memory_recall"],
        "appraisal": {
            "emotions": emotions,
            "intensity": intensity,
            "valence": context.get("emotional_valence"),
            "regulation_strategy": context.get("regulation_strategy"),
        },
        "emotion_delta": {},
        "empathy": {
            "confidence": 0.0,
            "gap": "Recall proves emotional provenance, not empathy accuracy.",
            "safe_response_constraint": "Use the recalled experience to shape personality and delivery; do not invent new facts.",
        },
        "dream_seed": f"Reflect synthetically on why the recalled experience still carries {', '.join(emotions)}.",
        "safe_response_constraint": "The dream may consolidate this experience but must not become a literal memory.",
        "provenance": {
            "source_collection": COLLECTION,
            "source_key": source_key,
            "source_document_sha256": _sha(doc),
            "recall_query": query,
            "recall_rank": recall_rank,
            "recall_response_sha256": recall_sha,
        },
    }


def run(args: argparse.Namespace) -> tuple[dict[str, Any], dict[str, Any]]:
    query = _one_line(args.query, 800)
    if not query.endswith("?"):
        raise SystemExit("BLOCKED_TRIGGER_RECALL_QUERY_NOT_QUESTION_SHAPED")
    tag = f"persona:{args.persona}"
    timeout = httpx.Timeout(20.0, connect=2.0)
    headers = {"X-Caller-Skill": "persona-dream"}
    with httpx.Client(base_url=args.memory_base_url.rstrip("/"), timeout=timeout, headers=headers) as client:
        recall_response = client.post("/recall", json={
            "q": query,
            "k": args.k,
            "collections": [COLLECTION],
            "tags": [tag],
            "threshold": 0.0,
        })
        recall_response.raise_for_status()
        recall = recall_response.json()
        recall_sha = _sha(recall)
        triggers: list[dict[str, Any]] = []
        source_rows: list[dict[str, Any]] = []
        for rank, row in enumerate(recall.get("items") or [], 1):
            key = str(row.get("_key") or "")
            if not key:
                continue
            reread_response = client.post("/list", json={
                "collection": COLLECTION,
                "limit": 2,
                "filters": {"_key": key},
            })
            reread_response.raise_for_status()
            docs = reread_response.json().get("documents") or []
            if len(docs) != 1 or not _matches_persona(docs[0], args.persona):
                continue
            trigger = _trigger(docs[0], query=query, recall_rank=rank, recall_sha=recall_sha)
            if trigger:
                triggers.append(trigger)
                source_rows.append({
                    "_key": key,
                    "recall_rank": rank,
                    "exact_reread": True,
                    "source_document_sha256": trigger["provenance"]["source_document_sha256"],
                })
            if len(triggers) >= args.limit:
                break

    status = "PASS_MEMORY_RECALL_EMOTIONAL_TRIGGERS" if triggers else "BLOCKED_NO_SOURCE_BOUND_EMOTIONAL_TRIGGER"
    packet = {
        "schema": SCHEMA,
        "status": status,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "persona_id": args.persona,
        "source": "$memory /recall + exact /list reread",
        "recall_query": query,
        "recall_response_sha256": recall_sha,
        "triggers": triggers,
        "boundary": "real persona-memory experience seeds synthetic consolidation; the dream is not literal experience",
    }
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "status": status,
        "persona_id": args.persona,
        "collection": COLLECTION,
        "persona_tag": tag,
        "query": query,
        "recall_found": bool(recall.get("found")),
        "recall_count": len(recall.get("items") or []),
        "recall_response_sha256": recall_sha,
        "trigger_count": len(triggers),
        "source_rows": source_rows,
        "packet_sha256": _sha(packet),
        "live": True,
        "mocked": False,
        "failed_gates": [] if triggers else ["no recalled persona-memory row had exact persona scope plus structured emotion and intensity"],
    }
    return packet, receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persona", default="embry")
    parser.add_argument("--query", required=True)
    parser.add_argument("--k", type=int, default=10)
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--memory-base-url", default="http://127.0.0.1:8601")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    packet, receipt = run(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.receipt.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.receipt.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']} triggers={receipt['trigger_count']}")
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
