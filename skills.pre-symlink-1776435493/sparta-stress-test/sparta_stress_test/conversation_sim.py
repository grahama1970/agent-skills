"""Multi-turn conversation simulator for SPARTA stress testing.

Follows the /battle pattern: round-based adversarial exchange between
Margaret Chen / Jennifer Cheung personas and the SPARTA QRA system,
graded by Brandon Bailey, archived by /episodic-archiver.

Session flow (max 4 turns):
  Turn 1: Persona asks a question (via /scillm)
  Turn 2: SPARTA system answers (via QRA lookup + NLG)
  Turn 3: Persona evaluates — clarifies if ambiguous, pushes back if unsatisfied
  Turn 4: SPARTA responds to follow-up (final)

Brandon grades the FULL session after all turns complete.
/episodic-archiver captures the exchange for cross-session learning.

Usage:
    from sparta_stress_test.conversation_sim import run_session, run_batch_sessions

    session = run_session(seed_question={"question": "...", "persona": "Margaret Chen"})
    results = run_batch_sessions(count=50)

This module is a thin re-export facade. All implementation lives in:
  - conversation_models.py   — dataclasses, constants, shared imports
  - conversation_prompts.py  — persona and grading prompt templates
  - conversation_synthesis.py — entity extraction, NLG synthesis, reranking
  - conversation_retrieval.py — Tier 1 lookup, query planning, _sparta_answer()
  - conversation_steering.py — steering functions, skill routing, QRA promotion
  - conversation_grading.py  — grading, self-grading loop, persona evaluation
  - conversation_runner.py   — run_session(), archiving, blame analysis
  - conversation_batch.py    — batch runner, aggregation, Shadow-LEGO post-run
"""

from __future__ import annotations

# Re-export data structures
from sparta_stress_test.conversation_models import (
    Turn,
    Tier1Result,
    SessionGrade,
    StressSession,
    SESSIONS_DIR,
    ADVERSARIAL_RATE,
    SELF_GRADE_MAX_ITERATIONS,
    SELF_GRADE_TARGET_COMPOSITE,
    OUTER_LOOP_MAX_ROUNDS,
    OUTER_LOOP_TARGET,
    OUTER_LOOP_STALL_TOLERANCE,
    SHADOW_DELTA_PATH,
    SHADOW_JSONL_PATH,
    MIN_STRATIFIED_SAMPLE,
    PI_MONO_SKILLS,
    SKILL_SLASH_PATTERN,
    _call_scillm,
    _get_db,
)

# Re-export prompts
from sparta_stress_test.conversation_prompts import (
    MARGARET_FOLLOWUP,
    JENNIFER_FOLLOWUP,
    BRANDON_SESSION_GRADE,
    QUERY_PLAN_PROMPT,
)

# Re-export synthesis functions (entity extraction, NLG, reranking)
from sparta_stress_test.conversation_synthesis import (
    _validate_entities_with_parents,
    _extract_entity_ids,
    _extract_keywords,
    _nlg_synthesize,
    _labeled_synthesize,
    _rerank_by_bridge_overlap,
)

# Re-export retrieval functions (Tier 1, query planning, _sparta_answer)
from sparta_stress_test.conversation_retrieval import (
    _get_control_catalog,
    _detect_explicit_skills,
    _qra_count_for_entities,
    _graph_neighbors_with_qras,
    _skill_suggest_via_memory,
    _tier1_lookup,
    _plan_query_strategy,
    _plan_query_heuristic,
    _recall_episodic_context,
    _sparta_answer,
)

# Re-export steering functions
from sparta_stress_test.conversation_steering import (
    _build_clarify_response,
    _build_no_coverage_response,
    _build_interview_response,
    _steer_control_only,
    _steer_unknown_entity,
    _execute_skill_chain,
    _suggest_skill,
    _check_promotion_eligible,
    _promote_to_qra,
)

# Re-export grading functions
from sparta_stress_test.conversation_grading import (
    _persona_evaluate,
    _grade_session_heuristic,
    _grade_session_brandon,
    _self_grade_response,
    _self_grading_loop,
    _log_shadow_entry,
    _log_shadow_delta,
)

# Re-export session runner
from sparta_stress_test.conversation_runner import (
    run_session,
    _archive_session,
    _analyze_session_blame,
    aggregate_blame,
)

# Re-export batch pipeline
from sparta_stress_test.conversation_batch import (
    run_batch_sessions,
    aggregate_sessions,
    shadow_lego_post_run,
    save_sessions,
)

__all__ = [
    # Data structures
    "Turn",
    "Tier1Result",
    "SessionGrade",
    "StressSession",
    "SESSIONS_DIR",
    # Session runner
    "run_session",
    "run_batch_sessions",
    # Aggregation
    "aggregate_sessions",
    "aggregate_blame",
    # Post-run pipeline
    "shadow_lego_post_run",
    # Save/Load
    "save_sessions",
    # Retrieval (for docs/tests)
    "_tier1_lookup",
    "_get_db",
    "_sparta_answer",
    "_extract_entity_ids",
]
