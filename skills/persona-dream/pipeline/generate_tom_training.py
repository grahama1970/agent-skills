#!/usr/bin/env python3
"""Generate TOM training data: annotate N records from disk, save to JSONL.

Usage:
    python3 generate_tom_training.py --limit 2000 --batch-size 20 --concurrency 5
    python3 generate_tom_training.py --limit 2000 --out /tmp/tom_training.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx


CHUTES_URL = os.environ.get("CHUTES_URL", "https://llm.chutes.ai/v1/chat/completions")
CHUTES_KEY = os.environ.get("CHUTES_API_KEY") or os.environ.get("CHUTES_API_TOKEN", "")
BATCH_MODEL = "deepseek-ai/DeepSeek-V3.2-TEE"
OUTPUT_DIR = Path("/mnt/storage12tb/skills/fact-extractor/outputs")

TOM_KIND_VALUES = {"emotion", "belief", "goal", "preference", "boundary", "relationship", "knowledge_gap", "unresolved_thread"}
AFFECT_VALUES = {"angry", "sad", "anxious", "confused", "happy", "neutral"}
INTENSITY_VALUES = {"low", "medium", "high", "extreme"}
MAX_TEXT_LENGTH = 600


def _extract_text(r: dict[str, Any]) -> str:
    for k in ("evidence_quote", "evidence_text", "text", "retrieval_text", "claim_text", "content", "title"):
        v = r.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def _build_prompt(batch: list[dict[str, Any]]) -> str:
    lines = []
    for i, rec in enumerate(batch):
        text = _extract_text(rec)[:MAX_TEXT_LENGTH]
        lines.append(f"[{i}] key={rec.get('_key','?')} persona={rec.get('persona_id','?')}")
        lines.append(f"    text: {text}")
    parts = [
        "Annotate each record below with theory-of-mind labels.",
        "",
        "Allowed tom_kind: emotion, belief, goal, preference, boundary, relationship, knowledge_gap, unresolved_thread",
        "  - emotion: speaker feels an affective state (guilt, fear, joy, etc.), OR an implicit emotional signal conveyed through terse narrative framing",
        "  - belief: speaker holds an assumption or conviction about something",
        "  - goal: speaker wants or intends an outcome",
        "  - preference: speaker likes/dislikes something (stable disposition, not momentary feeling)",
        "  - boundary: speaker sets or encounters a social/ethical limit",
        "  - relationship: speaker perceives a social connection between agents",
        "  - knowledge_gap: speaker lacks information another agent has",
        "  - unresolved_thread: speaker leaves a topic or question open",
        "Allowed affect: angry, sad, anxious, confused, happy, neutral",
        "  Implicit mapping: guilt->sad, fear->anxious, disgust->angry, joy->happy, surprise->confused",
        "  affect applies only when tom_kind=emotion; set to null for all other tom_kind values",
        "Allowed intensity: low, medium, high, extreme",
        "  - low: subtle implication, background state",
        "  - medium: explicit statement of the state",
        "  - high: strong or emphatic expression",
        "  - extreme: overwhelming or consuming state",
        "",
        "A record has ToM content if the text describes a speaker's internal mental state.",
        "Also recognize implicit emotional signals: a brief factual statement about an emotionally-charged event conveys emotion through framing even without explicit feeling words. Such records SHOULD receive an emotion label.",
        "",
        "If a record lacks ToM content (neither explicit nor implicit signals), set abstain=true AND set all fields to null.",
        "Never output abstain=false with tom_kind=null. Never output abstain=true with any non-null ToM field.",
        "",
        "source_quote: verbatim substring of the text that best supports the ToM label; empty if abstain=true",
        "confidence: 0.0 (abstain/no match), 0.5 (paraphrased), 1.0 (verbatim match)",
        "",
        "--- EXAMPLE ---",
        "Input: [0] key=ex1 speaker=xylar",
        "    text: Xylar felt a surge of guilt as he remembered the meeting.",
        'Output: [{"tom_kind":"emotion","affect":"sad","intensity":"high","source_quote":"felt a surge of guilt","confidence":1.0,"abstain":false}]',
        "",
        "Input: [1] key=ex2 speaker=admin",
        "    text: The cron job completed at 03:00 with no errors.",
        'Output: [{"tom_kind":null,"affect":null,"intensity":null,"source_quote":"","confidence":0.0,"abstain":true}]',
        "--- END EXAMPLE ---",
        "",
        "Output format — return ONLY this JSON array. One object per record in the same order.",
        "No markdown fences. No preamble. No trailing commentary. Start with [ and end with ].",
        '[{"tom_kind":"...","affect":null|"...","intensity":null|"...","source_quote":"...","confidence":0.0,"abstain":false}, ...]',
        "Note: affect and intensity must be null when tom_kind is not emotion; must NOT be null when tom_kind=emotion.",
        "",
        "--- RECORDS ---",
        *lines,
    ]
    return "\n".join(parts)


async def annotate_batch(client: httpx.AsyncClient, batch: list[dict[str, Any]], sem: asyncio.Semaphore) -> list[dict[str, Any]]:
    keys = [r.get("_key", "") for r in batch]
    prompt = _build_prompt(batch)
    async with sem:
        try:
            resp = await client.post(CHUTES_URL, headers={
                "Authorization": f"Bearer {CHUTES_KEY}", "Content-Type": "application/json",
            }, json={
                "model": BATCH_MODEL, "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1, "max_tokens": 4000,
            }, timeout=180.0)
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
            ann = {"_key": key, "error": f"missing_at_{i}", "abstain": True}
        results.append(ann)
    return results


def validate(ann: dict[str, Any]) -> list[str]:
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
    if not ann.get("source_quote") and not ann.get("abstain"):
        errors.append("missing source_quote")
    return errors


def collect_sample(limit: int) -> list[dict[str, Any]]:
    """Collect a balanced sample across books."""
    records = []
    books = sorted(OUTPUT_DIR.iterdir())
    for book_dir in books:
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
                    r["_key"] = r.get("_key") or r.get("artifact_id", f"r{len(records)}")
                    if not r.get("book_id"):
                        r["book_id"] = book_id
                    if not r.get("retrieval_text") and r.get("question"):
                        r["retrieval_text"] = f"{r['question']} {r.get('answer', '')}"
                    records.append(r)
                    if len(records) >= limit:
                        return records
    return records


async def main(limit: int, batch_size: int, concurrency: int, out_path: Path) -> None:
    records = collect_sample(limit)
    print(f"Collected {len(records)} records")

    batches = [records[i:i + batch_size] for i in range(0, len(records), batch_size)]
    print(f"Annotating {len(batches)} batches via Chutes {BATCH_MODEL}")

    sem = asyncio.Semaphore(concurrency)
    annotated = 0
    errors = 0
    start = time.time()
    out_lines = []

    async with httpx.AsyncClient(timeout=180.0) as client:
        tasks = [annotate_batch(client, batch, sem) for batch in batches]
        for batch_idx, coro in enumerate(asyncio.as_completed(tasks)):
            annotations = await coro
            for record, ann in zip(batches[batch_idx], annotations):
                if ann.get("error"):
                    errors += 1
                    continue
                val_errors = validate(ann)
                if val_errors or ann.get("abstain"):
                    continue
                record["tom_state_type"] = ann["tom_kind"]
                record["tom_state"] = json.dumps({"holder": ann.get("source_quote",""), "mental_state": ann["tom_kind"], "target": ann.get("affect","")})
                record["tom_affect"] = ann.get("affect", "")
                record["tom_intensity"] = ann.get("intensity", "")
                record["tom_confidence"] = ann.get("confidence", 0)
                out_lines.append(json.dumps(record, ensure_ascii=False))
                annotated += 1

            elapsed = time.time() - start
            rate = (batch_idx + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(batches) - batch_idx - 1) / rate if rate > 0 else 0
            print(f"  [{batch_idx+1}/{len(batches)}] annotated={annotated} errors={errors} [{elapsed:.0f}s, {rate:.2f}/s, ~{remaining:.0f}s]", flush=True)

    out_path.write_text("\n".join(out_lines), encoding="utf-8")
    elapsed = time.time() - start
    print(f"\nDone: {annotated} annotated records saved to {out_path} in {elapsed:.0f}s")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--out", default="/mnt/storage12tb/tom_training_data.jsonl")
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.batch_size, args.concurrency, Path(args.out)))
