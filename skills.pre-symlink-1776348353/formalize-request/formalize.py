#!/usr/bin/env python3
"""
Formalize Request Skill

Iteratively convert natural language requests into Lean4-like formal specifications.
Keep asking clarifying questions via /interview until the request is formalizable.
"""

import os
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import typer

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

app = typer.Typer(help="Formalize natural language requests into Lean4-like specs")

SKILL_DIR = Path(__file__).parent
SKILLS_DIR = SKILL_DIR.parent
INTERVIEW_SKILL = SKILLS_DIR / "interview"
LEAN4_PROVE_SKILL = SKILLS_DIR / "lean4-prove"


class SpecType(str, Enum):
    """
    Formal specification types.

    For SPARTA and retrieval-focused domains:
    - RETRIEVAL and COMPARISON are the PRIMARY targets (99% of queries)
    - LEAN4 is ONLY for mathematical/logical proofs (rare)

    Entity-anchored specs ARE formal specifications - they're verifiable
    against the taxonomy and prevent hallucination.
    """
    RETRIEVAL = "retrieval"      # Entity-anchored knowledge query
    COMPARISON = "comparison"    # Entity-anchored A vs B query
    LEAN4 = "lean4"              # Mathematical/logical proof ONLY
    UNKNOWN = "unknown"


@dataclass
class Ambiguity:
    """Represents a detected ambiguity in the request."""
    aspect: str  # entity, relation, type, bound, quantifier
    description: str
    question: str
    options: list[str] = field(default_factory=list)


@dataclass
class FormalSpec:
    """A formalized specification."""
    spec_type: SpecType
    spec: dict[str, Any]
    confidence: float  # 0.0-1.0
    lean4_goal: Optional[str] = None  # For LEAN4 type


@dataclass
class FormalizationResult:
    """Result of the formalization process."""
    success: bool
    nl_request: str
    refined_request: str
    formal_spec: Optional[FormalSpec]
    iterations: int
    ambiguities_resolved: list[str]
    exit_reason: str  # "success", "user_opt_out", "max_iterations"


# =============================================================================
# AMBIGUITY DETECTION
# =============================================================================

# Patterns that indicate ambiguity
PRONOUN_PATTERNS = [
    r'\b(it|this|that|these|those|they|them)\b',
    r'\b(the control|the technique|the attack)\b',  # Missing specific ID
]

VAGUE_RELATION_PATTERNS = [
    r'\b(helps? with|related to|about|regarding|concerning)\b',
    r'\b(affects?|impacts?|involves?)\b',  # Too vague
]

VAGUE_QUANTIFIER_PATTERNS = [
    r'\b(some|many|few|several|sometimes|often|usually)\b',
]

# Entity ID patterns (things we WANT to see)
ENTITY_ID_PATTERNS = [
    r'\b([A-Z]{1,4}-\d{4,5})\b',  # CM-0049, T1422, REC-0001
    r'\b(T\d{4}(?:\.\d{3})?)\b',  # MITRE ATT&CK: T1059, T1059.001
    r'\b(CWE-\d+)\b',  # CWE-628
    r'\b(CVE-\d{4}-\d+)\b',  # CVE-2024-1234
]


def detect_ambiguities(request: str) -> list[Ambiguity]:
    """Detect ambiguities in a user request."""
    ambiguities = []
    request_lower = request.lower()

    # Check for pronouns without entity anchors
    for pattern in PRONOUN_PATTERNS:
        if re.search(pattern, request_lower):
            # Check if there are entity IDs to anchor to
            has_entity_ids = any(
                re.search(p, request) for p in ENTITY_ID_PATTERNS
            )
            if not has_entity_ids:
                ambiguities.append(Ambiguity(
                    aspect="entity",
                    description="Pronouns used without specific entity IDs",
                    question="Which specific entity are you referring to?",
                    options=[
                        "A SPARTA control (e.g., CM-0049)",
                        "A MITRE technique (e.g., T1422)",
                        "A CWE weakness (e.g., CWE-628)",
                        "Something else (please specify)"
                    ]
                ))
                break

    # Check for vague relationships
    for pattern in VAGUE_RELATION_PATTERNS:
        match = re.search(pattern, request_lower)
        if match:
            ambiguities.append(Ambiguity(
                aspect="relation",
                description=f"Vague relationship: '{match.group()}'",
                question="What specific relationship are you asking about?",
                options=[
                    "Mitigates (control reduces risk of technique)",
                    "Prevents (control blocks technique entirely)",
                    "Detects (control identifies technique)",
                    "Compares (similarities/differences between entities)",
                    "Proves (mathematical/logical proof)"
                ]
            ))
            break

    # Check for vague quantifiers (especially in math/logic contexts)
    math_keywords = ['sum', 'prove', 'show', 'theorem', 'formula', 'equation']
    if any(kw in request_lower for kw in math_keywords):
        for pattern in VAGUE_QUANTIFIER_PATTERNS:
            if re.search(pattern, request_lower):
                ambiguities.append(Ambiguity(
                    aspect="quantifier",
                    description="Vague quantifier in mathematical context",
                    question="What are the precise bounds or quantifiers?",
                    options=[
                        "For all (∀) - universal quantifier",
                        "There exists (∃) - existential quantifier",
                        "Specific range (e.g., i ∈ [0, n))",
                        "Let me specify the exact bounds"
                    ]
                ))
                break

    # Check for missing entity if question seems to be about a specific thing
    question_words = ['what', 'how', 'why', 'when', 'which']
    if any(request_lower.startswith(qw) for qw in question_words):
        has_entity_ids = any(
            re.search(p, request) for p in ENTITY_ID_PATTERNS
        )
        if not has_entity_ids and not any(a.aspect == "entity" for a in ambiguities):
            # Check if it's a general question that's OK without entity
            general_patterns = [
                r'what is the (difference|relationship)',
                r'how (do|does|can|should)',
                r'why (is|are|do|does)',
            ]
            is_general = any(re.search(p, request_lower) for p in general_patterns)

            if not is_general:
                ambiguities.append(Ambiguity(
                    aspect="entity",
                    description="Question lacks specific entity reference",
                    question="Which specific control, technique, or concept?",
                    options=[
                        "I'll provide a specific ID (e.g., CM-0049, T1422)",
                        "I want a general answer (no specific entity)",
                    ]
                ))

    return ambiguities


# =============================================================================
# SPEC TYPE CLASSIFICATION
# =============================================================================

def classify_spec_type(request: str) -> SpecType:
    """Classify what type of formal spec this request needs."""
    request_lower = request.lower()

    # Math/Logic/Proof indicators
    math_keywords = [
        'prove', 'theorem', 'lemma', 'show that', 'demonstrate',
        'sum', 'product', 'integral', 'derivative',
        'for all', 'there exists', '∀', '∃',
        'implies', 'if and only if', 'iff',
    ]
    if any(kw in request_lower for kw in math_keywords):
        return SpecType.LEAN4

    # Comparison indicators
    comparison_keywords = [
        'compare', 'versus', 'vs', 'difference between',
        'better', 'worse', 'more effective', 'less effective',
        'which one', 'which is',
    ]
    if any(kw in request_lower for kw in comparison_keywords):
        return SpecType.COMPARISON

    # Default to retrieval
    return SpecType.RETRIEVAL


# =============================================================================
# FORMAL SPEC CONVERSION
# =============================================================================

def try_convert_to_spec(request: str) -> tuple[Optional[FormalSpec], list[Ambiguity]]:
    """
    Try to convert request to formal spec.
    Returns (spec, []) if successful, (None, ambiguities) if not.
    """
    ambiguities = detect_ambiguities(request)

    if ambiguities:
        return None, ambiguities

    spec_type = classify_spec_type(request)

    if spec_type == SpecType.LEAN4:
        spec, lean4_goal = convert_to_lean4_spec(request)
        return FormalSpec(
            spec_type=spec_type,
            spec=spec,
            confidence=0.9 if lean4_goal else 0.7,
            lean4_goal=lean4_goal
        ), []

    elif spec_type == SpecType.COMPARISON:
        spec = convert_to_comparison_spec(request)
        return FormalSpec(
            spec_type=spec_type,
            spec=spec,
            confidence=0.8
        ), []

    else:  # RETRIEVAL
        spec = convert_to_retrieval_spec(request)
        return FormalSpec(
            spec_type=spec_type,
            spec=spec,
            confidence=0.85
        ), []


def convert_to_retrieval_spec(request: str) -> dict:
    """Convert to retrieval spec."""
    spec = {
        "type": "retrieval",
        "entities": [],
        "relation": None,
        "constraints": []
    }

    # Extract entity IDs
    for pattern in ENTITY_ID_PATTERNS:
        for match in re.finditer(pattern, request):
            spec["entities"].append({
                "id": match.group(1),
                "raw": match.group(0)
            })

    # Detect relation type
    request_lower = request.lower()
    if 'mitigat' in request_lower:
        spec["relation"] = "mitigates"
    elif 'prevent' in request_lower:
        spec["relation"] = "prevents"
    elif 'detect' in request_lower:
        spec["relation"] = "detects"
    elif 'exploit' in request_lower:
        spec["relation"] = "exploits"

    return spec


def convert_to_comparison_spec(request: str) -> dict:
    """Convert to comparison spec."""
    spec = {
        "type": "comparison",
        "entities": [],
        "aspects": [],
        "context": None
    }

    # Extract entity IDs
    for pattern in ENTITY_ID_PATTERNS:
        for match in re.finditer(pattern, request):
            spec["entities"].append({
                "id": match.group(1),
                "raw": match.group(0)
            })

    # Detect comparison aspects
    request_lower = request.lower()
    if 'effective' in request_lower:
        spec["aspects"].append("effectiveness")
    if 'cost' in request_lower or 'expensive' in request_lower:
        spec["aspects"].append("cost")
    if 'implement' in request_lower:
        spec["aspects"].append("implementation")

    # Default aspects if none detected
    if not spec["aspects"]:
        spec["aspects"] = ["general_comparison"]

    return spec


# Removed: memory accessed via httpx to Unix socket (see _memory_cmd)
def _memory_cmd(args: list, timeout: int = 60) -> dict:
    """Call embry-memory daemon via Unix socket HTTP API."""
    str_args = [str(a) for a in args]
    subcmd = str_args[0] if str_args else ""
    rest = str_args[1:]

    # Parse CLI-style flags into a dict
    params: dict = {}
    list_keys: dict[str, list] = {}
    i = 0
    while i < len(rest):
        if rest[i].startswith("--"):
            key = rest[i][2:].replace("-", "_")
            if i + 1 < len(rest) and not rest[i + 1].startswith("--"):
                val = rest[i + 1]
                if key in ("tag", "tags", "collections"):
                    list_keys.setdefault(key, []).append(val)
                else:
                    params[key] = val
                i += 2
            else:
                params[key] = True
                i += 1
        else:
            i += 1
    for k, v in list_keys.items():
        params[k] = v

    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    with httpx.Client(transport=transport, base_url="http://localhost", timeout=float(timeout)) as client:
        if subcmd == "recall":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("k", params.get("limit", 5)))}
            for opt in ("scope", "threshold"):
                if opt in params:
                    body[opt] = float(params[opt]) if opt == "threshold" else params[opt]
            if "collections" in params:
                c = params["collections"]
                body["collections"] = c if isinstance(c, list) else [c]
            if "tags" in params:
                t = params["tags"]
                body["tags"] = t if isinstance(t, list) else [t]
            resp = client.post("/recall", json=body)
        elif subcmd == "learn":
            body = {"problem": params.get("problem", ""), "solution": params.get("solution", "")}
            if "scope" in params:
                body["scope"] = params["scope"]
            if "collection" in params:
                body["scope"] = params["collection"]
            if "tag" in params:
                body["tags"] = params["tag"] if isinstance(params["tag"], list) else [params["tag"]]
            if "tags" in params:
                body["tags"] = params["tags"] if isinstance(params["tags"], list) else [params["tags"]]
            if "json" in params:
                body.update(json.loads(params["json"]))
            resp = client.post("/learn", json=body)
        elif subcmd == "count":
            coll = params.get("collection", params.get("scope", "lessons"))
            resp = client.post("/query", json={"aql": f"RETURN LENGTH({coll})", "bind_vars": {}})
        elif subcmd == "sample":
            body = {"collection": params.get("collection", "lessons"), "limit": int(params.get("limit", 10))}
            if "fields" in params:
                body["return_fields"] = [f.strip() for f in str(params["fields"]).split(",")]
            resp = client.post("/list", json=body)
        elif subcmd == "tag":
            if "doc" in params:
                doc = json.loads(params["doc"]) if isinstance(params["doc"], str) else params["doc"]
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [doc]})
            elif "key" in params:
                tags_val = params.get("tags", "[]")
                tags_list = json.loads(tags_val) if isinstance(tags_val, str) else tags_val
                field = params.get("field", "tags")
                resp = client.post("/upsert", json={"collection": params.get("collection", "lessons"), "documents": [{"_key": params["key"], field: tags_list}]})
            else:
                raise RuntimeError(f"Unsupported tag args: {rest}")
        elif subcmd == "search":
            body = {"q": params.get("q", params.get("query", "")), "k": int(params.get("limit", 10))}
            if "collection" in params:
                body["collections"] = [params["collection"]]
            if "scope" in params:
                body["scope"] = params["scope"]
            resp = client.post("/recall", json=body)
        else:
            raise RuntimeError(f"Unsupported memory subcommand via httpx: {subcmd}")
        resp.raise_for_status()
        return resp.json()

def verify_entity_spec(spec: dict, taxonomy_db: str = "sparta") -> tuple[bool, str, list[str]]:
    """
    Verify an entity spec against a taxonomy database via /memory recall.
    Returns (success, message, unverified_entities).

    This is the KEY verification for SPARTA - entities must exist in the taxonomy.
    """
    unverified = []

    entities = spec.get("entities", [])
    if not entities:
        return False, "No entities specified", []

    try:
        for entity in entities:
            entity_id = entity.get("id") if isinstance(entity, dict) else entity

            # Query /memory for entity
            result = _memory_cmd([
                "recall", "--q", entity_id,
                "--scope", "brandon_bailey",
                "--k", "1",
            ])
            items = result.get("items", result.get("results", []))
            if not items:
                unverified.append(entity_id)

        if unverified:
            return False, f"Entities not found in taxonomy: {unverified}", unverified
        else:
            return True, f"All {len(entities)} entities verified in taxonomy", []

    except Exception as e:
        return False, f"Verification error: {e}", [
            (e.get("id") if isinstance(e, dict) else str(e)) for e in entities
        ]


def verify_lean4_goal(lean4_code: str) -> tuple[bool, str]:
    """
    Verify a Lean4 goal using the lean4-prove skill.
    Returns (success, message).
    """
    if not LEAN4_PROVE_SKILL.exists():
        return False, "lean4-prove skill not found"

    try:
        # Write goal to temp file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lean', delete=False) as f:
            f.write(lean4_code)
            goal_file = f.name

        # Call lean4-prove to verify (just type-check, don't prove)
        result = subprocess.run(
            ["bash", "run.sh", "check", goal_file],
            cwd=LEAN4_PROVE_SKILL,
            capture_output=True,
            text=True,
            timeout=60,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        Path(goal_file).unlink(missing_ok=True)

        if result.returncode == 0:
            return True, "Lean4 goal type-checks successfully"
        else:
            return False, f"Lean4 type-check failed: {result.stderr[:200]}"

    except subprocess.TimeoutExpired:
        return False, "Lean4 verification timed out"
    except Exception as e:
        return False, f"Lean4 verification error: {e}"


def retrieve_similar_proofs(requirement: str, k: int = 5) -> list[dict]:
    """
    Retrieve similar proofs from memory using lean4-prove skill.
    Useful for few-shot examples in formalization.
    """
    if not LEAN4_PROVE_SKILL.exists():
        return []

    try:
        # Import from lean4-prove skill
        import sys
        sys.path.insert(0, str(LEAN4_PROVE_SKILL))
        from prove import retrieve_similar_proofs as _retrieve

        return _retrieve(requirement, k=k)
    except Exception as e:
        print(f"Warning: Could not retrieve similar proofs: {e}")
        return []


def convert_to_lean4_spec(request: str) -> tuple[dict, Optional[str]]:
    """Convert to Lean4 spec and optionally generate Lean4 goal."""
    spec = {
        "type": "lean4",
        "statement": request,
        "variables": [],
        "hypothesis": None,
        "goal": None,
        "similar_proofs": [],
        "verified": False
    }

    # Try to extract mathematical structure
    # This is a simplified version - real implementation would use LLM

    # Look for sum patterns
    sum_match = re.search(r'sum.*?(\d+).*?to.*?(\w+)', request.lower())
    if sum_match:
        spec["variables"].append({"name": "n", "type": "ℕ"})
        spec["goal"] = "∑ i in Finset.range n, i = n * (n - 1) / 2"

    # Retrieve similar proofs for few-shot context
    similar = retrieve_similar_proofs(request, k=3)
    if similar:
        spec["similar_proofs"] = [
            {"statement": p.get("formal_statement", "")[:200], "tactics": p.get("tactics", [])}
            for p in similar
        ]

    # Generate Lean4 goal if we have enough info
    lean4_goal = None
    if spec.get("goal"):
        lean4_goal = f"""theorem formalized_goal (n : ℕ) : {spec["goal"]} := by
  sorry"""

        # Verify the generated goal
        verified, msg = verify_lean4_goal(lean4_goal)
        spec["verified"] = verified
        spec["verification_msg"] = msg

    return spec, lean4_goal


# =============================================================================
# INTERVIEW INTEGRATION
# =============================================================================

def ask_via_interview(ambiguities: list[Ambiguity]) -> dict[str, str]:
    """Use /interview skill to ask clarifying questions."""

    if not INTERVIEW_SKILL.exists():
        # Fallback to simple prompts
        print("\n[Interview skill not found, using fallback prompts]")
        answers = {}
        for amb in ambiguities:
            print(f"\n{amb.question}")
            for i, opt in enumerate(amb.options, 1):
                print(f"  {i}. {opt}")
            choice = input("Your choice (number or text): ").strip()
            answers[amb.aspect] = choice
        return answers

    # Build interview questions
    questions = []
    for amb in ambiguities:
        questions.append({
            "id": amb.aspect,
            "question": amb.question,
            "description": amb.description,
            "options": amb.options
        })

    # Write questions to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump({"questions": questions}, f)
        questions_file = f.name

    # Call interview skill
    try:
        result = subprocess.run(
            ["bash", "run.sh", "ask", "--questions-file", questions_file, "--json"],
            cwd=INTERVIEW_SKILL,
            capture_output=True,
            text=True,
            timeout=300,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(f"Interview error: {result.stderr}")
            return {}
    except Exception as e:
        print(f"Interview failed: {e}")
        return {}
    finally:
        Path(questions_file).unlink(missing_ok=True)


def refine_request(request: str, answers: dict[str, str]) -> str:
    """Refine the request based on interview answers."""
    refined = request

    # Entity refinement
    if "entity" in answers:
        answer = answers["entity"]
        # Extract ID if user provided one
        id_match = re.search(r'([A-Z]{1,4}-\d{4,5}|T\d{4}(?:\.\d{3})?|CWE-\d+)', answer)
        if id_match:
            entity_id = id_match.group(1)
            # Replace vague references with specific ID
            refined = re.sub(r'\b(it|this|that|the control|the technique)\b',
                           entity_id, refined, count=1, flags=re.IGNORECASE)

    # Relation refinement
    if "relation" in answers:
        answer = answers["relation"].lower()
        if "mitigate" in answer:
            refined = re.sub(r'\b(helps? with|related to)\b', 'mitigates', refined, flags=re.IGNORECASE)
        elif "prevent" in answer:
            refined = re.sub(r'\b(helps? with|related to)\b', 'prevents', refined, flags=re.IGNORECASE)
        elif "detect" in answer:
            refined = re.sub(r'\b(helps? with|related to)\b', 'detects', refined, flags=re.IGNORECASE)

    # Quantifier refinement
    if "quantifier" in answers:
        answer = answers["quantifier"].lower()
        if "for all" in answer or "∀" in answer:
            refined = re.sub(r'\b(some|many|several)\b', 'all', refined, flags=re.IGNORECASE)
        elif "exists" in answer or "∃" in answer:
            refined = re.sub(r'\b(some|many|several)\b', 'some specific', refined, flags=re.IGNORECASE)

    return refined


# =============================================================================
# MAIN FORMALIZATION LOOP
# =============================================================================

def formalize(
    request: str,
    max_iterations: int = 5,
    force: bool = False,
    dry_run: bool = False
) -> FormalizationResult:
    """
    Main formalization loop.
    Keep asking via /interview until the request is formalizable.
    """
    current_request = request
    iterations = 0
    ambiguities_resolved = []

    while iterations < max_iterations:
        iterations += 1

        # Try to convert
        spec, ambiguities = try_convert_to_spec(current_request)

        if spec is not None:
            # Success!
            return FormalizationResult(
                success=True,
                nl_request=request,
                refined_request=current_request,
                formal_spec=spec,
                iterations=iterations,
                ambiguities_resolved=ambiguities_resolved,
                exit_reason="success"
            )

        if dry_run:
            # Just show what would be asked
            print(f"\n[Dry run] Iteration {iterations} would ask:")
            for amb in ambiguities:
                print(f"  - {amb.aspect}: {amb.question}")
            continue

        if force:
            # User wants to proceed anyway
            return FormalizationResult(
                success=False,
                nl_request=request,
                refined_request=current_request,
                formal_spec=None,
                iterations=iterations,
                ambiguities_resolved=ambiguities_resolved,
                exit_reason="user_opt_out"
            )

        # Ask clarifying questions
        print(f"\n[Formalization iteration {iterations}]")
        print(f"Current request: {current_request}")
        print(f"Detected {len(ambiguities)} ambiguities:")
        for amb in ambiguities:
            print(f"  - {amb.aspect}: {amb.description}")

        answers = ask_via_interview(ambiguities)

        if not answers:
            # User cancelled or error
            return FormalizationResult(
                success=False,
                nl_request=request,
                refined_request=current_request,
                formal_spec=None,
                iterations=iterations,
                ambiguities_resolved=ambiguities_resolved,
                exit_reason="user_opt_out"
            )

        # Refine the request
        current_request = refine_request(current_request, answers)
        ambiguities_resolved.extend(answers.keys())

    # Max iterations reached
    return FormalizationResult(
        success=False,
        nl_request=request,
        refined_request=current_request,
        formal_spec=None,
        iterations=iterations,
        ambiguities_resolved=ambiguities_resolved,
        exit_reason="max_iterations"
    )


# =============================================================================
# CLI
# =============================================================================

@app.command()
def run(
    request: str = typer.Argument(..., help="User request to formalize"),
    max_iter: int = typer.Option(5, "--max-iter", "-m", help="Max clarification iterations"),
    force: bool = typer.Option(False, "--force", "-f", help="Proceed even if ambiguous"),
    dry_run: bool = typer.Option(False, "--dry-run", "-d", help="Show what would be asked"),
    output_json: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Formalize a natural language request into Lean4-like spec."""

    result = formalize(request, max_iterations=max_iter, force=force, dry_run=dry_run)

    if output_json:
        output = {
            "success": result.success,
            "nl_request": result.nl_request,
            "refined_request": result.refined_request,
            "iterations": result.iterations,
            "ambiguities_resolved": result.ambiguities_resolved,
            "exit_reason": result.exit_reason,
        }
        if result.formal_spec:
            output["formal_spec"] = {
                "type": result.formal_spec.spec_type.value,
                "spec": result.formal_spec.spec,
                "confidence": result.formal_spec.confidence,
                "lean4_goal": result.formal_spec.lean4_goal,
            }
        print(json.dumps(output, indent=2))
    else:
        print("\n" + "="*60)
        print("FORMALIZATION RESULT")
        print("="*60)
        print(f"Success: {result.success}")
        print(f"Exit reason: {result.exit_reason}")
        print(f"Iterations: {result.iterations}")
        print(f"Original: {result.nl_request}")
        print(f"Refined:  {result.refined_request}")

        if result.formal_spec:
            print(f"\nFormal Spec Type: {result.formal_spec.spec_type.value}")
            print(f"Confidence: {result.formal_spec.confidence:.0%}")
            print(f"Spec: {json.dumps(result.formal_spec.spec, indent=2)}")
            if result.formal_spec.lean4_goal:
                print(f"\nLean4 Goal:\n{result.formal_spec.lean4_goal}")


@app.command()
def check(
    request: str = typer.Argument(..., help="Request to check for ambiguities"),
):
    """Check a request for ambiguities without formalizing."""
    ambiguities = detect_ambiguities(request)

    if not ambiguities:
        print("No ambiguities detected - request is formalizable!")
        spec_type = classify_spec_type(request)
        print(f"Spec type: {spec_type.value}")
    else:
        print(f"Found {len(ambiguities)} ambiguities:")
        for amb in ambiguities:
            print(f"\n  [{amb.aspect}] {amb.description}")
            print(f"  Question: {amb.question}")
            if amb.options:
                print("  Options:")
                for opt in amb.options:
                    print(f"    - {opt}")


if __name__ == "__main__":
    app()
