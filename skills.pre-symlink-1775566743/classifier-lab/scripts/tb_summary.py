"""Read TensorBoard event files and output JSON summary for agent monitoring.

Usage:
    python tb_summary.py [--logdir /tmp/classifier_lab_tb] [--json]
    python tb_summary.py status [--json]

Outputs latest training metrics: loss curve, learning rate, best F1,
epoch count, and convergence assessment (improving/plateau/diverging).
"""
import json
import subprocess
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="TensorBoard training monitor for classifier-lab")


def read_tb_events(logdir: Path) -> dict:
    """Read TensorBoard events and return structured summary."""
    results = {}

    if not logdir.exists():
        return {"error": f"TB logdir does not exist: {logdir}", "runs": {}}

    try:
        from tensorboard.backend.event_processing.event_accumulator import (
            EventAccumulator,
        )
    except ImportError:
        try:
            from tbparse import SummaryReader

            reader = SummaryReader(str(logdir))
            df = reader.scalars
            if df.empty:
                return {"error": "No scalar data found", "runs": {}}
            for run_name, group in df.groupby("dir_name"):
                run_data = {}
                for tag, tag_group in group.groupby("tag"):
                    values = tag_group["value"].tolist()
                    steps = tag_group["step"].tolist()
                    run_data[tag] = {
                        "latest": values[-1] if values else None,
                        "min": min(values) if values else None,
                        "max": max(values) if values else None,
                        "count": len(values),
                        "first_step": steps[0] if steps else None,
                        "last_step": steps[-1] if steps else None,
                    }
                results[str(run_name)] = run_data
            return {"runs": results}
        except ImportError:
            return {
                "error": "Neither tensorboard nor tbparse installed. Run: pip install tbparse",
                "runs": {},
            }

    for run_dir in sorted(logdir.iterdir()):
        if not run_dir.is_dir():
            continue
        ea = EventAccumulator(str(run_dir))
        ea.Reload()
        run_data = {}
        for tag in ea.Tags().get("scalars", []):
            events = ea.Scalars(tag)
            values = [e.value for e in events]
            steps = [e.step for e in events]
            run_data[tag] = {
                "latest": values[-1] if values else None,
                "min": min(values) if values else None,
                "max": max(values) if values else None,
                "count": len(values),
                "first_step": steps[0] if steps else None,
                "last_step": steps[-1] if steps else None,
            }
        if run_data:
            results[run_dir.name] = run_data

    return {"runs": results}


def assess_convergence(run_data: dict) -> str:
    """Assess if training is converging, plateaued, or diverging."""
    loss = run_data.get("train/loss", {})
    if not loss or loss["count"] < 10:
        return "insufficient_data"

    if loss["latest"] is not None and loss["min"] is not None:
        if loss["latest"] <= loss["min"] * 1.05:
            return "converging"
        elif loss["latest"] > loss["max"] * 0.95:
            return "diverging"
        else:
            return "plateau"
    return "unknown"


def format_summary(data: dict) -> str:
    """Human-readable summary."""
    if "error" in data:
        return f"ERROR: {data['error']}"

    lines = []
    for run_name, metrics in data.get("runs", {}).items():
        lines.append(f"\n=== {run_name} ===")
        loss = metrics.get("train/loss", {})
        lr = metrics.get("train/lr", {})
        convergence = assess_convergence(metrics)

        if loss:
            lines.append(
                f"  Loss: latest={loss['latest']:.4f}  min={loss['min']:.4f}  "
                f"max={loss['max']:.4f}  steps={loss['count']}"
            )
        if lr:
            lines.append(f"  LR:   latest={lr['latest']:.6f}  steps={lr['count']}")
        lines.append(f"  Convergence: {convergence}")

        for tag, vals in sorted(metrics.items()):
            if tag in ("train/loss", "train/lr", "_convergence"):
                continue
            lines.append(
                f"  {tag}: latest={vals['latest']:.4f}  "
                f"min={vals['min']:.4f}  max={vals['max']:.4f}"
            )

    if not lines:
        return "No training runs found in TB logdir."
    return "\n".join(lines)


def find_active_benchmarks() -> list[dict]:
    """Find running classifier-lab benchmark processes and their output files."""
    result = subprocess.run(
        ["pgrep", "-af", "benchmark.py"],
        capture_output=True,
        text=True,
    )
    active = []
    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        pid, cmd = parts
        output_path = None
        if "--output-json" in cmd:
            idx = cmd.index("--output-json")
            rest = cmd[idx:].split()
            if len(rest) > 1:
                output_path = rest[1]
        labels_path = None
        if "--labels-jsonl" in cmd:
            idx = cmd.index("--labels-jsonl")
            rest = cmd[idx:].split()
            if len(rest) > 1:
                labels_path = rest[1]
        active.append(
            {
                "pid": int(pid),
                "output_json": output_path,
                "labels_jsonl": labels_path,
                "complete": Path(output_path).exists() if output_path else False,
            }
        )
    return active


@app.command()
def tb(
    logdir: str = typer.Option("/tmp/classifier_lab_tb", help="TensorBoard log directory"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Read TensorBoard events and show training progress."""
    data = read_tb_events(Path(logdir))
    if output_json:
        for run_name, metrics in data.get("runs", {}).items():
            data["runs"][run_name]["_convergence"] = assess_convergence(metrics)
        print(json.dumps(data, indent=2))
    else:
        print(format_summary(data))


@app.command()
def status(
    logdir: str = typer.Option("/tmp/classifier_lab_tb", help="TensorBoard log directory"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show status of active/completed benchmark runs."""
    active = find_active_benchmarks()
    completed = []
    running = []
    for b in active:
        if b["complete"] and b["output_json"]:
            try:
                data = json.loads(Path(b["output_json"]).read_text())
                completed.append(
                    {
                        "pid": b["pid"],
                        "output": b["output_json"],
                        "macro_f1": data.get("macro_f1"),
                        "accuracy": data.get("accuracy"),
                        "backbone": data.get("backbone"),
                        "wilson_lb": data.get("wilson_lb"),
                    }
                )
            except Exception as e:
                completed.append(
                    {"pid": b["pid"], "output": b["output_json"], "error": str(e)}
                )
        else:
            running.append(b)

    status_data = {
        "running": running,
        "completed": completed,
        "tb_logdir_exists": Path(logdir).exists(),
    }

    if output_json:
        print(json.dumps(status_data, indent=2))
    else:
        print(f"Active benchmarks: {len(running)}")
        for r in running:
            print(f"  PID {r['pid']}: {r['labels_jsonl']} -> {r['output_json']}")
        print(f"\nCompleted benchmarks: {len(completed)}")
        for c in completed:
            if "error" in c:
                print(f"  PID {c['pid']}: ERROR: {c['error']}")
            else:
                print(
                    f"  PID {c['pid']}: F1={c.get('macro_f1', '?'):.4f}  "
                    f"acc={c.get('accuracy', '?'):.4f}  "
                    f"wilson={c.get('wilson_lb', '?'):.4f}  "
                    f"backbone={c.get('backbone', '?')}"
                )
        print(f"\nTB logdir exists: {status_data['tb_logdir_exists']}")


if __name__ == "__main__":
    app()
