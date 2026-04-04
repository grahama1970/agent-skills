"""Generic JSON extraction evaluation for prompt-lab.

Compares LLM JSON output against expected JSON ground truth using
set-based precision/recall/F1 for array fields and exact match for
scalar fields.  Supports any structured extraction task.

Ground truth format:
{
  "name": "task_name",
  "description": "What this evaluates",
  "cases": [
    {
      "id": "case_1",
      "input": {"strings": "...", ...},
      "expected": {"field_a": ["val1", "val2"], "field_b": [...]},
      "notes": "optional"
    }
  ]
}
"""

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from rich.table import Table

from config import SKILL_DIR, ensure_dirs
from evaluation import load_models_config, save_eval_results
import httpx as _httpx
import os as _os
from model_memory import get_model_memory, record_eval_result
from pl_app import app, console


@dataclass
class JsonTestCase:
    """A test case with input context and expected JSON output."""

    id: str
    input: dict[str, Any]
    expected: dict[str, Any]
    notes: str = ""


@dataclass
class JsonFieldScore:
    """Precision/recall/F1 for a single array field."""

    field_name: str
    predicted: list[str]
    expected: list[str]

    @property
    def precision(self) -> float:
        if not self.predicted:
            return 1.0 if not self.expected else 0.0
        correct = len(set(self.predicted) & set(self.expected))
        return correct / len(self.predicted)

    @property
    def recall(self) -> float:
        if not self.expected:
            return 1.0
        correct = len(set(self.predicted) & set(self.expected))
        return correct / len(self.expected)

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        if p + r == 0:
            return 0.0
        return 2 * p * r / (p + r)


@dataclass
class JsonEvalResult:
    """Result of evaluating a single JSON extraction case."""

    case_id: str
    field_scores: list[JsonFieldScore] = field(default_factory=list)
    raw_output: str = ""
    parsed: bool = False
    latency_ms: float = 0.0
    error: str = ""

    @property
    def avg_f1(self) -> float:
        if not self.field_scores:
            return 0.0
        return sum(fs.f1 for fs in self.field_scores) / len(self.field_scores)

    @property
    def avg_precision(self) -> float:
        if not self.field_scores:
            return 0.0
        return sum(fs.precision for fs in self.field_scores) / len(self.field_scores)

    @property
    def avg_recall(self) -> float:
        if not self.field_scores:
            return 0.0
        return sum(fs.recall for fs in self.field_scores) / len(self.field_scores)


def _flatten_expected(value: Any) -> list[str]:
    """Flatten an expected value to a list of strings for set comparison."""
    if isinstance(value, list):
        result = []
        for item in value:
            if isinstance(item, str):
                result.append(item)
            elif isinstance(item, dict):
                # For objects like {"name": "X", "fields": [...]}, use the name
                if "name" in item:
                    result.append(str(item["name"]))
                if "enum_name" in item:
                    result.append(str(item["enum_name"]))
                    for s in item.get("states", []):
                        result.append(str(s))
            else:
                result.append(str(item))
        return result
    if isinstance(value, str):
        return [value]
    return []


def _flatten_predicted(value: Any) -> list[str]:
    """Flatten a predicted value to a list of strings for comparison."""
    return _flatten_expected(value)


def _score_case(
    predicted: dict[str, Any], expected: dict[str, Any]
) -> list[JsonFieldScore]:
    """Score predicted JSON against expected by comparing each array field."""
    scores = []
    for field_name, exp_value in expected.items():
        pred_value = predicted.get(field_name, [])
        exp_flat = _flatten_expected(exp_value)
        pred_flat = _flatten_predicted(pred_value)
        # Always score — empty-vs-empty is a correct prediction (F1=1.0)
        scores.append(JsonFieldScore(
            field_name=field_name,
            predicted=pred_flat,
            expected=exp_flat,
        ))
    return scores


def load_json_ground_truth(name: str) -> list[JsonTestCase]:
    """Load ground truth cases from a JSON file."""
    gt_path = SKILL_DIR / "ground_truth" / f"{name}.json"
    if not gt_path.exists():
        raise FileNotFoundError(f"Ground truth not found: {gt_path}")

    data = json.loads(gt_path.read_text())
    cases = []
    for case in data.get("cases", []):
        cases.append(JsonTestCase(
            id=case["id"],
            input=case["input"],
            expected=case["expected"],
            notes=case.get("notes", ""),
        ))
    return cases


async def _call_scillm(
    system: str, user: str, model_config: dict,
) -> tuple[str, float]:
    """Direct httpx call to /scillm — no parallel_acompletions dependency."""
    import time

    base = _os.environ.get("SCILLM_API_BASE", "http://localhost:4001")
    key = _os.environ.get("SCILLM_PROXY_KEY", "sk-dev-proxy-123")
    model_id = model_config.get("model", "text-gemini")

    t0 = time.time()
    async with _httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{base}/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": model_id,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "response_format": {"type": "json_object"},
                "max_tokens": 4096,
                "temperature": 0.0,
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    latency = (time.time() - t0) * 1000
    return content, latency


@app.command("eval-json")
def eval_json(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Prompt name"),
    model: str = typer.Option("gemini-flash", "--model", "-m", help="Model"),
    gt: str = typer.Option(..., "--gt", "-g", help="Ground truth name"),
    cases: int = typer.Option(0, "--cases", "-n", help="Number of cases (0=all)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Per-case details"),
    threshold: float = typer.Option(0.80, "--threshold", "-t", help="F1 threshold"),
):
    """Evaluate a JSON extraction prompt against ground truth.

    Compares LLM JSON output against expected JSON using set-based F1
    for each array field.  Works for any structured extraction task
    (ELF features, entity extraction, schema recovery, etc.).
    """
    ensure_dirs()
    models_config = load_models_config()

    if model not in models_config:
        console.print(f"[red]Model '{model}' not found. Available: {list(models_config.keys())}[/red]")
        raise typer.Exit(1)

    model_config = models_config[model]
    system_prompt, user_template = _load_json_prompt(prompt)
    test_cases = load_json_ground_truth(gt)

    if cases > 0:
        test_cases = test_cases[:cases]

    console.print(f"[bold]eval-json: prompt='{prompt}', model='{model}', gt='{gt}'[/bold]")
    console.print(f"Cases: {len(test_cases)}, Threshold: {threshold}")
    console.print()

    results: list[JsonEvalResult] = []

    async def run():
        for tc in test_cases:
            user_msg = user_template
            for key, val in tc.input.items():
                user_msg = user_msg.replace(f"{{{key}}}", str(val))

            try:
                raw, latency = await _call_scillm(system_prompt, user_msg, model_config)
            except Exception as exc:
                logger.warning(f"LLM call failed for {tc.id}: {exc}")
                results.append(JsonEvalResult(
                    case_id=tc.id, error=str(exc),
                ))
                continue

            result = JsonEvalResult(
                case_id=tc.id, raw_output=raw or "", latency_ms=latency,
            )

            try:
                # Try to parse JSON from the response
                parsed = _extract_json(raw)
                if parsed:
                    result.parsed = True
                    result.field_scores = _score_case(parsed, tc.expected)
                else:
                    result.error = "No valid JSON found in response"
            except Exception as exc:
                result.error = str(exc)

            results.append(result)

            if verbose:
                icon = "[green]PASS[/green]" if result.avg_f1 >= threshold else "[red]FAIL[/red]"
                console.print(f"  {icon} {tc.id}: F1={result.avg_f1:.3f} ({result.latency_ms:.0f}ms)")
                if result.error:
                    console.print(f"    [red]Error: {result.error}[/red]")
                for fs in result.field_scores:
                    console.print(
                        f"    {fs.field_name}: P={fs.precision:.2f} R={fs.recall:.2f} F1={fs.f1:.2f} "
                        f"({len(set(fs.predicted) & set(fs.expected))}/{len(fs.expected)} expected)"
                    )

    asyncio.run(run())

    # Summary
    avg_f1 = sum(r.avg_f1 for r in results) / len(results) if results else 0.0
    avg_precision = sum(r.avg_precision for r in results) / len(results) if results else 0.0
    avg_recall = sum(r.avg_recall for r in results) / len(results) if results else 0.0
    parse_rate = sum(1 for r in results if r.parsed) / len(results) if results else 0.0

    console.print()
    table = Table(title="eval-json Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Avg F1", f"{avg_f1:.3f}")
    table.add_row("Avg Precision", f"{avg_precision:.3f}")
    table.add_row("Avg Recall", f"{avg_recall:.3f}")
    table.add_row("Parse Rate", f"{parse_rate:.1%}")
    table.add_row("Avg Latency", f"{sum(r.latency_ms for r in results) / len(results):.0f}ms" if results else "0ms")
    table.add_row("Cases", str(len(results)))
    console.print(table)

    passed = avg_f1 >= threshold and parse_rate >= 0.8
    if passed:
        console.print(f"\n[green]QUALITY GATE PASSED (F1={avg_f1:.3f} >= {threshold})[/green]")
    else:
        console.print(f"\n[red]QUALITY GATE FAILED[/red]")
        if avg_f1 < threshold:
            console.print(f"  F1 {avg_f1:.3f} < {threshold}")
        if parse_rate < 0.8:
            console.print(f"  Parse rate {parse_rate:.1%} < 80%")

    # Save results
    results_data = {
        "prompt": prompt,
        "model": model,
        "ground_truth": gt,
        "timestamp": datetime.now().isoformat(),
        "avg_f1": avg_f1,
        "avg_precision": avg_precision,
        "avg_recall": avg_recall,
        "parse_rate": parse_rate,
        "passed": passed,
        "cases": [
            {
                "id": r.case_id,
                "f1": r.avg_f1,
                "parsed": r.parsed,
                "error": r.error,
                "field_scores": [
                    {"field": fs.field_name, "f1": fs.f1, "precision": fs.precision, "recall": fs.recall,
                     "predicted_count": len(fs.predicted), "expected_count": len(fs.expected)}
                    for fs in r.field_scores
                ],
            }
            for r in results
        ],
    }
    out_dir = SKILL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"json_{gt}_{model}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out_file.write_text(json.dumps(results_data, indent=2))
    console.print(f"\nResults: {out_file}")

    # Model memory
    model_mem = get_model_memory()
    if model_mem.enabled:
        record_eval_result(
            memory=model_mem,
            model_alias=model,
            model_id=model_config.get("model", model),
            prompt_type=f"json:{gt}",
            f1_score=avg_f1,
            latency_ms=sum(r.latency_ms for r in results) / len(results) if results else 0,
            observation=f"F1={avg_f1:.3f}, parse={parse_rate:.1%} - {'PASSED' if passed else 'FAILED'}",
            details=f"Prompt: {prompt}, GT: {gt}, Cases: {len(results)}",
        )

    if not passed:
        raise typer.Exit(1)


def _load_json_prompt(name: str) -> tuple[str, str]:
    """Load a prompt file and split into system + user template."""
    prompt_path = SKILL_DIR / "prompts" / f"{name}.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")

    content = prompt_path.read_text()
    # Strip leading comment lines (# prompt-lab-hash, # Version, etc.)
    lines = content.split("\n")
    while lines and lines[0].startswith("#"):
        lines.pop(0)
    content = "\n".join(lines)

    # Handle [SYSTEM]/[USER] format (same as evaluation.load_prompt)
    if "[SYSTEM]" in content and "[USER]" in content:
        parts = content.split("[USER]")
        system = parts[0].replace("[SYSTEM]", "").strip()
        user = parts[1].strip()
        return system, user
    # Handle --- separator
    if "\n---\n" in content:
        parts = content.split("\n---\n", 1)
        return parts[0].strip(), parts[1].strip()
    # Otherwise entire content is system prompt, user is the input
    return content.strip(), "{strings}"


def _extract_json(text: str) -> dict | None:
    """Extract JSON object from LLM response text."""
    # Try direct parse
    text = text.strip()
    if text.startswith("{"):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

    # Try extracting from markdown code block
    import re
    m = re.search(r'```(?:json)?\s*\n(.*?)\n```', text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { ... } block
    start = text.find("{")
    if start >= 0:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
    return None
