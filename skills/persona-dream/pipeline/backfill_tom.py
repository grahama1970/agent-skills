#!/usr/bin/env python3
"""Backfill ToM-lite annotations on all persona_memory records without tom_state_type.

Batch-mode: queries ArangoDB for all records lacking TOM, sends them in batches
of N to deepseek-ai/DeepSeek-V3.2-TEE via scillm, validates against controlled
vocabulary, and writes annotations back to ArangoDB.

Usage:
    python3 backfill_tom.py --batch-size 20 --concurrency 5
    python3 backfill_tom.py --dry-run  # preview without API calls
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

import httpx


# --- Config ---
SCILLM_URL = os.environ.get("SCILLM_URL", "http://127.0.0.1:4001")
SCILLM_KEY = os.environ.get("SCILLM_KEY", "sk-dev-proxy-123")
CHUTES_URL = os.environ.get("CHUTES_URL", "https://llm.chutes.ai/v1/chat/completions")
CHUTES_KEY = os.environ.get("CHUTES_API_KEY") or os.environ.get("CHUTES_API_TOKEN", "")
ARANGO_URL = os.environ.get("ARANGO_URL", "http://127.0.0.1:8529")
ARANGO_DB = os.environ.get("ARANGO_DB", "memory")
ARANGO_USER = os.environ.get("ARANGO_USER", "root")
ARANGO_PASS = os.environ.get("ARANGO_PASS", "openSesame")

BATCH_MODEL = os.environ.get("TOM_BACKFILL_MODEL", "deepseek-ai/DeepSeek-V3.2-TEE")
TOM_KIND_VALUES = {"emotion", "belief", "goal", "preference", "boundary", "relationship", "knowledge_gap", "unresolved_thread"}
AFFECT_VALUES = {"angry", "sad", "anxious", "confused", "happy", "neutral"}
INTENSITY_VALUES = {"low", "medium", "high", "extreme"}
MAX_TEXT_LENGTH = 600


# --- ArangoDB helpers ---

def _arango_auth() -> str:
    resp = httpx.post(
        f"{ARANGO_URL}/_open/auth",
        json={"username": ARANGO_USER, "password": ARANGO_PASS},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["jwt"]


def _arango_query(jwt: str, query: str, bind_vars: dict | None = None) -> list[dict[str, Any]]:
    all_results: list[dict[str, Any]] = []
    url = f"{ARANGO_URL}/_db/{ARANGO_DB}/_api/cursor"
    body = {"query": query, "bindVars": bind_vars or {}, "batchSize": 5000}
    resp = httpx.post(url, headers={"Authorization": f"bearer {jwt}"}, json=body, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    all_results.extend(data.get("result", []))
    while data.get("hasMore"):
        cursor_id = data["id"]
        resp = httpx.put(
            f"{url}/{cursor_id}",
            headers={"Authorization": f"bearer {jwt}"},
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        all_results.extend(data.get("result", []))
    return all_results


def _arango_update(jwt: str, collection: str, key: str, patch: dict) -> dict:
    resp = httpx.patch(
        f"{ARANGO_URL}/_db/{ARANGO_DB}/_api/document/{collection}/{key}",
        headers={"Authorization": f"bearer {jwt}"},
        json=patch,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# --- Scillm helpers ---

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
    use_chutes: bool = False,
) -> list[dict[str, Any]]:
    """Annotate one batch of records. Returns ordered list of annotation dicts + record keys."""
    keys = [r.get("_key", "") for r in batch]
    prompt = _build_batch_prompt(batch)

    api_url = CHUTES_URL if use_chutes else f"{SCILLM_URL.rstrip('/')}/v1/chat/completions"
    api_key = CHUTES_KEY if use_chutes else SCILLM_KEY
    api_skill = "persona-memory-tom-backfill" if not use_chutes else None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if api_skill:
        headers["X-Caller-Skill"] = api_skill

    async with sem:
        try:
            resp = await client.post(
                api_url,
                headers=headers,
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
            out: list[dict[str, Any]] = []
            for key in keys:
                out.append({"_key": key, "error": str(exc), "abstain": True})
            return out

    # Parse JSON from response
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
        print(f"  JSON parse error: {exc}", flush=True)
        out = []
        for key in keys:
            out.append({"_key": key, "error": f"json_parse:{exc}", "abstain": True})
        return out

    # Pair annotations with keys — handle mismatched lengths
    results: list[dict[str, Any]] = []
    for i, key in enumerate(keys):
        if i < len(annotations):
            ann = annotations[i]
            if isinstance(ann, dict):
                ann["_key"] = key
            else:
                ann = {"_key": key, "error": f"not_dict_at_{i}", "abstain": True}
        else:
            ann = {"_key": key, "error": "missing_annotation", "abstain": True}
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


async def run_backfill(
    batch_size: int = 20,
    concurrency: int = 5,
    dry_run: bool = False,
) -> None:
    print(f"Authenticating with ArangoDB at {ARANGO_URL}...")
    jwt = _arango_auth()
    print(f"Connected. DB: {ARANGO_DB}")

    # Fetch all records without TOM
    print("Fetching persona_memory records without tom_state_type...")
    records = _arango_query(
        jwt,
        "FOR doc IN persona_memory FILTER doc.tom_state_type == null RETURN "
        "{_key: doc._key, persona_id: doc.persona_id, "
        "retrieval_text: doc.retrieval_text, text: doc.text, content: doc.content, "
        "claim_text: doc.claim_text, evidence_text: doc.evidence_text, title: doc.title, "
        "source: doc.source, created_at: doc.created_at}",
    )
    print(f"Fetched {len(records)} records")

    if dry_run:
        print("\n--- DRY RUN ---")
        print(f"Would process {len(records)} records in {len(records) // batch_size + 1} batches of {batch_size}")
        print(f"Model: {BATCH_MODEL}")
        print(f"Concurrency: {concurrency}")
        sample_text = _extract_text(records[0]) if records else "(none)"
        print(f"First record: {records[0].get('_key', '?')} | {sample_text[:100]}")
        return

    # Build batches
    batches = [records[i:i + batch_size] for i in range(0, len(records), batch_size)]
    print(f"Processing {len(batches)} batches (batch_size={batch_size}, concurrency={concurrency})")

    sem = asyncio.Semaphore(concurrency)
    annotated = 0
    promoted = 0
    errors = 0
    skipped = 0
    start_time = time.time()

    async with httpx.AsyncClient(timeout=120.0) as client:
        tasks = [annotate_batch(client, batch, sem, use_chutes=True) for batch in batches]
        for batch_idx, coro in enumerate(asyncio.as_completed(tasks)):
            results = await coro
            for ann in results:
                key = ann.get("_key", "")
                if ann.get("error"):
                    errors += 1
                    print(f"  [{batch_idx+1}/{len(batches)}] {key}: ERROR {ann['error'][:80]}", flush=True)
                    continue
                if ann.get("abstain"):
                    skipped += 1
                    continue

                val_errors = validate_one(ann)
                if val_errors:
                    skipped += 1
                    print(f"  [{batch_idx+1}/{len(batches)}] {key}: validation fail: {val_errors}", flush=True)
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
                    _arango_update(jwt, "persona_memory", key, patch)
                    promoted += 1
                except Exception as exc:
                    errors += 1
                    print(f"  [{batch_idx+1}/{len(batches)}] {key}: DB write error: {exc}", flush=True)

                annotated += 1

            elapsed = time.time() - start_time
            rate = annotated / elapsed if elapsed > 0 else 0
            remaining = (len(batches) - batch_idx - 1) / rate if rate > 0 else 0
            print(
                f"  [{batch_idx+1}/{len(batches)}] "
                f"+{len(results)} records (annotated={annotated}, promoted={promoted}, "
                f"skipped={skipped}, errors={errors}) "
                f"[{elapsed:.0f}s, {rate:.1f}/s, ~{remaining:.0f}s remaining]",
                flush=True,
            )

    elapsed = time.time() - start_time
    print(f"\n--- Done in {elapsed:.0f}s ---")
    print(f"Promoted: {promoted} / {len(records)}")
    print(f"Skipped: {skipped}")
    print(f"Errors: {errors}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill ToM-lite annotations on persona_memory")
    parser.add_argument("--batch-size", type=int, default=20, help="Records per scillm call")
    parser.add_argument("--concurrency", type=int, default=5, help="Concurrent scillm calls")
    parser.add_argument("--dry-run", action="store_true", help="Preview without API calls")
    args = parser.parse_args()
    asyncio.run(run_backfill(
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        dry_run=args.dry_run,
    ))


if __name__ == "__main__":
    main()
