#!/usr/bin/env python3
"""
converge: Self-improvement convergence loop for Lean4 formalization.

Follows /conversation-lab convergence pattern:
  generate → compile → grade → train → compare → archive

Stopping conditions:
  - pass_rate >= 0.80 on MiniF2F
  - Plateau: 2 consecutive cycles with <5% improvement
  - Budget limit exceeded
  - Max cycles reached

State persisted to ~/.pi/lean4-prove/convergence_state.json.

Usage:
    python converge.py --max-cycles 10 --budget-limit 5000
"""
from __future__ import annotations

import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer


@dataclass
class CycleResult:
    """Result of a single convergence cycle."""
    cycle: int
    generated: int = 0
    compiled_ok: int = 0
    compiled_fail: int = 0
    pass_rate: float = 0.0
    grpo_trained: bool = False
    grpo_cost: float = 0.0
    benchmark_score: float = 0.0
    elapsed_seconds: float = 0.0
    timestamp: str = ""


@dataclass
class ConvergenceState:
    """Persistent convergence state."""
    cycles: List[CycleResult] = field(default_factory=list)
    current_model: str = ""
    total_cost: float = 0.0
    status: str = "pending"  # pending | running | converged | plateau | budget_exceeded | max_cycles
    started_at: str = ""
    stopped_at: str = ""

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, default=str))

    @classmethod
    def load(cls, path: Path) -> "ConvergenceState":
        if path.exists():
            data = json.loads(path.read_text())
            cycles = [CycleResult(**c) for c in data.pop("cycles", [])]
            return cls(cycles=cycles, **data)
        return cls()


class ConvergenceLoop:
    """Self-improvement convergence loop.

    Each cycle:
      1. GENERATE: formalize batch_size English requirements → Lean4
      2. COMPILE: parallel ×N via ParallelCompiler
      3. GRADE: pass/fail + error taxonomy
      4. TRAIN: GRPO on RunPod (if not plateau)
      5. COMPARE: pass_rate vs previous cycle
      6. ARCHIVE: /memory learn results + /episodic-archiver

    Args:
        max_cycles: Maximum number of convergence cycles
        budget_limit: Maximum RunPod spend ($)
        batch_size: Formalizations per cycle
        n_workers: Parallel compiler workers
        state_file: Path to state JSON
        target_pass_rate: Stop when MiniF2F pass rate reaches this
        plateau_threshold: Min improvement to avoid plateau detection
        plateau_count: Consecutive plateau cycles before stopping
    """

    def __init__(
        self,
        max_cycles: int = 10,
        budget_limit: float = 5000.0,
        batch_size: int = 500,
        n_workers: int = 20,
        state_file: Optional[Path] = None,
        target_pass_rate: float = 0.80,
        plateau_threshold: float = 0.05,
        plateau_count: int = 2,
    ):
        self.max_cycles = max_cycles
        self.budget_limit = budget_limit
        self.batch_size = batch_size
        self.n_workers = n_workers
        self.target_pass_rate = target_pass_rate
        self.plateau_threshold = plateau_threshold
        self.plateau_count = plateau_count

        if state_file is None:
            state_file = Path.home() / ".pi" / "lean4-prove" / "convergence_state.json"
        self.state_file = state_file
        self.state = ConvergenceState.load(state_file)

    def _get_training_problems(self) -> List[Dict]:
        """Fetch English requirements for formalization.

        Sources (priority order):
        1. lean4_autoformalization collection (ingested HF data)
        2. proof_jobs queue (pending requirements from extraction pipeline)
        3. Generated synthetic requirements
        """
        problems = []

        # Try lean4_autoformalization first via memory daemon
        try:
            import httpx
            transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
            with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
                resp = client.post("/recall", json={
                    "q": "english:*",
                    "collections": ["lean4_autoformalization"],
                    "k": self.batch_size,
                })
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        problems = data
                    elif isinstance(data, dict):
                        problems = data.get("items", data.get("results", []))
        except Exception:
            pass

        if not problems:
            # Fallback: generate simple test problems
            problems = [
                {"english": f"For all natural numbers n, n + {i} = {i} + n"}
                for i in range(min(self.batch_size, 50))
            ]

        return problems[:self.batch_size]

    def _formalize_batch(self, problems: List[Dict]) -> List[Dict]:
        """Formalize a batch of English requirements."""
        results = []
        try:
            from formalize import formalize
        except ImportError:
            # Stub: return empty results
            return [{"english": p.get("english", ""), "lean4_code": "", "compiled": False}
                    for p in problems]

        for p in problems:
            english = p.get("english", "")
            if not english:
                continue
            try:
                result = formalize(english, n_workers=self.n_workers)
                results.append({
                    "english": english,
                    "lean4_code": result.lean4_code,
                    "compiled": result.compiled,
                    "error": result.compile_error,
                })
            except Exception as e:
                results.append({
                    "english": english,
                    "lean4_code": "",
                    "compiled": False,
                    "error": str(e),
                })

        return results

    def _run_benchmark(self) -> float:
        """Run benchmark and return pass rate."""
        try:
            from benchmark import run_benchmark
            results = run_benchmark(eval_set="minif2f", n_workers=self.n_workers)
            return results.get("pass_rate", 0.0)
        except Exception:
            return 0.0

    def _check_plateau(self) -> bool:
        """Check if convergence has plateaued."""
        if len(self.state.cycles) < self.plateau_count + 1:
            return False

        recent = self.state.cycles[-self.plateau_count:]
        for i in range(1, len(recent)):
            improvement = recent[i].pass_rate - recent[i - 1].pass_rate
            if improvement > self.plateau_threshold:
                return False

        return True

    def _check_budget(self) -> bool:
        """Check if budget limit exceeded."""
        return self.state.total_cost >= self.budget_limit

    def _archive_cycle(self, cycle_result: CycleResult, formalization_results: List[Dict]):
        """Archive cycle results via /memory learn + /episodic-archiver."""
        try:
            import httpx
            doc = {
                "_key": f"lean4_convergence_cycle_{cycle_result.cycle}",
                "type": "convergence_cycle",
                "cycle": cycle_result.cycle,
                "pass_rate": cycle_result.pass_rate,
                "generated": cycle_result.generated,
                "compiled_ok": cycle_result.compiled_ok,
                "benchmark_score": cycle_result.benchmark_score,
                "timestamp": cycle_result.timestamp,
            }
            transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
            with httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0) as client:
                client.post("/learn", json={
                    "problem": f"lean4_convergence_cycle_{cycle_result.cycle}",
                    "solution": json.dumps(doc),
                    "scope": "task_states",
                })
        except Exception:
            pass  # Non-fatal

    def run_cycle(self, cycle_num: int) -> CycleResult:
        """Run a single convergence cycle."""
        t0 = time.time()
        result = CycleResult(
            cycle=cycle_num,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )

        print(f"\n{'='*60}", file=sys.stderr)
        print(f"Convergence Cycle {cycle_num}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        # 1. GENERATE: Get problems and formalize
        print(f"  [1/5] Fetching {self.batch_size} problems...", file=sys.stderr)
        problems = self._get_training_problems()
        result.generated = len(problems)

        print(f"  [2/5] Formalizing {len(problems)} requirements...", file=sys.stderr)
        formalization_results = self._formalize_batch(problems)

        # 3. GRADE
        result.compiled_ok = sum(1 for r in formalization_results if r.get("compiled"))
        result.compiled_fail = len(formalization_results) - result.compiled_ok
        result.pass_rate = (
            result.compiled_ok / len(formalization_results)
            if formalization_results else 0.0
        )

        print(
            f"  [3/5] Grade: {result.compiled_ok}/{len(formalization_results)} "
            f"compiled ({result.pass_rate:.1%})",
            file=sys.stderr,
        )

        # 4. TRAIN (GRPO) — only if we have enough data and not in mock mode
        # In production: this would invoke /ops-runpod + train_grpo.py
        print(f"  [4/5] GRPO training (deferred to /ops-runpod)", file=sys.stderr)
        result.grpo_trained = False  # Set true when RunPod job completes

        # 5. BENCHMARK
        print(f"  [5/5] Running benchmark...", file=sys.stderr)
        result.benchmark_score = self._run_benchmark()

        result.elapsed_seconds = time.time() - t0

        # Archive
        self._archive_cycle(result, formalization_results)

        return result

    def run(self):
        """Run the full convergence loop."""
        self.state.status = "running"
        self.state.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.state.save(self.state_file)

        start_cycle = len(self.state.cycles) + 1

        for cycle_num in range(start_cycle, start_cycle + self.max_cycles):
            # Check stopping conditions
            if self._check_budget():
                self.state.status = "budget_exceeded"
                print(
                    f"Budget limit reached (${self.state.total_cost:.0f} / "
                    f"${self.budget_limit:.0f})",
                    file=sys.stderr,
                )
                break

            if self._check_plateau():
                self.state.status = "plateau"
                print(
                    f"Plateau detected: {self.plateau_count} cycles with "
                    f"<{self.plateau_threshold:.0%} improvement",
                    file=sys.stderr,
                )
                break

            # Run cycle
            cycle_result = self.run_cycle(cycle_num)
            self.state.cycles.append(cycle_result)
            self.state.total_cost += cycle_result.grpo_cost
            self.state.save(self.state_file)

            # Check target
            if cycle_result.benchmark_score >= self.target_pass_rate:
                self.state.status = "converged"
                print(
                    f"TARGET REACHED: benchmark={cycle_result.benchmark_score:.1%} "
                    f">= {self.target_pass_rate:.1%}",
                    file=sys.stderr,
                )
                break

            print(
                f"  Cycle {cycle_num} complete: pass_rate={cycle_result.pass_rate:.1%}, "
                f"benchmark={cycle_result.benchmark_score:.1%}, "
                f"elapsed={cycle_result.elapsed_seconds:.0f}s",
                file=sys.stderr,
            )

        else:
            self.state.status = "max_cycles"

        self.state.stopped_at = time.strftime("%Y-%m-%dT%H:%M:%SZ")
        self.state.save(self.state_file)

        # Final summary
        print(json.dumps({
            "status": self.state.status,
            "total_cycles": len(self.state.cycles),
            "total_cost": self.state.total_cost,
            "final_pass_rate": self.state.cycles[-1].pass_rate if self.state.cycles else 0,
            "final_benchmark": self.state.cycles[-1].benchmark_score if self.state.cycles else 0,
            "state_file": str(self.state_file),
        }, indent=2))


def main(
    max_cycles: int = typer.Option(10, help="Maximum convergence cycles"),
    budget_limit: float = typer.Option(5000.0, help="Max RunPod spend ($)"),
    batch_size: int = typer.Option(500, help="Formalizations per cycle"),
    workers: int = typer.Option(20, help="Compiler workers"),
    state_file: Optional[Path] = typer.Option(None, help="State file path"),
):
    """Run self-improvement convergence loop."""
    loop = ConvergenceLoop(
        max_cycles=max_cycles,
        budget_limit=budget_limit,
        batch_size=batch_size,
        n_workers=workers,
        state_file=state_file,
    )
    loop.run()


if __name__ == "__main__":
    typer.run(main)
