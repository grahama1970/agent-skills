"""Task Monitor Models - Pydantic models for data structures.

This module defines all data models used across the task-monitor skill.
Layer: core models only (do not import from other task_monitor modules).
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskConfig(BaseModel):
    """Configuration for a monitored task."""
    name: str
    state_file: str
    total: Optional[int] = None
    description: Optional[str] = None
    on_complete: Optional[str] = None  # Command or "batch-report" to auto-run
    batch_type: Optional[str] = None  # For batch-report integration
    completed_at: Optional[str] = None  # Timestamp when task reached 100%
    hook_executed: bool = False  # Track if on_complete was already run
    quality_thresholds: Optional[dict] = None  # Quality thresholds for early termination
    paused: bool = False  # Whether task is paused
    project: Optional[str] = None  # Project name for grouping


class SessionRecord(BaseModel):
    """Record of a work session."""
    session_id: str
    project: Optional[str] = None
    tasks: list[str] = Field(default_factory=list)
    started_at: str
    ended_at: Optional[str] = None
    accomplishments: list[str] = Field(default_factory=list)
    notes: Optional[str] = None
    status: str = "active"  # active, completed, interrupted


class HistoryEntry(BaseModel):
    """Entry in task history."""
    task_name: str
    project: Optional[str] = None
    action: str  # started, progress, completed, failed, paused, resumed
    timestamp: str
    details: Optional[dict] = None


class QualityMetrics(BaseModel):
    """Quality metrics for a task."""
    metrics: dict[str, Any]  # Current rolling metrics
    recent_failures: Optional[list] = None  # Recent failures for debugging
    timestamp: Optional[str] = None
