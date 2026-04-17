#!/usr/bin/env python3
"""Generate 500-question validation batch for /create-evidence-case readiness.

Statistical target: 95% CI with ±4% margin of error overall, ±8% on adversarial.

Split:
  - 300 real questions (stratified by framework, sampled from sparta_qra)
  - 150 adversarial (6 strategies × 25 each, for per-strategy FP measurement)
  - 50 edge cases (typos, ambiguous, cross-domain boundary)

Adversarial strategies (25 each = 150 total):
  F: Fabricated control IDs (X23-MUSTARD, ZZ-PHANTOM-7, etc.)
  C: Fabricated technology composites (blockchain ledger, neural helmet)
  D: Wrong domain (GDPR, Bitcoin, TikTok on an aircraft)
  P: Plausible-sounding fabricated subsystems (quantum comms, holographic HUD)
  X: Mix of real + fabricated (real framework + impossible subsystem)
  N: Naval/maritime (F-36 is Air Force only)

Usage:
    uv run python generate_validation_500.py [--seed 42]
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from pathlib import Path

import typer

app = typer.Typer(no_args_is_help=False)

STATE_DIR = Path(__file__).resolve().parent / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

MEMORY_ROOT = Path(os.environ.get(
    "MEMORY_ROOT", str(Path.home() / "workspace/experiments/memory")
))

# Import templates from existing generator
sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_stress_questions import (
    CROSS_CONTROL_TEMPLATES,
    SINGLE_CONTROL_TEMPLATES,
    SUBSYSTEMS,
    THREATS,
)

# ── Framework normalization ────────────────────────────────────────────
FRAMEWORK_NORMALIZE = {
    "nvd": "NVD", "NVD": "NVD",
    "NIST": "NIST", "nist": "NIST",
    "ATT_CK_Enterprise": "ATT&CK", "ATT_CK_Mobile": "ATT&CK",
    "ATT_CK_ICS": "ATT&CK", "attack": "ATT&CK",
    "CWE": "CWE", "cwe": "CWE",
    "SPARTA": "SPARTA", "sparta": "SPARTA",
    "D3FEND": "D3FEND", "d3fend": "D3FEND",
    "ESA": "ESA",
    "ISO": "ISO", "iso": "ISO",
    "NASA": "NASA",
}

MIN_QUESTIONS_PER_FRAMEWORK = 3
TARGET_REAL = 300


def _get_arango_db():
    sys.path.insert(0, str(MEMORY_ROOT / "src"))
    from graph_memory.arango_client import get_db
    return get_db()


def _query_framework_distribution(db) -> dict[str, int]:
    cursor = db.aql.execute('''
        FOR c IN sparta_controls
          COLLECT fw = c.source_framework WITH COUNT INTO cnt
          RETURN {framework: fw, count: cnt}
    ''')
    raw = {r["framework"]: r["count"] for r in cursor}
    normalized: dict[str, int] = {}
    for raw_fw, count in raw.items():
        norm = FRAMEWORK_NORMALIZE.get(raw_fw)
        if norm:
            normalized[norm] = normalized.get(norm, 0) + count
    return normalized


def _compute_quotas(distribution: dict[str, int], target: int) -> dict[str, int]:
    total = sum(distribution.values())
    quotas = {}
    for fw, count in distribution.items():
        proportion = count / total
        quotas[fw] = max(MIN_QUESTIONS_PER_FRAMEWORK, round(proportion * target))

    # Adjust to hit target
    diff = target - sum(quotas.values())
    sorted_fws = sorted(quotas.keys(), key=lambda f: quotas[f], reverse=True)
    for fw in sorted_fws:
        if diff == 0:
            break
        step = 1 if diff > 0 else -1
        if quotas[fw] + step >= MIN_QUESTIONS_PER_FRAMEWORK:
            quotas[fw] += step
            diff -= step
    return quotas


def _sample_qras(db, framework_raw_names: list[str], limit: int) -> list[dict]:
    cursor = db.aql.execute('''
        LET fw_controls = (
            FOR c IN sparta_controls
              FILTER c.source_framework IN @frameworks
              RETURN c.control_id
        )
        FOR q IN sparta_qra
          FILTER q.control_id IN fw_controls
          SORT RAND()
          LIMIT @limit
          RETURN {control_id: q.control_id, question: q.question}
    ''', bind_vars={"frameworks": framework_raw_names, "limit": limit})
    return list(cursor)


def _get_raw_fw_names(normalized: str) -> list[str]:
    return [raw for raw, norm in FRAMEWORK_NORMALIZE.items() if norm == normalized]


def _qid(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:8]


# ── Real question generation ──────────────────────────────────────────

def generate_real_questions(db, quotas: dict[str, int]) -> list[dict]:
    questions = []
    for fw, quota in sorted(quotas.items(), key=lambda x: -x[1]):
        raw_names = _get_raw_fw_names(fw)
        docs = _sample_qras(db, raw_names, quota * 3)
        if not docs:
            continue

        random.shuffle(docs)
        fw_qs = []

        # Cross-control pairs (60%)
        for i in range(0, len(docs) - 1, 2):
            if len(fw_qs) >= int(quota * 0.6):
                break
            a, b = docs[i], docs[i + 1]
            if a["control_id"] == b["control_id"]:
                continue
            template = random.choice(CROSS_CONTROL_TEMPLATES)
            topic_a = a["question"].split("?")[0][:60].strip()
            topic_b = b["question"].split("?")[0][:60].strip()
            q_text = template.format(
                ctrl_a=a["control_id"], ctrl_b=b["control_id"],
                topic_a=topic_a, topic_b=topic_b,
            )
            fw_qs.append({
                "id": f"V-{fw[:3]}-{_qid(q_text)}",
                "question": q_text,
                "expected": "satisfied",
                "source": "validation_cross_control",
                "framework_stratum": fw,
            })

        # Single-control (remaining 40%)
        used = set()
        for doc in docs:
            if len(fw_qs) >= quota:
                break
            ctrl = doc["control_id"]
            if ctrl in used:
                continue
            used.add(ctrl)
            template = random.choice(SINGLE_CONTROL_TEMPLATES)
            q_text = template.format(
                ctrl=ctrl,
                subsystem=random.choice(SUBSYSTEMS),
                threat=random.choice(THREATS),
            )
            fw_qs.append({
                "id": f"V-{fw[:3]}-{_qid(q_text)}",
                "question": q_text,
                "expected": "satisfied",
                "source": "validation_single_control",
                "framework_stratum": fw,
            })

        print(f"  {fw}: {len(fw_qs)}/{quota}")
        questions.extend(fw_qs[:quota])

    return questions


# ── Adversarial question generation (150 = 6 strategies × 25) ─────────

FAKE_IDS = [
    "X23-MUSTARD", "ZZ-PHANTOM-7", "T9999.999", "ALFA-BRAVO-99",
    "QQ-UNICORN-42", "SV-XX-9999", "CM-FAKE-001", "ESA-Z0000",
    "NVD-0000-99999", "CWE-99999", "D3F-IMAGINARY", "ATT-ZERO",
    "NIST-FICTION-1", "ISO-FAKE-27999", "NASA-VOID-1", "SPARTA-NULL",
    "CV-2099-0001", "RQ-PHANTOM", "EXF-9999.99", "SC-OBLIVION-1",
    "TT-GHOST-42", "MIL-FAKE-1553", "ARINC-999", "DO-999C",
    "FIPS-999-9",
]

FAKE_TECH = [
    "blockchain-based supply chain ledger", "neural interface pilot helmet",
    "quantum encryption module", "holographic targeting system",
    "AI-powered autonomous wingman neural link", "plasma shield generator",
    "nanotube armor self-repair system", "dark matter propulsion controller",
    "biometric DNA authentication scanner", "photonic computing warfare module",
    "zero-point energy harvester", "molecular assembler maintenance bay",
    "gravitational wave communicator", "metamaterial cloaking processor",
    "neuromorphic threat prediction core", "quantum radar entanglement array",
    "tachyon-based FTL navigation", "antimatter containment flight computer",
    "telekinetic pilot assist module", "warp field integrity monitor",
    "consciousness upload backup system", "time dilation compensation unit",
    "parallel universe threat scanner", "singularity containment firmware",
    "psychic threat detection network",
]

WRONG_DOMAIN_COMBOS = [
    ("GDPR data privacy controls", "passenger manifests"),
    ("Bitcoin mining ASIC", "electromagnetic pulse"),
    ("TikTok content moderation filter", "network defenses"),
    ("self-driving autonomous taxi mode", "pedestrian detection"),
    ("agricultural IoT sensor networks", "crop monitoring pod"),
    ("Spotify playlist recommendation engine", "mission planning"),
    ("food delivery drone scheduling", "weapons bay"),
    ("social media sentiment analysis", "threat assessment"),
    ("cryptocurrency wallet", "mission data storage"),
    ("ride-sharing algorithm", "sortie planning"),
    ("smart home thermostat", "cockpit climate control"),
    ("Netflix streaming optimizer", "sensor data pipeline"),
    ("dating app matching algorithm", "target acquisition"),
    ("fitness tracker heart rate monitor", "pilot vitals"),
    ("Uber surge pricing model", "fuel management"),
    ("Amazon product recommendation", "munitions selection"),
    ("weather app notification system", "EW countermeasures"),
    ("restaurant reservation system", "maintenance scheduling"),
    ("gaming leaderboard", "kill chain tracking"),
    ("podcast transcription service", "SIGINT processing"),
    ("email spam filter", "radar signal processing"),
    ("parking meter payment app", "landing gear control"),
    ("pet food subscription service", "logistics resupply"),
    ("virtual reality gaming headset", "helmet-mounted display"),
    ("smartwatch sleep tracker", "pilot fatigue monitoring"),
]

PLAUSIBLE_FAKE_SUBSYSTEMS = [
    "quantum entanglement communication relay",
    "holographic heads-up display",
    "DNA-based authentication system",
    "brain-computer interface for weapons release",
    "matter replicator subsystem",
    "plasma-based electronic warfare system",
    "molecular-level stealth coating self-repair",
    "photonic computing threat processor",
    "zero-gravity fuel management module",
    "neural network flight computer with consciousness",
    "metamaterial radar absorbing skin controller",
    "quantum key distribution satellite link",
    "synthetic aperture sonar for ground mapping",
    "cold fusion auxiliary power unit",
    "gravitational anomaly detector",
    "biomechanical landing gear actuator",
    "dark energy thrust vectoring nozzle",
    "psychoacoustic countermeasure emitter",
    "tachyon-based early warning receiver",
    "antimatter emergency power supply",
    "nanoscale self-healing circuit board",
    "quantum dot infrared search and track",
    "neuromorphic electronic attack processor",
    "bioluminescent formation identification system",
    "chronon-stabilized mission computer clock",
]

REAL_FRAMEWORKS_FOR_MIX = [
    "SPARTA's Firmware Corruption technique",
    "DO-178C DAL-A requirements",
    "NIST 800-53 controls",
    "SPARTA supply chain protections",
    "ARP4761 safety assessment",
    "CMMC Level 2 requirements",
    "CWE-119 buffer overflow mitigations",
    "DISA STIG hardening guidelines",
    "IEC 62443 zone segmentation",
    "FIPS 140-3 cryptographic validation",
    "Common Criteria EAL requirements",
    "MIL-STD-882E hazard analysis",
    "DO-254 hardware assurance",
    "NIST 800-171 CUI protection",
    "ISO 27001 information security controls",
    "ATT&CK lateral movement techniques",
    "D3FEND network isolation countermeasures",
    "SPARTA reconnaissance threat vectors",
    "ESA satellite bus protection standards",
    "NASA procedural requirements for software",
    "DFARS 252.204-7012 compliance",
    "RMF authorization boundary controls",
    "STPA unsafe control action analysis",
    "NIST CSF recovery function requirements",
    "DO-333 formal methods supplement",
]

IMPOSSIBLE_SUBSYSTEMS_FOR_MIX = [
    "antigravity propulsion control software",
    "perpetual motion energy harvesting subsystem",
    "teleportation module",
    "cold fusion reactor maintenance procedures",
    "time travel navigation backup system",
    "warp drive containment firmware",
    "dimensional folding cargo system",
    "faster-than-light communication array",
    "consciousness transfer pilot backup",
    "antimatter warhead arming sequence",
    "gravity manipulation landing system",
    "parallel universe reconnaissance sensor",
    "quantum teleportation escape pod",
    "dark matter fuel injection controller",
    "tachyon-based missile guidance",
    "zero-point energy weapons charging",
    "neutrino-based stealth communication",
    "chronon field generator firmware",
    "singularity-powered ECM suite",
    "hyperspace navigation computer",
    "subspace transponder beacon",
    "inertial dampener control unit",
    "deflector shield harmonics tuner",
    "replicator pattern buffer",
    "transporter beam targeting array",
]

NAVAL_COMBOS = [
    ("naval variant", "carrier-based operations"),
    ("submarine-launched", "torpedo guidance"),
    ("maritime patrol", "anti-submarine warfare"),
    ("carrier operations", "catapult launch system"),
    ("naval aviation", "shipboard maintenance"),
    ("fleet defense", "naval datalake integration"),
    ("amphibious operations", "ship-to-shore data link"),
    ("naval depot", "saltwater corrosion protection"),
    ("frigate deployment", "sonar integration"),
    ("destroyer escort", "naval fire control"),
    ("submarine detection", "passive sonar array"),
    ("coast guard variant", "search and rescue pod"),
    ("aircraft carrier", "steam catapult interface"),
    ("naval weapons station", "depth charge controller"),
    ("littoral combat", "mine countermeasures"),
    ("fleet logistics", "underway replenishment system"),
    ("harbor defense", "port security scanner"),
    ("naval intelligence", "maritime surveillance pod"),
    ("oceanic patrol", "buoy deployment system"),
    ("naval research lab", "underwater drone controller"),
    ("ship self-defense", "close-in weapons system"),
    ("naval electronic warfare", "shipboard EW suite"),
    ("maritime domain awareness", "vessel tracking"),
    ("naval air training", "carrier qualification system"),
    ("submarine communications", "VLF antenna controller"),
]

REAL_CONTROL_IDS_FOR_TEMPLATES = [
    "SV-AC-2", "SV-CF-1", "SV-SP-1", "CM0028", "ESA-T2031",
    "CWE-119", "CWE-787", "T1001", "AC-2", "PE-12",
]


def _generate_adversarial_F(n: int) -> list[dict]:
    """Strategy F: Fabricated control IDs."""
    qs = []
    templates = [
        "How does SPARTA control {fake_id} mitigate {threat} on the F-36's {subsystem}?",
        "What countermeasures does {fake_id} provide for the F-36's {subsystem}?",
        "How should the F-36 implement {fake_id} to protect against {threat}?",
        "What is the relationship between {fake_id} and {real_id} for F-36 security?",
        "How does {fake_id} complement {real_id} for the F-36's {subsystem} protection?",
    ]
    for i in range(n):
        fake_id = FAKE_IDS[i % len(FAKE_IDS)]
        template = templates[i % len(templates)]
        q_text = template.format(
            fake_id=fake_id,
            threat=random.choice(THREATS),
            subsystem=random.choice(SUBSYSTEMS),
            real_id=random.choice(REAL_CONTROL_IDS_FOR_TEMPLATES),
        )
        qs.append({
            "id": f"VA-F{i+1:02d}",
            "question": q_text,
            "expected": "not_satisfied",
            "source": "adversarial_fabricated_id",
            "adversarial_strategy": "F",
        })
    return qs


def _generate_adversarial_C(n: int) -> list[dict]:
    """Strategy C: Fabricated technology composites."""
    qs = []
    templates = [
        "Which NIST 800-53 controls protect the F-36's {fake_tech} from {threat}?",
        "What SPARTA countermeasures address threats to the F-36's {fake_tech}?",
        "How does {real_id} protect the F-36's {fake_tech} from cyber attacks?",
        "What CMMC Level 5 requirements apply to the F-36's {fake_tech}?",
        "How should the F-36's {fake_tech} be hardened per DO-178C DAL-A?",
    ]
    for i in range(n):
        fake_tech = FAKE_TECH[i % len(FAKE_TECH)]
        template = templates[i % len(templates)]
        q_text = template.format(
            fake_tech=fake_tech,
            threat=random.choice(THREATS),
            real_id=random.choice(REAL_CONTROL_IDS_FOR_TEMPLATES),
        )
        qs.append({
            "id": f"VA-C{i+1:02d}",
            "question": q_text,
            "expected": "not_satisfied",
            "source": "adversarial_fabricated_tech",
            "adversarial_strategy": "C",
        })
    return qs


def _generate_adversarial_D(n: int) -> list[dict]:
    """Strategy D: Wrong domain composites."""
    qs = []
    templates = [
        "How does the F-36 implement {domain} for its {combo} using SPARTA countermeasures?",
        "What SPARTA controls protect the F-36's {combo} from cyber threats related to {domain}?",
        "How should {domain} integrate with the F-36's {combo} per NIST 800-53?",
    ]
    for i in range(n):
        domain, combo = WRONG_DOMAIN_COMBOS[i % len(WRONG_DOMAIN_COMBOS)]
        template = templates[i % len(templates)]
        q_text = template.format(domain=domain, combo=combo)
        qs.append({
            "id": f"VA-D{i+1:02d}",
            "question": q_text,
            "expected": "not_satisfied",
            "source": "adversarial_wrong_domain",
            "adversarial_strategy": "D",
        })
    return qs


def _generate_adversarial_P(n: int) -> list[dict]:
    """Strategy P: Plausible-sounding fabricated subsystems."""
    qs = []
    templates = [
        "What SPARTA countermeasures protect the F-36's {fake_sub} from {threat}?",
        "How does the F-36's {fake_sub} integrate with SPARTA's recommended anti-tamper measures?",
        "What SPARTA threats target the F-36's {fake_sub}?",
        "How should the F-36's {fake_sub} be certified under DO-178C DAL-A?",
    ]
    for i in range(n):
        fake_sub = PLAUSIBLE_FAKE_SUBSYSTEMS[i % len(PLAUSIBLE_FAKE_SUBSYSTEMS)]
        template = templates[i % len(templates)]
        q_text = template.format(fake_sub=fake_sub, threat=random.choice(THREATS))
        qs.append({
            "id": f"VA-P{i+1:02d}",
            "question": q_text,
            "expected": "not_satisfied",
            "source": "adversarial_plausible_fake",
            "adversarial_strategy": "P",
        })
    return qs


def _generate_adversarial_X(n: int) -> list[dict]:
    """Strategy X: Mix of real framework + impossible subsystem."""
    qs = []
    templates = [
        "How does {real_fw} affect the F-36's {impossible}?",
        "What {real_fw} apply to the F-36's {impossible}?",
        "How should {real_fw} cover the F-36's {impossible}?",
    ]
    for i in range(n):
        real_fw = REAL_FRAMEWORKS_FOR_MIX[i % len(REAL_FRAMEWORKS_FOR_MIX)]
        impossible = IMPOSSIBLE_SUBSYSTEMS_FOR_MIX[i % len(IMPOSSIBLE_SUBSYSTEMS_FOR_MIX)]
        template = templates[i % len(templates)]
        q_text = template.format(real_fw=real_fw, impossible=impossible)
        qs.append({
            "id": f"VA-X{i+1:02d}",
            "question": q_text,
            "expected": "not_satisfied",
            "source": "adversarial_real_plus_fake",
            "adversarial_strategy": "X",
        })
    return qs


def _generate_adversarial_N(n: int) -> list[dict]:
    """Strategy N: Naval/maritime (F-36 is Air Force only)."""
    qs = []
    templates = [
        "How does the F-36's {naval} affect {combo} in SPARTA threat modeling?",
        "What SPARTA controls apply to the F-36's {naval} for {combo}?",
        "How should {combo} be protected during the F-36's {naval}?",
    ]
    for i in range(n):
        naval, combo = NAVAL_COMBOS[i % len(NAVAL_COMBOS)]
        template = templates[i % len(templates)]
        q_text = template.format(naval=naval, combo=combo)
        qs.append({
            "id": f"VA-N{i+1:02d}",
            "question": q_text,
            "expected": "not_satisfied",
            "source": "adversarial_naval",
            "adversarial_strategy": "N",
        })
    return qs


# ── Edge cases (50) ──────────────────────────────────────────────────

def generate_edge_cases() -> list[dict]:
    """50 edge cases: typos, ambiguous, boundary questions."""
    edges = []

    # Typo variants of real controls (should still be satisfied — fuzzy match)
    typo_controls = [
        ("SV-AC-2", "SV-AC2"),    # missing dash
        ("CM0028", "CM028"),       # missing digit
        ("ESA-T2031", "ESA-T203"), # truncated
        ("CWE-119", "CWE119"),    # missing dash
        ("T1001", "T-1001"),      # extra dash
    ]
    for real, typo in typo_controls:
        q = f"How does {typo} protect the F-36's flight control computer from unauthorized firmware updates?"
        edges.append({
            "id": f"VE-T{len(edges)+1:02d}",
            "question": q,
            "expected": "satisfied",  # fuzzy match should resolve
            "source": "edge_typo",
            "note": f"Typo of {real}",
        })

    # Ambiguous questions (should be satisfied — domain is SPARTA)
    ambiguous = [
        "What are the main threats to the F-36?",
        "How secure is the F-36?",
        "Tell me about F-36 cybersecurity.",
        "What controls apply to the F-36?",
        "How does SPARTA help the F-36?",
        "What vulnerabilities affect the F-36's avionics?",
        "Is the F-36 protected against spoofing?",
        "What countermeasures exist for the F-36?",
        "How is firmware protected on the F-36?",
        "What are the F-36's biggest security risks?",
    ]
    for q in ambiguous:
        edges.append({
            "id": f"VE-A{len(edges)+1:02d}",
            "question": q,
            "expected": "satisfied",
            "source": "edge_ambiguous",
        })

    # Cross-framework boundary (real but unusual combinations — should be satisfied)
    cross_fw = [
        "How does CWE-787 relate to SPARTA countermeasure SV-CF-1 for the F-36's FADEC?",
        "What ATT&CK techniques map to D3FEND countermeasures for the F-36's avionics bus?",
        "How do NIST 800-53 controls complement ESA standards for the F-36's navigation system?",
        "What ISO 27001 requirements overlap with SPARTA controls for the F-36?",
        "How does NASA procedural guidance align with DO-178C for the F-36's flight software?",
    ]
    for q in cross_fw:
        edges.append({
            "id": f"VE-X{len(edges)+1:02d}",
            "question": q,
            "expected": "satisfied",
            "source": "edge_cross_framework",
        })

    # Very long questions (should still work)
    long_qs = [
        "Given the F-36's dual-engine FADEC system uses MIL-STD-1553 data buses for inter-engine communication and the flight control computer relies on ARINC 429 links for sensor fusion, how do SPARTA countermeasures like SV-CF-1 and SV-AC-2 work together to protect against firmware corruption attacks that could simultaneously compromise both engines during critical flight phases?",
        "Considering the F-36's electronic warfare suite must process real-time threat data from multiple sensors including radar warning receivers, missile approach warning systems, and chaff/flare dispensers while maintaining DO-178C DAL-A certified software integrity, what SPARTA techniques could an adversary use to disrupt the sensor fusion pipeline and how do D3FEND countermeasures address these attack vectors?",
    ]
    for q in long_qs:
        edges.append({
            "id": f"VE-L{len(edges)+1:02d}",
            "question": q,
            "expected": "satisfied",
            "source": "edge_long_question",
        })

    # Very short questions (boundary — should be satisfied if domain-relevant)
    short_qs = [
        "SPARTA SV-CF-1?",
        "CWE-119 F-36?",
        "F-36 GPS spoofing countermeasures?",
        "FADEC firmware protection?",
        "MIL-STD-1553 bus security?",
    ]
    for q in short_qs:
        edges.append({
            "id": f"VE-S{len(edges)+1:02d}",
            "question": q,
            "expected": "satisfied",
            "source": "edge_short_question",
        })

    # Non-English but domain-relevant terms
    intl_qs = [
        "What SPARTA countermeasures protect against Angriff auf die F-36 Avionik?",
        "How does the F-36 defend against menaces cybernétiques to its flight computer?",
        "What are the risques de sécurité for the F-36's communication system?",
    ]
    for q in intl_qs:
        edges.append({
            "id": f"VE-I{len(edges)+1:02d}",
            "question": q,
            "expected": "satisfied",
            "source": "edge_international",
        })

    # Completely off-topic (not adversarial, just wrong domain)
    offtopic = [
        "What is the best recipe for chocolate cake?",
        "How do I fix a leaking kitchen faucet?",
        "What are the rules of cricket?",
        "Who won the 2026 World Cup?",
        "How do I train a golden retriever puppy?",
    ]
    for q in offtopic:
        edges.append({
            "id": f"VE-O{len(edges)+1:02d}",
            "question": q,
            "expected": "not_satisfied",
            "source": "edge_offtopic",
        })

    # Fill remaining to 50 with real-but-tricky control references
    while len(edges) < 50:
        q = f"What does control {random.choice(REAL_CONTROL_IDS_FOR_TEMPLATES)} do for the F-36?"
        edges.append({
            "id": f"VE-R{len(edges)+1:02d}",
            "question": q,
            "expected": "satisfied",
            "source": "edge_simple_real",
        })

    return edges[:50]


@app.command()
def generate(
    seed: int = typer.Option(42, help="Random seed for reproducibility"),
    output: str = typer.Option("", help="Output file (default: state/questions_validation_500.json)"),
):
    """Generate 500-question validation batch."""
    random.seed(seed)
    output_path = Path(output) if output else STATE_DIR / "questions_validation_500.json"

    print("=" * 60)
    print("Validation Batch Generator (500 questions)")
    print("Target: 300 real + 150 adversarial + 50 edge cases")
    print("=" * 60)

    # Step 1: Framework distribution
    print("\nStep 1: Querying framework distribution...")
    db = _get_arango_db()
    distribution = _query_framework_distribution(db)
    total_controls = sum(distribution.values())
    print(f"  Total controls: {total_controls}")
    for fw, count in sorted(distribution.items(), key=lambda x: -x[1]):
        print(f"    {fw:12s}: {count:5d} ({count/total_controls*100:.1f}%)")

    # Step 2: Compute quotas for 300 real questions
    print(f"\nStep 2: Computing quotas for {TARGET_REAL} real questions...")
    quotas = _compute_quotas(distribution, TARGET_REAL)
    for fw, quota in sorted(quotas.items(), key=lambda x: -x[1]):
        print(f"    {fw:12s}: {quota:4d}")

    # Step 3: Generate real questions
    print("\nStep 3: Generating real questions...")
    real_qs = generate_real_questions(db, quotas)

    # Step 4: Generate adversarial (6 strategies × 25 = 150)
    print("\nStep 4: Generating 150 adversarial questions (6 strategies × 25)...")
    adv_qs = []
    adv_qs.extend(_generate_adversarial_F(25))
    adv_qs.extend(_generate_adversarial_C(25))
    adv_qs.extend(_generate_adversarial_D(25))
    adv_qs.extend(_generate_adversarial_P(25))
    adv_qs.extend(_generate_adversarial_X(25))
    adv_qs.extend(_generate_adversarial_N(25))
    print(f"  Generated {len(adv_qs)} adversarial questions")

    # Step 5: Edge cases
    print("\nStep 5: Generating 50 edge cases...")
    edge_qs = generate_edge_cases()
    print(f"  Generated {len(edge_qs)} edge cases")

    # Step 6: Combine, deduplicate, shuffle
    all_qs = real_qs + adv_qs + edge_qs
    seen = set()
    deduped = []
    for q in all_qs:
        key = q["question"].strip().lower()
        if key not in seen:
            seen.add(key)
            deduped.append(q)

    random.shuffle(deduped)
    output_path.write_text(json.dumps(deduped, indent=2))

    # Stats
    satisfied = sum(1 for q in deduped if q["expected"] == "satisfied")
    not_satisfied = sum(1 for q in deduped if q["expected"] == "not_satisfied")

    # Per-strategy counts
    strat_counts: dict[str, int] = {}
    for q in deduped:
        s = q.get("adversarial_strategy", q.get("source", "real"))
        strat_counts[s] = strat_counts.get(s, 0) + 1

    print(f"\n{'='*60}")
    print(f"Generated {len(deduped)} questions → {output_path}")
    print(f"  Satisfied (real + edge):  {satisfied}")
    print(f"  Not satisfied (adv):      {not_satisfied}")
    print(f"\n  Adversarial by strategy:")
    for strat in ["F", "C", "D", "P", "X", "N"]:
        count = strat_counts.get(strat, 0)
        print(f"    {strat}: {count}")
    print(f"\n  Edge case sources:")
    for src, count in sorted(strat_counts.items()):
        if src.startswith("edge_"):
            print(f"    {src}: {count}")


if __name__ == "__main__":
    app()
