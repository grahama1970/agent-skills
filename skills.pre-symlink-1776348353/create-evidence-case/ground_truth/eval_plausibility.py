#!/usr/bin/env python3
"""Evaluate plausibility prompt against 36 ground-truth fixtures.

Runs each fixture through available LLM backends, compares against
expected_answerable labels, and reports accuracy per backend.

Usage:
    uv run python eval_plausibility.py [--backends chutes,scillm] [--verbose]
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from dotenv import load_dotenv, find_dotenv

load_dotenv(find_dotenv(usecwd=True), override=False)

# Add parent to path for plausibility imports
SKILL_DIR = Path(__file__).resolve().parent.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from plausibility import _build_prompt, _parse_llm_response, _call_scillm

console = Console(stderr=True)
app = typer.Typer(no_args_is_help=True)

FIXTURES_PATH = Path(__file__).parent / "plausibility_answerability.json"
WINNER_PATH = Path(__file__).parent / "prompt_lab_winner.json"


def _load_fixtures() -> list[dict]:
    return json.loads(FIXTURES_PATH.read_text())


def _build_backends() -> list[tuple[str, str, str, str]]:
    """Build list of (name, url, model, key) backends to test.

    All backends route through scillm proxy (localhost:4001).
    Chutes models use the chutes-call gateway for direct access.
    """
    backends = []
    scillm_base = os.getenv("SCILLM_API_BASE", "http://localhost:4001")
    chutes_url = os.getenv("CHUTES_CALL_URL", "http://localhost:8630")

    # scillm models (direct provider calls via proxy)
    backends.append(("gemini-flash", f"{scillm_base}/v1/chat/completions", "gemini/gemini-2.5-flash", "sk-dev-proxy-123"))
    backends.append(("text-cascade", f"{scillm_base}/v1/chat/completions", "text", "sk-dev-proxy-123"))

    # Chutes models via chutes-call gateway
    backends.append(("deepseek-v3", f"{chutes_url}/chat", "deepseek-ai/DeepSeek-V3", "unused"))
    backends.append(("qwen3-235b", f"{chutes_url}/chat", "Qwen/Qwen3-235B-A22B-Thinking-2507", "unused"))
    backends.append(("qwen3-32b", f"{chutes_url}/chat", "Qwen/Qwen3-32B", "unused"))

    return backends


def _eval_fixture_against_backend(
    fixture: dict,
    backend_name: str,
    url: str,
    model: str,
    key: str,
    prompt_text: str | None = None,
) -> dict:
    """Evaluate a single fixture against a single backend.

    Returns dict with: id, expected, predicted, correct, reason, latency_ms, error
    """
    # Build prompt from fixture data
    question = fixture["question"]
    unmatched = fixture.get("unmatched_terms", [])
    resolved = fixture.get("resolved_terms", [])
    resolved_count = fixture.get("resolved_count", len(resolved))
    qra_count = fixture.get("qra_count", 0)

    # Build not_in_corpus and resolution_map from fixture data
    not_in_corpus = [{"term": t, "type": "text_fragment"} for t in unmatched]
    resolution_map = {}
    for t in resolved:
        # Parse "term (name)" format
        if " (" in t:
            term = t.split(" (")[0]
            name = t.split(" (")[1].rstrip(")")
        else:
            term = t
            name = t
        resolution_map[term] = {"exists": True, "name": name, "qra_count": qra_count}

    if prompt_text:
        # Use custom prompt template
        prompt = prompt_text.format(
            question=question,
            resolved_terms=", ".join(resolved) or "none",
            resolved_count=resolved_count,
            unresolved_terms=", ".join(unmatched) or "none",
            unresolved_count=len(unmatched),
        )
    else:
        prompt, _, _ = _build_prompt(question, not_in_corpus, resolution_map)

    expected = fixture["expected_answerable"]
    t0 = time.time()

    try:
        scillm_base = os.getenv("SCILLM_API_BASE", "http://localhost:4001")
        if url.startswith(scillm_base):
            text = _call_scillm(prompt, model=model)
        else:
            # Non-scillm backend (chutes-call gateway etc)
            import urllib.request
            body = json.dumps({
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            }).encode()
            req = urllib.request.Request(url, data=body, headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            })
            with urllib.request.urlopen(req, timeout=60) as http_resp:
                data = json.loads(http_resp.read().decode())
            if "choices" in data:
                text = data["choices"][0].get("message", {}).get("content", "")
            else:
                text = data.get("content", "")

        result = _parse_llm_response(text, backend_name, unmatched, resolved)
        predicted = result.get("answerable", result.get("plausible"))
        latency = (time.time() - t0) * 1000

        return {
            "id": fixture["id"],
            "expected": expected,
            "predicted": predicted,
            "correct": predicted == expected,
            "reason": result.get("reason", "")[:150],
            "latency_ms": round(latency),
            "error": None,
        }
    except Exception as e:
        latency = (time.time() - t0) * 1000
        return {
            "id": fixture["id"],
            "expected": expected,
            "predicted": None,
            "correct": False,
            "reason": "",
            "latency_ms": round(latency),
            "error": str(e)[:200],
        }


@app.command()
def run(
    backends_csv: str = typer.Option("", "--backends", "-b", help="Comma-separated backends (default: all available)"),
    include_claude: bool = typer.Option(False, "--claude", help="Include claude-subagent (slow)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-fixture details"),
    write_winner: bool = typer.Option(True, "--write-winner/--no-write-winner", help="Write prompt_lab_winner.json"),
    prompt_file: str = typer.Option("", "--prompt", "-p", help="Custom prompt file to test (default: built-in v8)"),
):
    """Evaluate plausibility prompt against 36 ground-truth fixtures."""
    fixtures = _load_fixtures()
    console.print(f"[bold]Plausibility Eval: {len(fixtures)} fixtures[/bold]")

    # Build backend list
    if backends_csv:
        all_backends = _build_backends()
        if include_claude:
            all_backends.append(("claude-subagent", "", "", ""))
        selected = backends_csv.split(",")
        backends = [b for b in all_backends if b[0] in selected]
    else:
        backends = _build_backends()
        if include_claude:
            backends.append(("claude-subagent", "", "", ""))

    if not backends:
        console.print("[red]No backends available[/red]")
        raise typer.Exit(1)

    console.print(f"Backends: {', '.join(b[0] for b in backends)}")

    # Load custom prompt if specified
    prompt_text = None
    if prompt_file:
        prompt_text = Path(prompt_file).read_text()
        console.print(f"Using custom prompt: {prompt_file}")

    # Run evaluation
    all_results: dict[str, list[dict]] = {}

    for backend_name, url, model, key in backends:
        console.print(f"\n[cyan]--- {backend_name} ---[/cyan]")
        results = []

        for i, fixture in enumerate(fixtures):
            result = _eval_fixture_against_backend(fixture, backend_name, url, model, key, prompt_text)
            results.append(result)

            if result["error"]:
                console.print(f"  [{i+1}/{len(fixtures)}] {fixture['id']}: [red]ERROR[/red] {result['error'][:80]}")
            elif verbose or not result["correct"]:
                expected_str = "answerable" if result["expected"] else "NOT answerable"
                predicted_str = "answerable" if result["predicted"] else "NOT answerable"
                status = "[green]OK[/green]" if result["correct"] else "[red]WRONG[/red]"
                console.print(
                    f"  [{i+1}/{len(fixtures)}] {fixture['id']}: {status} "
                    f"expected={expected_str} got={predicted_str} "
                    f"({result['latency_ms']}ms)"
                )
                if not result["correct"] and result["reason"]:
                    console.print(f"    Reason: {result['reason'][:120]}")
            else:
                # Correct and not verbose — just show progress
                if (i + 1) % 10 == 0 or i == len(fixtures) - 1:
                    correct_so_far = sum(1 for r in results if r["correct"])
                    console.print(f"  [{i+1}/{len(fixtures)}] {correct_so_far}/{i+1} correct so far")

        all_results[backend_name] = results

    # Summary table
    console.print("\n")
    summary_table = Table(title="Plausibility Eval Summary")
    summary_table.add_column("Backend", style="cyan")
    summary_table.add_column("Total", justify="right")
    summary_table.add_column("Correct", justify="right")
    summary_table.add_column("Accuracy", justify="right")
    summary_table.add_column("FP (false accept)", justify="right", style="red")
    summary_table.add_column("FN (false reject)", justify="right", style="yellow")
    summary_table.add_column("Errors", justify="right", style="dim")
    summary_table.add_column("Avg Latency", justify="right")

    best_backend = None
    best_accuracy = -1.0

    for backend_name, results in all_results.items():
        total = len(results)
        correct = sum(1 for r in results if r["correct"])
        errors = sum(1 for r in results if r["error"])
        non_error = total - errors
        accuracy = correct / non_error if non_error > 0 else 0.0

        # False positives: expected=False but predicted=True (adversarial accepted)
        fp = sum(1 for r in results if not r["expected"] and r["predicted"] is True)
        # False negatives: expected=True but predicted=False (real rejected)
        fn = sum(1 for r in results if r["expected"] and r["predicted"] is False)

        latencies = [r["latency_ms"] for r in results if not r["error"]]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0

        summary_table.add_row(
            backend_name,
            str(total),
            str(correct),
            f"{accuracy:.1%}",
            str(fp),
            str(fn),
            str(errors),
            f"{avg_latency:.0f}ms",
        )

        if accuracy > best_accuracy:
            best_accuracy = accuracy
            best_backend = backend_name

    console.print(summary_table)

    # Detailed mismatch report
    console.print("\n[bold]Mismatches by fixture:[/bold]")
    mismatch_table = Table()
    mismatch_table.add_column("ID", style="dim")
    mismatch_table.add_column("Question", max_width=60)
    mismatch_table.add_column("Expected")
    for backend_name in all_results:
        mismatch_table.add_column(backend_name, justify="center")

    for i, fixture in enumerate(fixtures):
        row_has_mismatch = False
        cols = []
        for backend_name, results in all_results.items():
            r = results[i]
            if r["error"]:
                cols.append("[dim]ERR[/dim]")
                row_has_mismatch = True
            elif r["correct"]:
                cols.append("[green]OK[/green]")
            else:
                cols.append("[red]WRONG[/red]")
                row_has_mismatch = True

        if row_has_mismatch:
            expected_str = "[green]YES[/green]" if fixture["expected_answerable"] else "[red]NO[/red]"
            mismatch_table.add_row(
                fixture["id"],
                fixture["question"][:60],
                expected_str,
                *cols,
            )

    console.print(mismatch_table)

    # Check for label issues — if ALL backends disagree with expected, the label may be wrong
    console.print("\n[bold]Potential bad labels (all backends disagree with expected):[/bold]")
    bad_labels = []
    for i, fixture in enumerate(fixtures):
        all_disagree = True
        for backend_name, results in all_results.items():
            r = results[i]
            if r["error"] or r["correct"]:
                all_disagree = False
                break
        if all_disagree and len(all_results) > 0:
            bad_labels.append(fixture)
            expected_str = "answerable" if fixture["expected_answerable"] else "NOT answerable"
            console.print(f"  [yellow]{fixture['id']}[/yellow]: expected={expected_str}")
            console.print(f"    Q: {fixture['question'][:80]}")

    if not bad_labels:
        console.print("  None found")

    console.print(f"\n[bold]Best backend: {best_backend} ({best_accuracy:.1%})[/bold]")

    # Write winner
    if write_winner and best_backend:
        winner = {
            "backend": best_backend,
            "accuracy": round(best_accuracy, 4),
            "total_fixtures": len(fixtures),
            "eval_date": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "prompt_version": "v8_default_to_true",
        }

        # Add model info for the winning backend
        for b_name, url, model, key in backends:
            if b_name == best_backend:
                winner["model"] = model
                winner["url"] = url
                break

        WINNER_PATH.write_text(json.dumps(winner, indent=2))
        console.print(f"[green]Wrote {WINNER_PATH}[/green]")

    # Write detailed results
    results_path = Path(__file__).parent / "eval_results.json"
    results_path.write_text(json.dumps({
        "eval_date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "fixtures_count": len(fixtures),
        "backends": {
            name: {
                "accuracy": sum(1 for r in results if r["correct"]) / max(len([r for r in results if not r["error"]]), 1),
                "false_positives": sum(1 for r in results if not r["expected"] and r["predicted"] is True),
                "false_negatives": sum(1 for r in results if r["expected"] and r["predicted"] is False),
                "errors": sum(1 for r in results if r["error"]),
                "results": results,
            }
            for name, results in all_results.items()
        },
        "bad_labels": [f["id"] for f in bad_labels],
    }, indent=2))
    console.print(f"[green]Wrote {results_path}[/green]")


if __name__ == "__main__":
    app()
