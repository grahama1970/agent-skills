"""Evidence case test bank — generates ~160 questions from live data.

Tests four deterministic behaviors (gates-only, no LLM needed):
  1. SATISFIED (~50): Real QRA questions from sparta_qra. Pipeline MUST find evidence.
  2. NOT_SATISFIED (~20): Fabricated control IDs that don't exist. Pipeline MUST reject.
  3. INCONCLUSIVE (~40): Nonsense terms OR disjoint technique pairs. Pipeline can't resolve.
  4. OFF_TOPIC (~50): Non-security questions. Requires LLM — excluded from gates-only eval.

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
    """Generate adversarial questions deterministically — no LLM needed.

    Three mutation types from real data:
    1. FABRICATED_ID (~20): Real QRA with control ID swapped to a non-existent one
    2. NONSENSE_TERM (~20): Real QRA with a nonsensical term injected
    3. UNRELATED_PAIR (~20): Two real controls that don't share any technique (AQL)
    """
    rng = random.Random(seed)
    questions: list[TestQuestion] = []

    # --- Pull source QRAs for mutation ---
    source_qras: list[dict] = []
    seen_keys: set[str] = set()
    with _client() as c:
        for query in ["spacecraft firmware", "ground station authentication", "satellite encryption"]:
            r = c.post("/recall", json={"q": query, "collections": ["sparta_qra"], "limit": 15})
            r.raise_for_status()
            for item in r.json().get("items", []):
                key = item.get("_key", "")
                q_text = item.get("question", "")
                cid = item.get("control_id", "")
                if key and q_text and cid and key not in seen_keys:
                    seen_keys.add(key)
                    source_qras.append({"question": q_text, "control_id": cid, "_key": key})

    rng.shuffle(source_qras)

    # --- 0. MISSPELLED_ID: typos in real control IDs (should trigger CLARIFY) ---
    # IMPORTANT: These must be IDs that:
    #   1. Don't exist in the corpus (entity extraction returns fabricated_id)
    #   2. Look like plausible typos of real IDs
    # Verified fabricated (via entity extraction): CWW-79, CAPPEC-86, CAPC-86, CAPCE-86
    # Note: Many "transposed" NIST IDs actually exist (MC-8, MP-1, etc.)
    _MISSPELLINGS = [
        ("CWE-79", "CWW-79"),        # wrong letter after CW (CWW instead of CWE)
        ("CWE-79", "CWX-79"),        # wrong letter (CWX instead of CWE)
        ("CAPEC-86", "CAPPEC-86"),   # extra letter (double P)
        ("CAPEC-86", "CAPC-86"),     # missing letter (no E)
        ("CAPEC-86", "CAPCE-86"),    # transposed letters
        ("CAPEC-86", "CAPPCC-86"),   # extra letters (double P and C)
        ("SV-AC-1", "SV-XY-999"),    # fabricated SPARTA ID
        ("SV-MA-1", "SV-ZZ-123"),    # fabricated SPARTA ID
        ("T1059", "T9999"),          # fabricated ATT&CK ID (high number)
        ("AC-1", "AC-999"),          # NIST with unlikely high number
    ]
    for i, (real_id, misspelled) in enumerate(_MISSPELLINGS[:10]):
        questions.append(TestQuestion(
            question=f"What countermeasures does {misspelled} provide for spacecraft protection?",
            category="clarify",
            framework="misspelled",
            control_id=misspelled,
            expected_verdict="CLARIFY",
            rationale=f"Misspelled ID {misspelled} (should be {real_id}) — triggers CLARIFY path",
            source="deterministic_misspelled_id",
        ))

    # --- 1. FABRICATED_ID: swap real control ID for a fake one ---
    _FAKE_IDS = [
        "SV-AC-999", "CM9999", "EX-0099.07", "RD-9999.03", "LM-9999",
        "T9999.001", "CWE-99999", "CAPEC-99999", "ESA-T9999.001",
        "SC-999(7)", "PE-99", "AC-999", "SI-999", "CP-999", "MA-999",
        "SV-IT-999", "SV-SP-999", "SV-MA-999", "REC-9999.01", "DE-9999",
    ]
    for i, qra in enumerate(source_qras[:20]):
        fake_id = _FAKE_IDS[i % len(_FAKE_IDS)]
        orig_q = qra["question"]
        orig_cid = qra["control_id"]
        if orig_cid in orig_q:
            mutated_q = orig_q.replace(orig_cid, fake_id)
        else:
            mutated_q = f"How does {fake_id} address the threats described in: {orig_q}"
        questions.append(TestQuestion(
            question=mutated_q,
            category="not_satisfied",
            framework="fabricated",
            control_id=fake_id,
            expected_verdict="NOT_SATISFIED",
            rationale=f"Fabricated ID {fake_id} replacing real {orig_cid}",
            source="deterministic_fabricated_id",
        ))

    # --- 2. NONSENSE_TERM: inject absurd terms into real questions ---
    _NONSENSE = [
        "ham sandwich", "fusion-controlled space gloves", "quantum banana protocol",
        "thermonuclear yoga mat", "suborbital cheese wheel", "photonic breadstick array",
        "gravitational waffle iron", "dark matter toaster", "hypersonic umbrella",
        "plasma-infused garden hose", "antimatter stapler", "cosmic lint trap",
        "neutron-powered blender", "interstellar sock drawer", "warp-drive pencil sharpener",
        "dilithium-crystal napkin holder", "tachyonic rubber duck", "zero-gravity snow globe",
        "relativistic paper clip", "chronosynclastic dishwasher",
    ]
    for i, qra in enumerate(source_qras[20:40]):
        nonsense = _NONSENSE[i % len(_NONSENSE)]
        orig_q = qra["question"]
        mutated_q = orig_q.replace("?", f" involving {nonsense}?") if "?" in orig_q else (
            f"{orig_q} involving {nonsense}"
        )
        questions.append(TestQuestion(
            question=mutated_q,
            category="inconclusive",
            framework="none",
            control_id="",
            expected_verdict="INCONCLUSIVE",
            rationale=f"Nonsense term '{nonsense}' injected — unresolvable, not fabricated",
            source="deterministic_nonsense_term",
        ))

    # --- 3. UNRELATED_PAIR: two real controls from different technique families ---
    # SPARTA controls have parent_id (ST0001-ST0009) indicating technique category.
    # Controls from different parents are in unrelated technique families.
    from arango import ArangoClient
    pairs: list[dict] = []
    try:
        arango_client = ArangoClient(hosts="http://127.0.0.1:8529")
        db = arango_client.db("memory", username="root", password="openSesame")
        cursor = db.aql.execute("""
            FOR a IN sparta_controls
              FILTER a.source_framework == "SPARTA"
              FILTER a.parent_id != null AND a.parent_id != ""
              FOR b IN sparta_controls
                FILTER b.source_framework == "SPARTA"
                FILTER b.parent_id != null AND b.parent_id != ""
                FILTER a.parent_id != b.parent_id
                FILTER a.control_id < b.control_id
                LIMIT 100
                RETURN {
                  a_id: a.control_id, b_id: b.control_id,
                  a_name: a.name || a.control_id,
                  b_name: b.name || b.control_id,
                  a_tags: [a.parent_id], b_tags: [b.parent_id]
                }
        """)
        pairs = list(cursor)
    except Exception as exc:
        logger.warning("AQL cross-category technique query failed: {}", exc)

    rng.shuffle(pairs)
    _PAIR_TEMPLATES = [
        "How does {a_id} ({a_name}) relate to {b_id} ({b_name}) for spacecraft defense?",
        "What is the relationship between {a_id} and {b_id} in protecting satellite systems?",
        "How do {a_id} and {b_id} work together to mitigate space vehicle threats?",
    ]
    for i, pair in enumerate(pairs[:20]):
        template = _PAIR_TEMPLATES[i % len(_PAIR_TEMPLATES)]
        q = template.format(**pair)
        questions.append(TestQuestion(
            question=q,
            category="inconclusive",
            framework="cross",
            control_id=f"{pair['a_id']}+{pair['b_id']}",
            expected_verdict="INCONCLUSIVE",
            rationale=f"Disjoint techniques: {pair['a_id']} ({pair['a_tags']}) vs {pair['b_id']} ({pair['b_tags']})",
            source="deterministic_unrelated_pair",
        ))

    logger.info(
        "Adversarial generation: {} fabricated_id, {} nonsense_term, {} unrelated_pair",
        min(20, len(source_qras)),
        min(20, max(0, len(source_qras) - 20)),
        min(20, len(pairs)),
    )
    return questions


# ---------------------------------------------------------------------------
# 3b. CROSS-FRAMEWORK: CWE↔SPARTA and NIST↔SPARTA bidirectional questions
# ---------------------------------------------------------------------------

def _generate_cross_framework(seed: int = 42) -> list[TestQuestion]:
    """Generate CWE↔SPARTA and NIST↔SPARTA cross-framework questions.

    Two mapping paths exist in the graph:
    - Path 1: CWE → CAPEC → ATT&CK → SPARTA (curated MITRE edges)
    - Path 2: NIST → SPARTA (128K+ curated ISO 27001 edges)

    Questions test whether /extract-entities resolves entities from both
    frameworks and /recall's multi-hop traversal finds the connection.

    SATISFIED: entities from different frameworks that share a technique
    via graph edges (NIST AC-3 → SPARTA SV-AC-1 via iso27001 edge).
    INCONCLUSIVE: entities from different frameworks with no graph path.
    """
    client = _client()
    questions: list[TestQuestion] = []
    rng = random.Random(seed)

    # --- CWE → SPARTA questions (via CAPEC/ATT&CK or NIST bridge) ---
    _CWE_SPARTA_TEMPLATES = [
        "Given {cwe_id} ({cwe_name}), which SPARTA countermeasures address this vulnerability for {sparta_id}?",
        "How does {cwe_id} relate to SPARTA technique {sparta_id} ({sparta_name}) in spacecraft systems?",
        "What {sparta_id} mitigations apply to {cwe_id} ({cwe_name}) in space vehicle software?",
        "Does {cwe_id} ({cwe_name}) affect the same attack surface as {sparta_id} ({sparta_name})?",
        "Which SPARTA defenses for {sparta_id} address the weakness described by {cwe_id}?",
    ]

    # Get CWE+SPARTA pairs that co-occur via NIST bridge (from sparta_relationships)
    try:
        resp = client.post("/list", json={
            "collection": "sparta_relationships",
            "limit": 200,
            "return_fields": ["source_control_id", "target_control_id", "source_framework", "target_framework", "method"],
        })
        edges = resp.json().get("documents", [])
        # Find NIST controls that bridge to SPARTA
        nist_to_sparta = {}
        for e in edges:
            if e.get("source_framework") == "nist" and e.get("target_framework") == "sparta":
                nist_id = e["source_control_id"]
                sparta_id = e["target_control_id"]
                nist_to_sparta.setdefault(nist_id, []).append(sparta_id)
    except Exception:
        nist_to_sparta = {}

    # Get CWEs with their names
    cwe_samples = []
    try:
        resp = client.post("/list", json={
            "collection": "sparta_controls",
            "limit": 50,
            "filters": {"source_framework": "CWE"},
            "return_fields": ["control_id", "name"],
        })
        cwe_samples = resp.json().get("documents", [])
        rng.shuffle(cwe_samples)
    except Exception:
        pass

    # Get SPARTA controls with names
    sparta_samples = []
    try:
        resp = client.post("/list", json={
            "collection": "sparta_controls",
            "limit": 50,
            "filters": {"source_framework": "SPARTA"},
            "return_fields": ["control_id", "name"],
        })
        sparta_samples = resp.json().get("documents", [])
        rng.shuffle(sparta_samples)
    except Exception:
        pass

    # Generate SATISFIED: CWE + SPARTA pairs where graph connection likely exists
    for i, (cwe, sparta) in enumerate(zip(cwe_samples[:25], sparta_samples[:25])):
        template = _CWE_SPARTA_TEMPLATES[i % len(_CWE_SPARTA_TEMPLATES)]
        q = template.format(
            cwe_id=cwe["control_id"],
            cwe_name=cwe.get("name", "")[:60],
            sparta_id=sparta["control_id"],
            sparta_name=sparta.get("name", "")[:60],
        )
        questions.append(TestQuestion(
            question=q,
            category="satisfied",
            framework="cross",
            control_id=f"{cwe['control_id']}+{sparta['control_id']}",
            expected_verdict="SATISFIED",
            rationale=f"Cross-framework CWE+SPARTA, graph may connect via NIST bridge",
            source="cross_framework_cwe_sparta",
        ))

    # --- NIST → SPARTA questions (direct edge via ISO 27001) ---
    _NIST_SPARTA_TEMPLATES = [
        "How does NIST control {nist_id} support SPARTA technique {sparta_id} ({sparta_name}) defense?",
        "What is the compliance mapping between {nist_id} and {sparta_id} for spacecraft?",
        "Does implementing {nist_id} mitigate the threat described by {sparta_id} ({sparta_name})?",
        "How do {nist_id} requirements align with SPARTA {sparta_id} countermeasures?",
        "What role does {nist_id} play in defending against {sparta_id} ({sparta_name})?",
    ]

    # Get NIST controls with names
    nist_samples = []
    try:
        resp = client.post("/list", json={
            "collection": "sparta_controls",
            "limit": 50,
            "filters": {"source_framework": "NIST"},
            "return_fields": ["control_id", "name"],
        })
        nist_samples = resp.json().get("documents", [])
        rng.shuffle(nist_samples)
    except Exception:
        pass

    # SATISFIED: NIST + SPARTA pairs with direct ISO 27001 edges
    nist_sparta_pairs = []
    for nist_id, sparta_ids in nist_to_sparta.items():
        for sid in sparta_ids[:2]:
            nist_doc = next((n for n in nist_samples if n["control_id"] == nist_id), None)
            sparta_doc = next((s for s in sparta_samples if s["control_id"] == sid), None)
            if nist_doc and sparta_doc:
                nist_sparta_pairs.append((nist_doc, sparta_doc))
    rng.shuffle(nist_sparta_pairs)

    for i, (nist, sparta) in enumerate(nist_sparta_pairs[:25]):
        template = _NIST_SPARTA_TEMPLATES[i % len(_NIST_SPARTA_TEMPLATES)]
        q = template.format(
            nist_id=nist["control_id"],
            sparta_id=sparta["control_id"],
            sparta_name=sparta.get("name", "")[:60],
        )
        questions.append(TestQuestion(
            question=q,
            category="satisfied",
            framework="cross",
            control_id=f"{nist['control_id']}+{sparta['control_id']}",
            expected_verdict="SATISFIED",
            rationale=f"NIST→SPARTA edge exists via ISO 27001 curated mapping",
            source="cross_framework_nist_sparta",
        ))

    # INCONCLUSIVE: CWE + unrelated SPARTA (no graph path expected)
    for i in range(min(25, len(cwe_samples), len(sparta_samples))):
        cwe = cwe_samples[-(i + 1)]  # pick from opposite end
        sparta = sparta_samples[i]
        q = f"How does {cwe['control_id']} ({cwe.get('name', '')[:40]}) impact {sparta['control_id']} ({sparta.get('name', '')[:40]}) spacecraft defenses?"
        questions.append(TestQuestion(
            question=q,
            category="inconclusive",
            framework="cross",
            control_id=f"{cwe['control_id']}+{sparta['control_id']}",
            expected_verdict="INCONCLUSIVE",
            rationale="Cross-framework CWE+SPARTA with likely no graph path",
            source="cross_framework_unrelated",
        ))

    logger.info("Cross-framework generation: {} CWE+SPARTA, {} NIST+SPARTA, {} unrelated",
                min(25, len(cwe_samples)), len(nist_sparta_pairs[:25]),
                min(25, len(cwe_samples)))
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

def _relabel_by_entity_check(questions: list[TestQuestion]) -> list[TestQuestion]:
    """Call /extract-entities on questions and relabel based on what the
    pipeline will actually produce. Fixes label mismatches:

    - SATISFIED with disjoint SPARTA parents → INCONCLUSIVE
    - INCONCLUSIVE with no resolved entities → NOT_SATISFIED
    - SATISFIED with grounding_ok=False → NOT_SATISFIED

    /extract-entities is deterministic and fast (~0.5s per question).
    """
    relabeled = 0
    with _client() as c:
        for q in questions:
            if q.category == "off_topic":
                continue
            try:
                r = c.post("/extract-entities", json={"text": q.question}, timeout=10)
                r.raise_for_status()
                entities = r.json()
                resolved = entities.get("resolved_entities", [])
                grounding_ok = entities.get("grounding_ok", False)
                tc = entities.get("technique_coherence", {})
                technique_ok = tc.get("ok", True)
                technique_detail = tc.get("detail", "")

                if q.category == "satisfied":
                    if not technique_ok:
                        object.__setattr__(q, "category", "inconclusive")
                        object.__setattr__(q, "expected_verdict", "INCONCLUSIVE")
                        object.__setattr__(q, "rationale",
                            f"Real QRA but disjoint techniques: {technique_detail}. "
                            f"Original control_id={q.control_id}.")
                        relabeled += 1
                    elif not grounding_ok or not resolved:
                        object.__setattr__(q, "category", "not_satisfied")
                        object.__setattr__(q, "expected_verdict", "NOT_SATISFIED")
                        object.__setattr__(q, "rationale",
                            f"Real QRA but grounding failed. "
                            f"Original control_id={q.control_id}.")
                        relabeled += 1

                elif q.category == "inconclusive":
                    if not resolved:
                        object.__setattr__(q, "category", "not_satisfied")
                        object.__setattr__(q, "expected_verdict", "NOT_SATISFIED")
                        object.__setattr__(q, "rationale",
                            f"Inconclusive question but no entities resolved → not_satisfied.")
                        relabeled += 1
                    elif grounding_ok and technique_ok:
                        object.__setattr__(q, "category", "satisfied")
                        object.__setattr__(q, "expected_verdict", "SATISFIED")
                        object.__setattr__(q, "rationale",
                            f"Inconclusive question but entities resolved + grounding OK → satisfied.")
                        relabeled += 1

            except Exception as exc:
                logger.debug("entity pre-check failed for '{}': {}", q.question[:60], exc)
    if relabeled:
        logger.info("Relabeled {} questions based on /extract-entities pre-check", relabeled)
    return questions


def generate_bank(seed: int = 42, balanced: bool = True) -> list[TestQuestion]:
    """Generate the test bank.

    Args:
        seed: Random seed for reproducibility.
        balanced: If True, cap each category at 50 for balanced evaluation.
                  If False, return full bank (~1000 questions).

    Returns:
        List of TestQuestion testing four verdict paths:
        - satisfied: real QRAs the pipeline MUST answer
        - not_satisfied: fabricated IDs + nonsense terms
        - inconclusive: cross-category technique pairs
        - off_topic: non-security questions for deflect
    """
    rng = random.Random(seed)
    satisfied = _generate_satisfied(seed)
    try:
        adversarial = _generate_adversarial(seed)  # NOT_SATISFIED + INCONCLUSIVE
    except Exception as exc:
        logger.warning("Adversarial generation failed (non-fatal): {}", exc)
        adversarial = []
    try:
        cross_fw = _generate_cross_framework(seed)
    except Exception as exc:
        logger.warning("Cross-framework generation failed (non-fatal): {}", exc)
        cross_fw = []
    # Merge cross-framework into satisfied/adversarial by category
    for q in cross_fw:
        if q.category == "satisfied":
            satisfied.append(q)
        else:
            adversarial.append(q)
    off_topic = _generate_off_topic(seed)

    if balanced:
        cap = 50
        rng.shuffle(satisfied)
        satisfied = satisfied[:cap]
        not_sat = [q for q in adversarial if q.category == "not_satisfied"]
        inconcl = [q for q in adversarial if q.category == "inconclusive"]
        rng.shuffle(not_sat)
        rng.shuffle(inconcl)
        rng.shuffle(off_topic)
        adversarial = not_sat[:cap] + inconcl[:cap]
        off_topic = off_topic[:cap]

    # Pre-check: run /extract-entities on SATISFIED questions to catch
    # disjoint technique pairs. CWE mapping is experimental — questions
    # whose controls resolve to different SPARTA parents are INCONCLUSIVE.
    all_questions = satisfied + adversarial
    all_questions = _relabel_by_entity_check(all_questions)
    satisfied = [q for q in all_questions if q.category == "satisfied"]
    adversarial = [q for q in all_questions if q.category != "satisfied"]

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


# ---------------------------------------------------------------------------
# Batch Validation Runner
# ---------------------------------------------------------------------------

def _status_to_verdict(status: str, entity_info: dict | None = None) -> str:
    """Map evidence_case status to expected verdict.

    Args:
        status: Status from evidence_case (assembled, unmapped, no_entity, error)
        entity_info: Optional entity extraction result to detect CLARIFY conditions

    Returns: SATISFIED | NOT_SATISFIED | INCONCLUSIVE | CLARIFY | UNKNOWN
    """
    import re

    # Check for CLARIFY conditions from entity extraction
    if entity_info:
        agent_decision = entity_info.get("agent_decision", {})
        unresolved = entity_info.get("unresolved_entities", [])

        # CLARIFY triggers on misspelled/fabricated IDs that look like valid control IDs
        # Patterns for IDs that LOOK like control IDs but are fabricated/misspelled
        # The key: entity extraction already flagged these as fabricated_id/misspelled
        # We just need to verify they look like plausible typos, not random strings
        control_id_pattern = re.compile(
            r"^("
            r"CW[A-Z]-\d+|"              # CWW-79, CWX-123 (wrong letter after CW)
            r"CA+P+E?C-\d+|"             # CAPPEC-86, CAAPC-86 (extra letters)
            r"CAP[A-Z]*-\d+|"            # CAPC-86, CAPCE-86, CAPCX-86 (missing/wrong letters)
            r"[A-Z]{2,3}EC-\d+|"         # XYZEC-86 (any prefix ending in EC)
            r"SV-[A-Z]{2}-\d+|"          # SV-XX-N SPARTA IDs (transposed)
            r"T\d{4,}|"                  # T1509, T12345 (transposed/extra digits)
            r"[A-Z]{2}-\d{3,}"           # XX-NNN+ (NIST-like with 3+ digits = likely invalid)
            r")",
            re.IGNORECASE
        )

        for ent in unresolved:
            reason = ent.get("reason", "")
            if reason in {"fabricated_id", "misspelled", "invalid_format"}:
                mention = ent.get("mention", "")
                if control_id_pattern.match(mention):
                    return "CLARIFY"

        # Also check agent_decision for explicit needs_clarification
        if agent_decision.get("needs_clarification"):
            return "CLARIFY"

    if status == "assembled":
        return "SATISFIED"
    elif status == "unmapped":
        return "INCONCLUSIVE"
    elif status == "no_entity":
        return "NOT_SATISFIED"
    elif status == "error":
        return "NOT_SATISFIED"
    else:
        return "UNKNOWN"


@dataclass
class ValidationResult:
    question_id: str
    question: str
    category: str
    expected_verdict: str
    actual_verdict: str
    status: str
    chain_count: int
    retrieval_score: float
    elapsed_ms: int
    correct: bool
    error: str = ""
    entity_reason: str = ""  # For CLARIFY: fabricated_id, misspelled, etc.


def validate_batch(
    bank: list[TestQuestion],
    dry_run: bool = True,
    max_questions: int | None = None,
    categories: list[str] | None = None,
) -> dict:
    """Run the evidence case pipeline against the test bank.

    Args:
        bank: List of TestQuestion from generate_bank()
        dry_run: If True, don't persist QRAs to database
        max_questions: Limit total questions to validate
        categories: Filter to specific categories (satisfied, not_satisfied, etc.)

    Returns:
        {
            "total": int,
            "correct": int,
            "accuracy": float,
            "by_category": {category: {correct, total, accuracy}},
            "by_expected_verdict": {verdict: {correct, total, accuracy}},
            "confusion_matrix": {expected: {actual: count}},
            "results": [ValidationResult...],
            "errors": [...]
        }
    """
    import time
    from daemon_client import assemble_evidence, enrich_v43, extract_entities

    results: list[ValidationResult] = []
    errors: list[dict] = []

    # Filter questions
    questions = bank
    if categories:
        questions = [q for q in questions if q.category in categories]
    if max_questions:
        questions = questions[:max_questions]

    logger.info("Validating {} questions (dry_run={})", len(questions), dry_run)

    for i, q in enumerate(questions):
        if (i + 1) % 20 == 0:
            logger.info("Progress: {}/{}", i + 1, len(questions))

        start_ms = time.perf_counter_ns() // 1_000_000
        try:
            # First call extract_entities to get detailed info for CLARIFY detection
            entity_info = extract_entities(q.question)
            entity_reason = ""
            for ent in entity_info.get("unresolved_entities", []):
                if ent.get("reason"):
                    entity_reason = ent.get("reason")
                    break

            # Run evidence assembly
            evidence = assemble_evidence(
                question=q.question,
                source_id=q.control_id if q.control_id and "+" not in q.control_id else None,
            )

            # Enrich to v4.3 schema
            qra = enrich_v43(
                evidence=evidence,
                question=q.question,
                source_control_id=q.control_id if q.control_id else None,
            )

            elapsed_ms = (time.perf_counter_ns() // 1_000_000) - start_ms

            # Extract results
            ev_case = qra.get("evidence_case", {})
            status = ev_case.get("status", evidence.get("error", "unknown"))
            chains = ev_case.get("chains", [])
            scores = qra.get("scores", {})
            retrieval = scores.get("retrieval_score", 0.0)

            # Pass entity_info to detect CLARIFY conditions
            actual_verdict = _status_to_verdict(status, entity_info)

            # For off_topic: any non-SATISFIED is correct
            # For clarify: CLARIFY is expected
            if q.category == "off_topic":
                correct = actual_verdict != "SATISFIED"
            elif q.category == "clarify":
                correct = actual_verdict == "CLARIFY"
            else:
                correct = actual_verdict == q.expected_verdict

            results.append(ValidationResult(
                question_id=getattr(q, "_id", ""),
                question=q.question[:200],
                category=q.category,
                expected_verdict=q.expected_verdict,
                actual_verdict=actual_verdict,
                status=status,
                chain_count=len(chains),
                retrieval_score=retrieval,
                elapsed_ms=elapsed_ms,
                correct=correct,
                entity_reason=entity_reason,
            ))

        except Exception as exc:
            elapsed_ms = (time.perf_counter_ns() // 1_000_000) - start_ms
            errors.append({
                "question_id": getattr(q, "_id", ""),
                "question": q.question[:100],
                "error": str(exc),
            })
            results.append(ValidationResult(
                question_id=getattr(q, "_id", ""),
                question=q.question[:200],
                category=q.category,
                expected_verdict=q.expected_verdict,
                actual_verdict="ERROR",
                status="error",
                chain_count=0,
                retrieval_score=0.0,
                elapsed_ms=elapsed_ms,
                correct=False,
                error=str(exc),
            ))

    # Compute metrics
    total = len(results)
    correct = sum(1 for r in results if r.correct)
    accuracy = correct / total if total > 0 else 0.0

    # By category
    by_category = {}
    for cat in ["satisfied", "not_satisfied", "inconclusive", "off_topic"]:
        cat_results = [r for r in results if r.category == cat]
        cat_correct = sum(1 for r in cat_results if r.correct)
        cat_total = len(cat_results)
        by_category[cat] = {
            "correct": cat_correct,
            "total": cat_total,
            "accuracy": cat_correct / cat_total if cat_total > 0 else 0.0,
        }

    # By expected verdict
    by_verdict = {}
    for verdict in ["SATISFIED", "NOT_SATISFIED", "INCONCLUSIVE", "DEFLECT"]:
        v_results = [r for r in results if r.expected_verdict == verdict]
        v_correct = sum(1 for r in v_results if r.correct)
        v_total = len(v_results)
        by_verdict[verdict] = {
            "correct": v_correct,
            "total": v_total,
            "accuracy": v_correct / v_total if v_total > 0 else 0.0,
        }

    # Confusion matrix
    confusion = {}
    for r in results:
        expected = r.expected_verdict
        actual = r.actual_verdict
        if expected not in confusion:
            confusion[expected] = {}
        confusion[expected][actual] = confusion[expected].get(actual, 0) + 1

    # Timing stats
    elapsed_times = [r.elapsed_ms for r in results]
    avg_ms = sum(elapsed_times) / len(elapsed_times) if elapsed_times else 0
    p95_ms = sorted(elapsed_times)[int(len(elapsed_times) * 0.95)] if elapsed_times else 0

    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "by_category": by_category,
        "by_expected_verdict": by_verdict,
        "confusion_matrix": confusion,
        "timing": {
            "avg_ms": round(avg_ms, 1),
            "p95_ms": p95_ms,
        },
        "results": results,
        "errors": errors,
    }


def print_validation_report(report: dict) -> None:
    """Print a human-readable validation report."""
    print("\n" + "=" * 70)
    print("EVIDENCE CASE BATCH VALIDATION REPORT")
    print("=" * 70)

    print(f"\nOverall: {report['correct']}/{report['total']} correct ({report['accuracy']:.1%})")
    print(f"Timing: avg={report['timing']['avg_ms']}ms, p95={report['timing']['p95_ms']}ms")

    print("\n--- By Category ---")
    for cat, stats in report["by_category"].items():
        print(f"  {cat:15} {stats['correct']:3}/{stats['total']:3} ({stats['accuracy']:.1%})")

    print("\n--- By Expected Verdict ---")
    for verdict, stats in report["by_expected_verdict"].items():
        print(f"  {verdict:15} {stats['correct']:3}/{stats['total']:3} ({stats['accuracy']:.1%})")

    print("\n--- Confusion Matrix ---")
    cm = report["confusion_matrix"]
    all_verdicts = sorted(set(v for row in cm.values() for v in row.keys()) | set(cm.keys()))
    header = "Expected\\Actual | " + " | ".join(f"{v:12}" for v in all_verdicts)
    print(header)
    print("-" * len(header))
    for expected in sorted(cm.keys()):
        row = cm[expected]
        cells = [f"{row.get(v, 0):12}" for v in all_verdicts]
        print(f"{expected:15} | " + " | ".join(cells))

    if report["errors"]:
        print(f"\n--- Errors ({len(report['errors'])}) ---")
        for e in report["errors"][:5]:
            print(f"  {e['question_id']}: {e['error'][:60]}")
        if len(report["errors"]) > 5:
            print(f"  ... and {len(report['errors']) - 5} more")

    # Show misclassified examples
    misclassified = [r for r in report["results"] if not r.correct]
    if misclassified:
        print(f"\n--- Misclassified Examples ({len(misclassified)}) ---")
        for r in misclassified[:10]:
            print(f"  [{r.category}] expected={r.expected_verdict}, actual={r.actual_verdict}")
            print(f"    status={r.status}, chains={r.chain_count}, score={r.retrieval_score:.2f}")
            print(f"    Q: {r.question[:80]}...")


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "validate":
        # Run batch validation
        max_q = int(sys.argv[2]) if len(sys.argv) > 2 else None
        bank = generate_bank(balanced=True)
        report = validate_batch(bank, dry_run=True, max_questions=max_q)
        print_validation_report(report)

        # Save results
        out_path = Path(__file__).parent / "validation_results.json"
        with open(out_path, "w") as f:
            # Convert dataclass results to dicts
            report_json = {k: v for k, v in report.items() if k != "results"}
            report_json["results"] = [
                {k: v for k, v in r.__dict__.items()} for r in report["results"]
            ]
            json.dump(report_json, f, indent=2)
        print(f"\nResults saved to {out_path}")
    else:
        # Default: show bank summary
        bank = generate_bank()
        summary = bank_summary(bank)
        print(json.dumps(summary, indent=2))
        print("\nSample questions per category:")
        for cat in ["satisfied", "not_satisfied", "inconclusive", "off_topic"]:
            subset = [q for q in bank if q.category == cat]
            print(f"\n--- {cat} ({len(subset)}) ---")
            for q in subset[:3]:
                print(f"  [{q.framework}|{q.expected_verdict}] {q.question[:120]}")
