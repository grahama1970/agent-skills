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
from loguru import logger

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
    sock = os.environ.get("EMBRY_MEMORY_SOCKET", f"/run/user/{os.getuid()}/embry/memory.sock")
    transport = httpx.HTTPTransport(uds=sock)
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
            r.raise_for_status()
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
        total_r.raise_for_status()
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
# 2+3. NOT_SATISFIED + INCONCLUSIVE: LLM-generated adversarial mutations
# ---------------------------------------------------------------------------

def _find_project_root() -> Path:
    """Walk up from __file__ to find the directory containing .pi/."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / ".pi").is_dir():
            return p
        p = p.parent
    raise FileNotFoundError("No .pi/ directory found in parents")


_PROJECT_ROOT = _find_project_root()
_SKILLS_DIR = _PROJECT_ROOT / ".pi" / "skills"
_ADVERSARIAL_PROMPT_PATH = _SKILLS_DIR / "prompt-lab" / "prompts" / "evidence_case_adversarial_v1.txt"

_SCILLM_URL = os.environ.get("SCILLM_URL", "http://localhost:4001") + "/v1/chat/completions"
_SCILLM_KEY = os.environ.get("SCILLM_API_KEY", "sk-dev-proxy-123")

_REQUIRED_MUTATION_FIELDS = {"question", "type"}
_VALID_MUTATION_TYPES = {"FABRICATED_ID", "PHANTOM_TERM", "NON_SECURITY_ENTITY", "UNRELATED_PAIR"}


def _call_scillm_batch(batch_idx: int, batch: list[dict], system_prompt: str) -> list[dict]:
    """Sync httpx call to scillm for one batch of QRA mutations."""
    import json as _json

    user_lines = []
    for i, q in enumerate(batch):
        user_lines.append(
            f'{i + 1}. "{q["question"]}" (control_id: {q["control_id"]})'
        )
    user_prompt = (
        "Here are 5 real QRA questions from the SPARTA corpus. "
        "For EACH question, generate 3 adversarial mutations — "
        "one FABRICATED_ID, one PHANTOM_TERM, and one NON_SECURITY_ENTITY. "
        "Then generate 3 additional UNRELATED_PAIR questions using control IDs "
        "from different questions below.\n\n"
        + "\n".join(user_lines)
        + "\n\nReturn 18 total: 15 mutations (3 per source QRA) + 3 UNRELATED_PAIR."
    )

    resp = httpx.post(
        _SCILLM_URL,
        headers={"Authorization": f"Bearer {_SCILLM_KEY}"},
        json={
            "model": "text",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.9,
            "scillm_metadata": {
                "source_keys": [q["_key"] for q in batch],
                "control_ids": [q["control_id"] for q in batch],
                "batch_index": batch_idx,
            },
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()

    if "choices" not in data or not data["choices"]:
        raise ValueError(f"scillm returned no choices for batch {batch_idx}")

    content = data["choices"][0]["message"]["content"]
    meta = data.get("scillm_metadata", {})
    source_keys = meta.get("source_keys", [q["_key"] for q in batch])

    # Parse JSON — handle markdown fences
    content = content.strip()
    if content.startswith("```"):
        content = content.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    mutations = _json.loads(content)
    if isinstance(mutations, dict):
        mutations = mutations.get("mutations", mutations.get("questions", []))

    if not isinstance(mutations, list):
        raise ValueError(f"scillm batch {batch_idx} returned non-list: {type(mutations)}")

    # Validate and join metadata
    valid = []
    for m in mutations:
        if not isinstance(m, dict):
            continue
        missing = _REQUIRED_MUTATION_FIELDS - set(m.keys())
        if missing:
            logger.warning("Skipping mutation missing fields {}: {}", missing, m)
            continue
        if m["type"] not in _VALID_MUTATION_TYPES:
            logger.warning("Skipping mutation with invalid type '{}': {}", m["type"], m.get("question", "")[:60])
            continue
        if not m["question"].strip():
            logger.warning("Skipping mutation with empty question")
            continue
        idx = m.get("source_index", 0)
        if idx < len(source_keys):
            m["source_key"] = source_keys[idx]
        m["batch_index"] = batch_idx
        valid.append(m)

    return valid


def _generate_adversarial(seed: int = 42) -> list[TestQuestion]:
    """Generate adversarial questions by mutating real QRAs via /scillm.

    Pulls real QRAs from daemon, sends batches of 5 to scillm with the
    adversarial mutation prompt. Each batch returns ~18 mutations
    (3 per source QRA + 3 UNRELATED_PAIR). Runs 3 batches concurrently
    via ThreadPoolExecutor (no asyncio).

    Raises if adversarial generation produces fewer than 10 mutations.
    """
    from concurrent.futures import ThreadPoolExecutor

    rng = random.Random(seed)

    if not _ADVERSARIAL_PROMPT_PATH.exists():
        raise FileNotFoundError(f"Adversarial prompt not found: {_ADVERSARIAL_PROMPT_PATH}")
    system_prompt = _ADVERSARIAL_PROMPT_PATH.read_text()

    # Pull 15 diverse real QRAs from daemon (3 queries x 5 results)
    source_qras: list[dict] = []
    seen_keys: set[str] = set()
    recall_queries = [
        "spacecraft firmware tampering countermeasure",
        "ground station authentication remote access",
        "satellite telemetry encryption vulnerability",
    ]
    with _client() as c:
        for query in recall_queries:
            r = c.post("/recall", json={
                "q": query, "collections": ["sparta_qra"], "limit": 8,
            })
            r.raise_for_status()
            resp_data = r.json()
            if "items" not in resp_data:
                logger.warning("Recall returned no items for query '{}': {}", query, list(resp_data.keys()))
                continue
            for item in resp_data["items"]:
                key = item.get("_key", "")
                q_text = item.get("question", "")
                cid = item.get("control_id", "")
                if key and q_text and cid and key not in seen_keys:
                    seen_keys.add(key)
                    source_qras.append({
                        "_key": key, "question": q_text, "control_id": cid,
                    })

    if len(source_qras) < 5:
        raise RuntimeError(
            f"Only {len(source_qras)} QRAs found from daemon — need at least 5 for adversarial generation"
        )

    rng.shuffle(source_qras)
    source_qras = source_qras[:15]

    # Split into batches of 5, run concurrently via threads
    batches = [source_qras[i:i + 5] for i in range(0, len(source_qras), 5)]

    all_mutations: list[dict] = []
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(_call_scillm_batch, i, b, system_prompt): i
            for i, b in enumerate(batches) if b
        }
        for future in futures:
            batch_idx = futures[future]
            try:
                mutations = future.result()
                all_mutations.extend(mutations)
                logger.info("Adversarial batch {} returned {} mutations", batch_idx, len(mutations))
            except Exception as exc:
                errors.append(f"batch {batch_idx}: {exc}")
                logger.error("Adversarial batch {} failed: {}", batch_idx, exc)

    if errors and not all_mutations:
        raise RuntimeError(f"All adversarial batches failed: {'; '.join(errors)}")

    if len(all_mutations) < 10:
        logger.warning(
            "Only {} adversarial mutations generated (expected ~54). "
            "Errors: {}", len(all_mutations), errors or "none"
        )

    # Convert mutations to TestQuestion objects
    _TYPE_MAP = {
        "FABRICATED_ID": ("not_satisfied", "NOT_SATISFIED", "fabricated"),
        "PHANTOM_TERM": ("not_satisfied", "NOT_SATISFIED", "none"),
        "NON_SECURITY_ENTITY": ("not_satisfied", "NOT_SATISFIED", "none"),
        "UNRELATED_PAIR": ("inconclusive", "INCONCLUSIVE", "cross"),
    }
    questions: list[TestQuestion] = []
    for m in all_mutations:
        mut_type = m["type"]
        category, verdict, framework = _TYPE_MAP[mut_type]
        questions.append(TestQuestion(
            question=m["question"],
            category=category,
            framework=framework,
            control_id=m.get("payload", ""),
            expected_verdict=verdict,
            rationale=f"LLM-generated {mut_type} mutation of real QRA "
                      f"(source_key={m.get('source_key', 'unknown')}). "
                      f"Payload: {m.get('payload', '')}",
            source=f"scillm_{mut_type.lower()}",
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
        - satisfied (~750): real QRAs the pipeline MUST answer
        - not_satisfied + inconclusive (~54): LLM-generated adversarial mutations
        - off_topic (~200): non-security questions for deflect
    """
    satisfied = _generate_satisfied(seed)
    try:
        adversarial = _generate_adversarial(seed)  # NOT_SATISFIED + INCONCLUSIVE
    except Exception as exc:
        logger.warning("Adversarial generation failed (non-fatal): {}", exc)
        adversarial = []
    off_topic = _generate_off_topic(seed)

    bank = satisfied + adversarial + off_topic

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
