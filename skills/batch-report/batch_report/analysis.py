"""Timing and failure analysis for batch-report skill.

This module handles analysis of timing data, failure patterns, state files,
quality gates evaluation including LLM-based gates.
"""
from __future__ import annotations

import json
import random
import subprocess
import tempfile
import os
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from batch_report.config import DEFAULT_QUALITY_GATES, SCILLM_SCRIPT
from batch_report.utils import get_batch_type_config, load_json

console = Console()


def analyze_timings(timings_files: list[Path]) -> dict:
    """Analyze timing data across all items.

    Args:
        timings_files: List of paths to timings_summary.json files.

    Returns:
        Timing analysis dict with step stats and totals.
    """
    step_times = defaultdict(list)
    total_times = []

    for timing_path in timings_files:
        timing = load_json(timing_path)
        if "_error" in timing:
            continue

        total_ms = timing.get("total_ms", 0)
        if total_ms:
            total_times.append(total_ms)

        for stage in timing.get("stages", []):
            name = stage.get("name", "unknown")
            latency = stage.get("latency_ms", 0)
            step_times[name].append(latency)

    # Calculate stats per step
    step_stats = {}
    for step, times in step_times.items():
        if times:
            step_stats[step] = {
                "avg_ms": sum(times) / len(times),
                "max_ms": max(times),
                "min_ms": min(times),
                "count": len(times),
                "total_ms": sum(times),
            }

    # Sort by total time (bottlenecks first)
    sorted_steps = sorted(
        step_stats.items(), key=lambda x: x[1]["total_ms"], reverse=True
    )

    # Calculate percentage of total
    grand_total = sum(s["total_ms"] for s in step_stats.values())
    for step, stats in step_stats.items():
        stats["pct_of_total"] = (
            (stats["total_ms"] / grand_total * 100) if grand_total else 0
        )

    return {
        "step_stats": dict(sorted_steps),
        "total_times": total_times,
        "avg_total_ms": sum(total_times) / len(total_times) if total_times else 0,
        "max_total_ms": max(total_times) if total_times else 0,
        "min_total_ms": min(total_times) if total_times else 0,
    }


def analyze_failures(output_dir: Path) -> dict:
    """Analyze failure patterns.

    Args:
        output_dir: Path to the batch output directory.

    Returns:
        Failure analysis dict with URLs, patterns, and details.
    """
    failures = {
        "failed_urls": [],
        "patterns": Counter(),
        "details": [],
    }

    # Check failed_urls.txt
    failed_urls_file = output_dir / "failed_urls.txt"
    if failed_urls_file.exists():
        with open(failed_urls_file, encoding="utf-8", errors="ignore") as f:
            failures["failed_urls"] = [line.strip() for line in f if line.strip()]

    # Analyze logs for error patterns
    for log_file in output_dir.glob("*/extractor.log"):
        item_id = log_file.parent.name
        try:
            found = None
            with open(log_file, encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if "CUDA out of memory" in line:
                        found = "CUDA OOM"; break
                    elif "Connection refused" in line:
                        found = "Connection refused"; break
                    elif "rate limit" in line.lower():
                        found = "Rate limited"; break
                    elif "Timeout" in line or "timeout" in line:
                        found = "Timeout"; break
                    elif "Error" in line or "ERROR" in line:
                        found = "Other error"; break
            if found:
                failures["patterns"][found] += 1
                failures["details"].append({"id": item_id, "pattern": found})
        except Exception:
            pass

    return failures


def analyze_state_file(state_path: Path) -> dict:
    """Analyze a generic .batch_state.json file.

    Args:
        state_path: Path to the .batch_state.json file.

    Returns:
        State analysis dict with progress metrics and ETAs.
    """
    state = load_json(state_path)
    if "_error" in state:
        return {"error": state["_error"]}

    # Calculate derived metrics
    total = state.get("total", 0)
    completed = state.get("completed", 0)
    failed = state.get("failed", 0)
    remaining = total - completed - failed if total else 0

    # Calculate progress
    progress_pct = (completed / total * 100) if total else 0

    # Calculate rate if timestamps available
    started = state.get("started_at")
    last_update = state.get("last_update") or state.get("updated_at")
    rate_per_hour = None
    eta_hours = None

    if started and last_update and completed > 0:
        try:
            start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
            update_dt = datetime.fromisoformat(last_update.replace("Z", "+00:00"))
            elapsed_hours = (update_dt - start_dt).total_seconds() / 3600
            if elapsed_hours > 0:
                rate_per_hour = completed / elapsed_hours
                if rate_per_hour > 0 and remaining > 0:
                    eta_hours = remaining / rate_per_hour
        except (ValueError, TypeError):
            pass

    return {
        "name": state.get("name", state_path.parent.name),
        "description": state.get("description", ""),
        "status": state.get("status", "unknown"),
        "total": total,
        "completed": completed,
        "failed": failed,
        "remaining": remaining,
        "progress_pct": progress_pct,
        "started_at": started,
        "last_update": last_update,
        "rate_per_hour": rate_per_hour,
        "eta_hours": eta_hours,
        "current_item": state.get("current_item"),
        "stats": state.get("stats", {}),
        "quality_gates": state.get("quality_gates", []),
        "batch_type": state.get("batch_type"),
    }


def evaluate_llm_gates(gates: list, output_dir: Path) -> dict:
    """Evaluate LLM-based quality gates using scillm.

    Args:
        gates: List of gate definitions.
        output_dir: Path to the batch output directory.

    Returns:
        Dict mapping metric names to pass rates (0.0-1.0).
    """
    if not SCILLM_SCRIPT:
        return {g.get("metric", "llm_eval"): 0.0 for g in gates if g.get("type") == "llm"}

    results = {}

    for gate in gates:
        if gate.get("type") != "llm":
            continue

        metric_name = gate.get("metric", "llm_eval")
        prompt_template = gate.get(
            "prompt", "Analyze this:\\n{sample}\\n\\nPASS or FAIL?"
        )
        sample_size = gate.get("sample_size", 5)
        # Default to checking if any jsonl file exists, prioritize common names
        data_file_candidates = (
            [gate.get("data_file")]
            if gate.get("data_file")
            else ["results.jsonl", "output.jsonl", "*.jsonl"]
        )

        data_file = None
        for cand in data_file_candidates:
            if not cand:
                continue
            if "*" in cand:
                matches = list(output_dir.glob(cand))
                if matches:
                    data_file = matches[0]
                    break
            else:
                f = output_dir / cand
                if f.exists():
                    data_file = f
                    break

        if not data_file:
            results[metric_name] = 0.0
            continue

        # Sample lines
        try:
            lines = data_file.read_text(encoding="utf-8", errors="ignore").splitlines()
            if not lines:
                results[metric_name] = 0.0
                continue

            # Simple random sampling
            samples = random.sample(lines, min(len(lines), sample_size))

            # Prepare prompts
            prompts = []
            for sample_text in samples:
                # Try to format as nice JSON if possible
                try:
                    loaded = json.loads(sample_text)
                    formatted_sample = json.dumps(loaded, indent=2)
                except (json.JSONDecodeError, ValueError):
                    formatted_sample = sample_text

                prompt = prompt_template.replace("{sample}", formatted_sample)
                if "PASS" not in prompt and "FAIL" not in prompt:
                    prompt += (
                        "\\n\\nReply with PASS if this meets quality standards, "
                        "otherwise FAIL."
                    )

                prompts.append({"prompt": prompt})

            # Run scillm batch
            with (
                tempfile.NamedTemporaryFile(
                    mode="w", suffix=".jsonl", delete=False
                ) as tmp_in,
                tempfile.NamedTemporaryFile(
                    mode="w", suffix=".jsonl", delete=False
                ) as tmp_out,
            ):
                tmp_in_path = Path(tmp_in.name)
                tmp_out_path = Path(tmp_out.name)

                try:
                    # Write inputs
                    for p in prompts:
                        tmp_in.write(json.dumps(p) + "\\n")
                    tmp_in.close()

                    # Run scillm (ensure capture_output=True to avoid clutter)
                    base_args = [
                        "batch",
                        "--input",
                        str(tmp_in_path),
                        "--output",
                        str(tmp_out_path),
                        "--json",
                    ]
                    cmd = [str(SCILLM_SCRIPT)] + base_args
                    try:
                        if not os.access(SCILLM_SCRIPT, os.X_OK):
                            cmd = ["bash", str(SCILLM_SCRIPT)] + base_args
                    except Exception:
                        cmd = ["bash", str(SCILLM_SCRIPT)] + base_args
                    subprocess.run(cmd, check=True, capture_output=True)

                    # Read results
                    out_lines = tmp_out_path.read_text().splitlines()
                    pass_count = 0
                    valid_responses = 0

                    for line in out_lines:
                        try:
                            res = json.loads(line)
                            if res.get("ok"):
                                content = res.get("content", "").upper()
                                # Check for PASS keyword
                                if "PASS" in content:
                                    pass_count += 1
                                valid_responses += 1
                        except (json.JSONDecodeError, ValueError, KeyError):
                            pass

                    pass_rate = (
                        (pass_count / valid_responses) if valid_responses > 0 else 0.0
                    )
                    results[metric_name] = pass_rate

                except subprocess.CalledProcessError as e:
                    console.print(
                        f"[red]LLM evaluation error for {metric_name}: {e}[/]"
                    )
                    results[metric_name] = 0.0
                finally:
                    # Cleanup
                    if tmp_in_path.exists():
                        tmp_in_path.unlink()
                    if tmp_out_path.exists():
                        tmp_out_path.unlink()

        except Exception as e:
            console.print(f"[red]Error evaluating gate {metric_name}: {e}[/]")
            results[metric_name] = 0.0

    return results


def evaluate_quality_gates(
    analysis: dict, output_dir: Optional[Path] = None
) -> list[dict]:
    """Evaluate quality gates for a batch analysis.

    Quality gates can come from:
    1. The state file itself (analysis['quality_gates'])
    2. The YAML config (fallback)
    3. Default gates if none specified

    Args:
        analysis: Analysis dict from analyze_state_file or similar.
        output_dir: Optional path to batch output directory for LLM gates.

    Returns:
        List of gate result dicts with metric, value, passed, severity, message.
    """
    batch_type = analysis.get("batch_type")

    # First check if gates are in the analysis/state itself
    gates = analysis.get("quality_gates", [])

    # Fallback to YAML config if no gates in state
    if not gates and batch_type:
        config = get_batch_type_config(batch_type)
        gates = config.get("quality_gates", [])

    # Default gates if nothing specified
    if not gates:
        gates = DEFAULT_QUALITY_GATES

    results = []

    # Calculate common metrics
    total = analysis.get("total", 0) or analysis.get("manifest_analysis", {}).get(
        "total", 0
    )
    successful = (
        analysis.get("successful", 0)
        or analysis.get("manifest_analysis", {}).get("successful", 0)
        or analysis.get("completed", 0)
    )
    failed = (
        analysis.get("failed", 0)
        or analysis.get("manifest_analysis", {}).get("failed", 0)
        or analysis.get("stats", {}).get("failed", 0)
    )

    metrics = {
        "success_rate": (successful / total) if total > 0 else 0,
        "failure_rate": (failed / total) if total > 0 else 0,
        "total": total,
        "successful": successful,
        "failed": failed,
        "completed": successful,
    }

    # Add any analysis-specific metrics
    if "state_analysis" in analysis:
        state = analysis["state_analysis"]
        metrics["progress_pct"] = state.get("progress_pct", 0)
        metrics["rate_per_hour"] = state.get("rate_per_hour", 0)

    # Add stats metrics
    if "stats" in analysis:
        for k, v in analysis["stats"].items():
            if isinstance(v, (int, float)):
                metrics[k] = v

    # Evaluate LLM gates if output_dir available
    if output_dir:
        llm_results = evaluate_llm_gates(gates, output_dir)
        metrics.update(llm_results)

    for gate in gates:
        metric_name = gate.get("metric", "")
        metric_value = metrics.get(metric_name, 0)

        passed = True
        reason = ""

        if "min" in gate:
            if metric_value < gate["min"]:
                passed = False
                reason = f"{metric_name}={metric_value:.2f} < min={gate['min']}"

        if "max" in gate:
            if metric_value > gate["max"]:
                passed = False
                reason = f"{metric_name}={metric_value:.2f} > max={gate['max']}"

        results.append(
            {
                "metric": metric_name,
                "value": metric_value,
                "passed": passed,
                "severity": gate.get("severity", "warning"),
                "message": gate.get("message", reason) if not passed else "",
                "reason": reason,
            }
        )

    return results
