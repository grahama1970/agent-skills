"""DAG schema constants aligned with $ask validation messages."""

from __future__ import annotations

import re

ASK_DAG_SCHEMA_VERSION = "ask.dag.v1"
SCILLM_EXEC_GRAPH_VERSION = "scillm.exec.graph.v1"
NODE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")

SCILLM_CALL_TO_NODE_TYPE: dict[str, str] = {
    "one-shot": "ask.oracle",
    "oneshot": "ask.oracle",
    "llm": "ask.oracle",
    "oracle": "ask.oracle",
    "ask.oracle": "ask.oracle",
    "memory.recall": "memory.recall",
    "memory": "memory.recall",
    "recall": "memory.recall",
    "dogpile.search": "dogpile.search",
    "dogpile": "dogpile.search",
    "research": "dogpile.search",
    "skill.run": "skill.run",
    "skill": "skill.run",
    "subagent": "skill.run",
    "subagent-runner": "skill.run",
    "deterministic": "skill.run",
    "command": "skill.run",
}

SCILLM_RAW_TYPE_TO_NODE_TYPE: dict[str, str] = {
    "scillm_call": "ask.oracle",
    "llm": "ask.oracle",
    "oracle": "ask.oracle",
    "memory": "memory.recall",
    "research": "dogpile.search",
    "skill": "skill.run",
    "deterministic": "skill.run",
    "command": "skill.run",
}

PHART_GIT_REV = "e3b482118a413ad694ac2176c3959d80e1422ef8"

ALLOWED_NODE_TYPES = frozenset({
    "memory.recall",
    "dogpile.search",
    "ask.oracle",
    "skill.run",
})
