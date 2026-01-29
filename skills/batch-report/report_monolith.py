#!/usr/bin/env python3
"""Batch Report - Post-run analysis and reporting for batch processing jobs.

Analyzes manifests, timings, and failures to generate comprehensive reports.
Optionally sends reports to agent-inbox for cross-project communication.

Usage:
    uv run python report.py analyze /path/to/batch/output
    uv run python report.py analyze /path/to/batch/output --send-to extractor
    uv run python report.py analyze /path/to/batch/output --json
    uv run python report.py summary /path/to/batch/output
    uv run python report.py failures /path/to/batch/output
    uv run python report.py state /path/to/.batch_state.json
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional
import random
import tempfile

import typer
from rich.console import Console
from rich.table import Table

try:
    import yaml
    HAS_YAML = True
except ImportError:
    yaml = None
    HAS_YAML = False

app = typer.Typer(help="Batch Report - Post-run analysis for batch jobs")
console = Console()


class BatchFormat(str, Enum):
    """Supported batch output formats."""
    extractor = "extractor"
    youtube = "youtube"
    generic = "generic"
    auto = "auto"


def detect_batch_format(output_dir: Path) -> BatchFormat:
    """Auto-detect batch format from directory structure."""
    # Check for extractor format (manifest.json, timings_summary.json)
    manifests = list(output_dir.glob("*/manifest.json"))
    if manifests and list(output_dir.glob("*/timings_summary.json")):
        return BatchFormat.extractor

    # Check for youtube transcripts format
    state_file = output_dir / ".batch_state.json"
    if state_file.exists():
        state = load_json(state_file)
        if "description" in state and "transcript" in state.get("description", "").lower():
            return BatchFormat.youtube

    # Check for generic state file
    if state_file.exists():
        return BatchFormat.generic

    # Fallback to generic
    return BatchFormat.generic

# Agent inbox location - search multiple paths
AGENT_INBOX_PATHS = [
    Path.home() / ".pi/skills/agent-inbox/inbox.py",
    Path.home() / ".claude/skills/agent-inbox/inbox.py",
]
AGENT_INBOX_SCRIPT = next((p for p in AGENT_INBOX_PATHS if p.exists()), AGENT_INBOX_PATHS[0])

# Batch config location
BATCH_CONFIG_PATH = Path.home() / ".pi" / "batch-report" / "batch_config.yaml"

SCILLM_SEARCH_PATHS = [
    Path.home() / ".pi/skills/scillm/run.sh",
    Path.home() / ".agent/skills/scillm/run.sh",
]
SCILLM_SCRIPT = next((p for p in SCILLM_SEARCH_PATHS if p.exists()), None)



def load_batch_config() -> dict:
    """Load batch configuration from YAML."""
    if not HAS_YAML:
        return {"batches": {}, "settings": {}}
    
    if not BATCH_CONFIG_PATH.exists():
        return {"batches": {}, "settings": {}}
    
    try:
        with open(BATCH_CONFIG_PATH) as f:
            return yaml.safe_load(f) or {"batches": {}, "settings": {}}
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load batch config: {e}[/]")
        return {"batches": {}, "settings": {}}


def get_batch_type_config(batch_type: str) -> dict:
    """Get configuration for a specific batch type."""
    config = load_batch_config()
    return config.get("batches", {}).get(batch_type, {})

def evaluate_llm_gates(gates: list, output_dir: Path) -> dict:
    """Evaluate LLM-based quality gates using scillm."""
    if not SCILLM_SCRIPT:
        return {g.get("metric", "llm_eval"): 0.0 for g in gates if g.get("type") == "llm"}

    results = {}
    
    for gate in gates:
        if gate.get("type") != "llm":
            continue
            
        metric_name = gate.get("metric", "llm_eval")
        prompt_template = gate.get("prompt", "Analyze this:\\n{sample}\\n\\nPASS or FAIL?")
        sample_size = gate.get("sample_size", 5)
        # Default to checking if any jsonl file exists, prioritize common names
        data_file_candidates = [gate.get("data_file")] if gate.get("data_file") else ["results.jsonl", "output.jsonl", "*.jsonl"]
        
        data_file = None
        for cand in data_file_candidates:
            if not cand: continue
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
            # print(f"DEBUG: Could not find data file for gate {metric_name} in {output_dir}")
            results[metric_name] = 0.0
            continue
            
        # Sample lines
        try:
            lines = data_file.read_text().splitlines()
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
                     prompt += "\\n\\nReply with PASS if this meets quality standards, otherwise FAIL."
                
                prompts.append({"prompt": prompt})

            # Run scillm batch
            with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp_in, \
                 tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tmp_out:
                
                tmp_in_path = Path(tmp_in.name)
                tmp_out_path = Path(tmp_out.name)
                
                try:
                    # Write inputs
                    for p in prompts:
                        tmp_in.write(json.dumps(p) + "\\n")
                    tmp_in.close()

                    # Run scillm (ensure capture_output=True to avoid clutter)
                    cmd = [str(SCILLM_SCRIPT), "batch", "--input", str(tmp_in_path), "--output", str(tmp_out_path), "--json"]
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
                            else:
                                pass
                        except (json.JSONDecodeError, ValueError, KeyError):
                            pass
                    
                    pass_rate = (pass_count / valid_responses) if valid_responses > 0 else 0.0
                    results[metric_name] = pass_rate
                    
                except subprocess.CalledProcessError as e:
                    console.print(f"[red]LLM evaluation error for {metric_name}: {e}[/]")
                    results[metric_name] = 0.0
                finally:
                    # Cleanup
                    if tmp_in_path.exists(): tmp_in_path.unlink()
                    if tmp_out_path.exists(): tmp_out_path.unlink()

        except Exception as e:
            console.print(f"[red]Error evaluating gate {metric_name}: {e}[/]")
            results[metric_name] = 0.0
            
    return results
def evaluate_quality_gates(analysis: dict, output_dir: Optional[Path] = None) -> list[dict]:
    """Evaluate quality gates for a batch analysis.
    
    Quality gates can come from:
    1. The state file itself (analysis['quality_gates'])
    2. The YAML config (fallback)
    3. Default gates if none specified
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
        gates = [
            {"metric": "success_rate", "min": 0.8, "severity": "warning", "message": "Success rate below 80%"}
        ]
    
    results = []
    
    # Calculate common metrics
    total = analysis.get("total", 0) or analysis.get("manifest_analysis", {}).get("total", 0)
    successful = analysis.get("successful", 0) or analysis.get("manifest_analysis", {}).get("successful", 0) or analysis.get("completed", 0)
    failed = analysis.get("failed", 0) or analysis.get("manifest_analysis", {}).get("failed", 0) or analysis.get("stats", {}).get("failed", 0)
    
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
        
        results.append({
            "metric": metric_name,
            "value": metric_value,
            "passed": passed,
            "severity": gate.get("severity", "warning"),
            "message": gate.get("message", reason) if not passed else "",
            "reason": reason,
        })
    
    return results


def format_quality_gates_report(gate_results: list[dict]) -> str:
    """Format quality gate results as markdown."""
    if not gate_results:
        return ""
    
    all_passed = all(r["passed"] for r in gate_results)
    
    lines = [
        "## Quality Gates",
        "",
        f"**Status:** {'✅ ALL PASSED' if all_passed else '❌ GATES FAILED'}",
        "",
        "| Gate | Value | Status | Severity |",
        "|------|-------|--------|----------|",
    ]
    
    for r in gate_results:
        status = "✅" if r["passed"] else "❌"
        severity = r["severity"].upper() if not r["passed"] else "-"
        value = f"{r['value']:.2f}" if isinstance(r['value'], float) else str(r['value'])
        lines.append(f"| {r['metric']} | {value} | {status} | {severity} |")
    
    # Add failure messages
    failures = [r for r in gate_results if not r["passed"]]
    if failures:
        lines.extend(["", "### Issues", ""])
        for r in failures:
            lines.append(f"- **[{r['severity'].upper()}]** {r['message']}")
    
    lines.append("")
    return "\n".join(lines)


def find_manifests(output_dir: Path) -> list[Path]:
    """Find all manifest.json files in output directory."""
    return list(output_dir.glob("*/manifest.json"))


def find_timings(output_dir: Path) -> list[Path]:
    """Find all timings_summary.json files."""
    return list(output_dir.glob("*/timings_summary.json"))


def find_final_reports(output_dir: Path) -> list[Path]:
    """Find all final_report.json files."""
    return list(output_dir.glob("*/14_report_generator/json_output/final_report.json"))


def load_json(path: Path) -> dict:
    """Load JSON file safely."""
    try:
        with open(path) as f:
            return json.load(f)
    except Exception as e:
        return {"_error": str(e), "_path": str(path)}


def analyze_manifests(manifests: list[Path]) -> dict:
    """Analyze manifest files for success/failure patterns."""
    results = {
        "total": len(manifests),
        "successful": 0,
        "partial": 0,
        "failed": 0,
        "items": [],
        "empty_content": [],
        "zero_metrics": [],
    }

    for manifest_path in manifests:
        manifest = load_json(manifest_path)
        item_id = manifest_path.parent.name

        if "_error" in manifest:
            results["failed"] += 1
            results["items"].append({"id": item_id, "status": "error", "error": manifest["_error"]})
            continue

        counts = manifest.get("counts", {})
        timings = manifest.get("timings_ms", {})

        # Check for empty/zero metrics
        total_blocks = counts.get("blocks02", 0)
        total_sections = counts.get("sections04", 0)

        if total_blocks == 0 and total_sections == 0:
            results["zero_metrics"].append(item_id)
            results["partial"] += 1
            results["items"].append({"id": item_id, "status": "partial", "reason": "zero_metrics"})
        else:
            results["successful"] += 1
            results["items"].append({
                "id": item_id,
                "status": "success",
                "blocks": total_blocks,
                "sections": total_sections,
                "tables": counts.get("tables05", 0),
                "total_time_ms": sum(timings.values()) if timings else 0,
            })

    return results


def analyze_timings(timings_files: list[Path]) -> dict:
    """Analyze timing data across all items."""
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
    sorted_steps = sorted(step_stats.items(), key=lambda x: x[1]["total_ms"], reverse=True)

    # Calculate percentage of total
    grand_total = sum(s["total_ms"] for s in step_stats.values())
    for step, stats in step_stats.items():
        stats["pct_of_total"] = (stats["total_ms"] / grand_total * 100) if grand_total else 0

    return {
        "step_stats": dict(sorted_steps),
        "total_times": total_times,
        "avg_total_ms": sum(total_times) / len(total_times) if total_times else 0,
        "max_total_ms": max(total_times) if total_times else 0,
        "min_total_ms": min(total_times) if total_times else 0,
    }


def analyze_failures(output_dir: Path) -> dict:
    """Analyze failure patterns."""
    failures = {
        "failed_urls": [],
        "patterns": Counter(),
        "details": [],
    }

    # Check failed_urls.txt
    failed_urls_file = output_dir / "failed_urls.txt"
    if failed_urls_file.exists():
        with open(failed_urls_file) as f:
            failures["failed_urls"] = [line.strip() for line in f if line.strip()]

    # Analyze logs for error patterns
    for log_file in output_dir.glob("*/extractor.log"):
        item_id = log_file.parent.name
        try:
            content = log_file.read_text()

            # Check for common error patterns
            if "CUDA out of memory" in content:
                failures["patterns"]["CUDA OOM"] += 1
                failures["details"].append({"id": item_id, "pattern": "CUDA OOM"})
            elif "Connection refused" in content:
                failures["patterns"]["Connection refused"] += 1
                failures["details"].append({"id": item_id, "pattern": "Connection refused"})
            elif "rate limit" in content.lower():
                failures["patterns"]["Rate limited"] += 1
                failures["details"].append({"id": item_id, "pattern": "Rate limited"})
            elif "Timeout" in content or "timeout" in content:
                failures["patterns"]["Timeout"] += 1
                failures["details"].append({"id": item_id, "pattern": "Timeout"})
            elif "Error" in content or "ERROR" in content:
                # Generic error
                failures["patterns"]["Other error"] += 1
        except Exception:
            pass

    return failures


def analyze_quality(final_reports: list[Path]) -> dict:
    """Analyze quality metrics from final reports."""
    quality = {
        "total_checked": len(final_reports),
        "pass": 0,
        "fail": 0,
        "empty_toc": 0,
        "no_sections": 0,
        "samples": [],
    }

    for report_path in final_reports[:20]:  # Sample first 20
        report = load_json(report_path)
        if "_error" in report:
            continue

        item_id = report_path.parent.parent.parent.name
        verification = report.get("verification", {})
        stats = report.get("statistics", {}).get("metrics", {})

        status = verification.get("status", "UNKNOWN")
        if status == "PASS":
            quality["pass"] += 1
        else:
            quality["fail"] += 1

        # Check for empty content
        if stats.get("total_sections", 0) == 0:
            quality["no_sections"] += 1

        toc = report.get("content_summary", {}).get("toc", [])
        if not toc:
            quality["empty_toc"] += 1

        quality["samples"].append({
            "id": item_id,
            "status": status,
            "sections": stats.get("total_sections", 0),
            "tables": stats.get("total_tables", 0),
            "requirements": stats.get("requirements_extracted", 0),
        })

    return quality


def analyze_state_file(state_path: Path) -> dict:
    """Analyze a generic .batch_state.json file."""
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


def generate_markdown_report(
    output_dir: Path,
    manifest_analysis: dict,
    timing_analysis: dict,
    failure_analysis: dict,
    quality_analysis: dict,
) -> str:
    """Generate markdown report."""
    run_id = output_dir.name if output_dir.name.startswith("run-") else output_dir.parent.name
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# Batch Report: {run_id}",
        f"",
        f"Generated: {now}",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total items | {manifest_analysis['total']} |",
        f"| Successful | {manifest_analysis['successful']} ({manifest_analysis['successful']/max(manifest_analysis['total'],1)*100:.1f}%) |",
        f"| Partial | {manifest_analysis['partial']} ({manifest_analysis['partial']/max(manifest_analysis['total'],1)*100:.1f}%) |",
        f"| Failed | {manifest_analysis['failed']} ({manifest_analysis['failed']/max(manifest_analysis['total'],1)*100:.1f}%) |",
        f"| Failed URLs | {len(failure_analysis['failed_urls'])} |",
        f"",
    ]

    # Timing analysis
    if timing_analysis["step_stats"]:
        avg_min = timing_analysis["avg_total_ms"] / 60000
        max_min = timing_analysis["max_total_ms"] / 60000

        lines.extend([
            f"## Timing Analysis",
            f"",
            f"- **Average time per item:** {avg_min:.1f} min",
            f"- **Max time:** {max_min:.1f} min",
            f"",
            f"### Bottlenecks (by total time)",
            f"",
            f"| Step | Avg (s) | Max (s) | % of Total |",
            f"|------|---------|---------|------------|",
        ])

        for step, stats in list(timing_analysis["step_stats"].items())[:10]:
            lines.append(
                f"| {step} | {stats['avg_ms']/1000:.1f} | {stats['max_ms']/1000:.1f} | {stats['pct_of_total']:.1f}% |"
            )
        lines.append("")

    # Failure patterns
    if failure_analysis["patterns"]:
        lines.extend([
            f"## Failure Patterns",
            f"",
            f"| Pattern | Count |",
            f"|---------|-------|",
        ])
        for pattern, count in failure_analysis["patterns"].most_common():
            lines.append(f"| {pattern} | {count} |")
        lines.append("")

    # Quality issues
    if quality_analysis["no_sections"] > 0 or quality_analysis["empty_toc"] > 0:
        lines.extend([
            f"## Quality Issues",
            f"",
            f"| Issue | Count |",
            f"|-------|-------|",
            f"| Zero sections extracted | {quality_analysis['no_sections']} |",
            f"| Empty table of contents | {quality_analysis['empty_toc']} |",
            f"| Zero metrics (false PASS) | {len(manifest_analysis['zero_metrics'])} |",
            f"",
        ])

    # Sample outputs
    if quality_analysis["samples"]:
        lines.extend([
            f"## Sample Outputs",
            f"",
            f"| ID | Status | Sections | Tables | Requirements |",
            f"|----|--------|----------|--------|--------------|",
        ])
        for sample in quality_analysis["samples"][:10]:
            lines.append(
                f"| {sample['id'][:16]} | {sample['status']} | {sample['sections']} | {sample['tables']} | {sample['requirements']} |"
            )
        lines.append("")

    # Recommendations
    lines.extend([
        f"## Recommendations",
        f"",
    ])

    # Generate recommendations based on analysis
    if timing_analysis["step_stats"]:
        top_bottleneck = list(timing_analysis["step_stats"].keys())[0] if timing_analysis["step_stats"] else None
        if top_bottleneck and "summarizer" in top_bottleneck.lower():
            lines.append(f"1. **Section summarizer bottleneck:** Consider batch summarization or `--skip-summaries` flag")
        if top_bottleneck and "table" in top_bottleneck.lower():
            lines.append(f"1. **Table processing bottleneck:** Add confidence threshold before VLM description")

    if len(manifest_analysis["zero_metrics"]) > 0:
        lines.append(f"2. **False PASS on zero content:** Add validation that blocks > 0 before marking PASS")

    if quality_analysis["no_sections"] > manifest_analysis["total"] * 0.1:
        lines.append(f"3. **High empty section rate:** Review PDF parsing for problematic document types")

    if failure_analysis["patterns"].get("CUDA OOM", 0) > 0:
        lines.append(f"4. **CUDA OOM errors:** Consider reducing batch size or model quantization")

    lines.append("")
    lines.append("---")
    lines.append(f"*Report generated by batch-report skill*")

    return "\n".join(lines)


def generate_generic_report(output_dir: Path, state_analysis: dict) -> str:
    """Generate a simple report from state file analysis."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines = [
        f"# Batch Report: {state_analysis['name']}",
        f"",
        f"Generated: {now}",
        f"",
    ]

    if state_analysis.get("description"):
        lines.extend([f"*{state_analysis['description']}*", ""])

    lines.extend([
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Status | {state_analysis['status']} |",
        f"| Total items | {state_analysis['total']} |",
        f"| Completed | {state_analysis['completed']} ({state_analysis['progress_pct']:.1f}%) |",
        f"| Failed | {state_analysis['failed']} |",
        f"| Remaining | {state_analysis['remaining']} |",
        f"",
    ])

    if state_analysis.get("rate_per_hour"):
        lines.extend([
            f"## Progress",
            f"",
            f"- **Rate:** {state_analysis['rate_per_hour']:.1f} items/hour",
        ])
        if state_analysis.get("eta_hours"):
            if state_analysis["eta_hours"] < 1:
                eta_str = f"{state_analysis['eta_hours'] * 60:.0f} minutes"
            else:
                eta_str = f"{state_analysis['eta_hours']:.1f} hours"
            lines.append(f"- **ETA:** {eta_str}")
        lines.append("")

    if state_analysis.get("current_item"):
        lines.extend([
            f"## Current",
            f"",
            f"Processing: `{state_analysis['current_item']}`",
            f"",
        ])

    lines.append("---")
    lines.append(f"*Report generated by batch-report skill*")

    return "\n".join(lines)


def send_to_agent_inbox(project: str, report: str, priority: str = "normal") -> Optional[str]:
    """Send report to agent-inbox."""
    if not AGENT_INBOX_SCRIPT.exists():
        console.print(f"[yellow]Warning: agent-inbox not found at {AGENT_INBOX_SCRIPT}[/]")
        return None

    try:
        result = subprocess.run(
            [
                sys.executable, str(AGENT_INBOX_SCRIPT),
                "send", "--to", project, "--type", "bug", "--priority", priority,
                report
            ],
            capture_output=True,
            text=True,
            cwd=AGENT_INBOX_SCRIPT.parent,
        )

        if result.returncode == 0:
            # Extract message ID from output
            for line in result.stdout.splitlines():
                if "Message sent:" in line:
                    return line.split("Message sent:")[-1].strip()
        else:
            console.print(f"[red]Failed to send to agent-inbox: {result.stderr}[/]")
    except Exception as e:
        console.print(f"[red]Error sending to agent-inbox: {e}[/]")

    return None


@app.command()
def analyze(
    output_dir: Path = typer.Argument(..., help="Batch output directory to analyze"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output file (default: stdout)"),
    send_to: Optional[str] = typer.Option(None, "--send-to", "-s", help="Send report to agent-inbox project"),
    priority: str = typer.Option("normal", "--priority", "-p", help="Priority for agent-inbox"),
    sample_count: int = typer.Option(5, "--sample", "-n", help="Number of samples to include"),
    format: BatchFormat = typer.Option(BatchFormat.auto, "--format", "-f", help="Batch format (auto-detected if not specified)"),
    as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON for piping"),
):
    """Generate full analysis report for a batch output directory."""
    if not output_dir.exists():
        console.print(f"[red]Error: Directory not found: {output_dir}[/]", stderr=True)
        raise typer.Exit(1)

    # Auto-detect format if needed
    detected_format = detect_batch_format(output_dir) if format == BatchFormat.auto else format

    if not as_json:
        console.print(f"[cyan]Analyzing batch output: {output_dir}[/]")
        console.print(f"  Format: {detected_format.value}")

    # Run format-specific analysis
    if detected_format == BatchFormat.extractor:
        manifests = find_manifests(output_dir)
        timings = find_timings(output_dir)
        final_reports = find_final_reports(output_dir)

        if not as_json:
            console.print(f"  Found {len(manifests)} manifests, {len(timings)} timing files, {len(final_reports)} reports")

        manifest_analysis = analyze_manifests(manifests)
        timing_analysis = analyze_timings(timings)
        failure_analysis = analyze_failures(output_dir)
        quality_analysis = analyze_quality(final_reports)

        if as_json:
            result = {
                "format": "extractor",
                "output_dir": str(output_dir),
                "manifest_analysis": manifest_analysis,
                "timing_analysis": timing_analysis,
                "failure_analysis": {
                    "failed_urls": failure_analysis["failed_urls"],
                    "patterns": dict(failure_analysis["patterns"]),
                    "details": failure_analysis["details"],
                },
                "quality_analysis": quality_analysis,
            }
            print(json.dumps(result, indent=2, default=str))
            return

        # Generate markdown report
        report = generate_markdown_report(
            output_dir, manifest_analysis, timing_analysis, failure_analysis, quality_analysis
        )
    else:
        # Generic or youtube format - use state file
        state_path = output_dir / ".batch_state.json"
        if not state_path.exists():
            console.print(f"[red]Error: No .batch_state.json found in {output_dir}[/]", stderr=True)
            raise typer.Exit(1)

        state_analysis = analyze_state_file(state_path)

        if as_json:
            result = {
                "format": detected_format.value,
                "output_dir": str(output_dir),
                "state_analysis": state_analysis,
            }
            print(json.dumps(result, indent=2, default=str))
            return

        # Generate simple report for generic/youtube
        report = generate_generic_report(output_dir, state_analysis)

    # Output
    if output:
        output.write_text(report)
        console.print(f"[green]Report written to: {output}[/]")
    else:
        console.print()
        console.print(report)

    # Send to agent-inbox
    if send_to:
        msg_id = send_to_agent_inbox(send_to, report, priority)
        if msg_id:
            console.print(f"[green]Report sent to agent-inbox: {msg_id}[/]")


@app.command()
def summary(
    output_dir: Path = typer.Argument(..., help="Batch output directory"),
    format: BatchFormat = typer.Option(BatchFormat.auto, "--format", "-f", help="Batch format"),
    as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Show quick summary stats."""
    if not output_dir.exists():
        console.print(f"[red]Error: Directory not found: {output_dir}[/]", stderr=True)
        raise typer.Exit(1)

    detected_format = detect_batch_format(output_dir) if format == BatchFormat.auto else format

    if detected_format == BatchFormat.extractor:
        manifests = find_manifests(output_dir)
        analysis = analyze_manifests(manifests)
        timings = analyze_timings(find_timings(output_dir))

        run_id = output_dir.name if output_dir.name.startswith("run-") else output_dir.parent.name
        success_rate = analysis["successful"] / max(analysis["total"], 1) * 100
        avg_min = timings["avg_total_ms"] / 60000 if timings["avg_total_ms"] else 0

        # Find top bottleneck
        top_step_name = None
        top_pct = 0
        if timings["step_stats"]:
            top_step_name = list(timings["step_stats"].keys())[0]
            top_pct = timings["step_stats"][top_step_name]["pct_of_total"]

        if as_json:
            result = {
                "batch": run_id,
                "format": "extractor",
                "total": analysis["total"],
                "successful": analysis["successful"],
                "partial": analysis["partial"],
                "failed": analysis["failed"],
                "success_rate": success_rate,
                "avg_time_min": avg_min,
                "top_bottleneck": top_step_name,
                "top_bottleneck_pct": top_pct,
            }
            print(json.dumps(result, indent=2))
            return

        top_step = f" | Slowest: {top_step_name} ({top_pct:.0f}%)" if top_step_name else ""
        console.print(f"[bold]Batch:[/] {run_id}")
        console.print(f"[bold]Total:[/] {analysis['total']} | [green]Success:[/] {analysis['successful']} | [yellow]Partial:[/] {analysis['partial']} | [red]Failed:[/] {analysis['failed']}")
        console.print(f"[bold]Success rate:[/] {success_rate:.1f}%")
        console.print(f"[bold]Avg time:[/] {avg_min:.1f} min{top_step}")
    else:
        # Generic/youtube - use state file
        state_path = output_dir / ".batch_state.json"
        if not state_path.exists():
            console.print(f"[red]Error: No .batch_state.json found[/]", stderr=True)
            raise typer.Exit(1)

        analysis = analyze_state_file(state_path)

        if as_json:
            print(json.dumps(analysis, indent=2, default=str))
            return

        console.print(f"[bold]Batch:[/] {analysis['name']}")
        console.print(f"[bold]Status:[/] {analysis['status']}")
        console.print(f"[bold]Total:[/] {analysis['total']} | [green]Completed:[/] {analysis['completed']} | [red]Failed:[/] {analysis['failed']} | Remaining: {analysis['remaining']}")
        console.print(f"[bold]Progress:[/] {analysis['progress_pct']:.1f}%")
        if analysis.get("rate_per_hour"):
            eta_str = f" | ETA: {analysis['eta_hours']:.1f}h" if analysis.get("eta_hours") else ""
            console.print(f"[bold]Rate:[/] {analysis['rate_per_hour']:.1f}/hour{eta_str}")


@app.command()
def failures(
    output_dir: Path = typer.Argument(..., help="Batch output directory"),
    as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """List failures with reasons."""
    if not output_dir.exists():
        console.print(f"[red]Error: Directory not found: {output_dir}[/]", stderr=True)
        raise typer.Exit(1)

    failure_analysis = analyze_failures(output_dir)

    if as_json:
        result = {
            "failed_urls": failure_analysis["failed_urls"],
            "patterns": dict(failure_analysis["patterns"]),
            "details": failure_analysis["details"],
        }
        print(json.dumps(result, indent=2))
        return

    table = Table(title="Failure Analysis")
    table.add_column("Pattern", style="red")
    table.add_column("Count", justify="right")

    for pattern, count in failure_analysis["patterns"].most_common():
        table.add_row(pattern, str(count))

    console.print(table)

    if failure_analysis["failed_urls"]:
        console.print(f"\n[bold]Failed URLs ({len(failure_analysis['failed_urls'])}):[/]")
        for url in failure_analysis["failed_urls"][:10]:
            console.print(f"  - {url[:80]}")
        if len(failure_analysis["failed_urls"]) > 10:
            console.print(f"  ... and {len(failure_analysis['failed_urls']) - 10} more")


@app.command()
def state(
    state_path: Path = typer.Argument(..., help="Path to .batch_state.json file"),
    as_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Analyze a standalone .batch_state.json file."""
    if not state_path.exists():
        console.print(f"[red]Error: State file not found: {state_path}[/]", stderr=True)
        raise typer.Exit(1)

    analysis = analyze_state_file(state_path)

    if "error" in analysis:
        console.print(f"[red]Error reading state file: {analysis['error']}[/]", stderr=True)
        raise typer.Exit(1)

    if as_json:
        print(json.dumps(analysis, indent=2, default=str))
        return

    # Pretty print
    console.print(f"[bold cyan]Batch:[/] {analysis['name']}")
    if analysis.get("description"):
        console.print(f"  {analysis['description']}")
    console.print()

    # Progress bar
    completed = analysis["completed"]
    total = analysis["total"]
    pct = analysis["progress_pct"]

    bar_width = 40
    filled = int(bar_width * pct / 100)
    bar = "[green]" + "█" * filled + "[/]" + "░" * (bar_width - filled)

    console.print(f"  {bar} {pct:.1f}%")
    console.print()

    console.print(f"  [bold]Status:[/] {analysis['status']}")
    console.print(f"  [bold]Completed:[/] {completed}/{total}")
    console.print(f"  [bold]Failed:[/] {analysis['failed']}")
    console.print(f"  [bold]Remaining:[/] {analysis['remaining']}")

    if analysis.get("rate_per_hour"):
        console.print(f"\n  [bold]Rate:[/] {analysis['rate_per_hour']:.1f} items/hour")
        if analysis.get("eta_hours"):
            if analysis["eta_hours"] < 1:
                eta_str = f"{analysis['eta_hours'] * 60:.0f} minutes"
            else:
                eta_str = f"{analysis['eta_hours']:.1f} hours"
            console.print(f"  [bold]ETA:[/] {eta_str}")

    if analysis.get("current_item"):
        console.print(f"\n  [bold]Current:[/] {analysis['current_item']}")

    # Quality Gates
    gates_results = evaluate_quality_gates(analysis, output_dir=state_path.parent)
    if gates_results:
        console.print()
        console.print("[bold]Quality Gates:[/]")
        
        table = Table(box=None)
        table.add_column("Metric", style="cyan")
        table.add_column("Value")
        table.add_column("Status")
        table.add_column("Details")
        
        for r in gates_results:
            status = "[green]PASS[/]" if r["passed"] else f"[red]FAIL ({r['severity'].upper()})[/]"
            value = f"{r['value']:.2f}" if isinstance(r['value'], float) else str(r['value'])
            msg = r["message"] if not r["passed"] else ""
            table.add_row(r["metric"], value, status, msg)
            
        console.print(table)


if __name__ == "__main__":
    app()
