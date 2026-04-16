"""
Prompt Lab Skill - Utilities
Task-monitor integration and helper functions.
"""
from typing import TYPE_CHECKING, Dict, Any, Optional

if TYPE_CHECKING:
    from evaluation import EvalSummary


def notify_task_monitor(
    task_name: str, 
    status: str, 
    metrics: Dict[str, Any], 
    message: str,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Notify task-monitor of evaluation result or watchdog status.

    Args:
        task_name: Name of the task to update
        status: Status string ('passed', 'failed', 'running')
        metrics: Detailed metrics dict
        message: Human-readable status message
        metadata: Optional technical metadata
    """
    try:
        from rich.console import Console
        console = Console()
    except ImportError:
        console = None

    try:
        import httpx

        payload = {
            "name": task_name,
            "status": status,
            "metrics": metrics,
            "message": message,
            "metadata": metadata or {},
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
