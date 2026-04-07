"""
Grid evaluation: question-by-model matrix with Pass/Fail and retry counts.

Runs ALL specified models against ALL questions (no early stopping).
Outputs a Rich table with questions as rows, models as columns, and
Pass/Fail/Pass-N cells. Summary row with totals and a one-line recommendation.
"""
import asyncio
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.table import Table
from rich.text import Text

from config import GROUND_TRUTH_DIR, PROMPTS_DIR, RESULTS_DIR, ensure_dirs
from evaluation import load_models_config
from llm import call_provider

from eval_app import app, console


def _check_answer(actual: str, expected: str, eval_mode: str) -> bool:
    """Check if model output matches expected answer."""
    actual = actual.strip()
    expected = expected.strip()

    if eval_mode == "exact":
        return actual.lower() == expected.lower()
    elif eval_mode == "contains":
        return expected.lower() in actual.lower()
    elif eval_mode == "json_field":
        # expected is "field=value", check parsed JSON
        if "=" not in expected:
            return expected.lower() in actual.lower()
        field, value = expected.split("=", 1)
        try:
            parsed = json.loads(actual)
            return str(parsed.get(field, "")).lower() == value.lower()
        except json.JSONDecodeError:
            return False
    elif eval_mode == "regex":
        return bool(re.search(expected, actual, re.IGNORECASE))
    elif eval_mode == "not_empty":
        return len(actual) > 0
    elif eval_mode == "agent_judge":
        return _agent_judge(actual, expected)
    else:
        # Default: contains
        return expected.lower() in actual.lower()


def _agent_judge(actual: str, expected: str) -> bool:
    """Use scillm to judge answer quality.

    Routes through the scillm proxy for LLM-based evaluation.
    Falls back to contains check if scillm is unavailable.
    """
    import httpx as _httpx

    judge_prompt = (
        "You are an evaluation judge. Compare the ACTUAL answer against the EXPECTED answer.\n"
        "Judge whether the ACTUAL answer is correct, accurate, and addresses the same intent.\n"
        "Minor wording differences are acceptable. Missing key information is a failure.\n"
        "Off-topic refusals when expected are correct (PASS). Off-topic answers when a real answer is expected are wrong (FAIL).\n"
        "Respond with ONLY one word: PASS or FAIL"
    )

    full_prompt = f"{judge_prompt}\n\nEXPECTED:\n{expected}\n\nACTUAL:\n{actual}\n\nVerdict (PASS or FAIL):"

    # scillm judge (API key, cheap, large context)
    for model in ("text-gemini", "text"):
        try:
            resp = _httpx.post(
                "http://localhost:4001/v1/chat/completions",
                headers={"Authorization": "Bearer sk-dev-proxy-123"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": full_prompt}],
                    "max_tokens": 8,
                },
                timeout=30.0,
            )
            if resp.status_code == 200:
                verdict = resp.json()["choices"][0]["message"]["content"].strip().upper()
                logger.debug("scillm judge ({}): {}", model, verdict)
                return "PASS" in verdict
        except Exception as e:
            logger.debug("scillm judge ({}) failed: {}", model, e)

    # Last resort: basic contains check
    return expected.lower() in actual.lower()


@app.command("grid-eval")
def grid_eval(
    ground_truth: str = typer.Option(
        ..., "--ground-truth", "-g", help="Ground truth JSON file"
    ),
    models: Optional[str] = typer.Option(
        None, "--models", "-m",
        help="Comma-separated model aliases (default: all in ground truth file)"
    ),
    prompt_file: Optional[str] = typer.Option(
        None, "--prompt", "-p", help="Optional system prompt file"
    ),
    max_retries: int = typer.Option(
        3, "--max-retries", "-r", help="Max retries per question per model"
    ),
    output: Optional[str] = typer.Option(
        None, "--output", "-o", help="Save results JSON to this path"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show model outputs on failure"
    ),
):
    """
    Run all models against all questions and display a comparison grid.

    Ground truth JSON format:
    {
      "title": "Qwen Model Comparison",
      "models": ["qwen2.5-3b-local", "qwen2.5-7b-local", ...],
      "questions": [
        {
          "id": 1,
          "short": "Simple math",
          "input": "What is 6 * 7?",
          "expected": "42",
          "eval": "contains"
        }
      ]
    }

    Eval modes: exact, contains, json_field, regex, not_empty
    """
    ensure_dirs()
    models_config = load_models_config()

    # Load ground truth
    gt_path = (
        Path(ground_truth) if Path(ground_truth).is_absolute()
        else Path(GROUND_TRUTH_DIR) / ground_truth
    )
    if not gt_path.exists():
        console.print(f"[red]Ground truth not found: {gt_path}[/red]")
        raise typer.Exit(1)

    with open(gt_path) as f:
        gt_data = json.load(f)

    questions = gt_data.get("questions", [])
    if not questions:
        console.print("[red]No questions found in ground truth[/red]")
        raise typer.Exit(1)

    # Resolve model list
    if models:
        model_names = [m.strip() for m in models.split(",")]
    else:
        model_names = gt_data.get("models", [])
    if not model_names:
        console.print("[red]No models specified (use --models or 'models' in ground truth)[/red]")
        raise typer.Exit(1)

    # Validate models exist in config
    missing = [m for m in model_names if m not in models_config]
    if missing:
        console.print(f"[red]Unknown models: {', '.join(missing)}[/red]")
        console.print(f"[dim]Available: {', '.join(k for k in models_config if not k.startswith('_'))}[/dim]")
        raise typer.Exit(1)

    # Preflight: check Ollama models are pulled
    ollama_models = [
        m for m in model_names
        if models_config[m].get("provider") == "ollama" or models_config[m].get("local")
    ]
    if ollama_models:
        import httpx as _httpx

        not_pulled = []
        try:
            resp = _httpx.get("http://localhost:11434/api/tags", timeout=5.0)
            if resp.status_code == 200:
                pulled = {m["name"] for m in resp.json().get("models", [])}
                for alias in ollama_models:
                    ollama_name = models_config[alias].get("model", alias)
                    # Ollama tags: "qwen2.5:3b" matches "qwen2.5:3b" in pulled set
                    if not any(ollama_name in p or p.startswith(ollama_name.split(":")[0]) for p in pulled):
                        not_pulled.append((alias, ollama_name))
        except Exception:
            console.print("[yellow]Ollama not reachable — local models may fail[/yellow]")

        if not_pulled:
            console.print("[yellow]These models need to be pulled first:[/yellow]")
            for alias, ollama_name in not_pulled:
                console.print(f"  ollama pull {ollama_name}")
            console.print()
            if not typer.confirm("Continue anyway? (unpulled models will show Err)"):
                raise typer.Exit(0)

    # Load system prompt
    system_prompt = ""
    if prompt_file:
        prompt_path = (
            Path(prompt_file) if Path(prompt_file).is_absolute()
            else Path(PROMPTS_DIR) / prompt_file
        )
        if prompt_path.exists():
            system_prompt = prompt_path.read_text()

    title = gt_data.get("title", "Grid Evaluation")
    console.print(f"\n[bold]{title}[/bold]")
    console.print(f"Questions: {len(questions)} | Models: {len(model_names)} | Max retries: {max_retries}")
    console.print()

    # results[q_idx][model_name] = {"pass": bool, "tries": int, "output": str}
    results: dict[int, dict[str, dict]] = {}

    async def eval_question(q_idx: int, question: dict, model_name: str):
        """Evaluate one question against one model with retries."""
        model_config = models_config[model_name]
        input_text = question["input"]
        expected = question.get("expected", "")
        eval_mode = question.get("eval", "contains")
        q_max_tries = question.get("max_tries", max_retries)

        if system_prompt:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_text},
            ]
        else:
            messages = [{"role": "user", "content": input_text}]

        consecutive_errors = 0
        last_error = ""
        content = ""

        for attempt in range(1, q_max_tries + 1):
            try:
                content, latency = await call_provider(messages, model_config)
                consecutive_errors = 0  # Reset on successful call
                passed = _check_answer(content, expected, eval_mode)
                if passed:
                    return {"pass": True, "tries": attempt, "error": False, "output": content}
            except Exception as e:
                consecutive_errors += 1
                last_error = str(e)
                logger.debug("Q{} model={} attempt={}: {}", q_idx, model_name, attempt, e)
                content = f"ERROR: {e}"
                # If first question and all attempts are connection errors, model is down
                if consecutive_errors >= 2 and ("connect" in last_error.lower() or "timeout" in last_error.lower()):
                    return {"pass": False, "tries": attempt, "error": True, "output": content}

        return {"pass": False, "tries": q_max_tries, "error": consecutive_errors > 0, "output": content}

    async def run_all():
        for q_idx, question in enumerate(questions):
            q_id = question.get("id", q_idx + 1)
            short = question.get("short", f"Q{q_id}")
            console.print(f"  Q{q_id}: {short}", end="")

            results[q_idx] = {}
            for model_name in model_names:
                result = await eval_question(q_idx, question, model_name)
                results[q_idx][model_name] = result

                marker = "[green].[/green]" if result["pass"] else "[red]X[/red]"
                console.print(f" {marker}", end="")

            console.print()

    asyncio.run(run_all())

    # Build display names: shorten model aliases for column headers
    display_names = {}
    for m in model_names:
        # Strip common suffixes for compact headers
        short = m.replace("-local", "").replace("-instruct", "")
        display_names[m] = short

    # Build Rich table
    console.print()
    table = Table(title=title, show_lines=True)
    table.add_column("#", style="dim", width=3, justify="right")
    table.add_column("Question", min_width=20, max_width=30)
    table.add_column("Expected", min_width=8, max_width=15)
    for m in model_names:
        table.add_column(display_names[m], justify="center", min_width=8)

    for q_idx, question in enumerate(questions):
        q_id = str(question.get("id", q_idx + 1))
        short = question.get("short", f"Q{q_id}")
        expected = question.get("expected", "")
        # Truncate expected for display
        expected_display = expected[:12] + "..." if len(expected) > 15 else expected

        cells = [q_id, short, expected_display]
        for model_name in model_names:
            r = results[q_idx][model_name]
            if r["pass"]:
                if r["tries"] == 1:
                    cells.append(Text("Pass", style="green"))
                else:
                    cells.append(Text(f"Pass/{r['tries']}", style="yellow"))
            elif r.get("error"):
                cells.append(Text("Err", style="magenta bold"))
            else:
                cells.append(Text("Fail", style="red bold"))

        table.add_row(*cells)

    # Summary row
    summary_cells: list = ["", "TOTAL", ""]
    for model_name in model_names:
        passed = sum(1 for q in results.values() if q[model_name]["pass"])
        errors = sum(1 for q in results.values() if q[model_name].get("error"))
        total = len(questions)
        retries = sum(
            q[model_name]["tries"] - 1
            for q in results.values()
            if q[model_name]["pass"] and q[model_name]["tries"] > 1
        )
        if errors == total:
            summary_cells.append(Text("DOWN", style="magenta bold"))
        else:
            style = "green" if passed == total else "yellow" if passed >= total * 0.8 else "red"
            text = f"{passed}/{total}"
            if retries > 0:
                text += f" ({retries}r)"
            if errors > 0:
                text += f" ({errors}err)"
            summary_cells.append(Text(text, style=style))

    table.add_row(*summary_cells, end_section=True)
    console.print(table)

    # Recommendation (exclude models that were entirely unreachable)
    model_scores = []
    for model_name in model_names:
        passed = sum(1 for q in results.values() if q[model_name]["pass"])
        errors = sum(1 for q in results.values() if q[model_name].get("error"))
        total_retries = sum(
            q[model_name]["tries"] - 1
            for q in results.values()
            if q[model_name]["pass"] and q[model_name]["tries"] > 1
        )
        params = models_config[model_name].get("params_b", float("inf"))
        if errors == len(questions):
            console.print(f"[magenta]{model_name}: all questions errored (model unreachable)[/magenta]")
            continue
        model_scores.append({
            "model": model_name,
            "passed": passed,
            "retries": total_retries,
            "params_b": params,
        })

    total_q = len(questions)

    # Sort: most passed → fewest retries → smallest params
    model_scores.sort(key=lambda x: (-x["passed"], x["retries"], x["params_b"]))

    # Find minimum viable (all pass, fewest retries, smallest)
    perfect = [m for m in model_scores if m["passed"] == total_q]
    viable = [m for m in model_scores if m["passed"] >= total_q * 0.8]

    console.print()
    if perfect:
        best = perfect[0]
        console.print(
            f"[bold green]Minimum viable:[/bold green] {best['model']} "
            f"({best['passed']}/{total_q}, {best['retries']} retries, {best['params_b']}B)"
        )
        if len(perfect) > 1:
            reliable = [m for m in perfect if m["retries"] == 0]
            if reliable:
                names = ", ".join(m["model"] for m in reliable)
                console.print(f"[bold green]Most reliable:[/bold green]  {names} (0 retries)")
    elif viable:
        best = viable[0]
        console.print(
            f"[bold yellow]Best available:[/bold yellow] {best['model']} "
            f"({best['passed']}/{total_q}, {best['retries']} retries, {best['params_b']}B)"
        )
        console.print(f"[yellow]No model passed all questions.[/yellow]")
    else:
        console.print("[bold red]No model reached 80% accuracy.[/bold red]")

    # Save results
    output_data = {
        "timestamp": datetime.now().isoformat(),
        "title": title,
        "models": model_names,
        "question_count": len(questions),
        "max_retries": max_retries,
        "grid": {
            str(question.get("id", q_idx + 1)): {
                "short": question.get("short", ""),
                "results": {
                    m: {"pass": results[q_idx][m]["pass"], "tries": results[q_idx][m]["tries"]}
                    for m in model_names
                },
            }
            for q_idx, question in enumerate(questions)
        },
        "summary": {
            m["model"]: {"passed": m["passed"], "retries": m["retries"], "params_b": m["params_b"]}
            for m in model_scores
        },
        "recommendation": perfect[0]["model"] if perfect else (viable[0]["model"] if viable else None),
    }

    output_path = Path(output) if output else RESULTS_DIR / f"grid_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)
    console.print(f"\n[dim]Results saved to {output_path}[/dim]")
