"""Evaluate NLG synthesis prompt against ground truth test cases.

Tests whether the prompt correctly:
1. Synthesizes relevant QRAs into natural language
2. Rejects fabricated frameworks (Orion Protocol etc.)
3. Detects QRA-question mismatches
4. Handles ambiguous and empty-result scenarios
"""
import json
import sys
import time
from pathlib import Path
from typing import Optional

import typer

SKILL_DIR = Path(__file__).parent

# Ensure scillm is importable
_scillm_path = str(SKILL_DIR.parent / "scillm")
if _scillm_path not in sys.path:
    sys.path.insert(0, _scillm_path)

_common_path = str(SKILL_DIR.parent / "common")
if _common_path not in sys.path:
    sys.path.insert(0, _common_path)

from pl_app import app


def _load_ground_truth() -> dict:
    gt_path = SKILL_DIR / "ground_truth" / "nlg_synthesis.json"
    return json.loads(gt_path.read_text())


def _load_prompt(name: str) -> str:
    prompt_path = SKILL_DIR / "prompts" / f"{name}.txt"
    return prompt_path.read_text()


def _format_prompt(template: str, tc_input: dict) -> str:
    """Fill prompt template with test case input via safe substitution."""
    qra_results = tc_input.get("qra_results", [])
    qra_text = json.dumps(qra_results, indent=2) if qra_results else "[]"
    # Use replace instead of .format() to avoid {{/}} conflicts in JSON examples
    result = template
    result = result.replace("{question}", tc_input["question"])
    result = result.replace("{target_control}", tc_input.get("target_control") or "N/A")
    result = result.replace("{qra_results}", qra_text)
    result = result.replace("{qra_count}", str(len(qra_results)))
    return result


def _evaluate_response(response: dict, expected: dict, tc_id: str) -> dict:
    """Score a single response against expected outcomes."""
    checks = {}
    passed = 0
    total = 0

    # Check 1: should_answer alignment
    total += 1
    resp_relevant = response.get("relevant", True)
    if resp_relevant == expected["should_answer"]:
        checks["relevance_gate"] = "PASS"
        passed += 1
    else:
        checks["relevance_gate"] = f"FAIL (got relevant={resp_relevant}, expected should_answer={expected['should_answer']})"

    # Check 2: cited controls match
    total += 1
    cited = set(response.get("cited_controls", []))
    expected_cited = set(expected.get("should_cite_controls", []))
    if expected_cited:
        overlap = cited & expected_cited
        if overlap == expected_cited:
            checks["citations"] = "PASS"
            passed += 1
        else:
            missing = expected_cited - cited
            checks["citations"] = f"FAIL (missing: {missing}, cited: {cited})"
    else:
        # Expected no citations
        if not cited or not resp_relevant:
            checks["citations"] = "PASS"
            passed += 1
        else:
            checks["citations"] = f"FAIL (should cite nothing, got: {cited})"

    # Check 3: rejection of fabricated/irrelevant content
    total += 1
    should_reject = expected.get("should_reject", [])
    resp_text = response.get("response", "").lower()
    if should_reject:
        # Response should NOT present these as valid answers
        # Check if response text explicitly rejects or at least doesn't endorse
        rejection_indicators = [
            "don't have information",
            "not recognized",
            "don't recognize",
            "not a standard",
            "no information",
            "not available",
            "cannot find",
            "no coverage",
            "irrelevant",
            "not relevant",
            "mismatch",
        ]
        has_rejection = any(ind in resp_text for ind in rejection_indicators)
        if has_rejection or not resp_relevant:
            checks["rejection"] = "PASS"
            passed += 1
        else:
            checks["rejection"] = f"FAIL (should reject {should_reject} but response appears to endorse)"
    else:
        checks["rejection"] = "PASS (no rejection needed)"
        passed += 1

    # Check 4: no hallucination (confidence should be low when data is bad)
    total += 1
    confidence = response.get("confidence", 0.5)
    if not expected["should_answer"] and confidence > 0.7:
        checks["hallucination_guard"] = f"FAIL (confidence {confidence} too high for should_answer=false)"
    else:
        checks["hallucination_guard"] = "PASS"
        passed += 1

    score = passed / total if total > 0 else 0
    return {
        "tc_id": tc_id,
        "score": score,
        "passed": passed,
        "total": total,
        "checks": checks,
        "expected_grade": expected.get("grade", "?"),
        "response_relevant": resp_relevant,
        "response_confidence": confidence,
    }


@app.command("eval-nlg")
def eval_nlg(
    prompt: str = typer.Option("nlg_synthesis_v1", "--prompt", "-p", help="Prompt name"),
    model: str = typer.Option("deepseek-ai/DeepSeek-V3-0324", "--model", "-m", help="Model to test"),
    cases: Optional[int] = typer.Option(None, "--cases", "-c", help="Limit test cases"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Evaluate NLG synthesis prompt against ground truth."""
    from batch import quick_completion

    gt = _load_ground_truth()
    template = _load_prompt(prompt)
    test_cases = gt["test_cases"]
    if cases:
        test_cases = test_cases[:cases]

    typer.echo(f"Evaluating prompt '{prompt}' with model '{model}' on {len(test_cases)} cases\n")

    results = []
    total_score = 0

    for i, tc in enumerate(test_cases):
        tc_id = tc["id"]
        tc_name = tc["name"]
        typer.echo(f"[{i+1}/{len(test_cases)}] {tc_name}...")

        filled_prompt = _format_prompt(template, tc["input"])

        t0 = time.time()
        try:
            raw = quick_completion(
                prompt=filled_prompt,
                model=model,
                system="You are Brandon Bailey, Principal Director of Cyber Assessments at The Aerospace Corporation. Respond ONLY with valid JSON.",
                json_mode=True,
                max_tokens=1024,
                temperature=0.2,
                timeout=60,
            )
            elapsed = time.time() - t0

            response = json.loads(raw)
            eval_result = _evaluate_response(response, tc["expected"], tc_id)
            eval_result["latency_s"] = round(elapsed, 1)
            eval_result["model"] = model
            results.append(eval_result)
            total_score += eval_result["score"]

            status = "PASS" if eval_result["score"] >= 0.75 else "FAIL"
            typer.echo(f"  {status} — score={eval_result['score']:.0%} ({eval_result['passed']}/{eval_result['total']}) [{elapsed:.1f}s]")

            if verbose:
                typer.echo(f"  Response: {response.get('response', '')[:120]}...")
                typer.echo(f"  Relevant: {response.get('relevant')} | Confidence: {response.get('confidence')}")
                typer.echo(f"  Cited: {response.get('cited_controls', [])}")
                for check_name, check_result in eval_result["checks"].items():
                    typer.echo(f"    {check_name}: {check_result}")
                typer.echo()

        except Exception as e:
            elapsed = time.time() - t0
            typer.echo(f"  ERROR — {e} [{elapsed:.1f}s]")
            results.append({
                "tc_id": tc_id,
                "score": 0,
                "passed": 0,
                "total": 4,
                "checks": {"error": str(e)},
                "latency_s": round(elapsed, 1),
                "model": model,
            })

    # Summary
    avg_score = total_score / len(results) if results else 0
    pass_count = sum(1 for r in results if r["score"] >= 0.75)

    typer.echo(f"\n{'='*60}")
    typer.echo(f"RESULTS: {prompt} @ {model}")
    typer.echo(f"{'='*60}")
    typer.echo(f"Cases:  {len(results)}")
    typer.echo(f"Passed: {pass_count}/{len(results)} ({pass_count/len(results):.0%})")
    typer.echo(f"Avg Score: {avg_score:.0%}")
    typer.echo()

    # Per-check summary
    check_names = ["relevance_gate", "citations", "rejection", "hallucination_guard"]
    for cn in check_names:
        pass_n = sum(1 for r in results if r.get("checks", {}).get(cn, "").startswith("PASS"))
        typer.echo(f"  {cn}: {pass_n}/{len(results)} pass")

    # Save results
    out_path = SKILL_DIR / "results" / f"nlg_eval_{prompt}_{model.split('/')[-1]}_{int(time.time())}.json"
    out_path.parent.mkdir(exist_ok=True)
    out_path.write_text(json.dumps({
        "prompt": prompt,
        "model": model,
        "avg_score": avg_score,
        "pass_rate": pass_count / len(results) if results else 0,
        "cases": results,
    }, indent=2))
    typer.echo(f"\nSaved: {out_path}")

    # Quality gate
    if avg_score < 0.75:
        typer.echo(f"\nQUALITY GATE FAILED: avg_score {avg_score:.0%} < 75%")
        raise typer.Exit(1)
    else:
        typer.echo(f"\nQUALITY GATE PASSED: avg_score {avg_score:.0%} >= 75%")
