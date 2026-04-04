#!/usr/bin/env python3
"""Task 8: Independent judge verification run.

Draws n=100 stratified sample from Task 6 evidence-case results,
sends each QRA to Gemini Flash 2.5 via /scillm with the validated
judge prompt, computes agreement rates with Wilson confidence intervals.

Usage:
    python judge_verification.py --evidence /tmp/sensai_v2_evidence_results.json
    python judge_verification.py --evidence /tmp/sensai_v2_evidence_results.json --n 50 --dry-run
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path
from typing import Any

import typer
from loguru import logger

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
JUDGE_PROMPT = SKILLS_DIR / "prompt-lab" / "prompts" / "qra_judge.txt"

app = typer.Typer(add_completion=False)


def wilson_ci(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for binomial proportion."""
    if total == 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z**2 / total
    center = (p + z**2 / (2 * total)) / denom
    spread = z * math.sqrt(p * (1 - p) / total + z**2 / (4 * total**2)) / denom
    return (max(0.0, center - spread), min(1.0, center + spread))


def stratified_sample(results: list[dict], n: int = 100) -> list[dict]:
    """Draw stratified sample: ~34 per verdict bucket."""
    buckets: dict[str, list[dict]] = {"satisfied": [], "inconclusive": [], "not_satisfied": []}

    for r in results:
        v = r.get("verdict_state", "")
        if v in buckets:
            buckets[v].append(r)

    per_bucket = n // 3
    remainder = n - per_bucket * 3
    sample = []

    for i, (verdict, items) in enumerate(buckets.items()):
        k = per_bucket + (1 if i < remainder else 0)
        k = min(k, len(items))
        sample.extend(random.sample(items, k))

    random.shuffle(sample)
    return sample


def load_judge_prompt() -> str:
    """Load the validated judge prompt."""
    if not JUDGE_PROMPT.exists():
        logger.error(f"Judge prompt not found: {JUDGE_PROMPT}")
        return ""

    content = JUDGE_PROMPT.read_text()

    # Extract system section
    if "[SYSTEM]" in content and "[USER]" in content:
        parts = content.split("[USER]")
        return parts[0].replace("[SYSTEM]", "").strip()
    return content.strip()


SCILLM_PROXY_URL = "http://localhost:4001/v1/chat/completions"
SCILLM_PROXY_KEY = "sk-dev-proxy-123"


def judge_qra(qra: dict, system_prompt: str, timeout: int = 60) -> dict[str, Any]:
    """Send a QRA to scillm proxy for independent judgment."""
    import httpx

    question = qra.get("question", "")
    reasoning = qra.get("reasoning", "")
    answer = qra.get("answer", "")

    user_msg = (
        f"Question: {question}\n\n"
        f"Reasoning: {reasoning}\n\n"
        f"Answer: {answer}\n\n"
        f"Respond with valid JSON only."
    )

    try:
        resp = httpx.post(
            SCILLM_PROXY_URL,
            headers={"Authorization": f"Bearer {SCILLM_PROXY_KEY}", "Content-Type": "application/json"},
            json={
                "model": "text",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                "max_tokens": 1024,
                "temperature": 0.0,
            },
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()

        # Extract JSON from response (may have markdown fences)
        if content.startswith("```"):
            lines = content.split("\n")
            json_lines = [l for l in lines if not l.startswith("```")]
            content = "\n".join(json_lines).strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"raw": content[:300], "error": "json_parse_failed"}
    except httpx.TimeoutException:
        return {"error": "timeout"}
    except Exception as e:
        return {"error": str(e)}


@app.command()
def verify(
    evidence: Path = typer.Option(..., "--evidence", "-e", help="Evidence results from Task 6"),
    n: int = typer.Option(100, "--n", help="Sample size"),
    output: Path = typer.Option("/tmp/sensai_v2_judge_verification.json", "--output", "-o"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    seed: int = typer.Option(42, "--seed"),
):
    """Run independent judge verification on stratified sample."""
    random.seed(seed)

    if not evidence.exists():
        logger.error(f"Evidence file not found: {evidence}")
        raise typer.Exit(1)

    data = json.loads(evidence.read_text())
    all_results = data.get("results", [])
    logger.info(f"Loaded {len(all_results)} evidence results")

    sample = stratified_sample(all_results, n)
    logger.info(f"Drew {len(sample)} stratified samples")

    system_prompt = load_judge_prompt()
    if not system_prompt:
        logger.error("Could not load judge prompt")
        raise typer.Exit(1)

    # Run judge
    agreements: dict[str, dict[str, int]] = {
        "satisfied": {"agree": 0, "disagree": 0, "error": 0},
        "inconclusive": {"agree": 0, "disagree": 0, "error": 0},
        "not_satisfied": {"agree": 0, "disagree": 0, "error": 0},
    }
    judge_results = []

    for i, item in enumerate(sample):
        evidence_verdict = item.get("verdict_state", "")

        if dry_run:
            judge_results.append({
                "id": item.get("id"),
                "evidence_verdict": evidence_verdict,
                "judge_verdict": "dry_run",
            })
            continue

        judge_out = judge_qra(item, system_prompt)
        judge_verdict = judge_out.get("judge_verdict", "error").lower()

        if "error" in judge_out and "judge_verdict" not in judge_out:
            judge_verdict = "error"

        # Map verdicts for agreement
        ev_normalized = evidence_verdict.lower().replace(" ", "_")
        jv_normalized = judge_verdict.lower().replace(" ", "_")

        if ev_normalized in agreements:
            if "error" in judge_out:
                agreements[ev_normalized]["error"] += 1
            elif ev_normalized == jv_normalized:
                agreements[ev_normalized]["agree"] += 1
            else:
                agreements[ev_normalized]["disagree"] += 1

        judge_results.append({
            "id": item.get("id"),
            "evidence_verdict": evidence_verdict,
            "judge_verdict": judge_verdict,
            "judge_confidence": judge_out.get("confidence", 0.0),
            "judge_rationale": judge_out.get("rationale", ""),
        })

        if (i + 1) % 20 == 0:
            logger.info(f"Progress: {i+1}/{len(sample)}")

    # Compute agreement rates with Wilson CIs
    report = {}
    for verdict, counts in agreements.items():
        total = counts["agree"] + counts["disagree"]
        rate = counts["agree"] / total if total > 0 else 0.0
        ci_low, ci_high = wilson_ci(counts["agree"], total)
        report[verdict] = {
            "agreement_rate": round(rate, 4),
            "wilson_ci_low": round(ci_low, 4),
            "wilson_ci_high": round(ci_high, 4),
            "agree": counts["agree"],
            "disagree": counts["disagree"],
            "errors": counts["error"],
            "total": total,
        }

    # Check thresholds
    sat_pass = report.get("satisfied", {}).get("agreement_rate", 0) >= 0.85
    notsat_pass = report.get("not_satisfied", {}).get("agreement_rate", 0) >= 0.75
    calibrated = sat_pass and notsat_pass

    output_data = {
        "sample_size": len(sample),
        "agreement_report": report,
        "thresholds": {
            "satisfied_threshold": 0.85,
            "satisfied_pass": sat_pass,
            "not_satisfied_threshold": 0.75,
            "not_satisfied_pass": notsat_pass,
            "calibrated": calibrated,
        },
        "judge_results": judge_results,
    }

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(output_data, indent=2))
    logger.info(f"Verification results written to {output}")

    # Print summary
    typer.echo(json.dumps({
        "agreement": report,
        "calibrated": calibrated,
    }, indent=2))

    if not calibrated:
        logger.warning("Pipeline NOT calibrated — recalibrate before proceeding to Task 9/10")


if __name__ == "__main__":
    app()
