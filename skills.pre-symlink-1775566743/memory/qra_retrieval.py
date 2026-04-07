#!/usr/bin/env python3
"""QRA Retrieval - Queries SPARTA DuckDB for relevant QRAs.

Uses the QuerySpec from intent mapper to search for relevant
Question-Reasoning-Answer pairs from the SPARTA knowledge base.

Usage:
    from qra_retrieval import search_qras, QRARetriever

    qras = search_qras(query_spec, limit=5)
"""

import json
import os
from pathlib import Path
from typing import Any

from loguru import logger

# Default SPARTA database path
DEFAULT_DB_PATH = Path(os.environ.get(
    "SPARTA_DB_PATH",
    str(Path.home() / "workspace/experiments/sparta/data/runs/"
        "run-recovery-verify-8k-backup-20260205_193440/backups/"
        "sparta_2540qras_20260205_131019.duckdb"),
))


class QRARetriever:
    """Retrieves QRAs from SPARTA DuckDB."""

    def __init__(self, db_path: Path | str | None = None):
        """Initialize retriever.

        Args:
            db_path: Path to SPARTA DuckDB. Uses default if None.
        """
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self._conn = None

    def _get_connection(self):
        """Get DuckDB connection (lazy init)."""
        if self._conn is None:
            import duckdb
            self._conn = duckdb.connect(str(self.db_path), read_only=True)
        return self._conn

    def close(self):
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def search(
        self,
        query_spec: dict[str, Any],
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search QRAs based on QuerySpec.

        Args:
            query_spec: QuerySpec from intent mapper
            limit: Maximum results to return

        Returns:
            List of QRA dicts with grounding scores
        """
        conn = self._get_connection()

        # Build search query based on spec
        where_clauses = []
        params = []

        # Filter by tier1 (tactical tags)
        tier1 = query_spec.get("tier1", [])
        if tier1:
            tier_conditions = []
            for t in tier1:
                tier_conditions.append("tactical_tags LIKE ?")
                params.append(f"%{t}%")
            where_clauses.append(f"({' OR '.join(tier_conditions)})")

        # Filter by entities (control/technique IDs)
        entities = query_spec.get("entities", [])
        if entities:
            entity_conditions = []
            for e in entities:
                entity_conditions.append("(control_id LIKE ? OR question LIKE ?)")
                params.extend([f"%{e}%", f"%{e}%"])
            where_clauses.append(f"({' OR '.join(entity_conditions)})")

        # Combine clauses
        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        # Build full query
        sql = f"""
        SELECT
            qra_id,
            control_id,
            question,
            reasoning,
            answer,
            citations,
            confidence,
            conceptual_tags,
            tactical_tags,
            grounding_score
        FROM qra
        WHERE {where_sql}
        ORDER BY grounding_score DESC
        LIMIT ?
        """
        params.append(limit)

        try:
            result = conn.execute(sql, params).fetchall()
            columns = [
                "qra_id", "control_id", "question", "reasoning", "answer",
                "citations", "confidence", "conceptual_tags", "tactical_tags",
                "grounding_score"
            ]

            qras = []
            for row in result:
                qra = dict(zip(columns, row))
                # Parse JSON fields
                if isinstance(qra.get("citations"), str):
                    try:
                        qra["citations"] = json.loads(qra["citations"])
                    except json.JSONDecodeError:
                        qra["citations"] = []
                if isinstance(qra.get("conceptual_tags"), str):
                    try:
                        qra["conceptual_tags"] = json.loads(qra["conceptual_tags"])
                    except json.JSONDecodeError:
                        qra["conceptual_tags"] = []
                if isinstance(qra.get("tactical_tags"), str):
                    try:
                        qra["tactical_tags"] = json.loads(qra["tactical_tags"])
                    except json.JSONDecodeError:
                        qra["tactical_tags"] = []
                qras.append(qra)

            logger.debug(f"Found {len(qras)} QRAs for spec: {query_spec.get('tier1', [])} / {query_spec.get('entities', [])}")
            return qras

        except Exception as e:
            logger.error(f"QRA search failed: {e}")
            return []

    def search_text(
        self,
        query_text: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Full-text search in QRAs.

        Args:
            query_text: Free text query
            limit: Maximum results

        Returns:
            List of matching QRAs
        """
        conn = self._get_connection()

        # Simple text search across question and answer
        sql = """
        SELECT
            qra_id,
            control_id,
            question,
            reasoning,
            answer,
            citations,
            confidence,
            conceptual_tags,
            tactical_tags,
            grounding_score
        FROM qra
        WHERE
            question LIKE ?
            OR answer LIKE ?
        ORDER BY grounding_score DESC
        LIMIT ?
        """

        search_pattern = f"%{query_text}%"

        try:
            result = conn.execute(sql, [search_pattern, search_pattern, limit]).fetchall()
            columns = [
                "qra_id", "control_id", "question", "reasoning", "answer",
                "citations", "confidence", "conceptual_tags", "tactical_tags",
                "grounding_score"
            ]
            return [dict(zip(columns, row)) for row in result]
        except Exception as e:
            logger.error(f"Text search failed: {e}")
            return []

    def get_stats(self) -> dict[str, Any]:
        """Get database statistics."""
        conn = self._get_connection()
        try:
            total = conn.execute("SELECT COUNT(*) FROM qra").fetchone()[0]
            avg_grounding = conn.execute("SELECT AVG(grounding_score) FROM qra").fetchone()[0]
            return {
                "total_qras": total,
                "avg_grounding": round(avg_grounding, 3) if avg_grounding else 0,
                "db_path": str(self.db_path),
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {"error": str(e)}


# Singleton instance
_retriever_instance: QRARetriever | None = None


def get_retriever() -> QRARetriever:
    """Get singleton retriever instance."""
    global _retriever_instance
    if _retriever_instance is None:
        _retriever_instance = QRARetriever()
    return _retriever_instance


def search_qras(query_spec: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    """Convenience function to search QRAs.

    Args:
        query_spec: QuerySpec from intent mapper
        limit: Maximum results

    Returns:
        List of QRA dicts
    """
    return get_retriever().search(query_spec, limit=limit)


if __name__ == "__main__":
    import sys

    retriever = QRARetriever()
    stats = retriever.get_stats()
    print(f"Database: {stats}")

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        results = retriever.search_text(query, limit=3)
        print(f"\nSearch for '{query}':")
        for qra in results:
            print(f"  [{qra['control_id']}] {qra['question'][:60]}...")
            print(f"    Grounding: {qra['grounding_score']:.2f}")
