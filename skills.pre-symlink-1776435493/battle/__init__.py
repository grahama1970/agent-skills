"""Battle skill public API with red/blue team orchestration."""
# Battle skill public API — re-exports from submodules.
# Business logic lives in config, state, scoring, memory, digital_twin,
# red_team, blue_team, orchestrator, report, qemu_support, fuzzing, gdb_support.
# Public surface defined in exports.py.
from config import SKILL_DIR, SKILLS_DIR, BATTLES_DIR, REPORTS_DIR, WORKTREES_DIR
from state import BattleState, Finding, Patch, RoundResult, AttackType, DefenseType, TwinMode
from scoring import Scorer, score_round
from memory import BattleMemory
from digital_twin import DigitalTwin
from red_team import RedAgent
from blue_team import BlueAgent
from orchestrator import BattleOrchestrator, TaskMonitor
from report import generate_report, generate_summary
from qemu_support import detect_qemu_machine, build_qemu_command, start_qemu_instance, stop_qemu_instance, create_golden_snapshot, restore_snapshot, configure_peripheral_stubs, enable_mmio_logging, read_mmio_log, create_qcow2_overlay, parse_qemu_config  # noqa: E501
from fuzzing import start_afl_fuzzing, stop_afl_fuzzing, get_fuzzing_stats, collect_crashes, triage_crash, add_to_corpus, get_corpus_stats, sync_corpus_from_findings  # noqa: E501
from gdb_support import get_gdb_connection_info, generate_gdb_script, test_gdb_connection, set_gdb_breakpoint
from exports import __all__
