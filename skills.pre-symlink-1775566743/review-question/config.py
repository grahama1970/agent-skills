"""Configuration: persona profiles, F36 categories, validation constants."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# F36 Datalake
# ---------------------------------------------------------------------------
F36_DATALAKE_ROOT = Path("/mnt/storage12tb/f36_datalake")

F36_CATEGORIES: dict[str, str] = {
    "01_avionics": "Avionics systems, flight computers, navigation, GPS, INS",
    "02_microprocessors": "Rad-hard processors, FPGAs, SoCs, embedded compute",
    "03_weapons": "Weapons integration, stores management, fire control",
    "04_display_ux": "Cockpit displays, HMI, helmet-mounted displays",
    "05_space_hardening": "Radiation hardening, SEU mitigation, space-grade components",
    "06_dual_engine": "Dual-engine architecture, cross-channel control, FADEC",
    "07_cybersecurity": "ICS/OT security, plant floor, SCADA, network defense",
    "08_requirements": "DO-178C, ARP4754A, requirements traceability, RTM",
    "09_flight_software": "Flight control software, autopilot, sensor fusion",
    "10_test_evaluation": "Test procedures, flight test, HIL/SIL simulation",
    "11_program_management": "Acquisition, milestones, EVM, contracts",
    "12_standards": "MIL-STD, DO-178C, NIST, ISO, DISA STIGs",
    "13_f35_legacy": "F-35 lessons learned, legacy architecture, migration",
    "14_vendor_deliverables": "Vendor artifacts, CDRLs, supply chain inspection",
    "15_machine_test_logs": "Manufacturing test data, acceptance test logs",
    "16_legacy_lineage": "Platform lineage, historical design evolution",
}

# ---------------------------------------------------------------------------
# Persona domain profiles
# ---------------------------------------------------------------------------

@dataclass
class PersonaProfile:
    name: str
    short_name: str  # CLI key: "margaret" or "jennifer"
    role: str
    organization: str
    f36_categories: list[str]
    domain_keywords: list[str]
    example_good: str
    example_bad: str
    bridges: dict[str, float] = field(default_factory=dict)


PERSONAS: dict[str, PersonaProfile] = {
    "margaret": PersonaProfile(
        name="Margaret Chen",
        short_name="margaret",
        role="Senior Requirements Engineer, Verification & Validation",
        organization="Pratt & Whitney",
        f36_categories=[
            "01_avionics", "06_dual_engine", "08_requirements",
            "09_flight_software", "10_test_evaluation", "12_standards",
        ],
        domain_keywords=[
            "DO-178C", "DAL-A", "DAL-B", "ARP4754A", "ARP4761",
            "requirements traceability", "RTM", "MISRA C", "MC/DC",
            "formal verification", "firmware", "avionics", "flight software",
            "safety-critical", "certification", "V&V", "structural coverage",
            "DO-330", "DO-333", "derived requirements", "PSAC", "SDP",
            "dual-engine", "FADEC", "cross-channel", "flight control",
        ],
        example_good=(
            "How do SPARTA countermeasures for GPS spoofing map to DO-178C "
            "DAL-A verification requirements for the F-36 navigation subsystem?"
        ),
        example_bad="What is the description of SV-SP-1?",
        bridges={"Precision": 0.95, "Resilience": 0.90, "Fragility": 0.85},
    ),
    "jennifer": PersonaProfile(
        name="Jennifer Cheung",
        short_name="jennifer",
        role="Cybersecurity Research Scientist",
        organization="NIWC Pacific",
        f36_categories=[
            "07_cybersecurity", "02_microprocessors", "05_space_hardening",
            "12_standards", "14_vendor_deliverables",
        ],
        domain_keywords=[
            "NIST RMF", "NIST 800-53", "NIST 800-171", "DISA STIG",
            "CMMC", "CUI", "ITAR", "ICS", "OT", "SCADA", "supply chain",
            "vendor", "C4ISR", "naval", "FedRAMP", "IL4", "IL5",
            "plant floor", "network segmentation", "zero trust",
            "RMF", "ATO", "POA&M", "CAT I", "CAT II", "MIL-STD-882E",
            "cross-domain", "data guard", "DARPA ARCOS",
        ],
        example_good=(
            "Which SPARTA techniques targeting supply chain integrity apply "
            "to F-36 vendor deliverable inspection, and what NIST 800-53 "
            "controls mitigate them?"
        ),
        example_bad="How many QRAs exist for CM0018?",
        bridges={"Precision": 0.90, "Resilience": 0.90, "Corruption": 0.85},
    ),
    "brandon": PersonaProfile(
        name="Brandon Bailey",
        short_name="brandon",
        role="Principal Director, Space Cyber",
        organization="Aerospace Corp",
        f36_categories=[
            "01_avionics", "03_weapons", "05_space_hardening",
            "09_flight_software", "13_f35_legacy",
        ],
        domain_keywords=[
            "SPARTA", "ATT&CK", "threat actor", "adversary", "kill chain",
            "TTP", "space vehicle", "satellite", "reconnaissance",
            "lateral movement", "command and control", "persistence",
            "firmware corruption", "secure boot", "red team",
            "attack surface", "exploitation", "countermeasure",
            "tactic", "technique", "exfiltration", "impact",
            "inhibit response", "resource development", "initial access",
        ],
        example_good=(
            "What SPARTA attack techniques target the F-36 flight software "
            "update mechanism, and which countermeasures protect the secure "
            "boot chain on the avionics bus?"
        ),
        example_bad="List all SV-SP controls.",
        bridges={"Precision": 0.95, "Corruption": 0.90, "Stealth": 0.85},
    ),
    "noah": PersonaProfile(
        name="Noah Evans",
        short_name="noah",
        role="Safety Engineer",
        organization="NASA",
        f36_categories=[
            "01_avionics", "06_dual_engine", "08_requirements",
            "09_flight_software", "10_test_evaluation",
        ],
        domain_keywords=[
            "STPA", "DO-178C", "DO-254", "ARP-4754", "ARP4761",
            "assurance case", "safety case", "GSN", "hazard",
            "loss scenario", "unsafe control action", "causal factor",
            "control structure", "fault tree", "functional hazard",
            "flight safety", "crew safety", "mishap", "DAL-A",
            "verification", "validation", "test procedure",
            "dual-engine", "FADEC", "cross-channel",
        ],
        example_good=(
            "How do STPA-identified unsafe control actions for the F-36 "
            "dual-engine FADEC map to SPARTA countermeasures that protect "
            "the cross-channel data link from adversarial interference?"
        ),
        example_bad="What is the status of DO-178C?",
        bridges={"Resilience": 0.95, "Fragility": 0.90, "Precision": 0.85},
    ),
    "paul": PersonaProfile(
        name="Paul Nakamura",
        short_name="paul",
        role="Manufacturing Engineer",
        organization="Lockheed Martin Fort Worth",
        f36_categories=[
            "06_dual_engine", "10_test_evaluation", "14_vendor_deliverables",
            "15_machine_test_logs", "16_legacy_lineage",
        ],
        domain_keywords=[
            "machine test", "vendor QA", "process control", "weld inspection",
            "tolerance", "CNC", "alloy batch", "acceptance test",
            "manufacturing", "plant floor", "supply chain",
            "vendor deliverable", "CDRL", "material substitution",
            "non-conformance", "deviation", "calibration",
            "first article inspection", "destructive testing",
            "non-destructive testing", "NDT", "radiographic",
            "heat treatment", "surface finish", "dimensional inspection",
        ],
        example_good=(
            "What SPARTA supply chain attack techniques could compromise "
            "the F-36 vendor alloy batch traceability, and how do "
            "manufacturing acceptance tests detect tampered materials?"
        ),
        example_bad="Show me the CNC machine logs.",
        bridges={"Precision": 0.90, "Resilience": 0.85, "Fragility": 0.80},
    ),
    "rob": PersonaProfile(
        name="Rob Armstrong",
        short_name="rob",
        role="Formal Methods Expert",
        organization="Sandia National Laboratories",
        f36_categories=[
            "01_avionics", "08_requirements", "09_flight_software",
            "10_test_evaluation", "12_standards",
        ],
        domain_keywords=[
            "formal verification", "model checking", "theorem proving",
            "Lean4", "Coq", "Isabelle", "TLA+", "SPIN", "NuSMV",
            "DO-178C", "DO-333", "DAL-A", "formal methods supplement",
            "proof obligation", "refinement", "invariant", "liveness",
            "safety property", "temporal logic", "CTL", "LTL",
            "abstract interpretation", "dependent types", "type theory",
            "FIPS 140-3", "Common Criteria", "EAL", "CC certification",
            "bisimulation", "state machine", "Kripke structure",
            "certified compiler", "CompCert", "seL4", "verified kernel",
        ],
        example_good=(
            "How can Lean4 proof obligations verify that SPARTA countermeasures "
            "for the F-36 avionics bus satisfy DO-178C DAL-A formal methods "
            "supplement (DO-333) requirements for absence of runtime errors?"
        ),
        example_bad="What is formal verification?",
        bridges={"Precision": 0.95, "Resilience": 0.90, "Fragility": 0.85},
    ),
    "embry": PersonaProfile(
        name="Embry",
        short_name="embry",
        role="AI Compliance Assistant",
        organization="Embry OS",
        f36_categories=list(F36_CATEGORIES.keys()),  # all 16 categories
        domain_keywords=[
            "compliance drift", "cross-domain", "multi-persona",
            "legacy lineage", "what would Brandon say",
            "what would Jennifer say", "what would Noah say",
            "cross-program", "F-35 to F-36", "threat landscape",
            "compliance mapping", "safety analysis", "extraction quality",
            "manufacturing provenance", "sensor correlation",
            "multi-generational", "program comparison",
            "risk assessment", "gap analysis", "coverage",
        ],
        example_good=(
            "Where does the F-36 compliance posture drift from the F-35 "
            "legacy baseline, and which personas should review the gaps "
            "in avionics and flight software categories?"
        ),
        example_bad="What is a QRA?",
        bridges={"Precision": 0.85, "Resilience": 0.85, "Loyalty": 0.80},
    ),
}

# ---------------------------------------------------------------------------
# System leakage detection
# ---------------------------------------------------------------------------

SYSTEM_LEAKAGE_TERMS: list[str] = [
    "QRA", "qra", "AQL", "aql", "ArangoDB", "arango",
    "control_id", "control ID", "SV-SP-", "SV-AC-", "SV-CF-",
    "SV-MA-", "SV-IT-", "SV-AV-", "CM0", "EX-0", "REC-0",
    "RecallSource", "recall_source", "graph_memory",
    "setup_schema", "datalake_state", "checkpoint.json",
    "JSONL", "jsonl", "pipe-delimited", "|",
    "sparta_qra", "sparta_controls", "knowledge_chunks",
    "hybrid_search", "BM25", "embedding",
]

# Terms that are OK in context (not leakage)
ALLOWED_TERMS: list[str] = [
    "SPARTA", "NIST", "D3FEND", "ATT&CK", "CWE",
    "countermeasure", "technique", "control",
]

# ---------------------------------------------------------------------------
# Difficulty definitions
# ---------------------------------------------------------------------------

DIFFICULTY_LEVELS: dict[str, str] = {
    "easy": "Single-domain, direct mapping between F36 concern and SPARTA control",
    "medium": "Cross-domain, requires synthesis across two frameworks or F36 categories",
    "hard": "Multi-hop reasoning across F36 datalake + SPARTA + framework mappings",
    "ambiguous": "Deliberately vague or cross-persona, tests classifier edge cases",
}

# ---------------------------------------------------------------------------
# Question distribution per batch
# ---------------------------------------------------------------------------

DEFAULT_BATCH_SIZE = 20  # per persona
DIFFICULTY_DISTRIBUTION = {"easy": 5, "medium": 8, "hard": 5, "ambiguous": 2}

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------

RESULTS_DIR = Path(__file__).parent / "results"
CONVERSATIONS_DIR = RESULTS_DIR / "conversations"
