"""Deterministic feature extraction from ELF binary strings.

Extracts KH.literal values, enum assignments, JSON-RPC methods,
and Zod schema fields using regex on semicolon-split statements.
No LLM needed — these are structural patterns with zero ambiguity.

The LLM is used downstream for CLASSIFICATION (which literals are
event types vs content types), not extraction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from elf_parser import extract_statements
from loguru import logger


@dataclass
class DeterministicFeatures:
    """Features extracted deterministically from binary strings."""

    literals: list[str] = field(default_factory=list)
    enums: dict[str, list[str]] = field(default_factory=dict)
    jsonrpc_methods: list[str] = field(default_factory=list)
    schemas: dict[str, list[dict]] = field(default_factory=dict)


def extract_all(binary_path: str) -> DeterministicFeatures:
    """Extract all deterministic features from an ELF binary."""
    features = DeterministicFeatures()

    # 1. KH.literal values
    stmts = extract_statements(binary_path, pattern=r'KH\.literal\(')
    for s in stmts:
        for m in re.finditer(r'KH\.literal\(["\'](\w+)["\']\)', s):
            val = m.group(1)
            if val not in features.literals:
                features.literals.append(val)
    logger.info(f"Extracted {len(features.literals)} KH.literal values")

    # 2. Enum assignments: M.Key="value"
    stmts2 = extract_statements(
        binary_path, pattern=r'[A-Z]\w*\.\w+\s*=\s*"[a-z_]+"'
    )
    for s in stmts2:
        for m in re.finditer(r'([A-Z]\w*)\.(\w+)\s*=\s*"([a-z_]+)"', s):
            var, _key, val = m.group(1), m.group(2), m.group(3)
            features.enums.setdefault(var, [])
            if val not in features.enums[var]:
                features.enums[var].append(val)

    # Filter to meaningful enums (3+ states, at least 2 with underscores)
    filtered = {}
    for var, vals in features.enums.items():
        underscore = [v for v in vals if "_" in v]
        if len(underscore) >= 2 and len(vals) <= 30:
            filtered[var] = vals
    features.enums = filtered
    logger.info(f"Extracted {len(features.enums)} enum groups")

    # 3. JSON-RPC methods: method:KH.literal("dotted.name")
    stmts3 = extract_statements(
        binary_path, pattern=r'method:\s*KH\.literal'
    )
    seen_methods: set[str] = set()
    for s in stmts3:
        for m in re.finditer(r'method:\s*KH\.literal\(["\']([a-z_.]+)["\']\)', s):
            name = m.group(1)
            if name not in seen_methods:
                seen_methods.add(name)
                features.jsonrpc_methods.append(name)
    logger.info(f"Extracted {len(features.jsonrpc_methods)} JSON-RPC methods")

    # 4. Zod schemas: varName=KH.object({field:KH.type(),...})
    stmts4 = extract_statements(binary_path, pattern=r'KH\.object\(\{')
    for s in stmts4:
        obj_match = re.match(r'(\w+)\s*=\s*KH\.object\(\{(.+)\}\)', s)
        if obj_match:
            name = obj_match.group(1)
            body = obj_match.group(2)
            # Capture field name AND KH type (e.g., KH.string(), KH.number())
            typed_fields = [
                {"name": m[0], "type": m[1]}
                for m in re.findall(r'(\w+):\s*KH\.(\w+)\(', body)
            ]
            if len(typed_fields) >= 3:
                features.schemas[name] = typed_fields
    logger.info(f"Extracted {len(features.schemas)} schemas")

    return features
