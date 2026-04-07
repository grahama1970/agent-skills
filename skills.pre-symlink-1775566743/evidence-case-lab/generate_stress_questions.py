#!/usr/bin/env python3
"""Generate ~500 stress test questions from SPARTA corpus in /memory.

Two sources:
  A. Direct cross-control mining — pull QRA samples from /memory, build
     natural questions by pairing controls (no LLM needed, fast)
  B. Persona-driven LLM generation — use scillm to generate F-36 grounded
     questions from persona profiles (margaret, jennifer, brandon, noah, paul, rob)

Output: questions file compatible with run_stress_test.py
Format: [{"id": "...", "question": "...", "expected": "satisfied|not_satisfied"}]
"""
import hashlib
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path
import httpx

random.seed(42)  # reproducible

MEMORY_ROOT = Path(os.environ.get(
    "MEMORY_ROOT", str(Path.home() / "workspace/experiments/memory")
))
SKILLS_DIR = Path(__file__).resolve().parent.parent
# Memory accessed via httpx Unix socket (see _memory_cmd)

STATE_DIR = Path(__file__).resolve().parent / "state"
STATE_DIR.mkdir(parents=True, exist_ok=True)

# Existing questions for regression testing
EXISTING_QUESTIONS = STATE_DIR / "questions_combined.json"


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

def _scillm_generate(prompt: str, timeout=90) -> str:
    """Call scillm for question generation."""
    scillm_dir = Path.home() / ".pi" / "skills" / "scillm"
    if not scillm_dir.exists():
        scillm_dir = SKILLS_DIR / "scillm"

    cmd = [
        "uv", "run", "--directory", str(scillm_dir),
        "python", "batch.py", "single",
        "--json", "--timeout", str(timeout),
    ]
    model = os.environ.get("SCILLM_MODEL") or os.environ.get("SCILLM_DEFAULT_MODEL")
    if model:
        cmd.extend(["--model", model])
    cmd.append(prompt)

    env = dict(os.environ)
    env.pop("VIRTUAL_ENV", None)
    env.pop("CLAUDECODE", None)

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=120,
        cwd=str(scillm_dir), env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(f"scillm failed (rc={result.returncode}): {result.stderr[:300]}")
    return result.stdout.strip()


# ── Source A: Direct cross-control mining from /memory ──────────────────

CROSS_CONTROL_TEMPLATES = [
    "How does {ctrl_a} relate to {ctrl_b} in terms of the F-36's {topic_a}?",
    "What is the relationship between {ctrl_a} and {ctrl_b} for protecting the F-36's spacecraft-derived components?",
    "If an attacker exploits weaknesses covered by {ctrl_a}, how does {ctrl_b} provide defense-in-depth for the F-36?",
    "Compare the defensive approaches of {ctrl_a} and {ctrl_b} for the F-36's avionics security.",
    "How should {ctrl_a} and {ctrl_b} be implemented together to address {topic_a} on the F-36?",
    "What gaps exist between {ctrl_a} and {ctrl_b} regarding {topic_b} for the F-36 program?",
    "Explain how {ctrl_a} addresses {topic_a} and how {ctrl_b} complements it for the F-36.",
    "What attack vectors span both {ctrl_a} and {ctrl_b} in the context of F-36 flight software?",
    "How do countermeasures in {ctrl_a} interact with those in {ctrl_b} for F-36 firmware protection?",
    "What are the cross-domain implications of {ctrl_a} and {ctrl_b} for the F-36's dual-engine FADEC system?",
    "Which SPARTA techniques target both {ctrl_a} and {ctrl_b} in the F-36's avionics bus?",
    "How would you prioritize {ctrl_a} vs {ctrl_b} for the F-36's navigation system protection?",
    "What SPARTA countermeasures bridge {ctrl_a} and {ctrl_b} for the F-36's sensor fusion module?",
    "How do {ctrl_a} and {ctrl_b} work together to protect the F-36 from supply chain attacks?",
    "What verification approach covers both {ctrl_a} and {ctrl_b} for the F-36's DO-178C certification?",
]

SINGLE_CONTROL_TEMPLATES = [
    "What SPARTA countermeasures does {ctrl} provide for the F-36's {subsystem}?",
    "How does {ctrl} protect the F-36's flight control software from {threat}?",
    "Which SPARTA techniques does {ctrl} mitigate in the F-36's avionics architecture?",
    "How should the F-36 implement {ctrl} to protect its {subsystem}?",
    "What threats does {ctrl} address for the F-36's dual-engine control system?",
    "How does {ctrl} relate to DO-178C DAL-A requirements for the F-36?",
    "What NIST 800-53 controls complement {ctrl} for the F-36's cybersecurity posture?",
    "How does {ctrl} protect against firmware corruption in the F-36's {subsystem}?",
    "What D3FEND techniques align with {ctrl} for the F-36's defense-in-depth strategy?",
    "How should {ctrl} be tested during the F-36's HIL simulation?",
]

SUBSYSTEMS = [
    "flight control computer", "navigation system", "GPS/INS fusion module",
    "avionics data bus", "FADEC system", "sensor fusion module",
    "MIL-STD-1553 bus", "ARINC 429 links", "radar warning receiver",
    "electronic warfare suite", "mission computer", "stores management system",
    "C4ISR data fusion module", "helmet-mounted display",
    "engine control unit", "fuel management system",
    "communication system", "IFF transponder",
]

THREATS = [
    "unauthorized firmware updates", "bus spoofing attacks",
    "supply chain tampering", "side-channel attacks",
    "GPS spoofing", "RF interference", "data exfiltration",
    "command injection", "privilege escalation",
    "man-in-the-middle attacks", "denial of service",
]


def generate_cross_control_questions(n: int) -> list[dict]:
    """Generate questions by pairing controls from /memory sample."""
    sample_count = min(n * 3, 500)
    print(f"Sampling {sample_count} QRAs from /memory for cross-control mining...")
    try:
        result = _memory_cmd([
            "sample", "--collection", "sparta_qra", "--limit", str(sample_count),
            "--random", "--fields", "control_id,question,tags",
        ])
        docs = result.get("items", result.get("results", []))
    except Exception as e:
        print(f"  Memory sample failed: {e}")
        return []

    if not docs:
        print("  No QRAs returned from /memory sample")
        return []

    print(f"  Got {len(docs)} QRAs from /memory")
    random.shuffle(docs)

    questions = []

    # Cross-control pairs
    pairs = []
    for i in range(0, len(docs) - 1, 2):
        a, b = docs[i], docs[i + 1]
        a_ctrl = a.get("control_id", a.get("_key", ""))
        b_ctrl = b.get("control_id", b.get("_key", ""))
        if a_ctrl and b_ctrl and a_ctrl != b_ctrl:
            pairs.append((a, b))
        if len(pairs) >= n // 2:
            break

    for a, b in pairs:
        template = random.choice(CROSS_CONTROL_TEMPLATES)
        raw_a = a.get("question", "cybersecurity controls")
        raw_b = b.get("question", "threat mitigation")
        topic_a = raw_a.split("?")[0].split(".")[0][:60].strip()
        topic_b = raw_b.split("?")[0].split(".")[0][:60].strip()
        a_ctrl = a.get("control_id", a.get("_key", "unknown"))
        b_ctrl = b.get("control_id", b.get("_key", "unknown"))

        q_text = template.format(
            ctrl_a=a_ctrl, ctrl_b=b_ctrl,
            topic_a=topic_a, topic_b=topic_b,
        )
        qid = hashlib.sha256(q_text.encode()).hexdigest()[:8]
        questions.append({
            "id": f"XC-{qid}",
            "question": q_text,
            "expected": "satisfied",
            "source": "cross_control",
        })

    # Single-control questions from remaining docs
    used = set()
    for doc in docs:
        if len(questions) >= n:
            break
        ctrl = doc.get("control_id", doc.get("_key", ""))
        if not ctrl or ctrl in used:
            continue
        used.add(ctrl)
        template = random.choice(SINGLE_CONTROL_TEMPLATES)
        subsystem = random.choice(SUBSYSTEMS)
        threat = random.choice(THREATS)
        q_text = template.format(ctrl=ctrl, subsystem=subsystem, threat=threat)
        qid = hashlib.sha256(q_text.encode()).hexdigest()[:8]
        questions.append({
            "id": f"SC-{qid}",
            "question": q_text,
            "expected": "satisfied",
            "source": "single_control",
        })

    print(f"  Generated {len(questions)} cross-control + single-control questions")
    return questions[:n]


# ── Source B: Persona-driven LLM generation ─────────────────────────────

PERSONA_CONFIGS = {
    "margaret": {
        "name": "Margaret Chen",
        "role": "Senior Requirements Engineer",
        "org": "Pratt & Whitney",
        "keywords": "DO-178C, DAL-A, ARP4754A, requirements traceability, MISRA C, MC/DC, formal verification, firmware, avionics, flight software, FADEC, dual-engine",
        "categories": "avionics, dual-engine FADEC, requirements/certification, flight software, test/evaluation, standards",
    },
    "jennifer": {
        "name": "Jennifer Cheung",
        "role": "Cybersecurity Research Scientist",
        "org": "NIWC Pacific",
        "keywords": "NIST 800-53, NIST 800-171, DISA STIG, CMMC, CUI, ITAR, ICS, SCADA, supply chain, vendor, C4ISR, FedRAMP, zero trust, network segmentation",
        "categories": "cybersecurity, microprocessors, space hardening, standards, vendor deliverables",
    },
    "brandon": {
        "name": "Brandon Bailey",
        "role": "Principal Director, Space Cyber",
        "org": "Aerospace Corp",
        "keywords": "SPARTA, ATT&CK, threat actor, kill chain, TTP, space vehicle, satellite, lateral movement, firmware corruption, secure boot, red team, attack surface, exploitation, countermeasure",
        "categories": "avionics, weapons, space hardening, flight software, F-35 legacy",
    },
    "noah": {
        "name": "Noah Evans",
        "role": "Safety Engineer",
        "org": "NASA",
        "keywords": "STPA, DO-178C, DO-254, ARP-4754, ARP4761, assurance case, GSN, hazard, loss scenario, unsafe control action, fault tree, functional hazard, DAL-A, dual-engine, FADEC",
        "categories": "avionics, dual-engine, requirements, flight software, test/evaluation",
    },
    "paul": {
        "name": "Paul Nakamura",
        "role": "Manufacturing Engineer",
        "org": "Lockheed Martin Fort Worth",
        "keywords": "machine test, vendor QA, process control, weld inspection, acceptance test, manufacturing, plant floor, supply chain, CDRL, non-conformance, first article inspection, NDT",
        "categories": "dual-engine, test/evaluation, vendor deliverables, machine test logs, legacy lineage",
    },
    "rob": {
        "name": "Rob Armstrong",
        "role": "Formal Methods Expert",
        "org": "Sandia National Laboratories",
        "keywords": "formal verification, model checking, theorem proving, Lean4, DO-178C, DO-333, DAL-A, proof obligation, invariant, safety property, FIPS 140-3, Common Criteria, seL4",
        "categories": "avionics, requirements, flight software, test/evaluation, standards",
    },
}


def _build_generation_prompt(persona_key: str, count: int) -> str:
    """Build a prompt for generating questions from a persona."""
    p = PERSONA_CONFIGS[persona_key]
    return f"""[SYSTEM]
You are generating questions that {p['name']} ({p['role']}, {p['org']}) would ask about SPARTA threats and countermeasures as they relate to the F-36 fighter program.

Domain expertise: {p['keywords']}
F-36 categories: {p['categories']}

RULES:
1. Every question MUST connect a specific F-36 concern to SPARTA threats or countermeasures
2. Questions sound like a real engineer asking a colleague
3. NEVER mention QRAs, AQL, control IDs, databases, or internal system concepts
4. Reference specific F-36 subsystems (avionics bus, FADEC, navigation system, etc.)
5. Use vocabulary natural to {p['name']}'s role
6. Each question must contain at least one term from their domain expertise
7. Use common SPARTA terms (countermeasures, threat, attack, firmware, exploit, vulnerability)

DIFFICULTY MIX: Generate a mix of easy (direct mapping), medium (cross-domain), and hard (multi-hop reasoning).

Output a JSON array of objects: [{{"question": "...", "difficulty": "easy|medium|hard"}}]

[USER]
Generate {count} questions. Return ONLY a JSON array."""


def generate_persona_questions(n_per_persona: int = 15) -> list[dict]:
    """Generate questions via scillm for each persona."""
    all_questions = []
    personas = list(PERSONA_CONFIGS.keys())

    for persona_key in personas:
        print(f"Generating {n_per_persona} questions for {PERSONA_CONFIGS[persona_key]['name']}...")
        prompt = _build_generation_prompt(persona_key, n_per_persona)

        try:
            raw = _scillm_generate(prompt)
            data = json.loads(raw)

            # Unwrap dict wrappers
            if isinstance(data, dict):
                for key in ("questions", "data", "results", "items"):
                    if key in data:
                        data = data[key]
                        break
                else:
                    if "question" in data:
                        data = [data]
                    elif len(data) == 1:
                        val = list(data.values())[0]
                        if isinstance(val, list):
                            data = val
            if not isinstance(data, list):
                print(f"  Expected list, got {type(data)}")
                continue

            for item in data:
                if not isinstance(item, dict) or not item.get("question"):
                    continue
                q_text = item["question"]
                qid = hashlib.sha256(q_text.encode()).hexdigest()[:8]
                all_questions.append({
                    "id": f"P-{persona_key[:3].upper()}-{qid}",
                    "question": q_text,
                    "expected": "satisfied",
                    "source": f"persona_{persona_key}",
                    "difficulty": item.get("difficulty", "medium"),
                })

            print(f"  Got {len(data)} questions from {persona_key}")
        except Exception as e:
            print(f"  Failed for {persona_key}: {e}")
            continue

        time.sleep(1)  # rate limit courtesy

    print(f"Total persona-generated: {len(all_questions)}")
    return all_questions


# ── Source C: Adversarial questions ─────────────────────────────────────

ADVERSARIAL_QUESTIONS = [
    # Fabricated control IDs
    {"id": "ADV-F01", "question": "How does SPARTA control X23-MUSTARD mitigate spoofing attacks on the F-36's avionics bus?", "expected": "not_satisfied"},
    {"id": "ADV-F02", "question": "What countermeasures does ZZ-PHANTOM-7 in the SPRATA framework protect against for the F-36?", "expected": "not_satisfied"},
    {"id": "ADV-F03", "question": "How does SPARTA control T9999.999 prevent the F-36's coffee maker from being hacked?", "expected": "not_satisfied"},
    {"id": "ADV-F04", "question": "What does control ALFA-BRAVO-99 provide for F-36 radar cross-section management?", "expected": "not_satisfied"},
    {"id": "ADV-F05", "question": "How does countermeasure QQ-UNICORN-42 protect the F-36's stealth coating database?", "expected": "not_satisfied"},
    # Fabricated technology composites
    {"id": "ADV-C01", "question": "Which NIST 800-53 controls protect the F-36's blockchain-based supply chain ledger from ransomware?", "expected": "not_satisfied"},
    {"id": "ADV-C02", "question": "What CMMC Level 7 requirements apply to the F-36's neural interface pilot helmet?", "expected": "not_satisfied"},
    {"id": "ADV-C03", "question": "Compare ESA-T2031 firmware protection with CM0028 tamper resistance for the F-36's underwater sonar array.", "expected": "not_satisfied"},
    {"id": "ADV-C04", "question": "How does the F-36 use Kerberos ticket-granting for its weapon targeting authentication with DO-178C DAL-A verification?", "expected": "not_satisfied"},
    {"id": "ADV-C05", "question": "What SPARTA defenses protect the F-36's Windows XP flight management display from SQL injection via USB?", "expected": "not_satisfied"},
    # Misspelled/near-miss
    {"id": "ADV-M01", "question": "What countermeasures does CM0028 provide for the F-36's quatnum encryption module?", "expected": "not_satisfied"},
    {"id": "ADV-M02", "question": "How does the SPRTA framework address threats to the F-36's hyperloop propulsion system?", "expected": "not_satisfied"},
    # Wrong domain composites
    {"id": "ADV-D01", "question": "How does the F-36 implement GDPR data privacy controls for passenger manifests using SPARTA countermeasures?", "expected": "not_satisfied"},
    {"id": "ADV-D02", "question": "What SPARTA controls protect the F-36's Bitcoin mining ASIC from electromagnetic pulse attacks?", "expected": "not_satisfied"},
    {"id": "ADV-D03", "question": "How should the F-36's TikTok content moderation filter integrate with SPARTA network defenses?", "expected": "not_satisfied"},
    {"id": "ADV-D04", "question": "What SPARTA countermeasures protect the F-36's self-driving autonomous taxi mode from pedestrian detection failures?", "expected": "not_satisfied"},
    {"id": "ADV-D05", "question": "How does SPARTA address agricultural IoT sensor networks on the F-36's crop monitoring pod?", "expected": "not_satisfied"},
    # Plausible-sounding but fabricated subsystems
    {"id": "ADV-P01", "question": "What SPARTA countermeasures protect the F-36's quantum entanglement communication relay from eavesdropping?", "expected": "not_satisfied"},
    {"id": "ADV-P02", "question": "How does the F-36's holographic heads-up display integrate with SPARTA's recommended anti-tamper measures?", "expected": "not_satisfied"},
    {"id": "ADV-P03", "question": "What SPARTA threats target the F-36's DNA-based authentication system for pilot biometric verification?", "expected": "not_satisfied"},
    {"id": "ADV-P04", "question": "How should the F-36's brain-computer interface for weapons release integrate with SPARTA secure boot requirements?", "expected": "not_satisfied"},
    {"id": "ADV-P05", "question": "What SPARTA defenses protect the F-36's matter replicator subsystem from supply chain contamination attacks?", "expected": "not_satisfied"},
    # Mix of real + fabricated (trickiest)
    {"id": "ADV-X01", "question": "How does SPARTA's Firmware Corruption technique affect the F-36's antigravity propulsion control software?", "expected": "not_satisfied"},
    {"id": "ADV-X02", "question": "What DO-178C DAL-A requirements apply to the F-36's perpetual motion energy harvesting subsystem?", "expected": "not_satisfied"},
    {"id": "ADV-X03", "question": "How do NIST 800-53 controls for the F-36's teleportation module align with SPARTA countermeasures?", "expected": "not_satisfied"},
    {"id": "ADV-X04", "question": "What SPARTA supply chain protections apply to the F-36's cold fusion reactor maintenance procedures?", "expected": "not_satisfied"},
    {"id": "ADV-X05", "question": "How should ARP4761 safety assessment cover the F-36's time travel navigation backup system?", "expected": "not_satisfied"},
]


# ── Main orchestrator ───────────────────────────────────────────────────

def main():
    output_file = STATE_DIR / "questions_stress_500.json"

    # Load existing R01-R40 + ADV01-ADV10 for regression
    existing = []
    if EXISTING_QUESTIONS.exists():
        all_existing = json.loads(EXISTING_QUESTIONS.read_text())
        existing = [q for q in all_existing if q["id"].startswith("R") or q["id"].startswith("ADV")]
        print(f"Loaded {len(existing)} existing regression questions (R01-R40 + ADV01-ADV10)")

    # Source A: Cross-control from /memory (~200 questions)
    cross_control = generate_cross_control_questions(200)

    # Source B: Persona-driven LLM generation (~150 questions, 25 per persona)
    persona = generate_persona_questions(n_per_persona=25)

    # Source C: New adversarial questions
    adversarial = ADVERSARIAL_QUESTIONS
    print(f"Added {len(adversarial)} new adversarial questions")

    # Combine all
    all_questions = existing + cross_control + persona + adversarial

    # Deduplicate by question text
    seen = set()
    deduped = []
    for q in all_questions:
        key = q["question"].strip().lower()
        if key not in seen:
            seen.add(key)
            deduped.append(q)

    # Shuffle non-regression questions
    regression = [q for q in deduped if q["id"].startswith("R") or q["id"].startswith("ADV0")]
    new_qs = [q for q in deduped if q not in regression]
    random.shuffle(new_qs)
    final = regression + new_qs

    # Write output
    output_file.write_text(json.dumps(final, indent=2))

    # Stats
    satisfied = sum(1 for q in final if q["expected"] == "satisfied")
    not_satisfied = sum(1 for q in final if q["expected"] == "not_satisfied")
    inconclusive = sum(1 for q in final if q["expected"] == "inconclusive")

    print(f"\n{'='*60}")
    print(f"Generated {len(final)} questions → {output_file}")
    print(f"  Satisfied (real):       {satisfied}")
    print(f"  Not satisfied (adv):    {not_satisfied}")
    print(f"  Inconclusive:           {inconclusive}")
    print(f"  Sources: regression={len(regression)}, cross_control={len(cross_control)}, persona={len(persona)}, adversarial={len(adversarial)}")


if __name__ == "__main__":
    main()
