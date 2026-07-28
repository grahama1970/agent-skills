from __future__ import annotations

import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from battle_skill.orchestrator import BattleOrchestrator
from battle_skill.state import AttackType, BattleState, Finding


class _RedAgent:
    def __init__(self, events: list[tuple[str, float]]) -> None:
        self.events = events

    def attack(self, round_num: int) -> list[Finding]:
        self.events.append(("red_start", time.monotonic()))
        time.sleep(0.05)
        self.events.append(("red_terminal", time.monotonic()))
        return [
            Finding(
                id=f"finding-{round_num}",
                type=AttackType.SCAN,
                severity="medium",
                description="deterministic finding",
            )
        ]

    def validate_finding_cascade(self, finding: Finding) -> Finding:
        return finding


class _BlueAgent:
    def __init__(self, events: list[tuple[str, float]], inputs: list[list[Finding]]) -> None:
        self.events = events
        self.inputs = inputs

    def defend(self, findings: list[Finding], round_num: int):
        self.events.append(("blue_start", time.monotonic()))
        self.inputs.append(list(findings))
        time.sleep(0.10)
        self.events.append(("blue_terminal", time.monotonic()))
        return []


class _Twin:
    def sync_blue_to_arena(self) -> None:
        raise AssertionError("no patches means sync must not run")


def _event(events: list[tuple[str, float]], name: str) -> float:
    return next(value for key, value in events if key == name)


def test_run_round_concurrent_starts_red_and_proactive_blue_before_await(
    tmp_path: Path,
) -> None:
    orchestrator = BattleOrchestrator.__new__(BattleOrchestrator)
    events: list[tuple[str, float]] = []
    blue_inputs: list[list[Finding]] = []
    orchestrator.battle_id = "test-overlap"
    orchestrator.worker_timeout = 2
    orchestrator.red_agent = _RedAgent(events)
    orchestrator.blue_agent = _BlueAgent(events, blue_inputs)
    orchestrator.digital_twin = _Twin()
    orchestrator.state = BattleState(
        battle_id="test-overlap",
        target_path=str(tmp_path),
        max_rounds=1,
    )
    orchestrator.null_rounds = 0
    orchestrator.stable_rounds = 0
    orchestrator.last_scores = (0.0, 0.0)

    result = orchestrator.run_round_concurrent(1)

    assert len(result.red_findings) == 1
    assert blue_inputs == [[]]
    assert _event(events, "blue_start") < _event(events, "red_terminal")
    assert _event(events, "red_start") < _event(events, "blue_terminal")
