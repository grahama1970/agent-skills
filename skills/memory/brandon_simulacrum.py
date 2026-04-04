#!/usr/bin/env python3
"""SPARTA Intern Simulacrum - Embry.

Scales Brandon Bailey's security expertise from 100s to 1000s of professionals.
Uses grounded QRA responses with 0.7 threshold to prevent hallucination.

Architecture:
    User Query -> Intent Mapper -> SPARTA QRAs -> Grounding Gate (>=0.7) -> Embry Persona -> Response
                      |                                                        |
              Out-of-scope? -> "I don't know"                     Low confidence? -> Escalate to Brandon

Usage:
    python brandon_simulacrum.py --query "How do I detect RF jamming?"
    python brandon_simulacrum.py --interactive

Modules:
    simulacrum_retrieval  - ArangoDB hybrid search, library, graph expansion
    simulacrum_intent     - Intent detection cascade, entity extraction, clarify
    simulacrum_synthesis  - QRA retrieval orchestration, LLM synthesis, persona formatting
"""

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import typer
from loguru import logger

from brandon_audit import BrandonAuditLogger
from brandon_gate import (
    compute_response_confidence,
    filter_by_grounding,
    format_grounded_response,
    format_uncertain_response,
)
from scope_enforcement import handle_out_of_scope, is_in_scope

# Re-export submodule public APIs for backward compatibility
from simulacrum_intent import (  # noqa: F401
    extract_entities,
    get_intent_cascade,
    get_intent_heuristic,
    get_intent_manual,
    run_clarify,
)
from simulacrum_retrieval import (  # noqa: F401
    MEMORY_ROOT,
    MEMORY_VENV_PYTHON,
    expand_qras_via_subgraph,
    query_brandon_library,
    search_sparta_qras_arango,
)
from simulacrum_synthesis import (
    capture_synthesis_as_qra,  # noqa: F401
    format_embry_response,
    get_mock_qras,  # noqa: F401
    llm_synthesize,  # noqa: F401
    retrieve_qras,
    synthesize_cross_control,
)

app = typer.Typer(help="SPARTA Intern Simulacrum - Embry")

# Co-evolutionary feedback logging (Shadow-LEGO)
try:
    _assistant_dir = str(Path(__file__).resolve().parent.parent / "assistant")
    if _assistant_dir not in sys.path:
        sys.path.insert(0, _assistant_dir)
    from assistant.model_factory import log_subgraph_feedback

    HAS_SUBGRAPH_FEEDBACK = True
except (ImportError, NameError):
    HAS_SUBGRAPH_FEEDBACK = False

# Shared cascade runner
_SKILLS_DIR = Path(__file__).resolve().parent.parent
if str(_SKILLS_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILLS_DIR))
try:
    from common.cascade import CascadeRunner, TierDef, TierResult

    HAS_CASCADE = True
except ImportError:
    HAS_CASCADE = False

# Optional integrations - graceful fallback if not available
try:
    from intent_mapper import IntentMapper
    from intent_mapper import get_intent as ollama_get_intent

    OLLAMA_AVAILABLE = IntentMapper().is_available()
except ImportError:
    OLLAMA_AVAILABLE = False
    ollama_get_intent = None

# DuckDB is DEPRECATED -- all QRA retrieval now via ArangoDB hybrid search
DUCKDB_AVAILABLE = False
duckdb_search_qras = None

try:
    from space_classifier import classify_query

    CLASSIFIER_AVAILABLE = True
except ImportError:
    CLASSIFIER_AVAILABLE = False
    classify_query = None


class EmbrySPARTAIntern:
    """SPARTA Intern simulacrum - Embry.

    Embry is Brandon Bailey's intern at The Aerospace Corporation.
    She answers questions grounded in the SPARTA threat matrix,
    with appropriate humility and escalation when uncertain.
    """

    def __init__(
        self,
        qra_source: str | None = None,
        intent_model_path: str | None = None,
        log_dir: Path | str = Path("logs/sparta_intern_sessions"),
        client_scope: str = "sparta",
    ):
        """Initialize the simulacrum.

        Args:
            qra_source: Path to QRA database or API endpoint
            intent_model_path: Path to LoRA intent mapper model
            log_dir: Directory for session logs
            client_scope: Client scope for QRA storage (e.g., "fort_worth_f36")
        """
        self.qra_source = qra_source
        self.intent_model_path = intent_model_path
        self.audit = BrandonAuditLogger(log_dir=log_dir)
        self._client_scope = client_scope

        # Session state
        self.session_id = str(uuid.uuid4())[:8]
        self.user_id = "anonymous"
        self.queries_this_session = 0
        self.topics_discussed: list[str] = []
        self.user_expertise: str | None = None

        # Load persona for response formatting
        self._load_persona()

    def _load_persona(self) -> None:
        """Load Embry's persona definition."""
        persona_path = Path(__file__).parent / "BRANDON_INTERN_PERSONA.md"
        if persona_path.exists():
            self.persona_text = persona_path.read_text()
        else:
            self.persona_text = ""

    def _get_intent(self, query: str) -> dict[str, Any]:
        """Route query through intent mapper.

        Uses CascadeRunner (classifier -> Ollama -> heuristic) when available,
        falls back to manual cascade otherwise.

        Args:
            query: User's question

        Returns:
            Intent result with action, confidence, entities
        """
        cascade_imports = None
        if HAS_CASCADE:
            cascade_imports = {
                "TierResult": TierResult,
                "TierDef": TierDef,
                "CascadeRunner": CascadeRunner,
            }
        return get_intent_cascade(
            query,
            classifier_available=CLASSIFIER_AVAILABLE,
            classify_query_fn=classify_query,
            ollama_available=OLLAMA_AVAILABLE,
            ollama_get_intent_fn=ollama_get_intent,
            has_cascade=HAS_CASCADE,
            cascade_imports=cascade_imports,
        )

    def respond(self, query: str, user_id: str | None = None) -> dict[str, Any]:
        """Generate response to user query.

        Args:
            query: User's question
            user_id: Optional user identifier

        Returns:
            Response dict with response text, confidence, metadata
        """
        start_time = time.time()

        if user_id:
            self.user_id = user_id

        self.queries_this_session += 1
        is_first = self.queries_this_session == 1

        # Step 1: Intent mapping
        intent = self._get_intent(query)
        intent["original_query"] = query

        # Step 2: Handle out-of-scope
        if not is_in_scope(intent["action"]):
            oos_result = handle_out_of_scope(query, intent["action"])
            self.audit.log_interaction(
                session_id=self.session_id,
                user_id=self.user_id,
                query=query,
                intent_result=intent,
                response=oos_result["response"],
                grounding_scores=[],
                rejected_qras=0,
                response_time_ms=(time.time() - start_time) * 1000,
                user_expertise=self.user_expertise,
            )
            return {
                "response": oos_result["response"],
                "in_scope": False,
                "confidence": "none",
                "session_id": self.session_id,
            }

        # Step 3: Handle clarification needed
        if intent["action"] == "CLARIFY":
            return self._handle_clarify(query, intent, start_time, is_first)

        # Step 4: Retrieve QRAs
        qras, graph_exp = retrieve_qras(intent)

        # Step 4b: Log co-evolutionary subgraph feedback (Shadow-LEGO)
        if HAS_SUBGRAPH_FEEDBACK and qras and graph_exp:
            self._log_subgraph_feedback(qras, graph_exp, intent)

        # Step 5: Apply grounding gate
        accepted, rejected = filter_by_grounding(qras)
        confidence = compute_response_confidence(accepted, len(rejected))

        # Step 6: Generate response
        if not accepted:
            return self._handle_no_accepted_qras(
                query, intent, confidence, rejected, start_time, is_first
            )

        # Cross-control synthesis: show QRAs transparently, then synthesize
        unique_controls = {q.get("control_id") for q in accepted}
        if len(unique_controls) >= 2:
            grounded_response = synthesize_cross_control(
                query, accepted, client_scope=self._client_scope
            )
        else:
            grounded_response = format_grounded_response(accepted, confidence)
        response = format_embry_response(grounded_response, confidence, is_first)
        escalated = confidence["confidence_level"] == "low"
        escalation_reason = "Low overall confidence" if escalated else None

        # Track library vs SPARTA source mix
        library_count = sum(
            1 for q in accepted if q.get("_source") == "brandon_library"
        )
        sparta_count = len(accepted) - library_count

        # Step 7: Log the interaction
        grounding_scores = [qra.get("grounding_score", 0.0) for qra in accepted]
        self.audit.log_interaction(
            session_id=self.session_id,
            user_id=self.user_id,
            query=query,
            intent_result=intent,
            response=response,
            grounding_scores=grounding_scores,
            rejected_qras=len(rejected),
            response_time_ms=(time.time() - start_time) * 1000,
            escalated=escalated,
            escalation_reason=escalation_reason,
            user_expertise=self.user_expertise,
        )

        return {
            "response": response,
            "in_scope": True,
            "confidence": confidence["confidence_level"],
            "avg_grounding": confidence.get("avg_grounding", 0.0),
            "qras_used": len(accepted),
            "qras_rejected": len(rejected),
            "sparta_sources": sparta_count,
            "library_sources": library_count,
            "escalated": escalated,
            "session_id": self.session_id,
        }

    def _handle_clarify(
        self,
        query: str,
        intent: dict[str, Any],
        start_time: float,
        is_first: bool,
    ) -> dict[str, Any]:
        """Handle queries that need clarification.

        Args:
            query: User's question
            intent: Intent mapping result
            start_time: Query start timestamp
            is_first: Whether this is the first query in session

        Returns:
            Response dict with clarification
        """
        clarify_result = run_clarify(query, intent)

        if clarify_result and clarify_result.get("clarify_questions"):
            questions = clarify_result["clarify_questions"]
            clarify_response = (
                f"I want to make sure I understand your question correctly. "
                f"{questions[0]['question']}"
            )
            if len(questions) > 1:
                clarify_response += "\n\nOr alternatively: " + questions[1]["question"]
        else:
            clarify_response = (
                f"I want to make sure I understand your question correctly. "
                f"{intent.get('clarify_question', 'Could you provide more details?')}"
            )

        self.audit.log_interaction(
            session_id=self.session_id,
            user_id=self.user_id,
            query=query,
            intent_result=intent,
            response=clarify_response,
            grounding_scores=[],
            rejected_qras=0,
            response_time_ms=(time.time() - start_time) * 1000,
            user_expertise=self.user_expertise,
        )

        return {
            "response": clarify_response,
            "in_scope": True,
            "needs_clarification": True,
            "confidence": "pending",
            "session_id": self.session_id,
            "clarify_diagnostics": (
                clarify_result.get("diagnostics") if clarify_result else None
            ),
        }

    def _handle_no_accepted_qras(
        self,
        query: str,
        intent: dict[str, Any],
        confidence: dict[str, Any],
        rejected: list[dict[str, Any]],
        start_time: float,
        is_first: bool,
    ) -> dict[str, Any]:
        """Handle case where no QRAs pass the grounding threshold.

        Args:
            query: User's question
            intent: Intent mapping result
            confidence: Confidence metrics
            rejected: Rejected QRAs
            start_time: Query start timestamp
            is_first: Whether this is the first query in session

        Returns:
            Response dict
        """
        clarify_result = run_clarify(query, intent)
        if clarify_result and clarify_result.get("needs_clarification"):
            questions = clarify_result.get("clarify_questions", [])
            if questions:
                uncertain_response = (
                    f"I couldn't find strong answers for that. "
                    f"{questions[0]['question']}"
                )
                if len(questions) > 1:
                    uncertain_response += f"\n\nOr: {questions[1]['question']}"
                response = format_embry_response(
                    uncertain_response, confidence, is_first
                )
                self.audit.log_interaction(
                    session_id=self.session_id,
                    user_id=self.user_id,
                    query=query,
                    intent_result=intent,
                    response=response,
                    grounding_scores=[],
                    rejected_qras=len(rejected),
                    response_time_ms=(time.time() - start_time) * 1000,
                    user_expertise=self.user_expertise,
                )
                return {
                    "response": response,
                    "in_scope": True,
                    "needs_clarification": True,
                    "confidence": "pending",
                    "session_id": self.session_id,
                    "clarify_diagnostics": clarify_result.get("diagnostics"),
                }

        # Fallback: no useful clarification, give uncertain response
        uncertain_response = format_uncertain_response(query, len(rejected))
        response = format_embry_response(uncertain_response, confidence, is_first)

        self.audit.log_interaction(
            session_id=self.session_id,
            user_id=self.user_id,
            query=query,
            intent_result=intent,
            response=response,
            grounding_scores=[],
            rejected_qras=len(rejected),
            response_time_ms=(time.time() - start_time) * 1000,
            escalated=True,
            escalation_reason="All QRAs below 0.7 grounding threshold",
            user_expertise=self.user_expertise,
        )

        return {
            "response": response,
            "in_scope": True,
            "confidence": confidence["confidence_level"],
            "avg_grounding": confidence.get("avg_grounding", 0.0),
            "qras_used": 0,
            "qras_rejected": len(rejected),
            "escalated": True,
            "session_id": self.session_id,
        }

    def _log_subgraph_feedback(
        self,
        qras: list[dict[str, Any]],
        graph_exp: dict[str, Any],
        intent: dict[str, Any],
    ) -> None:
        """Log co-evolutionary subgraph feedback (Shadow-LEGO).

        Args:
            qras: All retrieved QRAs
            graph_exp: Graph expansion metadata
            intent: Intent mapping result
        """
        base_qras = [q for q in qras if q.get("_source") != "subgraph_expansion"]
        base_avg = (
            sum(q.get("grounding_score", 0) for q in base_qras) / len(base_qras)
            if base_qras
            else 0.0
        )
        classifier_name = intent.get("_classifier", {}).get("model", "heuristic")
        if isinstance(classifier_name, dict):
            classifier_name = "heuristic"
        seeds = graph_exp.get("seeds", intent.get("entities", []))
        confidence_val = intent.get("confidence", 0.5)
        try:
            log_subgraph_feedback(
                classifier_name=str(classifier_name),
                seeds=seeds,
                subgraph_qra_count=graph_exp["raw_count"],
                avg_grounding=graph_exp["raw_avg_grounding"],
                baseline_qra_count=len(base_qras),
                baseline_grounding=base_avg,
                confidence=float(confidence_val),
                scope="brandon_bailey",
            )
        except Exception as e:
            logger.debug(f"Subgraph feedback logging failed (non-fatal): {e}")

    def get_session_summary(self) -> dict[str, Any]:
        """Get summary of current session.

        Returns:
            Session statistics
        """
        return self.audit.get_session_summary(self.session_id)


def interactive_session(embry: EmbrySPARTAIntern) -> None:
    """Run interactive session with Embry.

    Args:
        embry: Initialized simulacrum instance
    """
    print("\n" + "=" * 60)
    print("SPARTA Intern Session - Embry")
    print("=" * 60)
    print("Type 'quit' to exit, 'summary' for session stats\n")

    while True:
        try:
            query = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not query:
            continue
        if query.lower() == "quit":
            break
        if query.lower() == "summary":
            summary = embry.get_session_summary()
            print(f"\nSession Summary: {json.dumps(summary, indent=2)}\n")
            continue

        result = embry.respond(query)
        print(f"\nEmbry: {result['response']}\n")

        # Show metadata in debug mode
        if result.get("escalated"):
            print(f"[Escalated: {result.get('escalation_reason', 'Low confidence')}]\n")

    # Final summary
    print("\n" + "=" * 60)
    summary = embry.get_session_summary()
    print(f"Session ended. {summary.get('queries', 0)} queries processed.")
    print("=" * 60)


@app.command()
def main(
    query: Optional[str] = typer.Option(
        None, "-q", "--query", help="Single query to process"
    ),
    interactive: bool = typer.Option(
        False, "-i", "--interactive", help="Run interactive session"
    ),
    user_id: str = typer.Option(
        "anonymous", "--user-id", help="User identifier for logging"
    ),
    log_dir: str = typer.Option(
        "logs/sparta_intern_sessions", "--log-dir", help="Log directory"
    ),
) -> None:
    """SPARTA Intern Simulacrum - Embry."""
    embry = EmbrySPARTAIntern(log_dir=log_dir)

    if query:
        result = embry.respond(query, user_id=user_id)
        print(result["response"])
        return

    if interactive:
        interactive_session(embry)
        return

    # Default: show help
    print("Use --query or --interactive to start. See --help for usage.")
    raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
