"""Thin wrapper around shared TaskClient for prompt-lab skill.

Preserves the PromptLabTaskClient interface and convenience functions.
Domain-specific tracking (quality gates, case timing, heartbeat) built on top
of the shared TaskClient core.
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from common.task_monitor import TaskClient

HEARTBEAT_INTERVAL_S = float(os.getenv("PROMPT_LAB_HEARTBEAT_INTERVAL_S", "30.0"))

SKILL_DIR = Path(__file__).parent
ERROR_LOG = SKILL_DIR / "prompt_lab_errors.json"


@dataclass
class GateMetrics:
    passed: int = 0
    failed: int = 0

    @property
    def rate(self) -> float:
        total = self.passed + self.failed
        return self.passed / total if total > 0 else 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {"passed": self.passed, "failed": self.failed, "rate": round(self.rate, 4)}


@dataclass
class FailureRecord:
    case_id: str
    gate: str
    question: str
    reason: str
    score: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id, "gate": self.gate,
            "question": self.question[:100], "reason": self.reason,
            "score": self.score, "timestamp": self.timestamp,
        }


class PromptLabTaskClient:
    """Task-monitor compatible progress tracker for prompt-lab.

    Delegates core registration/state to shared TaskClient; adds
    quality gate metrics and async heartbeat on top.
    """

    def __init__(
        self,
        task_name: str,
        total_cases: int,
        description: Optional[str] = None,
        register: bool = True,
    ):
        self.task_name = task_name
        self.total_cases = total_cases
        desc = description or f"Prompt-Lab: {task_name}"

        self._client = TaskClient(
            skill_name=f"prompt-lab:{task_name}",
            total=total_cases,
            description=desc,
            state_dir=str(SKILL_DIR),
            register=register,
        )

        self.gates = {
            "ambiguity": GateMetrics(),
            "anchoring": GateMetrics(),
            "grounding": GateMetrics(),
        }
        self.failures: List[FailureRecord] = []
        self.total_qras = 0
        self.case_times: Dict[str, float] = {}

        # Heartbeat tracking
        self.current_case: Optional[str] = None
        self.current_case_start: Optional[float] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    @property
    def completed(self) -> int:
        return self._client.completed

    def start_case(self, case_id: str):
        self.current_case = case_id
        self.current_case_start = time.time()

    def end_case(self, case_id: str):
        if self.current_case_start:
            self.case_times[case_id] = time.time() - self.current_case_start
        self.current_case = None
        self.current_case_start = None

    def heartbeat(self):
        item = ""
        if self.current_case and self.current_case_start:
            elapsed = time.time() - self.current_case_start
            item = f"processing {self.current_case} ({elapsed:.0f}s)"
        self._client.heartbeat(item=item)

    async def _heartbeat_loop(self, interval: float = HEARTBEAT_INTERVAL_S):
        try:
            while True:
                await asyncio.sleep(interval)
                self.heartbeat()
        except asyncio.CancelledError:
            pass

    async def start_heartbeat(self, interval: float = HEARTBEAT_INTERVAL_S):
        if self._heartbeat_task is not None:
            return self._heartbeat_task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop(interval))
        return self._heartbeat_task

    async def stop_heartbeat(self):
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None

    def update(
        self,
        case_id: str,
        ambiguity_rate: float,
        anchoring_rate: float,
        grounding_rate: float,
        qra_count: int,
        failures: Optional[List[Dict[str, Any]]] = None,
    ):
        self.total_qras += qra_count

        if ambiguity_rate >= 1.0:
            self.gates["ambiguity"].passed += 1
        else:
            self.gates["ambiguity"].failed += 1

        if anchoring_rate >= 1.0:
            self.gates["anchoring"].passed += 1
        else:
            self.gates["anchoring"].failed += 1

        if grounding_rate >= 0.85:
            self.gates["grounding"].passed += 1
        else:
            self.gates["grounding"].failed += 1

        if failures:
            for f in failures:
                self.failures.append(FailureRecord(
                    case_id=case_id,
                    gate=f.get("failed_gate", "unknown"),
                    question=f.get("question", ""),
                    reason=f.get("reason", ""),
                    score=f.get("score"),
                ))

        self._client.update(
            item=case_id,
            total_qras=self.total_qras,
            ambiguity_rate=round(self.gates["ambiguity"].rate, 4),
            anchoring_rate=round(self.gates["anchoring"].rate, 4),
            grounding_rate=round(self.gates["grounding"].rate, 4),
        )

    def finish(self, success: bool = True):
        self._client.finish(success=success)

        if self.failures:
            try:
                error_data = {
                    "task_name": self.task_name,
                    "completed_at": datetime.now().isoformat(),
                    "success": success,
                    "total_cases": self.total_cases,
                    "total_failures": len(self.failures),
                    "gates": {n: m.to_dict() for n, m in self.gates.items()},
                    "failures": [f.to_dict() for f in self.failures],
                }
                tmp = ERROR_LOG.with_suffix(".tmp")
                tmp.write_text(json.dumps(error_data, indent=2))
                os.replace(tmp, ERROR_LOG)
            except Exception:
                pass

    def get_summary(self) -> Dict[str, Any]:
        summary = self._client.get_summary()
        summary.update({
            "gates": {
                "ambiguity": self.gates["ambiguity"].rate,
                "anchoring": self.gates["anchoring"].rate,
                "grounding": self.gates["grounding"].rate,
            },
            "failures": len(self.failures),
            "total_qras": self.total_qras,
        })
        return summary


# Convenience functions
_current_client: Optional[PromptLabTaskClient] = None


def start_monitoring(task_name: str, total_cases: int) -> PromptLabTaskClient:
    global _current_client
    _current_client = PromptLabTaskClient(task_name, total_cases)
    return _current_client


def get_monitor() -> Optional[PromptLabTaskClient]:
    return _current_client


def end_monitoring(success: bool = True):
    global _current_client
    if _current_client:
        _current_client.finish(success)
        _current_client = None
