"""Generate teacher rationales for chain-reasoning GPT training data.

Reads gpt_rationale.jsonl, sends each (request, skills) pair through
chutes-call batch to generate detailed rationales explaining WHY skills
compose for each request. Writes enriched records back.

Usage:
    uv run python scripts/generate_rationales.py \
        --input state/training/gpt_rationale.jsonl \
        --output state/training/gpt_rationale_enriched.jsonl \
        --batch-size 50 --concurrency 5
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer
from loguru import logger

# Add chutes-call to path
import httpx

CHUTES_CALL_URL = "http://localhost:8630"

app = typer.Typer()

RATIONALE_SYSTEM_PROMPT = (
    "You are a skill-chain reasoning expert for Embry OS, an AI agent operating system.\n"
    "Given a user request and the skill chain that was used to fulfill it, explain WHY "
    "these specific skills compose together to solve the request.\n\n"
    "Rules:\n"
    "- Explain the BOND between consecutive skills (how output of skill A feeds into skill B)\n"
    "- Reference what each skill provides (its capability)\n"
    "- Explain why THIS ordering matters\n"
    "- If a single skill suffices, explain why no chain is needed\n"
    "- Keep rationale concise (2-4 sentences)\n"
    "- Do NOT repeat the request or skill list — focus on the reasoning\n"
    "- Write in present tense, active voice\n"
)


def build_user_prompt(request: str, skills: list[str]) -> str:
    """Build the user prompt for rationale generation."""
    # Truncate long requests to save tokens
    req_short = request[:500] if len(request) > 500 else request
    skills_str = " → ".join(f"/{s}" for s in skills)
    return (
        f"User request: {req_short}\n\n"
        f"Skill chain used: {skills_str}\n\n"
        f"Explain WHY this chain of skills composes to fulfill this request."
    )


@app.command()
def generate(
    input_file: Path = typer.Option("state/training/gpt_rationale.jsonl", "--input", "-i"),
    output_file: Path = typer.Option("state/training/gpt_rationale_enriched.jsonl", "--output", "-o"),
    batch_size: int = typer.Option(50, "--batch-size", "-b", help="Records per batch call"),
    concurrency: int = typer.Option(5, "--concurrency", "-c"),
    model: str = typer.Option("deepseek-ai/DeepSeek-V3", "--model", "-m"),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Skip already-enriched records"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show first 3 prompts without calling LLM"),
):
    """Generate teacher rationales via chutes-call batch."""
    if not input_file.exists():
        logger.error("Input file not found: {}", input_file)
        raise typer.Exit(1)

    # Load all records
    records = []
    with open(input_file) as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    logger.info("Loaded {} records from {}", len(records), input_file)

    # Load already-enriched records if resuming
    enriched_ids: set[str] = set()
    existing_enriched: list[dict] = []
    if resume and output_file.exists():
        with open(output_file) as f:
            for line in f:
                if line.strip():
                    rec = json.loads(line)
                    existing_enriched.append(rec)
                    # Use request hash as ID
                    req = rec.get("input", {}).get("request", "")
                    enriched_ids.add(hash(req))
        logger.info("Resuming: {} already enriched", len(enriched_ids))

    # Filter to unenriched records
    to_process = []
    for rec in records:
        req = rec.get("input", {}).get("request", "")
        if hash(req) not in enriched_ids:
            to_process.append(rec)
    logger.info("To process: {} records", len(to_process))

    if dry_run:
        for rec in to_process[:3]:
            req = rec["input"]["request"]
            skills = rec["output"]["skills"]
            prompt = build_user_prompt(req, skills)
            print(f"\n--- PROMPT ---\n{prompt}\n")
        return

    if not to_process:
        logger.info("All records already enriched")
        return

    # Process in batches
    all_enriched = list(existing_enriched)
    total_batches = (len(to_process) + batch_size - 1) // batch_size
    success = 0
    failed = 0

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(to_process))
        batch_records = to_process[start:end]

        # Build batch requests
        requests = []
        for rec in batch_records:
            req = rec["input"]["request"]
            skills = rec["output"]["skills"]
            requests.append({
                "messages": [
                    {"role": "system", "content": RATIONALE_SYSTEM_PROMPT},
                    {"role": "user", "content": build_user_prompt(req, skills)},
                ],
                "max_tokens": 300,
                "temperature": 0.3,
            })

        logger.info(
            "Batch {}/{}: {} records",
            batch_idx + 1, total_batches, len(batch_records),
        )

        try:
            payload = {
                "requests": requests,
                "concurrency": concurrency,
                "tenacious": True,
                "stream": False,
                "caller": "generate-rationales",
                "model": model,
            }
            resp = httpx.post(
                f"{CHUTES_CALL_URL}/batch",
                json=payload,
                timeout=httpx.Timeout(300.0, connect=10.0),
            )
            resp.raise_for_status()
            responses = resp.json()
        except Exception as exc:
            logger.error("Batch {} failed: {}", batch_idx + 1, exc)
            failed += len(batch_records)
            for rec in batch_records:
                all_enriched.append(rec)
            continue

        # Merge responses into records
        for i, (rec, r) in enumerate(zip(batch_records, responses)):
            content = r.get("content") or r.get("raw_content")
            if r.get("ok") and content:
                rec["output"]["teacher_rationale"] = content.strip()
                success += 1
            else:
                logger.warning(
                    "Record {} failed: {}",
                    start + i,
                    r.get("error", "unknown"),
                )
                failed += 1
            all_enriched.append(rec)

        # Write checkpoint after each batch
        with open(output_file, "w") as f:
            for rec in all_enriched:
                f.write(json.dumps(rec) + "\n")
        logger.info("Checkpoint: {}/{} enriched", success, success + failed)

        # Brief pause between batches
        if batch_idx < total_batches - 1:
            time.sleep(1)

    # Final stats
    rationale_lengths = []
    for rec in all_enriched:
        rat = rec.get("output", {}).get("teacher_rationale", "")
        if rat:
            rationale_lengths.append(len(rat))

    avg_len = sum(rationale_lengths) / len(rationale_lengths) if rationale_lengths else 0
    coverage = len(rationale_lengths) / len(all_enriched) * 100 if all_enriched else 0

    logger.info("\n=== Rationale Generation Complete ===")
    logger.info("Total records: {}", len(all_enriched))
    logger.info("Success: {}, Failed: {}", success, failed)
    logger.info("Coverage: {:.1f}%", coverage)
    logger.info("Avg rationale length: {:.0f} chars", avg_len)
    logger.info("Output: {}", output_file)


if __name__ == "__main__":
    app()
