"""Parameter sweep engine for RVC vocal conversion tuning.

Two-phase sweep:
  Phase 1 (Diagnostic): Vary one param at a time, hold others at default.
  Phase 2 (Cross): Combine top-2 values from each param.

Uses Docker RVC container for inference, then evaluates each output.

Merged from hum-lab/src/sweep.py.
"""

from __future__ import annotations

import itertools
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

from evaluate import EvalScores, build_reference_profile, evaluate

console = Console()

STORAGE_ROOT = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media"
DOCKER_CONTAINER = "rvc-training"

# Default parameter values
DEFAULTS = {
    "pitch": 0,
    "f0method": "rmvpe",
    "index_rate": 0.75,
    "filter_radius": 3,
    "protect": 0.33,
}

# Sweep grids per parameter
SWEEP_GRID = {
    "pitch": [-4, -2, 0, 2, 4],
    "f0method": ["rmvpe", "harvest", "crepe"],
    "index_rate": [0.3, 0.5, 0.75, 1.0],
    "filter_radius": [0, 3, 5, 7],
    "protect": [0.0, 0.33, 0.5],
}


@dataclass
class SweepResult:
    """Result for a single inference + evaluation."""

    params: dict
    scores: Optional[EvalScores] = None
    output_path: Optional[str] = None
    error: Optional[str] = None
    duration_s: float = 0.0

    def to_dict(self) -> dict:
        d = {
            "params": self.params,
            "output_path": self.output_path,
            "duration_s": self.duration_s,
        }
        if self.scores:
            d["scores"] = self.scores.to_dict()
            passed, failures = self.scores.passes_gates()
            d["passes_gates"] = passed
            d["gate_failures"] = failures
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class SweepRun:
    """Full sweep run with all results."""

    persona: str
    track: str
    phase: str  # "diagnostic", "cross", or "full"
    started: str = ""
    completed: str = ""
    results: list[SweepResult] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "persona": self.persona,
            "track": self.track,
            "phase": self.phase,
            "started": self.started,
            "completed": self.completed,
            "results": [r.to_dict() for r in self.results],
        }

    def ranked(self) -> list[SweepResult]:
        """Return results sorted by overall score, descending."""
        scored = [r for r in self.results if r.scores is not None]
        return sorted(scored, key=lambda r: r.scores.overall, reverse=True)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path) -> "SweepRun":
        with open(path) as f:
            data = json.load(f)
        run = cls(
            persona=data["persona"],
            track=data["track"],
            phase=data["phase"],
            started=data.get("started", ""),
            completed=data.get("completed", ""),
        )
        for rd in data.get("results", []):
            scores = None
            if "scores" in rd:
                s = rd["scores"]
                scores = EvalScores(**s)
            run.results.append(
                SweepResult(
                    params=rd["params"],
                    scores=scores,
                    output_path=rd.get("output_path"),
                    error=rd.get("error"),
                    duration_s=rd.get("duration_s", 0),
                )
            )
        return run


def _find_vocals(persona: str, track: str) -> Optional[Path]:
    """Find the original vocals input for a track."""
    cache_dir = STORAGE_ROOT / "personas" / persona / "hum-cache"

    vocals = cache_dir / f"{track}_vocals.wav"
    if vocals.exists():
        return vocals

    converted = cache_dir / f"{track}.wav"
    if converted.exists():
        return converted

    return None


def _find_human_reference(persona: str, track: str) -> Optional[Path]:
    """Find human humming reference for a track."""
    ref_dir = STORAGE_ROOT / "personas" / persona / "hum-cache" / "references"
    for name in [f"{track}_human.wav", f"{track}.wav"]:
        p = ref_dir / name
        if p.exists():
            return p
    if ref_dir.exists():
        refs = sorted(ref_dir.glob("*.wav"))
        if refs:
            return refs[0]
    return None


def _rvc_infer_docker(
    persona: str,
    input_path: Path,
    output_path: Path,
    params: dict,
) -> bool:
    """Run RVC inference inside Docker container."""
    model_dir = STORAGE_ROOT / "music" / "rvc-models" / "voice" / persona
    model_path = model_dir / f"{persona}.pth"
    index_path = model_dir / f"{persona}.index"

    if not model_path.exists():
        console.print(f"[red]Model not found: {model_path}[/red]")
        return False

    host_scratch = STORAGE_ROOT / "music" / "rvc-webui" / "logs" / "_hum_lab_scratch"
    host_scratch.mkdir(parents=True, exist_ok=True)

    docker_scratch = "/app/logs/_hum_lab_scratch"

    scratch_input = host_scratch / "input.wav"
    scratch_output = host_scratch / "output.wav"
    shutil.copy2(input_path, scratch_input)

    scratch_model = host_scratch / f"{persona}.pth"
    scratch_index = host_scratch / f"{persona}.index"
    if not scratch_model.exists():
        shutil.copy2(model_path, scratch_model)
    if index_path.exists() and not scratch_index.exists():
        shutil.copy2(index_path, scratch_index)

    cmd = [
        "docker", "exec", DOCKER_CONTAINER,
        "python", "/app/tools/infer_cli.py",
        "--f0up_key", str(params.get("pitch", 0)),
        "--input_path", f"{docker_scratch}/input.wav",
        "--opt_path", f"{docker_scratch}/output.wav",
        "--model_name", f"{docker_scratch}/{persona}.pth",
        "--index_path", f"{docker_scratch}/{persona}.index" if index_path.exists() else "",
        "--index_rate", str(params.get("index_rate", 0.75)),
        "--f0method", str(params.get("f0method", "rmvpe")),
        "--filter_radius", str(params.get("filter_radius", 3)),
        "--protect", str(params.get("protect", 0.33)),
        "--device", "cuda:0",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

    if result.returncode != 0:
        console.print(f"[dim red]RVC error: {result.stderr[:200]}[/dim red]")
        return False

    if scratch_output.exists():
        shutil.copy2(scratch_output, output_path)
        return output_path.exists()

    return False


def _build_diagnostic_combos() -> list[dict]:
    """Phase 1: Vary one param at a time, hold others at default."""
    combos = [dict(DEFAULTS)]

    for param_name, values in SWEEP_GRID.items():
        for val in values:
            if val == DEFAULTS[param_name]:
                continue
            combo = dict(DEFAULTS)
            combo[param_name] = val
            combos.append(combo)

    return combos


def _build_cross_combos(diagnostic_results: list[SweepResult]) -> list[dict]:
    """Phase 2: Combine top-2 values from each param."""
    param_scores: dict[str, dict] = {}
    for param_name in SWEEP_GRID:
        param_scores[param_name] = {}
        for val in SWEEP_GRID[param_name]:
            param_scores[param_name][str(val)] = []

    for r in diagnostic_results:
        if r.scores is None:
            continue
        for param_name in SWEEP_GRID:
            val = str(r.params.get(param_name, DEFAULTS[param_name]))
            if val in param_scores[param_name]:
                param_scores[param_name][val].append(r.scores.overall)

    top2: dict[str, list] = {}
    for param_name, val_scores in param_scores.items():
        avg_scores = []
        for val, scores in val_scores.items():
            if scores:
                avg_scores.append((val, np.mean(scores)))
        avg_scores.sort(key=lambda x: x[1], reverse=True)
        top_vals = [v for v, _ in avg_scores[:2]]

        original_vals = []
        for v in top_vals:
            grid_vals = SWEEP_GRID[param_name]
            for gv in grid_vals:
                if str(gv) == v:
                    original_vals.append(gv)
                    break
        top2[param_name] = original_vals if original_vals else [DEFAULTS[param_name]]

    param_names = list(top2.keys())
    value_lists = [top2[p] for p in param_names]

    combos = []
    for values in itertools.product(*value_lists):
        combo = dict(zip(param_names, values))
        combos.append(combo)

    seen = set()
    unique = []
    for c in combos:
        key = tuple(sorted(c.items()))
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return unique


def run_sweep(
    persona: str = "embry",
    track: str = "hawaiian_war_chant",
    phase: str = "full",
) -> SweepRun:
    """Execute a full parameter sweep."""
    run = SweepRun(persona=persona, track=track, phase=phase)
    run.started = datetime.now().isoformat()

    input_path = _find_vocals(persona, track)
    if input_path is None:
        console.print(f"[red]No vocals found for {persona}/{track}[/red]")
        return run

    ref_path = _find_human_reference(persona, track)
    if ref_path:
        console.print(f"[dim]Human reference: {ref_path.name}[/dim]")
    else:
        console.print("[dim]No human reference — using heuristic naturalness[/dim]")

    console.print("[dim]Building persona MFCC reference profile...[/dim]")
    ref_mfcc_mean, ref_mfcc_std = build_reference_profile(persona)

    results_dir = (
        STORAGE_ROOT / "personas" / persona / "hum-cache" / "lab-results"
    )
    results_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="hum_lab_") as tmpdir:
        tmpdir = Path(tmpdir)

        # Phase 1: Diagnostic
        if phase in ("diagnostic", "full"):
            combos = _build_diagnostic_combos()
            console.print(
                f"\n[bold cyan]Phase 1: Diagnostic[/bold cyan] — {len(combos)} combos"
            )

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("{task.completed}/{task.total}"),
                console=console,
            ) as progress:
                task = progress.add_task("Diagnostic sweep", total=len(combos))

                for i, params in enumerate(combos):
                    result = _run_single(
                        persona, track, params, input_path, ref_path,
                        ref_mfcc_mean, ref_mfcc_std, tmpdir, i,
                    )
                    run.results.append(result)
                    progress.update(task, advance=1)

                    if result.scores:
                        desc = _params_short(params)
                        score = result.scores.overall
                        color = "green" if score >= 0.6 else "yellow" if score >= 0.5 else "red"
                        progress.update(
                            task,
                            description=f"[{color}]{score:.2f}[/{color}] {desc}",
                        )

        # Phase 2: Cross
        if phase in ("cross", "full"):
            diagnostic_results = [r for r in run.results if r.scores]
            if not diagnostic_results:
                console.print("[yellow]No diagnostic results — skipping cross phase[/yellow]")
            else:
                cross_combos = _build_cross_combos(diagnostic_results)
                diag_keys = {
                    tuple(sorted(r.params.items()))
                    for r in run.results
                }
                cross_combos = [
                    c for c in cross_combos
                    if tuple(sorted(c.items())) not in diag_keys
                ]

                if cross_combos:
                    console.print(
                        f"\n[bold cyan]Phase 2: Cross[/bold cyan] — {len(cross_combos)} new combos"
                    )

                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TextColumn("{task.completed}/{task.total}"),
                        console=console,
                    ) as progress:
                        task = progress.add_task("Cross sweep", total=len(cross_combos))
                        offset = len(run.results)

                        for i, params in enumerate(cross_combos):
                            result = _run_single(
                                persona, track, params, input_path, ref_path,
                                ref_mfcc_mean, ref_mfcc_std, tmpdir, offset + i,
                            )
                            run.results.append(result)
                            progress.update(task, advance=1)

                            if result.scores:
                                desc = _params_short(params)
                                score = result.scores.overall
                                color = "green" if score >= 0.6 else "yellow" if score >= 0.5 else "red"
                                progress.update(
                                    task,
                                    description=f"[{color}]{score:.2f}[/{color}] {desc}",
                                )
                else:
                    console.print("[dim]All cross combos already covered in diagnostic[/dim]")

    run.completed = datetime.now().isoformat()

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    result_path = results_dir / f"sweep_{track}_{ts}.json"
    run.save(result_path)
    console.print(f"\n[bold green]Sweep complete.[/bold green] Results: {result_path}")

    _print_top_results(run, n=5)

    return run


def _run_single(
    persona: str,
    track: str,
    params: dict,
    input_path: Path,
    ref_path: Optional[Path],
    ref_mfcc_mean: np.ndarray,
    ref_mfcc_std: np.ndarray,
    tmpdir: Path,
    idx: int,
) -> SweepResult:
    """Run a single inference + evaluation."""
    output_path = tmpdir / f"output_{idx:03d}.wav"
    start = time.monotonic()

    ok = _rvc_infer_docker(persona, input_path, output_path, params)

    if not ok or not output_path.exists():
        return SweepResult(
            params=params,
            error="RVC inference failed",
            duration_s=round(time.monotonic() - start, 1),
        )

    scores = evaluate(
        output_path=output_path,
        input_path=input_path,
        reference_path=ref_path,
        persona=persona,
        ref_mfcc_mean=ref_mfcc_mean,
        ref_mfcc_std=ref_mfcc_std,
    )

    elapsed = round(time.monotonic() - start, 1)

    return SweepResult(
        params=params,
        scores=scores,
        output_path=str(output_path),
        duration_s=elapsed,
    )


def _params_short(params: dict) -> str:
    """Short description of params that differ from defaults."""
    diffs = []
    for k, v in params.items():
        if v != DEFAULTS.get(k):
            diffs.append(f"{k}={v}")
    return ", ".join(diffs) if diffs else "defaults"


def _print_top_results(run: SweepRun, n: int = 10) -> None:
    """Print a ranked table of top results."""
    ranked = run.ranked()
    if not ranked:
        console.print("[yellow]No scored results[/yellow]")
        return

    table = Table(title=f"Top {min(n, len(ranked))} Results")
    table.add_column("#", style="dim", width=3)
    table.add_column("Params", min_width=30)
    table.add_column("Timbre", justify="right")
    table.add_column("Melody", justify="right")
    table.add_column("Natural", justify="right")
    table.add_column("Artifacts", justify="right")
    table.add_column("Overall", justify="right", style="bold")
    table.add_column("Gates", justify="center")

    for i, r in enumerate(ranked[:n]):
        s = r.scores
        passed, _failures = s.passes_gates()
        gate_str = "[green]PASS[/green]" if passed else "[red]FAIL[/red]"

        overall_color = "green" if s.overall >= 0.6 else "yellow" if s.overall >= 0.5 else "red"

        table.add_row(
            str(i + 1),
            _params_short(r.params),
            f"{s.timbre:.3f}",
            f"{s.melody:.3f}",
            f"{s.naturalness:.3f}",
            f"{s.artifacts:.3f}",
            f"[{overall_color}]{s.overall:.3f}[/{overall_color}]",
            gate_str,
        )

    console.print(table)


def find_latest_sweep(persona: str, track: Optional[str] = None) -> Optional[Path]:
    """Find the most recent sweep results file."""
    results_dir = STORAGE_ROOT / "personas" / persona / "hum-cache" / "lab-results"
    if not results_dir.exists():
        return None

    pattern = f"sweep_{track}_*.json" if track else "sweep_*.json"
    files = sorted(results_dir.glob(pattern), reverse=True)
    return files[0] if files else None


def print_ranked(persona: str, track: Optional[str] = None, n: int = 20) -> None:
    """Load and display ranked results from the latest sweep."""
    path = find_latest_sweep(persona, track)
    if path is None:
        console.print(f"[yellow]No sweep results found for {persona}[/yellow]")
        return

    console.print(f"[dim]Loading: {path.name}[/dim]")
    run = SweepRun.load(path)
    _print_top_results(run, n=n)

    ranked = run.ranked()
    if ranked:
        passing = [r for r in ranked if r.scores.passes_gates()[0]]
        console.print(
            f"\n{len(ranked)} scored, {len(passing)} pass gates, "
            f"best overall: {ranked[0].scores.overall:.3f}"
        )
