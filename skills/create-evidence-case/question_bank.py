"""Real persona questions for evidence case integration testing.

Margaret Chen (Pratt & Whitney) — flight software, DO-178C, formal verification.
Jennifer Cheung (NIWC Pacific) — NIST, DISA STIG, supply chain, C4ISR.

Each question has expected answerability so we can validate the system's verdict.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TestQuestion:
    question: str
    persona: str
    difficulty: str  # easy | medium | hard
    expected_answerable: str  # yes | maybe | no
    category_hint: str  # compliance | code | analytics | pipeline | general
    rationale: str


QUESTIONS: list[TestQuestion] = [
    # --- EASY: Single entity, direct SPARTA mapping ---
    TestQuestion(
        question="What SPARTA countermeasures protect the F-36 flight software from firmware tampering during avionics maintenance windows?",
        persona="margaret",
        difficulty="easy",
        expected_answerable="yes",
        category_hint="compliance",
        rationale="Firmware tampering is core SPARTA threat; maintenance windows are F-36 operational baseline. Multiple QRAs exist.",
    ),
    TestQuestion(
        question="What DISA STIG controls should be applied to the F-36's C4ISR systems to defend against SPARTA-identified network exploitation threats?",
        persona="jennifer",
        difficulty="easy",
        expected_answerable="yes",
        category_hint="compliance",
        rationale="C4ISR + DISA STIG + network exploitation = well-covered in SPARTA QRA corpus.",
    ),
    TestQuestion(
        question="Which SPARTA threats are most relevant to the F-36's navigation system GPS receivers?",
        persona="margaret",
        difficulty="easy",
        expected_answerable="yes",
        category_hint="compliance",
        rationale="GPS spoofing, signal degradation = known SPARTA threats with QRAs.",
    ),
    TestQuestion(
        question="How do NIST 800-171 requirements for CUI protection align with SPARTA's recommended defenses for the F-36's embedded computing systems?",
        persona="jennifer",
        difficulty="easy",
        expected_answerable="yes",
        category_hint="compliance",
        rationale="CUI + 800-171 + embedded = standard compliance mapping.",
    ),

    # --- MEDIUM: Cross-domain, multi-hop, constraint balancing ---
    TestQuestion(
        question="How should we apply SPARTA's secure boot recommendations to the F-36's dual FADEC systems while maintaining fault tolerance specified in ARP4754A?",
        persona="margaret",
        difficulty="medium",
        expected_answerable="yes",
        category_hint="compliance",
        rationale="Secure boot + fault tolerance dual-channel = real engineering trade-off. Requires multi-hop traversal.",
    ),
    TestQuestion(
        question="How do NIST 800-53 access controls for the F-36 manufacturing plant floor network align with SPARTA countermeasures for supply chain attacks targeting vendor deliverables?",
        persona="jennifer",
        difficulty="medium",
        expected_answerable="yes",
        category_hint="compliance",
        rationale="Confirmed passing 6/6 gates in validation review. Brandon answered with AC-3, AC-6, SI-7 mappings.",
    ),
    TestQuestion(
        question="How does the F-36's flight software development process, compliant with DO-178C DAL-A, address SPARTA threats related to code injection in the autopilot system?",
        persona="margaret",
        difficulty="medium",
        expected_answerable="yes",
        category_hint="compliance",
        rationale="DO-178C DAL-A + code injection = direct SPARTA technique mapping.",
    ),

    # --- HARD: Multi-hop, legacy coupling, formal methods ---
    TestQuestion(
        question="Given the F-35's legacy vulnerabilities in its mission computer firmware, what SPARTA hardware-based attestation techniques would you recommend for the F-36's upgraded avionics suite to detect compromised components while maintaining DO-178C traceability?",
        persona="margaret",
        difficulty="hard",
        expected_answerable="maybe",
        category_hint="compliance",
        rationale="F-35 cross-reference + attestation + DO-178C traceability = 3-way intersection. May need decomposition.",
    ),
    TestQuestion(
        question="Considering ARP4761 safety assessment, what SPARTA attack techniques pose the highest risk to the F-36's autopilot, and how would you integrate D3FEND countermeasures without compromising MC/DC coverage requirements?",
        persona="margaret",
        difficulty="hard",
        expected_answerable="maybe",
        category_hint="compliance",
        rationale="4-way: ARP4761 + SPARTA attacks + D3FEND + MC/DC. Requires multi-hop graph traversal.",
    ),

    # --- UNANSWERABLE: No coverage, ambiguous, off-topic ---
    # Q10: FPGA + CMMC — entities don't share a technique (INCONCLUSIVE, not SATISFIED)
    TestQuestion(
        question="Given the F-36's use of third-party FPGA vendors, which SPARTA supply chain attack vectors should we prioritize in our CMMC Level 3 compliance audits?",
        persona="jennifer",
        difficulty="medium",
        expected_answerable="inconclusive",
        category_hint="compliance",
        rationale="Supply chain QRAs exist but are SOFTWARE supply chain. FPGA hardware chain is a gap. "
                  "CMMC Level 3 is a process framework with no SPARTA technique mapping. "
                  "Per-component recall shows entities DON'T share a technique. "
                  "/memory clarify explains the gap. Previous false positive now correctly INCONCLUSIVE.",
    ),
    # Q11: Traceability matrix — process question, but QRAs on crypto libs are genuinely relevant
    TestQuestion(
        question="How should we adjust our requirements traceability matrix for third-party cryptographic libraries?",
        persona="margaret",
        difficulty="medium",
        expected_answerable="maybe",
        category_hint="compliance",
        rationale="Process question ('adjust RTM'), but QRAs on CWE-1395 (vulnerable third-party "
                  "components) and T1204.005 (malicious library) provide genuine security context "
                  "for crypto library RTM. 90% Harden coherence. SATISFIED is defensible (QRAs inform "
                  "what to trace), INCONCLUSIVE also acceptable (process details need agent reasoning).",
    ),
    # Q12: Off-topic — no SPARTA content at all (NOT_SATISFIED)
    TestQuestion(
        question="What is your favorite color?",
        persona="jennifer",
        difficulty="easy",
        expected_answerable="no",
        category_hint="general",
        rationale="Off-topic. No SPARTA/F-36 content. Should be rejected at topic check.",
    ),
]
