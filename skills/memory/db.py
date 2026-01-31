"""
Memory Skill - ArangoDB Connection Utility
Canonical provider for ArangoDB database objects used across skills.
"""
import os
from typing import Any
from arango import ArangoClient

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
