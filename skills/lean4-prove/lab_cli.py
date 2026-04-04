#!/usr/bin/env python3
"""
lab_cli: Typer CLI for lean4-prove lab subcommands.

Self-improving lab capabilities for formal verification:
  - ingest: HF datasets → ArangoDB
  - compile: Parallel batch compilation (×20 silos via LeanInteract)
  - formalize: Bidirectional English↔Lean4
  - converge: Self-improvement loop (GRPO + compiler)
  - benchmark: Eval on MiniF2F + QRA chains
  - report: Convergence metrics + trend analysis
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="lab",
    help="Self-improving lab for formal verification (GRPO + Lean4 compiler rewards)",
)


@app.command()
def ingest(
    dataset: str = typer.Option(
        "casey-martin/ntp-lean4-autoformalization",
        help="HuggingFace dataset identifier",
    ),
    limit: int = typer.Option(0, help="Limit rows (0=all)"),
    batch_size: int = typer.Option(500, help="Batch size for /memory learn"),
):
    """Ingest autoformalization datasets from HuggingFace into ArangoDB."""
    from ingest_autoformalization import main as _ingest_main

    _ingest_main(dataset=dataset, limit=limit, batch_size=batch_size)


@app.command()
def compile(
    input: Path = typer.Option(..., help="JSONL file with proof code (one per line, 'code' field)"),
    workers: int = typer.Option(20, help="Number of parallel Lean4 silos"),
    timeout: float = typer.Option(30.0, help="Per-proof timeout in seconds"),
    output: Optional[Path] = typer.Option(None, help="Output JSONL file (default: stdout)"),
):
    """Parallel batch compilation via LeanInteract (×N silos)."""
    from compiler import ParallelCompiler

    compiler = ParallelCompiler(n_workers=workers, timeout=timeout)

    proofs = []
    for line in input.read_text().strip().splitlines():
        row = json.loads(line)
        proofs.append(row.get("code", row.get("lean4_code", "")))

    results = compiler.compile_batch(proofs)

    lines = []
    for proof, result in zip(proofs, results):
        lines.append(json.dumps({
            "success": result.success,
            "code": proof[:200],
            "error": result.error,
            "elapsed_ms": result.elapsed_ms,
        }))

    out_text = "\n".join(lines)
    if output:
        output.write_text(out_text)
        print(f"Wrote {len(results)} results to {output}", file=sys.stderr)
    else:
        print(out_text)


@app.command()
def formalize(
    english: str = typer.Option(None, help="English requirement to formalize"),
    lean4: str = typer.Option(None, help="Lean4 code to informalize"),
    round_trip: bool = typer.Option(False, help="Run round-trip check"),
    workers: int = typer.Option(20, help="Compiler workers for verification"),
):
    """Bidirectional English↔Lean4 formalization."""
    from formalize import formalize as _formalize, informalize, round_trip_check

    if round_trip and english:
        result = round_trip_check(english, n_workers=workers)
        print(json.dumps(result.__dict__, indent=2, default=str))
    elif english:
        result = _formalize(english, n_workers=workers)
        print(json.dumps(result.__dict__, indent=2, default=str))
    elif lean4:
        result = informalize(lean4)
        print(json.dumps({"english": result}, indent=2))
    else:
        print("Error: provide --english or --lean4", file=sys.stderr)
        raise typer.Exit(1)


@app.command()
def converge(
    max_cycles: int = typer.Option(10, help="Maximum convergence cycles"),
    budget_limit: float = typer.Option(5000.0, help="Max RunPod spend ($)"),
    batch_size: int = typer.Option(500, help="Formalizations per cycle"),
    workers: int = typer.Option(20, help="Compiler workers"),
    state_file: Optional[Path] = typer.Option(None, help="State file path"),
):
    """Run self-improvement convergence loop (GRPO + compiler rewards)."""
    from converge import ConvergenceLoop

    loop = ConvergenceLoop(
        max_cycles=max_cycles,
        budget_limit=budget_limit,
        batch_size=batch_size,
        n_workers=workers,
        state_file=state_file,
    )
    loop.run()


@app.command()
def benchmark(
    eval: str = typer.Option("minif2f", help="Eval set: minif2f, prover-bench, qra"),
    output: Optional[Path] = typer.Option(None, help="Output JSON file"),
    workers: int = typer.Option(20, help="Compiler workers"),
    pass_at_n: int = typer.Option(32, help="Pass@N for sampling"),
):
    """Evaluate on benchmark datasets (MiniF2F, ProverBench, QRA chains)."""
    from benchmark import run_benchmark

    results = run_benchmark(
        eval_set=eval,
        n_workers=workers,
        pass_at_n=pass_at_n,
    )

    out_text = json.dumps(results, indent=2)
    if output:
        output.write_text(out_text)
        print(f"Benchmark results written to {output}", file=sys.stderr)
    else:
        print(out_text)


@app.command()
def report(
    baseline: Optional[Path] = typer.Option(None, help="Baseline benchmark JSON"),
    trained: Optional[Path] = typer.Option(None, help="Trained benchmark JSON"),
    state_file: Optional[Path] = typer.Option(None, help="Convergence state file"),
):
    """Generate convergence metrics report with trend analysis."""
    data = {}
    if baseline and baseline.exists():
        data["baseline"] = json.loads(baseline.read_text())
    if trained and trained.exists():
        data["trained"] = json.loads(trained.read_text())
    if state_file and state_file.exists():
        data["convergence"] = json.loads(state_file.read_text())

    # Compute deltas
    if "baseline" in data and "trained" in data:
        b = data["baseline"]
        t = data["trained"]
        deltas = {}
        for key in set(b.keys()) & set(t.keys()):
            if isinstance(b[key], (int, float)) and isinstance(t[key], (int, float)):
                deltas[key] = {
                    "baseline": b[key],
                    "trained": t[key],
                    "delta": t[key] - b[key],
                    "relative": f"{(t[key] - b[key]) / max(abs(b[key]), 1e-9) * 100:.1f}%",
                }
        data["deltas"] = deltas

    print(json.dumps(data, indent=2, default=str))


if __name__ == "__main__":
    app()
