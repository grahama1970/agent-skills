"""main - intent-mapper.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import typer

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

app = typer.Typer()

@app.command()
def main(name: str = typer.Option("World")): # pragma: no cover
    """A simple CLI application."""
    monitor = TaskClient("intent-mapper", total=1) if TaskClient else None
    print(f"Hello {name}")
    if monitor:
        monitor.update(item=name)
        monitor.finish()


if __name__ == "__main__":
    app()