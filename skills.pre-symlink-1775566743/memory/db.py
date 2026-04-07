"""
Memory Skill - ArangoDB Connection Utility
Canonical provider for ArangoDB database objects used across skills.
"""
import os
from typing import Any, List, Tuple
from arango import ArangoClient

# Collections that must exist for the memory system to function.
# Format: (name, edge) — edge=True for edge collections.
REQUIRED_COLLECTIONS: List[Tuple[str, bool]] = [
    ("lessons", False),
    ("lesson_edges", True),
    ("lesson_embeddings", False),
    ("persona_journals", False),
    ("taxonomy_bridges", False),
    ("taxonomy_edges", True),
    ("personas", False),
    ("skill_chains", False),
]


def get_db(url: str = None, db_name: str = None, user: str = None, password: str = None) -> Any:
    """
    Get a connection to the Memory ArangoDB instance.
    Prioritizes explicit arguments, then environment variables, then defaults.
    """
    url = url or os.getenv("ARANGO_URL", "http://127.0.0.1:8529")
    db_name = db_name or os.getenv("ARANGO_DB", "memory")
    user = user or os.getenv("ARANGO_USER", "root")
    password = password or os.getenv("ARANGO_PASS", "")

    client = ArangoClient(hosts=url)
    return client.db(db_name, username=user, password=password)


def ensure_collections(db: Any = None) -> List[str]:
    """Ensure all required collections exist, creating any that are missing.

    Returns list of newly created collection names.
    """
    if db is None:
        db = get_db()

    created = []
    for name, is_edge in REQUIRED_COLLECTIONS:
        if not db.has_collection(name):
            db.create_collection(name, edge=is_edge)
            created.append(name)
    return created
