"""Receipt schemas for deterministic Battle fixture runs.

Inputs are in-process dataclass values from the Battle fixture runner and judge. Outputs
are JSON receipt files with stable schemas. Failures surface through normal file
IO exceptions from ``Path.write_text`` rather than silent fallback behavior.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


@dataclass
class CommandResult:
    command: list[str]
    exit_code: int
    stdout_path: str | None = None
    stderr_path: str | None = None


@dataclass
class RedReceipt:
    schema: str = "battle.red_receipt.v1"
    battle_id: str = ""
    round_number: int = 1
    status: Literal["PASS", "FAIL", "BLOCKED"] = "BLOCKED"
    finding_id: str | None = None
    exploit_confirmed: bool = False
    exploit_artifact: str | None = None
    commands_run: list[CommandResult] = field(default_factory=list)
    next_agent: str = "battle-blue"
    created_at: str = field(default_factory=utc_now)


@dataclass
class BlueReceipt:
    schema: str = "battle.blue_receipt.v1"
    battle_id: str = ""
    round_number: int = 1
    status: Literal["PASS", "FAIL", "BLOCKED"] = "BLOCKED"
    patch_artifact: str | None = None
    changed_files: list[str] = field(default_factory=list)
    commands_run: list[CommandResult] = field(default_factory=list)
    next_agent: str = "battle-scorekeeper"
    created_at: str = field(default_factory=utc_now)


@dataclass
class JudgeReceipt:
    schema: str = "battle.judge_receipt.v1"
    battle_id: str = ""
    round_number: int = 1
    status: Literal["PASS", "FAIL", "INSUFFICIENT_EVIDENCE", "BLOCKED"] = "BLOCKED"
    verdict: Literal[
        "BLUE_SUCCESS",
        "RED_SUCCESS",
        "FAKE_DEFENSE",
        "INSUFFICIENT_EVIDENCE",
        "BLOCKED",
    ] = "BLOCKED"
    exploit_confirmed_before_patch: bool = False
    exploit_blocked_after_patch: bool = False
    regression_tests_pass: bool = False
    functionality_preserved: bool = False
    commands_run: list[CommandResult] = field(default_factory=list)
    next_agent: str = "human"
    created_at: str = field(default_factory=utc_now)


def to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    return value


def write_json(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(to_jsonable(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
