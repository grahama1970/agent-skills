#!/usr/bin/env python3
"""Re-ingest all fact-extractor accepted_records.jsonl to persona_memory via memory service.

Then run TOM backfill via Chutes deepseek-ai/DeepSeek-V3.2-TEE.

Usage:
    python3 reingest_and_backfill.py [--dry-run]
    python3 reingest_and_backfill.py --reingest-only
    python3 reingest_and_backfill.py --backfill-only
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


# --- Config ---
MEMORY_URL = os.environ.get("MEMORY_URL", "http://127.0.0.1:8601")
CHUTES_URL = os.environ.get("CHUTES_URL", "https://llm.chutes.ai/v1/chat/completions")
CHUTES_KEY = os.environ.get("CHUTES_API_KEY") or os.environ.get("CHUTES_API_TOKEN", "")
BATCH_MODEL = "deepseek-ai/DeepSeek-V3.2-TEE"
OUTPUT_DIR = Path("/mnt/storage12tb/skills/fact-extractor/outputs")

TOM_KIND_VALUES = {"emotion", "belief", "goal", "preference", "boundary", "relationship", "knowledge_gap", "unresolved_thread"}
AFFECT_VALUES = {"angry", "sad", "anxious", "confused", "happy", "neutral"}
INTENSITY_VALUES = {"low", "medium", "high", "extreme"}
MAX_TEXT_LENGTH = 600


# --- Re-ingestion ---

def collect_all_records() -> list[dict[str, Any]]:
    """Collect all accepted_records.jsonl from all books."""
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
                    record = json.loads(line)
                    record["_key"] = record.get("_key") or record.get("artifact_id") or f"reingest_{len(all_records)}"
                    if not record.get("book_id"):
                        record["book_id"] = book_id
                    if not record.get("retrieval_text") and record.get("question"):
                        record["retrieval_text"] = f"{record['question']} {record.get('answer', '')}"
                    all_records.append(record)
    return all_records


def upsert_batch(batch: list[dict[str, Any]]) -> tuple[int, list[str]]:
    """Upsert one batch to memory service. Returns (count, errors)."""
    errors: list[str] = []
    resp = httpx.post(
        f"{MEMORY_URL.rstrip('/')}/upsert",
        json={"collection": "persona_memory", "documents": batch},
        timeout=60,
    )
    if resp.status_code >= 400:
        return 0, [f"upsert failed: {resp.status_code} {resp.text[:200]}"]
    result = resp.json()
    stored = result.get("stored", 0) or result.get("count", len(batch))
    return stored, errors


def reingest(dry_run: bool = False) -> int:
    """Re-ingest all records to persona_memory. Returns total count."""
    records = collect_all_records()
    print(f"Found {len(records)} records on disk")

    if dry_run:
        sample = records[0] if records else {}
        print(f"Sample: {json.dumps(sample, indent=2)[:300]}")
        return 0

    # Upsert in batches
    batch_size = 500
    batches = [records[i:i + batch_size] for i in range(0, len(records), batch_size)]
    total_stored = 0
    total_errors = 0
    start = time.time()

    for i, batch in enumerate(batches):
        stored, errors = upsert_batch(batch)
        total_stored += stored
        total_errors += len(errors)
        elapsed = time.time() - start
        rate = (i + 1) / elapsed if elapsed > 0 else 0
        remaining = (len(batches) - i - 1) / rate if rate > 0 else 0
        status = f"[{i+1}/{len(batches)}] {stored} stored"
        if errors:
            status += f", {errors[0][:60]}"
        print(f"  {status} [{elapsed:.0f}s, {rate:.1f}/s, ~{remaining:.0f}s remaining]", flush=True)

    elapsed = time.time() - start
    print(f"Re-ingested {total_stored}/{len(records)} records in {elapsed:.0f}s ({total_errors} errors)")
    return total_stored


# --- TOM Backfill ---

def _extract_text(record: dict[str, Any]) -> str:
    for key in ("retrieval_text", "claim_text", "evidence_text", "text", "content", "title"):
        val = record.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def _build_batch_prompt(batch: list[dict[str, Any]]) -> str:
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


async def annotate_batch(
    client: httpx.AsyncClient,
    batch: list[dict[str, Any]],
    sem: asyncio.Semaphore,
) -> list[dict[str, Any]]:
    keys = [r.get("_key", "") for r in batch]
    prompt = _build_batch_prompt(batch)
    async with sem:
        try:
            resp = await client.post(
                CHUTES_URL,
                headers={
                    "Authorization": f"Bearer {CHUTES_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": BATCH_MODEL,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 4000,
                },
                timeout=180.0,
            )
            resp.raise_for_status()
            body = resp.json()
            content = body["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            print(f"  ERROR: {exc}", flush=True)
            return [{"_key": key, "error": str(exc), "abstain": True} for key in keys]

    if "```json" in content:
        content = content.split("```json")[1].split("```")[0]
    elif "```" in content:
        content = content.split("```")[1].split("```")[0]
    content = content.strip()

    try:
        annotations = json.loads(content)
        if not isinstance(annotations, list):
            annotations = [annotations]
    except json.JSONDecodeError as exc:
        return [{"_key": key, "error": f"json_parse:{exc}", "abstain": True} for key in keys]

    results: list[dict[str, Any]] = []
    for i, key in enumerate(keys):
        if i < len(annotations) and isinstance(annotations[i], dict):
            ann = annotations[i]
            ann["_key"] = key
        else:
            ann = {"_key": key, "error": f"missing_annotation_at_{i}", "abstain": True}
        results.append(ann)
    return results


def validate_one(ann: dict[str, Any]) -> list[str]:
    errors: list[str] = []
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


def fetch_no_tom_records() -> list[dict[str, Any]]:
    """Fetch all persona_memory records without TOM via recall."""
    all_items: list[dict[str, Any]] = []
    seen: set[str] = set()
    queries = ["persona", "memory", "character", "event", "feeling", "story", "fact"]
    import random
    random.shuffle(queries)
    for q in queries:
        if len(all_items) >= 10000:
            break
        try:
            resp = httpx.post(
                f"{MEMORY_URL.rstrip('/')}/recall",
                json={"q": q, "collections": ["persona_memory"], "k": 200},
                timeout=30,
            )
            if resp.status_code != 200:
                continue
            for item in resp.json().get("items", []):
                key = item.get("_key", "")
                if key not in seen and not item.get("tom_state_type"):
                    seen.add(key)
                    all_items.append(item)
        except Exception:
            continue
    return all_items


async def run_backfill(batch_size: int = 20, concurrency: int = 5, dry_run: bool = False) -> None:
    records = fetch_no_tom_records()
    print(f"Fetched {len(records)} records without TOM from memory service")

    if dry_run:
        sample_text = _extract_text(records[0]) if records else "(none)"
        sample_key = records[0].get("_key", "?") if records else "?"
        print(f"Would process {len(records)} records in {len(records)//batch_size+1} batches")
        print(f"Model: {BATCH_MODEL}")
        print(f"First record: {sample_key} | {sample_text[:100]}")
        return

    batches = [records[i:i + batch_size] for i in range(0, len(records), batch_size)]
    print(f"Processing {len(batches)} batches")

    sem = asyncio.Semaphore(concurrency)
    annotated = 0
    promoted = 0
    errors = 0
    skipped = 0
    start_time = time.time()

    async with httpx.AsyncClient(timeout=180.0) as client:
        tasks = [annotate_batch(client, batch, sem) for batch in batches]
        for batch_idx, coro in enumerate(asyncio.as_completed(tasks)):
            results = await coro
            for ann in results:
                key = ann.get("_key", "")
                if ann.get("error"):
                    errors += 1
                    continue
                if ann.get("abstain"):
                    skipped += 1
                    continue
                val_errors = validate_one(ann)
                if val_errors:
                    skipped += 1
                    print(f"  [{batch_idx+1}/{len(batches)}] {key}: validation: {val_errors}", flush=True)
                    continue
                patch = {
                    "tom_state_type": ann.get("tom_kind", ""),
                    "tom_state": json.dumps({
                        "holder": ann.get("source_quote", ""),
                        "mental_state": ann.get("tom_kind", ""),
                        "target": ann.get("affect", ""),
                    }),
                    "tom_affect": ann.get("affect", ""),
                    "tom_intensity": ann.get("intensity", ""),
                    "tom_confidence": ann.get("confidence", 0),
                }
                try:
                    resp = httpx.post(
                        f"{MEMORY_URL.rstrip('/')}/upsert",
                        json={"collection": "persona_memory", "documents": [{**{"_key": key}, **patch}]},
                        timeout=15,
                    )
                    if resp.status_code >= 400:
                        errors += 1
                        print(f"  [{batch_idx+1}/{len(batches)}] {key}: upsert fail: {resp.text[:100]}", flush=True)
                    else:
                        promoted += 1
                except Exception as exc:
                    errors += 1
                    print(f"  [{batch_idx+1}/{len(batches)}] {key}: upsert error: {exc}", flush=True)
                annotated += 1

            elapsed = time.time() - start_time
            rate = annotated / elapsed if elapsed > 0 else 0
            remaining = (len(batches) - batch_idx - 1) / rate if rate > 0 else 0
            print(
                f"  [{batch_idx+1}/{len(batches)}] "
                f"+{len(results)} (annotated={annotated}, promoted={promoted}, "
                f"skipped={skipped}, errors={errors}) "
                f"[{elapsed:.0f}s, {rate:.1f}/s, ~{remaining:.0f}s remaining]",
                flush=True,
            )

    elapsed = time.time() - start_time
    print(f"\nDone in {elapsed:.0f}s — promoted={promoted}, skipped={skipped}, errors={errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-ingest + TOM backfill")
    parser.add_argument("--reingest-only", action="store_true")
    parser.add_argument("--backfill-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    args = parser.parse_args()

    if not args.backfill_only:
        reingest(dry_run=args.dry_run)
    if not args.reingest_only:
        asyncio.run(run_backfill(
            batch_size=args.batch_size,
            concurrency=args.concurrency,
            dry_run=args.dry_run,
        ))


if __name__ == "__main__":
    main()
