#!/usr/bin/env python3
"""Loader for the persona/relationship cognition contract (Defect 5).

Phases 13 (self-interpretation), 14 (ToM validation), and 16 (behavior
evaluation) carry NO hardcoded persona strings. Every persona id, counterpart
id, relationship descriptor, recall-question template, protected-identity
anchor, and phase-16 evaluation vocabulary string is externalized into ONE
fixture contract that satisfies
``contracts/persona_dream_cognition_contract.v1.schema.json``. Swap the fixture
to retarget the cognitive loop to a different persona/relationship lane.

The default fixture for the current lane is
``fixtures/persona_dream_cognition_contract.embry_kai_surf.v1.json`` and may be
overridden with the ``PERSONA_DREAM_COGNITION_CONTRACT`` environment variable or
an explicit path argument.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_SKILL_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONTRACT_PATH = (
    _SKILL_ROOT / "fixtures" / "persona_dream_cognition_contract.embry_kai_surf.v1.json"
)
CONTRACT_SCHEMA_ID = "persona_dream.persona_dream_cognition_contract.v1"


def contract_path(explicit: Path | str | None = None) -> Path:
    if explicit:
        return Path(explicit)
    env = os.environ.get("PERSONA_DREAM_COGNITION_CONTRACT")
    if env:
        return Path(env)
    return DEFAULT_CONTRACT_PATH


def load_contract(explicit: Path | str | None = None) -> dict[str, Any]:
    """Load and minimally validate the cognition contract. Fail closed."""
    path = contract_path(explicit)
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"cognition contract must be a JSON object: {path}")
    if value.get("schema") != CONTRACT_SCHEMA_ID:
        raise ValueError(
            f"cognition contract wrong schema: {value.get('schema')!r} (expected {CONTRACT_SCHEMA_ID})"
        )
    for field in ("persona_id", "persona_title", "default_subject", "default_target",
                  "counterparts", "recall_question_templates", "protected_identity_anchors"):
        if not value.get(field):
            raise ValueError(f"cognition contract missing required field: {field} ({path})")
    return value


def primary_counterpart(contract: dict[str, Any]) -> dict[str, Any]:
    counterparts = contract.get("counterparts") or []
    if not counterparts:
        raise ValueError("cognition contract has no counterparts")
    return counterparts[0]


def recall_questions(contract: dict[str, Any]) -> list[str]:
    """Fill the recall-question templates from persona/counterpart slots."""
    persona_title = contract["persona_title"]
    counterpart_title = primary_counterpart(contract)["title"]
    out: list[str] = []
    for tmpl in contract["recall_question_templates"]:
        out.append(tmpl.format(persona_title=persona_title, counterpart_title=counterpart_title))
    return out
