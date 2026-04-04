#!/usr/bin/env python3
"""Generate 731 new questions to expand the stress test from 269 to 1000.

Categories and counts:
  - 90 adversarial (40 new types + 50 harder variants)
  - 30 inconclusive (borderline questions)
  - 30 cross-framework (3+ frameworks combined)
  - 80 domain-specific (crypto, radar, avionics, firmware, FADEC, nav, supply chain)
  - 50 compliance edge cases
  - 100 general SPARTA (fill control coverage gaps)
  - 351 additional from underrepresented strata

Uses scillm to generate questions via LLM, then validates format.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error

SCILLM_BASE = os.getenv("SCILLM_API_BASE", "http://localhost:4001")
SCILLM_KEY = os.getenv("SCILLM_PROXY_KEY", "sk-dev-proxy-123")

def call_scillm(prompt: str, model: str = "text", max_tokens: int = 4096) -> str:
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }).encode()
    req = urllib.request.Request(
        f"{SCILLM_BASE}/v1/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {SCILLM_KEY}",
        },
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"]


def generate_batch(category: str, expected: str, count: int, prompt_context: str,
                   start_id: int, prefix: str = "S") -> list[dict]:
    """Generate a batch of questions via scillm."""
    prompt = f"""Generate exactly {count} F-36 cybersecurity questions for stress testing a SPARTA Q&A system.

CONTEXT: {prompt_context}

CATEGORY: {category}
EXPECTED VERDICT: {expected}

Each question must be about the F-36 fighter aircraft and SPARTA space vehicle cybersecurity controls.
The SPARTA corpus has 8,979 controls covering threat countermeasures for space vehicles and aircraft.

Return a JSON object with a "questions" array. Each element:
{{"question": "the question text", "notes": "why this expected verdict"}}

RULES:
- Questions must be specific and technical, not generic
- Reference real frameworks: SPARTA, NIST 800-171, CWE, ATT&CK, D3FEND, DO-178C, ARP4754A, CMMC, ISO 27001, MIL-STD-1553
- Reference real SPARTA controls: SV-AC-*, SV-CF-*, SV-MA-*, CM00*, ESA-T*
- Reference real CWEs: CWE-77, CWE-78, CWE-89, CWE-119, CWE-120, CWE-125, CWE-190, CWE-416, CWE-787
- Reference real F-36 subsystems: FADEC, AESA radar, DAS, EOTS, CNI, MFDs, HMD, EW suite
- Do NOT repeat questions from previous batches
- Make questions varied in structure (How/What/Which/Given/Considering)
"""
    import re
    try:
        raw = call_scillm(prompt, max_tokens=max_tokens_for(count))
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
        raw = re.sub(r"```json\s*", "", raw)
        raw = re.sub(r"```\s*", "", raw)
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
        else:
            print(f"  WARN: no JSON found for {category}, raw={raw[:100]}", file=sys.stderr)
            return []
    except Exception as e:
        print(f"  ERR: {category}: {e}", file=sys.stderr)
        return []

    items = data.get("questions", [])
    results = []
    for i, item in enumerate(items[:count]):
        qid = f"{prefix}{start_id + i:03d}"
        results.append({
            "id": qid,
            "question": item["question"],
            "expected": expected,
            "category": category,
            "source": "generated_expansion",
            "framework_stratum": category,
            "notes": item.get("notes", ""),
        })
    return results


def max_tokens_for(count: int) -> int:
    return min(8192, max(2048, count * 120))


def generate_adversarial(start_id: int) -> list[dict]:
    """Generate adversarial questions with various poison types."""
    all_adv = []

    # Type 1: Fabricated control IDs (20)
    fabricated_ids = [
        "XZ-PHANTOM-9", "SV-QQ-77", "CM9999", "ESA-Z0001", "NIST-FAKE-42",
        "CWE-99999", "ATT-FAKE-T9999", "D3-BOGUS-001", "MIL-STD-FAKE-7",
        "SV-XX-123", "CM-ALPHA-7", "ESA-GHOST-3", "SPARTA-ZZZ-1", "CWE-00001",
        "SV-DELTA-99", "CM-OMEGA-5", "ESA-VOID-8", "NIST-NULL-3", "ATT-SHADOW-6",
        "D3-PHANTOM-2",
    ]
    f36_systems = [
        "avionics bus", "FADEC", "AESA radar", "DAS", "EOTS", "CNI suite",
        "flight control computer", "mission computer", "EW suite", "HMD",
        "MIL-STD-1553 bus", "ARINC 429 links", "GPS receiver", "INS",
        "data fusion module", "secure boot", "firmware update", "crypto module",
        "sensor calibration", "weapon systems",
    ]
    attacks = [
        "spoofing", "injection", "tampering", "denial of service", "replay attacks",
        "buffer overflow", "firmware manipulation", "side-channel attacks",
        "man-in-the-middle", "privilege escalation", "code injection",
        "supply chain compromise", "electromagnetic interference", "GPS jamming",
        "radar deception", "data exfiltration", "key compromise",
        "malicious firmware", "bus flooding", "sensor manipulation",
    ]
    for i in range(20):
        fid = fabricated_ids[i]
        sys_ = f36_systems[i % len(f36_systems)]
        atk = attacks[i % len(attacks)]
        q = f"How does {fid} protect the F-36's {sys_} from {atk}?"
        all_adv.append({
            "id": f"ADV{start_id + i:03d}",
            "question": q,
            "expected": "not_satisfied",
            "poison_type": "hallucinated_control",
            "category": "adversarial_fabricated_id",
            "framework_stratum": "adversarial_fabricated_id",
            "rationale": f"{fid} is not a real control ID. No match in 8,979 controls.",
        })

    # Type 2: Wrong-domain technology (20)
    wrong_domain = [
        ("blockchain-based supply chain ledger", "Blockchain is not used in avionics"),
        ("quantum entanglement communication module", "Quantum entanglement comms don't exist in F-36"),
        ("neural interface helmet for pilot cognitive load", "Neural interfaces not in fighter aircraft"),
        ("holographic HUD with gesture recognition", "Holographic HUDs not real in fighters"),
        ("Kerberos authentication for avionics bus", "Kerberos is enterprise IT, not avionics"),
        ("Windows 11 based mission computer", "Windows is not certified flight software"),
        ("SQL injection via USB maintenance port", "Absurd attack vector for avionics"),
        ("OAuth 2.0 token management for sensor fusion", "OAuth is web auth, not avionics"),
        ("Docker containerization of flight control software", "Docker not used in DAL-A systems"),
        ("5G cellular backup for tactical datalinks", "5G not used in fighter comms"),
        ("GraphQL API for radar data streaming", "GraphQL is web tech, not avionics"),
        ("MongoDB for flight recorder data storage", "MongoDB not used in avionics"),
        ("Kubernetes orchestration of EW countermeasures", "Kubernetes not in fighter systems"),
        ("WebSocket protocol for pilot-to-ground comms", "WebSocket is web protocol"),
        ("Redis caching for radar track correlation", "Redis is web infra, not avionics"),
        ("TLS 1.3 for MIL-STD-1553 bus encryption", "MIL-STD-1553 uses different security"),
        ("REST API authentication for weapon release", "REST APIs not used in weapon systems"),
        ("JWT tokens for FADEC command authorization", "JWT is web auth, not engine control"),
        ("Elasticsearch for threat log analysis in cockpit", "Elasticsearch not in fighter avionics"),
        ("gRPC for inter-LRU communication", "gRPC is cloud-native, not avionics protocol"),
    ]
    for i, (tech, reason) in enumerate(wrong_domain):
        q = f"How does the F-36 use {tech} to enhance cybersecurity per SPARTA recommendations?"
        all_adv.append({
            "id": f"ADV{start_id + 20 + i:03d}",
            "question": q,
            "expected": "not_satisfied",
            "poison_type": "wrong_domain_tech",
            "category": "adversarial_wrong_domain",
            "framework_stratum": "adversarial_wrong_domain",
            "rationale": reason,
        })

    # Type 3: Fabricated standards (20)
    fake_standards = [
        ("CMMC Level 5", "CMMC max is Level 3"),
        ("MIL-STD-999X", "Not a real military standard"),
        ("NIST SP 800-999", "Not a real NIST publication"),
        ("DO-178D", "DO-178C is current, no D exists"),
        ("ISO 99999", "Not a real ISO standard"),
        ("DISA STIG v99", "Not a real STIG version"),
        ("ARP4754B", "ARP4754A is current, no B exists"),
        ("RTCA DO-999", "Not a real RTCA document"),
        ("IEC 62443-99", "Not a real IEC 62443 part"),
        ("FIPS 999", "Not a real FIPS publication"),
        ("SAE AS9999", "Not a real SAE standard"),
        ("MIL-HDBK-999", "Not a real military handbook"),
        ("NIST CSF v5.0", "CSF v2.0 is current, no v5"),
        ("DFARS 252.999", "Not a real DFARS clause"),
        ("DO-326B", "DO-326A is current, no B exists"),
        ("MIL-STD-464B", "Not a real MIL-STD version"),
        ("ARINC 999", "Not a real ARINC standard"),
        ("IEEE 802.99", "Not a real IEEE standard"),
        ("STANAG 9999", "Not a real NATO STANAG"),
        ("JPALS Block 99", "Not a real JPALS block"),
    ]
    for i, (std, reason) in enumerate(fake_standards):
        sys_ = f36_systems[i % len(f36_systems)]
        q = f"How do {std} requirements apply to the F-36's {sys_} cybersecurity per SPARTA?"
        all_adv.append({
            "id": f"ADV{start_id + 40 + i:03d}",
            "question": q,
            "expected": "not_satisfied",
            "poison_type": "fabricated_standard",
            "category": "adversarial_fabricated_standard",
            "framework_stratum": "adversarial_fabricated_standard",
            "rationale": reason,
        })

    # Type 4: Composite adversarial — real control + fabricated context (20)
    real_controls = ["SV-AC-2", "SV-CF-1", "CM0028", "CM0041", "ESA-T2031",
                     "SV-MA-2", "SV-CF-3", "CM0015", "ESA-T2016", "SV-AC-1"]
    fake_contexts = [
        "quantum computing attack on", "alien signal interference with",
        "time-travel paradox affecting", "teleportation vulnerability in",
        "dark matter interference on", "warp drive compatibility with",
        "anti-gravity field effects on", "tachyon beam disruption of",
        "interdimensional breach via", "parallel universe data leak from",
        "zero-point energy override of", "fusion reactor feedback to",
        "plasma shield bypass of", "graviton wave attack on",
        "neutrino-based data exfiltration from", "antimatter containment breach in",
        "subspace communication hijack of", "chrono-shift exploitation of",
        "dark energy manipulation of", "quantum tunneling bypass of",
    ]
    for i in range(20):
        ctrl = real_controls[i % len(real_controls)]
        ctx = fake_contexts[i]
        sys_ = f36_systems[i % len(f36_systems)]
        q = f"How does {ctrl} address {ctx} the F-36's {sys_}?"
        all_adv.append({
            "id": f"ADV{start_id + 60 + i:03d}",
            "question": q,
            "expected": "not_satisfied",
            "poison_type": "composite_real_control_fake_context",
            "category": "adversarial_composite",
            "framework_stratum": "adversarial_composite",
            "rationale": f"{ctrl} is real but '{ctx.strip()}' is science fiction, not cybersecurity.",
        })

    # Type 5: Naval/maritime (10) — F-36 is Air Force only
    naval_questions = [
        "How do SPARTA countermeasures apply to the F-36's naval deployment on aircraft carriers?",
        "What submarine communications protocols does the F-36 naval variant use per SPARTA?",
        "How should SPARTA defenses be adapted for the F-36's carrier operations environment?",
        "What maritime radar integration does the F-36 naval aviation variant require?",
        "How do SPARTA controls address the F-36's submarine-launched variant cybersecurity?",
        "What carrier operations cybersecurity requirements apply to the F-36 per SPARTA?",
        "How does the F-36 naval variant handle maritime communication security per SPARTA?",
        "What SPARTA countermeasures protect the F-36's shipboard maintenance systems?",
        "How do naval deployment conditions affect SPARTA control implementation on the F-36?",
        "What maritime environmental threats should the F-36 naval variant address per SPARTA?",
    ]
    for i, q in enumerate(naval_questions):
        all_adv.append({
            "id": f"ADV{start_id + 80 + i:03d}",
            "question": q,
            "expected": "not_satisfied",
            "poison_type": "naval_off_topic",
            "category": "adversarial_naval",
            "framework_stratum": "adversarial_naval",
            "rationale": "F-36 is Air Force only. Naval/maritime deployment is off-topic.",
        })

    return all_adv


def generate_inconclusive(start_id: int) -> list[dict]:
    """Generate borderline questions that should be inconclusive."""
    questions = [
        ("How effective are SPARTA countermeasures when applied to classified F-36 systems that cannot be fully documented?", "Inherently unanswerable — classified systems can't be validated"),
        ("What is the exact probability of a successful cyber attack on the F-36's FADEC through SPARTA-identified vectors?", "Exact probability requires classified threat intel not in SPARTA corpus"),
        ("How would SPARTA recommendations change if the F-36 incorporated AI-driven autonomous flight?", "Hypothetical future capability, speculative"),
        ("What SPARTA controls would apply to the F-36 if it operated in a post-quantum computing environment?", "Speculative future scenario"),
        ("How do SPARTA recommendations account for insider threats from F-36 maintenance personnel with nation-state backing?", "Extremely specific threat model not directly in corpus"),
        ("What is the cost-benefit ratio of implementing all SPARTA countermeasures on the F-36?", "Cost data not in SPARTA corpus"),
        ("How would SPARTA controls need to be modified for the F-36's successor aircraft program?", "Future aircraft not in scope"),
        ("What SPARTA defenses apply to the F-36's classified electronic attack capabilities?", "Classified capabilities can't be publicly assessed"),
        ("How do SPARTA countermeasures compare to those recommended by allied nations for similar aircraft?", "Allied nation controls not in SPARTA corpus"),
        ("What is the mean time to compromise for the F-36's avionics if SPARTA controls are not implemented?", "Quantitative attack metrics not in corpus"),
        ("How should SPARTA controls be prioritized given unknown zero-day vulnerabilities in F-36 COTS components?", "Unknown zero-days are by definition not in corpus"),
        ("What SPARTA recommendations address the F-36's vulnerability to attacks using currently classified techniques?", "Classified attack techniques not publicly documented"),
        ("How do SPARTA controls account for the F-36's electromagnetic compatibility with coalition aircraft?", "EMC with coalition aircraft is integration-specific, not directly in SPARTA"),
        ("What is the residual risk of the F-36 after implementing all SPARTA-recommended countermeasures?", "Residual risk calculation needs classified threat data"),
        ("How should SPARTA countermeasures adapt to the F-36's evolving threat landscape in 2035?", "Future threat prediction out of scope"),
        ("What SPARTA controls address social engineering attacks targeting F-36 program personnel?", "Social engineering of personnel is organizational, not technical"),
        ("How do SPARTA recommendations account for the F-36's cognitive electronic warfare capabilities?", "Cognitive EW is emerging tech, may not be fully covered"),
        ("What SPARTA defenses protect against attacks from space-based weapons targeting the F-36?", "Space-based weapon attacks on aircraft are speculative"),
        ("How should SPARTA controls be modified for F-36 operations in a GPS-denied, comms-jammed environment simultaneously?", "Extreme combined scenario may exceed corpus coverage"),
        ("What SPARTA countermeasures address the F-36's vulnerability to deepfake-generated tactical data?", "Deepfake tactical data is emerging threat, limited coverage"),
        ("How do SPARTA controls account for supply chain attacks that occur after F-36 delivery to operational units?", "Post-delivery supply chain is operational, may have limited coverage"),
        ("What is the F-36's cyber resilience score using SPARTA metrics alone?", "No standardized cyber resilience score in SPARTA"),
        ("How should SPARTA recommendations be weighted against competing compliance frameworks for the F-36?", "Framework weighting is policy, not technical"),
        ("What SPARTA controls address attacks exploiting the F-36's maintenance diagnostic port during combat?", "Combat maintenance scenario is edge case"),
        ("How do SPARTA countermeasures protect the F-36 from attacks using commercially available SDR equipment?", "SDR attacks are partially covered but specific equipment varies"),
        ("What SPARTA defenses apply to the F-36's use of machine learning for predictive maintenance?", "ML for maintenance is emerging, limited SPARTA coverage"),
        ("How should SPARTA controls be implemented on the F-36 given budget constraints of 60% of recommended levels?", "Budget-constrained implementation is policy, not technical"),
        ("What SPARTA countermeasures address the F-36's vulnerability to attacks on its digital twin simulation?", "Digital twin attacks are IT-domain, may not map to SPARTA"),
        ("How do SPARTA recommendations account for the F-36's interoperability with legacy 4th-gen fighters?", "Legacy interop is integration-specific, may have limited coverage"),
        ("What SPARTA controls would apply if the F-36 were exported to a nation without CMMC certification?", "Export scenarios are policy-dependent, not directly in SPARTA"),
    ]
    results = []
    for i, (q, notes) in enumerate(questions):
        results.append({
            "id": f"S{start_id + i:03d}",
            "question": q,
            "expected": "inconclusive",
            "category": "borderline_inconclusive",
            "source": "generated_expansion",
            "framework_stratum": "borderline_inconclusive",
            "notes": notes,
        })
    return results


def main():
    existing = json.load(open("/home/graham/.claude/skills/evidence-case-lab/state/questions_combined.json"))
    print(f"Existing questions: {len(existing)}", file=sys.stderr)

    all_new = []
    next_s_id = 220  # S001-S219 exist
    next_adv_id = 11  # ADV01-ADV10 exist

    # 1. Adversarial questions (90 total, handcrafted)
    print("Generating 90 adversarial questions...", file=sys.stderr)
    adv = generate_adversarial(next_adv_id)
    all_new.extend(adv)
    print(f"  Generated {len(adv)} adversarial", file=sys.stderr)

    # 2. Inconclusive questions (30, handcrafted)
    print("Generating 30 inconclusive questions...", file=sys.stderr)
    inc = generate_inconclusive(next_s_id)
    all_new.extend(inc)
    next_s_id += len(inc)
    print(f"  Generated {len(inc)} inconclusive", file=sys.stderr)

    # 3. LLM-generated domain-specific questions
    domain_batches = [
        ("crypto_comms", "satisfied", 25,
         "Questions about F-36 cryptographic systems, key management, NSA Type 1 crypto, Link 16 encryption, COMSEC, secure voice, datalink security. Reference real controls and CWEs."),
        ("avionics_bus_deep", "satisfied", 20,
         "Questions about F-36 MIL-STD-1553, ARINC 429, bus guardian, time-division bus access, avionics LRU authentication, bus monitoring, message authentication codes on avionics buses."),
        ("radar_ew_deep", "satisfied", 20,
         "Questions about F-36 AESA radar cybersecurity, electronic warfare suite, radar waveform protection, EW library updates, jamming countermeasures, Low Probability of Intercept, radar cross-section management."),
        ("firmware_secure_boot", "satisfied", 20,
         "Questions about F-36 secure boot chain, firmware integrity verification, trusted platform module, code signing for avionics updates, bootloader security, firmware rollback protection."),
        ("fadec_engine_deep", "satisfied", 20,
         "Questions about F-36 FADEC dual-redundant architecture, engine control cybersecurity, thrust management protection, fuel system integrity, FADEC command authentication, engine health monitoring security."),
        ("navigation_gps_ins", "satisfied", 20,
         "Questions about F-36 GPS anti-jam, INS/GPS integration, navigation warfare, SAASM receivers, M-code GPS, inertial navigation security, position authentication, NAVWAR countermeasures."),
        ("supply_chain_deep", "satisfied", 20,
         "Questions about F-36 supply chain integrity, COTS component vetting, hardware trojan detection, counterfeit part prevention, vendor security assessment, DFARS compliance, trusted foundry requirements."),
        ("cross_framework_multi", "satisfied", 35,
         "Questions that combine 3+ frameworks. Example: 'How do CWE-787, NIST AC-4, and SPARTA SV-CF-1 collectively address the F-36's buffer overflow risks?' Must reference specific controls from at least 3 of: SPARTA, NIST 800-171, CWE, ATT&CK, D3FEND, DO-178C, ISO 27001."),
        ("compliance_edge", "satisfied", 30,
         "Questions about F-36 compliance edge cases: CMMC Level 3 vs SPARTA overlap, DO-178C DAL-A certification with SPARTA, ARP4754A development assurance, DISA STIG applicability, ITAR + cybersecurity intersection, DO-326A airborne security."),
        ("sensor_systems", "satisfied", 25,
         "Questions about F-36 sensor cybersecurity: EOTS (electro-optical targeting), DAS (distributed aperture system), infrared search and track, synthetic aperture radar, sensor fusion, targeting pod security, sensor data integrity."),
        ("weapon_systems", "satisfied", 25,
         "Questions about F-36 weapon systems cybersecurity: weapon release authorization, stores management, smart munition interfaces, weapon bus security, missile datalink protection, fire control system integrity."),
        ("c4isr_datalinks", "satisfied", 25,
         "Questions about F-36 C4ISR: tactical datalinks (Link 16, MADL), multi-domain command and control, SATCOM security, beyond-line-of-sight comms, data fusion module protection, coalition interoperability security."),
        ("maintenance_logistics", "satisfied", 25,
         "Questions about F-36 maintenance cybersecurity: ALIS/ODIN logistics system, maintenance diagnostic security, software reprogramming protection, depot-level maintenance security, portable maintenance aids, health monitoring data protection."),
        ("mission_planning", "satisfied", 20,
         "Questions about F-36 mission planning cybersecurity: mission data file protection, threat library updates, route planning security, mission debrief data handling, mission planning system integrity."),
        ("redundancy_safety", "satisfied", 25,
         "Questions about F-36 redundancy and safety: dual-redundant flight controls, dissimilar redundancy, common-mode failure prevention, safety-critical partitioning, DO-254 hardware assurance, fail-safe cybersecurity modes."),
        ("emerging_threats", "satisfied", 20,
         "Questions about emerging threats to F-36: AI-powered attacks on avionics, machine learning poisoning of sensor data, adversarial ML against target recognition, cognitive electronic warfare, advanced persistent threats targeting aircraft."),
        ("general_sparta_fill", "satisfied", 100,
         "General SPARTA questions about the F-36 covering: access control, configuration management, incident response, network segmentation, data protection, authentication, logging and monitoring, boundary protection, system integrity, personnel security. Mix easy and hard questions. Reference specific SPARTA control families: SV-AC, SV-CF, SV-MA, SV-IT, SV-SP, CM00xx, ESA-Txxxx."),
    ]

    for category, expected, count, context in domain_batches:
        print(f"Generating {count} {category} questions...", file=sys.stderr)
        # Split into batches of 25 to avoid token limits
        batch_results = []
        remaining = count
        batch_start = next_s_id
        while remaining > 0:
            batch_size = min(25, remaining)
            batch = generate_batch(category, expected, batch_size, context, batch_start)
            if not batch:
                print(f"  WARN: empty batch for {category}, retrying with text model", file=sys.stderr)
                time.sleep(2)
                batch = generate_batch(category, expected, batch_size, context, batch_start)
            batch_results.extend(batch)
            batch_start += len(batch)
            remaining -= len(batch)
            if remaining > 0:
                time.sleep(1)  # Rate limit courtesy
        all_new.extend(batch_results)
        next_s_id = batch_start
        print(f"  Generated {len(batch_results)} {category}", file=sys.stderr)

    # Combine existing + new
    combined = existing + all_new
    print(f"\nTotal: {len(combined)} questions ({len(existing)} existing + {len(all_new)} new)", file=sys.stderr)

    # Write expanded question file
    outfile = "/home/graham/.claude/skills/evidence-case-lab/state/questions_1000.json"
    with open(outfile, "w") as f:
        json.dump(combined, f, indent=2)
    print(f"Written to {outfile}", file=sys.stderr)

    # Summary by category
    cats = {}
    for q in combined:
        cat = q.get("framework_stratum", q.get("category", "unknown"))
        cats[cat] = cats.get(cat, 0) + 1
    print("\nCategory distribution:", file=sys.stderr)
    for cat, count in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {cat:40s}: {count:4d}", file=sys.stderr)


if __name__ == "__main__":
    main()
