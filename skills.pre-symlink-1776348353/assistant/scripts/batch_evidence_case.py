#!/usr/bin/env python3
"""Task 6: Batch evidence-case validation of stratified sample.

Composes with /create-evidence-case via subprocess (skill-to-skill pattern).
Reads JSONL sample from Task 5, runs each QRA through evidence-case pipeline,
records per-QRA verdicts.

Usage:
    python batch_evidence_case.py --input /tmp/sensai_v2_sample_500.jsonl
    python batch_evidence_case.py --input /tmp/sensai_v2_sample_500.jsonl --dry-run
"""

from __future__ import annotations
import os

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import typer
from loguru import logger

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
EVIDENCE_CASE_RUN = SKILLS_DIR / "create-evidence-case" / "run.sh"

app = typer.Typer(add_completion=False)


def run_evidence_case(qra: dict[str, Any], timeout: int = 120) -> dict[str, Any]:
    """Run a single QRA through /create-evidence-case via subprocess."""
    if not EVIDENCE_CASE_RUN.exists():
        return {"error": "create-evidence-case run.sh not found"}

    # Build a focused claim from the QRA answer (the assertion to verify).
    # The answer IS the claim — the question provides context but the answer
    # is what /create-evidence-case needs to structurally validate.
    answer = qra.get("answer", "")
    question = qra.get("question", "")

    # Use the first 2 sentences of the answer as the claim (focused assertion).
    # Long concatenated Q+A produces vague claims that fail gate 2.
    sentences = [s.strip() for s in answer.replace("\n", " ").split(".") if s.strip()]
    claim = ". ".join(sentences[:2]) + "." if sentences else answer
    if len(claim) < 30 and question:
        # Answer too short — prepend question for context
        claim = f"{question} — {claim}"
    if len(claim) > 500:
        claim = claim[:500]

    try:
        result = subprocess.run(
            [str(EVIDENCE_CASE_RUN), "create", claim, "--json", "-q"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        if result.returncode != 0:
            logger.debug(f"evidence-case exited {result.returncode}: {result.stderr[:200]}")
            return {"error": f"exit {result.returncode}", "stderr": result.stderr[:200]}

        try:
            return json.loads(result.stdout.strip())
        except json.JSONDecodeError:
            return {"raw_output": result.stdout[:500], "error": "json_parse_failed"}

    except subprocess.TimeoutExpired:
        return {"error": f"timeout ({timeout}s)"}
    except Exception as e:
        return {"error": str(e)}


@app.command()
def batch(
    input_file: Path = typer.Option(..., "--input", "-i", help="JSONL sample from Task 5"),
    output_file: Path = typer.Option(
        "/tmp/sensai_v2_evidence_results.json", "--output", "-o",
    ),
    dry_run: bool = typer.Option(False, "--dry-run"),
    timeout: int = typer.Option(120, "--timeout", help="Per-QRA timeout in seconds"),
    limit: int = typer.Option(0, "--limit", help="Process only first N QRAs (0=all)"),
):
    """Run evidence-case validation on stratified QRA sample."""
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        raise typer.Exit(1)

    # Load QRAs
    qras = []
    with open(input_file) as f:
        for line in f:
            line = line.strip()
            if line:
                qras.append(json.loads(line))

    if limit > 0:
        qras = qras[:limit]

    logger.info(f"Processing {len(qras)} QRAs (dry_run={dry_run})")

    results = []
    verdicts = {"satisfied": 0, "inconclusive": 0, "not_satisfied": 0, "error": 0}
    ctrl_to_ctrl = 0

    for i, qra in enumerate(qras):
        qra_id = qra.get("_key", qra.get("id", f"qra_{i}"))

        if dry_run:
            results.append({"id": qra_id, "verdict_state": "dry_run"})
            continue

        start = time.time()
        ec_result = run_evidence_case(qra, timeout=timeout)
        latency_ms = (time.time() - start) * 1000

        verdict = ec_result.get("verdict_state", "error")
        if "error" in ec_result and "verdict_state" not in ec_result:
            verdict = "error"

        verdicts[verdict] = verdicts.get(verdict, 0) + 1

        # Check if flagged as control-to-control
        is_ctrl_to_ctrl = qra.get("ctrl_to_ctrl_flag", False)
        if is_ctrl_to_ctrl:
            ctrl_to_ctrl += 1

        results.append({
            "id": qra_id,
            "verdict_state": verdict,
            "grade": ec_result.get("grade", ""),
            "gates_passed": ec_result.get("gates_passed", 0),
            "gates_total": ec_result.get("gates_total", 0),
            "stopped_at_gate": ec_result.get("stopped_at_gate", ""),
            "latency_ms": round(latency_ms, 1),
            "ctrl_to_ctrl": is_ctrl_to_ctrl,
            "tactical_tags": qra.get("tactical_tags", []),
        })

        if (i + 1) % 50 == 0:
            logger.info(f"Progress: {i+1}/{len(qras)} — verdicts so far: {verdicts}")

    # Write results
    output = {
        "total": len(results),
        "verdicts": verdicts,
        "ctrl_to_ctrl_count": ctrl_to_ctrl,
        "results": results,
    }

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(output, indent=2))
    logger.info(f"Results written to {output_file}")
    logger.info(f"Verdicts: {verdicts}")
    logger.info(f"Control-to-control QRAs: {ctrl_to_ctrl}")

    typer.echo(json.dumps({"verdicts": verdicts, "total": len(results)}, indent=2))


if __name__ == "__main__":
    app()
