"""
Prompt Lab Skill - Utilities
Task-monitor integration and helper functions.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from evaluation import EvalSummary


def notify_task_monitor(task_name: str, passed: bool, summary: "EvalSummary") -> None:
    """
    Notify task-monitor of evaluation result for quality gate.

    Args:
        task_name: Name of the task to update
        passed: Whether the quality gate passed
        summary: Evaluation summary with metrics
    """
    try:
        from rich.console import Console
        console = Console()
    except ImportError:
        console = None

    try:
        import httpx

        status = "passed" if passed else "failed"
        payload = {
            "name": task_name,
            "status": status,
            "metrics": {
                "avg_f1": summary.avg_f1,
                "correction_success_rate": summary.correction_success_rate,
                "total_rejected": summary.total_rejected,
            },
            "message": f"Prompt validation {status}: F1={summary.avg_f1:.3f}, corrections={summary.total_correction_rounds}",
        }

        try:
            resp = httpx.post("http://localhost:8765/tasks/update", json=payload, timeout=2.0)
            if resp.status_code == 200 and console:
                console.print(f"[dim]Task-monitor notified: {task_name} = {status}[/dim]")
        except httpx.ConnectError:
            if console:
                console.print("[dim]Task-monitor not running, skipping notification[/dim]")

    except ImportError:
        if console:
            console.print("[dim]httpx not installed, skipping task-monitor notification[/dim]")
