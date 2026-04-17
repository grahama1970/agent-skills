#!/usr/bin/env python3
"""
Persona validation: test personas against ground truth or Q&A.

Includes simulacrum-style probes that test philosophy and reasoning
rather than Wikipedia trivia.
"""

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .persona import (
    get_persona,
    run_skill,
)
from .quality_metrics import PersonaQualityScore
from .quality_diagnose import diagnose_persona

from loguru import logger as log


@dataclass
class ValidationTest:
    """A single validation test case."""
    question: str
    expected_contains: list[str] = field(default_factory=list)  # Must contain these
    expected_not_contains: list[str] = field(default_factory=list)  # Must not contain
    min_confidence: float = 0.0  # Minimum relevance score


def validate_persona(
    name: str,
    scope: str = "personas",
    tests: Optional[list[ValidationTest]] = None,
    ground_truth_file: Optional[Path] = None,
) -> PersonaQualityScore:
    """
    Validate a persona by testing Q&A responses.

    Args:
        name: Persona name
        scope: Memory scope
        tests: List of ValidationTest cases
        ground_truth_file: YAML/JSON file with test cases

    Returns:
        PersonaQualityScore with test results
    """
    # First run diagnosis
    score = diagnose_persona(name, scope)

    # Load tests from file if provided
    if ground_truth_file and ground_truth_file.exists():
        tests = _load_tests_from_file(ground_truth_file, name)

    if not tests:
        # Generate default tests based on persona
        tests = _generate_default_tests(name, scope)

    if not tests:
        log.warning("No tests to run for %s", name)
        return score

    # Run tests
    passed = 0
    failed = 0
    details = []

    for test in tests:
        result = _run_single_test(name, scope, test)
        details.append(result)

        if result["passed"]:
            passed += 1
        else:
            failed += 1

    score.tests_passed = passed
    score.tests_failed = failed
    score.test_details = details

    # Calculate accuracy score
    total = passed + failed
    if total > 0:
        score.accuracy = passed / total

    return score


def _load_tests_from_file(path: Path, persona_name: str) -> list[ValidationTest]:
    """Load validation tests from YAML or JSON file."""
    tests = []

    try:
        if path.suffix in (".yaml", ".yml"):
            import yaml
            data = yaml.safe_load(path.read_text())
        else:
            data = json.loads(path.read_text())

        # Look for tests matching this persona
        persona_tests = data.get(persona_name, data.get("default", []))

        for t in persona_tests:
            tests.append(ValidationTest(
                question=t["question"],
                expected_contains=t.get("expected_contains", []),
                expected_not_contains=t.get("expected_not_contains", []),
                min_confidence=t.get("min_confidence", 0.0),
            ))
    except Exception as e:
        log.error("Failed to load tests from %s: %s", path, e)

    return tests


def _generate_default_tests(name: str, scope: str) -> list[ValidationTest]:
    """
    Generate simulacrum-style tests that probe philosophy and reasoning.

    NOT Wikipedia trivia like "When was X born?"
    YES philosophy probes like "How would you approach X?" or "Why did you choose Y?"

    The goal is to test if the persona can REASON like the real person,
    not just regurgitate facts about them.
    """
    persona = get_persona(name, scope)
    if not persona:
        return []

    tests = []

    # Get persona's domain and expertise for context
    domain = (persona.domain or "").lower()
    expertise = [e.lower() for e in (persona.expertise or [])]
    bridges = list(persona.bridge_weights.keys()) if persona.bridge_weights else []

    # -------------------------------------------------------------------------
    # Philosophy/Worldview Test
    # -------------------------------------------------------------------------
    # Ask about their core philosophy - should reveal their worldview
    tests.append(ValidationTest(
        question=f"What is {name}'s core philosophy or approach to their work?",
        expected_contains=[],  # We check for coherent reasoning, not specific words
        expected_not_contains=["wikipedia", "born in", "died in"],  # No trivia
    ))

    # -------------------------------------------------------------------------
    # Reasoning/Decision Test
    # -------------------------------------------------------------------------
    # Ask WHY they would make a specific choice - tests reasoning ability
    if "film" in domain or "animation" in domain or "director" in domain:
        tests.append(ValidationTest(
            question=f"How would {name} approach a scene that needs to convey deep emotion without dialogue?",
            expected_contains=[],
            expected_not_contains=["i don't know", "no information"],
        ))
    elif "music" in domain or "composer" in domain:
        tests.append(ValidationTest(
            question=f"How would {name} build tension in a musical piece?",
            expected_contains=[],
            expected_not_contains=["i don't know", "no information"],
        ))
    elif "writing" in domain or "author" in domain or "writer" in domain:
        tests.append(ValidationTest(
            question=f"How would {name} develop a morally ambiguous character?",
            expected_contains=[],
            expected_not_contains=["i don't know", "no information"],
        ))
    elif "science" in domain or "research" in domain:
        tests.append(ValidationTest(
            question=f"How would {name} approach a problem where conventional methods have failed?",
            expected_contains=[],
            expected_not_contains=["i don't know", "no information"],
        ))
    else:
        tests.append(ValidationTest(
            question=f"What would {name} say is the biggest mistake people make in their field?",
            expected_contains=[],
            expected_not_contains=["i don't know", "no information"],
        ))

    # -------------------------------------------------------------------------
    # Technique/Craft Test
    # -------------------------------------------------------------------------
    # Ask about specific techniques - should reveal deep craft knowledge
    if expertise:
        exp = expertise[0]
        tests.append(ValidationTest(
            question=f"What is {name}'s unique approach to {exp}? What makes it distinctive?",
            expected_contains=[],
            expected_not_contains=["no specific information"],
        ))

    # -------------------------------------------------------------------------
    # Bridge-Aligned Test (Federated Taxonomy)
    # -------------------------------------------------------------------------
    # Test based on their taxonomy bridges
    bridge_questions = {
        "Precision": f"How does {name} ensure accuracy and precision in their work?",
        "Resilience": f"How has {name} dealt with failure or setbacks?",
        "Fragility": f"What does {name} see as the biggest vulnerabilities in their field?",
        "Corruption": f"What does {name} criticize about the mainstream in their field?",
        "Stealth": f"What subtle techniques does {name} use that most people miss?",
        "Loyalty": f"What principles does {name} refuse to compromise on?",
    }

    for bridge in bridges[:2]:  # Test up to 2 bridges
        if bridge in bridge_questions:
            tests.append(ValidationTest(
                question=bridge_questions[bridge],
                expected_contains=[],
                expected_not_contains=["no information", "i don't know"],
            ))

    return tests


def _generate_simulacrum_probe(name: str, scope: str, probe_type: str = "philosophy") -> ValidationTest:
    """
    Generate a single deep simulacrum probe.

    Probe types:
    - philosophy: Core worldview and beliefs
    - technique: Specific craft methods
    - motivation: Why they make choices
    - criticism: What they oppose/critique
    - hypothetical: How they'd handle a new scenario
    - bridge_traversal: Cross-domain connection via taxonomy bridges
    """
    persona = get_persona(name, scope)

    probes = {
        "philosophy": [
            f"What drives {name}'s creative decisions at the deepest level?",
            f"What would {name} say art/their-work is ultimately FOR?",
            f"What belief does {name} hold that most peers would disagree with?",
        ],
        "technique": [
            f"Walk me through how {name} would approach a new project from the very beginning.",
            f"What technical choice does {name} make that others in their field typically don't?",
            f"How does {name}'s process differ from the conventional approach?",
        ],
        "motivation": [
            f"Why does {name} continue working when they could have stopped long ago?",
            f"What personal experience shaped how {name} approaches their work?",
            f"What is {name} trying to prove or communicate through their work?",
        ],
        "criticism": [
            f"What does {name} think is fundamentally wrong with modern {persona.domain if persona else 'practice'}?",
            f"Who or what would {name} criticize in their field, and why?",
            f"What popular trend does {name} refuse to follow?",
        ],
        "hypothetical": [
            f"If {name} were starting their career today, what would they do differently?",
            f"How would {name} solve a problem that seems impossible by conventional means?",
            f"What advice would {name} give to someone just starting in their field?",
        ],
        # Bridge traversal probes test cross-domain reasoning via Federated Taxonomy
        "bridge_traversal": _generate_bridge_traversal_probes(name, persona),
    }

    questions = probes.get(probe_type, probes["philosophy"])

    # Handle bridge_traversal which returns a list of ValidationTests
    if probe_type == "bridge_traversal" and questions:
        return random.choice(questions) if questions else ValidationTest(
            question=f"How does {name}'s approach connect to broader principles?",
            expected_contains=[],
            expected_not_contains=["no information"],
        )

    return ValidationTest(
        question=random.choice(questions) if questions else f"What is {name}'s core philosophy?",
        expected_contains=[],
        expected_not_contains=["wikipedia", "born", "died", "no information", "i don't know"],
    )


def _generate_bridge_traversal_probes(name: str, persona) -> list[ValidationTest]:
    """
    Generate bridge traversal probes based on persona's bridge weights.

    Tests if the persona can connect concepts across domains using
    the Federated Taxonomy bridges (Precision, Resilience, Fragility, etc.)
    """
    if not persona or not persona.bridge_weights:
        return []

    probes = []
    bridges = list(persona.bridge_weights.keys())

    # Bridge-specific cross-domain questions
    bridge_probe_templates = {
        "Precision": [
            f"How does {name}'s attention to detail influence their broader philosophy?",
            f"What can other fields learn from {name}'s methodical approach?",
            f"How would {name}'s precision translate to solving a completely different problem?",
        ],
        "Resilience": [
            f"What do {name}'s experiences with failure teach about endurance in any field?",
            f"How does {name}'s approach to setbacks parallel fault tolerance in systems?",
            f"What makes {name}'s work endure while others fade?",
        ],
        "Fragility": [
            f"What vulnerabilities does {name} acknowledge in their own approach?",
            f"How does {name} use awareness of fragility to create stronger work?",
            f"What does {name}'s handling of delicate subjects teach about emotional intelligence?",
        ],
        "Corruption": [
            f"How does {name} view decay and decline as creative forces?",
            f"What corrupting influences does {name} intentionally embrace or reject?",
            f"How does {name}'s work explore moral compromise or hidden decay?",
        ],
        "Loyalty": [
            f"What traditions or principles does {name} remain loyal to despite pressure to change?",
            f"How does {name} balance loyalty to craft with evolution of style?",
            f"What does {name}'s commitment to their vision teach about integrity?",
        ],
        "Stealth": [
            f"What subtle techniques does {name} use that audiences might miss on first viewing?",
            f"How does {name} hide complexity beneath apparent simplicity?",
            f"What hidden layers exist in {name}'s most accessible work?",
        ],
    }

    for bridge in bridges[:3]:  # Test top 3 bridges
        if bridge in bridge_probe_templates:
            question = random.choice(bridge_probe_templates[bridge])
            probes.append(ValidationTest(
                question=question,
                expected_contains=[],  # Looking for coherent reasoning, not keywords
                expected_not_contains=["no information", "i don't know", "wikipedia"],
            ))

    return probes


def _run_single_test(name: str, scope: str, test: ValidationTest) -> dict:
    """
    Run a single validation test with simulacrum-aware evaluation.

    For simulacrum testing, we evaluate:
    1. Substantiveness: Is the answer more than "I don't know"?
    2. Coherence: Does it sound like reasoned thought?
    3. Persona alignment: Does it reflect the persona's known style?
    4. No trivia: Not just regurgitating Wikipedia facts
    """
    result = {
        "question": test.question,
        "passed": False,
        "answer": "",
        "failures": [],
        "quality_notes": [],
    }

    # Query /ask
    ask_result = run_skill("ask", [
        "ask", test.question,
        "--scope", scope,
        "--k", "5",
    ], timeout=90)

    if ask_result["returncode"] != 0:
        result["failures"].append(f"Query failed: {ask_result['stderr'][:100]}")
        return result

    answer = ask_result["stdout"]
    answer_lower = answer.lower()
    result["answer"] = answer[:1000]  # Keep more for analysis

    # -------------------------------------------------------------------------
    # Check expected_contains (if specified)
    # -------------------------------------------------------------------------
    for expected in test.expected_contains:
        if expected.lower() not in answer_lower:
            result["failures"].append(f"Missing expected: '{expected}'")

    # -------------------------------------------------------------------------
    # Check expected_not_contains (trivia/failure indicators)
    # -------------------------------------------------------------------------
    for unexpected in test.expected_not_contains:
        if unexpected.lower() in answer_lower:
            result["failures"].append(f"Contains unexpected: '{unexpected}'")

    # -------------------------------------------------------------------------
    # Simulacrum Quality Checks
    # -------------------------------------------------------------------------

    # 1. Substantiveness check - answer should be meaningful
    word_count = len(answer.split())
    if word_count < 20:
        result["failures"].append(f"Answer too short ({word_count} words) - not substantive")
    elif word_count > 50:
        result["quality_notes"].append(f"Substantive answer ({word_count} words)")

    # 2. Failure indicators - signs of no real knowledge
    failure_phrases = [
        "i don't have",
        "no specific information",
        "i cannot find",
        "there is no information",
        "i'm not sure",
        "i don't know",
        "no results found",
        "could not find",
    ]
    for phrase in failure_phrases:
        if phrase in answer_lower:
            result["failures"].append(f"Knowledge gap indicator: '{phrase}'")
            break

    # 3. Trivia indicators - signs of Wikipedia regurgitation vs reasoning
    trivia_phrases = [
        "was born in",
        "died in",
        "is a japanese",
        "is an american",
        "is a british",
        "founded in",
        "established in",
        "according to wikipedia",
    ]
    trivia_count = sum(1 for p in trivia_phrases if p in answer_lower)
    if trivia_count >= 2:
        result["quality_notes"].append("Warning: Answer may be trivia-focused, not reasoning")

    # 4. Reasoning indicators - signs of actual simulacrum thought
    reasoning_phrases = [
        "because",
        "this reflects",
        "the reason",
        "philosophy",
        "approach",
        "believes",
        "would say",
        "perspective",
        "in their view",
        "technique",
        "method",
        "intentionally",
        "deliberately",
    ]
    reasoning_count = sum(1 for p in reasoning_phrases if p in answer_lower)
    if reasoning_count >= 2:
        result["quality_notes"].append(f"Good reasoning indicators ({reasoning_count} found)")

    # 5. First-person indicators - simulacrum speaking AS the persona
    first_person = ["i believe", "i think", "my approach", "i would", "in my view"]
    if any(p in answer_lower for p in first_person):
        result["quality_notes"].append("Persona speaking in first person (good simulacrum)")

    result["passed"] = len(result["failures"]) == 0
    return result


def validate_simulacrum(
    name: str,
    scope: str = "personas",
    probe_types: list[str] = None,
    verbose: bool = False,
) -> PersonaQualityScore:
    """
    Deep simulacrum validation - tests if persona can REASON like the real person.

    Unlike basic validation, this:
    - Asks philosophy/reasoning questions, not trivia
    - Checks for substantive, coherent responses
    - Looks for reasoning patterns, not keyword matches
    - Penalizes Wikipedia-style regurgitation
    - Tests bridge traversal (cross-domain reasoning via Federated Taxonomy)

    Args:
        name: Persona name
        scope: Memory scope
        probe_types: Types of probes (philosophy, technique, motivation, criticism, hypothetical, bridge_traversal)
        verbose: Include detailed quality notes

    Returns:
        PersonaQualityScore with simulacrum-specific metrics
    """
    if probe_types is None:
        # Include bridge_traversal by default for Horus-depth validation
        probe_types = ["philosophy", "technique", "motivation", "bridge_traversal"]

    # Start with basic diagnosis
    score = diagnose_persona(name, scope)

    # Generate and run simulacrum probes
    tests = []
    for probe_type in probe_types:
        test = _generate_simulacrum_probe(name, scope, probe_type)
        tests.append(test)

    # Also include domain-specific default tests
    tests.extend(_generate_default_tests(name, scope))

    # Run all tests
    passed = 0
    failed = 0
    details = []

    for test in tests:
        result = _run_single_test(name, scope, test)
        details.append(result)

        if result["passed"]:
            passed += 1
        else:
            failed += 1

    score.tests_passed = passed
    score.tests_failed = failed
    score.test_details = details

    # Calculate accuracy score
    total = passed + failed
    if total > 0:
        score.accuracy = passed / total

    return score
