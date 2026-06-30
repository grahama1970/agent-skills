#!/usr/bin/env python3
"""Batch job: run deterministic /create-evidence-case for all sparta_qra records.

This is the deterministic-only phase:
- Flashtext entity extraction
- Graph traversal for crosswalk chains
- Description fetch from sparta_controls
- Build glossary, target_records, cwe_record

No LLM calls. Stage A (gate) and Stage B (generate) run later at inference time.

Output: Updates each QRA with an `evidence_case` field containing the payload.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

import httpx
import typer

app = typer.Typer(help="Batch evidence case generation for sparta_qra")

MEMORY_SOCKET = "/run/user/1000/embry/memory.sock"
BATCH_SIZE = 100
STATE_FILE = Path("${HOME}/.claude/skills/create-qras/.evidence_case_batch_state.json")


def get_memory_client() -> httpx.Client:
    """Get httpx client for memory daemon via Unix socket."""
    transport = httpx.HTTPTransport(uds=MEMORY_SOCKET)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=60.0)


def load_state() -> dict:
    """Load batch state from disk."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"processed": 0, "success": 0, "failed": 0, "skipped": 0, "last_key": None}


def save_state(state: dict) -> None:
    """Save batch state to disk."""
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fetch_qras(client: httpx.Client, offset: int, limit: int) -> list[dict]:
    """Fetch QRAs from sparta_qra collection."""
    resp = client.post("/list", json={
        "collection": "sparta_qra",
        "limit": limit,
        "offset": offset,
    })
    resp.raise_for_status()
    return resp.json().get("documents", [])


def build_evidence_case(client: httpx.Client, question: str, source_id: str | None = None) -> dict:
    """Call /create-evidence-case endpoint."""
    payload = {"question": question}
    if source_id:
        payload["source_id"] = source_id
    resp = client.post("/create-evidence-case", json=payload)
    resp.raise_for_status()
    return resp.json()


def update_qra_with_evidence(client: httpx.Client, qra_key: str, evidence_case: dict) -> bool:
    """Update QRA document with evidence_case field."""
    doc = {
        "_key": qra_key,
        "evidence_case": evidence_case,
        "evidence_case_ts": int(time.time()),
    }
    resp = client.post("/store", json={"document": doc, "collection": "sparta_qra"})
    return resp.status_code == 200


@app.command()
def run(
    limit: int = typer.Option(0, help="Max QRAs to process (0 = all)"),
    batch_size: int = typer.Option(BATCH_SIZE, help="Batch size for fetching"),
    resume: bool = typer.Option(True, help="Resume from last checkpoint"),
    dry_run: bool = typer.Option(False, help="Don't write, just count"),
):
    """Run batch evidence case generation."""
    client = get_memory_client()

    # Get total count
    resp = client.post("/list", json={"collection": "sparta_qra", "limit": 1})
    total = resp.json().get("total", 0)
    print(f"Total QRAs in sparta_qra: {total}")

    # Load state
    state = load_state() if resume else {"processed": 0, "success": 0, "failed": 0, "skipped": 0, "last_key": None}
    offset = state["processed"]

    if offset >= total:
        print("All QRAs already processed.")
        return

    if limit > 0:
        total = min(offset + limit, total)

    print(f"Resuming from offset {offset}, target {total}")
    start_time = time.time()

    while offset < total:
        batch = fetch_qras(client, offset, batch_size)
        if not batch:
            break

        for qra in batch:
            qra_key = qra.get("_key", "")
            question = qra.get("question", "")

            # Skip if already has evidence_case
            if qra.get("evidence_case") and not dry_run:
                state["skipped"] += 1
                state["processed"] += 1
                continue

            if not question:
                state["failed"] += 1
                state["processed"] += 1
                continue

            try:
                # Extract source ID from question if present (e.g., CWE-287)
                source_id = None
                for pattern in ["CWE-", "CAPEC-"]:
                    if pattern in question.upper():
                        # Find the ID
                        import re
                        match = re.search(rf"({pattern}\d+)", question, re.I)
                        if match:
                            source_id = match.group(1).upper()
                            break

                evidence = build_evidence_case(client, question, source_id)

                if not dry_run:
                    if update_qra_with_evidence(client, qra_key, evidence):
                        state["success"] += 1
                    else:
                        state["failed"] += 1
                else:
                    # In dry run, count as success if we got evidence
                    if evidence.get("glossary") or evidence.get("cwe_record"):
                        state["success"] += 1
                    else:
                        state["failed"] += 1

            except Exception as e:
                print(f"Error processing {qra_key}: {e}")
                state["failed"] += 1

            state["processed"] += 1
            state["last_key"] = qra_key

            # Progress report every 100
            if state["processed"] % 100 == 0:
                elapsed = time.time() - start_time
                rate = state["processed"] / elapsed if elapsed > 0 else 0
                eta = (total - offset - state["processed"]) / rate if rate > 0 else 0
                print(f"Processed: {state['processed']}/{total - offset} | "
                      f"Success: {state['success']} | Failed: {state['failed']} | "
                      f"Skipped: {state['skipped']} | Rate: {rate:.1f}/s | ETA: {eta/60:.1f}m")
                save_state(state)

        offset += len(batch)
        state["processed"] = offset
        save_state(state)

    elapsed = time.time() - start_time
    print(f"\nBatch complete in {elapsed/60:.1f} minutes")
    print(f"Total processed: {state['processed']}")
    print(f"Success: {state['success']}")
    print(f"Failed: {state['failed']}")
    print(f"Skipped (already had evidence): {state['skipped']}")


@app.command()
def status():
    """Show batch status."""
    state = load_state()
    print(json.dumps(state, indent=2))


@app.command()
def reset():
    """Reset batch state."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()
    print("Batch state reset.")


@app.command()
def sample(count: int = 5):
    """Sample a few QRAs and show their evidence cases."""
    client = get_memory_client()

    # Get random sample
    qras = fetch_qras(client, 0, count * 10)
    import random
    samples = random.sample(qras, min(count, len(qras)))

    for qra in samples:
        print(f"\n{'='*60}")
        print(f"QRA: {qra.get('_key', '?')}")
        print(f"Question: {qra.get('question', '?')[:100]}...")

        question = qra.get("question", "")
        if question:
            evidence = build_evidence_case(client, question)
            print(f"Glossary entries: {len(evidence.get('glossary', []))}")
            print(f"Crosswalk chains: {len(evidence.get('crosswalk_chains', []))}")
            print(f"CWE record: {'yes' if evidence.get('cwe_record') else 'no'}")
            print(f"Target records: {len(evidence.get('target_records', []))}")
            if evidence.get("cwe_record"):
                print(f"  CWE: {evidence['cwe_record'].get('control_id')}")
            for t in evidence.get("target_records", [])[:3]:
                print(f"  Target: {t.get('control_id')} ({t.get('framework')})")


if __name__ == "__main__":
    app()
