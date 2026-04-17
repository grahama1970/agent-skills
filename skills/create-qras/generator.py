#!/usr/bin/env python3
"""
QRA Generator - Unified QRA generation from controls, documents, or text.

Three QRA types:
- relationship: CWE→SPARTA mappings via /create-evidence-case crosswalk chains
- standalone: From sparta_url_knowledge documents
- independent: NIST/MITRE controls without technique mapping (direct extraction)
"""
import asyncio
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

import httpx
import typer
import yaml

# Import schema validation for CWE QRAs
try:
    from qra_schema import QRAResult, validate_qra_payload, validate_grounding_against_record
    HAS_SCHEMA_VALIDATION = True
except ImportError:
    HAS_SCHEMA_VALIDATION = False

# Import two-stage relationship QRA schemas
try:
    from relationship_qra_schema import (
        GateResult,
        EligiblePair,
        RelationshipQRAPair,
        validate_gate_response,
        validate_qra_response,
        validate_grounding_against_payload,
    )
    HAS_TWO_STAGE_SCHEMA = True
except ImportError:
    HAS_TWO_STAGE_SCHEMA = False

app = typer.Typer(help="Generate QRA pairs from various sources")

# Framework detection patterns
# Updated 2026-04-16 to match actual control_id formats in sparta_controls
FRAMEWORK_PATTERNS = {
    "CWE": re.compile(r"^CWE-\d+$", re.I),
    "CAPEC": re.compile(r"^CAPEC-\d+$", re.I),
    # ATT&CK: T=techniques, M=mitigations (skip S=software via control_type filter)
    "ATT&CK": re.compile(r"^[TM]\d{4}(\.\d{3})?$", re.I),
    # SPARTA: ST=tactics, XXX-NNNN=techniques (REC,EXE,IAC,etc), CM=countermeasures
    "SPARTA": re.compile(r"^(ST\d{4}|[A-Z]{2,4}-\d{4}(\.\d{2})?|CM[-]?\w+)$", re.I),
    "NIST": re.compile(r"^[A-Z]{2}-\d+(\(\d+\))?$", re.I),  # AC-17, AC-17(1)
    "D3FEND": re.compile(r"^D3-[A-Z]+$", re.I),  # D3-AI, D3-MFA
    # ESA space threat techniques
    "ESA": re.compile(r"^ESA-T\d{4}(\.\d{3})?$", re.I),  # ESA-T1489.001
}

# Controls that need relationship QRAs (have crosswalk chains)
RELATIONSHIP_FRAMEWORKS = {"CWE", "CAPEC", "ATT&CK"}

# Controls that get independent QRAs (no crosswalk needed)
INDEPENDENT_FRAMEWORKS = {"NIST", "SPARTA"}

# Worksheets.yaml location (single source of truth for framework registry)
WORKSHEETS_YAML = Path("/home/graham/workspace/experiments/sparta/config/worksheets.yaml")

# Fallback map if worksheets.yaml unavailable
_FALLBACK_FRAMEWORK_MAP = {
    "ATT&CK": "ATT_CK_Enterprise",
    "ATTACK": "ATT_CK_Enterprise",
    "ATT_CK": "ATT_CK_Enterprise",
    "CWE": "CWE",
    "CAPEC": "CAPEC",
    "NIST": "NIST_800_53",
    "SPARTA": "SPARTA",
    "D3FEND": "D3FEND",
}

def _load_framework_source_map() -> dict[str, str]:
    """Load framework alias → canonical value map from worksheets.yaml.

    Returns dict mapping all aliases to their canonical source_framework value.
    Falls back to hardcoded map if worksheets.yaml unavailable.
    """
    if not WORKSHEETS_YAML.exists():
        return _FALLBACK_FRAMEWORK_MAP.copy()

    try:
        with open(WORKSHEETS_YAML) as f:
            config = yaml.safe_load(f)

        registry = config.get("framework_registry", {})
        if not registry:
            return _FALLBACK_FRAMEWORK_MAP.copy()

        # Build alias → canonical map
        alias_map = {}
        for canonical, info in registry.items():
            # Map canonical name to itself
            alias_map[canonical] = canonical
            alias_map[canonical.upper()] = canonical
            alias_map[canonical.lower()] = canonical
            # Map all aliases to canonical
            for alias in info.get("aliases", []):
                alias_map[alias] = canonical
                alias_map[alias.upper()] = canonical
                alias_map[alias.lower()] = canonical

        return alias_map
    except Exception:
        return _FALLBACK_FRAMEWORK_MAP.copy()


def _load_framework_prompt_map() -> dict[str, str]:
    """Load canonical framework → prompt branch name from worksheets.yaml.

    For prompt selection, we need to normalize database values like 'ATT_CK_Enterprise'
    to the branch names used in if/elif checks like 'ATT&CK'.

    Uses the first alias that matches an if/elif branch name, or falls back to canonical.
    """
    # Known branch names used in the if/elif prompt selection
    known_branches = {"CWE", "CAPEC", "ATT&CK", "D3FEND", "NIST", "SPARTA", "ESA"}

    if not WORKSHEETS_YAML.exists():
        return {}

    try:
        with open(WORKSHEETS_YAML) as f:
            config = yaml.safe_load(f)

        registry = config.get("framework_registry", {})
        if not registry:
            return {}

        # Build canonical → branch name map
        prompt_map = {}
        for canonical, info in registry.items():
            # Check if canonical itself is a known branch
            if canonical in known_branches:
                prompt_map[canonical] = canonical
                continue
            # Check aliases for a known branch name
            for alias in info.get("aliases", []):
                if alias in known_branches:
                    prompt_map[canonical] = alias
                    break
            else:
                # No known branch found, use canonical
                prompt_map[canonical] = canonical

        return prompt_map
    except Exception:
        return {}


# Load framework source map from worksheets.yaml (or fallback)
FRAMEWORK_SOURCE_MAP = _load_framework_source_map()

# Load canonical → prompt branch name map from worksheets.yaml
# Used to normalize 'ATT_CK_Enterprise' → 'ATT&CK' for prompt selection
FRAMEWORK_PROMPT_MAP = _load_framework_prompt_map()

# Prompt template directory (centralized in prompt-lab)
PROMPT_LAB_DIR = Path("/home/graham/workspace/experiments/scillm/.skills/prompt-lab/prompts/qra")
# Local prompts directory (for native mode prompts)
LOCAL_PROMPTS_DIR = Path(__file__).parent / "prompts"
# Native prompts subdirectory (clean naming: prompts/native/{framework}_system.txt)
NATIVE_PROMPTS_DIR = LOCAL_PROMPTS_DIR / "native"

# Framework → category mapping for native QRAs
FRAMEWORK_TO_CATEGORY = {
    "CWE": "cwe_native",
    "CAPEC": "capec_native",
    "NIST": "nist_native",
    "ATT_CK_Enterprise": "attack_native",
    "ATT_CK_Mobile": "attack_native",
    "ATT_CK_ICS": "attack_native",
    "ATT&CK": "attack_native",  # For detected framework
    "D3FEND": "d3fend_native",
    "SPARTA": "sparta_native",
    "ESA": "esa_native",
    "ESA_Shield": "esa_native",
}

# FRAMEWORK_PROMPT_MAP is loaded from worksheets.yaml above
# It maps canonical source_framework → prompt branch name (e.g., ATT_CK_Enterprise → ATT&CK)

# Thin frameworks that need URL enrichment for native QRAs
THIN_FRAMEWORKS = {"NIST", "ATT_CK_Enterprise", "ATT_CK_Mobile", "ATT_CK_ICS", "CAPEC", "D3FEND", "SPARTA", "ATT&CK"}


def _load_prompt(prompt_name: str) -> str:
    """Load prompt template from prompt-lab."""
    prompt_file = PROMPT_LAB_DIR / f"{prompt_name}.txt"
    if not prompt_file.exists():
        raise FileNotFoundError(f"Prompt template not found: {prompt_file}")
    return prompt_file.read_text()


def _load_prompt_pair(prompt_name: str, native: bool = False) -> tuple[str, str]:
    """Load system + user prompt pair from local prompts or prompt-lab.

    Returns (system_prompt, user_prompt_template).
    For native mode, checks prompts/native/ directory with clean naming.
    Otherwise checks local prompts/ dir first, then falls back to prompt-lab.
    """
    # For native prompts, use clean naming: prompts/native/{framework}_system.txt
    if native:
        system_file = NATIVE_PROMPTS_DIR / f"{prompt_name}_system.txt"
        user_file = NATIVE_PROMPTS_DIR / f"{prompt_name}_user.txt"
        if system_file.exists() and user_file.exists():
            return system_file.read_text(), user_file.read_text()
        raise FileNotFoundError(f"Native prompt template not found: {prompt_name} (expected {system_file})")

    # Check local prompts directory first (for non-native mode)
    for prompt_dir in [LOCAL_PROMPTS_DIR, PROMPT_LAB_DIR]:
        system_file = prompt_dir / f"{prompt_name}_system.txt"
        user_file = prompt_dir / f"{prompt_name}_user.txt"

        if system_file.exists() and user_file.exists():
            return system_file.read_text(), user_file.read_text()

        # Fallback to single-file format (backwards compat)
        single_file = prompt_dir / f"{prompt_name}.txt"
        if single_file.exists():
            return "", single_file.read_text()  # Empty system, full user

    raise FileNotFoundError(f"Prompt template not found: {prompt_name}")


def _get_memory_client() -> httpx.Client:
    """Get httpx client for memory daemon via Unix socket."""
    transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=30.0)


def _get_scillm_client() -> httpx.Client:
    """Get httpx client for scillm."""
    return httpx.Client(
        base_url="http://localhost:4001",
        headers={
            "Authorization": "Bearer sk-dev-proxy-123",
            "x-caller-skill": "create-qras",
        },
        timeout=300.0,  # Chutes can take 200s+ per call under load
    )


def _get_async_scillm_client() -> httpx.AsyncClient:
    """Get async httpx client for scillm batch processing."""
    return httpx.AsyncClient(
        base_url="http://localhost:4001",
        headers={
            "Authorization": "Bearer sk-dev-proxy-123",
            "x-caller-skill": "create-qras",
        },
        timeout=300.0,  # Chutes can take 200s+ per call under load
    )


def _get_provider_concurrency(model: str = "text") -> int:
    """Query proxy for the target provider's concurrency limit.

    Calls /v1/scillm/concurrency endpoint which handles model→provider mapping
    and returns effective_limit (accounting for adaptive backoff from 429s).
    Falls back to 4 if the query fails.
    """
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(
                f"http://localhost:4001/v1/scillm/concurrency?model={model}",
                headers={
                    "Authorization": "Bearer sk-dev-proxy-123",
                    "X-Caller-Skill": "create-qras",
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                return max(1, data.get("chunk_size", 4))
    except Exception:
        pass

    return 4  # Default fallback


def _detect_framework(control_id: str) -> str | None:
    """Detect framework from control ID pattern."""
    for framework, pattern in FRAMEWORK_PATTERNS.items():
        if pattern.match(control_id):
            return framework
    return None


def _generate_qra_key(qra_type: str, source_id: str, target_id: str | None = None) -> str:
    """Generate deterministic _key for QRA document."""
    if target_id:
        seed = f"{qra_type}:{source_id}:{target_id}"
    else:
        seed = f"{qra_type}:{source_id}"
    return f"qra_{hashlib.sha256(seed.encode()).hexdigest()[:16]}"


def _create_evidence_case(client: httpx.Client, question: str) -> dict[str, Any]:
    """Call /create-evidence-case daemon endpoint for crosswalk data."""
    try:
        resp = client.post("/create-evidence-case", json={"question": question})
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e), "glossary": [], "crosswalk_chains": []}


def _check_relationship_gates(evidence: dict) -> tuple[bool, str]:
    """Check deterministic gates for relationship QRAs."""
    entities = evidence.get("glossary", [])
    chains = evidence.get("crosswalk_chains", [])

    if not entities:
        return False, "no_entities"

    # Check for SPARTA target by framework field
    def is_sparta(e):
        framework = e.get("framework", "") or e.get("source_framework", "")
        return framework == "SPARTA"

    has_sparta = any(is_sparta(e) for e in entities)
    if not has_sparta:
        return False, "no_sparta_target"

    if not chains:
        return False, "no_crosswalk_chain"

    return True, "gates_passed"


def _fetch_control(client: httpx.Client, control_id: str) -> dict | None:
    """Fetch control document from sparta_controls."""
    try:
        resp = client.post(
            "/recall/by-keys",
            json={
                "keys": [control_id],
                "key_field": "control_id",
                "collection": "sparta_controls",
            },
        )
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
        return docs[0] if docs else None
    except Exception:
        return None


def _fetch_document(client: httpx.Client, doc_key: str, collection: str) -> dict | None:
    """Fetch document from a collection."""
    try:
        resp = client.post(
            "/recall/by-keys",
            json={"keys": [doc_key], "key_field": "_key", "collection": collection},
        )
        resp.raise_for_status()
        docs = resp.json().get("documents", [])
        return docs[0] if docs else None
    except Exception:
        return None


def _find_sparta_targets(client: httpx.Client, control_doc: dict) -> list[dict]:
    """Find SPARTA targets for a CWE control.

    Two lookup paths (after Step 08 fix, edges are canonical):
    1. DIRECT: CWE→SPARTA edges in sparta_relationships (from cwe_class_ids)
    2. 2-HOP: CWE.nist_control_ids → NIST→SPARTA edges (Heimdall mapping)
    """
    control_id = control_doc.get("control_id", "")

    try:
        sparta_targets = []
        seen_ids = set()

        # Path 1: Direct CWE→SPARTA edges (canonical after Step 08 fix)
        # Edges created from cwe_class_ids field on SPARTA Techniques
        resp = client.post(
            "/list",
            json={
                "collection": "sparta_relationships",
                "limit": 50,
                "filters": {
                    "source_control_id": control_id,
                    "target_framework": "SPARTA",
                },
            },
        )
        if resp.status_code == 200:
            data = resp.json()
            for edge in data.get("documents", []):
                target_id = edge.get("target_control_id", "")
                if target_id and target_id not in seen_ids:
                    target_doc = _fetch_control(client, target_id)
                    if target_doc:
                        seen_ids.add(target_id)
                        sparta_targets.append(target_doc)

        # Path 2: 2-hop via NIST (CWE.nist_control_ids → NIST→SPARTA edges)
        # Fallback for CWEs not in SPARTA's curated mapping but with Heimdall NIST links
        # Note: NIST→SPARTA edges use lowercase "sparta", CWE→SPARTA use uppercase "SPARTA"
        if not sparta_targets:
            nist_ids = control_doc.get("nist_control_ids") or []
            for nist_id in nist_ids[:5]:
                for tf_case in ["sparta", "SPARTA"]:  # Check both cases
                    resp = client.post(
                        "/list",
                        json={
                            "collection": "sparta_relationships",
                            "limit": 50,
                            "filters": {
                                "source_control_id": nist_id,
                                "target_framework": tf_case,
                            },
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        for edge in data.get("documents", []):
                            target_id = edge.get("target_control_id", "")
                            if target_id and target_id not in seen_ids:
                                target_doc = _fetch_control(client, target_id)
                                if target_doc:
                                    seen_ids.add(target_id)
                                    sparta_targets.append(target_doc)

        return sparta_targets[:10]
    except Exception:
        return []


# ------------------------------------------------------------------
# Native QRA Helpers (URL enrichment, control formatting)
# ------------------------------------------------------------------

def _load_url_content_for_control(client: httpx.Client, control_id: str) -> str:
    """Load supplementary URL content for a control from sparta_url_knowledge.

    Used by native mode to enrich thin framework descriptions with fetched web content.
    """
    try:
        # First get url_ids linked to this control via sparta_control_urls
        resp = client.post(
            "/list",
            json={
                "collection": "sparta_control_urls",
                "limit": 10,
                "filters": {"control_id": control_id},
            },
        )
        if resp.status_code != 200:
            return ""

        url_ids = [doc.get("url_id") for doc in resp.json().get("documents", []) if doc.get("url_id")]
        if not url_ids:
            return ""

        # Get URL content chunks
        resp = client.post(
            "/list",
            json={
                "collection": "sparta_url_knowledge",
                "limit": 10,
                "filters": {"url_id": {"$in": url_ids[:5]}},
            },
        )
        if resp.status_code != 200:
            return ""

        chunks = [doc.get("text", "") for doc in resp.json().get("documents", [])]
        content = "\n\n".join(c for c in chunks if c)
        return content[:20000]  # Cap at 20K chars
    except Exception:
        return ""


def _format_control_details_for_native(control: dict) -> str:
    """Format control details for native QRA prompt.

    Returns structured text with control ID, name, framework, description,
    and framework-specific fields.
    """
    lines = []

    # Core fields
    control_id = control.get("control_id", control.get("_key", "unknown"))
    lines.append(f"Technique ID: {control_id}")
    lines.append(f"Name: {control.get('name', control.get('title', ''))}")
    lines.append(f"Framework: {control.get('source_framework', '')}")

    if desc := control.get("description"):
        lines.append(f"\nDescription:\n{desc}")

    # ATT&CK-specific fields
    framework = control.get("source_framework", "")
    if framework.startswith("ATT_CK") or framework == "ATT&CK":
        if tactics := control.get("tactics"):
            lines.append(f"\nTactics: {', '.join(tactics) if isinstance(tactics, list) else tactics}")
        if platforms := control.get("platforms"):
            lines.append(f"Platforms: {', '.join(platforms) if isinstance(platforms, list) else platforms}")

    # CAPEC-specific fields
    if framework == "CAPEC":
        if likelihood := control.get("likelihood_of_attack"):
            lines.append(f"\nLikelihood of Attack: {likelihood}")
        if severity := control.get("typical_severity"):
            lines.append(f"Typical Severity: {severity}")
        if cwe_ids := control.get("related_cwe_ids"):
            cwe_list = cwe_ids[:10] if isinstance(cwe_ids, list) else [cwe_ids]
            lines.append(f"Related CWEs: {', '.join(cwe_list)}")

    # D3FEND-specific fields
    if framework == "D3FEND":
        if parent := control.get("parent_id"):
            lines.append(f"\nParent: {parent}")

    # NIST-specific fields
    if framework == "NIST":
        if parent := control.get("parent_id"):
            lines.append(f"\nParent Control: {parent}")

    return "\n".join(lines)


def _generate_native_qra(
    memory: httpx.Client,
    scillm: httpx.Client,
    control: dict,
    max_pairs: int = 6,
    dump_prompt: Path | None = None,
) -> list[dict] | dict:
    """Generate native QRAs for a control - extracts "what is X?" from framework source docs.

    Native QRAs answer questions like "What is T1595 Active Scanning according to MITRE ATT&CK?"
    grounded directly in the framework documentation, NOT in SPARTA context.

    Returns list of QRA dicts or error dict.
    """
    control_id = control.get("control_id", control.get("_key"))
    control_name = control.get("name", control.get("title", ""))
    framework = control.get("source_framework", "")

    # Determine which prompt to use based on framework
    # New clean naming: prompts/native/{framework}_system.txt
    FRAMEWORK_TO_PROMPT = {
        "ATT_CK_Enterprise": "attack",
        "ATT_CK_Mobile": "attack",
        "ATT_CK_ICS": "attack",
        "ATT&CK": "attack",
        "CWE": "cwe",
        "CAPEC": "capec",
        "D3FEND": "d3fend",
        "NIST": "nist",
        "SPARTA": "sparta",
        "ESA": "esa",
    }
    prompt_name = FRAMEWORK_TO_PROMPT.get(framework)
    if not prompt_name:
        # Try prefix matching for ATT&CK variants
        if framework.startswith("ATT_CK") or framework.startswith("ATT&CK"):
            prompt_name = "attack"
        elif framework.startswith("SV-") or "SPARTA" in framework.upper():
            prompt_name = "sparta"
        else:
            return {"error": f"No native prompt for framework: {framework}", "control_id": control_id}

    # Load system + user prompt pair from prompts/native/
    try:
        system_prompt, user_template = _load_prompt_pair(prompt_name, native=True)
    except FileNotFoundError as e:
        return {"error": str(e), "control_id": control_id}

    # Format control details
    control_details = _format_control_details_for_native(control)

    # Load supplementary URL content for thin frameworks
    supplementary_content = ""
    if framework in THIN_FRAMEWORKS:
        supplementary_content = _load_url_content_for_control(memory, control_id)
        if not supplementary_content:
            supplementary_content = "(No supplementary URL content available)"

    # Build user message with template substitution
    # Extract additional fields needed by framework-specific prompts
    parent_id = control.get("parent_id", control.get("parent", ""))
    family = control.get("family", control.get("control_family", ""))
    family_name = control.get("family_name", "")  # Explicit family name (for NIST)
    mind = control.get("mind", control.get("tactic", ""))  # D3FEND taxonomy field

    user_prompt = user_template.format(
        framework=framework,
        control_id=control_id,
        control_name=control_name,
        control_details=control_details,
        supplementary_content=supplementary_content,
        parent_id=parent_id,
        family=family,
        family_name=family_name,
        mind=mind,
    )

    # Dump prompt for human review if requested
    if dump_prompt:
        prompt_file = _dump_prompt_to_file(f"{system_prompt}\n\n---\n\n{user_prompt}", control_id, dump_prompt)
        return {"prompt_dumped": str(prompt_file), "control_id": control_id}

    # Call scillm
    try:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        resp = scillm.post(
            "/v1/chat/completions",
            json={
                "model": "text",  # Use stable model
                "messages": messages,
                "response_format": {"type": "json_object"},
                "temperature": 0.1,
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(content)

        # Check for skipped/abstained
        if result.get("skipped_reason"):
            return {
                "skipped": True,
                "skipped_reason": result.get("skipped_reason"),
                "control_id": control_id,
                "pair_count": 0,
            }

        pairs = result.get("pairs", [])
        if not pairs:
            return {"error": "no_pairs", "control_id": control_id}

        # Convert to storage format with native category
        run_id = f"skill_create_qras_native_{int(time.time())}"
        category = FRAMEWORK_TO_CATEGORY.get(framework, f"{framework.lower()}_native")
        qra_docs = []

        for idx, pair in enumerate(pairs, start=1):
            qra_key = _generate_qra_key("native", f"{control_id}_p{idx}")

            qra = {
                "_key": qra_key,
                "qra_id": qra_key,
                "run_id": run_id,
                "qra_type": "native",
                "category": category,  # e.g., "attack_native", "cwe_native"
                "source_framework": framework,
                "source_control_id": control_id,
                "sparta_linked": False,
                "created_at": int(time.time()),
                "generator": "skill:create-qras:native",
                "prompt_version": "control_to_qra_v6",
                "verdict": "SATISFIED",
                # Core QRA fields
                "question": pair.get("question", ""),
                "reasoning": pair.get("reasoning", ""),
                "answer": pair.get("answer", ""),
                "pair_type": pair.get("pair_type", "threat_description"),
                "evidence_quotes": pair.get("evidence_quotes", []),
                "confidence": pair.get("confidence", "medium"),
                "actionable_for": pair.get("actionable_for", "training"),
            }
            qra_docs.append(qra)

        return qra_docs

    except Exception as e:
        return {"error": str(e), "control_id": control_id}


# ------------------------------------------------------------------
# Quality Gates and Verification
# ------------------------------------------------------------------

def _verify_qra_grounding(qra: dict, source_text: str) -> tuple[bool, str, float]:
    """Verify evidence_quotes actually appear in source documents.

    Returns (passed, reason, grounding_score).
    """
    quotes = qra.get("evidence_quotes", [])
    if not quotes:
        return False, "no_evidence_quotes", 0.0

    grounded = 0
    for quote in quotes:
        quote_text = quote.get("quote", "")
        if not quote_text:
            continue
        # Fuzzy match - allow minor variations
        if quote_text in source_text or quote_text.lower() in source_text.lower():
            grounded += 1
        else:
            # Try substring match (at least 50 chars)
            if len(quote_text) > 50 and quote_text[:50] in source_text:
                grounded += 1

    score = grounded / len(quotes) if quotes else 0.0
    if score < 0.5:
        return False, "citations_not_grounded", score
    return True, "grounded", score


def _score_qra_quality(qra: dict, ground_truth: dict | None = None) -> dict:
    """Score QRA quality with detailed breakdown.

    Returns dict with scores and pass/fail status.
    """
    scores = {
        "has_question": bool(qra.get("question")),
        "has_reasoning": bool(qra.get("reasoning")),
        "has_answer": bool(qra.get("answer")),
        "has_evidence": bool(qra.get("evidence_quotes")),
        "reasoning_length": len(qra.get("reasoning", "").split()),
        "answer_length": len(qra.get("answer", "").split()),
        "evidence_count": len(qra.get("evidence_quotes", [])),
    }

    # Basic quality score (0-1)
    basic_score = sum([
        0.2 if scores["has_question"] else 0,
        0.2 if scores["has_reasoning"] and scores["reasoning_length"] > 10 else 0,
        0.2 if scores["has_answer"] and scores["answer_length"] > 5 else 0,
        0.2 if scores["evidence_count"] >= 2 else (0.1 if scores["evidence_count"] == 1 else 0),
        0.2 if qra.get("pair_type") else 0,
    ])
    scores["basic_score"] = round(basic_score, 2)

    # Ground truth validation (if provided)
    if ground_truth:
        question = qra.get("question", "").lower()
        reasoning = qra.get("reasoning", "").lower()
        answer = qra.get("answer", "").lower()

        q_hits = sum(1 for kw in ground_truth.get("expected_question_contains", []) if kw.lower() in question)
        r_hits = sum(1 for kw in ground_truth.get("expected_reasoning_contains", []) if kw.lower() in reasoning)
        a_hits = sum(1 for kw in ground_truth.get("expected_answer_contains", []) if kw.lower() in answer)

        q_total = len(ground_truth.get("expected_question_contains", []))
        r_total = len(ground_truth.get("expected_reasoning_contains", []))
        a_total = len(ground_truth.get("expected_answer_contains", []))

        scores["question_keyword_hits"] = f"{q_hits}/{q_total}"
        scores["reasoning_keyword_hits"] = f"{r_hits}/{r_total}"
        scores["answer_keyword_hits"] = f"{a_hits}/{a_total}"

        gt_score = (
            (q_hits / q_total if q_total else 1) * 0.33 +
            (r_hits / r_total if r_total else 1) * 0.33 +
            (a_hits / a_total if a_total else 1) * 0.34
        )
        scores["ground_truth_score"] = round(gt_score, 2)

    # Pass/fail
    scores["passed"] = scores["basic_score"] >= 0.6
    return scores


def _build_prompt_for_review(
    prompt_template: str,
    source_control: dict,
    target_control: dict,
    evidence: dict,
    max_pairs: int = 5,
) -> str:
    """Build the full prompt for human review (without calling LLM)."""
    source_id = source_control.get("control_id", source_control.get("_key"))
    source_framework = _detect_framework(source_id) or "UNKNOWN"
    target_id = target_control.get("control_id", target_control.get("_key"))

    # Build prior_qra_evidence summary
    prior_qras = evidence.get("prior_qra_evidence", [])
    prior_qra_summary = [
        {
            "question": q.get("question", "")[:200],
            "answer": q.get("answer", "")[:300],
            "citation_id": q.get("citation_id"),
        }
        for q in prior_qras[:5]
        if q.get("question") and q.get("answer")
    ]

    evidence_case = {
        "cwe_record" if source_framework == "CWE" else "capec_record": {
            "control_id": source_id,
            "description": source_control.get("description", source_control.get("text", "")),
            "extended_description": source_control.get("extended_description", ""),
        },
        "target_records": [{
            "control_id": target_id,
            # Use actual framework from document, not regex (IA-0001 is SPARTA, not NIST)
            "framework": target_control.get("source_framework") or _detect_framework(target_id) or "SPARTA",
            "description": target_control.get("description", target_control.get("text", "")),
        }],
        "glossary": evidence.get("glossary", []),
        "crosswalk_chains": evidence.get("crosswalk_chains", []),
        "prior_qra_evidence": prior_qra_summary,
    }

    return prompt_template.format(
        max_pairs=max_pairs,
        evidence_case_json=json.dumps(evidence_case, indent=2),
    )


def _dump_prompt_to_file(prompt: str, control_id: str, output_dir: Path) -> Path:
    """Save prompt to text file for human review in web chat."""
    output_dir.mkdir(parents=True, exist_ok=True)
    filename = f"prompt_{control_id}_{int(time.time())}.txt"
    filepath = output_dir / filename

    header = f"""# QRA Prompt for {control_id}
# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
#
# Copy this entire prompt into Claude.ai or ChatGPT to test manually.
# Compare output against ground truth fixtures.
#
# ============================================================

"""
    filepath.write_text(header + prompt)
    return filepath


# ------------------------------------------------------------------
# Two-Stage QRA Pipeline (Gate → Generate)
# ------------------------------------------------------------------

def _build_evidence_case_payload(
    source_control: dict,
    target_control: dict | None,
    evidence: dict,
    source_framework: str,
) -> dict:
    """Build the evidence_case payload for two-stage pipeline.

    If target_control is None, extracts ALL potential targets from the glossary
    (SPARTA, ATT&CK, CAPEC) for Stage A evaluation.
    """
    source_id = source_control.get("control_id", source_control.get("_key"))

    prior_qras = evidence.get("prior_qra_evidence", [])
    prior_qra_summary = [
        {
            "question": q.get("question", "")[:200],
            "answer": q.get("answer", "")[:300],
            "citation_id": q.get("citation_id"),
        }
        for q in prior_qras[:5]
        if q.get("question") and q.get("answer")
    ]

    # Build target_records from glossary if no explicit target
    if target_control is None:
        # Extract all potential targets from glossary (SPARTA, ATT&CK, CAPEC)
        # Exclude the source control and CWE/NIST (those are sources, not targets)
        target_frameworks = {"SPARTA", "MITRE_ATT&CK", "ATT&CK", "CAPEC"}
        target_records = []
        seen_ids = {source_id}

        for g in evidence.get("glossary", []):
            gid = g.get("id", "")
            gfw = g.get("framework", "")
            # Normalize ATT&CK variants
            if gfw == "ATT&CK":
                gfw = "MITRE_ATT&CK"
            if gfw in target_frameworks and gid not in seen_ids:
                seen_ids.add(gid)
                target_records.append({
                    "control_id": gid,
                    "framework": gfw,
                    "description": g.get("description", ""),
                })
    else:
        # Single explicit target
        target_id = target_control.get("control_id", target_control.get("_key"))
        target_records = [{
            "control_id": target_id,
            "framework": target_control.get("source_framework") or _detect_framework(target_id) or "SPARTA",
            "description": target_control.get("description", target_control.get("text", "")),
        }]

    return {
        "cwe_record" if source_framework == "CWE" else "capec_record": {
            "control_id": source_id,
            "description": source_control.get("description", source_control.get("text", "")),
            "extended_description": source_control.get("extended_description", ""),
        },
        "target_records": target_records,
        "glossary": evidence.get("glossary", []),
        "crosswalk_chains": evidence.get("crosswalk_chains", []),
        "prior_qra_evidence": prior_qra_summary,
    }


def _run_gate_stage(
    scillm: httpx.Client,
    evidence_case: dict,
    source_framework: str,
) -> dict:
    """Stage A: Run evidence gate to determine eligible pairs.

    Returns GateResult dict with eligible_pairs, rejected_pairs, diagnosis.
    """
    # Load gate prompts
    prompt_prefix = "cwe" if source_framework == "CWE" else "capec"
    system_prompt, user_template = _load_prompt_pair(f"{prompt_prefix}_gate")

    user_prompt = user_template.format(
        evidence_case_json=json.dumps(evidence_case, indent=2),
    )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    try:
        resp = scillm.post(
            "/v1/chat/completions",
            json={
                "model": "text",
                "messages": messages,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(content)

        # Validate with Pydantic if available
        if HAS_TWO_STAGE_SCHEMA:
            try:
                gate_result = validate_gate_response(result)
                return gate_result.model_dump()
            except Exception as e:
                return {"error": f"gate_validation_failed: {e}", "raw": result}

        return result
    except Exception as e:
        return {"error": str(e), "eligible_pairs": [], "diagnosis": {"overall_status": "error"}}


def _run_generate_stage(
    scillm: httpx.Client,
    eligible_pair: dict,
    evidence_case: dict,
    source_framework: str,
) -> dict:
    """Stage B: Generate QRA prose for a single pre-approved pair.

    Returns RelationshipQRAPair dict.
    """
    prompt_prefix = "cwe" if source_framework == "CWE" else "capec"
    system_prompt, user_template = _load_prompt_pair(f"{prompt_prefix}_generate")

    # Extract pair details for template (v2 schema fields)
    source_key = "cwe_id" if source_framework == "CWE" else "capec_id"
    source_id = eligible_pair.get(source_key, "")
    target_id = eligible_pair.get("target_id", "")
    target_framework = eligible_pair.get("target_framework", "SPARTA")
    primary_pair_type = eligible_pair.get("primary_pair_type", "relationship")
    bridge_strength = eligible_pair.get("bridge_strength", "adequate")
    bridge_type = eligible_pair.get("bridge_type", "terminal")
    duplicate_risk = eligible_pair.get("duplicate_risk", "none")
    cwe_quote = eligible_pair.get(f"{prompt_prefix}_quote", "")
    target_quote = eligible_pair.get("target_quote", "")
    bridge_quotes = eligible_pair.get("bridge_quotes", [])
    bridge_quotes_formatted = json.dumps(bridge_quotes)

    user_prompt = user_template.format(
        cwe_id=source_id if source_framework == "CWE" else "",
        capec_id=source_id if source_framework == "CAPEC" else "",
        target_id=target_id,
        target_framework=target_framework,
        primary_pair_type=primary_pair_type,
        bridge_strength=bridge_strength,
        bridge_type=bridge_type,
        duplicate_risk=duplicate_risk,
        cwe_quote=cwe_quote,
        capec_quote=cwe_quote,  # Reuse for CAPEC template compatibility
        target_quote=target_quote,
        bridge_quotes=bridge_quotes_formatted,
        evidence_case_json=json.dumps(evidence_case, indent=2),
    )

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    try:
        resp = scillm.post(
            "/v1/chat/completions",
            json={
                "model": "text",
                "messages": messages,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(content)

        # Validate with Pydantic if available
        if HAS_TWO_STAGE_SCHEMA:
            try:
                qra_result = validate_qra_response(result)
                # Return first pair if multiple (shouldn't happen in Stage B)
                if hasattr(qra_result, "pairs") and qra_result.pairs:
                    return qra_result.pairs[0].model_dump()
                return qra_result.model_dump()
            except Exception as e:
                return {"error": f"generate_validation_failed: {e}", "raw": result}

        return result
    except Exception as e:
        return {"error": str(e)}


def _generate_relationship_qra_two_stage(
    scillm: httpx.Client,
    source_control: dict,
    target_control: dict,
    evidence: dict,
    dump_prompt: Path | None = None,
) -> list[dict]:
    """Generate relationship QRA using two-stage pipeline.

    Stage A: Evidence gate → eligible_pairs[]
    Stage B: QRA generation for each eligible pair

    Returns list of QRA dicts (one per eligible pair).
    """
    source_id = source_control.get("control_id", source_control.get("_key"))
    target_id = target_control.get("control_id", target_control.get("_key"))
    source_framework = _detect_framework(source_id) or "CWE"

    # Build evidence case payload
    evidence_case = _build_evidence_case_payload(
        source_control, target_control, evidence, source_framework
    )

    # Dump prompt for manual review if requested
    if dump_prompt:
        prompt_prefix = "cwe" if source_framework == "CWE" else "capec"
        gate_sys, gate_user = _load_prompt_pair(f"{prompt_prefix}_gate")
        gen_sys, gen_user = _load_prompt_pair(f"{prompt_prefix}_generate")

        full_prompt = f"""# Two-Stage QRA Pipeline for {source_id}
# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}

# ============================================================
# STAGE A: EVIDENCE GATE
# ============================================================

## [SYSTEM MESSAGE]
{gate_sys}

## [USER MESSAGE]
{gate_user.format(evidence_case_json=json.dumps(evidence_case, indent=2))}

# ============================================================
# STAGE B: QRA GENERATION (template - fill in eligible_pair)
# ============================================================

## [SYSTEM MESSAGE]
{gen_sys}

## [USER MESSAGE]
{gen_user}
"""
        prompt_file = _dump_prompt_to_file(full_prompt, source_id, dump_prompt)
        return [{"prompt_dumped": str(prompt_file), "source_id": source_id, "target_id": target_id}]

    # Stage A: Run evidence gate
    gate_result = _run_gate_stage(scillm, evidence_case, source_framework)

    if gate_result.get("error"):
        return [{"error": gate_result["error"], "stage": "gate", "source_id": source_id}]

    eligible_pairs = gate_result.get("eligible_pairs", [])
    diagnosis = gate_result.get("diagnosis", {})

    if not eligible_pairs:
        return [{
            "error": "no_eligible_pairs",
            "stage": "gate",
            "source_id": source_id,
            "target_id": target_id,
            "diagnosis": diagnosis,
            "rejected_pairs": gate_result.get("rejected_pairs", []),
        }]

    # Stage B: Generate QRA for each eligible pair
    qras = []
    run_id = f"skill_create_qras_{int(time.time())}"

    for pair in eligible_pairs:
        qra = _run_generate_stage(scillm, pair, evidence_case, source_framework)

        if qra.get("error"):
            qras.append({"error": qra["error"], "stage": "generate", "pair": pair})
            continue

        # Add metadata - match existing sparta_qra schema
        pair_target_id = pair.get("target_id", target_id)
        qra_key = _generate_qra_key("relationship", source_id, pair_target_id)

        qra["_key"] = qra_key
        qra["qra_id"] = qra_key
        qra["run_id"] = run_id
        qra["qra_type"] = "relationship"
        qra["source_framework"] = source_framework
        qra["source_control_id"] = source_id
        qra["target_framework"] = pair.get("target_framework", "SPARTA")
        qra["target_control_id"] = pair_target_id
        qra["sparta_linked"] = qra["target_framework"] == "SPARTA"
        qra["evidence_case"] = evidence
        qra["crosswalk_chain"] = [
            c.get("path", []) for c in evidence.get("crosswalk_chains", [])[:1]
        ]
        qra["created_at"] = int(time.time())
        qra["generator"] = "skill:create-qras:two-stage"

        # Gate metadata from Stage A
        qra["gate_result"] = {
            "bridge_strength": pair.get("bridge_strength"),
            "grounding_rationale": pair.get("grounding_rationale"),
            "suggested_pair_types": pair.get("suggested_pair_types"),
        }

        # Quality verification
        source_text = (
            source_control.get("description", "") + " " +
            source_control.get("extended_description", "") + " " +
            target_control.get("description", "")
        )
        grounded, grounding_reason, grounding_score = _verify_qra_grounding(qra, source_text)
        quality_scores = _score_qra_quality(qra)

        qra["grounding_verified"] = grounded
        qra["grounding_score"] = grounding_score
        qra["quality_scores"] = quality_scores
        qra["verdict"] = "SATISFIED" if grounded and quality_scores["passed"] else "NEEDS_REVIEW"

        qras.append(qra)

    return qras


# ------------------------------------------------------------------
# QRA Generation Functions (Legacy Single-Stage)
# ------------------------------------------------------------------

def _generate_relationship_qra(
    scillm: httpx.Client,
    source_control: dict,
    target_control: dict,
    evidence: dict,
    max_pairs: int = 5,
    dump_prompt: Path | None = None,
) -> dict | None:
    """Generate relationship QRA using LLM with crosswalk evidence."""
    source_id = source_control.get("control_id", source_control.get("_key"))
    target_id = target_control.get("control_id", target_control.get("_key"))
    source_framework = _detect_framework(source_id) or "UNKNOWN"

    # Select prompt template based on source framework (two-message format: system + user)
    if source_framework == "CWE":
        system_prompt, user_template = _load_prompt_pair("cwe_relationship")
    elif source_framework == "CAPEC":
        system_prompt, user_template = _load_prompt_pair("capec_relationship")
    else:
        system_prompt, user_template = _load_prompt_pair("cwe_relationship")  # fallback

    # Build evidence case payload — includes glossary + prior_qra_evidence for retrieval augmentation
    prior_qras = evidence.get("prior_qra_evidence", [])
    # Limit to top 5 most relevant, keep only question/answer for prompt size
    prior_qra_summary = [
        {
            "question": q.get("question", "")[:200],
            "answer": q.get("answer", "")[:300],
            "citation_id": q.get("citation_id"),  # /create-evidence-case returns citation_id, not control_id
        }
        for q in prior_qras[:5]
        if q.get("question") and q.get("answer")
    ]

    evidence_case = {
        "cwe_record" if source_framework == "CWE" else "capec_record": {
            "control_id": source_id,
            "description": source_control.get("description", source_control.get("text", "")),
            "extended_description": source_control.get("extended_description", ""),
        },
        "target_records": [{
            "control_id": target_id,
            # Use actual framework from document, not regex (IA-0001 is SPARTA, not NIST)
            "framework": target_control.get("source_framework") or _detect_framework(target_id) or "SPARTA",
            "description": target_control.get("description", target_control.get("text", "")),
        }],
        "glossary": evidence.get("glossary", []),  # All resolved entities with descriptions
        "crosswalk_chains": evidence.get("crosswalk_chains", []),
        "prior_qra_evidence": prior_qra_summary,
    }

    user_prompt = user_template.format(
        max_pairs=max_pairs,
        evidence_case_json=json.dumps(evidence_case, indent=2),
    )

    # Build messages — two-message format (system + user) if system prompt exists
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    # Dump prompt for human review if requested
    if dump_prompt:
        full_prompt = f"[SYSTEM]\n{system_prompt}\n\n[USER]\n{user_prompt}" if system_prompt else user_prompt
        prompt_file = _dump_prompt_to_file(full_prompt, source_id, dump_prompt)
        # Return early if only dumping (no LLM call)
        return {"prompt_dumped": str(prompt_file), "source_id": source_id, "target_id": target_id}

    try:
        resp = scillm.post(
            "/v1/chat/completions",
            json={
                "model": "text",
                "messages": messages,
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(content)

        # Handle multiple pairs or single pair
        pairs = result.get("pairs", [result] if "question" in result else [])
        if not pairs:
            return {"error": result.get("reason", "no_pairs"), "source_id": source_id}

        # Take first pair for now (batch mode can iterate)
        qra = pairs[0]

        # Add metadata - match existing sparta_qra schema
        qra_key = _generate_qra_key("relationship", source_id, target_id)
        run_id = f"skill_create_qras_{int(time.time())}"
        qra["_key"] = qra_key
        qra["qra_id"] = qra_key  # Required for secondary unique index (run_id, qra_id)
        qra["run_id"] = run_id
        qra["qra_type"] = "relationship"
        qra["source_framework"] = source_framework
        qra["source_control_id"] = source_id  # Match existing schema field name
        # Use actual framework from document, not regex (IA-0001 is SPARTA, not NIST)
        qra["target_framework"] = target_control.get("source_framework") or _detect_framework(target_id) or "SPARTA"
        qra["target_control_id"] = target_id  # Match existing schema field name
        qra["sparta_linked"] = qra["target_framework"] == "SPARTA"
        # Store FULL evidence case - required for every QRA
        qra["evidence_case"] = evidence
        qra["crosswalk_chain"] = [
            c.get("path", []) for c in evidence.get("crosswalk_chains", [])[:1]
        ]
        qra["created_at"] = int(time.time())  # Match existing schema field name
        qra["generator"] = "skill:create-qras"

        # Quality verification
        source_text = (
            source_control.get("description", "") + " " +
            source_control.get("extended_description", "") + " " +
            target_control.get("description", "")
        )
        grounded, grounding_reason, grounding_score = _verify_qra_grounding(qra, source_text)
        quality_scores = _score_qra_quality(qra)

        qra["grounding_verified"] = grounded
        qra["grounding_score"] = grounding_score
        qra["quality_scores"] = quality_scores
        qra["verdict"] = "SATISFIED" if grounded and quality_scores["passed"] else "NEEDS_REVIEW"
        qra["gate_result"] = "gates_passed" if quality_scores["passed"] else grounding_reason

        return qra
    except Exception as e:
        return {"error": str(e), "source_id": source_id, "target_id": target_id}


async def _generate_relationship_qra_async(
    client: httpx.AsyncClient,
    source_control: dict,
    target_control: dict,
    evidence: dict,
    max_pairs: int = 5,
    batch_id: str | None = None,
    expected_total: int | None = None,
    chunk_index: int | None = None,
    chunk_total: int | None = None,
    item_index_in_chunk: int | None = None,
) -> dict | None:
    """Async version: Generate relationship QRA using LLM with crosswalk evidence.

    If batch_id is provided, uses scillm_metadata for automatic batch resume.
    """
    source_id = source_control.get("control_id", source_control.get("_key"))
    target_id = target_control.get("control_id", target_control.get("_key"))
    source_framework = _detect_framework(source_id) or "UNKNOWN"

    # Select prompt template based on source framework
    if source_framework == "CWE":
        prompt_template = _load_prompt("cwe_relationship")
    elif source_framework == "CAPEC":
        prompt_template = _load_prompt("capec_relationship")
    else:
        prompt_template = _load_prompt("cwe_relationship")

    # Build evidence case payload — includes prior_qra_evidence for retrieval augmentation
    prior_qras = evidence.get("prior_qra_evidence", [])
    prior_qra_summary = [
        {
            "question": q.get("question", "")[:200],
            "answer": q.get("answer", "")[:300],
            "control_id": q.get("control_id"),
        }
        for q in prior_qras[:5]
        if q.get("question") and q.get("answer")
    ]

    evidence_case = {
        "cwe_record" if source_framework == "CWE" else "capec_record": {
            "control_id": source_id,
            "description": source_control.get("description", source_control.get("text", "")),
            "extended_description": source_control.get("extended_description", ""),
        },
        "target_records": [{
            "control_id": target_id,
            "framework": target_control.get("source_framework") or _detect_framework(target_id) or "SPARTA",
            "description": target_control.get("description", target_control.get("text", "")),
        }],
        "crosswalk_chains": evidence.get("crosswalk_chains", []),
        "prior_qra_evidence": prior_qra_summary,
    }

    prompt = prompt_template.format(
        max_pairs=max_pairs,
        evidence_case_json=json.dumps(evidence_case, indent=2),
    )

    try:
        request_body = {
            "model": "text",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        }
        # Add scillm_metadata for automatic batch resume and chunk tracking
        if batch_id:
            metadata = {
                "batch_id": batch_id,
                "item_id": f"{source_id}->{target_id}",
            }
            if expected_total is not None:
                metadata["expected_total"] = expected_total
            if chunk_index is not None:
                metadata["chunk_index"] = chunk_index
            if chunk_total is not None:
                metadata["chunk_total"] = chunk_total
            if item_index_in_chunk is not None:
                metadata["item_index_in_chunk"] = item_index_in_chunk
            request_body["scillm_metadata"] = metadata

        resp = await client.post("/v1/chat/completions", json=request_body,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(content)

        pairs = result.get("pairs", [result] if "question" in result else [])
        if not pairs:
            return {"error": result.get("reason", "no_pairs"), "source_id": source_id}

        qra = pairs[0]

        # Add metadata - match existing sparta_qra schema
        qra_key = _generate_qra_key("relationship", source_id, target_id)
        run_id = f"skill_create_qras_{int(time.time())}"
        qra["_key"] = qra_key
        qra["qra_id"] = qra_key
        qra["run_id"] = run_id
        qra["qra_type"] = "relationship"
        qra["source_framework"] = source_framework
        qra["source_control_id"] = source_id
        qra["target_framework"] = target_control.get("source_framework") or _detect_framework(target_id) or "SPARTA"
        qra["target_control_id"] = target_id
        qra["sparta_linked"] = qra["target_framework"] == "SPARTA"
        qra["evidence_case"] = evidence
        qra["crosswalk_chain"] = [c.get("path", []) for c in evidence.get("crosswalk_chains", [])[:1]]
        qra["created_at"] = int(time.time())
        qra["generator"] = "skill:create-qras"

        # Quality verification
        source_text = (
            source_control.get("description", "") + " " +
            source_control.get("extended_description", "") + " " +
            target_control.get("description", "")
        )
        grounded, grounding_reason, grounding_score = _verify_qra_grounding(qra, source_text)
        quality_scores = _score_qra_quality(qra)

        qra["grounding_verified"] = grounded
        qra["grounding_score"] = grounding_score
        qra["quality_scores"] = quality_scores
        qra["verdict"] = "SATISFIED" if grounded and quality_scores["passed"] else "NEEDS_REVIEW"
        qra["gate_result"] = "gates_passed" if quality_scores["passed"] else grounding_reason

        return qra
    except Exception as e:
        return {"error": str(e), "source_id": source_id, "target_id": target_id}


async def _run_batch_relationship_qras(
    items: list[tuple[dict, dict, dict]],  # [(source_control, target_control, evidence), ...]
    chunk_size: int = 4,
    progress_callback=None,
    batch_id: str | None = None,
) -> list[dict]:
    """Run batch relationship QRA generation with chunked parallel processing.

    Uses chunked asyncio.gather per scillm SKILL.md pattern for 50+ items.
    If batch_id is provided, enables automatic resume via scillm_metadata.
    """
    all_results = []
    total = len(items)

    # Generate batch_id if not provided (enables automatic resume on retry)
    if batch_id is None:
        from datetime import datetime
        batch_id = f"create-qras-relationship-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    async with _get_async_scillm_client() as client:
        for chunk_start in range(0, total, chunk_size):
            chunk = items[chunk_start:chunk_start + chunk_size]
            chunk_num = chunk_start // chunk_size + 1
            total_chunks = (total + chunk_size - 1) // chunk_size

            if progress_callback:
                progress_callback(f"Chunk {chunk_num}/{total_chunks} ({chunk_start+1}-{min(chunk_start+chunk_size, total)}/{total})")

            # Process chunk with per-item retry (respects chunk_size concurrency)
            max_retries = 3

            async def process_with_retry(orig_idx: int, src: dict, tgt: dict, ev: dict):
                """Process single item with retries."""
                last_error = None
                for attempt in range(max_retries + 1):
                    if attempt > 0:
                        await asyncio.sleep(30 * attempt)  # 30s, 60s, 90s backoff
                    try:
                        result = await _generate_relationship_qra_async(
                            client, src, tgt, ev,
                            batch_id=batch_id,
                            expected_total=total,
                            chunk_index=chunk_num,
                            chunk_total=total_chunks,
                            item_index_in_chunk=orig_idx + 1,
                        )
                        return result  # Success
                    except Exception as e:
                        last_error = e
                        if progress_callback and attempt < max_retries:
                            progress_callback(f"  Retry {attempt+1}/{max_retries} for {src.get('control_id', src.get('_key'))}")
                # All retries exhausted
                return {
                    "error": f"Failed after {max_retries} retries: {last_error}",
                    "source_id": src.get("control_id", src.get("_key")),
                    "target_id": tgt.get("control_id", tgt.get("_key")),
                }

            # Run chunk in parallel (chunk_size already limits concurrency)
            chunk_tasks = [process_with_retry(i, src, tgt, ev) for i, (src, tgt, ev) in enumerate(chunk)]
            chunk_results = await asyncio.gather(*chunk_tasks)

            # Collect results
            for result in chunk_results:
                all_results.append(result)

    return all_results


def _build_independent_evidence_case(control: dict) -> dict:
    """Build evidence case for independent QRA (control is the evidence)."""
    control_id = control.get("control_id", control.get("_key"))
    return {
        "qra_type": "independent",
        "source_control": {
            "control_id": control_id,
            "framework": control.get("source_framework", _detect_framework(control_id) or "UNKNOWN"),
            "title": control.get("title", control.get("name", "")),
            "description": control.get("description", control.get("text", ""))[:2000],
        },
        "glossary": [{"id": control_id, "framework": control.get("source_framework", "")}],
        "crosswalk_chains": [],  # No crosswalk for independent QRAs
    }


def _format_cwe_record(control: dict) -> str:
    """Format CWE document into human-readable text for prompt injection."""
    control_id = control.get("control_id", control.get("_key"))
    parts = []

    # Basic info
    parts.append(f"CWE ID: {control_id}")
    if title := control.get("title", control.get("name")):
        parts.append(f"Title: {title}")

    # Description
    if desc := control.get("description"):
        parts.append(f"\nDESCRIPTION\n-----------\n{desc}")

    # Extended description
    if ext_desc := control.get("extended_description"):
        parts.append(f"\nEXTENDED DESCRIPTION\n--------------------\n{ext_desc}")

    # Likelihood of exploit
    if likelihood := control.get("likelihood_of_exploit"):
        parts.append(f"\nLIKELIHOOD OF EXPLOIT\n---------------------\n{likelihood}")

    # Common consequences
    if consequences := control.get("common_consequences"):
        parts.append("\nCOMMON CONSEQUENCES\n-------------------")
        if isinstance(consequences, list):
            for i, c in enumerate(consequences, 1):
                scope = c.get("scope", [])
                if isinstance(scope, list):
                    scope = ", ".join(scope)
                impact = c.get("impact", [])
                if isinstance(impact, list):
                    impact = ", ".join(impact)
                note = c.get("note", "")
                parts.append(f"{i}. Affects: {scope}")
                parts.append(f"   Impacts: {impact}")
                if note:
                    parts.append(f"   Detail: {note}")
        elif isinstance(consequences, str):
            parts.append(consequences)

    # Modes of introduction
    if modes := control.get("modes_of_introduction"):
        parts.append("\nMODES OF INTRODUCTION\n---------------------")
        if isinstance(modes, list):
            for m in modes:
                phase = m.get("phase", "Unknown")
                note = m.get("note", "")
                parts.append(f"- Phase: {phase}")
                if note:
                    parts.append(f"  Note: {note}")
        elif isinstance(modes, str):
            parts.append(modes)

    # Potential mitigations
    if mitigations := control.get("potential_mitigations"):
        parts.append("\nPOTENTIAL MITIGATIONS\n---------------------")
        if isinstance(mitigations, list):
            for i, m in enumerate(mitigations, 1):
                phase = m.get("phase", "")
                strategy = m.get("strategy", "")
                desc = m.get("description", m.get("note", ""))
                parts.append(f"{i}. Phase: {phase}")
                if strategy:
                    parts.append(f"   Strategy: {strategy}")
                if desc:
                    parts.append(f"   Action: {desc}")
        elif isinstance(mitigations, str):
            parts.append(mitigations)

    # Observed examples (CVEs)
    if examples := control.get("observed_examples"):
        parts.append("\nOBSERVED EXAMPLES (CVEs)\n------------------------")
        if isinstance(examples, list):
            for ex in examples[:5]:  # Limit to 5 examples
                ref = ex.get("reference", "")
                desc = ex.get("description", "")
                parts.append(f"- {ref}: {desc}")
        elif isinstance(examples, str):
            parts.append(examples)

    # Related attack patterns (CAPECs)
    if patterns := control.get("related_attack_patterns"):
        parts.append("\nRELATED ATTACK PATTERNS (CAPECs)\n--------------------------------")
        if isinstance(patterns, list):
            capec_list = ", ".join(str(p) for p in patterns[:10])
            parts.append(capec_list)
        elif isinstance(patterns, str):
            parts.append(patterns)

    return "\n".join(parts)


def _generate_independent_qra(
    scillm: httpx.Client,
    control: dict,
    max_pairs: int = 6,
    dump_prompt: Path | None = None,
) -> list[dict] | dict | None:
    """Generate independent QRAs for CWE/NIST/MITRE control (no crosswalk needed).

    Returns a list of QRA dicts (one per pair), or error dict, or None.
    New schema returns 1-6 pairs per control, not exactly 3.
    """
    control_id = control.get("control_id", control.get("_key"))
    # Prefer document's source_framework field; regex detection is fallback for unknown sources
    framework = control.get("source_framework") or _detect_framework(control_id) or "UNKNOWN"

    # Use CWE-specific template with rich fields, or generic independent template
    if framework == "CWE":
        prompt_template = _load_prompt("cwe_independent")
        cwe_record = _format_cwe_record(control)
        prompt = prompt_template.format(
            control_id=control_id,
            cwe_record=cwe_record,
        )
    else:
        # Generic independent template for NIST/SPARTA etc
        title = control.get("title", control.get("name", "Untitled"))
        description = control.get("description", control.get("text", "No description"))
        prompt_template = _load_prompt("independent")
        prompt = prompt_template.format(
            max_pairs=max_pairs,
            framework=framework,
            control_id=control_id,
            title=title,
            description=description,
        )

    # Dump prompt for human review if requested
    if dump_prompt:
        prompt_file = _dump_prompt_to_file(prompt, control_id, dump_prompt)
        return {"prompt_dumped": str(prompt_file), "control_id": control_id}

    try:
        resp = scillm.post(
            "/v1/chat/completions",
            json={
                "model": "text",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(content)

        # New schema: check abstained flag
        if result.get("abstained", False):
            return {
                "abstained": True,
                "abstain_reason_code": result.get("abstain_reason_code", "unknown"),
                "abstain_reason": result.get("abstain_reason", "Model abstained"),
                "control_id": control_id,
                "pair_count": 0,
            }

        # New schema: pairs array with 1-6 items
        pairs = result.get("pairs", [])
        if not pairs:
            # Fallback for old schema or empty response
            return {"error": result.get("reason", "no_pairs"), "control_id": control_id}

        # Optionally validate with Pydantic schema for CWE
        if framework == "CWE" and HAS_SCHEMA_VALIDATION:
            try:
                # Build record sections for grounding validation
                record_sections = _extract_cwe_sections(control)
                validated = validate_qra_payload(result, record_sections)
                pairs = [p.model_dump() for p in validated.pairs]
            except Exception as validation_error:
                # Log validation error but continue with unvalidated pairs
                print(f"Schema validation warning for {control_id}: {validation_error}")

        # Convert each pair to storage format
        run_id = f"skill_create_qras_{int(time.time())}"
        qra_docs = []

        for idx, pair in enumerate(pairs, start=1):
            # Generate unique key per pair
            qra_key = _generate_qra_key("independent", f"{control_id}_p{idx}")

            qra = {
                "_key": qra_key,
                "qra_id": qra_key,
                "run_id": run_id,
                "qra_type": "independent",
                "source_framework": framework,
                "source_control_id": control_id,
                "sparta_linked": False,
                "created_at": int(time.time()),
                "generator": "skill:create-qras",
                "verdict": "SATISFIED",
                # Core QRA fields from new schema
                "pair_id": pair.get("pair_id", f"{control_id}-QRA-{idx}"),
                "pair_type": pair.get("pair_type"),
                "actionable_for": pair.get("actionable_for", []),
                "question": pair.get("question"),
                "reasoning": pair.get("reasoning"),
                "answer": pair.get("answer"),
                "confidence": pair.get("confidence"),
                # New schema uses 'evidence' array, convert to evidence_quotes for compatibility
                "evidence_quotes": [
                    {"field": e.get("field"), "quote": e.get("quote")}
                    for e in pair.get("evidence", [])
                ],
                "evidence_case": _build_independent_evidence_case(control),
            }
            qra_docs.append(qra)

        return qra_docs

    except Exception as e:
        return {"error": str(e), "control_id": control_id}


def _extract_cwe_sections(control: dict) -> dict[str, str]:
    """Extract CWE sections for grounding validation.

    IMPORTANT: This must match the format used by _format_cwe_record so that
    quotes copied from the prompt will match during validation.
    """
    sections = {}

    if "description" in control:
        sections["description"] = control["description"]
    if "extended_description" in control:
        sections["extended_description"] = control["extended_description"]
    if "likelihood_of_exploit" in control:
        sections["likelihood_of_exploit"] = control["likelihood_of_exploit"]

    # Format common_consequences - include both raw note AND full formatted version
    # so quotes from either format will match
    if "common_consequences" in control:
        consequences = control["common_consequences"]
        if isinstance(consequences, list):
            parts = []
            for c in consequences:
                note = c.get("note", c.get("detail", ""))
                if note:
                    parts.append(note)
                # Also add scope/impact text that appears in prompt format
                scope = c.get("scope", [])
                if isinstance(scope, list):
                    scope = ", ".join(scope)
                impact = c.get("impact", [])
                if isinstance(impact, list):
                    impact = ", ".join(impact)
                if scope:
                    parts.append(f"Affects: {scope}")
                if impact:
                    parts.append(f"Impacts: {impact}")
            sections["common_consequences"] = "\n".join(parts)
        else:
            sections["common_consequences"] = str(consequences)

    # Format modes_of_introduction - include phase and note
    if "modes_of_introduction" in control:
        modes = control["modes_of_introduction"]
        if isinstance(modes, list):
            parts = []
            for m in modes:
                phase = m.get("phase", "")
                note = m.get("note", "")
                if phase:
                    parts.append(phase)
                    parts.append(f"Phase: {phase}")  # Include formatted version
                if note:
                    parts.append(note)
                    parts.append(f"Note: {note}")  # Include formatted version
            sections["modes_of_introduction"] = "\n".join(parts)
        else:
            sections["modes_of_introduction"] = str(modes)

    # Format potential_mitigations - include raw and formatted versions
    if "potential_mitigations" in control:
        mitigations = control["potential_mitigations"]
        if isinstance(mitigations, list):
            parts = []
            for m in mitigations:
                desc = m.get("description", m.get("action", ""))
                phase = m.get("phase", "")
                strategy = m.get("strategy", "")
                if desc:
                    parts.append(desc)  # Raw description
                    parts.append(f"Action: {desc}")  # Formatted version from prompt
                if phase:
                    parts.append(f"Phase: {phase}")
                if strategy:
                    parts.append(f"Strategy: {strategy}")
            sections["potential_mitigations"] = "\n".join(parts)
        else:
            sections["potential_mitigations"] = str(mitigations)

    # Format observed_examples - include both formats
    if "observed_examples" in control:
        examples = control["observed_examples"]
        if isinstance(examples, list):
            parts = []
            for e in examples:
                ref = e.get("reference", "")
                desc = e.get("description", "")
                if desc:
                    parts.append(desc)  # Raw description
                if ref and desc:
                    parts.append(f"{ref}: {desc}")  # With reference prefix
            sections["observed_examples"] = "\n".join(parts)
        else:
            sections["observed_examples"] = str(examples)

    return sections


async def _generate_independent_qra_async(
    client: httpx.AsyncClient,
    control: dict,
    max_pairs: int = 6,
    batch_id: str | None = None,
    expected_total: int | None = None,
    chunk_index: int | None = None,
    chunk_total: int | None = None,
    item_index_in_chunk: int | None = None,
) -> list[dict] | dict | None:
    """Async version: Generate independent QRAs for CWE/NIST/MITRE control.

    Returns a list of QRA dicts (one per pair), or error dict, or None.
    New schema returns 1-6 pairs per control, not exactly 3.

    If batch_id is provided, uses scillm_metadata for automatic batch resume.
    If expected_total is provided, includes it in metadata for dashboard progress.
    """
    control_id = control.get("control_id", control.get("_key"))
    # Prefer document's source_framework field; regex detection is fallback for unknown sources
    raw_framework = control.get("source_framework") or _detect_framework(control_id) or "UNKNOWN"
    # Normalize to prompt branch names (e.g., ATT_CK_Enterprise → ATT&CK) using worksheets.yaml
    framework = FRAMEWORK_PROMPT_MAP.get(raw_framework, raw_framework)

    # Use framework-specific templates or generic independent template
    system_prompt = ""  # Default: user-only request

    if framework == "CWE":
        # Native CWE prompts with system + user messages
        system_prompt, user_template = _load_prompt_pair("cwe", native=True)
        control_name = control.get("name", control.get("title", "Unknown"))
        control_details = control.get("description", "No description")
        parent_id = control.get("parent_id", "")
        prompt = user_template.format(
            control_id=control_id,
            control_name=control_name,
            control_details=control_details,
            parent_id=parent_id or "(None)",
        )
    elif framework == "ATT&CK":
        # Native ATT&CK prompts with system + user messages
        system_prompt, user_template = _load_prompt_pair("attack", native=True)
        control_name = control.get("question", control.get("title", control.get("name", "Unknown")))
        control_details = control.get("answer", control.get("description", "No description"))
        # For supplementary content, use extended_content if available
        supplementary = control.get("extended_content", control.get("supplementary", ""))
        prompt = user_template.format(
            framework=control.get("source_framework", "ATT_CK_Enterprise"),
            control_id=control_id,
            control_name=control_name,
            control_details=control_details,
            supplementary_content=supplementary or "(No supplementary content available)",
        )
    elif framework == "D3FEND":
        # Native D3FEND prompts with system + user messages
        system_prompt, user_template = _load_prompt_pair("d3fend", native=True)
        control_name = control.get("name", control.get("title", "Unknown"))
        control_details = control.get("description", "No description")
        parent_id = control.get("parent_id", "Unknown")
        mind_list = control.get("mind", [])
        mind = ", ".join(mind_list) if isinstance(mind_list, list) else str(mind_list)
        prompt = user_template.format(
            control_id=control_id,
            control_name=control_name,
            control_details=control_details,
            parent_id=parent_id,
            mind=mind or "Unknown",
        )
    elif framework == "CAPEC":
        # Native CAPEC prompts with system + user messages
        system_prompt, user_template = _load_prompt_pair("capec", native=True)
        control_name = control.get("name", control.get("title", "Unknown"))
        control_details = control.get("description", "No description")
        parent_id = control.get("parent_id", "")
        category_name = control.get("category_name", "")
        prompt = user_template.format(
            control_id=control_id,
            control_name=control_name,
            control_details=control_details,
            parent_id=parent_id or "(None)",
            category_name=category_name or "(Unknown)",
        )
    elif framework == "NIST":
        # Native NIST prompts with system + user messages
        system_prompt, user_template = _load_prompt_pair("nist", native=True)
        control_name = control.get("name", control.get("title", "Unknown"))
        control_details = control.get("description", "No description")
        family = control.get("family", control.get("control_family", ""))
        family_name = control.get("family_name", "")
        prompt = user_template.format(
            control_id=control_id,
            control_name=control_name,
            control_details=control_details,
            family=family or "(Unknown)",
            family_name=family_name or "(Unknown)",
        )
    elif framework == "SPARTA":
        # Native SPARTA prompts with system + user messages
        system_prompt, user_template = _load_prompt_pair("sparta", native=True)
        control_name = control.get("name", control.get("title", "Unknown"))
        control_details = control.get("description", "No description")
        parent_id = control.get("parent_id", "")
        family = control.get("family", control.get("control_family", ""))
        prompt = user_template.format(
            control_id=control_id,
            control_name=control_name,
            control_details=control_details,
            parent_id=parent_id or "(None)",
            family=family or "(Unknown)",
        )
    elif framework == "ESA":
        # Native ESA prompts with system + user messages
        system_prompt, user_template = _load_prompt_pair("esa", native=True)
        control_name = control.get("name", control.get("title", "Unknown"))
        control_details = control.get("description", "No description")
        parent_id = control.get("parent_id", "")
        prompt = user_template.format(
            control_id=control_id,
            control_name=control_name,
            control_details=control_details,
            parent_id=parent_id or "(None)",
        )
    else:
        # Generic independent template for unknown frameworks
        title = control.get("title", control.get("name", "Untitled"))
        description = control.get("description", control.get("text", "No description"))
        prompt_template = _load_prompt("independent")
        prompt = prompt_template.format(
            max_pairs=max_pairs,
            framework=framework,
            control_id=control_id,
            title=title,
            description=description,
        )

    try:
        # Build messages - include system prompt if present
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        request_body = {
            "model": "text",
            "messages": messages,
            "response_format": {"type": "json_object"},
        }
        # Add scillm_metadata for automatic batch resume and dashboard progress
        if batch_id:
            metadata = {
                "batch_id": batch_id,
                "item_id": control_id,
            }
            if expected_total:
                metadata["expected_total"] = expected_total
            # Chunk tracking for hierarchical dashboard display
            if chunk_index is not None:
                metadata["chunk_index"] = chunk_index
            if chunk_total is not None:
                metadata["chunk_total"] = chunk_total
            if item_index_in_chunk is not None:
                metadata["item_index_in_chunk"] = item_index_in_chunk
            request_body["scillm_metadata"] = metadata

        resp = await client.post("/v1/chat/completions", json=request_body)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(content)

        # New schema: check abstained flag
        if result.get("abstained", False):
            return {
                "abstained": True,
                "abstain_reason_code": result.get("abstain_reason_code", "unknown"),
                "abstain_reason": result.get("abstain_reason", "Model abstained"),
                "control_id": control_id,
                "pair_count": 0,
            }

        # New schema: pairs array with 1-6 items
        pairs = result.get("pairs", [])
        if not pairs:
            # Check both old and new schema field names
            reason = result.get("reason") or result.get("abstain_reason") or "no_pairs"
            return {"error": reason, "control_id": control_id, "raw_result": result}

        # Convert each pair to storage format
        run_id = f"skill_create_qras_{int(time.time())}"
        qra_docs = []

        # Determine qra_type based on framework using FRAMEWORK_TO_CATEGORY
        qra_type = FRAMEWORK_TO_CATEGORY.get(framework, f"{framework.lower()}_native")

        for idx, pair in enumerate(pairs, start=1):
            qra_key = _generate_qra_key(qra_type, f"{control_id}_p{idx}")

            # Handle evidence format (ATT&CK uses evidence_quotes, CWE uses evidence)
            raw_evidence = pair.get("evidence_quotes", pair.get("evidence", []))
            evidence_quotes = [
                {
                    "quote": e.get("quote", ""),
                    "relevance": e.get("relevance", e.get("field", "")),
                }
                for e in raw_evidence
            ]

            qra = {
                "_key": qra_key,
                "qra_id": qra_key,
                "run_id": run_id,
                "qra_type": qra_type,
                "category": qra_type,  # e.g., "attack_native", "cwe_native"
                "source_framework": framework,
                "source_control_id": control_id,
                "sparta_linked": False,
                "created_at": int(time.time()),
                "generator": "skill:create-qras",
                "verdict": "SATISFIED",
                "pair_id": pair.get("pair_id", f"{control_id}-QRA-{idx}"),
                "pair_type": pair.get("pair_type"),
                "actionable_for": pair.get("actionable_for", []),
                "question": pair.get("question"),
                "reasoning": pair.get("reasoning"),
                "answer": pair.get("answer"),
                "confidence": pair.get("confidence"),
                "evidence_quotes": evidence_quotes,
                "evidence_case": _build_independent_evidence_case(control),
            }
            qra_docs.append(qra)

        return qra_docs

    except Exception as e:
        return {"error": str(e), "control_id": control_id}


async def _run_batch_independent_qras(
    controls: list[dict],
    chunk_size: int = 4,
    progress_callback=None,
    batch_id: str | None = None,
    store_callback=None,  # Called with each QRA after chunk completes
) -> list[dict]:
    """Run batch independent QRA generation with chunked parallel processing.

    Uses chunked asyncio.gather per scillm SKILL.md pattern for 50+ items.
    If batch_id is provided, enables automatic resume via scillm_metadata.
    If store_callback is provided, stores QRAs immediately after each chunk (crash-safe).
    """
    all_results = []
    stored_count = 0
    total = len(controls)

    # Generate batch_id if not provided (enables automatic resume on retry)
    if batch_id is None:
        from datetime import datetime
        batch_id = f"create-qras-independent-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    async with _get_async_scillm_client() as client:
        for chunk_start in range(0, total, chunk_size):
            chunk = controls[chunk_start:chunk_start + chunk_size]
            chunk_num = chunk_start // chunk_size + 1
            total_chunks = (total + chunk_size - 1) // chunk_size

            if progress_callback:
                progress_callback(f"Chunk {chunk_num}/{total_chunks} ({chunk_start+1}-{min(chunk_start+chunk_size, total)}/{total})")

            # Simple parallel processing - no retry wrapper
            tasks = [
                _generate_independent_qra_async(
                    client, ctrl,
                    batch_id=batch_id,
                    expected_total=total,
                    chunk_index=chunk_num,
                    chunk_total=total_chunks,
                    item_index_in_chunk=i + 1,
                )
                for i, ctrl in enumerate(chunk)
            ]
            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

            # Collect and store results immediately (crash-safe)
            chunk_stored = 0
            for result in chunk_results:
                if isinstance(result, Exception):
                    all_results.append({"error": str(result)})
                elif isinstance(result, list):
                    for r in result:
                        all_results.append(r)
                        if store_callback and "error" not in r and not r.get("skipped"):
                            if store_callback(r):
                                chunk_stored += 1
                                stored_count += 1
                else:
                    all_results.append(result)
                    if store_callback and "error" not in result and not result.get("skipped"):
                        if store_callback(result):
                            chunk_stored += 1
                            stored_count += 1

            if progress_callback and store_callback:
                progress_callback(f"  Stored {chunk_stored} QRAs (total: {stored_count})")

    return all_results


def _build_standalone_evidence_case(doc: dict) -> dict:
    """Build evidence case for standalone QRA (document is the evidence)."""
    doc_key = doc.get("_key", "unknown")
    content = doc.get("content", doc.get("text", doc.get("extracted_text", "")))
    return {
        "qra_type": "standalone",
        "source_document": {
            "doc_key": doc_key,
            "url": doc.get("url", doc.get("source_url", "")),
            "title": doc.get("title", doc.get("name", "")),
            "content_preview": content[:2000] if content else "",
        },
        "glossary": [],
        "crosswalk_chains": [],
    }


def _generate_standalone_qra(
    scillm: httpx.Client,
    doc: dict,
    max_pairs: int = 5,
) -> dict | None:
    """Generate standalone QRA from URL knowledge document."""
    doc_key = doc.get("_key", "unknown")
    content = doc.get("content", doc.get("text", doc.get("extracted_text", "")))
    title = doc.get("title", doc.get("name", "Untitled"))
    url = doc.get("url", doc.get("source_url", ""))

    if not content or len(content) < 100:
        return {"error": "insufficient_content", "doc_key": doc_key}

    # Truncate very long content
    if len(content) > 8000:
        content = content[:8000] + "..."

    # Load prompt template from prompt-lab
    prompt_template = _load_prompt("standalone")
    prompt = prompt_template.format(
        max_pairs=max_pairs,
        title=title,
        url=url,
        content=content,
    )

    try:
        resp = scillm.post(
            "/v1/chat/completions",
            json={
                "model": "text",
                "messages": [{"role": "user", "content": prompt}],
                "response_format": {"type": "json_object"},
            },
        )
        resp.raise_for_status()
        response_content = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(response_content)

        # Handle multiple pairs or single pair
        pairs = result.get("pairs", [result] if "question" in result else [])
        if not pairs:
            return {"error": result.get("reason", "no_pairs"), "doc_key": doc_key}

        qra = pairs[0]

        # Add metadata - match existing sparta_qra schema
        qra_key = _generate_qra_key("standalone", doc_key)
        run_id = f"skill_create_qras_{int(time.time())}"
        qra["_key"] = qra_key
        qra["qra_id"] = qra_key  # Required for secondary unique index (run_id, qra_id)
        qra["run_id"] = run_id
        qra["qra_type"] = "standalone"
        qra["source_doc"] = doc_key
        qra["source_url"] = url
        qra["source_title"] = title
        qra["sparta_linked"] = False  # Standalone QRAs are portable by design
        # Store evidence case - document is the evidence
        qra["evidence_case"] = _build_standalone_evidence_case(doc)
        qra["created_at"] = int(time.time())  # Match existing schema field name
        qra["generator"] = "skill:create-qras"
        qra["verdict"] = "SATISFIED"

        return qra
    except Exception as e:
        return {"error": str(e), "doc_key": doc_key}


EMBEDDING_URL = "http://localhost:8602"


def _get_embedding(text: str) -> list[float] | None:
    """Get embedding vector from embedding service."""
    if not text.strip():
        return None
    try:
        resp = httpx.post(
            f"{EMBEDDING_URL}/embed/batch",
            json={"texts": [text]},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        # Service returns "embeddings" key (not "vectors")
        embeddings = data.get("embeddings", [])
        if embeddings and len(embeddings) > 0:
            return embeddings[0]
    except Exception as e:
        import sys
        print(f"EMBEDDING ERROR: {e}", file=sys.stderr)
    return None


def _store_qra(client: httpx.Client, qra: dict) -> bool:
    """Store QRA to sparta_qra collection with embedding."""
    import sys
    # Generate embedding from question + answer + reasoning
    embed_text = f"{qra.get('question', '')} {qra.get('answer', '')} {qra.get('reasoning', '')}".strip()
    print(f"DEBUG: Getting embedding for {qra.get('_key', 'unknown')} ({len(embed_text)} chars)", file=sys.stderr)
    embedding = _get_embedding(embed_text)
    print(f"DEBUG: Got embedding: {len(embedding) if embedding else None}", file=sys.stderr)
    if embedding:
        qra["embedding"] = embedding
        print(f"DEBUG: Added embedding to qra, now has {len(qra.get('embedding', []))} dims", file=sys.stderr)
    else:
        print(f"WARNING: No embedding for {qra.get('_key', 'unknown')}", file=sys.stderr)

    try:
        payload = {"document": qra, "collection": "sparta_qra"}
        print(f"DEBUG: Sending payload with embedding={len(qra.get('embedding', []))} dims, keys={list(qra.keys())}", file=sys.stderr)
        resp = client.post("/store", json=payload)
        if resp.status_code != 200:
            print(f"STORAGE FAILED {resp.status_code} for {qra.get('_key', 'unknown')}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"STORAGE ERROR for {qra.get('_key', 'unknown')}: {e}", file=sys.stderr)
        return False


@app.command()
def generate(
    control: str = typer.Option(None, "--control", help="Control ID (CWE-79, T1595, AC-17, etc.)"),
    source: str = typer.Option(None, "--source", help="Source control for relationship QRA"),
    target: str = typer.Option(None, "--target", help="Target control for relationship QRA"),
    doc: str = typer.Option(None, "--doc", help="Document key from sparta_url_knowledge"),
    collection: str = typer.Option(None, "--collection", help="Process all docs in collection"),
    text: str = typer.Option(None, "--text", help="Generate from raw text"),
    framework: str = typer.Option(None, "--framework", help="Batch generate for framework (e.g., ATT_CK_Enterprise)"),
    limit: int = typer.Option(50, "--limit", help="Limit batch size"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview without storing"),
    no_verify: bool = typer.Option(False, "--no-verify", help="Skip evidence verification"),
    mode: str = typer.Option(
        "auto",
        "--mode",
        help="""QRA generation mode:
        - native: 'What is X?' from framework source docs (category: attack_native, cwe_native, etc.)
        - relationship: 'How does X relate to SPARTA Y?' via crosswalk chains (needs SPARTA target)
        - standalone: From URL knowledge documents (no control ID needed)
        - auto: Detect mode from input (default - relationship for CWE/CAPEC, native for ATT&CK/NIST)
        """,
    ),
    independent: bool = typer.Option(False, "--independent", help="[DEPRECATED] Use --mode native instead"),
    store: bool = typer.Option(True, "--store", help="Store to sparta_qra"),
    output: str = typer.Option(None, "--output", help="Write results to JSON file"),
    dump_prompts: str = typer.Option(None, "--dump-prompts", help="Save prompts to dir for human review (no LLM call)"),
    two_stage: bool = typer.Option(False, "--two-stage", help="Use two-stage pipeline (gate → generate)"),
    batch_id: str = typer.Option(None, "--batch-id", help="Batch ID for resume (reuse same ID to skip completed items)"),
):
    """Generate QRA pairs from controls, documents, or text.

    MODES (use --mode to select explicitly):

      native       - Extract "What is X?" QRAs from framework source documentation.
                     Answers: "What is T1595 Active Scanning according to MITRE ATT&CK?"
                     Category: attack_native, cwe_native, nist_native, etc.
                     Best for: ATT&CK, CWE, NIST, CAPEC, D3FEND definitions.

      relationship - Generate "How does X relate to SPARTA Y?" QRAs via crosswalk chains.
                     Answers: "How does CWE-287 enable bypass of SPARTA control IA-0001?"
                     Category: sparta_context
                     Best for: CWE→SPARTA, CAPEC→SPARTA mappings with evidence chains.

      standalone   - Extract QRAs from URL knowledge documents (PDFs, fetched pages).
                     Answers: "What are satellite ground station security indicators?"
                     Category: standalone
                     Best for: Supplementary documents, research papers, guidelines.

      auto         - Detect mode from input (default):
                     - CWE/CAPEC → relationship (has crosswalk chains to SPARTA)
                     - ATT&CK/NIST/D3FEND → native (definitions from source docs)
                     - --doc → standalone
    """
    memory = _get_memory_client()

    # If dumping prompts, skip scillm initialization
    dump_prompt_dir = Path(dump_prompts) if dump_prompts else None
    if dump_prompt_dir:
        typer.echo(f"Dumping prompts to {dump_prompt_dir} (no LLM calls)")
        scillm = None
    else:
        scillm = _get_scillm_client()

    results = []

    # Handle deprecated --independent flag
    if independent:
        typer.echo("Warning: --independent is deprecated. Use --mode native instead.", err=True)
        if mode == "auto":
            mode = "native"

    if control:
        # Single control - detect type and generate appropriate QRA
        framework_type = _detect_framework(control)
        control_doc = _fetch_control(memory, control)
        if not control_doc:
            typer.echo(f"Control {control} not found in sparta_controls", err=True)
            raise typer.Exit(1)

        # Determine effective mode
        effective_mode = mode
        if mode == "auto":
            # Auto-detect: CWE/CAPEC → relationship, ATT&CK/NIST/D3FEND → native
            if framework_type in RELATIONSHIP_FRAMEWORKS:
                effective_mode = "relationship"
            else:
                effective_mode = "native"

        # Route to appropriate generator based on mode
        if effective_mode == "native":
            # Native mode: "What is X?" from framework source docs
            category = FRAMEWORK_TO_CATEGORY.get(
                control_doc.get("source_framework", framework_type or ""),
                f"{(framework_type or 'unknown').lower()}_native"
            )
            typer.echo(f"Generating native QRA for {control} (category: {category})...")

            qra_result = _generate_native_qra(memory, scillm, control_doc, dump_prompt=dump_prompt_dir)
            if isinstance(qra_result, list):
                results.extend(qra_result)
            else:
                results.append(qra_result)

        elif effective_mode == "relationship":
            # Relationship mode: "How does X relate to SPARTA Y?" via crosswalk
            typer.echo(f"Generating relationship QRA for {control}...")

            # Find SPARTA targets using edge traversal
            sparta_targets = _find_sparta_targets(memory, control_doc)
            if not sparta_targets:
                typer.echo(f"No SPARTA targets found for {control}", err=True)
                results.append({"control": control, "error": "no_sparta_target"})
            else:
                # Use top SPARTA target
                target_doc = sparta_targets[0]
                target_id = target_doc.get("control_id", "")
                typer.echo(f"Found SPARTA target: {target_id}")

                # Get evidence case for the relationship
                question = f"How does {control} relate to {target_id}?"
                evidence = _create_evidence_case(memory, question)

                gate_failed = False
                if not no_verify:
                    # Gate: check evidence has meaningful content
                    if not evidence.get("glossary") and not evidence.get("crosswalk_chains"):
                        typer.echo(f"Gate failed: no_evidence", err=True)
                        results.append({"control": control, "gate_result": "no_evidence", "skipped": True})
                        gate_failed = True

                if not gate_failed:
                    if two_stage:
                        qras = _generate_relationship_qra_two_stage(scillm, control_doc, target_doc, evidence, dump_prompt=dump_prompt_dir)
                        results.extend(qras)
                    else:
                        qra = _generate_relationship_qra(scillm, control_doc, target_doc, evidence, dump_prompt=dump_prompt_dir)
                        results.append(qra)

        else:
            typer.echo(f"Unknown mode: {effective_mode}. Use native, relationship, standalone, or auto.", err=True)
            raise typer.Exit(1)

    elif source and target:
        # Explicit source→target relationship QRA
        typer.echo(f"Generating relationship QRA: {source} → {target}...")
        source_doc = _fetch_control(memory, source)
        target_doc = _fetch_control(memory, target)

        if not source_doc or not target_doc:
            typer.echo("Source or target control not found", err=True)
            raise typer.Exit(1)

        # First check for direct edge in sparta_relationships (CWE→SPARTA etc.)
        source_framework = source_doc.get("source_framework", "")
        target_framework = target_doc.get("source_framework", "")
        direct_edge = None
        try:
            resp = memory.post("/list", json={
                "collection": "sparta_relationships",
                "limit": 1,
                "filters": {"source_control_id": source, "target_control_id": target}
            })
            if resp.status_code == 200:
                edges = resp.json().get("documents", [])
                if edges:
                    direct_edge = edges[0]
                    typer.echo(f"Found direct edge: {source} → {target} (method: {direct_edge.get('method')})")
        except Exception:
            pass

        if direct_edge:
            # Build evidence from direct edge - more reliable than /create-evidence-case
            evidence = {
                "glossary": [
                    {"id": source, "framework": source_framework},
                    {"id": target, "framework": target_framework},
                ],
                "crosswalk_chains": [{
                    "path": [source, target],
                    "source": "sparta_relationships",
                    "method": direct_edge.get("method", "direct")
                }]
            }
        else:
            # Fall back to /create-evidence-case for multi-hop chains
            question = f"How does {source} relate to {target}?"
            evidence = _create_evidence_case(memory, question)

        if two_stage:
            qras = _generate_relationship_qra_two_stage(scillm, source_doc, target_doc, evidence, dump_prompt=dump_prompt_dir)
            results.extend(qras)
        else:
            qra = _generate_relationship_qra(scillm, source_doc, target_doc, evidence, dump_prompt=dump_prompt_dir)
            results.append(qra)

    elif doc:
        # Standalone QRA from document
        typer.echo(f"Generating standalone QRA from document {doc}...")
        # Parse collection/key if format is collection/key
        if "/" in doc:
            coll, key = doc.split("/", 1)
        else:
            coll, key = "sparta_url_knowledge", doc

        doc_data = _fetch_document(memory, key, coll)
        if not doc_data:
            typer.echo(f"Document {doc} not found", err=True)
            raise typer.Exit(1)

        qra = _generate_standalone_qra(scillm, doc_data)
        results.append(qra)

    elif collection:
        # Batch standalone QRAs from collection
        typer.echo(f"Generating standalone QRAs from {collection} (limit: {limit})...")
        try:
            resp = memory.post(
                "/list",
                json={"collection": collection, "limit": limit},
            )
            resp.raise_for_status()
            docs = resp.json().get("documents", [])

            for i, doc_data in enumerate(docs):
                typer.echo(f"  [{i+1}/{len(docs)}] {doc_data.get('_key', 'unknown')}")
                qra = _generate_standalone_qra(scillm, doc_data)
                results.append(qra)
        except Exception as e:
            typer.echo(f"Failed to list collection: {e}", err=True)
            raise typer.Exit(1)

    elif framework:
        # Batch generate for framework
        typer.echo(f"Generating QRAs for framework {framework} (limit: {limit})...")
        framework_upper = framework.upper()

        try:
            # Use native mode if --mode native or deprecated --independent flag is set
            # mode == "native" overrides the default relationship behavior for CWE/CAPEC/ATT&CK
            use_relationship = framework_upper in RELATIONSHIP_FRAMEWORKS and mode != "native"
            if use_relationship:
                # For relationship frameworks: get controls that have SPARTA edges
                # Query sparta_relationships to find distinct source controls with SPARTA targets
                mappings = {}  # source_control_id -> first SPARTA target
                offset = 0
                while len(mappings) < limit:
                    resp = memory.post(
                        "/list",
                        json={
                            "collection": "sparta_relationships",
                            "limit": 500,
                            "offset": offset,
                            "filters": {"source_framework": framework_upper, "target_framework": "SPARTA"},
                        },
                    )
                    resp.raise_for_status()
                    docs = resp.json().get("documents", [])
                    if not docs:
                        break
                    for d in docs:
                        src_id = d.get("source_control_id")
                        if src_id and src_id not in mappings:
                            mappings[src_id] = d.get("target_control_id")
                    offset += 500

                typer.echo(f"Found {len(mappings)} {framework_upper}s with SPARTA mappings")

                # Pre-fetch all controls and build batch items
                typer.echo("Pre-fetching controls...")
                batch_items = []
                for ctrl_id, target_id in list(mappings.items())[:limit]:
                    ctrl = _fetch_control(memory, ctrl_id)
                    target_doc = _fetch_control(memory, target_id)

                    if not ctrl or not target_doc:
                        results.append({"control": ctrl_id, "gate_result": "control_not_found", "skipped": True})
                        continue

                    # Build minimal evidence from the edge
                    evidence = {
                        "glossary": [
                            {"id": ctrl_id, "framework": framework_upper},
                            {"id": target_id, "framework": "SPARTA"},
                        ],
                        "crosswalk_chains": [{
                            "path": [ctrl_id, target_id],
                            "source": "sparta_relationships",
                            "method": f"curated:{framework.lower()}_class_ids"
                        }]
                    }
                    batch_items.append((ctrl, target_doc, evidence))

                # Query dynamic concurrency from proxy
                chunk_size = _get_provider_concurrency("text")
                typer.echo(f"Processing {len(batch_items)} items in parallel (chunk_size={chunk_size})...")

                # Dump prompts mode - no LLM calls
                if dump_prompt_dir:
                    for ctrl, target_doc, evidence in batch_items:
                        qra = _generate_relationship_qra(scillm, ctrl, target_doc, evidence, dump_prompt=dump_prompt_dir)
                        results.append(qra)
                else:
                    # Run batch with chunked parallel processing
                    def progress(msg):
                        typer.echo(f"  {msg}")

                    batch_results = asyncio.run(_run_batch_relationship_qras(
                        batch_items,
                        chunk_size=chunk_size,
                        progress_callback=progress,
                        batch_id=batch_id,
                    ))
                    results.extend(batch_results)
            else:
                # For native frameworks: list controls with pagination (API max is 500)
                # Map user-friendly framework name to stored source_framework value
                source_framework_filter = FRAMEWORK_SOURCE_MAP.get(framework_upper, framework_upper)

                # SPARTA-specific: only include actionable control types
                # Exclude indicators (detection patterns) and requirements (free-form text)
                actionable_types = {"technique", "countermeasure", "tactic"}
                filter_by_type = framework_upper == "SPARTA"

                controls = []
                offset = 0
                page_size = 500
                while len(controls) < limit:
                    # Fetch more than needed if filtering, since some will be excluded
                    fetch_limit = page_size if filter_by_type else min(page_size, limit - len(controls))
                    resp = memory.post(
                        "/list",
                        json={
                            "collection": "sparta_controls",
                            "limit": fetch_limit,
                            "offset": offset,
                            "filters": {"source_framework": source_framework_filter},
                        },
                    )
                    resp.raise_for_status()
                    docs = resp.json().get("documents", [])
                    if not docs:
                        break
                    # Filter by control_type for SPARTA
                    if filter_by_type:
                        docs = [d for d in docs if d.get("control_type") in actionable_types]
                    controls.extend(docs)
                    offset += fetch_limit  # Advance by actual fetch size
                    typer.echo(f"  Fetched {len(controls)} {framework} controls...")
                # Trim to limit after filtering
                controls = controls[:limit]

                # Query dynamic concurrency from proxy
                chunk_size = _get_provider_concurrency("text")
                typer.echo(f"Processing {len(controls)} {framework} controls in parallel (chunk_size={chunk_size})...")

                def progress(msg):
                    typer.echo(f"  {msg}")

                # Store callback for immediate per-chunk storage
                def store_cb(qra):
                    return _store_qra(memory, qra) if store and not dry_run else False

                batch_results = asyncio.run(_run_batch_independent_qras(
                    controls,
                    chunk_size=chunk_size,
                    progress_callback=progress,
                    batch_id=batch_id,
                    store_callback=store_cb if store and not dry_run else None,
                ))
                results.extend(batch_results)

        except Exception as e:
            typer.echo(f"Failed: {e}", err=True)
            raise typer.Exit(1)

    elif text:
        # Corpus QRA from raw text
        typer.echo("Generating corpus QRA from text...")
        qra = _generate_standalone_qra(scillm, {"_key": "corpus_input", "content": text})
        results.append(qra)

    else:
        typer.echo("No input specified. Use --control, --doc, --collection, --framework, or --text", err=True)
        raise typer.Exit(1)

    # Store results (skip if already stored per-chunk via store_callback)
    if store and not dry_run:
        # Framework batches store per-chunk, others store here
        already_stored = any(r.get("_stored") for r in results)
        if not already_stored:
            stored = 0
            for qra in results:
                if "error" not in qra and not qra.get("skipped"):
                    if _store_qra(memory, qra):
                        stored += 1
            typer.echo(f"Stored {stored}/{len(results)} QRAs")

    # Output
    if output:
        Path(output).write_text(json.dumps(results, indent=2))
        typer.echo(f"Results written to {output}")
    else:
        typer.echo(json.dumps(results, indent=2))


@app.command("list-sources")
def list_sources():
    """List available QRA sources."""
    memory = _get_memory_client()

    sources = {
        "Relationship Frameworks (crosswalk)": ["CWE", "CAPEC", "ATT&CK"],
        "Independent Frameworks (direct)": ["NIST", "SPARTA"],
        "Document Collections": [],
    }

    # Count documents in relevant collections
    for coll in ["sparta_url_knowledge", "sparta_controls"]:
        try:
            resp = memory.post("/list", json={"collection": coll, "limit": 1})
            resp.raise_for_status()
            total = resp.json().get("total", 0)
            sources["Document Collections"].append(f"{coll}: {total} docs")
        except Exception:
            sources["Document Collections"].append(f"{coll}: unavailable")

    typer.echo(json.dumps(sources, indent=2))


@app.command()
def stats():
    """Show QRA generation statistics."""
    memory = _get_memory_client()

    try:
        resp = memory.post(
            "/list",
            json={"collection": "sparta_qra", "limit": 1},
        )
        resp.raise_for_status()
        total = resp.json().get("total", 0)

        typer.echo(f"Total QRAs in sparta_qra: {total}")

        # Sample to get type distribution
        resp = memory.post(
            "/list",
            json={"collection": "sparta_qra", "limit": 100},
        )
        docs = resp.json().get("documents", [])
        types = {}
        for d in docs:
            t = d.get("qra_type", "unknown")
            types[t] = types.get(t, 0) + 1

        if types:
            typer.echo("Sample type distribution:")
            for t, count in sorted(types.items()):
                typer.echo(f"  {t}: {count}")

    except Exception as e:
        typer.echo(f"Failed to get stats: {e}", err=True)


@app.command()
def preflight(
    fixture: str = typer.Option(
        "fixtures/cwe_relationship_ground_truth.json",
        "--fixture",
        help="Path to ground truth fixture file"
    ),
    output_dir: str = typer.Option(
        "./preflight_prompts",
        "--output-dir",
        help="Directory to dump prompts for human review"
    ),
    run_eval: bool = typer.Option(False, "--run-eval", help="Actually run LLM and score against ground truth"),
):
    """Pre-flight check: dump prompts for human review and optionally evaluate against ground truth.

    Usage:
      # Step 1: Dump prompts for human review (no LLM calls)
      python3 generator.py preflight --output-dir ./review_prompts

      # Step 2: Copy prompts to Claude.ai/ChatGPT and verify output quality

      # Step 3: Run automated evaluation (with LLM)
      python3 generator.py preflight --run-eval
    """
    memory = _get_memory_client()
    fixture_path = Path(__file__).parent / fixture

    if not fixture_path.exists():
        typer.echo(f"Fixture file not found: {fixture_path}", err=True)
        raise typer.Exit(1)

    ground_truth = json.loads(fixture_path.read_text())
    typer.echo(f"Loaded {len(ground_truth)} ground truth test cases")

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    results = []
    for i, case in enumerate(ground_truth):
        source_id = case["source_control"]
        target_id = case["target_control"]
        typer.echo(f"\n[{i+1}/{len(ground_truth)}] {case['name']}")

        # Fetch controls
        source_doc = _fetch_control(memory, source_id)
        target_doc = _fetch_control(memory, target_id)

        if not source_doc or not target_doc:
            typer.echo(f"  SKIP: Control not found ({source_id} or {target_id})")
            results.append({"case": case["id"], "status": "control_not_found"})
            continue

        # Get evidence case
        question = f"How does {source_id} relate to {target_id}?"
        evidence = _create_evidence_case(memory, question)

        # Build and dump prompt
        source_framework = _detect_framework(source_id) or "UNKNOWN"
        if source_framework == "CWE":
            prompt_template = _load_prompt("cwe_relationship")
        else:
            prompt_template = _load_prompt("cwe_relationship")

        prompt = _build_prompt_for_review(prompt_template, source_doc, target_doc, evidence)
        prompt_file = output_path / f"prompt_{case['id']}.txt"
        prompt_file.write_text(f"# Test Case: {case['name']}\n# Expected: {case.get('notes', '')}\n\n{prompt}")
        typer.echo(f"  Dumped: {prompt_file}")

        if run_eval:
            # Actually run LLM and score
            scillm = _get_scillm_client()
            qra = _generate_relationship_qra(scillm, source_doc, target_doc, evidence)

            if qra and "error" not in qra:
                scores = _score_qra_quality(qra, case)
                typer.echo(f"  Quality: basic={scores['basic_score']}, gt={scores.get('ground_truth_score', 'N/A')}")
                results.append({
                    "case": case["id"],
                    "status": "evaluated",
                    "scores": scores,
                    "qra": qra,
                })
            else:
                typer.echo(f"  FAIL: {qra.get('error', 'no output')}")
                results.append({"case": case["id"], "status": "generation_failed", "error": qra})
        else:
            results.append({"case": case["id"], "status": "prompt_dumped", "file": str(prompt_file)})

    # Summary
    typer.echo(f"\n{'='*50}")
    typer.echo(f"Preflight complete: {len(results)} cases processed")
    typer.echo(f"Prompts saved to: {output_path}")

    if run_eval:
        passed = sum(1 for r in results if r.get("scores", {}).get("passed"))
        typer.echo(f"Quality gate: {passed}/{len(results)} passed")

        # Write detailed results
        results_file = output_path / "eval_results.json"
        results_file.write_text(json.dumps(results, indent=2))
        typer.echo(f"Results: {results_file}")


if __name__ == "__main__":
    app()
