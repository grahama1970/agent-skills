#!/usr/bin/env python3
"""Read all fact-extractor accepted_records.jsonl → annotate TOM via Chutes → upsert to memory.

Usage:
    python3 annotate_and_store.py [--dry-run]
    python3 annotate_and_store.py --skip-tom  # upsert without TOM (for testing)
    python3 annotate_and_store.py --batch-size 20 --concurrency 5
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx


MEMORY_URL = os.environ.get("MEMORY_URL", "http://127.0.0.1:8601")
CHUTES_URL = os.environ.get("CHUTES_URL", "https://llm.chutes.ai/v1/chat/completions")
CHUTES_KEY = os.environ.get("CHUTES_API_KEY") or os.environ.get("CHUTES_API_TOKEN", "")
BATCH_MODEL = "deepseek-ai/DeepSeek-V3.2-TEE"
OUTPUT_DIR = Path("/mnt/storage12tb/skills/fact-extractor/outputs")

TOM_KIND_VALUES = {"emotion", "belief", "goal", "preference", "boundary", "relationship", "knowledge_gap", "unresolved_thread"}
AFFECT_VALUES = {"angry", "sad", "anxious", "confused", "happy", "neutral"}
INTENSITY_VALUES = {"low", "medium", "high", "extreme"}
MAX_TEXT_LENGTH = 600


def collect_records() -> list[dict[str, Any]]:
    all_records: list[dict[str, Any]] = []
    for book_dir in sorted(OUTPUT_DIR.iterdir()):
        if not book_dir.is_dir():
            continue
        book_id = book_dir.name
        for jsonl_path in book_dir.rglob("accepted_records.jsonl"):
            with open(jsonl_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    r = json.loads(line)
                    r["_key"] = r.get("_key") or r.get("artifact_id") or f"reingest_{len(all_records)}"
                    if not r.get("book_id"):
                        r["book_id"] = book_id
                    if not r.get("retrieval_text") and r.get("question"):
                        r["retrieval_text"] = f"{r['question']} {r.get('answer', '')}"
                    all_records.append(r)
    return all_records


def _extract_text(record: dict[str, Any]) -> str:
    for key in ("retrieval_text", "claim_text", "evidence_text", "text", "content", "title"):
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _build_tom_prompt(batch: list[dict[str, Any]]) -> str:
    lines = []
    for i, rec in enumerate(batch):
        text = _extract_text(rec)[:MAX_TEXT_LENGTH]
        pid = rec.get("persona_id", "?")
        key = rec.get("_key", "?")
        lines.append(f"[{i}] key={key} persona={pid}")
        lines.append(f"    text: {text}")
    parts = [
        "Annotate each persona memory record below with theory-of-mind labels.",
        "Use ONLY the allowed values. Quote exact text that supports each label.",
        "If a record lacks emotional/ToM content, set abstain=true for that record.",
        "Do NOT infer hidden intent beyond the text.",
        "",
        f"Allowed tom_kind: {', '.join(sorted(TOM_KIND_VALUES))}",
        f"Allowed affect: {', '.join(sorted(AFFECT_VALUES))}",
        f"Allowed intensity: {', '.join(sorted(INTENSITY_VALUES))}",
        "",
        "Reply ONLY with a JSON array. One object per input record, in the same order:",
        '[{"tom_kind":"...","affect":"...","intensity":"...","source_quote":"...","confidence":0.0,"abstain":false}, ...]',
        "",
        "--- RECORDS ---",
        *lines,
    ]
    return "\n".join(parts)


async def annotate_batch(client: httpx.AsyncClient, batch: list[dict[str, Any]], sem: asyncio.Semaphore) -> list[dict[str, Any]]:
    keys = [r.get("_key", "") for r in batch]
    prompt = _build_tom_prompt(batch)
    async with sem:
        try:
            resp = await client.post(
                CHUTES_URL,
                headers={"Authorization": f"Bearer {CHUTES_KEY}", "Content-Type": "application/json"},
                json={"model": BATCH_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.1, "max_tokens": 4000},
                timeout=180.0,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            return [{"_key": key, "error": str(exc), "abstain": True} for key in keys]

    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]

    try:
        annotations = json.loads(content.strip())
        if not isinstance(annotations, list):
            annotations = [annotations]
    except json.JSONDecodeError as exc:
        return [{"_key": key, "error": f"json_parse:{exc}", "abstain": True} for key in keys]

    results = []
    for i, key in enumerate(keys):
        if i < len(annotations) and isinstance(annotations[i], dict):
            ann = annotations[i]
            ann["_key"] = key
        else:
            ann = {"_key": key, "error": f"missing_annotation_at_{i}", "abstain": True}
        results.append(ann)
    return results


def validate_tom(ann: dict[str, Any]) -> list[str]:
    errors = []
    if ann.get("abstain"):
        return errors
    tk = ann.get("tom_kind", "")
    if tk and tk not in TOM_KIND_VALUES:
        errors.append(f"invalid tom_kind: {tk}")
    af = ann.get("affect", "")
    if af and af not in AFFECT_VALUES:
        errors.append(f"invalid affect: {af}")
    it = ann.get("intensity", "")
    if it and it not in INTENSITY_VALUES:
        errors.append(f"invalid intensity: {it}")
    sq = ann.get("source_quote", "")
    if not sq and not ann.get("abstain"):
        errors.append("missing source_quote")
    conf = ann.get("confidence", 0)
    if not isinstance(conf, (int, float)) or conf < 0 or conf > 1:
        errors.append(f"invalid confidence: {conf}")
    return errors


def apply_tom(record: dict[str, Any], ann: dict[str, Any]) -> dict[str, Any]:
    record["tom_state_type"] = ann.get("tom_kind", "")
    record["tom_state"] = json.dumps({
        "holder": ann.get("source_quote", ""),
        "mental_state": ann.get("tom_kind", ""),
        "target": ann.get("affect", ""),
    })
    record["tom_affect"] = ann.get("affect", "")
    record["tom_intensity"] = ann.get("intensity", "")
    record["tom_confidence"] = ann.get("confidence", 0)
    return record


def upsert_batch(batch: list[dict[str, Any]]) -> int:
    resp = httpx.post(
        f"{MEMORY_URL.rstrip('/')}/upsert",
        json={"collection": "persona_memory", "documents": batch},
        timeout=120,
    )
    if resp.status_code >= 400:
        err = resp.text[:200]
        print(f"  upsert batch failed ({len(batch)} docs): {resp.status_code} {err}", flush=True)
        return 0
    result = resp.json()
    return result.get("stored", 0) or result.get("count", len(batch))


async def main_async(
    batch_size: int = 20,
    concurrency: int = 5,
    skip_tom: bool = False,
    dry_run: bool = False,
) -> None:
    records = collect_records()
    print(f"Collected {len(records)} records from disk")

    if dry_run:
        sample = records[0] if records else {}
        print(f"Sample: {json.dumps(sample, indent=2)[:400]}")
        return

    if skip_tom:
        # Upsert directly without TOM annotation
        store_batch_size = 500
        batches = [records[i:i + store_batch_size] for i in range(0, len(records), store_batch_size)]
        total = 0
        for i, batch in enumerate(batches):
            stored = upsert_batch(batch)
            total += stored
            print(f"  [{i+1}/{len(batches)}] upserted {stored} (total: {total})", flush=True)
        print(f"Done: {total} records upserted")
        return

    # Step 1: Annotate TOM in batches
    tom_batches = [records[i:i + batch_size] for i in range(0, len(records), batch_size)]
    print(f"Annotating {len(tom_batches)} TOM batches (batch_size={batch_size}, concurrency={concurrency})")

    sem = asyncio.Semaphore(concurrency)
    annotated = 0
    abstained = 0
    errors = 0
    start = time.time()

    async with httpx.AsyncClient(timeout=180.0) as client:
        tasks = [annotate_batch(client, batch, sem) for batch in tom_batches]
        for batch_idx, coro in enumerate(asyncio.as_completed(tasks)):
            annotations = await coro
            for i, ann in enumerate(annotations):
                if ann.get("error"):
                    errors += 1
                    continue
                if ann.get("abstain"):
                    abstained += 1
                    continue
                val_errors = validate_tom(ann)
                if val_errors:
                    abstained += 1
                    continue
                apply_tom(records[annotated + abstained + errors - 1], ann)
                annotated += 1

            elapsed = time.time() - start
            rate = (annotated + abstained + errors) / elapsed if elapsed > 0 else 0
            remaining = (len(tom_batches) - batch_idx - 1) / rate if rate > 0 else 0
            print(
                f"  [{batch_idx+1}/{len(tom_batches)}] "
                f"annotated={annotated} abstained={abstained} errors={errors} "
                f"[{elapsed:.0f}s, {rate:.1f}/s, ~{remaining:.0f}s remaining]",
                flush=True,
            )

    elapsed = time.time() - start
    print(f"\nTOM annotation done in {elapsed:.0f}s — {annotated} TOM, {abstained} abstained, {errors} errors")

    # Step 2: Upsert all records (with TOM now pre-populated) to memory
    store_batch_size = 500
    store_batches = [records[i:i + store_batch_size] for i in range(0, len(records), store_batch_size)]
    print(f"\nUpserting {len(store_batches)} batches to memory...")

    total_stored = 0
    for i, batch in enumerate(store_batches):
        stored = upsert_batch(batch)
        total_stored += stored
        elapsed = time.time() - start
        print(f"  [{i+1}/{len(store_batches)}] upserted {stored} (total: {total_stored}) [{elapsed:.0f}s]", flush=True)

    print(f"\nDone: {total_stored}/{len(records)} records stored to persona_memory")


def main() -> None:
    parser = argparse.ArgumentParser(description="Annotate TOM → store to memory")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-tom", action="store_true")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()
    asyncio.run(main_async(
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        skip_tom=args.skip_tom,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
