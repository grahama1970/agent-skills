"""DAG schema constants aligned with $ask validation messages."""

from __future__ import annotations

import re

ASK_DAG_SCHEMA_VERSION = "ask.dag.v1"
SCILLM_EXEC_GRAPH_VERSION = "scillm.exec.graph.v1"
NODE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")
ALLOWED_NODE_TYPES = frozenset({
    "memory.recall",
    "dogpile.search",
    "ask.oracle",
    "skill.run",
})
