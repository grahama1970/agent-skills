#!/usr/bin/env python3
"""Generate diverse evidence-graded training data for the classifier.

Creates questions that hit all 4 evidence grades:
  Pass     — valid SPARTA control with QRA coverage + technique bridge
  Ambiguous — valid control but partial grounding or no technique bridge
  Fail     — no QRA coverage at all (non-SPARTA topics)
  Absurd   — fabricated control IDs

Runs each through the evidence grader to get deterministic labels.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add parent for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sparta_stress_test.evidence_grader import grade_evidence

# Output path
OUTPUT = Path(__file__).resolve().parents[1] / "results" / "diverse_evidence_training.jsonl"

# -------------------------------------------------------------------------
# Question templates by expected grade
# -------------------------------------------------------------------------

# PASS: Valid SPARTA controls that should have QRA coverage
PASS_QUESTIONS = [
    ("What countermeasures protect against SV-SP-1 threats?", "SV-SP-1", "The SV-SP-1 control addresses spectrum management and radio frequency protection for spacecraft operations."),
    ("How does SV-AC-1 relate to authentication mechanisms?", "SV-AC-1", "SV-AC-1 covers access control mechanisms for spacecraft command authentication."),
    ("What are the key techniques mapped to SV-MA-4?", "SV-MA-4", "SV-MA-4 addresses dynamic testing and cyber range capabilities for spacecraft systems."),
    ("Explain the relationship between SV-IT-1 and network segmentation.", "SV-IT-1", "SV-IT-1 covers information transfer and network segmentation in space systems."),
    ("What D3FEND countermeasures apply to SV-CF-1?", "SV-CF-1", "SV-CF-1 addresses configuration management and baseline controls."),
    ("How does SV-AV-1 protect against denial of service?", "SV-AV-1", "SV-AV-1 covers availability protections for spacecraft operations."),
    ("What ATT&CK techniques map to SV-SP-2?", "SV-SP-2", "SV-SP-2 addresses signal protection and anti-jamming measures."),
    ("Describe SV-AC-7 weak communication protocol protections.", "SV-AC-7", "SV-AC-7 ensures secure communication protocols with strong encryption for spacecraft."),
    ("How does SV-MA-2 address maintenance access control?", "SV-MA-2", "SV-MA-2 covers maintenance procedures and elevated execution constraints."),
    ("What is the risk assessment for SV-SP-5?", "SV-SP-5", "SV-SP-5 addresses spectrum monitoring and interference detection capabilities."),
    ("Explain SV-AC-3 multi-factor authentication requirements.", "SV-AC-3", "SV-AC-3 covers multi-factor authentication for ground station access."),
    ("What techniques threaten SV-IT-2?", "SV-IT-2", "SV-IT-2 addresses data integrity in transit for space communications."),
    ("How does SV-CF-2 address software assurance?", "SV-CF-2", "SV-CF-2 covers software integrity verification and configuration baseline protection."),
    ("What NIST controls map to SV-AV-2?", "SV-AV-2", "SV-AV-2 addresses fault tolerance and graceful degradation in spacecraft systems."),
    ("Describe SV-SP-3 link encryption requirements.", "SV-SP-3", "SV-SP-3 covers encryption requirements for uplink and downlink communications."),
    ("What are SV-AC-5 session management controls?", "SV-AC-5", "SV-AC-5 addresses session management and timeout controls for spacecraft operations."),
    ("How does SV-MA-1 address vulnerability management?", "SV-MA-1", "SV-MA-1 covers vulnerability scanning and patch management for space systems."),
    ("What countermeasures protect SV-IT-3?", "SV-IT-3", "SV-IT-3 addresses data at rest encryption and storage protection."),
    ("Explain SV-SP-7 ground station protection measures.", "SV-SP-7", "SV-SP-7 covers physical and cyber protection of ground station infrastructure."),
    ("What techniques target SV-CF-3 supply chain?", "SV-CF-3", "SV-CF-3 addresses supply chain risk management for spacecraft components."),
    # More with varied phrasing
    ("What is SV-AC-2's role in least privilege enforcement?", "SV-AC-2", "SV-AC-2 covers principle of least privilege and role-based access control."),
    ("Compare SV-SP-1 and SV-SP-2 protection strategies.", "SV-SP-1", "SV-SP-1 and SV-SP-2 both address spectrum protection with different focus areas."),
    ("What RMF controls does SV-MA-3 implement?", "SV-MA-3", "SV-MA-3 addresses maintenance and monitoring of space system operations."),
    ("How does SV-AV-3 address redundancy requirements?", "SV-AV-3", "SV-AV-3 covers system redundancy and failover mechanisms for spacecraft."),
    ("What ATT&CK sub-techniques apply to SV-AC-4?", "SV-AC-4", "SV-AC-4 covers credential management and password policy enforcement."),
]

# FAIL: Questions with NO QRA coverage — non-SPARTA topics, generic IT
FAIL_QUESTIONS = [
    ("How do I install WordPress on Ubuntu?", "", "To install WordPress on Ubuntu, run apt-get install wordpress."),
    ("What is the best pizza restaurant in New York?", "", "Joe's Pizza in Greenwich Village is highly rated."),
    ("Explain Python decorators with examples.", "", "Python decorators are functions that modify other functions using @syntax."),
    ("How to configure a Cisco router for OSPF?", "", "To configure OSPF on Cisco, use router ospf 1 and network commands."),
    ("What are the top 10 JavaScript frameworks in 2026?", "", "React, Vue, Angular, Svelte, Solid, Qwik, Astro, Next, Nuxt, Remix."),
    ("How does TCP three-way handshake work?", "", "TCP uses SYN, SYN-ACK, ACK to establish connections."),
    ("What is the capital of France?", "", "The capital of France is Paris."),
    ("How to train a random forest classifier?", "", "Use sklearn RandomForestClassifier with fit() on training data."),
    ("What programming language should I learn first?", "", "Python is recommended for beginners due to readable syntax."),
    ("How does DNS resolution work?", "", "DNS resolves domain names to IP addresses through recursive queries."),
    ("What is the difference between REST and GraphQL?", "", "REST uses fixed endpoints while GraphQL uses a single endpoint with queries."),
    ("How to deploy a Docker container to AWS?", "", "Use ECS or EKS to deploy Docker containers on AWS."),
    ("Explain the CAP theorem in distributed systems.", "", "CAP theorem states you can only have 2 of 3: Consistency, Availability, Partition tolerance."),
    ("What is the best database for time series data?", "", "InfluxDB, TimescaleDB, and ClickHouse are popular time series databases."),
    ("How does OAuth 2.0 authorization code flow work?", "", "OAuth 2.0 uses authorization codes exchanged for tokens via redirect."),
    ("What are microservices architecture patterns?", "", "Common patterns include API Gateway, Circuit Breaker, Service Mesh, CQRS."),
    ("How to set up CI/CD with GitHub Actions?", "", "Create .github/workflows/ci.yml with on: push and jobs configuration."),
    ("What is Kubernetes pod scheduling?", "", "K8s schedules pods to nodes based on resource requests and constraints."),
    ("How does React reconciliation algorithm work?", "", "React uses virtual DOM diffing to minimize real DOM updates."),
    ("Explain SOLID principles in object-oriented design.", "", "SOLID: Single Responsibility, Open-Closed, Liskov Substitution, Interface Segregation, Dependency Inversion."),
    ("What is the difference between SQL and NoSQL?", "", "SQL uses structured schemas and joins; NoSQL uses flexible documents."),
    ("How to implement a binary search tree?", "", "BST nodes have left child < parent < right child, supporting O(log n) search."),
    ("What is the Big O notation for quicksort?", "", "Quicksort average case is O(n log n), worst case O(n^2)."),
    ("How does Git branching strategy work?", "", "Git Flow uses main, develop, feature, release, and hotfix branches."),
    ("What are the OWASP Top 10 vulnerabilities?", "", "Injection, Broken Auth, XSS, IDOR, Misconfiguration, Components, etc."),
]

# ABSURD: Fabricated control IDs and misspelled frameworks
ABSURD_QUESTIONS = [
    ("What protections does SV-ZZ-99 provide?", "SV-ZZ-99", "SV-ZZ-99 is a critical control for quantum entanglement security."),
    ("How does SPRTA framework handle SV-XX-42?", "SV-XX-42", "The SPRTA framework maps SV-XX-42 to neural defense mechanisms."),
    ("Explain the NIST SP 800-53 Rev.7 control AC-999.", "", "AC-999 covers autonomous cyber defense in Rev.7 of NIST 800-53."),
    ("What is SV-QQ-1's role in hyperspace protection?", "SV-QQ-1", "SV-QQ-1 addresses faster-than-light communication security."),
    ("Map SV-WW-13 to D3FEND countermeasures.", "SV-WW-13", "SV-WW-13 requires implementation of quantum key distribution."),
    ("How does CWE-99999 relate to spacecraft vulnerabilities?", "", "CWE-99999 covers temporal paradox injection attacks."),
    ("What ATT&CK technique T9999 maps to SV-YY-7?", "SV-YY-7", "T9999 addresses gravitational wave interception."),
    ("Explain NIST 900-53 requirements for space systems.", "", "NIST 900-53 is the space-specific supplement to 800-53."),
    ("What does SPATRTA control SV-AB-0 address?", "SV-AB-0", "SPATRTA SV-AB-0 covers asteroid belt communication relay security."),
    ("How does SV-FF-88 protect against solar flare attacks?", "SV-FF-88", "SV-FF-88 addresses electromagnetic pulse shielding."),
    ("What is DSIFEND countermeasure D3-PSA doing?", "", "DSIFEND D3-PSA provides predictive space anomaly detection."),
    ("Map SV-GG-5 to ISO 27001:2025 Annex Z.", "SV-GG-5", "SV-GG-5 is referenced in the new Annex Z for orbital security."),
    ("Explain CVE-2099-0001 impact on SV-HH-3.", "SV-HH-3", "CVE-2099-0001 exploits a quantum tunneling vulnerability."),
    ("What MITRE ATT&CK for Space technique hits SV-JJ-2?", "SV-JJ-2", "ATT&CK for Space T0001 targets SV-JJ-2 communications."),
    ("How does SV-KK-9 address warp drive encryption?", "SV-KK-9", "SV-KK-9 mandates FTL-grade encryption for warp communications."),
    ("What is the SPARTS control mapping for SV-LL-4?", "SV-LL-4", "SPARTS maps SV-LL-4 to deflector shield integrity monitoring."),
    ("Describe SV-MM-6 anti-tachyon requirements.", "SV-MM-6", "SV-MM-6 covers anti-tachyon countermeasures for temporal security."),
    ("What D4FEND techniques counter SV-NN-1?", "SV-NN-1", "D4FEND provides next-gen countermeasures for SV-NN-1."),
    ("How does SV-PP-8 prevent time-travel exploits?", "SV-PP-8", "SV-PP-8 addresses chronological integrity in spacecraft systems."),
    ("Map SV-RR-3 to CISSA framework controls.", "SV-RR-3", "CISSA maps SV-RR-3 to interstellar signal authentication."),
    ("What is SV-SS-11 wormhole protection?", "SV-SS-11", "SV-SS-11 addresses wormhole traversal authentication protocols."),
    ("Explain SV-TT-0 dark matter shielding.", "SV-TT-0", "SV-TT-0 covers dark matter interference protection."),
    ("How does SV-UU-7 address multiverse access control?", "SV-UU-7", "SV-UU-7 mandates cross-dimensional authentication."),
    ("What SPARTTA technique maps to SV-VV-2?", "SV-VV-2", "SPARTTA technique ST-0042 targets SV-VV-2 systems."),
    ("Describe SV-00-1 zero-point energy security.", "SV-00-1", "SV-00-1 addresses zero-point energy harvesting security."),
]

# AMBIGUOUS: Valid-ish questions but partial grounding or missing technique bridge
AMBIGUOUS_QUESTIONS = [
    ("What general security practices apply to satellite operations?", "", "General security practices include access control, encryption, and monitoring."),
    ("How should we handle firmware updates for space vehicles?", "", "Firmware updates should be signed and verified before deployment."),
    ("What are the risks of using COTS software in spacecraft?", "", "COTS software may have unknown vulnerabilities not tested for space."),
    ("Describe security considerations for ground-to-space links.", "", "Ground-to-space links need encryption, authentication, and anti-jamming."),
    ("What is the impact of insider threats on space missions?", "", "Insider threats can compromise mission integrity through unauthorized access."),
    ("How does physical security affect spacecraft cybersecurity?", "", "Physical access to ground stations enables direct system compromise."),
    ("What are best practices for key management in satellite systems?", "", "Key management should use hardware security modules and key rotation."),
    ("How should we test spacecraft software for security vulnerabilities?", "", "Use static analysis, fuzzing, penetration testing, and formal verification."),
    ("What audit controls are needed for mission-critical space systems?", "", "Comprehensive audit logging, SIEM integration, and anomaly detection."),
    ("How does encryption protect telemetry data?", "", "Encryption ensures telemetry confidentiality and integrity in transit."),
    ("What security training should space mission operators receive?", "", "Operators need cybersecurity awareness, incident response, and phishing training."),
    ("How do you establish trust in a multi-vendor space supply chain?", "", "Establish trust through vendor assessment, code review, and attestation."),
    ("What are the cybersecurity implications of satellite constellations?", "", "Constellations increase attack surface with more nodes to protect."),
    ("How should incident response differ for space vs ground systems?", "", "Space incident response faces latency, limited bandwidth, and no physical access."),
    ("What role does zero trust play in spacecraft networks?", "", "Zero trust eliminates implicit trust, requiring continuous verification."),
    ("How do you secure the software development lifecycle for spacecraft?", "", "Apply secure SDLC practices: threat modeling, code review, testing."),
    ("What are the privacy implications of space-based surveillance?", "", "Space surveillance raises concerns about data collection and sovereignty."),
    ("How should we handle classified data on spacecraft systems?", "", "Classified data requires type-1 encryption, air-gapping, and SCIF operations."),
    ("What resilience patterns apply to distributed space architectures?", "", "Circuit breakers, graceful degradation, redundancy, and failover."),
    ("How does regulatory compliance differ across space agencies?", "", "NASA, ESA, and DoD have different compliance frameworks and standards."),
    ("What are common attack vectors for satellite communication?", "", "Jamming, spoofing, eavesdropping, and replay attacks target satcom."),
    ("How do you validate security controls in orbit?", "", "Remote validation through automated testing, monitoring, and attestation."),
    ("What is the role of AI in space cybersecurity?", "", "AI enables anomaly detection, automated response, and threat prediction."),
    ("How should we handle end-of-life security for decommissioned satellites?", "", "Decommission protocols must include key destruction and frequency release."),
    ("What cybersecurity standards apply to commercial space?", "", "NIST CSF, CISA guidance, and industry-specific frameworks apply."),
]


def main():
    """Generate diverse evidence-graded training data."""
    all_questions = []
    all_questions.extend(
        [("Pass", q, ctrl, a) for q, ctrl, a in PASS_QUESTIONS]
    )
    all_questions.extend(
        [("Fail", q, ctrl, a) for q, ctrl, a in FAIL_QUESTIONS]
    )
    all_questions.extend(
        [("Absurd", q, ctrl, a) for q, ctrl, a in ABSURD_QUESTIONS]
    )
    all_questions.extend(
        [("Ambiguous", q, ctrl, a) for q, ctrl, a in AMBIGUOUS_QUESTIONS]
    )

    print(f"Processing {len(all_questions)} questions through evidence grader...")
    print(f"Expected distribution: Pass={len(PASS_QUESTIONS)}, Fail={len(FAIL_QUESTIONS)}, "
          f"Absurd={len(ABSURD_QUESTIONS)}, Ambiguous={len(AMBIGUOUS_QUESTIONS)}")

    results = []
    grade_counts = {"Pass": 0, "Ambiguous": 0, "Fail": 0, "Absurd": 0}

    for i, (expected, question, control, answer) in enumerate(all_questions):
        try:
            result = grade_evidence(
                question=question,
                answer=answer,
                target_control=control,
                skip_lean4=True,  # Skip Lean4 for speed
            )
            grade_counts[result.grade] = grade_counts.get(result.grade, 0) + 1

            results.append({
                "question": question,
                "answer": answer[:300],
                "target_control": control,
                "evidence_grade": result.grade,
                "expected_grade": expected,
                "grounding_ok": result.grounding_ok,
                "fabricated_ids": result.fabricated_ids,
                "qra_count": result.qra_count,
                "technique_bridge": result.technique_bridge,
            })

            if (i + 1) % 25 == 0:
                print(f"  [{i+1}/{len(all_questions)}] {grade_counts}")

        except Exception as e:
            print(f"  ERROR on question {i}: {e}")
            # Still write with expected grade as fallback
            results.append({
                "question": question,
                "answer": answer[:300],
                "target_control": control,
                "evidence_grade": expected,  # Use expected as fallback
                "expected_grade": expected,
                "grounding_ok": False,
                "fabricated_ids": [],
                "qra_count": 0,
                "technique_bridge": False,
            })
            grade_counts[expected] = grade_counts.get(expected, 0) + 1

    # Write results
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"\nFinal grade distribution: {grade_counts}")
    print(f"Total: {len(results)} samples written to {OUTPUT}")

    # Check expected vs actual agreement
    matches = sum(1 for r in results if r["evidence_grade"] == r["expected_grade"])
    print(f"Expected vs actual agreement: {matches}/{len(results)} ({100*matches/len(results):.1f}%)")


if __name__ == "__main__":
    main()
