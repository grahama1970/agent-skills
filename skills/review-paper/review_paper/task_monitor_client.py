"""task_monitor_client - review_paper.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""
from __future__ import annotations
# --- dotenv (MUST be before any os.getenv / os.environ) ---
import sys
from pathlib import Path as _Path

def _resolve_skills_dir() -> _Path:
    p = _Path(__file__).resolve()
    for parent in [p, *p.parents]:
        if parent.name == "skills":
            return parent
    return p.parents[1]

_SKILLS_DIR = _resolve_skills_dir()
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env
except Exception:
    def _load_env() -> None:
        return

_load_env()



import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

TASK_MONITOR_REGISTRY = Path.home() / ".pi" / "task-monitor" / "registry.json"
STATE_FILE = Path(__file__).resolve().parent.parent / "review_paper_task_state.json"
TM_RUN = Path(__file__).resolve().parent.parent.parent / "task-monitor" / "run.sh"


class ReviewPaperTaskClient:
    def __init__(self, task_name: str, total_items: int):
        self.task_name = task_name
        self.total_items = total_items
        self.completed = 0
        self.start_time = time.time()
        self._register_task()
        self._write_state(status="running")

    def _register_task(self) -> None:
        TASK_MONITOR_REGISTRY.parent.mkdir(parents=True, exist_ok=True)
        registry: dict[str, Any] = {}
        if TASK_MONITOR_REGISTRY.exists():
            registry = json.loads(
                TASK_MONITOR_REGISTRY.read_text(encoding="utf-8"),
            )
        registry[f"review-paper:{self.task_name}"] = {
            "state_file": str(STATE_FILE),
            "total": self.total_items,
            "project": "review-paper",
        }
        TASK_MONITOR_REGISTRY.write_text(
            json.dumps(registry, indent=2), encoding="utf-8",
        )

    def _write_state(self, status: str) -> None:
        state = {
            "completed": self.completed,
            "total": self.total_items,
            "progress_pct": round(
                (self.completed / max(1, self.total_items)) * 100, 1,
            ),
            "status": status,
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, STATE_FILE)

    def _tm(self, *args: str) -> bool:
        if not TM_RUN.exists():
            return False
        try:
            result = subprocess.run(
                [str(TM_RUN), *args],
                capture_output=True, text=True, timeout=30,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return result.returncode == 0
        except Exception:
            return False

    def start_session(self) -> None:
        self._tm("start-session", "--project", "review-paper")

    def accomplishment(self, text: str) -> None:
        self._tm("add-accomplishment", "--text", text)

    def update(self, count: int = 1) -> None:
        self.completed += count
        self._write_state(status="running")

    def finish(self, notes: str) -> None:
        self._write_state(status="completed")
        self._tm("end-session", "--notes", notes)
