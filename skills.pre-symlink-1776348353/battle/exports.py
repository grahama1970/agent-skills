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

This module defines the public surface of the battle package.
All symbols listed in __all__ are re-exported from __init__.py.
"""

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
    # QEMU Support
    "detect_qemu_machine",
    "build_qemu_command",
    "start_qemu_instance",
    "stop_qemu_instance",
    "create_golden_snapshot",
    "restore_snapshot",
    "configure_peripheral_stubs",
    "enable_mmio_logging",
    "read_mmio_log",
    "create_qcow2_overlay",
    "parse_qemu_config",
    # Fuzzing
    "start_afl_fuzzing",
    "stop_afl_fuzzing",
    "get_fuzzing_stats",
    "collect_crashes",
    "triage_crash",
    "add_to_corpus",
    "get_corpus_stats",
    "sync_corpus_from_findings",
    # GDB Support
    "get_gdb_connection_info",
    "generate_gdb_script",
    "test_gdb_connection",
    "set_gdb_breakpoint",
]
