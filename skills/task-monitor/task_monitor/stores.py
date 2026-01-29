"""Task Monitor Stores - Data persistence for history, sessions, and quality.

This module provides storage classes for persisting task monitor data to disk.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from task_monitor.config import (
    HISTORY_FILE,
    MAX_HISTORY_ENTRIES,
    MAX_QUALITY_ENTRIES,
    MAX_SESSION_ENTRIES,
    REGISTRY_DIR,
    REGISTRY_FILE,
    SESSIONS_FILE,
)
from task_monitor.models import (
    HistoryEntry,
    QualityMetrics,
    SessionRecord,
    TaskConfig,
)


class TaskRegistry:
    """Registry of monitored tasks."""

    def __init__(self, registry_file: Path = REGISTRY_FILE):
        self.registry_file = registry_file
        self.tasks: dict[str, TaskConfig] = {}
        self._load()

    def _load(self):
        """Load registry from file."""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, encoding="utf-8") as f:
                    data = json.load(f)
                    self.tasks = {k: TaskConfig(**v) for k, v in data.get("tasks", {}).items()}
            except (OSError, json.JSONDecodeError):
                self.tasks = {}

    def _save(self):
        """Save registry to file."""
        data = {"tasks": {k: v.model_dump() for k, v in self.tasks.items()}}
        with open(self.registry_file, 'w', encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def register(self, config: TaskConfig):
        """Register a new task."""
        self.tasks[config.name] = config
        self._save()

    def unregister(self, name: str):
        """Unregister a task."""
        if name in self.tasks:
            del self.tasks[name]
            self._save()

    def get_all(self) -> dict[str, TaskConfig]:
        """Get all registered tasks."""
        return self.tasks.copy()


class HistoryStore:
    """Store for task history - enables 'where was I?' queries."""

    def __init__(self, history_file: Path = HISTORY_FILE):
        self.history_file = history_file
        self._history: list[dict] = []
        self._load()

    def _load(self):
        """Load history from file."""
        if self.history_file.exists():
            try:
                with open(self.history_file, encoding="utf-8") as f:
                    self._history = json.load(f)
            except (OSError, json.JSONDecodeError):
                self._history = []

    def _save(self):
        """Save history to file."""
        # Keep last N entries
        if len(self._history) > MAX_HISTORY_ENTRIES:
            self._history = self._history[-MAX_HISTORY_ENTRIES:]
        with open(self.history_file, 'w', encoding="utf-8") as f:
            json.dump(self._history, f, indent=2)

    def record(self, entry: HistoryEntry):
        """Record a history entry."""
        self._history.append(entry.model_dump())
        self._save()

    def search(self, term: str, limit: int = 50) -> list[dict]:
        """Search history by task name or project."""
        term_lower = term.lower()
        results = []
        for entry in reversed(self._history):
            if (term_lower in entry.get("task_name", "").lower() or
                term_lower in (entry.get("project") or "").lower()):
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def get_recent(self, limit: int = 20) -> list[dict]:
        """Get recent history entries."""
        return list(reversed(self._history[-limit:]))

    def get_by_project(self, project: str, limit: int = 100) -> list[dict]:
        """Get history for a specific project."""
        results = []
        for entry in reversed(self._history):
            if entry.get("project") == project:
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    def get_last_session_context(self) -> dict:
        """Get context about the last work session for 'where was I?'"""
        if not self._history:
            return {"message": "No history found"}

        # Find the most recent entries
        recent = self._history[-50:]

        # Group by task
        tasks_worked = {}
        for entry in recent:
            task = entry.get("task_name")
            if task not in tasks_worked:
                tasks_worked[task] = {
                    "task_name": task,
                    "project": entry.get("project"),
                    "last_action": entry.get("action"),
                    "last_timestamp": entry.get("timestamp"),
                    "details": entry.get("details"),
                }
            else:
                # Update with most recent
                tasks_worked[task]["last_action"] = entry.get("action")
                tasks_worked[task]["last_timestamp"] = entry.get("timestamp")
                tasks_worked[task]["details"] = entry.get("details")

        # Find incomplete tasks (started but not completed)
        incomplete = []
        completed = []
        for task_info in tasks_worked.values():
            if task_info["last_action"] in ["started", "progress", "paused"]:
                incomplete.append(task_info)
            elif task_info["last_action"] == "completed":
                completed.append(task_info)

        return {
            "incomplete_tasks": incomplete,
            "completed_tasks": completed,
            "last_activity": self._history[-1] if self._history else None,
            "suggestion": incomplete[0] if incomplete else None,
        }


class SessionTracker:
    """Track work sessions for resume context."""

    def __init__(self, sessions_file: Path = SESSIONS_FILE):
        self.sessions_file = sessions_file
        self._sessions: list[dict] = []
        self._load()

    def _load(self):
        """Load sessions from file."""
        if self.sessions_file.exists():
            try:
                with open(self.sessions_file, encoding="utf-8") as f:
                    self._sessions = json.load(f)
            except (OSError, json.JSONDecodeError):
                self._sessions = []

    def _save(self):
        """Save sessions to file."""
        # Keep last N sessions
        if len(self._sessions) > MAX_SESSION_ENTRIES:
            self._sessions = self._sessions[-MAX_SESSION_ENTRIES:]
        with open(self.sessions_file, 'w', encoding="utf-8") as f:
            json.dump(self._sessions, f, indent=2)

    def start_session(self, project: str = None) -> str:
        """Start a new work session."""
        session_id = str(uuid.uuid4())[:8]
        session = SessionRecord(
            session_id=session_id,
            project=project,
            started_at=datetime.now().isoformat(),
            status="active",
        )
        self._sessions.append(session.model_dump())
        self._save()
        return session_id

    def end_session(self, session_id: str, notes: str = None):
        """End a work session."""
        for session in self._sessions:
            if session.get("session_id") == session_id:
                session["ended_at"] = datetime.now().isoformat()
                session["status"] = "completed"
                if notes:
                    session["notes"] = notes
                self._save()
                return

    def add_accomplishment(self, session_id: str, accomplishment: str):
        """Add an accomplishment to the current session."""
        for session in self._sessions:
            if session.get("session_id") == session_id:
                if "accomplishments" not in session:
                    session["accomplishments"] = []
                session["accomplishments"].append(accomplishment)
                self._save()
                return

    def add_task(self, session_id: str, task_name: str):
        """Add a task to the current session."""
        for session in self._sessions:
            if session.get("session_id") == session_id:
                if "tasks" not in session:
                    session["tasks"] = []
                if task_name not in session["tasks"]:
                    session["tasks"].append(task_name)
                    self._save()
                return

    def get_active_session(self) -> Optional[dict]:
        """Get the currently active session."""
        for session in reversed(self._sessions):
            if session.get("status") == "active":
                return session
        return None

    def get_last_session(self) -> Optional[dict]:
        """Get the most recent session (active or completed)."""
        return self._sessions[-1] if self._sessions else None

    def get_sessions(self, project: str = None, limit: int = 10) -> list[dict]:
        """Get recent sessions, optionally filtered by project."""
        results = []
        for session in reversed(self._sessions):
            if project and session.get("project") != project:
                continue
            results.append(session)
            if len(results) >= limit:
                break
        return results


class QualityStore:
    """Store for quality metrics history."""

    def __init__(self, store_dir: Path = REGISTRY_DIR):
        self.store_dir = store_dir / "quality"
        self.store_dir.mkdir(parents=True, exist_ok=True)

    def push(self, task_name: str, metrics: QualityMetrics) -> None:
        """Push quality metrics for a task."""
        file_path = self.store_dir / f"{task_name}.json"

        # Load existing history
        history = []
        if file_path.exists():
            try:
                with open(file_path, encoding="utf-8") as f:
                    history = json.load(f)
            except (OSError, json.JSONDecodeError):
                history = []

        # Add new metrics with timestamp
        entry = metrics.model_dump()
        entry["timestamp"] = datetime.now().isoformat()
        history.append(entry)

        # Keep last N entries
        if len(history) > MAX_QUALITY_ENTRIES:
            history = history[-MAX_QUALITY_ENTRIES:]

        # Save
        with open(file_path, 'w', encoding="utf-8") as f:
            json.dump(history, f, indent=2)

    def get(self, task_name: str, limit: int = 100) -> list:
        """Get quality metrics history for a task."""
        file_path = self.store_dir / f"{task_name}.json"

        if not file_path.exists():
            return []

        try:
            with open(file_path, encoding="utf-8") as f:
                history = json.load(f)
            return history[-limit:]
        except (OSError, json.JSONDecodeError):
            return []

    def get_latest(self, task_name: str) -> Optional[dict]:
        """Get latest quality metrics for a task."""
        history = self.get(task_name, limit=1)
        return history[-1] if history else None
