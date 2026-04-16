#!/usr/bin/env python3
"""Brandon's Intern Simulacrum - Audit Logging.

Tracks all interactions for:
- Quality monitoring
- Error pattern detection
- Usage analytics
- Compliance/traceability

Usage:
    from brandon_audit import BrandonAuditLogger

    logger = BrandonAuditLogger()
    logger.log_interaction(session_id, user_id, query, intent_result, ...)
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class BrandonAuditLogger:
    """Audit logger for SPARTA Intern simulacrum interactions."""

    def __init__(
        self,
        log_dir: Path | str = Path("logs/sparta_intern_sessions"),
        max_response_preview: int = 500,
    ):
        """Initialize the audit logger.

        Args:
            log_dir: Directory for log files (daily rotation)
            max_response_preview: Max chars of response to store
        """
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_response_preview = max_response_preview

    def _get_log_file(self) -> Path:
        """Get today's log file path."""
        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self.log_dir / f"{date_str}.jsonl"

    def log_interaction(
        self,
        session_id: str,
        user_id: str,
        query: str,
        intent_result: dict[str, Any],
        response: str,
        grounding_scores: list[float],
        rejected_qras: int,
        response_time_ms: float,
        escalated: bool = False,
        escalation_reason: str | None = None,
        user_expertise: str | None = None,
    ) -> dict[str, Any]:
        """Log a single interaction.

        Args:
            session_id: Unique session identifier
            user_id: User identifier (may be anonymous)
            query: The user's original query
            intent_result: Result from intent mapper
            response: The generated response
            grounding_scores: List of grounding scores for used QRAs
            rejected_qras: Count of QRAs rejected by grounding gate
            response_time_ms: Total response generation time
            escalated: Whether this was escalated to "ask Brandon"
            escalation_reason: Why escalation was triggered
            user_expertise: Detected user expertise level

        Returns:
            The logged entry dict
        """
        # Compute aggregate metrics
        avg_grounding = (
            sum(grounding_scores) / len(grounding_scores)
            if grounding_scores
            else 0.0
        )

        entry = {
            # Identifiers
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "user_id": user_id,
            # Query info
            "query": query,
            "query_length": len(query),
            # Intent mapper results
            "intent_action": intent_result.get("action"),
            "intent_confidence": intent_result.get("confidence"),
            "intent_entities": intent_result.get("entities", []),
            "intent_tier1_tags": intent_result.get("tier1", []),
            # Response info
            "response_preview": response[: self.max_response_preview],
            "response_length": len(response),
            # Quality metrics
            "avg_grounding": round(avg_grounding, 3),
            "min_grounding": round(min(grounding_scores), 3) if grounding_scores else 0,
            "max_grounding": round(max(grounding_scores), 3) if grounding_scores else 0,
            "qras_used": len(grounding_scores),
            "qras_rejected": rejected_qras,
            # Performance
            "response_time_ms": round(response_time_ms, 1),
            # Classification
            "in_scope": intent_result.get("action") != "NO_MATCH",
            "escalated": escalated,
            "escalation_reason": escalation_reason,
            "user_expertise": user_expertise,
        }

        # Write to log file
        log_file = self._get_log_file()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return entry

    def log_error(
        self,
        session_id: str,
        user_id: str,
        query: str,
        error_type: str,
        error_message: str,
        stack_trace: str | None = None,
    ) -> dict[str, Any]:
        """Log an error during interaction.

        Args:
            session_id: Session identifier
            user_id: User identifier
            query: The query that caused the error
            error_type: Type/class of error
            error_message: Error message
            stack_trace: Optional stack trace

        Returns:
            The logged error entry
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "user_id": user_id,
            "query": query,
            "error": True,
            "error_type": error_type,
            "error_message": error_message,
            "stack_trace": stack_trace,
        }

        log_file = self._get_log_file()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return entry

    def log_session_start(
        self,
        session_id: str,
        user_id: str,
        user_agent: str | None = None,
        interface: str = "text",
    ) -> dict[str, Any]:
        """Log session start for analytics.

        Args:
            session_id: New session identifier
            user_id: User identifier
            user_agent: Client user agent string
            interface: "text" or "voice"

        Returns:
            The logged entry
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "user_id": user_id,
            "event": "session_start",
            "user_agent": user_agent,
            "interface": interface,
        }

        log_file = self._get_log_file()
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

        return entry

    def get_session_summary(self, session_id: str) -> dict[str, Any]:
        """Get summary statistics for a session.

        Args:
            session_id: Session to summarize

        Returns:
            Summary dict with query count, avg grounding, etc.
        """
        log_file = self._get_log_file()
        if not log_file.exists():
            return {"session_id": session_id, "queries": 0}

        entries = []
        with open(log_file, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("session_id") == session_id and not entry.get("error"):
                        entries.append(entry)
                except json.JSONDecodeError:
                    continue

        if not entries:
            return {"session_id": session_id, "queries": 0}

        grounding_scores = [e["avg_grounding"] for e in entries if e.get("avg_grounding")]
        response_times = [e["response_time_ms"] for e in entries if e.get("response_time_ms")]

        return {
            "session_id": session_id,
            "queries": len(entries),
            "in_scope_queries": sum(1 for e in entries if e.get("in_scope")),
            "out_of_scope_queries": sum(1 for e in entries if not e.get("in_scope")),
            "escalations": sum(1 for e in entries if e.get("escalated")),
            "avg_grounding": round(sum(grounding_scores) / len(grounding_scores), 3) if grounding_scores else 0,
            "avg_response_time_ms": round(sum(response_times) / len(response_times), 1) if response_times else 0,
            "total_qras_used": sum(e.get("qras_used", 0) for e in entries),
            "total_qras_rejected": sum(e.get("qras_rejected", 0) for e in entries),
        }

    def get_daily_summary(self, date: str | None = None) -> dict[str, Any]:
        """Get summary statistics for a day.

        Args:
            date: Date string YYYY-MM-DD (default: today)

        Returns:
            Summary dict with session count, query count, etc.
        """
        if date is None:
            date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        log_file = self.log_dir / f"{date}.jsonl"
        if not log_file.exists():
            return {"date": date, "sessions": 0, "queries": 0}

        entries = []
        sessions = set()
        errors = 0

        with open(log_file, encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    if entry.get("error"):
                        errors += 1
                    elif entry.get("event") != "session_start":
                        entries.append(entry)
                    sessions.add(entry.get("session_id"))
                except json.JSONDecodeError:
                    continue

        grounding_scores = [e["avg_grounding"] for e in entries if e.get("avg_grounding")]

        return {
            "date": date,
            "sessions": len(sessions),
            "queries": len(entries),
            "errors": errors,
            "in_scope_queries": sum(1 for e in entries if e.get("in_scope")),
            "out_of_scope_queries": sum(1 for e in entries if not e.get("in_scope")),
            "escalations": sum(1 for e in entries if e.get("escalated")),
            "avg_grounding": round(sum(grounding_scores) / len(grounding_scores), 3) if grounding_scores else 0,
        }


if __name__ == "__main__":
    # Quick self-test
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        logger = BrandonAuditLogger(log_dir=tmpdir)

        # Log session start
        logger.log_session_start("session-001", "user-abc", interface="text")

        # Log interaction
        entry = logger.log_interaction(
            session_id="session-001",
            user_id="user-abc",
            query="How do I detect RF jamming?",
            intent_result={"action": "QUERY", "confidence": 0.85, "entities": ["T-0023"]},
            response="Based on SPARTA technique T-0023, RF jamming can be detected by...",
            grounding_scores=[0.85, 0.78, 0.92],
            rejected_qras=1,
            response_time_ms=245.5,
            user_expertise="intermediate",
        )

        print("Logged interaction:")
        print(json.dumps(entry, indent=2))

        # Log out-of-scope
        logger.log_interaction(
            session_id="session-001",
            user_id="user-abc",
            query="What's the weather?",
            intent_result={"action": "NO_MATCH", "confidence": 0.0},
            response="That's outside SPARTA's scope...",
            grounding_scores=[],
            rejected_qras=0,
            response_time_ms=50.0,
        )

        # Get summary
        summary = logger.get_session_summary("session-001")
        print("\nSession summary:")
        print(json.dumps(summary, indent=2))

        daily = logger.get_daily_summary()
        print("\nDaily summary:")
        print(json.dumps(daily, indent=2))

        print("\nAll tests passed!")
