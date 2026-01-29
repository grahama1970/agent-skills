"""
Battle Skill - Red vs Blue Team Security Competition Orchestrator

Based on research into:
- RvB Framework (arXiv 2601.19726)
- DARPA AIxCC scoring system
- Microsoft PyRIT multi-turn orchestration
- DeepTeam async batch processing

Concurrent Execution:
- Red and Blue teams run in separate threads
- Shared state protected by locks
- Dynamic interaction via message queues
"""
from config import (
    SKILL_DIR,
    SKILLS_DIR,
    BATTLES_DIR,
    REPORTS_DIR,
    WORKTREES_DIR,
)
from state import (
    BattleState,
    Finding,
    Patch,
    RoundResult,
    AttackType,
    DefenseType,
    TwinMode,
)
from scoring import Scorer, score_round
from memory import BattleMemory
from digital_twin import DigitalTwin
from red_team import RedAgent
from blue_team import BlueAgent
from orchestrator import BattleOrchestrator, TaskMonitor
from report import generate_report, generate_summary

__all__ = [
    # Config
    "SKILL_DIR",
    "SKILLS_DIR",
    "BATTLES_DIR",
    "REPORTS_DIR",
    "WORKTREES_DIR",
    # State
    "BattleState",
    "Finding",
    "Patch",
    "RoundResult",
    "AttackType",
    "DefenseType",
    "TwinMode",
    # Scoring
    "Scorer",
    "score_round",
    # Memory
    "BattleMemory",
    # Digital Twin
    "DigitalTwin",
    # Agents
    "RedAgent",
    "BlueAgent",
    # Orchestrator
    "BattleOrchestrator",
    "TaskMonitor",
    # Report
    "generate_report",
    "generate_summary",
]
