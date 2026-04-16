#!/usr/bin/env python3
"""Evaluate chain-rationale prompt against held-out test cases via chutes-call /batch.

Metrics:
  1. Format validity: valid JSON with 'skills' array and 'rationale_prompt' string
  2. Accuracy: Jaccard similarity between predicted and ground truth skills
  3. Rationale grounding: rationale mentions at least one skill name

Usage:
    uv run python scripts/eval_chain_rationale.py \
        --prompt prompts/chain_rationale_v1.txt \
        --ground-truth ground_truth/chain_rationale.json \
        --held-out ../../skill-lab/state/training/held_out.jsonl
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx
import typer
from loguru import logger

app = typer.Typer(add_completion=False)

CHUTES_CALL_URL = "http://localhost:8630"


def load_prompt(path: Path) -> tuple[str, str]:
    """Parse [SYSTEM] / [USER] prompt file into system_prompt, user_template."""
    text = path.read_text()
    parts = text.split("[USER]")
    system = parts[0].replace("[SYSTEM]", "").strip()
    user_template = parts[1].strip() if len(parts) > 1 else "{description}"
    return system, user_template


def load_held_out(path: Path) -> list[dict]:
    """Load held-out JSONL records."""
    records = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def load_ground_truth_json(path: Path) -> list[dict]:
    """Load ground truth JSON (prompt-lab format)."""
    data = json.loads(path.read_text())
    return data.get("cases", [])


def check_format_validity(content: str) -> tuple[bool, dict | None]:
    """Check if content is valid JSON with required chain-rationale fields."""
    try:
        parsed = json.loads(content.strip())
    except (json.JSONDecodeError, TypeError):
        return False, None

    if not isinstance(parsed, dict):
        return False, None

    skills = parsed.get("skills")
    if not isinstance(skills, list) or len(skills) == 0:
        return False, None

    if not all(isinstance(s, str) for s in skills):
        return False, None

    rationale = parsed.get("rationale_prompt")
    if not isinstance(rationale, str) or len(rationale) < 5:
        return False, None

    return True, parsed


def jaccard_similarity(pred: list[str], expected: list[str]) -> float:
    """Jaccard similarity between predicted and expected skill lists."""
    pred_set = set(s.lower().strip() for s in pred)
    exp_set = set(s.lower().strip() for s in expected)
    if not pred_set and not exp_set:
        return 1.0
    if not pred_set or not exp_set:
        return 0.0
    return len(pred_set & exp_set) / len(pred_set | exp_set)


def check_rationale_grounding(parsed: dict) -> bool:
    """Check if rationale mentions at least one skill from the skills array."""
    rationale = parsed.get("rationale_prompt", "").lower()
    skills = parsed.get("skills", [])
    return any(s.lower() in rationale for s in skills)


@app.command()
def evaluate(
    prompt: Path = typer.Option(
        ..., "--prompt", "-p",
        help="Prompt file (e.g. prompts/chain_rationale_v1.txt)",
    ),
    held_out: Path = typer.Option(
        ..., "--held-out", "-h",
        help="Held-out JSONL file",
    ),
    concurrency: int = typer.Option(5, "--concurrency", "-c"),
    model: str = typer.Option("deepseek-ai/DeepSeek-V3", "--model", "-m"),
    max_cases: int = typer.Option(0, "--max-cases", "-n", help="0 = all"),
):
    """Run chain-rationale prompt evaluation via chutes-call /batch."""
    # Load prompt
    system_prompt, user_template = load_prompt(prompt)
    logger.info(f"Loaded prompt: {prompt.name}")
    logger.info(f"System prompt: {len(system_prompt)} chars")

    # Load held-out cases
    cases = load_held_out(held_out)
    if max_cases > 0:
        cases = cases[:max_cases]
    logger.info(f"Loaded {len(cases)} held-out cases")

    # Build batch request
    requests = []
    for case in cases:
        request_text = case["input"]["request"]
        # Truncate very long requests for the eval (the model gets 512 tokens max)
        if len(request_text) > 500:
            request_text = request_text[:500]

        user_msg = user_template.replace("{description}", request_text)
        requests.append({
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
            "model": model,
            "temperature": 0.3,
            "max_tokens": 300,
        })

    # Call chutes-call /batch
    logger.info(f"Sending {len(requests)} requests to chutes-call /batch (concurrency={concurrency})")
    t0 = time.time()

    with httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        resp = client.post(
            f"{CHUTES_CALL_URL}/batch",
            json={
                "requests": requests,
                "concurrency": concurrency,
                "stream": False,
                "tenacious": True,
                "caller": "prompt-lab-chain-rationale-eval",
            },
        )
        resp.raise_for_status()
        batch_results = resp.json()

    elapsed = time.time() - t0
    logger.info(f"Batch completed in {elapsed:.1f}s")

    # Score results
    format_valid = 0
    total_jaccard = 0.0
    rationale_grounded = 0
    any_overlap_count = 0
    errors = 0
    per_case = []

    for i, result in enumerate(batch_results):
        case = cases[i]
        expected_skills = case["output"]["skills"]
        content = result.get("content", "")
        ok = result.get("ok", False)

        if not ok:
            errors += 1
            per_case.append({
                "id": i, "format_valid": False, "jaccard": 0.0,
                "grounded": False, "any_overlap": False,
                "error": result.get("error", "unknown"),
            })
            continue

        valid, parsed = check_format_validity(content)

        if valid and parsed:
            format_valid += 1
            pred_skills = parsed.get("skills", [])
            jacc = jaccard_similarity(pred_skills, expected_skills)
            total_jaccard += jacc
            # Softer metric: any overlap at all
            pred_set = set(s.lower().strip() for s in pred_skills)
            exp_set = set(s.lower().strip() for s in expected_skills)
            has_overlap = len(pred_set & exp_set) > 0
            if has_overlap:
                any_overlap_count += 1
            grounded = check_rationale_grounding(parsed)
            if grounded:
                rationale_grounded += 1
            per_case.append({
                "id": i, "format_valid": True, "jaccard": round(jacc, 3),
                "grounded": grounded, "any_overlap": has_overlap,
                "pred_skills": pred_skills,
                "expected_skills": expected_skills,
            })
        else:
            per_case.append({
                "id": i, "format_valid": False, "jaccard": 0.0,
                "grounded": False, "any_overlap": False, "raw": content[:200],
            })

    n = len(cases)
    n_valid = n - errors  # cases that got responses

    # Compute metrics
    format_rate = format_valid / n if n > 0 else 0
    avg_jaccard = total_jaccard / format_valid if format_valid > 0 else 0
    overlap_rate = any_overlap_count / format_valid if format_valid > 0 else 0
    grounding_rate = rationale_grounded / format_valid if format_valid > 0 else 0

    # Combined score: format 0.3, overlap 0.2, jaccard 0.3, grounding 0.2
    # Using overlap_rate instead of pure jaccard gives credit for noisy ground truth
    combined = 0.3 * format_rate + 0.2 * overlap_rate + 0.3 * avg_jaccard + 0.2 * grounding_rate

    # Print report
    print("\n" + "=" * 60)
    print("CHAIN-RATIONALE PROMPT EVALUATION")
    print("=" * 60)
    print(f"Prompt:          {prompt.name}")
    print(f"Model:           {model}")
    print(f"Cases:           {n}")
    print(f"Errors:          {errors}")
    print(f"Elapsed:         {elapsed:.1f}s")
    print("-" * 60)
    print(f"Format validity: {format_valid}/{n} ({format_rate:.1%})")
    print(f"Any overlap:     {any_overlap_count}/{format_valid} ({overlap_rate:.1%})")
    print(f"Avg Jaccard:     {avg_jaccard:.3f}")
    print(f"Grounding rate:  {rationale_grounded}/{format_valid} ({grounding_rate:.1%})")
    print(f"Combined score:  {combined:.3f}")
    print("-" * 60)

    # Quality gates
    gates_pass = True
    if format_rate < 0.90:
        print(f"FAIL: Format validity {format_rate:.1%} < 90%")
        gates_pass = False
    else:
        print(f"PASS: Format validity {format_rate:.1%} >= 90%")

    if combined < 0.75:
        print(f"FAIL: Combined score {combined:.3f} < 0.75")
        gates_pass = False
    else:
        print(f"PASS: Combined score {combined:.3f} >= 0.75")

    print("=" * 60)

    # Save detailed results
    output_path = prompt.parent.parent / "eval_results" / f"{prompt.stem}_eval.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps({
        "prompt": prompt.name,
        "model": model,
        "n_cases": n,
        "metrics": {
            "format_validity": round(format_rate, 4),
            "overlap_rate": round(overlap_rate, 4),
            "avg_jaccard": round(avg_jaccard, 4),
            "grounding_rate": round(grounding_rate, 4),
            "combined_score": round(combined, 4),
        },
        "gates_pass": gates_pass,
        "errors": errors,
        "elapsed_s": round(elapsed, 1),
        "per_case": per_case,
    }, indent=2))
    logger.info(f"Results saved to {output_path}")

    # Show worst cases
    failures = [c for c in per_case if not c.get("format_valid")]
    if failures:
        print(f"\nFormat failures ({len(failures)}):")
        for f in failures[:5]:
            raw = f.get("raw", f.get("error", ""))
            print(f"  Case {f['id']}: {raw[:100]}")

    low_jaccard = sorted(
        [c for c in per_case if c.get("format_valid")],
        key=lambda x: x["jaccard"],
    )[:5]
    if low_jaccard:
        print(f"\nLowest Jaccard cases:")
        for c in low_jaccard:
            print(f"  Case {c['id']}: J={c['jaccard']:.3f} pred={c.get('pred_skills', [])} exp={c.get('expected_skills', [])}")

    raise typer.Exit(0 if gates_pass else 1)


if __name__ == "__main__":
    app()
