"""
QRA Validation Gates for SPARTA-style Question-Reasoning-Answer Generation

This module implements the validation gates from SPARTA Stage 12 for use in prompt-lab:
1. Ambiguity Gate - Checks question length and context keyword usage
2. Entity Anchoring - Verifies questions explicitly name the entities being asked about

Based on: ${HOME}/workspace/experiments/sparta/src/sparta/pipeline_duckdb/12_qra.py

Memory lessons:
- https://github.com/sparta-qra/lessons/23015969 - Entity anchoring definition
- https://github.com/sparta-qra/lessons/23499474 - Ambiguity gate fix (include IDs)
- https://github.com/sparta-qra/lessons/23514182 - Phase 0 context_keywords fix
"""

import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ValidationResult:
    """Result of a validation check."""
    ok: bool
    reason: str
    

class AmbiguityGate:
    """
    Input Guard: Detects ambiguous questions that fail to reference context.
    
    From SPARTA 12_qra.py lines 76-100.
    
    A question passes the ambiguity gate if:
    1. It has >= 5 words (not too short/vague)
    2. It contains at least one context keyword (entity name or ID)
    
    Example context_keywords: ["CM-0049", "Firmware Update Verification", "T1059"]
    """
    
    MIN_WORD_COUNT = 5
    
    @classmethod
    def check(cls, question: str, context_keywords: List[str]) -> ValidationResult:
        """
        Check if question is ambiguous using keyword density and length heuristic.
        
        Args:
            question: The question text to validate
            context_keywords: List of entity names and IDs that should appear in question
                             Example: ["CM-0049", "Firmware Update", "D3-FEV"]
        
        Returns:
            ValidationResult with ok=True if passes, ok=False with reason if fails
        
        Examples:
            >>> AmbiguityGate.check("What does it do?", ["CM-0049", "Firmware Update"])
            ValidationResult(ok=False, reason="Too short (ambiguous)")
            
            >>> AmbiguityGate.check("How does Firmware Update Verification work?", 
            ...                     ["CM-0049", "Firmware Update Verification"])
            ValidationResult(ok=True, reason="Pass")
            
            >>> AmbiguityGate.check("What are the security implications?", ["CM-0049"])
            ValidationResult(ok=False, reason="Missing context keywords (hallucination risk)")
        """
        # 1. Length Check (Too short = likely vague)
        word_count = len(question.split())
        if word_count < cls.MIN_WORD_COUNT:
            return ValidationResult(
                ok=False,
                reason=f"Too short ({word_count} words < {cls.MIN_WORD_COUNT} minimum)"
            )
        
        # 2. Context Keyword Check
        # The question MUST reference specific entities from the context
        question_lower = question.lower()
        found_keywords = [k for k in context_keywords if k.lower() in question_lower]
        
        if not found_keywords:
            return ValidationResult(
                ok=False,
                reason=f"Missing context keywords (hallucination risk). Expected one of: {context_keywords}"
            )
        
        return ValidationResult(ok=True, reason=f"Pass (found: {found_keywords})")


class EntityAnchoring:
    """
    Entity Anchoring: Verifies questions explicitly name entities instead of using pronouns.
    
    From memory lessons:
    - lesson 23015969: "Every question MUST explicitly name the control, technique, or concept"
    - lesson 23446996: "BAD: 'What does it do?' GOOD: 'What does Firmware Update Verification do?'"
    
    This is closely related to Ambiguity Gate but focuses specifically on entity naming.
    
    A question passes entity anchoring if it contains at least one entity identifier
    from the context (name or ID).
    """
    
    # Common pronouns that indicate missing entity anchoring
    PRONOUN_INDICATORS = [
        "it", "this", "that", "these", "those",
        "they", "them", "their", "its",
    ]
    
    @classmethod
    def check(cls, question: str, context_keywords: List[str]) -> ValidationResult:
        """
        Check if question explicitly names entities instead of using pronouns.
        
        Args:
            question: The question text to validate
            context_keywords: List of entity names and IDs that should appear in question
        
        Returns:
            ValidationResult with ok=True if passes, ok=False with reason if fails
        
        Examples:
            >>> EntityAnchoring.check("What does it do?", ["CM-0049", "Firmware Update"])
            ValidationResult(ok=False, reason="Uses pronoun 'it' instead of entity name...")
            
            >>> EntityAnchoring.check("What does Firmware Update Verification do?",
            ...                       ["CM-0049", "Firmware Update Verification"])
            ValidationResult(ok=True, reason="Pass (references: ['Firmware Update Verification'])")
            
            >>> EntityAnchoring.check("How does this prevent attacks?", ["CM-0049"])
            ValidationResult(ok=False, reason="Uses pronoun 'this' instead of entity name...")
        """
        question_lower = question.lower()
        
        # Check for entity references
        found_keywords = [k for k in context_keywords if k.lower() in question_lower]
        
        # Check for pronoun usage
        words = question_lower.split()
        found_pronouns = [p for p in cls.PRONOUN_INDICATORS if p in words]
        
        # If uses pronouns and no entities, fail
        if found_pronouns and not found_keywords:
            return ValidationResult(
                ok=False,
                reason=f"Uses pronoun(s) {found_pronouns} instead of entity name. "
                       f"Expected one of: {context_keywords}. "
                       f"BAD: 'What does it do?' GOOD: 'What does {context_keywords[0]} do?'"
            )
        
        # If uses pronouns BUT also names entities, warn but pass
        if found_pronouns and found_keywords:
            return ValidationResult(
                ok=True,
                reason=f"Pass but contains pronouns {found_pronouns}. "
                       f"References entities: {found_keywords}"
            )
        
        # If no entity references at all, fail
        if not found_keywords:
            return ValidationResult(
                ok=False,
                reason=f"No entity references found. Expected one of: {context_keywords}"
            )
        
        # All good - names entities, no problem pronouns
        return ValidationResult(
            ok=True,
            reason=f"Pass (references: {found_keywords})"
        )

    @staticmethod
    def _entity_mentioned(keywords: List[str], question_lower: str) -> bool:
        """
        Check if any keyword (or significant part) is mentioned in the question.

        Handles:
        - Exact matches (case-insensitive)
        - ID patterns (CWE-xxx, T1xxx, CM-xxxx, RD-x.x)
        - Parenthetical parts of long CWE names
        - Significant trailing phrases for very long names (40+ chars)
        """
        for keyword in keywords:
            if not keyword:
                continue
            keyword_lower = keyword.lower()

            # Direct match
            if keyword_lower in question_lower:
                return True

            # ID pattern matching (CWE-xxx, T1xxx, CM-xxxx, RD-x.x)
            if re.match(r'^(cwe-\d+|t\d+\.?\d*|cm-?\d+|rd-\d+\.?\d*)', keyword_lower):
                if keyword_lower in question_lower:
                    return True

            # Parenthetical parts of long CWE names like "Improper Input Validation ('Injection')"
            paren_match = re.search(r"\('([^']+)'\)|\(([^)]+)\)", keyword)
            if paren_match:
                paren_text = (paren_match.group(1) or paren_match.group(2)).lower()
                if len(paren_text) > 5 and paren_text in question_lower:
                    return True

            # Significant trailing phrases for long names (30+ chars)
            # e.g., "Credential Access Through Kerberoasting" -> "kerberoasting"
            if len(keyword) >= 30:
                words = keyword.split()
                if len(words) >= 3:
                    # Check last 2 words
                    last_words = ' '.join(words[-2:]).lower()
                    if last_words in question_lower:
                        return True
                    # Also check just the last word if it's substantial
                    if len(words[-1]) > 6 and words[-1].lower() in question_lower:
                        return True

        return False

    @classmethod
    def check_relationship(
        cls,
        question: str,
        entity_a_keywords: List[str],
        entity_b_keywords: List[str]
    ) -> ValidationResult:
        """
        Check if question names BOTH entities in a phase 0 relationship QRA.

        Phase 0 QRAs relate two controls/entities (source + target), so the question
        must explicitly name BOTH to avoid ambiguity.

        Args:
            question: The question text to validate
            entity_a_keywords: Keywords for first entity (e.g., source_control name + ID)
            entity_b_keywords: Keywords for second entity (e.g., target_control name + ID)

        Returns:
            ValidationResult with ok=True if BOTH entities mentioned, False otherwise

        Example:
            >>> EntityAnchoring.check_relationship(
            ...     "How does CM-0049 relate to T1059 Command Execution?",
            ...     ["CM-0049", "Firmware Update"],
            ...     ["T1059", "Command Execution"]
            ... )
            ValidationResult(ok=True, reason="Pass (both entities mentioned)")

            >>> EntityAnchoring.check_relationship(
            ...     "How do these controls relate?",
            ...     ["CM-0049", "Firmware Update"],
            ...     ["T1059", "Command Execution"]
            ... )
            ValidationResult(ok=False, reason="Missing entity_A [...] and entity_B [...] in question")
        """
        question_lower = question.lower()

        a_found = cls._entity_mentioned(entity_a_keywords, question_lower)
        b_found = cls._entity_mentioned(entity_b_keywords, question_lower)

        if a_found and b_found:
            return ValidationResult(ok=True, reason="Pass (both entities mentioned)")

        # Build detailed failure reason
        parts = []
        if not a_found:
            parts.append(f"entity_A {entity_a_keywords}")
        if not b_found:
            parts.append(f"entity_B {entity_b_keywords}")

        return ValidationResult(
            ok=False,
            reason=f"Missing {' and '.join(parts)} in question"
        )


class QuestionQuality:
    """
    Question Quality: Evaluates if questions are corpus-grounded and avoid templates.
    
    QRA questions must:
    1. NOT be simple yes/no questions
    2. NOT follow generic templates ("Does X do Y?", "Is X related to Y?")
    3. Extract SPECIFIC information from the corpus
    4. Show diversity in phrasing and depth
    
    From SPARTA QRA design:
    - Questions should extract different information from source material
    - Avoid repetitive patterns across QRAs
    - Prefer "What/How/Why" over "Does/Is/Can"
    """
    
    # Template indicators (low-quality question patterns)
    YES_NO_INDICATORS = [
        "does", "is", "are", "can", "will", "has", "have",
        "should", "would", "could", "may", "might"
    ]
    
    # Generic template patterns to avoid
    TEMPLATE_PATTERNS = [
        "does {entity} do",
        "is {entity} related to",
        "can {entity} prevent",
        "does {entity} provide",
        "is {entity} a type of",
    ]
    
    # Preferred question starters (open-ended)
    PREFERRED_STARTERS = [
        "what", "how", "why", "which", "when", "where",
        "explain", "describe", "compare", "identify"
    ]
    
    @classmethod
    def check(cls, question: str, expected_complexity: str = "medium") -> ValidationResult:
        """
        Check if question is corpus-grounded and not templated.
        
        Args:
            question: The question text to validate
            expected_complexity: Expected complexity level (simple, medium, complex)
        
        Returns:
            ValidationResult with ok=True if passes, ok=False with reason if fails
        
        Examples:
            >>> QuestionQuality.check("Does CM-0049 prevent attacks?")
            ValidationResult(ok=False, reason="Yes/no question (starts with 'does')")
            
            >>> QuestionQuality.check("What specific cryptographic algorithms does CM-0049 use?")
            ValidationResult(ok=True, reason="Pass (open-ended, specific)")
            
            >>> QuestionQuality.check("Is Firmware Update Verification related to security?")
            ValidationResult(ok=False, reason="Generic template question")
        """
        question_lower = question.lower().strip()
        first_word = question_lower.split()[0] if question_lower else ""
        
        # Check for yes/no questions
        if first_word in cls.YES_NO_INDICATORS:
            return ValidationResult(
                ok=False,
                reason=f"Yes/no question (starts with '{first_word}'). "
                       f"Prefer open-ended: What/How/Why/Explain."
            )
        
        # Check for generic templates
        question_pattern = question_lower.replace("?", "").strip()
        
        # Only flag truly generic templates (no technical specificity)
        # Good questions like "What specific algorithms..." should pass
        has_specificity_markers = any(marker in question_lower for marker in [
            "specific", "exactly", "precisely", "which", "particular",
            "algorithm", "mechanism", "implementation", "technique",
            "method", "process", "procedure", "step", "phase",
            "verify", "validate", "authenticate", "cryptographic",
            "rollback", "downgrade", "unauthorized", "attack", "threat"
        ])
        
        # Generic patterns we DO want to catch
        truly_generic = [
            "what does {entity} do",  # Too vague
            "is {entity} related to", # Generic relationship
            "does {entity} provide",  # Vague action
        ]
        
        if not has_specificity_markers:
            # No technical specificity - check for generic patterns
            for template in truly_generic:
                template_core = template.replace("{entity}", "").strip()
                if template_core in question_pattern:
                    return ValidationResult(
                        ok=False,
                        reason=f"Generic template question without technical specificity. "
                               f"Add: specific mechanisms/algorithms/steps/phases."
                    )
        
        # Check for preferred open-ended starters
        has_preferred_starter = any(question_lower.startswith(p) for p in cls.PREFERRED_STARTERS)
        
        if not has_preferred_starter:
            return ValidationResult(
                ok=False,
                reason=f"Question doesn't use preferred starters (What/How/Why/Explain). "
                       f"Current: '{first_word}'"
            )
        
        # Check for specificity (avoid generic asking)
        # Generic indicators: "generally", "overall", "in general", "typically"
        generic_terms = ["generally", "overall", "in general", "typically", "usually"]
        if any(term in question_lower for term in generic_terms):
            return ValidationResult(
                ok=False,
                reason="Question uses generic terms (generally/overall/typically). "
                       "Ask about SPECIFIC mechanisms/implementations from corpus."
            )
        
        # Check minimum complexity for non-simple questions
        word_count = len(question.split())
        if expected_complexity == "medium" and word_count < 8:
            return ValidationResult(
                ok=False,
                reason=f"Question too short for '{expected_complexity}' complexity "
                       f"({word_count} words < 8 minimum). Add specificity."
            )
        
        if expected_complexity == "complex" and word_count < 12:
            return ValidationResult(
                ok=False,
                reason=f"Question too short for '{expected_complexity}' complexity "
                       f"({word_count} words < 12 minimum). Add depth/multi-part reasoning."
            )
        
        return ValidationResult(
            ok=True,
            reason=f"Pass (open-ended, {'specific' if word_count >= 8 else 'adequate'})"
        )


def validate_qra_question(
    question: str,
    context_keywords: List[str],
    check_ambiguity: bool = True,
    check_entity_anchoring: bool = True,
    check_quality: bool = True,
    expected_complexity: str = "medium"
) -> dict:
    """
    Run all QRA validation gates on a question.
    
    Args:
        question: The question text to validate
        context_keywords: List of entity names and IDs that should appear in question
        check_ambiguity: Whether to run ambiguity gate (default: True)
        check_entity_anchoring: Whether to run entity anchoring (default: True)
        check_quality: Whether to run question quality check (default: True)
        expected_complexity: Expected complexity level for quality check (simple/medium/complex)
    
    Returns:
        Dict with validation results:
        {
            "ok": bool,  # Overall pass/fail
            "ambiguity_gate": ValidationResult,
            "entity_anchoring": ValidationResult,
            "question_quality": ValidationResult,
            "failed_gates": List[str]  # Names of failed gates
        }
    
    Example:
        >>> result = validate_qra_question(
        ...     "What specific verification steps does CM-0049 perform before firmware installation?",
        ...     ["CM-0049", "Firmware Update Verification"],
        ...     check_quality=True
        ... )
        >>> print(result["ok"])
        True
    """
    results = {
        "ok": True,
        "failed_gates": []
    }
    
    if check_ambiguity:
        ambiguity_result = AmbiguityGate.check(question, context_keywords)
        results["ambiguity_gate"] = ambiguity_result
        if not ambiguity_result.ok:
            results["ok"] = False
            results["failed_gates"].append("ambiguity_gate")
    
    if check_entity_anchoring:
        anchoring_result = EntityAnchoring.check(question, context_keywords)
        results["entity_anchoring"] = anchoring_result
        if not anchoring_result.ok:
            results["ok"] = False
            results["failed_gates"].append("entity_anchoring")
    
    if check_quality:
        quality_result = QuestionQuality.check(question, expected_complexity)
        results["question_quality"] = quality_result
        if not quality_result.ok:
            results["ok"] = False
            results["failed_gates"].append("question_quality")
    
    return results


# Example usage
if __name__ == "__main__":
    # Test cases from SPARTA
    test_cases = [
        {
            "question": "What does it do?",
            "keywords": ["CM-0049", "Firmware Update Verification"],
            "expected": False,
            "reason": "Too short + pronoun + no entity"
        },
        {
            "question": "What does Firmware Update Verification do?",
            "keywords": ["CM-0049", "Firmware Update Verification"],
            "expected": False,  # Too short for medium complexity
            "reason": "Names entity but too short for medium complexity"
        },
        {
            "question": "How does CM-0049 prevent malicious firmware installation?",
            "keywords": ["CM-0049", "Firmware Update Verification"],
            "expected": False,  # 7 words < 8 minimum for medium
            "reason": "Good but too short for medium complexity (7 words)"
        },
        {
            "question": "What are the security implications?",
            "keywords": ["CM-0049", "Firmware Update Verification"],
            "expected": False,
            "reason": "No entity references"
        },
        {
            "question": "How does this control validate firmware authenticity before installation?",
            "keywords": ["CM-0049", "Firmware Update Verification"],
            "expected": False,  # Uses "this" pronoun, no entity name/ID
            "reason": "Uses pronoun but no entity name/ID"
        },
        {
            "question": "Does CM-0049 prevent attacks?",
            "keywords": ["CM-0049", "Firmware Update Verification"],
            "expected": False,
            "reason": "Yes/no question (low quality)"
        },
        {
            "question": "Is Firmware Update Verification related to security?",
            "keywords": ["CM-0049", "Firmware Update Verification"],
            "expected": False,
            "reason": "Yes/no generic template"
        },
        {
            "question": "What specific cryptographic algorithms does CM-0049 use to verify firmware signatures?",
            "keywords": ["CM-0049", "Firmware Update Verification"],
            "expected": True,
            "reason": "Open-ended, specific, corpus-grounded"
        },
        {
            "question": "How does CM-0049 handle firmware rollback attacks and what specific mechanisms prevent unauthorized version downgrades?",
            "keywords": ["CM-0049", "Firmware Update Verification"],
            "expected": True,
            "reason": "Complex multi-part question"
        },
        {
            "question": "Can Firmware Update Verification be bypassed?",
            "keywords": ["CM-0049", "Firmware Update Verification"],
            "expected": False,
            "reason": "Yes/no question (starts with 'can')"
        },
    ]
    
    print("QRA Validation Gate Tests (with Quality Checks)")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test['reason']}")
        print(f"Question: {test['question']}")
        print(f"Keywords: {test['keywords']}")
        
        result = validate_qra_question(
            test["question"], 
            test["keywords"],
            check_quality=True
        )
        
        print(f"Expected: {'PASS' if test['expected'] else 'FAIL'}")
        print(f"Actual: {'PASS' if result['ok'] else 'FAIL'}")
        
        if not result["ok"]:
            print(f"Failed gates: {result['failed_gates']}")
            if "ambiguity_gate" in result:
                print(f"  - Ambiguity: {result['ambiguity_gate'].reason}")
            if "entity_anchoring" in result:
                print(f"  - Anchoring: {result['entity_anchoring'].reason}")
            if "question_quality" in result:
                print(f"  - Quality: {result['question_quality'].reason}")
        else:
            if "question_quality" in result:
                print(f"  ✓ Quality: {result['question_quality'].reason}")
        
        match = result["ok"] == test["expected"]
        status = '✓ PASS' if match else '✗ FAIL'
        print(f"Result: {status}")
        
        if match:
            passed += 1
        else:
            failed += 1
    
    print("\n" + "=" * 80)
    print(f"Standard tests: {passed}/{len(test_cases)} passed")

    # Relationship tests for check_relationship method (phase 0 QRAs)
    print("\n" + "=" * 80)
    print("Relationship Anchoring Tests (Phase 0 QRAs)")
    print("=" * 80)

    relationship_tests = [
        {
            "question": "How does CM-0049 relate to T1059 Command Execution?",
            "entity_a": ["CM-0049", "Firmware Update"],
            "entity_b": ["T1059", "Command Execution"],
            "expected": True,
            "reason": "Both entities named explicitly"
        },
        {
            "question": "How do these controls relate?",
            "entity_a": ["CM-0049", "Firmware Update"],
            "entity_b": ["T1059", "Command Execution"],
            "expected": False,
            "reason": "No entities named (uses pronoun)"
        },
        {
            "question": "How does Firmware Update Verification mitigate Command Execution attacks?",
            "entity_a": ["CM-0049", "Firmware Update Verification"],
            "entity_b": ["T1059", "Command and Scripting Interpreter"],
            "expected": False,
            "reason": "Only entity A named, missing entity B ID or full name"
        },
        {
            "question": "What mechanisms does CM-0049 use against T1059?",
            "entity_a": ["CM-0049", "Firmware Update"],
            "entity_b": ["T1059", "Command Execution"],
            "expected": True,
            "reason": "Both IDs present"
        },
        {
            "question": "How does the Improper Input Validation ('Injection') weakness relate to kerberoasting techniques?",
            "entity_a": ["CWE-74", "Improper Input Validation ('Injection')"],
            "entity_b": ["T1558.003", "Credential Access Through Kerberoasting"],
            "expected": True,
            "reason": "Parenthetical match for CWE + trailing phrase for technique"
        },
    ]

    rel_passed = 0
    rel_failed = 0

    for i, test in enumerate(relationship_tests, 1):
        print(f"\nRelationship Test {i}: {test['reason']}")
        print(f"Question: {test['question']}")
        print(f"Entity A: {test['entity_a']}")
        print(f"Entity B: {test['entity_b']}")

        result = EntityAnchoring.check_relationship(
            test["question"],
            test["entity_a"],
            test["entity_b"]
        )

        print(f"Expected: {'PASS' if test['expected'] else 'FAIL'}")
        print(f"Actual: {'PASS' if result.ok else 'FAIL'}")
        print(f"Reason: {result.reason}")

        match = result.ok == test["expected"]
        status = '✓ PASS' if match else '✗ FAIL'
        print(f"Result: {status}")

        if match:
            rel_passed += 1
        else:
            rel_failed += 1

    print("\n" + "=" * 80)
    print(f"Relationship tests: {rel_passed}/{len(relationship_tests)} passed")

    total_passed = passed + rel_passed
    total_tests = len(test_cases) + len(relationship_tests)
    total_failed = failed + rel_failed

    print("\n" + "=" * 80)
    print(f"TOTAL: {total_passed}/{total_tests} tests passed")

    if total_failed > 0:
        print(f"❌ {total_failed} tests failed")
        exit(1)
    else:
        print("✅ All tests passed!")
        exit(0)
