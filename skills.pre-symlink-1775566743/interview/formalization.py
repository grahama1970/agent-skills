#!/usr/bin/env python3
"""
Formalization Module for Interview Skill

Supports SPARTA and other high-precision domains that require
Lean4-convertible formal specifications before proceeding.

The standard: KEEP ASKING until the request CAN be expressed in Lean4.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from interview import Question, Option


class AmbiguityType(str, Enum):
    """Types of ambiguity that prevent Lean4 conversion."""
    MISSING_ENTITY = "missing_entity"       # No specific entity ID
    VAGUE_RELATION = "vague_relation"       # "helps with" instead of "mitigates"
    UNBOUND_PRONOUN = "unbound_pronoun"     # "it", "this", "they"
    MISSING_QUANTIFIER = "missing_quantifier"  # "some" instead of "∀" or "∃"
    MISSING_TYPE = "missing_type"           # No type annotation
    MISSING_BOUNDS = "missing_bounds"       # No range specified


@dataclass
class Ambiguity:
    """A detected ambiguity that prevents Lean4 conversion."""
    type: AmbiguityType
    description: str
    location: str  # What part of the request
    question: Question  # The clarifying question to ask


@dataclass
class FormalSpec:
    """A Lean4-convertible formal specification."""
    lean4_repr: str           # Lean4 representation (may be pseudo-code)
    entities: list[str]       # Entity IDs involved
    relations: list[str]      # Relationship types
    quantifiers: list[str]    # ∀, ∃, etc.
    types: dict[str, str]     # Variable: Type mappings
    is_verified: bool = False # Whether it compiles in Lean4


# =============================================================================
# ENTITY PATTERNS (for SPARTA and similar domains)
# =============================================================================

ENTITY_PATTERNS = {
    "sparta_control": r'(CM-\d{4,5})',
    "sparta_technique": r'(ST\d{4})',
    "mitre_technique": r'(T\d{4}(?:\.\d{3})?)',
    "cwe": r'(CWE-\d+)',
    "cve": r'(CVE-\d{4}-\d+)',
    "d3fend": r'(D3-[A-Z]{2,4})',
    "nist_control": r'([A-Z]{2}-\d{1,2}(?:\.\d{1,2})?)',
}

VAGUE_RELATION_WORDS = [
    "helps with", "related to", "about", "regarding", "concerning",
    "affects", "impacts", "involves", "deals with", "pertains to",
]

EXPLICIT_RELATIONS = {
    "mitigates": "Control reduces risk of technique",
    "prevents": "Control blocks technique entirely",
    "detects": "Control identifies technique occurrence",
    "enables": "Technique enables another technique",
    "requires": "Technique requires prerequisite",
    "exploits": "Attack exploits weakness",
    "implements": "Control implements requirement",
    "violates": "Action violates policy",
}

PRONOUNS = ["it", "this", "that", "these", "those", "they", "them", "its", "their"]

VAGUE_QUANTIFIERS = ["some", "many", "few", "several", "sometimes", "often", "usually", "mostly"]


# =============================================================================
# AMBIGUITY DETECTION
# =============================================================================

def detect_ambiguities(request: str, domain: str = "sparta") -> list[Ambiguity]:
    """
    Detect all ambiguities that prevent Lean4 conversion.

    Returns a list of Ambiguity objects, each with a Question to ask.
    """
    ambiguities = []
    request_lower = request.lower()

    # 1. Check for unbound pronouns
    for pronoun in PRONOUNS:
        pattern = rf'\b{pronoun}\b'
        if re.search(pattern, request_lower):
            # Check if there's an entity nearby that binds it
            has_entity = any(
                re.search(p, request) for p in ENTITY_PATTERNS.values()
            )
            if not has_entity:
                ambiguities.append(Ambiguity(
                    type=AmbiguityType.UNBOUND_PRONOUN,
                    description=f"Pronoun '{pronoun}' has no explicit referent",
                    location=f"'{pronoun}' in request",
                    question=_make_entity_question(pronoun, domain)
                ))
                break  # One pronoun question at a time

    # 2. Check for vague relations
    for vague in VAGUE_RELATION_WORDS:
        if vague in request_lower:
            ambiguities.append(Ambiguity(
                type=AmbiguityType.VAGUE_RELATION,
                description=f"Vague relation '{vague}' - what specific relationship?",
                location=f"'{vague}' in request",
                question=_make_relation_question(vague)
            ))
            break  # One relation question at a time

    # 3. Check for missing entity (if no entities found at all)
    has_any_entity = any(
        re.search(p, request) for p in ENTITY_PATTERNS.values()
    )
    if not has_any_entity and not any(a.type == AmbiguityType.UNBOUND_PRONOUN for a in ambiguities):
        ambiguities.append(Ambiguity(
            type=AmbiguityType.MISSING_ENTITY,
            description="No specific entity identified",
            location="entire request",
            question=_make_entity_discovery_question(domain)
        ))

    # 4. Check for vague quantifiers (in math/logic contexts)
    math_keywords = ['sum', 'prove', 'show', 'theorem', 'formula', 'all', 'every', 'any']
    if any(kw in request_lower for kw in math_keywords):
        for vague_q in VAGUE_QUANTIFIERS:
            if vague_q in request_lower:
                ambiguities.append(Ambiguity(
                    type=AmbiguityType.MISSING_QUANTIFIER,
                    description=f"Vague quantifier '{vague_q}' - need ∀ or ∃",
                    location=f"'{vague_q}' in request",
                    question=_make_quantifier_question(vague_q)
                ))
                break

    return ambiguities


def can_convert_to_lean4(request: str, domain: str = "sparta") -> tuple[bool, list[Ambiguity]]:
    """
    Check if a request can be converted to Lean4.

    Returns (can_convert, ambiguities).
    If can_convert is True, ambiguities is empty.
    """
    ambiguities = detect_ambiguities(request, domain)
    return len(ambiguities) == 0, ambiguities


def try_convert_to_lean4(request: str, domain: str = "sparta") -> Optional[FormalSpec]:
    """
    Attempt to convert a request to Lean4-like formal spec.

    Returns None if ambiguities remain.
    """
    can_convert, ambiguities = can_convert_to_lean4(request, domain)
    if not can_convert:
        return None

    # Extract entities
    entities = []
    for name, pattern in ENTITY_PATTERNS.items():
        for match in re.finditer(pattern, request):
            entities.append(match.group(1))

    # Detect relation
    relations = []
    request_lower = request.lower()
    for rel in EXPLICIT_RELATIONS.keys():
        if rel in request_lower:
            relations.append(rel)

    # Build Lean4-like representation
    if len(entities) >= 2 and relations:
        lean4_repr = f"def query : Prop := {relations[0]}({entities[0]}, {entities[1]})"
    elif len(entities) == 1:
        lean4_repr = f"def query : Entity := {entities[0]}"
    else:
        lean4_repr = f"-- Could not fully formalize: {request[:50]}"

    return FormalSpec(
        lean4_repr=lean4_repr,
        entities=entities,
        relations=relations,
        quantifiers=[],
        types={e: "Entity" for e in entities},
        is_verified=False
    )


# =============================================================================
# QUESTION GENERATORS
# =============================================================================

def _make_entity_question(pronoun: str, domain: str) -> Question:
    """Generate a question to resolve a pronoun to an entity."""

    if domain == "sparta":
        options = [
            Option(
                label="SPARTA Control (CM-XXXX)",
                description="A defensive control from the SPARTA framework"
            ),
            Option(
                label="SPARTA Technique (STXXXX)",
                description="An attack technique from the SPARTA framework"
            ),
            Option(
                label="MITRE ATT&CK Technique (T1XXX)",
                description="A technique from the MITRE ATT&CK framework"
            ),
            Option(
                label="CWE Weakness (CWE-XXX)",
                description="A weakness from the Common Weakness Enumeration"
            ),
        ]
    else:
        options = [
            Option(label="I'll provide a specific ID", description="Enter the exact identifier"),
            Option(label="General concept (no specific ID)", description="Proceed without specific entity"),
        ]

    return Question(
        id=f"resolve_pronoun_{pronoun}",
        header="Entity",
        text=f"What does '{pronoun}' refer to? Please provide a specific ID.",
        type="select",
        options=options,
        required=True,
        multi_select=False
    )


def _make_entity_discovery_question(domain: str) -> Question:
    """Generate a question to discover what entity the user is asking about."""

    if domain == "sparta":
        options = [
            Option(
                label="A specific control",
                description="E.g., CM-0049 (Network Segmentation)"
            ),
            Option(
                label="A specific technique",
                description="E.g., T1422 (Constellation Hopping)"
            ),
            Option(
                label="A relationship between entities",
                description="E.g., how CM-0049 mitigates T1422"
            ),
            Option(
                label="General concept",
                description="No specific entity (lower precision)"
            ),
        ]
    else:
        options = [
            Option(label="Specific entity", description="I'll provide an ID"),
            Option(label="General question", description="No specific entity needed"),
        ]

    return Question(
        id="discover_entity",
        header="Subject",
        text="What specific entity or relationship is this question about?",
        type="select",
        options=options,
        required=True,
        multi_select=False
    )


def _make_relation_question(vague_word: str) -> Question:
    """Generate a question to clarify a vague relationship."""

    options = [
        Option(label="mitigates", description=EXPLICIT_RELATIONS["mitigates"]),
        Option(label="prevents", description=EXPLICIT_RELATIONS["prevents"]),
        Option(label="detects", description=EXPLICIT_RELATIONS["detects"]),
        Option(label="enables", description=EXPLICIT_RELATIONS["enables"]),
        Option(label="exploits", description=EXPLICIT_RELATIONS["exploits"]),
    ]

    return Question(
        id="clarify_relation",
        header="Relation",
        text=f"You said '{vague_word}'. What is the precise relationship?",
        type="select",
        options=options,
        required=True,
        multi_select=False
    )


def _make_quantifier_question(vague_quantifier: str) -> Question:
    """Generate a question to clarify a vague quantifier."""

    options = [
        Option(
            label="For all (∀)",
            description="Universal quantifier - applies to every case"
        ),
        Option(
            label="There exists (∃)",
            description="Existential quantifier - applies to at least one case"
        ),
        Option(
            label="Specific range",
            description="I'll specify the exact range (e.g., i ∈ [0, n))"
        ),
    ]

    return Question(
        id="clarify_quantifier",
        header="Quantifier",
        text=f"You said '{vague_quantifier}'. What is the precise quantifier?",
        type="select",
        options=options,
        required=True,
        multi_select=False
    )


# =============================================================================
# FORMALIZATION LOOP
# =============================================================================

def generate_formalization_questions(
    request: str,
    domain: str = "sparta",
    previous_answers: dict[str, Any] | None = None
) -> tuple[list[Question], Optional[FormalSpec]]:
    """
    Generate the next set of clarifying questions to formalize a request.

    Returns (questions, formal_spec):
    - If questions is empty and formal_spec is not None: formalization complete
    - If questions is not empty: need to ask these questions
    - If both empty: something went wrong

    This is the core function for iterative formalization via /interview.
    """
    # Apply previous answers to refine the request
    refined_request = _apply_answers(request, previous_answers or {})

    # Try to convert
    spec = try_convert_to_lean4(refined_request, domain)
    if spec is not None:
        return [], spec  # Success!

    # Detect ambiguities and generate questions
    ambiguities = detect_ambiguities(refined_request, domain)
    questions = [amb.question for amb in ambiguities]

    return questions, None


def _apply_answers(request: str, answers: dict[str, Any]) -> str:
    """Apply interview answers to refine the request."""
    refined = request

    for q_id, answer in answers.items():
        value = answer.get("value", "") if isinstance(answer, dict) else str(answer)

        # Handle entity resolution
        if "resolve_pronoun" in q_id or q_id == "discover_entity":
            # Extract entity ID from answer if present
            id_match = re.search(r'([A-Z]{1,4}-\d{4,5}|T\d{4}|CWE-\d+)', str(value))
            if id_match:
                entity_id = id_match.group(1)
                # Replace first pronoun with entity
                for pronoun in PRONOUNS:
                    pattern = rf'\b{pronoun}\b'
                    if re.search(pattern, refined, re.IGNORECASE):
                        refined = re.sub(pattern, entity_id, refined, count=1, flags=re.IGNORECASE)
                        break

        # Handle relation clarification
        if q_id == "clarify_relation":
            for vague in VAGUE_RELATION_WORDS:
                if vague in refined.lower():
                    refined = re.sub(
                        rf'\b{re.escape(vague)}\b',
                        value,
                        refined,
                        count=1,
                        flags=re.IGNORECASE
                    )
                    break

        # Handle quantifier clarification
        if q_id == "clarify_quantifier":
            for vague_q in VAGUE_QUANTIFIERS:
                if vague_q in refined.lower():
                    quant_map = {
                        "For all (∀)": "for all",
                        "There exists (∃)": "there exists",
                    }
                    replacement = quant_map.get(value, value)
                    refined = re.sub(
                        rf'\b{vague_q}\b',
                        replacement,
                        refined,
                        count=1,
                        flags=re.IGNORECASE
                    )
                    break

    return refined


# =============================================================================
# SPARTA-SPECIFIC HELPERS
# =============================================================================

def make_sparta_formalization_session(request: str) -> dict:
    """
    Create an interview session configuration for SPARTA formalization.

    Use this to start a formalization loop via the interview skill.
    """
    questions, spec = generate_formalization_questions(request, domain="sparta")

    return {
        "title": "SPARTA Request Formalization",
        "context": (
            "To ensure precision in space cybersecurity QRA generation, "
            "your request must be unambiguous and formally specifiable. "
            "Please answer these clarifying questions."
        ),
        "domain": "sparta",
        "original_request": request,
        "formalization_mode": True,
        "exit_criterion": "lean4_convertible",
        "questions": [q.__dict__ for q in questions] if questions else [],
        "formal_spec": spec.__dict__ if spec else None,
        "iteration": 1,
        "max_iterations": 5,
    }


def format_formal_spec_preview(spec: FormalSpec) -> str:
    """Format a formal spec for display to the user."""
    lines = [
        "═══════════════════════════════════════════════════════",
        "FORMAL SPECIFICATION (Lean4-like)",
        "═══════════════════════════════════════════════════════",
        "",
        spec.lean4_repr,
        "",
        f"Entities:  {', '.join(spec.entities) or 'None'}",
        f"Relations: {', '.join(spec.relations) or 'None'}",
        f"Types:     {spec.types or 'None'}",
        f"Verified:  {'✓' if spec.is_verified else '○ (not compiled)'}",
        "",
        "═══════════════════════════════════════════════════════",
    ]
    return "\n".join(lines)


# =============================================================================
# CLI
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python formalization.py <request>")
        print("Example: python formalization.py 'How does it help with security?'")
        sys.exit(1)

    request = " ".join(sys.argv[1:])
    print(f"Request: {request}\n")

    can_convert, ambiguities = can_convert_to_lean4(request)

    if can_convert:
        spec = try_convert_to_lean4(request)
        print("✓ Request is Lean4-convertible!")
        print(format_formal_spec_preview(spec))
    else:
        print(f"✗ Found {len(ambiguities)} ambiguities:\n")
        for amb in ambiguities:
            print(f"  [{amb.type.value}] {amb.description}")
            print(f"    Question: {amb.question.text}")
            if amb.question.options:
                for opt in amb.question.options:
                    print(f"      - {opt.label}: {opt.description}")
            print()
