"""Configuration constants, paths, thresholds, and domain knowledge.

All static configuration for the SPARTA Reality Check skill lives here.
This includes SPARTA domain data, space terminology, annealing schedules,
persona data, fix suggestions, and verification technique definitions.
"""

from pathlib import Path

# =============================================================================
# PATHS AND DIRECTORIES
# =============================================================================

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SPARTA_DIR = _PROJECT_ROOT / "sparta"
MEMORY_DIR = _PROJECT_ROOT / "memory"
SPARTA_EXCEL = SPARTA_DIR / "data/source/SPARTA-Data.xlsx"
SPARTA_WEBSITE = "https://aerospace.org/sparta"
CONVERGENCE_FILE = Path("/tmp/sparta_reality_check_convergence.jsonl")

# =============================================================================
# CLIENT KNOWLEDGE: The Aerospace Corporation SPARTA Framework
# =============================================================================
# Website: https://aerospace.org/sparta
# SPARTA = Space Attack Research & Tactic Analysis
#
# SPARTA provides a taxonomy of space system threats and countermeasures,
# similar to MITRE ATT&CK but focused on space systems.
#
# SPARTA Structure:
# - 216 Techniques: Organized by tactic (e.g., REC=Reconnaissance, EX=Execution)
# - 91 Countermeasures: Security controls mapped to techniques
# - Cross-references: MITRE ATT&CK, NIST 800-53, D3FEND, CWE, etc.
# =============================================================================

SPARTA_TECHNIQUE_CATEGORIES = {
    "REC": "Reconnaissance",
    "RD": "Resource Development",
    "IA": "Initial Access",
    "EX": "Execution",
    "PER": "Persistence",
    "DE": "Defense Evasion",
    "LM": "Lateral Movement",
    "EXF": "Exfiltration",
    "IMP": "Impact",
}

EXPECTED_SPARTA_STRUCTURE = {
    "techniques": 216,
    "countermeasures": 91,
    "technique_columns": [
        "ID", "Name", "Description", "References",
        "Notional Risk Scores (HIGH | MED | LOW)",
        "Aerospace Related Threats", "Related MITRE ATT&CK",
        "Related ESA SPACE-SHIELD", "Countermeasures",
        "NIST Rev5 Controls", "ISO IEC 27001", "D3FEND Techniques",
        "CWE Classes", "Indicators of Behavior", "Related MITRE EMB3D Threats",
    ],
    "countermeasure_columns": [
        "Category", "ID", "Name", "Description", "Sources",
        "NIST Rev5 Controls", "Sample Requirements",
        "ESA Space Shield Mitigation", "ISO IEC 27001",
        "D3FEND Techniques", "Deployment", "Aerospace Space Threats",
        "SPARTA TTPs Mitigated", "NASA's Space Security: Best Practice Guide",
        "Related MTIRE EMB3D Mitigations",
    ],
}

# =============================================================================
# DOMAIN EXPERT KNOWLEDGE: Space-Based Cybersecurity
# =============================================================================

# Space system terminology that should appear in space cybersecurity QRAs
SPACE_TERMINOLOGY = {
    # Space Segments
    "satellite", "spacecraft", "payload", "bus", "orbit", "orbital",
    "LEO", "MEO", "GEO", "HEO", "constellation", "formation flying",
    # Ground Segments
    "ground station", "ground segment", "mission control", "TT&C",
    "telemetry", "tracking", "command", "uplink", "downlink",
    # Link Segments
    "RF", "radio frequency", "SATCOM", "transponder", "antenna",
    "signal", "jamming", "spoofing", "interference", "link budget",
    # Protocols & Standards
    "CCSDS", "SpaceWire", "MIL-STD", "space packet", "telecommand",
    # Threats
    "ASAT", "anti-satellite", "kinetic", "directed energy", "laser",
    "cyber-physical", "supply chain", "insider threat",
    # Countermeasures
    "encryption", "authentication", "anomaly detection", "resilience",
    "redundancy", "hardening", "monitoring", "segmentation",
}

# Expected MITRE ATT&CK tactic alignment for SPARTA categories
EXPECTED_MITRE_ALIGNMENT = {
    "REC": ["TA0043"],  # Reconnaissance
    "RD": ["TA0042"],   # Resource Development
    "IA": ["TA0001"],   # Initial Access
    "EX": ["TA0002"],   # Execution
    "PER": ["TA0003"],  # Persistence
    "DE": ["TA0005"],   # Defense Evasion
    "LM": ["TA0008"],   # Lateral Movement
    "EXF": ["TA0010"],  # Exfiltration
    "IMP": ["TA0040"],  # Impact
}

# Space-specific attack vectors that should be referenced appropriately
SPACE_ATTACK_VECTORS = {
    "REC": ["signal intelligence", "orbit determination", "ground station enumeration",
            "supply chain reconnaissance", "personnel targeting"],
    "IA": ["RF injection", "ground station compromise", "supply chain insertion",
           "insider access", "social engineering"],
    "EX": ["command injection", "malicious telecommand", "firmware exploitation",
           "payload manipulation"],
    "IMP": ["denial of service", "jamming", "spoofing", "data corruption",
            "mission degradation", "collision", "deorbit"],
}

# Suspicious patterns that indicate non-space-specific or hallucinated content
SUSPICIOUS_GENERIC_PATTERNS = [
    "typical network",
    "standard IT",
    "like any other",
    "traditional cyber",
    "normal computer",
    "regular malware",
    "common web",
    "standard phishing",  # Unless contextualized for space personnel
]

# Domain expert questions a real client would ask
EXPERT_QUESTIONS = [
    "Does this QRA specifically address space system characteristics?",
    "Are the MITRE ATT&CK mappings appropriate for space context?",
    "Does the answer reflect understanding of space segment architecture?",
    "Are countermeasures feasible for space systems (SWaP constraints)?",
    "Does this account for space-specific constraints (latency, radiation, etc.)?",
]

# =============================================================================
# BRANDON BAILEY PERSONA: SPARTA Creator & Space Cybersecurity Pioneer
# =============================================================================

BRANDON_BAILEY_PERSONA = {
    "name": "Brandon Bailey",
    "title": "Cybersecurity Researcher, Aerospace Corporation",
    "division": "Cybersecurity and Advanced Platforms Subdivision",
    "expertise": [
        "SPARTA framework architecture",
        "Space-specific TTP taxonomy",
        "Red team/adversarial emulation for space systems",
        "TTP framework integration (SPARTA + MITRE ATT&CK + D3FEND)",
        "Space policy and executive order compliance",
    ],
    "collaborators": ["Paul de Naray", "Joseph Daniel Painter"],
    "publications": [
        "OTR-2025-00018: Recommended Practices for Integrating TTP Frameworks",
        "DEF CON 33: Hacking Space to Defend It",
        "Pioneering Space Cybersecurity (Medium, Jan 2025)",
    ],
    "reputation": {
        "Space Force": "Advisor on space cyber defense posture",
        "NASA": "Collaboration on spacecraft security standards",
        "SpaceX": "Commercial space security framework alignment",
        "DOD": "SPARTA adoption for space domain awareness",
    },
    "reference_systems": [
        "GPS III", "AEHF", "SBIRS", "WGS",  # DOD constellations
        "Starlink", "Dragon", "Falcon 9",    # SpaceX
        "ISS", "Artemis", "Gateway",          # NASA
        "Space Fence", "GSSAP",               # Space domain awareness
    ],
}

# Additional expert: Dr. James Pavur (DEF CON 30 "Space Jam")
DR_JAMES_PAVUR_EXPERTISE = {
    "name": "Dr. James Pavur",
    "talk": "DEF CON 30 - Space Jam: Exploring Radio Frequency Attacks in Outer Space",
    "focus": "RF exploitation, satellite radio link security, SATCOM hacking",
    "key_concepts": [
        "Radio link dependency in all satellite missions",
        "RF signal exploitation techniques",
        "SATCOM protocol vulnerabilities",
        "DVB-S2 weaknesses",
        "Signal jamming and spoofing",
        "Ground station RF security",
    ],
    "questions_he_would_ask": [
        "Does this address the RF link as an attack surface?",
        "Are SATCOM protocol vulnerabilities considered?",
        "What about signal-level attacks (jamming, spoofing)?",
        "Is the ground station RF interface secured?",
    ],
    "red_flags": [
        "Generic IT security language without space context",
        "MITRE ATT&CK mappings that don't make sense for space domain",
        "Missing space segment architecture (ground/link/space)",
        "Countermeasures that ignore SWaP constraints",
        "No mention of RF/SATCOM when relevant",
        "Treating spacecraft like traditional IT assets",
        "Ignoring latency and communication window constraints",
        "Missing cross-references to related frameworks (D3FEND, NIST)",
    ],
    "review_questions": [
        "Does this actually describe a SPACE threat, or just a generic cyber threat?",
        "Would this TTP work against a satellite with 15-minute comm windows?",
        "Is the MITRE mapping sensible? T1059 (scripting) for a spacecraft bus?",
        "Does this countermeasure account for radiation-hardened limitations?",
        "Where's the space segment architecture context?",
        "Is this threat realistic given orbital mechanics constraints?",
        "Would this actually work against a real space system like GPS III?",
        "Does the grounding actually cite SPARTA source material?",
    ],
    "pass_criteria": [
        "QRA explicitly references space-specific characteristics",
        "MITRE mappings are defensible for space context",
        "Countermeasures are feasible within SWaP constraints",
        "Answer demonstrates understanding of space segment architecture",
        "Cross-references are accurate and traceable",
    ],
}

# =============================================================================
# ANNEALING SCHEDULE: Dynamic Thresholds Based on Corpus Size
# =============================================================================

ANNEALING_SCHEDULE = {
    # Phase 0: Bootstrap (0-5K)
    (0, 5000): {
        "anchoring_fail_pct": 50,
        "generic_fail_pct": 80,
        "grounding_min": 0.50,
        "phase_name": "Bootstrap",
        "brandon_says": "Let's see what the pipeline produces before judging too harshly."
    },
    # Phase 1: Early Growth (5K-15K)
    (5000, 15000): {
        "anchoring_fail_pct": 40,
        "generic_fail_pct": 70,
        "grounding_min": 0.55,
        "phase_name": "Early Growth",
        "brandon_says": "The pipeline is maturing. Time to raise the bar a bit."
    },
    # Phase 2: Mid Growth (15K-40K)
    (15000, 40000): {
        "anchoring_fail_pct": 35,
        "generic_fail_pct": 65,
        "grounding_min": 0.60,
        "phase_name": "Mid Growth",
        "brandon_says": "We have enough data to know what good looks like. No more excuses."
    },
    # Phase 3: Late Growth (40K-80K)
    (40000, 80000): {
        "anchoring_fail_pct": 30,
        "generic_fail_pct": 60,
        "grounding_min": 0.65,
        "phase_name": "Late Growth",
        "brandon_says": "Quality matters more than quantity now. Tightening the screws."
    },
    # Phase 4: Refinement (80K-100K)
    (80000, 100000): {
        "anchoring_fail_pct": 25,
        "generic_fail_pct": 55,
        "grounding_min": 0.70,
        "phase_name": "Refinement",
        "brandon_says": "We're approaching production. Time to be strict."
    },
    # Phase 5: Final (100K+)
    (100000, float('inf')): {
        "anchoring_fail_pct": 20,
        "generic_fail_pct": 50,
        "grounding_min": 0.75,
        "phase_name": "Gold Standard",
        "brandon_says": "This is production quality. No compromises."
    },
}

# =============================================================================
# FIX SUGGESTIONS: Remediation guidance for each check type
# =============================================================================

FIX_SUGGESTIONS = {
    "url_file_alignment": {
        "description": "Files downloaded for MITRE ATT&CK URLs contain wrong technique content",
        "root_cause": "Likely redirect handling, hash collision, or race condition in concurrent downloads",
        "fixes": [
            "1. Check download function for proper redirect following",
            "2. Add URL->content validation in download pipeline",
            "3. Re-download mismatched URLs individually",
            "4. Implement checksumming for downloaded files",
        ],
        "severity": "CRITICAL",
        "owner": "fetch/download logic in SPARTA pipeline",
    },
    "verbatim_grounding": {
        "description": "QRA answers contain hallucination patterns (LLM self-references)",
        "root_cause": "LLM generating text about its own capabilities instead of using source material",
        "fixes": [
            "1. Add post-processing filter to reject responses with hallucination phrases",
            "2. Strengthen prompt to require verbatim quotes from source",
            "3. Re-generate affected QRAs with stricter grounding requirements",
        ],
        "severity": "HIGH",
        "owner": "QRA generation prompt engineering",
    },
    "qra_structure": {
        "description": "QRAs have structural issues (orphans, duplicates, empty answers)",
        "root_cause": "Data integrity issues in QRA storage or relationship management",
        "fixes": [
            "1. Verify relationship_id constraint when storing QRAs",
            "2. Add de-duplication check before inserting questions",
            "3. Validate answer content before storing",
            "4. Clean up orphan QRAs that reference deleted relationships",
        ],
        "severity": "HIGH",
        "owner": "QRA storage and relationship management",
    },
    "marginal_analysis": {
        "description": "Marginal QRAs that aren't correct negatives indicate quality issues",
        "root_cause": "Model not extracting properly or source text inadequate",
        "fixes": [
            "1. Review prompt for marginal QRA generation",
            "2. Check if source text actually contains relevant information",
            "3. Consider rejecting QRAs below threshold instead of storing",
            "4. Add self-correction retry for low-scoring QRAs",
        ],
        "severity": "MEDIUM",
        "owner": "QRA generation pipeline",
    },
    "qra_stats": {
        "description": "Too many marginal or poor quality QRAs",
        "root_cause": "Quality issues in generation or inadequate source material",
        "fixes": [
            "1. Review prompt engineering for verbatim grounding",
            "2. Add quality gate before storing (reject if grounding < 0.65)",
            "3. Implement self-correction loop in QRA generation",
        ],
        "severity": "MEDIUM",
        "owner": "QRA generation pipeline",
    },
}

# =============================================================================
# VERIFICATION TECHNIQUES: Methods for fresh verification
# =============================================================================

VERIFICATION_TECHNIQUES = [
    {
        "name": "database_sampling",
        "description": "Random stratified sampling from DuckDB with file inspection",
        "method": "internal",
    },
    {
        "name": "fresh_url_fetch",
        "description": "Re-fetch select URLs live via httpx to compare against cached content",
        "method": "external",
        "command": "fetcher",
    },
    {
        "name": "browser_verification",
        "description": "Headless browser fetch via /surf to handle JavaScript rendering",
        "method": "external",
        "command": "surf",
    },
    {
        "name": "excel_crossref",
        "description": "Cross-reference QRAs against original SPARTA-Data.xlsx",
        "method": "internal",
    },
    {
        "name": "mitre_api_verify",
        "description": "Verify technique metadata against MITRE ATT&CK STIX API",
        "method": "external",
    },
]

# =============================================================================
# PERSONA VALIDATION INDICATORS
# =============================================================================

LAYPERSON_INDICATORS = {
    "good": ["what is", "why is", "how does", "explain", "basic", "simply"],
    "bad": ["CVE-", "CVSS", "exploit chain", "RCE", "buffer overflow", "heap spray"],
    "answer_max_jargon": 3,
}

PROJECT_MANAGER_INDICATORS = {
    "good": ["risk", "impact", "mitigation", "compliance", "budget", "timeline", "stakeholder"],
    "bad": ["assembly", "shellcode", "gadget", "ROP chain", "kernel"],
    "answer_max_jargon": 8,
}

EXPERT_INDICATORS = {
    "good": ["exploit", "vulnerability", "attack vector", "defense in depth", "CVE", "CWE"],
    "bad": [],
    "answer_min_jargon": 3,
}

TECHNICAL_JARGON = [
    "CVE", "CWE", "CVSS", "exploit", "vulnerability", "buffer overflow",
    "injection", "authentication", "authorization", "encryption", "cipher",
    "protocol", "telemetry", "uplink", "downlink", "RF", "SATCOM",
    "firmware", "bootloader", "kernel", "syscall", "memory corruption",
    "TT&C", "CCSDS", "SpaceWire", "ephemeris", "orbital", "constellation",
]

# Tactic keywords for anchoring checks
TACTIC_KEYWORDS = {
    "REC": ["reconnaissance", "gather", "discover", "enumerate", "scan"],
    "IA": ["initial access", "entry", "intrusion", "compromise", "foothold"],
    "EX": ["execution", "execute", "run", "inject", "command"],
    "PER": ["persistence", "persist", "maintain", "backdoor", "implant"],
    "PE": ["privilege", "escalation", "elevate", "root", "admin"],
    "DE": ["evasion", "evade", "hide", "obfuscate", "bypass"],
    "LM": ["lateral", "movement", "pivot", "spread", "propagate"],
    "EXF": ["exfiltration", "exfiltrate", "steal", "extract", "transfer"],
    "IMP": ["impact", "disrupt", "destroy", "deny", "degrade"],
}
