#!/usr/bin/env python3
"""
QRA Generator - Unified QRA generation from controls, documents, or text.

Three QRA types:
- relationship: CWE→SPARTA mappings via /create-evidence-case crosswalk chains
- standalone: From sparta_url_knowledge documents
- independent: NIST/MITRE controls without technique mapping (direct extraction)
"""
import asyncio
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import time
import importlib.util
from pathlib import Path
from typing import Any

import httpx
import typer
import yaml

SKILLS_ROOT = Path(__file__).resolve().parents[1]
if str(SKILLS_ROOT) not in sys.path:
    sys.path.insert(0, str(SKILLS_ROOT))


def _load_json_cleaner():
    """Prefer the project-local SPARTA JSON helper, then fall back to skill common."""
    candidates = []
    project_root_env = os.environ.get("SPARTA_PROJECT_ROOT")
    if project_root_env:
        candidates.append(Path(project_root_env) / ".agents" / "skills" / "json_utils.py")
    candidates.append(Path.cwd() / ".agents" / "skills" / "json_utils.py")
    candidates.append(Path("${HOME}/workspace/experiments/sparta/.agents/skills/json_utils.py"))
    for candidate in candidates:
        if not candidate.exists():
            continue
        spec = importlib.util.spec_from_file_location("_sparta_json_utils", candidate)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cleaner = getattr(module, "clean_json_string", None)
        if callable(cleaner):
            return cleaner
    try:
        from common.json_utils import clean_json_string
    except ImportError:
        return None
    return clean_json_string


_clean_llm_json = _load_json_cleaner()

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
CREATE_QRAS_MANIFEST_STATE_FILE = Path.home() / ".create_qras_manifest_state.json"
SCILLM_BATCH_CHUNK_SIZE = 8
SCILLM_QRA_MODEL_POOL = os.getenv("SCILLM_QRA_MODEL_POOL", "qra-deepseek-pool")

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
    "NVD": re.compile(r"^CVE-\d{4}-\d+$", re.I),
}

# Controls that need relationship QRAs (have crosswalk chains)
RELATIONSHIP_FRAMEWORKS = {"CWE", "CAPEC", "ATT&CK"}

# Controls that get independent QRAs (no crosswalk needed)
INDEPENDENT_FRAMEWORKS = {"NIST", "SPARTA"}

# Worksheets.yaml location (single source of truth for framework registry)
WORKSHEETS_YAML = Path("${HOME}/workspace/experiments/sparta/config/worksheets.yaml")

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
PROMPT_LAB_DIR = Path("${HOME}/workspace/experiments/scillm/.skills/prompt-lab/prompts/qra")
# Local prompts directory (for native mode prompts)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Atomically persist JSON payloads used for lightweight progress state."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2))
    os.replace(tmp, path)
LOCAL_PROMPTS_DIR = Path(__file__).parent / "prompts"
# Native prompts subdirectory (clean naming: prompts/native/{framework}_system.txt)
NATIVE_PROMPTS_DIR = LOCAL_PROMPTS_DIR / "native"


def _memory_base_url() -> str:
    """Use the Docker-backed /memory API, not legacy Unix-socket wrappers."""
    url = (
        os.getenv("MEMORY_SERVICE_URL")
        or os.getenv("MEMORY_API_URL")
        or os.getenv("MEMORY_SERVER_URL")
        or "http://127.0.0.1:8601"
    ).rstrip("/")
    if url.startswith(("unix://", "http+unix://")):
        return "http://127.0.0.1:8601"
    return url

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
    "NVD": "cve_native",
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
        candidate_dirs = [NATIVE_PROMPTS_DIR, NATIVE_PROMPTS_DIR / "sparta"]
        for prompt_dir in candidate_dirs:
            system_file = prompt_dir / f"{prompt_name}_system.txt"
            user_file = prompt_dir / f"{prompt_name}_user.txt"
            if system_file.exists() and user_file.exists():
                return system_file.read_text(), user_file.read_text()
        raise FileNotFoundError(
            f"Native prompt template not found: {prompt_name} "
            f"(checked {[str(p) for p in candidate_dirs]})"
        )

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
    """Get httpx client for the Docker-backed /memory API."""
    return httpx.Client(base_url=_memory_base_url(), timeout=30.0)


def _get_scillm_client() -> httpx.Client:
    """Get httpx client for scillm."""
    return httpx.Client(
        base_url="http://localhost:4001",
        headers={
            "Authorization": "Bearer sk-dev-proxy-123",
            "x-caller-skill": "create-qras",
        },
        timeout=900.0,  # Server-side QRA pool may queue and run up to 600s per lane
    )


def _get_async_scillm_client() -> httpx.AsyncClient:
    """Get async httpx client for scillm batch processing."""
    return httpx.AsyncClient(
        base_url="http://localhost:4001",
        headers={
            "Authorization": "Bearer sk-dev-proxy-123",
            "x-caller-skill": "create-qras",
        },
        timeout=900.0,  # Server-side QRA pool may queue and run up to 600s per lane
    )


def _first_json_value(text: str) -> dict[str, Any] | list[Any] | None:
    """Return the first complete JSON object/array in text."""
    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char not in "{[":
            continue
        try:
            value, _end = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(value, (dict, list)):
            return value
    return None


def _parse_json_content(content: str) -> dict[str, Any]:
    """Parse model JSON content through the shared skill JSON repair path."""
    text = content.strip()
    if not text:
        raise ValueError("empty_json_response")
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    parsed = _first_json_value(text)
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        return {"pairs": parsed}
    if _clean_llm_json is not None:
        parsed = _clean_llm_json(content, return_dict=True)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"pairs": parsed}
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        return {"pairs": parsed}
    raise ValueError(f"non_object_json_response:{parsed!r}")


def _is_transient_qra_error(error: Any) -> bool:
    """Return true for provider/proxy errors that are safe to retry."""
    text = str(error or "").lower()
    return any(
        marker in text
        for marker in (
            "429",
            "500",
            "502",
            "503",
            "504",
            "bad gateway",
            "internal server error",
            "service unavailable",
            "gateway timeout",
            "timeout",
            "timed out",
            "temporarily",
            "connection reset",
            "empty_json_response",
            "non_object_json_response",
        )
    )


def _get_async_memory_client() -> httpx.AsyncClient:
    """Get async httpx client for the Docker-backed /memory API."""
    return httpx.AsyncClient(base_url=_memory_base_url(), timeout=60.0)


async def _create_evidence_case_async(
    client: httpx.AsyncClient,
    question: str,
    source_id: str | None = None,
) -> dict[str, Any]:
    """Async: Call /create-evidence-case endpoint for crosswalk chains.

    Called per-result as LLM responses arrive via as_completed pattern.
    """
    try:
        payload = {"question": question}
        if source_id:
            payload["source_id"] = source_id
        resp = await client.post("/create-evidence-case", json=payload)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e), "glossary": [], "crosswalk_chains": []}


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


def _fetch_existing_control_ids(client: httpx.Client, control_ids: list[str]) -> set[str]:
    """Fetch the subset of control_ids that exist in sparta_controls via /memory."""
    if not control_ids:
        return set()

    resp = client.post(
        "/recall/by-keys",
        json={
            "keys": control_ids,
            "key_field": "control_id",
            "collection": "sparta_controls",
            "return_fields": ["control_id"],
        },
    )
    resp.raise_for_status()
    docs = resp.json().get("documents", [])
    return {doc.get("control_id") for doc in docs if doc.get("control_id")}


def _manifest_control_from_job(job: dict[str, Any]) -> dict[str, Any] | None:
    """Build a lightweight control document from a manifest row when possible."""
    identity = job.get("identity", {})
    source = job.get("source_record") or {}

    control_id = (
        identity.get("source_control_id")
        or identity.get("technique_id")
        or identity.get("countermeasure_id")
        or identity.get("tactic_id")
    )
    if not control_id:
        return None

    doc = {
        "control_id": control_id,
        "source_framework": job.get("source_framework") or _detect_framework(control_id) or "UNKNOWN",
    }
    doc.update(source)

    if "technique_name" in source and "name" not in doc:
        doc["name"] = source["technique_name"]
    if "countermeasure_name" in source and "name" not in doc:
        doc["name"] = source["countermeasure_name"]
    if "tactic_name" in source and "name" not in doc:
        doc["name"] = source["tactic_name"]
    if "description" not in doc or not doc.get("description"):
        doc["description"] = (
            source.get("technique_description")
            or source.get("countermeasure_description")
            or source.get("parent_tactic_description")
            or ""
        )

    return doc


def _normalized_job_source_id(job: dict[str, Any]) -> str | None:
    """Return the DB-resolvable source id for a manifest job.

    Some SPARTA countermeasure canonicals still invert fields:
    - identity.source_control_id contains prose like "Comms Link"
    - source_record.name contains the real CM code like "CM0029"
    Prefer the CM code for DB checks and v2 overlap matching.
    """
    identity = job.get("identity", {})
    source = job.get("source_record") or {}

    source_id = identity.get("source_control_id") or identity.get("technique_id")
    if (
        job.get("job_type") == "canonical"
        and source.get("control_type") == "countermeasure"
        and isinstance(source.get("name"), str)
        and FRAMEWORK_PATTERNS["SPARTA"].match(source["name"])
    ):
        return source["name"]
    return source_id


def _build_sparta_native_prompt(
    memory: httpx.Client | httpx.AsyncClient | None,
    control: dict,
) -> tuple[str, str]:
    """Build the native SPARTA prompt pair for a control."""
    control_id = control.get("control_id", control.get("_key", ""))
    control_type = control.get("control_type", "countermeasure")
    control_name = control.get("name", control.get("title", "Unknown"))
    control_description = control.get("description", "No description")
    parent_id = control.get("parent_id", "")

    if control_type == "tactic":
        system_prompt, user_template = _load_prompt_pair("tactic_canonical", native=True)
        user_prompt = user_template.format(
            control_id=control_id,
            control_name=control_name,
            control_description=control_description,
        )
        return system_prompt, user_prompt

    if control_type == "technique":
        parent_tactic = _fetch_control(memory, parent_id) if memory and parent_id else None
        system_prompt, user_template = _load_prompt_pair("technique_canonical", native=True)
        user_prompt = user_template.format(
            control_id=control_id,
            control_name=control_name,
            control_type=control_type,
            control_description=control_description,
            parent_id=parent_id or "",
            parent_tactic_id=(parent_tactic or {}).get("control_id", parent_id or ""),
            parent_tactic_name=(parent_tactic or {}).get("name", ""),
            parent_tactic_description=(parent_tactic or {}).get("description", ""),
        )
        return system_prompt, user_prompt

    system_prompt, user_template = _load_prompt_pair("countermeasure_canonical", native=True)
    user_prompt = user_template.format(
        control_id=control_id,
        control_name=control_name,
        control_type=control_type,
        control_description=control_description,
    )
    return system_prompt, user_prompt


def _build_manifest_control_lookup(jobs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Index manifest-provided control snapshots for execution fallback."""
    lookup: dict[str, dict[str, Any]] = {}
    for job in jobs:
        doc = _manifest_control_from_job(job)
        if not doc:
            continue

        control_id = doc.get("control_id")
        if control_id and control_id not in lookup:
            lookup[control_id] = doc

        # Some SPARTA countermeasure canonicals still carry the CM code in `name`
        # while `source_control_id` is prose. Alias the CM code too.
        name = doc.get("name")
        if (
            doc.get("control_type") == "countermeasure"
            and isinstance(name, str)
            and FRAMEWORK_PATTERNS["SPARTA"].match(name)
        ):
            lookup.setdefault(name, {**doc, "control_id": name})

    return lookup


def _resolve_manifest_control(
    client: httpx.Client,
    control_id: str,
    manifest_lookup: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Resolve a manifest control without letting sparse snapshots hide live data."""
    manifest_doc = manifest_lookup.get(control_id) if manifest_lookup else None
    live_doc = _fetch_control(client, control_id)

    if manifest_doc and live_doc:
        merged = dict(live_doc)
        for key, value in manifest_doc.items():
            if value in (None, "", [], {}):
                continue
            if (
                isinstance(value, str)
                and isinstance(live_doc.get(key), str)
                and key.endswith("description")
            ):
                manifest_text = value.strip()
                live_text = str(live_doc.get(key) or "").strip()
                if len(live_text) > len(manifest_text) and live_text.startswith(manifest_text):
                    continue
            merged[key] = value
        return merged

    return live_doc or manifest_doc


def _build_inline_relationship_control(
    control_id: str | None,
    name: str | None,
    control_type: str,
    description: str = "",
    source_framework: str = "SPARTA",
) -> dict[str, Any] | None:
    """Build a minimal control doc from a relationship row when no richer doc exists."""
    if not control_id or not name:
        return None
    return {
        "control_id": control_id,
        "name": name,
        "description": description,
        "control_type": control_type,
        "source_framework": source_framework,
    }


def _build_skipped_result(reason: str | None = None, **fields: Any) -> dict[str, Any]:
    """Normalize zero-pair model outcomes into explicit skips, not hard errors."""
    payload = dict(fields)
    payload["skipped"] = True
    payload["skipped_reason"] = reason or "no_pairs"
    payload["pair_count"] = 0
    return payload


def _summarize_existing_qras(
    client: httpx.Client,
    control_ids: list[str],
    progress_callback=None,
) -> tuple[dict[str, dict[str, int]], list[dict[str, str]]]:
    """Summarize legacy QRA totals per source control using one paged scan.

    Do not issue one filtered /list request per control. On the large legacy
    sparta_qra collection, those filters are slow enough to make review appear
    stalled and they violate the memory skill's batch-access contract.
    """
    summary: dict[str, dict[str, int]] = {}
    errors: list[dict[str, str]] = []
    if not control_ids:
        return summary, errors

    wanted = set(control_ids)
    offset = 0
    limit = 500
    scanned = 0
    try:
        while True:
            resp = client.post(
                "/list",
                json={
                    "collection": "sparta_qra",
                    "allow_full_scan": True,
                    "offset": offset,
                    "limit": limit,
                    "return_fields": ["source_control_id", "control_id"],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            docs = data.get("documents", [])
            if not docs:
                break

            for doc in docs:
                for field in ("source_control_id", "control_id"):
                    control_id = doc.get(field)
                    if control_id in wanted:
                        field_totals = summary.setdefault(control_id, {})
                        field_totals[field] = field_totals.get(field, 0) + 1

            scanned += len(docs)
            offset += len(docs)
            if progress_callback:
                progress_callback(f"Existing-QRA scan {scanned}/{data.get('total', scanned)}")
            if scanned >= data.get("total", 0):
                break
    except Exception as exc:
        errors.append({
            "field": "scan",
            "control_id": "*",
            "error": str(exc),
        })

    return summary, errors


def _summarize_existing_v2_jobs(
    client: httpx.Client,
    jobs: list[dict],
    progress_callback=None,
) -> list[dict[str, Any]]:
    """Summarize manifest jobs that already exist in the v2 target collections."""
    existing_jobs: list[dict[str, Any]] = []

    canonical_counts: dict[str, int] = {}
    relationship_counts: dict[str, int] = {}

    def fetch_all(collection: str, return_fields: list[str]) -> list[dict[str, Any]]:
        docs: list[dict[str, Any]] = []
        offset = 0
        limit = 500
        while True:
            resp = client.post(
                "/list",
                json={
                    "collection": collection,
                    "allow_full_scan": True,
                    "offset": offset,
                    "limit": limit,
                    "return_fields": return_fields,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            docs.extend(data.get("documents", []))
            offset += data.get("count", 0)
            if offset >= data.get("total", 0) or data.get("count", 0) == 0:
                break
        return docs

    canonical_docs = fetch_all("sparta_qra_canonical", ["source_control_id"])
    for idx, doc in enumerate(canonical_docs, start=1):
        control_id = doc.get("source_control_id")
        if control_id:
            canonical_counts[control_id] = canonical_counts.get(control_id, 0) + 1
        if progress_callback and idx % 100 == 0:
            progress_callback(f"Target-collection scan canonical {idx}/{len(canonical_docs)}")

    relationship_docs = fetch_all("sparta_qra_relationship", ["source_control_id", "target_control_id"])
    for idx, doc in enumerate(relationship_docs, start=1):
        source_id = doc.get("source_control_id")
        target_id = doc.get("target_control_id")
        if source_id and target_id:
            pair_key = f"{source_id}:{target_id}"
            relationship_counts[pair_key] = relationship_counts.get(pair_key, 0) + 1
        if progress_callback and idx % 100 == 0:
            progress_callback(f"Target-collection scan relationship {idx}/{len(relationship_docs)}")

    for job in jobs:
        identity = job.get("identity", {})
        if job.get("job_type") == "canonical":
            source_id = _normalized_job_source_id(job)
            existing_count = canonical_counts.get(source_id, 0)
            if existing_count:
                existing_jobs.append({
                    "job_id": job.get("job_id"),
                    "collection": "sparta_qra_canonical",
                    "existing_count": existing_count,
                    "source_control_id": source_id,
                })
        else:
            source_id = identity.get("technique_id")
            target_id = (
                identity.get("target_control_id")
                or identity.get("countermeasure_id")
                or identity.get("tactic_id")
            )
            pair_key = f"{source_id}:{target_id}"
            existing_count = relationship_counts.get(pair_key, 0)
            if existing_count:
                existing_jobs.append({
                    "job_id": job.get("job_id"),
                    "collection": "sparta_qra_relationship",
                    "existing_count": existing_count,
                    "source_control_id": source_id,
                    "target_control_id": target_id,
                })

    return existing_jobs


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

    try:
        if framework == "SPARTA":
            system_prompt, user_prompt = _build_sparta_native_prompt(memory, control)
        else:
            # Load system + user prompt pair from prompts/native/
            system_prompt, user_template = _load_prompt_pair(prompt_name, native=True)

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
    except FileNotFoundError as e:
        return {"error": str(e), "control_id": control_id}

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
                "evidence_case": _build_independent_evidence_case(control),
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
        return [_build_skipped_result(
            "no_eligible_pairs",
            stage="gate",
            source_id=source_id,
            target_id=target_id,
            diagnosis=diagnosis,
            rejected_pairs=gate_result.get("rejected_pairs", []),
        )]

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
            return _build_skipped_result(
                result.get("skipped_reason") or result.get("reason") or "no_pairs",
                source_id=source_id,
                target_id=target_id,
                raw_result=result,
            )

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
    prompt_kind: str | None = None,
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

    if prompt_kind and prompt_kind.startswith("sparta_"):
        if prompt_kind == "sparta_tactic_technique_relationship":
            system_prompt, user_template = _load_prompt_pair("tactic_technique_relationship", native=True)
            prompt = user_template.format(
                technique_id=source_id,
                technique_name=source_control.get("name", ""),
                technique_description=source_control.get("description", ""),
                parent_tactic_id=target_id,
                parent_tactic_name=target_control.get("name", ""),
                parent_tactic_description=target_control.get("description", ""),
            )
        elif prompt_kind == "sparta_technique_countermeasure_relationship":
            system_prompt, user_template = _load_prompt_pair("technique_countermeasure_relationship", native=True)
            prompt = user_template.format(
                technique_id=source_id,
                technique_name=source_control.get("name", ""),
                technique_description=source_control.get("description", ""),
                countermeasure_id=target_id,
                countermeasure_name=target_control.get("name", ""),
                countermeasure_description=target_control.get("description", ""),
                relationship_note=evidence.get("relationship_note", ""),
            )
        else:
            return {"error": f"unsupported_prompt_kind:{prompt_kind}", "source_id": source_id, "target_id": target_id}

        try:
            request_body = {
                "model": "text",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "response_format": {"type": "json_object"},
            }
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

            resp = await client.post("/v1/chat/completions", json=request_body)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            result = json.loads(content)

            pairs = result.get("pairs", [])
            if not pairs:
                return _build_skipped_result(
                    result.get("skipped_reason") or result.get("reason") or "no_pairs",
                    source_id=source_id,
                    target_id=target_id,
                    raw_result=result,
                )

            qra = pairs[0]
            qra_key = _generate_qra_key("relationship", source_id, target_id)
            run_id = f"skill_create_qras_{int(time.time())}"
            qra["_key"] = qra_key
            qra["qra_id"] = qra_key
            qra["run_id"] = run_id
            qra["qra_type"] = "relationship"
            qra["prompt_kind"] = prompt_kind
            qra["source_framework"] = "SPARTA"
            qra["source_control_id"] = source_id
            qra["target_framework"] = "SPARTA"
            qra["target_control_id"] = target_id
            qra["sparta_linked"] = True
            qra["evidence_case"] = evidence
            qra["crosswalk_chain"] = []
            qra["created_at"] = int(time.time())
            qra["generator"] = "skill:create-qras"

            source_text = (
                source_control.get("description", "") + " " +
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
            return _build_skipped_result(
                result.get("skipped_reason") or result.get("reason") or "no_pairs",
                source_id=source_id,
                target_id=target_id,
                raw_result=result,
            )

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
    items: list[tuple[dict, dict, dict, str | None]],  # [(source_control, target_control, evidence, prompt_kind), ...]
    chunk_size: int = 4,
    progress_callback=None,
    batch_id: str | None = None,
    store_callback=None,  # Called with each QRA as it completes (as_completed pattern)
    state_callback=None,
) -> list[dict]:
    """Run batch relationship QRA generation with as_completed pattern.

    Uses asyncio.as_completed to process each LLM result immediately:
    1. Fire chunk_size LLM calls in parallel
    2. As each completes, call /create-evidence-case to enrich
    3. Store immediately via store_callback (crash-safe)

    This maximizes throughput since evidence case enrichment runs while
    other LLM calls are still in flight.
    """
    all_results = []
    stored_count = 0
    total = len(items)

    # Generate batch_id if not provided (enables automatic resume on retry)
    if batch_id is None:
        from datetime import datetime
        batch_id = f"create-qras-relationship-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    async with _get_async_scillm_client() as scillm_client:
        async with _get_async_memory_client() as memory_client:
            for chunk_start in range(0, total, chunk_size):
                chunk = items[chunk_start:chunk_start + chunk_size]
                chunk_num = chunk_start // chunk_size + 1
                total_chunks = (total + chunk_size - 1) // chunk_size

                if progress_callback:
                    progress_callback(f"Chunk {chunk_num}/{total_chunks} ({chunk_start+1}-{min(chunk_start+chunk_size, total)}/{total})")
                if state_callback:
                    state_callback({
                        "event": "chunk_start",
                        "chunk_num": chunk_num,
                        "total_chunks": total_chunks,
                        "range_start": chunk_start + 1,
                        "range_end": min(chunk_start + chunk_size, total),
                        "total_jobs": total,
                    })

                # Process chunk with per-item retry (respects chunk_size concurrency)
                max_retries = 3

                async def process_with_retry(orig_idx: int, src: dict, tgt: dict, ev: dict, pk: str | None):
                    """Process single item with retries, returns (index, result)."""
                    last_error = None
                    for attempt in range(max_retries + 1):
                        if attempt > 0:
                            await asyncio.sleep(30 * attempt)  # 30s, 60s, 90s backoff
                        try:
                            result = await _generate_relationship_qra_async(
                                scillm_client, src, tgt, ev,
                                prompt_kind=pk,
                                batch_id=batch_id,
                                expected_total=total,
                                chunk_index=chunk_num,
                                chunk_total=total_chunks,
                                item_index_in_chunk=orig_idx + 1,
                            )
                            return (orig_idx, src, tgt, result)  # Success - include context for evidence case
                        except Exception as e:
                            last_error = e
                            if progress_callback and attempt < max_retries:
                                progress_callback(f"  Retry {attempt+1}/{max_retries} for {src.get('control_id', src.get('_key'))}")
                    # All retries exhausted
                    return (orig_idx, src, tgt, {
                        "error": f"Failed after {max_retries} retries: {last_error}",
                        "source_id": src.get("control_id", src.get("_key")),
                        "target_id": tgt.get("control_id", tgt.get("_key")),
                    })

                # Create tasks for chunk
                chunk_tasks = [
                    process_with_retry(i, src, tgt, ev, pk)
                    for i, (src, tgt, ev, pk) in enumerate(chunk)
                ]

                # Process results as they complete (as_completed pattern)
                chunk_stored = 0
                for coro in asyncio.as_completed(chunk_tasks):
                    orig_idx, src, tgt, result = await coro

                    # Skip errors
                    if isinstance(result, dict) and "error" in result:
                        all_results.append(result)
                        if state_callback:
                            state_callback({
                                "event": "job_complete",
                                "source_id": src.get("control_id", src.get("_key")),
                                "target_id": tgt.get("control_id", tgt.get("_key")),
                                "ok": False,
                                "skipped": False,
                                "qra_count": 0,
                                "stored_count": 0,
                                "error": result.get("error"),
                            })
                        continue

                    # Enrich with evidence case (runs while other LLM calls in flight)
                    item_qra_count = 0
                    item_stored_count = 0
                    item_skipped = False
                    if isinstance(result, list):
                        for qra in result:
                            if "error" not in qra:
                                if qra.get("skipped"):
                                    item_skipped = True
                                    all_results.append(qra)
                                    continue
                                question = qra.get("question", "")
                                source_id = src.get("control_id", src.get("_key"))
                                evidence = await _create_evidence_case_async(memory_client, question, source_id)
                                qra["evidence_case"] = evidence
                                qra["evidence_case_ts"] = int(time.time())

                            all_results.append(qra)
                            if qra.get("skipped"):
                                item_skipped = True
                            if "error" not in qra and not qra.get("skipped"):
                                item_qra_count += 1

                            # Store immediately (crash-safe)
                            if store_callback and "error" not in qra:
                                if store_callback(qra):
                                    chunk_stored += 1
                                    stored_count += 1
                                    item_stored_count += 1
                    else:
                        if result.get("skipped"):
                            item_skipped = True
                            all_results.append(result)
                        elif "error" not in result:
                            question = result.get("question", "")
                            source_id = src.get("control_id", src.get("_key"))
                            evidence = await _create_evidence_case_async(memory_client, question, source_id)
                            result["evidence_case"] = evidence
                            result["evidence_case_ts"] = int(time.time())
                            all_results.append(result)
                        else:
                            all_results.append(result)

                        if "error" not in result and not result.get("skipped"):
                            item_qra_count += 1

                        if store_callback and "error" not in result and not result.get("skipped"):
                            if store_callback(result):
                                chunk_stored += 1
                                stored_count += 1
                                item_stored_count += 1

                    if state_callback:
                        state_callback({
                            "event": "job_complete",
                            "source_id": src.get("control_id", src.get("_key")),
                            "target_id": tgt.get("control_id", tgt.get("_key")),
                            "ok": True,
                            "skipped": item_skipped and item_qra_count == 0,
                            "qra_count": item_qra_count,
                            "stored_count": item_stored_count,
                            "error": None,
                        })

                if progress_callback and store_callback:
                    progress_callback(f"  Stored {chunk_stored} QRAs (total: {stored_count})")

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


def _source_description_text(control: dict) -> str:
    """Return the source-backed description text used for deterministic native fallback."""
    text = str(control.get("description") or control.get("text") or "").strip()
    if not text or text.lower() in {"no description", "none", "n/a", "null"}:
        return ""
    return re.sub(r"\s+", " ", text)


def _first_sentence_or_clause(text: str, limit: int = 420) -> str:
    """Compact source text without inventing a summary."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    match = re.search(r"(?<=[.!?])\s+", text[:limit])
    if match:
        return text[: match.end()].strip()
    return text[:limit].rstrip() + "..."


def _build_deterministic_native_qras(
    control: dict,
    framework: str,
    *,
    raw_result: dict[str, Any] | None = None,
) -> list[dict] | None:
    """Build one source-description QRA when the LLM abstains on source-backed native content.

    This fallback is deliberately narrow: it only uses the exact control id,
    name/title, and description already present in the source control document.
    """
    control_id = str(control.get("control_id") or control.get("_key") or "").strip()
    description = _source_description_text(control)
    if not control_id or len(description) < 80:
        return None

    control_name = str(control.get("name") or control.get("title") or control_id).strip()
    qra_type = FRAMEWORK_TO_CATEGORY.get(framework, f"{framework.lower()}_native")
    qra_key = _generate_qra_key(qra_type, f"{control_id}_p1")
    framework_label = framework if framework != "ATT&CK" else "MITRE ATT&CK"
    excerpt = _first_sentence_or_clause(description, limit=700)

    raw_reason = ""
    if raw_result:
        raw_reason = str(raw_result.get("skipped_reason") or raw_result.get("reason") or "").strip()

    return [
        {
            "_key": qra_key,
            "qra_id": qra_key,
            "run_id": f"skill_create_qras_{int(time.time())}",
            "qra_type": qra_type,
            "category": qra_type,
            "source_framework": framework,
            "source_control_id": control_id,
            "sparta_linked": False,
            "created_at": int(time.time()),
            "generator": "skill:create-qras",
            "generation_method": "deterministic_native_source_description_fallback",
            "fallback_from_model_no_pairs": True,
            "fallback_reason": raw_reason,
            "verdict": "SATISFIED",
            "pair_id": f"{control_id}-QRA-1",
            "pair_type": "source_description_definition",
            "actionable_for": ["training"],
            "question": f"What is {control_id} {control_name} according to {framework_label}?",
            "reasoning": (
                f"The source control record for {control_id} contains a source-backed "
                "description, so the answer is derived directly from that description."
            ),
            "answer": f"{control_id} {control_name}: {excerpt}",
            "confidence": "medium",
            "evidence_quotes": [
                {
                    "quote": excerpt,
                    "relevance": "Source control description used verbatim or with safe truncation.",
                }
            ],
            "evidence_case": _build_independent_evidence_case(control),
        }
    ]


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
            return _build_skipped_result(
                result.get("skipped_reason") or result.get("reason") or "no_pairs",
                control_id=control_id,
                raw_result=result,
            )

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


def _build_independent_qra_messages(
    memory: httpx.Client | httpx.AsyncClient | None,
    control: dict,
    max_pairs: int = 6,
) -> tuple[str, str, list[dict]]:
    """Build the native independent-QRA prompt messages for one control."""
    control_id = control.get("control_id", control.get("_key"))
    raw_framework = control.get("source_framework") or _detect_framework(control_id) or "UNKNOWN"
    framework = FRAMEWORK_PROMPT_MAP.get(raw_framework, raw_framework)
    system_prompt = ""

    if framework == "CWE":
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
        system_prompt, user_template = _load_prompt_pair("attack", native=True)
        control_name = control.get("question", control.get("title", control.get("name", "Unknown")))
        control_details = control.get("answer", control.get("description", "No description"))
        supplementary = control.get("extended_content", control.get("supplementary", ""))
        prompt = user_template.format(
            framework=control.get("source_framework", "ATT_CK_Enterprise"),
            control_id=control_id,
            control_name=control_name,
            control_details=control_details,
            supplementary_content=supplementary or "(No supplementary content available)",
        )
    elif framework == "D3FEND":
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
        system_prompt, prompt = _build_sparta_native_prompt(memory, control)
    elif framework == "ESA":
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
    elif framework == "NVD":
        system_prompt, user_template = _load_prompt_pair("cve", native=True)
        control_name = control.get("name", control.get("title", "Unknown"))
        control_details = control.get("description", "No description")
        weaknesses = control.get("weaknesses", control.get("cwe_ids", []))
        if isinstance(weaknesses, list):
            weaknesses = json.dumps(weaknesses)
        vuln_status = control.get("vuln_status", control.get("status", "Unknown"))
        prompt = user_template.format(
            cve_id=control_id,
            control_name=control_name,
            control_details=control_details,
            weaknesses=weaknesses,
            vuln_status=vuln_status,
        )
    else:
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

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    return raw_framework, framework, messages


def _independent_qra_docs_from_result(
    control: dict,
    raw_framework: str,
    framework: str,
    result: dict,
) -> list[dict] | dict | None:
    """Convert one parsed independent-QRA model result into storage documents."""
    control_id = control.get("control_id", control.get("_key"))

    if result.get("abstained", False):
        return {
            "abstained": True,
            "abstain_reason_code": result.get("abstain_reason_code", "unknown"),
            "abstain_reason": result.get("abstain_reason", "Model abstained"),
            "control_id": control_id,
            "pair_count": 0,
        }

    pairs = result.get("pairs", [])
    if not pairs:
        fallback_qras = _build_deterministic_native_qras(control, framework, raw_result=result)
        if fallback_qras:
            return fallback_qras
        reason = result.get("reason") or result.get("abstain_reason") or "no_pairs"
        return _build_skipped_result(reason, control_id=control_id, raw_result=result)

    if framework == "CWE" and HAS_SCHEMA_VALIDATION:
        try:
            record_sections = _extract_cwe_sections(control)
            validated = validate_qra_payload(result, record_sections)
            pairs = [p.model_dump() for p in validated.pairs]
        except Exception as validation_error:
            print(f"Schema validation warning for {control_id}: {validation_error}")

    run_id = f"skill_create_qras_{int(time.time())}"
    qra_docs = []
    qra_type = FRAMEWORK_TO_CATEGORY.get(framework, f"{framework.lower()}_native")

    for idx, pair in enumerate(pairs, start=1):
        qra_key = _generate_qra_key(qra_type, f"{control_id}_p{idx}")
        raw_evidence = pair.get("evidence_quotes", pair.get("evidence", []))
        evidence_quotes = [
            {
                "quote": e.get("quote", ""),
                "relevance": e.get("relevance", e.get("field", "")),
            }
            for e in raw_evidence
        ]

        qra_docs.append({
            "_key": qra_key,
            "qra_id": qra_key,
            "run_id": run_id,
            "qra_type": qra_type,
            "category": qra_type,
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
        })

    return qra_docs


async def _iter_sse_events(response: httpx.Response):
    """Yield ``(event, data)`` pairs from a text/event-stream response."""
    event_name = "message"
    data_lines: list[str] = []
    async for line in response.aiter_lines():
        if line == "":
            if data_lines:
                raw_data = "\n".join(data_lines)
                yield event_name, json.loads(raw_data)
            event_name = "message"
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[len("event:"):].strip() or "message"
        elif line.startswith("data:"):
            data_lines.append(line[len("data:"):].strip())
    if data_lines:
        yield event_name, json.loads("\n".join(data_lines))


async def _post_scillm_batch_stream(
    client: httpx.AsyncClient,
    payload: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Submit a scillm model-pool batch and collect terminal item events.

    The stream endpoint emits heartbeats while items are running, which prevents
    the caller from mistaking a long provider call for a dead connection. The
    QRA runner still returns per-item results to the existing storage path.
    """
    results_by_id: dict[str, dict[str, Any]] = {}
    batch_done: dict[str, Any] | None = None
    async with client.stream("POST", "/v1/scillm/batch/completions/stream", json=payload) as response:
        response.raise_for_status()
        async for event_name, event_data in _iter_sse_events(response):
            if event_name == "item_completed":
                item_id = str(event_data.get("item_id") or event_data.get("id") or "")
                if item_id:
                    results_by_id[item_id] = event_data
            elif event_name == "item_failed":
                item_id = str(event_data.get("item_id") or event_data.get("id") or "")
                if item_id:
                    results_by_id[item_id] = event_data
            elif event_name == "item_replayed":
                item_id = str(event_data.get("item_id") or event_data.get("id") or "")
                if item_id:
                    replayed = dict(event_data)
                    if "ok" not in replayed:
                        replayed["ok"] = replayed.get("status") == "ok"
                    results_by_id[item_id] = replayed
            elif event_name == "batch_done":
                batch_done = event_data
            elif event_name in {"batch_started", "item_started", "heartbeat"}:
                continue

    if batch_done is None:
        raise RuntimeError("scillm batch stream ended without batch_done")
    return results_by_id


async def _generate_independent_qra_chunk_async(
    client: httpx.AsyncClient,
    memory: httpx.AsyncClient,
    controls: list[dict],
    max_pairs: int = 6,
    batch_id: str | None = None,
    chunk_index: int | None = None,
    attempt: int = 1,
) -> list[tuple[int, dict, list[dict] | dict | None]]:
    """Generate one real multi-item scillm pool batch for a chunk of controls."""
    parent_batch_id = batch_id or f"create-qras-independent-{int(time.time())}"
    attempt_suffix = f"-attempt-{attempt:02d}" if attempt > 1 else ""
    child_batch_id = (
        f"{parent_batch_id}-chunk-{chunk_index:04d}{attempt_suffix}"
        if chunk_index is not None
        else f"{parent_batch_id}{attempt_suffix}"
    )
    items = []
    metadata_by_id = {}

    for idx, control in enumerate(controls):
        control_id = str(control.get("control_id", control.get("_key")))
        try:
            raw_framework, framework, messages = _build_independent_qra_messages(memory, control, max_pairs=max_pairs)
        except Exception as e:
            metadata_by_id[control_id] = (idx, control, None, None)
            items.append({"id": control_id, "messages": [{"role": "user", "content": f"Prompt build failed: {e}"}]})
            continue
        metadata_by_id[control_id] = (idx, control, raw_framework, framework)
        items.append({"id": control_id, "messages": messages})

    try:
        results_by_id = await _post_scillm_batch_stream(
            client,
            {
                "model_pool": SCILLM_QRA_MODEL_POOL,
                "batch_id": child_batch_id,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "items": items,
            },
        )
    except Exception as e:
        return [
            (idx, control, {"error": str(e), "control_id": control.get("control_id", control.get("_key")), "batch_id": child_batch_id})
            for idx, control in enumerate(controls)
        ]
    output = []
    for item in items:
        item_id = str(item.get("id"))
        idx, control, raw_framework, framework = metadata_by_id[item_id]
        item_result = results_by_id.get(item_id)
        if not item_result:
            output.append((idx, control, {
                "error": "scillm batch returned no result for item",
                "control_id": control.get("control_id", control.get("_key")),
                "batch_id": child_batch_id,
            }))
            continue
        if not raw_framework or not framework:
            output.append((idx, control, {
                "error": "independent QRA prompt build failed",
                "control_id": control.get("control_id", control.get("_key")),
                "batch_id": child_batch_id,
            }))
            continue
        if not item_result.get("ok"):
            output.append((idx, control, {
                "error": item_result.get("error") or "scillm batch item failed",
                "control_id": control.get("control_id", control.get("_key")),
                "batch_id": child_batch_id,
                "provider": item_result.get("provider"),
                "model": item_result.get("model"),
            }))
            continue
        try:
            parsed = _parse_json_content(item_result.get("content") or "")
            output.append((idx, control, _independent_qra_docs_from_result(control, raw_framework, framework, parsed)))
        except Exception as e:
            output.append((idx, control, {
                "error": str(e),
                "control_id": control.get("control_id", control.get("_key")),
                "batch_id": child_batch_id,
                "provider": item_result.get("provider"),
                "model": item_result.get("model"),
            }))

    return output


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
        system_prompt, prompt = _build_sparta_native_prompt(client, control)
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
    elif framework == "NVD":
        # Native CVE/NVD prompts
        system_prompt, user_template = _load_prompt_pair("cve", native=True)
        control_name = control.get("name", control.get("title", "Unknown"))
        control_details = control.get("description", "No description")
        weaknesses = control.get("weaknesses", control.get("cwe_ids", []))
        if isinstance(weaknesses, list):
            weaknesses = json.dumps(weaknesses)
        vuln_status = control.get("vuln_status", control.get("status", "Unknown"))
        prompt = user_template.format(
            cve_id=control_id,
            control_name=control_name,
            control_details=control_details,
            weaknesses=weaknesses,
            vuln_status=vuln_status,
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

        item_id = str(control_id)
        safe_item_id = re.sub(r"[^A-Za-z0-9_.:-]+", "_", item_id)
        parent_batch_id = batch_id or f"create-qras-independent-{int(time.time())}"
        child_batch_id = (
            f"{parent_batch_id}-chunk-{chunk_index:04d}-{safe_item_id}"
            if chunk_index is not None
            else f"{parent_batch_id}-{safe_item_id}"
        )
        resp = await client.post(
            "/v1/scillm/batch/completions",
            json={
                "model_pool": SCILLM_QRA_MODEL_POOL,
                "batch_id": child_batch_id,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "items": [
                    {
                        "id": item_id,
                        "messages": messages,
                    }
                ],
            },
        )
        resp.raise_for_status()
        batch_data = resp.json()
        results = batch_data.get("results") or []
        if not results:
            return {"error": "scillm batch returned no results", "control_id": control_id, "batch_id": child_batch_id}
        item_result = results[0]
        if not item_result.get("ok"):
            return {
                "error": item_result.get("error") or "scillm batch item failed",
                "control_id": control_id,
                "batch_id": child_batch_id,
                "provider": item_result.get("provider"),
                "model": item_result.get("model"),
            }
        content = item_result.get("content") or ""
        result = _parse_json_content(content)

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
            fallback_qras = _build_deterministic_native_qras(control, framework, raw_result=result)
            if fallback_qras:
                return fallback_qras
            # Check both old and new schema field names
            reason = result.get("reason") or result.get("abstain_reason") or "no_pairs"
            return _build_skipped_result(reason, control_id=control_id, raw_result=result)

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
    store_callback=None,  # Called with each QRA as it completes (as_completed pattern)
    state_callback=None,
) -> list[dict]:
    """Run batch independent QRA generation through the scillm model pool.

    Each chunk is submitted as one multi-item /v1/scillm/batch/completions
    request. The pool scheduler assigns lanes by item index within that request,
    so one-item calls would bypass the intended Chutes/OpenCode Go distribution.
    Completed chunk items are enriched and stored immediately for crash safety.
    """
    all_results = []
    stored_count = 0
    total = len(controls)

    # Generate batch_id if not provided (enables automatic resume on retry)
    if batch_id is None:
        from datetime import datetime
        batch_id = f"create-qras-independent-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    async with _get_async_scillm_client() as scillm_client:
        async with _get_async_memory_client() as memory_client:
            for chunk_start in range(0, total, chunk_size):
                chunk = controls[chunk_start:chunk_start + chunk_size]
                chunk_num = chunk_start // chunk_size + 1
                total_chunks = (total + chunk_size - 1) // chunk_size

                if progress_callback:
                    progress_callback(f"Chunk {chunk_num}/{total_chunks} ({chunk_start+1}-{min(chunk_start+chunk_size, total)}/{total})")
                if state_callback:
                    state_callback({
                        "event": "chunk_start",
                        "chunk_num": chunk_num,
                        "total_chunks": total_chunks,
                        "range_start": chunk_start + 1,
                        "range_end": min(chunk_start + chunk_size, total),
                        "total_jobs": total,
                    })

                # Submit the whole chunk as one real scillm pool batch. The
                # pool distributes lanes by item index inside a batch, so
                # one-item calls defeat Chutes/OpenCode Go model pooling.
                chunk_results = []
                last_chunk_error = None
                for attempt in range(1, 4):
                    chunk_results = await _generate_independent_qra_chunk_async(
                        scillm_client,
                        memory_client,
                        chunk,
                        batch_id=batch_id,
                        chunk_index=chunk_num,
                        attempt=attempt,
                    )
                    retryable_errors = [
                        (ctrl, result.get("error"))
                        for _idx, ctrl, result in chunk_results
                        if isinstance(result, dict)
                        and result.get("error")
                        and _is_transient_qra_error(result.get("error"))
                    ]
                    hard_errors = [
                        (ctrl, result.get("error"))
                        for _idx, ctrl, result in chunk_results
                        if isinstance(result, dict)
                        and result.get("error")
                        and not _is_transient_qra_error(result.get("error"))
                    ]
                    if not retryable_errors or hard_errors or attempt == 3:
                        break
                    last_chunk_error = retryable_errors[0][1]
                    if state_callback:
                        for ctrl, error in retryable_errors:
                            state_callback({
                                "event": "job_retry",
                                "source_id": ctrl.get("control_id", ctrl.get("_key")),
                                "attempt": attempt,
                                "error": error,
                            })
                    await asyncio.sleep(10 * attempt)

                if not chunk_results:
                    raise RuntimeError(f"QRA generation failed for chunk {chunk_num}: {last_chunk_error or 'empty result'}")

                # Process results after the scillm pool batch returns.
                chunk_stored = 0
                for idx, ctrl, result in sorted(chunk_results, key=lambda item: item[0]):

                    # Handle exceptions
                    if isinstance(result, Exception):
                        all_results.append({"error": str(result)})
                        if state_callback:
                            state_callback({
                                "event": "job_complete",
                                "source_id": ctrl.get("control_id", ctrl.get("_key")),
                                "ok": False,
                                "skipped": False,
                                "qra_count": 0,
                                "stored_count": 0,
                                "error": str(result),
                            })
                        continue

                    # Process list of QRAs or single QRA
                    if isinstance(result, dict) and result.get("error"):
                        error = result.get("error")
                        all_results.append(result)
                        if state_callback:
                            state_callback({
                                "event": "job_complete",
                                "source_id": ctrl.get("control_id", ctrl.get("_key")),
                                "ok": False,
                                "skipped": False,
                                "qra_count": 0,
                                "stored_count": 0,
                                "error": error,
                            })
                        continue

                    qras_to_process = result if isinstance(result, list) else [result]
                    item_qra_count = 0
                    item_stored_count = 0
                    item_skipped = False

                    for qra in qras_to_process:
                        if "error" in qra or qra.get("skipped"):
                            all_results.append(qra)
                            if qra.get("skipped"):
                                item_skipped = True
                            continue

                        # Enrich with evidence case (runs while other LLM calls in flight)
                        question = qra.get("question", "")
                        source_id = ctrl.get("control_id", ctrl.get("_key"))
                        evidence = await _create_evidence_case_async(memory_client, question, source_id)
                        qra["evidence_case"] = evidence
                        qra["evidence_case_ts"] = int(time.time())

                        all_results.append(qra)
                        item_qra_count += 1

                        # Store immediately (crash-safe)
                        if store_callback:
                            if store_callback(qra):
                                chunk_stored += 1
                                stored_count += 1
                                item_stored_count += 1

                    if state_callback:
                        first_error = result.get("error") if isinstance(result, dict) else None
                        state_callback({
                            "event": "job_complete",
                            "source_id": ctrl.get("control_id", ctrl.get("_key")),
                            "ok": first_error is None,
                            "skipped": item_skipped and item_qra_count == 0,
                            "qra_count": item_qra_count,
                            "stored_count": item_stored_count,
                            "error": first_error,
                        })

                if progress_callback and store_callback:
                    progress_callback(f"  Stored {chunk_stored} QRAs (total: {stored_count})")

                chunk_errors = [
                    result
                    for _idx, _ctrl, result in chunk_results
                    if isinstance(result, dict) and result.get("error")
                ]
                if chunk_errors:
                    first_error = chunk_errors[0]
                    raise RuntimeError(
                        "QRA generation failed for "
                        f"{first_error.get('control_id', 'unknown')}: {first_error.get('error')}"
                    )

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
    max_pairs: int = 6,
) -> list[dict] | dict | None:
    """Generate standalone QRA from URL knowledge document.

    Uses doc2qra v3 prompts with:
    - Cybersecurity domain filtering
    - Source quality awareness
    - Relevance filtering (no author bio, citation metrics, etc.)

    Returns list of QRA dicts, or error dict, or None.
    """
    doc_key = doc.get("_key", "unknown")
    content = doc.get("content", doc.get("text", doc.get("extracted_text", "")))
    title = doc.get("title", doc.get("name", "Untitled"))
    url = doc.get("url", doc.get("source_url", ""))

    if not content or len(content) < 100:
        return {"error": "insufficient_content", "doc_key": doc_key}

    # Truncate very long content
    if len(content) > 8000:
        content = content[:8000] + "..."

    # Load system + user prompts from native directory (doc2qra v3)
    try:
        system_prompt, user_template = _load_prompt_pair("doc2qra", native=True)
    except FileNotFoundError:
        # Fallback to legacy prompt-lab if native prompts not found
        prompt_template = _load_prompt("standalone")
        prompt = prompt_template.format(
            max_pairs=max_pairs,
            title=title,
            url=url,
            content=content,
        )
        messages = [{"role": "user", "content": prompt}]
    else:
        # Use v3 system + user prompt structure
        user_prompt = user_template.format(
            max_pairs=max_pairs,
            title=title,
            url=url,
            content=content,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

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
        response_content = resp.json()["choices"][0]["message"]["content"]
        result = json.loads(response_content)

        # Handle v3 format (items) or legacy format (pairs)
        items = result.get("items", result.get("pairs", []))
        if not items:
            return {"error": result.get("reason", "no_pairs"), "doc_key": doc_key}

        # Track source quality from response
        source_quality = result.get("source_quality", "unknown")

        # Process all items (not just first one)
        qras = []
        run_id = f"skill_create_qras_{int(time.time())}"

        for i, item in enumerate(items):
            qra_key = _generate_qra_key("standalone", f"{doc_key}_{i}")
            item["_key"] = qra_key
            item["qra_id"] = qra_key
            item["run_id"] = run_id
            item["qra_type"] = "standalone"
            item["source_doc"] = doc_key
            item["source_url"] = url
            item["source_title"] = title
            item["source_quality"] = source_quality
            item["sparta_linked"] = False
            item["evidence_case"] = _build_standalone_evidence_case(doc)
            item["created_at"] = int(time.time())
            item["generator"] = "skill:create-qras:doc2qra_v3"
            item["prompt_version"] = "doc2qra_v3"
            item["verdict"] = "SATISFIED"
            qras.append(item)

        return qras if len(qras) > 1 else qras[0] if qras else None

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


def _json_safe_copy(value: Any, *, _seen: set[int] | None = None) -> Any:
    """Return a plain JSON-serializable copy, breaking cycles deterministically."""
    if _seen is None:
        _seen = set()

    if value is None or isinstance(value, (str, int, float, bool)):
        return value

    value_id = id(value)
    if value_id in _seen:
        return "[Circular]"

    if isinstance(value, dict):
        _seen.add(value_id)
        try:
            return {str(key): _json_safe_copy(item, _seen=_seen) for key, item in value.items()}
        finally:
            _seen.remove(value_id)

    if isinstance(value, (list, tuple, set, frozenset)):
        _seen.add(value_id)
        try:
            return [_json_safe_copy(item, _seen=_seen) for item in value]
        finally:
            _seen.remove(value_id)

    if isinstance(value, (_dt.datetime, _dt.date)):
        return value.isoformat()

    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")

    if hasattr(value, "model_dump"):
        try:
            return _json_safe_copy(value.model_dump(), _seen=_seen)
        except Exception:
            pass

    try:
        json.dumps(value)
        return value
    except Exception:
        return str(value)


def _store_qra(client: httpx.Client, qra: dict, collection: str | None = None) -> bool:
    """Store QRA to v2 collection through memory's canonical upsert path.

    v2 architecture:
    - sparta_qra_canonical: native QRAs (about one control)
    - sparta_qra_relationship: relationship QRAs (why two controls relate)
    """
    # Determine target collection from qra_type if not specified
    if collection is None:
        qra_type = qra.get("qra_type", "")
        if qra_type in ("relationship", "sparta_context"):
            collection = "sparta_qra_relationship"
        else:
            # native, independent, standalone → canonical
            collection = "sparta_qra_canonical"

    qra_doc = _json_safe_copy(qra)
    for field in ("_id", "_rev", "embedding", "embeddings", "embedding_multimodal"):
        qra_doc.pop(field, None)

    try:
        payload = {"documents": [qra_doc], "collection": collection, "skip_embedding": False}
        resp = client.post("/upsert", json=payload)
        if resp.status_code != 200:
            raise RuntimeError(
                f"/upsert {collection} failed for {qra.get('_key', 'unknown')} "
                f"({resp.status_code}): {resp.text[:1000]}"
            )
        resp.raise_for_status()
        result = resp.json()
        if result.get("errors"):
            raise RuntimeError(f"/upsert {collection} returned errors for {qra.get('_key', 'unknown')}: {result['errors']}")
        return True
    except Exception as e:
        raise RuntimeError(f"QRA storage failed for {qra.get('_key', 'unknown')} in {collection}: {e}") from e


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
                    batch_items.append((ctrl, target_doc, evidence, None))

                # Fixed per /scillm and /best-practices-scillm: never exceed 4 concurrent text calls
                chunk_size = SCILLM_BATCH_CHUNK_SIZE
                typer.echo(f"Processing {len(batch_items)} items in parallel (chunk_size={chunk_size})...")

                # Dump prompts mode - no LLM calls
                if dump_prompt_dir:
                    for ctrl, target_doc, evidence, _prompt_kind in batch_items:
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

                # Fixed per /scillm and /best-practices-scillm: never exceed 4 concurrent text calls
                chunk_size = SCILLM_BATCH_CHUNK_SIZE
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
    if store and not dry_run and not dump_prompt_dir:
        # Framework batches store per-chunk, others store here
        already_stored = any(r.get("_stored") for r in results)
        if not already_stored:
            stored = 0
            for qra in results:
                if "error" not in qra and not qra.get("skipped") and not qra.get("prompt_dumped"):
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
def manifest(
    manifest_path: str = typer.Argument(..., help="Path to execution manifest JSON"),
    limit: int = typer.Option(0, "--limit", "-l", help="Max jobs to process (0=all)"),
    prompt_kind: str = typer.Option("", "--prompt-kind", "-p", help="Filter by prompt_kind"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be processed"),
    skip_review: bool = typer.Option(False, "--skip-review", help="Skip review gate check"),
    batch_id: str = typer.Option("", "--batch-id", help="Stable scillm batch id for replay/resume"),
):
    """Execute QRA generation from a pre-built manifest.

    Uses the existing batch functions with proper timeout (300s), as_completed pattern,
    and evidence case enrichment.

    Example:
        python generator.py manifest sparta_v2_batch_manifest.json --limit 50
    """
    from pathlib import Path as P
    manifest_file = P(manifest_path)
    if not manifest_file.exists():
        typer.echo(f"Manifest not found: {manifest_path}", err=True)
        raise typer.Exit(1)

    with open(manifest_file) as f:
        manifest_data = json.load(f)

    if not batch_id:
        safe_stem = re.sub(r"[^A-Za-z0-9_.:-]+", "-", manifest_file.stem).strip("-")
        batch_id = f"create-qras-manifest-{safe_stem}"

    # Check review gate
    review_path = manifest_file.with_name(manifest_file.stem.replace("_manifest", "_review") + ".json")
    if review_path.exists() and not skip_review:
        with open(review_path) as f:
            review = json.load(f)
        verdict = review.get("verdict", {})
        status = verdict.get("status", "UNKNOWN")
        if status == "BLOCKED":
            typer.echo(f"[BLOCKED] Review verdict: {status}")
            typer.echo(f"  Reason: {verdict.get('reason', '')}")
            raise typer.Exit(1)
        elif status == "CANARY_ONLY":
            typer.echo(f"[WARNING] Review has {len(review.get('warnings', []))} warnings")
            typer.echo("  Proceed with staged canaries only until warnings are cleared.")
        elif status == "FULL_RUN_OK":
            typer.echo(f"[READY] Review verdict: {status}")
        else:
            typer.echo(f"[BLOCKED] Unknown review verdict: {status}", err=True)
            raise typer.Exit(1)
    elif not review_path.exists() and not skip_review:
        typer.echo(f"[BLOCKED] No review file found: {review_path}", err=True)
        typer.echo("Run './run.sh review <manifest>' first or pass --skip-review explicitly.", err=True)
        raise typer.Exit(1)

    all_manifest_jobs = manifest_data.get("jobs", [])
    jobs = all_manifest_jobs

    # Filter by prompt_kind
    if prompt_kind:
        jobs = [j for j in jobs if j.get("prompt_kind") == prompt_kind]

    # Apply limit
    if limit > 0:
        jobs = jobs[:limit]

    # Group by job type
    canonical_jobs = [j for j in jobs if j.get("job_type") == "canonical"]
    relationship_jobs = [j for j in jobs if j.get("job_type") == "relationship"]

    typer.echo(f"\nManifest: {manifest_path}")
    typer.echo(f"  Total jobs: {len(jobs)}")
    typer.echo(f"  Canonical: {len(canonical_jobs)}")
    typer.echo(f"  Relationship: {len(relationship_jobs)}")

    if dry_run:
        typer.echo("\n[DRY RUN] Would process above jobs using existing batch functions")
        return

    # Use existing batch functions
    memory = _get_memory_client()
    total_qras = 0
    errors = 0
    manifest_control_lookup = _build_manifest_control_lookup(all_manifest_jobs)
    started_at = int(time.time())

    state: dict[str, Any] = {
        "name": "create-qras-manifest",
        "status": "running",
        "manifest_path": str(manifest_file.resolve()),
        "review_status": (
            review.get("verdict", {}).get("status", "SKIPPED")
            if review_path.exists() and not skip_review else "SKIPPED"
        ),
        "started_at": started_at,
        "updated_at": started_at,
        "phase": "initializing",
        "prompt_kind_filter": prompt_kind or None,
        "limit": limit or 0,
        "total_jobs": len(jobs),
        "canonical_jobs": len(canonical_jobs),
        "relationship_jobs": len(relationship_jobs),
        "completed_jobs": 0,
        "successful_jobs": 0,
        "failed_jobs": 0,
        "skipped_jobs": 0,
        "stored_qras": 0,
        "generated_qras": 0,
        "current_item": "",
        "last_message": "Manifest loaded",
        "last_error": None,
        "chunk_num": None,
        "total_chunks": None,
        "range_start": None,
        "range_end": None,
        "progress_pct": 0.0,
    }

    def persist_state() -> None:
        state["updated_at"] = int(time.time())
        total_jobs = int(state.get("total_jobs", 0) or 0)
        completed_jobs = int(state.get("completed_jobs", 0) or 0)
        state["progress_pct"] = round((completed_jobs / total_jobs * 100.0), 1) if total_jobs else 0.0
        _write_json_atomic(CREATE_QRAS_MANIFEST_STATE_FILE, state)

    persist_state()

    def progress(msg: str):
        chunk_match = re.search(r"Chunk (\d+)/(\d+) \((\d+)-(\d+)/(\d+)\)", msg)
        if chunk_match:
            state["chunk_num"] = int(chunk_match.group(1))
            state["total_chunks"] = int(chunk_match.group(2))
            state["range_start"] = int(chunk_match.group(3))
            state["range_end"] = int(chunk_match.group(4))
        state["last_message"] = msg
        persist_state()
        typer.echo(f"  {msg}")

    def store_cb(qra: dict) -> bool:
        return _store_qra(memory, qra)

    def state_event(event: dict[str, Any]) -> None:
        if event.get("event") == "chunk_start":
            state["chunk_num"] = event.get("chunk_num")
            state["total_chunks"] = event.get("total_chunks")
            state["range_start"] = event.get("range_start")
            state["range_end"] = event.get("range_end")
        elif event.get("event") == "job_complete":
            state["completed_jobs"] = int(state.get("completed_jobs", 0)) + 1
            state["generated_qras"] = int(state.get("generated_qras", 0)) + int(event.get("qra_count", 0) or 0)
            state["stored_qras"] = int(state.get("stored_qras", 0)) + int(event.get("stored_count", 0) or 0)
            if event.get("skipped"):
                state["skipped_jobs"] = int(state.get("skipped_jobs", 0)) + 1
            elif event.get("ok"):
                state["successful_jobs"] = int(state.get("successful_jobs", 0)) + 1
            else:
                state["failed_jobs"] = int(state.get("failed_jobs", 0)) + 1
                state["last_error"] = event.get("error")

            source_id = event.get("source_id") or ""
            target_id = event.get("target_id") or ""
            state["current_item"] = f"{source_id} -> {target_id}" if target_id else source_id
        persist_state()

    try:
        # Process canonical jobs via _run_batch_independent_qras
        if canonical_jobs:
            state["phase"] = "canonical"
            state["last_message"] = f"Processing {len(canonical_jobs)} canonical jobs"
            persist_state()
            typer.echo(f"\nProcessing {len(canonical_jobs)} canonical jobs...")
            controls = []
            missing_controls = []
            for job in canonical_jobs:
                ctrl_id = job.get("identity", {}).get("source_control_id")
                if ctrl_id:
                    ctrl = _resolve_manifest_control(memory, ctrl_id, manifest_control_lookup)
                    if ctrl:
                        controls.append(ctrl)
                    else:
                        missing_controls.append(ctrl_id)

            if missing_controls:
                state["skipped_jobs"] = int(state.get("skipped_jobs", 0)) + len(missing_controls)
                state["completed_jobs"] = int(state.get("completed_jobs", 0)) + len(missing_controls)
                state["last_message"] = f"Skipped {len(missing_controls)} unresolved canonical jobs"
                persist_state()
                typer.echo(f"  Skipped {len(missing_controls)} canonical jobs with unresolved controls")

            if controls:
                results = asyncio.run(_run_batch_independent_qras(
                    controls=controls,
                    chunk_size=SCILLM_BATCH_CHUNK_SIZE,
                    progress_callback=progress,
                    store_callback=store_cb,
                    state_callback=state_event,
                    batch_id=batch_id,
                ))
                qra_count = sum(1 for r in results if isinstance(r, dict) and "error" not in r and not r.get("skipped"))
                skipped_items = [r for r in results if isinstance(r, dict) and r.get("skipped")]
                error_items = [r for r in results if isinstance(r, dict) and "error" in r]
                err_count = len(error_items)
                total_qras += qra_count
                errors += err_count
                state["last_message"] = f"Canonical complete: {qra_count} QRAs, {len(skipped_items)} skipped, {err_count} errors"
                persist_state()
                typer.echo(f"  Generated {qra_count} QRAs, {len(skipped_items)} skipped, {err_count} errors")
                for item in skipped_items[:5]:
                    typer.echo(
                        "    SKIP "
                        f"{item.get('control_id', item.get('source_id', 'unknown'))}: "
                        f"{item.get('skipped_reason', item.get('reason', 'unknown'))}"
                    )
                for item in error_items[:5]:
                    typer.echo(f"    ERROR {item.get('source_id', item.get('control_id', 'unknown'))}: {item.get('error')}")
                if qra_count == 0 and skipped_items and not error_items:
                    raise RuntimeError(
                        f"canonical manifest produced zero QRAs and skipped {len(skipped_items)} jobs; "
                        "treating as failed no-op"
                    )

        # Process relationship jobs via _run_batch_relationship_qras
        if relationship_jobs:
            state["phase"] = "relationship"
            state["last_message"] = f"Processing {len(relationship_jobs)} relationship jobs"
            persist_state()
            typer.echo(f"\nProcessing {len(relationship_jobs)} relationship jobs...")
            items = []
            missing_relationship_controls = []
            for job in relationship_jobs:
                identity = job.get("identity", {})
                source_record = job.get("source_record") or {}
                tech_id = identity.get("technique_id")
                cm_id = identity.get("countermeasure_id")
                tactic_id = identity.get("tactic_id")

                if tech_id and (cm_id or tactic_id):
                    other_id = cm_id or tactic_id
                    tech = _resolve_manifest_control(memory, tech_id, manifest_control_lookup)
                    other = _resolve_manifest_control(memory, other_id, manifest_control_lookup)
                    if not tech:
                        tech = _build_inline_relationship_control(
                            tech_id,
                            source_record.get("technique_name"),
                            "technique",
                            source_record.get("technique_description", ""),
                            job.get("source_framework") or "SPARTA",
                        )
                    if not other:
                        other = _build_inline_relationship_control(
                            other_id,
                            source_record.get("countermeasure_name") or source_record.get("tactic_name"),
                            "countermeasure" if cm_id else "tactic",
                            source_record.get("countermeasure_description") or source_record.get("parent_tactic_description", ""),
                            job.get("source_framework") or "SPARTA",
                        )
                    if tech and other:
                        items.append((tech, other, {}, job.get("prompt_kind")))
                    else:
                        missing_relationship_controls.append(job.get("job_id"))

            if missing_relationship_controls:
                state["skipped_jobs"] = int(state.get("skipped_jobs", 0)) + len(missing_relationship_controls)
                state["completed_jobs"] = int(state.get("completed_jobs", 0)) + len(missing_relationship_controls)
                state["last_message"] = f"Skipped {len(missing_relationship_controls)} unresolved relationship jobs"
                persist_state()
                typer.echo(f"  Skipped {len(missing_relationship_controls)} relationship jobs with unresolved controls")

            if items:
                results = asyncio.run(_run_batch_relationship_qras(
                    items=items,
                    chunk_size=SCILLM_BATCH_CHUNK_SIZE,
                    progress_callback=progress,
                    store_callback=store_cb,
                    state_callback=state_event,
                    batch_id=batch_id,
                ))
                qra_count = sum(1 for r in results if isinstance(r, dict) and "error" not in r and not r.get("skipped"))
                skipped_items = [r for r in results if isinstance(r, dict) and r.get("skipped")]
                error_items = [r for r in results if isinstance(r, dict) and "error" in r]
                err_count = len(error_items)
                total_qras += qra_count
                errors += err_count
                state["last_message"] = f"Relationship complete: {qra_count} QRAs, {len(skipped_items)} skipped, {err_count} errors"
                persist_state()
                typer.echo(f"  Generated {qra_count} QRAs, {len(skipped_items)} skipped, {err_count} errors")
                for item in skipped_items[:5]:
                    typer.echo(
                        "    SKIP "
                        f"{item.get('source_id', 'unknown')} -> {item.get('target_id', 'unknown')}: "
                        f"{item.get('skipped_reason', item.get('reason', 'unknown'))}"
                    )
                for item in error_items[:5]:
                    typer.echo(
                        f"    ERROR {item.get('source_id', 'unknown')} -> {item.get('target_id', 'unknown')}: {item.get('error')}"
                    )
                if qra_count == 0 and skipped_items and not error_items:
                    raise RuntimeError(
                        f"relationship manifest produced zero QRAs and skipped {len(skipped_items)} jobs; "
                        "treating as failed no-op"
                    )

        state["status"] = "completed"
        state["phase"] = "done"
        state["last_message"] = f"Complete: {total_qras} QRAs, {errors} errors"
        persist_state()
        typer.echo(f"\n=== Complete ===")
        typer.echo(f"  Total QRAs: {total_qras}")
        typer.echo(f"  Total errors: {errors}")
    except Exception as exc:
        state["status"] = "failed"
        state["last_error"] = str(exc)
        state["last_message"] = f"Failed: {exc}"
        persist_state()
        raise


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


@app.command()
def review(
    manifest_path: str = typer.Argument(..., help="Path to execution manifest JSON"),
    output: str = typer.Option("", "--output", "-o", help="Output path for review JSON (default: manifest_review.json)"),
    audit_legacy_overlap: bool = typer.Option(
        False,
        "--audit-legacy-overlap",
        help="Opt in to scanning legacy sparta_qra for overlap warnings. Disabled by default because v2 target collections are authoritative for repair gating.",
    ),
):
    """Generate a review dossier for a manifest with deterministic checks.

    Computes:
    - Duplicate job_id / logical key detection
    - Missing prompt_kind rows
    - Sentinel/placeholder row counts
    - Collection reconciliation
    - Source/target referential integrity
    - Already-existing QRA skip counts
    - Prompt hash verification
    - Final verdict: BLOCKED / CANARY_ONLY / FULL_RUN_OK

    Example:
        python generator.py review sparta_v2_manifest.json
        python generator.py review sparta_v2_manifest.json -o review_output.json
    """
    from pathlib import Path as P
    from datetime import datetime
    import hashlib

    manifest_file = P(manifest_path)
    if not manifest_file.exists():
        typer.echo(f"Manifest not found: {manifest_path}", err=True)
        raise typer.Exit(1)

    with open(manifest_file) as f:
        manifest_data = json.load(f)

    jobs = manifest_data.get("jobs", [])
    typer.echo(f"Reviewing manifest: {manifest_path} ({len(jobs)} jobs)")

    # === Deterministic checks ===
    blocking_issues = []
    warnings = []

    # 1. Duplicate job_id
    job_ids = [j.get("job_id") for j in jobs if j.get("job_id")]
    dup_job_ids = [jid for jid in set(job_ids) if job_ids.count(jid) > 1]
    if dup_job_ids:
        blocking_issues.append({
            "id": "B001",
            "title": "Duplicate job_id",
            "detail": f"Found {len(dup_job_ids)} duplicate job_ids: {dup_job_ids[:5]}"
        })

    # 2. Duplicate logical keys (source+target for relationships)
    logical_keys = []
    for j in jobs:
        identity = j.get("identity", {})
        if j.get("job_type") == "relationship":
            key = f"{identity.get('technique_id', '')}:{identity.get('countermeasure_id', identity.get('tactic_id', ''))}"
        else:
            key = identity.get("source_control_id", j.get("job_id", ""))
        logical_keys.append(key)
    dup_logical = [k for k in set(logical_keys) if logical_keys.count(k) > 1]
    if dup_logical:
        blocking_issues.append({
            "id": "B002",
            "title": "Duplicate logical keys",
            "detail": f"Found {len(dup_logical)} duplicates: {dup_logical[:5]}"
        })

    # 3. Missing prompt_kind
    missing_prompt_kind = [j.get("job_id") for j in jobs if not j.get("prompt_kind")]
    if missing_prompt_kind:
        blocking_issues.append({
            "id": "B003",
            "title": "Missing prompt_kind",
            "detail": f"{len(missing_prompt_kind)} jobs missing prompt_kind: {missing_prompt_kind[:5]}"
        })

    # 4. Sentinel/placeholder detection
    sentinel_patterns = ["CM-NA", "Not Identified", "placeholder", "TBD", "N/A", "UNKNOWN"]
    sentinel_rows = []
    for j in jobs:
        identity = j.get("identity", {})
        identity_str = json.dumps(identity).lower()
        for pattern in sentinel_patterns:
            if pattern.lower() in identity_str:
                sentinel_rows.append({"job_id": j.get("job_id"), "pattern": pattern})
                break
    if sentinel_rows:
        warnings.append({
            "id": "W001",
            "title": "Sentinel/placeholder rows detected",
            "detail": f"{len(sentinel_rows)} rows contain sentinel patterns (will return zero pairs per policy)"
        })

    # 5. Referential integrity + existing-QRA checks (via /memory HTTPX only)
    memory = None
    missing_source = []
    missing_target = []
    existing_target_jobs: list[dict[str, Any]] = []
    legacy_existing_qras: dict[str, dict[str, int]] = {}
    qra_lookup_errors: list[dict[str, str]] = []
    source_ids = sorted({
        _normalized_job_source_id(j)
        for j in jobs
        if _normalized_job_source_id(j)
    })
    target_ids = sorted({
        (
            j.get("identity", {}).get("target_control_id")
            or j.get("identity", {}).get("countermeasure_id")
            or j.get("identity", {}).get("tactic_id")
        )
        for j in jobs
        if j.get("job_type") == "relationship"
        and (
            j.get("identity", {}).get("target_control_id")
            or j.get("identity", {}).get("countermeasure_id")
            or j.get("identity", {}).get("tactic_id")
        )
    })
    try:
        memory = _get_memory_client()
    except Exception as e:
        warnings.append({
            "id": "W006",
            "title": "DB connectivity failed",
            "detail": f"Could not create /memory client: {e}"
        })
        memory = None

    if memory is not None:
        try:
            resolved_sources = _fetch_existing_control_ids(memory, source_ids)
            resolved_targets = _fetch_existing_control_ids(memory, target_ids)
            missing_source = [cid for cid in source_ids if cid not in resolved_sources]
            missing_target = [cid for cid in target_ids if cid not in resolved_targets]
            if missing_source:
                blocking_issues.append({
                    "id": "B004",
                    "title": "Missing source controls",
                    "detail": f"{len(missing_source)} source controls not in DB: {missing_source[:5]}"
                })
            if missing_target:
                warnings.append({
                    "id": "W002",
                    "title": "Missing target controls",
                    "detail": f"{len(missing_target)} target controls not in DB: {missing_target[:5]}"
                })
        except Exception as e:
            warnings.append({
                "id": "W006",
                "title": "DB connectivity failed",
                "detail": f"Could not verify referential integrity: {e}"
            })

        try:
            existing_target_jobs = _summarize_existing_v2_jobs(
                memory,
                jobs,
                progress_callback=lambda msg: typer.echo(f"  {msg}"),
            )
            if existing_target_jobs:
                warnings.append({
                    "id": "W003",
                    "title": "Already-existing target-collection jobs",
                    "detail": f"{len(existing_target_jobs)} manifest jobs already exist in v2 target collections"
                })
        except Exception as e:
            warnings.append({
                "id": "W007",
                "title": "Target-collection lookup failed",
                "detail": f"Could not verify existing v2 target jobs: {e}"
            })

        if audit_legacy_overlap:
            try:
                legacy_existing_qras, qra_lookup_errors = _summarize_existing_qras(
                    memory,
                    source_ids,
                    progress_callback=lambda msg: typer.echo(f"  {msg}"),
                )
                if legacy_existing_qras:
                    warnings.append({
                        "id": "W004",
                        "title": "Legacy sparta_qra overlap",
                        "detail": f"{len(legacy_existing_qras)} source controls already have legacy sparta_qra docs"
                    })
                if qra_lookup_errors:
                    warnings.append({
                        "id": "W005",
                        "title": "Existing-QRA scan errors",
                        "detail": f"{len(qra_lookup_errors)} paged legacy sparta_qra scans failed during review"
                    })
            except Exception as e:
                warnings.append({
                    "id": "W008",
                    "title": "Legacy overlap lookup failed",
                    "detail": f"Could not verify legacy sparta_qra overlap: {e}"
                })

    # 6. Prompt inventory with hashes
    prompt_kinds = set(j.get("prompt_kind") for j in jobs if j.get("prompt_kind"))
    prompt_inventory = []
    sparta_prompts_dir = Path(__file__).parent / "prompts" / "native" / "sparta"
    shared_base_file = sparta_prompts_dir / "_shared_base.txt"
    shared_base_hash = None
    if shared_base_file.exists():
        shared_base_hash = hashlib.md5(shared_base_file.read_text().encode()).hexdigest()
    for pk in prompt_kinds:
        # Map prompt_kind to file
        prompt_file_map = {
            "sparta_technique_canonical": "technique_canonical",
            "sparta_tactic_canonical": "tactic_canonical",
            "sparta_countermeasure_canonical": "countermeasure_canonical",
            "sparta_tactic_technique_relationship": "tactic_technique_relationship",
            "sparta_technique_countermeasure_relationship": "technique_countermeasure_relationship",
            "sparta_url_excerpt": "url_excerpt",
        }
        file_stem = prompt_file_map.get(pk, pk.replace("sparta_", ""))
        system_file = sparta_prompts_dir / f"{file_stem}_system.txt"
        user_file = sparta_prompts_dir / f"{file_stem}_user.txt"

        sys_hash = None
        user_hash = None
        pair_types = []
        version = "unknown"

        if system_file.exists():
            content = system_file.read_text()
            sys_hash = hashlib.md5(content.encode()).hexdigest()
            # Extract version from comment
            for line in content.split("\n")[:10]:
                if "Prompt version:" in line:
                    version = line.split(":")[-1].strip().split()[0]
                    break
            # Extract pair_types from JSON schema
            if '"pair_type":' in content:
                import re
                match = re.search(r'"pair_type":\s*"([^"]+)"', content)
                if match:
                    pair_types = [p.strip() for p in match.group(1).split("|")]

        if user_file.exists():
            user_hash = hashlib.md5(user_file.read_text().encode()).hexdigest()

        prompt_inventory.append({
            "prompt_kind": pk,
            "version": version,
            "shared_base_path": str(shared_base_file),
            "shared_base_hash": shared_base_hash,
            "system_prompt_path": str(system_file),
            "system_prompt_hash": sys_hash,
            "user_prompt_path": str(user_file),
            "user_prompt_hash": user_hash,
            "max_pairs": 3,  # From prompts
            "pair_types": pair_types,
            "semantic_risks": ["two_sided_evidence_required"] if "relationship" in pk else []
        })

    # 7. Compute verdict
    if blocking_issues:
        verdict_status = "BLOCKED"
        verdict_reason = f"{len(blocking_issues)} blocking issues must be resolved"
    elif warnings:
        verdict_status = "CANARY_ONLY"
        verdict_reason = f"{len(warnings)} warnings require review before full run"
    else:
        verdict_status = "FULL_RUN_OK"
        verdict_reason = "All checks passed"

    # 8. Build review dossier
    manifest_hash = hashlib.sha256(json.dumps(manifest_data, sort_keys=True).encode()).hexdigest()[:16]

    review_dossier = {
        "schema_version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "batch_identity": {
            "batch_name": manifest_data.get("batch_name", manifest_file.stem),
            "execution_manifest_path": str(manifest_file),
            "execution_manifest_hash": f"sha256:{manifest_hash}"
        },
        "verdict": {
            "status": verdict_status,
            "reason": verdict_reason,
            "blocking_count": len(blocking_issues),
            "warning_count": len(warnings)
        },
        "blocking_issues": blocking_issues,
        "warnings": warnings,
        "prompt_inventory": prompt_inventory,
        "db_sanity": [
            {
                "name": "referential_integrity",
                "status": "fail" if missing_source else ("warn" if missing_target else "pass"),
                "detail": f"sources_missing={len(missing_source)}, targets_missing={len(missing_target)}",
            },
            {
                "name": "existing_target_collection_jobs",
                "status": "warn" if existing_target_jobs else "pass",
                "detail": f"{len(existing_target_jobs)} jobs already exist in v2 collections",
            },
            {
                "name": "legacy_sparta_qra_overlap",
                "status": ("warn" if legacy_existing_qras else "pass") if audit_legacy_overlap else "skipped",
                "detail": (
                    f"{len(legacy_existing_qras)} source ids already exist in legacy sparta_qra"
                    if audit_legacy_overlap
                    else "legacy overlap scan skipped by default; v2 target collections are authoritative for repair gating"
                ),
            },
            {
                "name": "existing_qra_lookup",
                "status": "warn" if qra_lookup_errors else "pass",
                "detail": f"{len(qra_lookup_errors)} lookup errors",
            },
        ],
        "manifest_invariants": [
            {"name": "duplicate_job_ids", "status": "pass" if not dup_job_ids else "fail", "value": len(dup_job_ids)},
            {"name": "duplicate_logical_keys", "status": "pass" if not dup_logical else "fail", "value": len(dup_logical)},
            {"name": "sentinel_rows", "status": "warn" if sentinel_rows else "pass", "value": len(sentinel_rows)},
            {"name": "missing_prompt_kind", "status": "pass" if not missing_prompt_kind else "fail", "value": len(missing_prompt_kind)},
        ],
        "risky_samples": [
            {"job_id": s["job_id"], "prompt_kind": next((j.get("prompt_kind") for j in jobs if j.get("job_id") == s["job_id"]), "unknown"), "reasons": [f"Contains: {s['pattern']}"]}
            for s in sentinel_rows[:20]
        ],
        "executor": {
            "path": str(Path(__file__)),
            "hash": hashlib.md5(Path(__file__).read_bytes()).hexdigest()[:16],
            "crash_safe": True,
            "resume_supported": True,
            "default_concurrency": 4,
            "write_mode": "chunked",
            "timeout_seconds": 300,
            "batch_pattern": "as_completed",
            "evidence_enrichment": True
        },
        "required_actions": []
    }

    # Populate required_actions
    if blocking_issues:
        review_dossier["required_actions"].append("Fix all blocking issues before execution")
    if sentinel_rows:
        review_dossier["required_actions"].append(f"Review {len(sentinel_rows)} sentinel rows (will return zero pairs)")
    if existing_target_jobs:
        review_dossier["required_actions"].append("Decide: skip or regenerate jobs already present in v2 target collections")

    # Output
    if output:
        output_path = P(output)
    else:
        output_path = manifest_file.with_name(manifest_file.stem.replace("_manifest", "_review") + ".json")

    with open(output_path, "w") as f:
        json.dump(review_dossier, f, indent=2)

    # Print summary
    typer.echo(f"\n{'='*60}")
    typer.echo(f"Review Dossier: {output_path}")
    typer.echo(f"{'='*60}")
    typer.echo(f"Verdict: {verdict_status}")
    typer.echo(f"Reason: {verdict_reason}")
    typer.echo(f"Blocking: {len(blocking_issues)} | Warnings: {len(warnings)}")
    typer.echo(f"Prompts: {len(prompt_inventory)} kinds")
    typer.echo(f"Sentinels: {len(sentinel_rows)} rows")
    if review_dossier["required_actions"]:
        typer.echo(f"\nRequired actions:")
        for action in review_dossier["required_actions"]:
            typer.echo(f"  - {action}")
    typer.echo(f"\nReview saved to: {output_path}")


if __name__ == "__main__":
    app()
