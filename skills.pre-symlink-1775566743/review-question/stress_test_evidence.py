#!/usr/bin/env python3
"""Stress test the evidence case pipeline against F36 + SPARTA questions.

Tests:
1. F36 + SPARTA entity → should be ANSWERABLE with datalake connection
2. SPARTA-only → should be ANSWERABLE (no datalake needed)
3. Pure F36 context (no entity IDs) → should detect context, may need clarify
4. Nonsense / ambiguous → should be NEEDS_CLARIFICATION
5. Invalid entity IDs → should be INVALID_IDS
6. No coverage entity → should be NO_COVERAGE or ANSWERABLE depending on QRAs
"""
import json
import sys
import time
from pathlib import Path

# Add the skill dir to path
sys.path.insert(0, str(Path(__file__).parent))

from evidence_case import build_evidence_case

# Test cases: (question, expected_classifications, description)
TEST_CASES = [
    # --- Category 1: F36 + SPARTA entity (datalake + controls) ---
    (
        "What countermeasures protect the F-36 avionics from CWE-287?",
        ["ANSWERABLE", "PARTIALLY_ANSWERABLE"],
        "F36 avionics + CWE entity",
    ),
    (
        "How does SV-MA-3 affect the F-36 flight control software?",
        ["ANSWERABLE", "PARTIALLY_ANSWERABLE"],
        "SPARTA technique + F36 flight software",
    ),
    (
        "What SPARTA controls apply to F-36 radar subsystem vulnerabilities related to SV-SP-1?",
        ["ANSWERABLE", "PARTIALLY_ANSWERABLE"],
        "F36 radar + SPARTA spoofing",
    ),

    # --- Category 2: SPARTA-only (no F36/datalake context) ---
    (
        "Describe the countermeasures for SV-SP-1",
        ["ANSWERABLE"],
        "Single SPARTA entity, should have QRAs",
    ),
    (
        "How do SV-MA-3 and CWE-287 relate?",
        ["ANSWERABLE", "PARTIALLY_ANSWERABLE", "DECOMPOSE"],
        "Two SPARTA entities, relationship check",
    ),
    (
        "What is the relationship between T1557 and SV-CF-1?",
        ["ANSWERABLE", "PARTIALLY_ANSWERABLE", "DECOMPOSE"],
        "MITRE ATT&CK + SPARTA technique",
    ),

    # --- Category 3: Pure F36 context (no entity IDs) ---
    (
        "What are the cybersecurity risks to the F-36 dual-engine FADEC system?",
        ["ANSWERABLE", "NEEDS_CLARIFICATION", "NO_COVERAGE"],
        "F36 context but no explicit SPARTA IDs",
    ),
    (
        "How secure is the F-36 supply chain against adversarial tampering?",
        ["ANSWERABLE", "NEEDS_CLARIFICATION", "NO_COVERAGE"],
        "F36 supply chain context",
    ),

    # --- Category 4: Nonsense / ambiguous ---
    (
        "What is the meaning of life?",
        ["NEEDS_CLARIFICATION"],
        "No SPARTA entities, no F36 context",
    ),
    (
        "Tell me about security",
        ["NEEDS_CLARIFICATION"],
        "Too vague, no entities",
    ),

    # --- Category 5: Invalid entity IDs ---
    (
        "What countermeasures protect against SV-FAKE-99?",
        ["INVALID_IDS"],
        "Non-existent SPARTA entity",
    ),

    # --- Category 6: Edge cases ---
    (
        "Compare CM0001 with CM0002 countermeasures",
        ["ANSWERABLE", "PARTIALLY_ANSWERABLE", "DECOMPOSE", "INVALID_IDS"],
        "Two CM entities, may or may not exist",
    ),
    (
        "How do STPA unsafe control actions for dual-engine FADEC map to SPARTA countermeasures?",
        ["NO_COVERAGE", "NEEDS_CLARIFICATION", "ANSWERABLE"],
        "F36 context with technical terminology, no explicit IDs",
    ),
]


def run_stress_test():
    """Run all test cases and report results."""
    results = []
    total_time = 0
    passed = 0
    failed = 0

    print("=" * 80)
    print("EVIDENCE CASE STRESS TEST")
    print("=" * 80)
    print()

    for i, (question, expected, description) in enumerate(TEST_CASES, 1):
        print(f"[{i:2d}/{len(TEST_CASES)}] {description}")
        print(f"     Q: {question[:80]}")

        t0 = time.monotonic()
        try:
            case = build_evidence_case(question, recursive=False)
            elapsed = (time.monotonic() - t0) * 1000
            total_time += elapsed

            classification = case.classification
            match = classification in expected

            status = "PASS" if match else "FAIL"
            if match:
                passed += 1
            else:
                failed += 1

            # Gate summary
            gate_str = " ".join(
                f"G{g.gate}:{'Y' if g.passed else 'N'}" for g in case.gates
            )

            # Datalake info
            dl_str = ""
            if case.datalake_connections:
                cats = [c.category for c in case.datalake_connections]
                shared = []
                for c in case.datalake_connections:
                    shared.extend(c.shared_bridges.keys())
                dl_str = f" | DL: {','.join(cats[:3])}"
                if shared:
                    dl_str += f" bridges={','.join(set(shared))}"

            print(f"     -> {status} | {classification} (expected: {expected})")
            print(f"        Gates: {gate_str} | QRAs: {case.total_qras} | {elapsed:.0f}ms{dl_str}")

            # Show entities if any
            if case.entities:
                ents = [
                    f"{e.entity_id}({'Y' if e.exists else 'N'},{e.qra_count}q)"
                    for e in case.entities[:5]
                ]
                print(f"        Entities: {' '.join(ents)}")

            results.append({
                "question": question[:80],
                "description": description,
                "classification": classification,
                "expected": expected,
                "match": match,
                "total_qras": case.total_qras,
                "gates": [
                    {"gate": g.gate, "passed": g.passed, "time_ms": round(g.time_ms)}
                    for g in case.gates
                ],
                "datalake_connections": len(case.datalake_connections),
                "elapsed_ms": round(elapsed),
            })

        except Exception as exc:
            elapsed = (time.monotonic() - t0) * 1000
            total_time += elapsed
            failed += 1
            print(f"     -> ERROR: {exc}")
            results.append({
                "question": question[:80],
                "description": description,
                "classification": "ERROR",
                "expected": expected,
                "match": False,
                "error": str(exc)[:200],
                "elapsed_ms": round(elapsed),
            })

        print()

    # Summary
    print("=" * 80)
    print(f"RESULTS: {passed}/{len(TEST_CASES)} passed, {failed} failed")
    print(f"Total time: {total_time:.0f}ms ({total_time/1000:.1f}s)")
    print(f"Avg per case: {total_time/len(TEST_CASES):.0f}ms")
    print("=" * 80)

    # Write results JSON
    results_dir = Path(__file__).parent / "results"
    results_dir.mkdir(exist_ok=True)
    results_file = results_dir / f"stress_test_{int(time.time())}.json"
    with open(results_file, "w") as f:
        json.dump({
            "timestamp": time.time(),
            "passed": passed,
            "failed": failed,
            "total": len(TEST_CASES),
            "total_time_ms": round(total_time),
            "results": results,
        }, f, indent=2)
    print(f"\nResults written to: {results_file}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(run_stress_test())
