"""ArangoDB connection helper for monitor-memory.

Follows the same pattern as ops-arango/maintain.py and memory/db.py.

Inputs: ARANGO_URL, ARANGO_DB, ARANGO_USER, ARANGO_PASS from environment.
Outputs: python-arango StandardDatabase instance.
"""
from __future__ import annotations

import os

from arango import ArangoClient

import config


def get_db():
    """Connect to ArangoDB using environment configuration."""
    client = ArangoClient(hosts=config.ARANGO_URL)
    return client.db(
        config.ARANGO_DB,
        username=os.environ.get("ARANGO_USER", "root"),
        password=os.environ.get("ARANGO_PASS", ""),
    )
