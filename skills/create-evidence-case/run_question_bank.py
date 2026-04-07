"""Run question bank through the evidence case pipeline.

Generates ~999 questions from live data sources, then runs each through
EvidenceCaseRunner. Supports --gates-only for deterministic-only checks
(no LLM, no lean4, no plausibility — just entity extraction + recall +
same-technique check).

Usage:
    python run_question_bank.py
    python run_question_bank.py --gates-only --limit 50
    python run_question_bank.py --check-regression
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from question_bank import TestQuestion, generate_bank, bank_summary
from runner import EvidenceCaseRunner

app = typer.Typer()
console = Console()

OUTPUT_DIR = Path("/tmp/evidence-case-v2-results")
STATE_DIR = Path(__file__).parent / "state"
BASELINE_FILE = STATE_DIR / "eval_baseline.json"

# Map expected_verdict → accepted runner verdict_state values
_VERDICT_MAP = {
    "SATISFIED": {"satisfied"},
    "NOT_SATISFIED": {"not_satisfied"},
    "INCONCLUSIVE": {"inconclusive"},
    "DEFLECT": {"not_satisfied"},  # off-topic → not_satisfied in runner
}


def _is_correct(expected_verdict: str, actual_verdict: str) -> bool:
    """Check if the actual verdict matches the expected one."""
    accepted = _VERDICT_MAP.get(expected_verdict, set())
    return actual_verdict in accepted


def _run_one(runner: EvidenceCaseRunner, q: TestQuestion, idx: int, total: int) -> dict:
    """Run a single question and return the result with metadata."""
    start = time.monotonic()
    try:
        result = runner.run(
            claim_text=q.question,
            category=q.category,
            show_progress=False,
        )
    except Exception as exc:
        logger.error("Q{:03d} crashed: {}", idx, exc)
        result = {
            "claim": {"text": q.question, "category": q.category, "id": f"error_{idx}"},
            "verdict": {"state": "error", "grade": "F", "score": 0.0},
            "answer": f"CRASH: {exc}",
            "gate_trace": [],
            "gates_passed": 0,
            "gates_total": 0,
        }
    elapsed = time.monotonic() - start

    verdict_state = result.get("verdict", {}).get("state", "unknown")
    correct = _is_correct(q.expected_verdict, verdict_state)

    result["_meta"] = {
        "question_index": idx,
        "category": q.category,
        "framework": q.framework,
        "control_id": q.control_id,
        "expected_verdict": q.expected_verdict,
        "verdict_state": verdict_state,
        "correct": correct,
        "source": q.source,
        "elapsed_sec": round(elapsed, 2),
    }
    return result


def _build_report(results: list[dict], elapsed_total: float, gates_only: bool) -> str:
    """Build aggregate validation report."""
    lines = []
    mode = "Gates-Only" if gates_only else "Full Pipeline"
    lines.append(f"# Evidence Case Test Bank — {mode} Report")
    lines.append(f"\n**Date**: {time.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Total time**: {elapsed_total:.1f}s")
    lines.append(f"**Questions**: {len(results)}")
    lines.append("")

    correct = sum(1 for r in results if r.get("_meta", {}).get("correct"))
    total = len(results)
    accuracy = correct / total if total else 0
    lines.append(f"## Accuracy: {correct}/{total} ({accuracy:.0%})")
    lines.append("")

    # Per-category accuracy
    lines.append("## Accuracy by Category")
    lines.append("")
    for cat in ("satisfied", "not_satisfied", "inconclusive", "off_topic"):
        subset = [r for r in results if r["_meta"]["category"] == cat]
        if subset:
            cat_correct = sum(1 for r in subset if r["_meta"]["correct"])
            lines.append(f"- {cat}: {cat_correct}/{len(subset)} ({cat_correct/len(subset):.0%})")

    # False positives (expected NOT_SATISFIED/INCONCLUSIVE/DEFLECT but got satisfied)
    fp = [r for r in results if r["_meta"]["expected_verdict"] != "SATISFIED"
          and r["_meta"]["verdict_state"] == "satisfied"]
    lines.append(f"\n**False positives**: {len(fp)}")
    for r in fp[:10]:
        lines.append(f"  - Q{r['_meta']['question_index']:03d}: {r['claim']['text'][:60]}...")

    # False negatives (expected SATISFIED but got not_satisfied)
    fn = [r for r in results if r["_meta"]["expected_verdict"] == "SATISFIED"
          and r["_meta"]["verdict_state"] == "not_satisfied"]
    lines.append(f"**False negatives**: {len(fn)}")
    for r in fn[:10]:
        lines.append(f"  - Q{r['_meta']['question_index']:03d}: {r['claim']['text'][:60]}...")

    lines.append("")

    # Per-framework accuracy
    lines.append("## Accuracy by Framework")
    lines.append("")
    frameworks = sorted({r["_meta"]["framework"] for r in results})
    for fw in frameworks:
        subset = [r for r in results if r["_meta"]["framework"] == fw]
        if subset:
            fw_correct = sum(1 for r in subset if r["_meta"]["correct"])
            lines.append(f"- {fw}: {fw_correct}/{len(subset)} ({fw_correct/len(subset):.0%})")

    lines.append("")

    # Gate failure distribution
    gate_failures: dict[str, int] = {}
    for r in results:
        stopped = r.get("stopped_at_gate")
        if stopped:
            gate_failures[stopped] = gate_failures.get(stopped, 0) + 1
    if gate_failures:
        lines.append("## Gate Failure Distribution")
        lines.append("")
        for gate, count in sorted(gate_failures.items(), key=lambda x: -x[1]):
            lines.append(f"- {gate}: {count} questions stopped here")
        lines.append("")

    return "\n".join(lines)


@app.command()
def run(
    output_dir: str = typer.Option(str(OUTPUT_DIR), "--output-dir", "-o"),
    gates_only: bool = typer.Option(False, "--gates-only",
                                     help="Run deterministic gates only (no LLM, no lean4)"),
    limit: int = typer.Option(0, "--limit", "-n",
                               help="Max questions to run (0 = all)"),
    seed: int = typer.Option(42, "--seed", help="Random seed for bank generation"),
    json_output: bool = typer.Option(False, "--json"),
    check_regression: bool = typer.Option(False, "--check-regression"),
    save_baseline: bool = typer.Option(False, "--save-baseline"),
) -> None:
    """Run question bank through the evidence case pipeline."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    console.print(f"[bold]Generating question bank (seed={seed})...[/]")
    bank = generate_bank(seed=seed)
    summary = bank_summary(bank)
    console.print(f"[bold]Bank: {len(bank)} questions[/]")
    for k, v in summary.get("by_category", {}).items():
        console.print(f"  {k}: {v}")

    if limit > 0:
        bank = bank[:limit]
        console.print(f"[dim]Limited to first {limit} questions[/]")

    workers = 5 if gates_only else 1  # daemon handles concurrent requests
    runner = EvidenceCaseRunner(gates_only=gates_only)
    results: list[dict] = [{}] * len(bank)  # pre-allocate for ordered results
    total_start = time.monotonic()
    correct_count = 0
    done_count = 0

    from concurrent.futures import ThreadPoolExecutor, as_completed

    def _process(idx_q: tuple[int, TestQuestion]) -> tuple[int, dict]:
        idx, q = idx_q
        return idx, _run_one(runner, q, idx, len(bank))

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_process, (idx, q)): idx for idx, q in enumerate(bank, 1)}
        for future in as_completed(futures):
            idx, result = future.result()
            results[idx - 1] = result

            # Save per-question JSON
            q_path = out / f"q{idx:03d}.json"
            q_path.write_text(json.dumps(result, indent=2, default=str))

            m = result["_meta"]
            done_count += 1
            if m["correct"]:
                correct_count += 1
            icon = "[green]CORRECT[/]" if m["correct"] else "[red]WRONG[/]"
            console.print(
                f"[bold cyan]Q{idx:03d}[/] ({done_count}/{len(bank)}) "
                f"{icon} expected={m['expected_verdict']} got={m['verdict_state']} "
                f"({m['elapsed_sec']:.1f}s) "
                f"[dim]running={correct_count}/{done_count}[/]"
            )

    total_elapsed = time.monotonic() - total_start

    # Save aggregate report
    report = _build_report(results, total_elapsed, gates_only)
    report_path = out / "REPORT.md"
    report_path.write_text(report)

    # Save all results as JSON
    all_path = out / "all_results.json"
    all_path.write_text(json.dumps(results, indent=2, default=str))

    # Compute summary
    correct = sum(1 for r in results if r["_meta"]["correct"])
    accuracy = correct / len(results) if results else 0
    false_positives = sum(
        1 for r in results
        if r["_meta"]["expected_verdict"] != "SATISFIED"
        and r["_meta"]["verdict_state"] == "satisfied"
    )
    false_negatives = sum(
        1 for r in results
        if r["_meta"]["expected_verdict"] == "SATISFIED"
        and r["_meta"]["verdict_state"] == "not_satisfied"
    )

    run_summary = {
        "version": 2,
        "date": time.strftime("%Y-%m-%d"),
        "gates_only": gates_only,
        "accuracy": round(accuracy, 3),
        "correct": correct,
        "total": len(results),
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "elapsed_sec": round(total_elapsed, 2),
        "output_dir": str(out),
    }

    console.print(f"\n[bold]Results: {correct}/{len(results)} correct ({accuracy:.0%})[/]")
    console.print(f"False positives: {false_positives}, False negatives: {false_negatives}")
    console.print(f"Report: {report_path}")
    console.print(f"Time: {total_elapsed:.1f}s ({total_elapsed/len(results):.1f}s/question)")

    if json_output:
        print(json.dumps(run_summary, indent=2))

    if save_baseline:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        baseline = {**run_summary, "regression_threshold": 0.08}
        BASELINE_FILE.write_text(json.dumps(baseline, indent=2))
        console.print(f"[green]Saved baseline: {BASELINE_FILE}[/]")

    if check_regression:
        if not BASELINE_FILE.exists():
            console.print("[yellow]No baseline file — skipping regression check[/]")
            return

        baseline = json.loads(BASELINE_FILE.read_text())
        baseline_accuracy = baseline.get("accuracy", 0)
        threshold = baseline.get("regression_threshold", 0.08)
        drop = baseline_accuracy - accuracy

        if drop > threshold:
            console.print(
                f"[bold red]REGRESSION: accuracy dropped {drop:.1%} "
                f"(baseline={baseline_accuracy:.0%}, current={accuracy:.0%})[/]"
            )
            sys.exit(1)
        else:
            console.print(
                f"[green]No regression: baseline={baseline_accuracy:.0%}, "
                f"current={accuracy:.0%}[/]"
            )


if __name__ == "__main__":
    app()
