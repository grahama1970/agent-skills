"""Dispatch strategies via /code-runner self-improvement loop.

Each strategy becomes a /code-runner task spec. /code-runner handles
error correction, strategy escalation, and /memory integration.
Falls back to direct subprocess if /code-runner is unavailable.

Results are always read from output JSON files on disk.
"""
from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from loguru import logger

from .manifest import Strategy

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
CODE_RUNNER = SKILLS_DIR / "code-runner"


@dataclass
class StrategyResult:
    name: str
    f1: float = 0.0
    exit_code: int = -1
    duration_ms: int = 0
    output_file: str = ""
    raw_json: dict = field(default_factory=dict)
    error: str = ""


def _build_benchmark_cmd(strategy: Strategy, data_dir: str, output_json: str) -> str:
    """Build exact benchmark shell command from strategy HPs."""
    skill_dir = SKILLS_DIR / "classifier-lab"
    data_path = Path(data_dir)

    # Text modality: use text_classifier.py directly (benchmark.py is vision-oriented)
    if strategy.modality == "text":
        create_clf = SKILLS_DIR / "create-classifier"
        train_file = data_path / "train.jsonl"
        val_file = data_path / "val.jsonl"
        if not val_file.exists():
            val_file = train_file  # fallback: use train as val
        return (
            f"cd {create_clf} && unset VIRTUAL_ENV && uv run python templates/text_classifier.py "
            f"--train-file {train_file} "
            f"--val-file {val_file} "
            f"--output-dir /tmp/thunderdome-model-{strategy.name} "
            f"--model {strategy.backbones} "
            f"--epochs {strategy.epochs} "
            f"--batch-size {strategy.batch_size} "
            f"--learning-rate {strategy.lr} "
            f"--max-length 128 "
            f"--early-stopping 3 "
            f"&& python3 -c \""
            f"import json; s=json.load(open('/tmp/thunderdome-model-{strategy.name}/training_summary.json')); "
            f"m=s.get('val_metrics',{{}}); "
            f"json.dump({{'selected_metrics': {{'macro_f1': m.get('eval_f1_macro',0)}}, 'status': 'ok'}}, open('{output_json}','w'))\""
        )

    # Vision/tabular: use --data-dir
    return (
        f"cd {skill_dir} && unset VIRTUAL_ENV && uv run python scripts/benchmark.py "
        f"--data-dir {data_dir} "
        f"--modality {strategy.modality} "
        f"--backbones {strategy.backbones} "
        f"--epochs {strategy.epochs} "
        f"--lr {strategy.lr} "
        f"--batch-size {strategy.batch_size} "
        f"--mixup-alpha {strategy.mixup_alpha} "
        f"--cutmix-alpha {strategy.cutmix_alpha} "
        f"--random-erasing {strategy.random_erasing} "
        f"--dropout {strategy.dropout} "
        f"--weight-decay {strategy.weight_decay} "
        f"--label-smoothing {strategy.label_smoothing} "
        f"--output-json {output_json} "
        f"--store-memory"
    )


def _build_task_spec(strategy: Strategy, data_dir: str, round_num: int) -> dict:
    """Build a /code-runner task spec JSON for this strategy."""
    output_json = f"/tmp/thunderdome-{strategy.name}-r{round_num}.json"
    bench_cmd = _build_benchmark_cmd(strategy, data_dir, output_json)
    return {
        "task_id": f"thunderdome-{strategy.name}-r{round_num}",
        "title": f"Thunderdome: {strategy.name} round {round_num}",
        "prompt": (
            f"Run this classifier benchmark command. If it fails, read the error "
            f"and fix the issue (e.g. adjust batch size for OOM, fix import errors). "
            f"The command should produce {output_json} with F1 score.\n\n"
            f"Command: {bench_cmd}"
        ),
        "backend": "text",
        "cwd": str(SKILLS_DIR / "classifier-lab"),
        "output_dir": f"/tmp/thunderdome-cr-{strategy.name}-r{round_num}",
        "definition_of_done": {
            "command": (
                f"{bench_cmd} && python3 -c \""
                f"import json; d=json.load(open('{output_json}')); "
                f"f1=d['selected_metrics']['macro_f1']; "
                f"assert f1 > 0.1, f'F1={{f1}} is too low — check data format and modality'\""
            ),
            "assertion": f"F1 > 0.1 in {output_json}",
        },
        "allowlist_optional": True,  # code-runner can edit any file if needed for fixes
    }


def _run_via_code_runner(spec: dict) -> int:
    """Run a task spec through /code-runner. Returns exit code."""
    spec_path = Path(spec["output_dir"]) / "task-spec.json"
    spec_path.parent.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec, indent=2))

    cmd = f"cd {CODE_RUNNER} && ./run.sh run {spec_path} --max-rounds 3"
    proc = subprocess.run(
        ["bash", "-lc", cmd],
        capture_output=True, text=True,
        env={**os.environ, "VIRTUAL_ENV": ""},
    )
    return proc.returncode


async def _run_one(strategy: Strategy, data_dir: str, round_num: int,
                   use_code_runner: bool) -> StrategyResult:
    """Run one strategy concurrently via async subprocess."""
    start = time.monotonic()
    result = StrategyResult(name=strategy.name)
    output_json = f"/tmp/thunderdome-{strategy.name}-r{round_num}.json"
    result.output_file = output_json

    # Remove stale output from prior rounds
    if Path(output_json).exists():
        Path(output_json).unlink()

    bench_cmd = _build_benchmark_cmd(strategy, data_dir, output_json)
    logger.info(f"[{strategy.name}] async: {bench_cmd[:120]}...")

    env = {**os.environ}
    env.pop("VIRTUAL_ENV", None)

    try:
        proc = await asyncio.create_subprocess_exec(
            "bash", "-c", bench_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=600)
        result.exit_code = proc.returncode or 0
        if result.exit_code != 0 and stderr:
            logger.warning(f"  [{strategy.name}] stderr: {stderr.decode()[-300:]}")
    except asyncio.TimeoutError:
        logger.warning(f"  [{strategy.name}] timed out after 600s")
        result.exit_code = -1
        result.error = "timeout"
    except Exception as e:
        logger.warning(f"  [{strategy.name}] failed: {e}")
        result.exit_code = -1
        result.error = str(e)

    result.duration_ms = int((time.monotonic() - start) * 1000)

    # Read result from disk
    if Path(output_json).exists():
        try:
            data = json.loads(Path(output_json).read_text())
            result.raw_json = data
            result.f1 = data.get("selected_metrics", {}).get("macro_f1", 0.0)
            logger.info(f"[{strategy.name}] F1={result.f1:.4f} ({result.duration_ms // 1000}s)")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"[{strategy.name}] cannot read {output_json}: {e}")
    else:
        logger.warning(f"[{strategy.name}] no output file")

    return result


def dispatch_strategies(
    strategies: list[Strategy],
    data_dir: str,
    round_num: int,
    use_code_runner: bool = False,
) -> list[StrategyResult]:
    """Run N strategies concurrently via async subprocess. All backbones race in parallel."""
    logger.info(f"Dispatching {len(strategies)} strategies concurrently (async subprocess)")

    async def _run_all():
        return await asyncio.gather(*[
            _run_one(s, data_dir, round_num, False) for s in strategies
        ])

    results = asyncio.run(_run_all())

    for r in results:
        status = f"F1={r.f1:.4f}" if r.f1 > 0 else f"FAILED" if r.error else "no output"
        logger.info(f"Strategy '{r.name}': {status} ({r.duration_ms // 1000}s)")

    return list(results)
