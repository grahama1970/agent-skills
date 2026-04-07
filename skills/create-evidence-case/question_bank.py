"""Evidence case test bank — generates ~160 questions from live data.

Tests three compliance behaviors:
  1. SATISFIED (~80): Real QRA questions from sparta_qra. Pipeline MUST find evidence.
  2. NOT_SATISFIED (~40): Plausible space/security terms NOT in corpus. Pipeline MUST
     reject — no grounding means no answer, not a hallucinated one.
  3. INCONCLUSIVE (~20): Real controls that DON'T share a technique. Pipeline MUST
     say "inconclusive" not fabricate a connection.
  4. OFF_TOPIC (~20): Non-security questions. Pipeline MUST deflect.

Every run pulls fresh data from the daemon. No hardcoded questions.
"""
from __future__ import annotations

import hashlib
import os
import random
from dataclasses import dataclass
from pathlib import Path

import httpx

# Load .env for HF_TOKEN
_env_path = Path(__file__).resolve().parents[3] / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class TestQuestion:
    question: str
    category: str  # satisfied | not_satisfied | inconclusive | off_topic
    framework: str  # SPARTA | NIST | CWE | CAPEC | cross | none
    control_id: str  # real control ID, empty for ungrounded
    expected_verdict: str  # SATISFIED | NOT_SATISFIED | INCONCLUSIVE | DEFLECT
    rationale: str
    source: str = ""  # where this question came from: sparta_qra | generated | recombined


# ---------------------------------------------------------------------------
# Daemon client
# ---------------------------------------------------------------------------

def _client() -> httpx.Client:
    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=30)


# ---------------------------------------------------------------------------
# 1. SATISFIED: Real QRA questions that MUST be answerable
# ---------------------------------------------------------------------------

_RECALL_QUERIES = [
    # SPARTA techniques & countermeasures
    "spacecraft firmware tampering countermeasure",
    "GPS spoofing satellite navigation",
    "ground station authentication SPARTA",
    "telemetry encryption space vehicle",
    "command injection spacecraft bus",
    "RF interference communication link",
    "supply chain hardware trojan satellite",
    "software update integrity verification",
    "key management satellite communication",
    "access control spacecraft telecommand",
    "jamming satellite uplink frequency",
    "malicious code spacecraft payload",
    "side channel attack space processor",
    "replay attack satellite command",
    "denial of service ground segment",
    "data exfiltration spacecraft telemetry",
    "insider threat launch operations",
    "physical tampering satellite hardware",
    "signal intelligence reconnaissance spacecraft",
    "persistence mechanism flight computer",
    "privilege escalation ground control",
    "credential theft mission operations",
    "network scanning space infrastructure",
    "lateral movement ground station network",
    "memory corruption embedded avionics",
    # CWE-specific
    "CWE buffer overflow flight software",
    "CWE improper authentication space system",
    "CWE race condition satellite firmware",
    "CWE integer overflow avionics",
    "CWE cryptographic failure space communication",
    "CWE null pointer dereference spacecraft",
    "CWE use after free embedded system",
    "CWE command injection ground station",
    "CWE path traversal mission planning",
    "CWE improper input validation telemetry",
    "CWE insufficient entropy key generation",
    "CWE hard coded credentials satellite",
    "CWE missing encryption sensitive data",
    "CWE cross site scripting ground portal",
    "CWE SQL injection mission database",
    "CWE deserialization untrusted data spacecraft",
    "CWE improper certificate validation",
    "CWE time of check time of use flight software",
    "CWE uncontrolled resource consumption satellite",
    "CWE improper access control space vehicle",
    # NIST-specific
    "NIST access control space system",
    "NIST incident response satellite",
    "NIST audit logging spacecraft",
    "NIST system integrity space vehicle",
    "NIST configuration management ground station",
    "NIST identification authentication satellite",
    "NIST media protection classified space",
    "NIST personnel security clearance space",
    "NIST physical protection ground facility",
    "NIST risk assessment space mission",
    "NIST security assessment authorization satellite",
    "NIST system communications protection spacecraft",
    "NIST system information integrity space",
    "NIST contingency planning space operations",
    "NIST maintenance satellite ground equipment",
    "NIST program management space cybersecurity",
    # CAPEC-specific
    "CAPEC man in the middle satellite",
    "CAPEC denial of service spacecraft",
    "CAPEC code injection space system",
    "CAPEC eavesdropping space communication",
    "CAPEC brute force authentication space",
    "CAPEC buffer overflow exploitation satellite",
    "CAPEC session hijacking ground station",
    "CAPEC phishing social engineering space program",
    "CAPEC fuzzing protocol spacecraft interface",
    "CAPEC privilege escalation space system",
    "CAPEC cache poisoning ground network",
    "CAPEC cross site request forgery mission portal",
    "CAPEC XML injection space data exchange",
    "CAPEC hardware reverse engineering satellite",
    "CAPEC firmware manipulation space vehicle",
    "CAPEC supply chain compromise space component",
    # Cross-framework
    "ATT&CK technique spacecraft persistence",
    "D3FEND countermeasure satellite defense",
    "MITRE ATT&CK lateral movement space network",
    "SPARTA technique ATT&CK mapping spacecraft",
    "CWE weakness CAPEC attack pattern spacecraft",
]


def _classify_framework(control_id: str) -> str:
    """Classify framework from control_id prefix."""
    if not control_id:
        return "SPARTA"
    if control_id.startswith("CWE"):
        return "CWE"
    if control_id.startswith("CAPEC"):
        return "CAPEC"
    if control_id.startswith("T") and "." in control_id:
        return "ATT&CK"
    # NIST controls like AC-1, SI-7, SC-13
    if "-" in control_id and control_id.split("-")[0].isalpha() and len(control_id.split("-")[0]) <= 3:
        return "NIST"
    return "SPARTA"


def _generate_satisfied(seed: int = 42) -> list[TestQuestion]:
    """Pull real QRA questions from sparta_qra via two strategies:
    1. /recall with diverse queries (gets high-relevance QRAs)
    2. /list with random offsets (gets broad corpus coverage)

    These are questions the pipeline MUST be able to answer.
    """
    questions: list[TestQuestion] = []
    seen = set()
    rng = random.Random(seed)

    with _client() as c:
        # Strategy 1: recall-based (topical diversity)
        for query in _RECALL_QUERIES:
            r = c.post("/recall", json={
                "q": query,
                "collections": ["sparta_qra"],
                "limit": 10,
            })
            items = r.json().get("items", [])
            rng.shuffle(items)

            for item in items[:5]:
                q_text = item.get("question", item.get("problem", ""))
                if not q_text or q_text in seen:
                    continue
                seen.add(q_text)

                cid = item.get("control_id", "")
                questions.append(TestQuestion(
                    question=q_text,
                    category="satisfied",
                    framework=_classify_framework(cid),
                    control_id=cid,
                    expected_verdict="SATISFIED",
                    rationale=f"Real QRA from sparta_qra. control_id={cid}. "
                              f"Pipeline must find this evidence.",
                    source="sparta_qra",
                ))

        # Strategy 2: random offset sampling (corpus breadth)
        # sparta_qra has 218K docs — sample from different regions
        total_r = c.post("/list", json={"collection": "sparta_qra", "limit": 1})
        total = total_r.json().get("total", 200000)
        for i in range(40):
            offset = rng.randint(0, max(1, total - 100))
            r = c.post("/list", json={
                "collection": "sparta_qra",
                "limit": 30,
                "offset": offset,
            })
            docs = r.json().get("documents", [])
            rng.shuffle(docs)
            for doc in docs[:10]:
                q_text = doc.get("question", doc.get("problem", ""))
                if not q_text or q_text in seen:
                    continue
                seen.add(q_text)
                cid = doc.get("control_id", "")
                questions.append(TestQuestion(
                    question=q_text,
                    category="satisfied",
                    framework=_classify_framework(cid),
                    control_id=cid,
                    expected_verdict="SATISFIED",
                    rationale=f"Real QRA from sparta_qra (random sample). control_id={cid}. "
                              f"Pipeline must find this evidence.",
                    source="sparta_qra",
                ))

    rng.shuffle(questions)
    return questions[:750]


# ---------------------------------------------------------------------------
# 2. NOT_SATISFIED: Plausible terms NOT in corpus
# ---------------------------------------------------------------------------

def _generate_not_satisfied(seed: int = 42) -> list[TestQuestion]:
    """Generate questions with plausible space/security terms that don't exist
    in the SPARTA corpus. The pipeline MUST reject these — not hallucinate.

    Strategy: recombine real vocabulary from control names into phrases
    that sound right but aren't indexed anywhere.
    """
    questions: list[TestQuestion] = []

    # Plausible-but-nonexistent space/security compound terms
    # These combine real domain vocabulary into phrases that SOUND right
    # but have zero matches in sparta_qra or sparta_controls
    phantom_terms = [
        "fusion-controlled reaction wheel shielding",
        "quantum-resistant bus arbitration protocol",
        "orbital debris trajectory encryption",
        "magnetospheric plasma authentication layer",
        "cryogenic propellant telemetry hardening",
        "solar sail deployment integrity verification",
        "ion thruster command sanitization",
        "star tracker firmware attestation module",
        "thermal vacuum chamber access provisioning",
        "radiation belt transit key rotation",
        "lunar relay node certificate pinning",
        "deep space network packet deduplication",
        "attitude determination gyroscope tampering",
        "electric propulsion bus isolation protocol",
        "optical crosslink frequency hopping defense",
        "payload fairing jettison command verification",
        "reaction control system nonce generation",
        "space debris collision avoidance authentication",
        "transponder frequency allocation hardening",
        "umbilical disconnect command injection prevention",
        "vibration test stand telemetry spoofing",
        "xenon tank pressure sensor integrity check",
        "zero-gravity fluid dynamics buffer overflow",
        "ablative heat shield firmware rollback",
        "berthing mechanism handshake protocol validation",
        "constellation mesh network session hijacking",
        "de-orbit burn authorization chain",
        "electromagnetic compatibility shielding attestation",
        "flight termination system key escrow",
        "gravity gradient stabilization replay attack",
    ]

    # Include all phantom terms — the pipeline's job is to detect they're not real.
    # No pre-verification. BM25 partial matches don't mean grounding exists.
    for term in phantom_terms:
        questions.append(TestQuestion(
            question=f"What SPARTA countermeasures address {term}?",
            category="not_satisfied",
            framework="none",
            control_id="",
            expected_verdict="NOT_SATISFIED",
            rationale=f"Phantom term '{term}' sounds like real space/security vocabulary "
                      f"but is a recombination of domain words into a nonexistent concept. "
                      f"Entity extraction should classify as not_in_corpus. "
                      f"Pipeline must NOT hallucinate an answer.",
            source="recombined",
        ))

    # Also add questions with fabricated control IDs
    fabricated_ids = [
        ("CWE-99999", "Improper Spacecraft Thermal Management"),
        ("CAPEC-9001", "Quantum Decoherence Exploitation"),
        ("NIST-SP-800-999", "Guidelines for Lunar Network Security"),
        ("SPARTA-EX-9999", "Hypothetical Warp Drive Attack Vector"),
        ("CVE-2099-00001", "Future Vulnerability in Space Protocol"),
        ("CWE-88888", "Gravitational Lensing Side Channel"),
        ("CAPEC-7777", "Dark Matter Signal Injection"),
        ("ATT&CK-T9999", "Fictional Persistence Technique"),
        ("D3FEND-D9999", "Nonexistent Defensive Technique"),
        ("SPARTA-CM-9999", "Phantom Countermeasure"),
    ]

    for fid, fname in fabricated_ids:
        questions.append(TestQuestion(
            question=f"How does {fid} ({fname}) apply to spacecraft cybersecurity?",
            category="not_satisfied",
            framework="fabricated",
            control_id=fid,
            expected_verdict="NOT_SATISFIED",
            rationale=f"Fabricated control ID {fid} does not exist in sparta_controls. "
                      f"Entity extraction must flag as fabricated_id. "
                      f"Pipeline must return NOT_SATISFIED.",
            source="generated",
        ))

    return questions


# ---------------------------------------------------------------------------
# 3. INCONCLUSIVE: Real controls that DON'T share a technique
# ---------------------------------------------------------------------------

def _generate_inconclusive(seed: int = 42) -> list[TestQuestion]:
    """Pair real controls from different frameworks that have NO graph path
    between them. The pipeline should say INCONCLUSIVE, not fabricate a link.

    Strategy: pick controls from unrelated domains (e.g., a web-specific CWE
    and a space-specific SPARTA technique) and verify via /recall that they
    don't co-occur.
    """
    questions: list[TestQuestion] = []
    rng = random.Random(seed)

    # Pairs chosen from unrelated domains — web CWEs vs space SPARTA,
    # physical CAPEC vs network NIST, etc.
    candidate_pairs = [
        # Web-specific CWE + space-specific SPARTA
        ("CWE-79", "Cross-Site Scripting", "CWE",
         "SV-MA-3", "Attitude Determination Error", "SPARTA"),
        ("CWE-89", "SQL Injection", "CWE",
         "SV-CF-2", "Thermal Damage", "SPARTA"),
        ("CWE-352", "Cross-Site Request Forgery", "CWE",
         "EX-0016", "Jamming", "SPARTA"),
        # Physical CAPEC + network NIST
        ("CAPEC-390", "Bypassing Physical Security", "CAPEC",
         "AC-17", "Remote Access", "NIST"),
        ("CAPEC-440", "Hardware Integrity Attack", "CAPEC",
         "SC-13", "Cryptographic Protection", "NIST"),
        # Unrelated SPARTA techniques
        ("REC-0001.04", "Launch Facility", "SPARTA",
         "SV-SP-7", "Software Protection", "SPARTA"),
        # Unrelated CWE categories
        ("CWE-120", "Buffer Copy without Checking Size", "CWE",
         "CWE-613", "Insufficient Session Expiration", "CWE"),
        ("CWE-476", "NULL Pointer Dereference", "CWE",
         "CWE-1021", "Improper Restriction of Rendered UI Layers", "CWE"),
        # CAPEC physical vs CAPEC social
        ("CAPEC-1", "Accessing Functionality Not Properly Constrained", "CAPEC",
         "CAPEC-410", "Information Elicitation", "CAPEC"),
        ("CAPEC-100", "Overflow Buffers", "CAPEC",
         "CAPEC-416", "Manipulate Human Behavior", "CAPEC"),
    ]

    # Verify pairs don't share techniques via /recall
    verified_pairs = []
    with _client() as c:
        for cid1, name1, fw1, cid2, name2, fw2 in candidate_pairs:
            # Search for both together
            r = c.post("/recall", json={
                "q": f"{cid1} {name1} {cid2} {name2}",
                "collections": ["sparta_qra"],
                "limit": 3,
            })
            items = r.json().get("items", [])
            # If recall finds items mentioning BOTH controls, they DO share context
            both_mentioned = any(
                cid1 in str(it) and cid2 in str(it) for it in items
            )
            if not both_mentioned:
                verified_pairs.append((cid1, name1, fw1, cid2, name2, fw2))

    for cid1, name1, fw1, cid2, name2, fw2 in verified_pairs[:20]:
        questions.append(TestQuestion(
            question=f"How does {cid1} ({name1}) in {fw1} relate to "
                     f"{cid2} ({name2}) in {fw2} for spacecraft threat mitigation?",
            category="inconclusive",
            framework="cross",
            control_id=f"{cid1}+{cid2}",
            expected_verdict="INCONCLUSIVE",
            rationale=f"Controls {cid1} ({fw1}) and {cid2} ({fw2}) exist but do NOT "
                      f"share a technique or graph path. Pipeline must return "
                      f"INCONCLUSIVE, not fabricate a connection between them.",
            source="generated",
        ))

    return questions


# ---------------------------------------------------------------------------
# 4. OFF_TOPIC: Non-security questions for deflect path
# ---------------------------------------------------------------------------

def _generate_off_topic(seed: int = 42) -> list[TestQuestion]:
    """Pull real human questions from HuggingFace lmsys-chat-1m dataset.

    Falls back to a large static set if the API is unavailable.
    These are real questions humans asked LLMs — zero security content.
    """
    rng = random.Random(seed)
    questions: list[TestQuestion] = []
    seen = set()

    # Try HuggingFace API first (rows endpoint, no auth needed for public datasets)
    # Pull from public HuggingFace datasets (ultrachat_200k is not gated)
    hf_token = os.environ.get("HF_TOKEN", "")
    hf_headers = {"Authorization": f"Bearer {hf_token}"} if hf_token else {}
    hf_datasets = [
        ("lmsys/lmsys-chat-1m", "default", "train", "conversation", 900000),
        ("HuggingFaceH4/ultrachat_200k", "default", "train_sft", "messages", 180000),
    ]
    for ds_name, config, split, msg_key, max_offset in hf_datasets:
        try:
            for batch in range(3):
                offset = rng.randint(0, max_offset)
                r = httpx.get(
                    "https://datasets-server.huggingface.co/rows",
                    params={"dataset": ds_name, "config": config,
                            "split": split, "offset": offset, "length": 100},
                    headers=hf_headers,
                    timeout=15,
                )
                if r.status_code != 200:
                    break
                rows = r.json().get("rows", [])
                for row in rows:
                    msgs = row.get("row", {}).get(msg_key, [])
                    if not msgs:
                        continue
                    first_msg = msgs[0].get("content", "")
                    if not first_msg or len(first_msg) > 300 or len(first_msg) < 10:
                        continue
                    lower = first_msg.lower()
                    if any(w in lower for w in [
                        "hack", "exploit", "vulnerability", "security",
                        "attack", "malware", "encrypt", "cyber",
                        "password", "firewall", "virus", "phishing",
                        "weapon", "kill", "bomb", "terror",
                    ]):
                        continue
                    if first_msg in seen:
                        continue
                    seen.add(first_msg)
                    questions.append(TestQuestion(
                        question=first_msg,
                        category="off_topic",
                        framework="none",
                        control_id="",
                        expected_verdict="DEFLECT",
                        rationale=f"Real human question from {ds_name}. "
                                  "Zero security/compliance content. Pipeline must deflect.",
                        source="huggingface",
                    ))
        except Exception:
            pass

    # Static fallback / supplement to reach 100 off-topic
    static = [
        "What temperature should I bake sourdough bread at for a crispy crust?",
        "Why are the leaves on my monstera turning yellow?",
        "What is the difference between stability and neutral running shoes?",
        "Should I use whole eggs or just yolks for pasta carbonara?",
        "How often should I change the strings on my acoustic guitar?",
        "What is the fat over lean rule in oil painting?",
        "Is the Sicilian Defense better than the French Defense for beginners?",
        "How often should I change my car's transmission fluid?",
        "What is the best way to stop a puppy from biting?",
        "Why does my wifi signal drop in the bedroom?",
        "What grind size should I use for a French press?",
        "When should I plant tomatoes in zone 7?",
        "What aperture should I use for portrait photography?",
        "Is it better to sleep in a cold or warm room?",
        "Can I wash darks and lights together in cold water?",
        "Why do my chocolate chip cookies come out flat?",
        "How do I fix a squeaky bicycle chain?",
        "What are the best sci-fi movies from the 1980s?",
        "How long does it take to learn piano as an adult?",
        "When is the deadline for filing taxes in the United States?",
        "What is the best time to visit Japan for cherry blossoms?",
        "How do I remove a red wine stain from a white shirt?",
        "What is the difference between a crocodile and an alligator?",
        "How many calories are in a banana?",
        "What causes thunder and lightning?",
        "How do I parallel park a car?",
        "What is the tallest building in the world?",
        "How do I cook a perfect medium-rare steak?",
        "What is the capital of Australia?",
        "How do I tie a Windsor knot?",
        "What is the difference between baking soda and baking powder?",
        "How do I get gum out of hair?",
        "What is a good beginner yoga routine?",
        "How do I unclog a kitchen sink?",
        "What are the rules of cricket?",
        "How do I train for a 5K run?",
        "What is the best way to store avocados?",
        "How do I remove wallpaper?",
        "What is the difference between a latte and a cappuccino?",
        "How do I sharpen kitchen knives at home?",
        "What is the best fertilizer for roses?",
        "How do I calculate my body mass index?",
        "What is the best way to learn a new language?",
        "How do I change a flat tire?",
        "What are the health benefits of green tea?",
        "How do I write a cover letter for a job application?",
        "What is the best way to organize a small closet?",
        "How do I make homemade pasta from scratch?",
        "What is the difference between indica and sativa?",
        "How do I set up a home aquarium?",
    ]

    for q_text in static:
        if q_text not in seen:
            seen.add(q_text)
            questions.append(TestQuestion(
                question=q_text,
                category="off_topic",
                framework="none",
                control_id="",
                expected_verdict="DEFLECT",
                rationale="Off-topic question. Zero security/compliance content. "
                          "Pipeline must deflect at answerability check.",
                source="generated",
            ))

    rng.shuffle(questions)
    return questions[:200]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_bank(seed: int = 42) -> list[TestQuestion]:
    """Generate the full test bank (~1000 questions).

    Returns:
        List of TestQuestion testing four verdict paths:
        - satisfied (~600): real QRAs the pipeline MUST answer
        - not_satisfied (~200): plausible phantom terms + fabricated IDs
        - inconclusive (~50): real controls with no shared technique
        - off_topic (~150): non-security questions for deflect
    """
    satisfied = _generate_satisfied(seed)
    not_satisfied = _generate_not_satisfied(seed)
    inconclusive = _generate_inconclusive(seed)
    off_topic = _generate_off_topic(seed)

    bank = satisfied + not_satisfied + inconclusive + off_topic

    # Tag each with a stable ID
    for q in bank:
        q_hash = hashlib.md5(q.question.encode()).hexdigest()[:8]
        object.__setattr__(q, "_id", f"{q.category}_{q_hash}")

    return bank


def bank_summary(bank: list[TestQuestion]) -> dict:
    """Return category/framework/verdict breakdown."""
    from collections import Counter
    return {
        "total": len(bank),
        "by_category": dict(Counter(q.category for q in bank)),
        "by_framework": dict(Counter(q.framework for q in bank)),
        "by_expected_verdict": dict(Counter(q.expected_verdict for q in bank)),
        "by_source": dict(Counter(q.source for q in bank)),
    }


if __name__ == "__main__":
    import json
    bank = generate_bank()
    summary = bank_summary(bank)
    print(json.dumps(summary, indent=2))
    print("\nSample questions per category:")
    for cat in ["satisfied", "not_satisfied", "inconclusive", "off_topic"]:
        subset = [q for q in bank if q.category == cat]
        print(f"\n--- {cat} ({len(subset)}) ---")
        for q in subset[:3]:
            print(f"  [{q.framework}|{q.expected_verdict}] {q.question[:120]}")
