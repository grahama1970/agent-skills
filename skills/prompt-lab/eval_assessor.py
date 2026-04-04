"""Evaluate QRA assessor prompts against hand-graded ground truth.

Usage:
    uv run python eval_assessor.py --prompt shadow_qra_assessor --runs 3
    uv run python eval_assessor.py --prompt shadow_qra_assessor_v3 --runs 3 --verbose
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import httpx
import typer
from loguru import logger

app = typer.Typer(add_completion=False)

PROMPT_DIR = Path(__file__).parent / "prompts"
GT_DIR = Path(__file__).parent / "ground_truth"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)

SCILLM_URL = os.environ.get("SCILLM_API_BASE", "http://localhost:4001") + "/v1/chat/completions"
SCILLM_KEY = os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")


def _call_scillm(system: str, user: str, model: str = "text", timeout: int = 30) -> str | None:
    """Send a single completion request to scillm."""
    try:
        resp = httpx.post(
            SCILLM_URL,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": 256,
                "temperature": 0.1,
            },
            headers={"Authorization": f"Bearer {SCILLM_KEY}"},
            timeout=timeout,
        )
        if resp.status_code != 200:
            logger.warning(f"HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"scillm call failed: {e}")
        return None


def _parse_grade(content: str) -> dict | None:
    """Parse JSON grade from LLM response."""
    if not content:
        return None
    # Strip markdown fences
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Try to find JSON in the response
        import re
        match = re.search(r'\{[^{}]+\}', text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None


@app.command()
def eval(
    prompt: str = typer.Option("shadow_qra_assessor", "--prompt", "-p"),
    model: str = typer.Option("text", "--model", "-m"),
    runs: int = typer.Option(3, "--runs", "-r", help="Runs per case for consistency"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Evaluate assessor prompt against ground truth."""
    # Load prompt
    prompt_path = PROMPT_DIR / f"{prompt}.txt"
    if not prompt_path.exists():
        typer.echo(f"Prompt not found: {prompt_path}")
        raise typer.Exit(1)
    system_prompt = prompt_path.read_text().strip()

    # Load ground truth
    gt_path = GT_DIR / "shadow_qra_assessor.json"
    if not gt_path.exists():
        typer.echo(f"Ground truth not found: {gt_path}")
        raise typer.Exit(1)
    gt = json.loads(gt_path.read_text())
    cases = gt["cases"]

    typer.echo(f"Prompt: {prompt} ({len(system_prompt)} chars)")
    typer.echo(f"Cases: {len(cases)}, Runs per case: {runs}")
    typer.echo(f"Model: {model}")
    typer.echo("=" * 60)

    results = []
    for case in cases:
        user_msg = f"Question: {case['question']}\nAnswer: {case['answer']}"
        if case.get("citations"):
            user_msg += f"\nCitations: {json.dumps(case['citations'])}"

        case_results = []
        for r in range(runs):
            raw = _call_scillm(system_prompt, user_msg, model=model)
            parsed = _parse_grade(raw)
            if parsed:
                case_results.append(parsed)
            else:
                case_results.append({"grade": "PARSE_ERROR", "raw": raw})
            time.sleep(0.5)  # Rate limit courtesy

        # Compute consistency
        grades = [cr.get("grade", "?") for cr in case_results]
        expected = case["expected_grade"]
        correct = sum(1 for g in grades if g == expected)
        consistent = len(set(grades)) == 1

        result = {
            "qra_key": case["qra_key"],
            "expected": expected,
            "grades": grades,
            "correct": correct,
            "runs": runs,
            "consistent": consistent,
            "details": case_results,
        }
        results.append(result)

        marker = "✓" if correct == runs else ("~" if correct > 0 else "✗")
        typer.echo(f"  {marker} {case['qra_key'][:20]:20s} expected={expected:8s} got={grades}  ({correct}/{runs})")
        if verbose:
            for cr in case_results:
                typer.echo(f"    fidelity={cr.get('fidelity','?'):8s} alignment={cr.get('alignment','?'):8s} action={cr.get('actionability','?'):8s} rationale={cr.get('rationale','?')[:80]}")

    # Summary
    typer.echo("=" * 60)
    total_correct = sum(r["correct"] for r in results)
    total_attempts = sum(r["runs"] for r in results)
    consistent_cases = sum(1 for r in results if r["consistent"])
    exact_match = sum(1 for r in results if r["correct"] == r["runs"])
    parse_errors = sum(1 for r in results for g in r["grades"] if g == "PARSE_ERROR")

    typer.echo(f"Accuracy:    {total_correct}/{total_attempts} = {total_correct/total_attempts*100:.1f}%")
    typer.echo(f"Exact match: {exact_match}/{len(cases)} cases (all {runs} runs correct)")
    typer.echo(f"Consistent:  {consistent_cases}/{len(cases)} cases (same grade all runs)")
    typer.echo(f"Parse errors: {parse_errors}")

    # Per-grade breakdown
    for grade in ["PASS", "PARTIAL", "FAIL"]:
        expected_n = sum(1 for c in cases if c["expected_grade"] == grade)
        correct_n = sum(1 for r, c in zip(results, cases) if c["expected_grade"] == grade and r["correct"] == r["runs"])
        typer.echo(f"  {grade}: {correct_n}/{expected_n} exact match")

    # Save results
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = RESULTS_DIR / f"assessor_{prompt}_{ts}.json"
    out_path.write_text(json.dumps({
        "prompt": prompt,
        "model": model,
        "runs": runs,
        "accuracy": total_correct / total_attempts,
        "exact_match": exact_match / len(cases),
        "consistency": consistent_cases / len(cases),
        "parse_errors": parse_errors,
        "results": results,
    }, indent=2))
    typer.echo(f"\nSaved: {out_path}")


if __name__ == "__main__":
    app()
