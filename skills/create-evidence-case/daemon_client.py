"""Thin httpx client for /memory daemon endpoints.

All data access goes through the daemon via Unix socket.
This replaces direct graph_memory imports.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any

import httpx
from loguru import logger


SOCKET_PATH = "/run/user/1000/embry/memory.sock"
TIMEOUT = httpx.Timeout(60.0, connect=5.0)


def _get_client() -> httpx.Client:
    """Get httpx client with Unix socket transport."""
    transport = httpx.HTTPTransport(uds=SOCKET_PATH)
    return httpx.Client(transport=transport, base_url="http://localhost", timeout=TIMEOUT)


def assemble_evidence(
    question: str,
    source_id: str | None = None,
    skip_qra_recall: bool = False,
) -> dict[str, Any]:
    """Call daemon /create-evidence-case for evidence assembly.

    Args:
        question: Question text (used for QRA recall if not skipped)
        source_id: Explicit control ID (e.g., "CWE-287") - enables fast path
        skip_qra_recall: If True and source_id provided, skip entity extraction
                         and build evidence directly from known control

    Returns: {question_text, glossary, crosswalk_chains, prior_qra_evidence, ...}
    """
    with _get_client() as client:
        resp = client.post("/create-evidence-case", json={
            "question": question,
            "source_id": source_id or "",
            "skip_qra_recall": skip_qra_recall,
        })
        if resp.status_code != 200:
            logger.error("assemble_evidence failed: HTTP {}", resp.status_code)
            return {"error": f"HTTP {resp.status_code}", "question": question}
        return resp.json()


def assemble_evidence_fast(source_id: str) -> dict[str, Any]:
    """Fast path: assemble evidence from a known control ID.

    Skips entity extraction and QRA recall. Uses direct graph traversal
    from the control's crosswalk edges. ~50ms vs ~500ms.
    """
    question = f"What is {source_id}?"
    return assemble_evidence(question, source_id=source_id, skip_qra_recall=True)


def assemble_evidence_batch(
    items: list[tuple[str, str | None]],
    max_workers: int = 8,
) -> list[dict[str, Any]]:
    """Batch evidence assembly using daemon's parallel endpoint.

    Args:
        items: List of (question, source_id) tuples
        max_workers: Parallel workers in daemon (default 8)

    Returns:
        List of {question, source_id, evidence} or {question, source_id, error}
    """
    if not items:
        return []

    payload = {
        "items": [
            {"question": q, "source_id": sid or "", "skip_qra_recall": True}
            for q, sid in items
        ],
        "max_workers": max_workers,
    }

    with _get_client() as client:
        resp = client.post("/create-evidence-case-batch", json=payload, timeout=httpx.Timeout(300.0, connect=5.0))
        if resp.status_code != 200:
            logger.error("assemble_evidence_batch failed: HTTP {}", resp.status_code)
            return [{"question": q, "source_id": sid, "error": f"HTTP {resp.status_code}"} for q, sid in items]
        return resp.json().get("results", [])


def extract_entities(text: str) -> dict[str, Any]:
    """Call daemon /extract-entities."""
    with _get_client() as client:
        resp = client.post("/extract-entities", json={"text": text})
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}"}
        return resp.json()


def recall(
    q: str,
    k: int = 10,
    collections: list[str] | None = None,
    threshold: float = 0.3,
) -> dict[str, Any]:
    """Call daemon /recall for semantic search."""
    with _get_client() as client:
        payload = {"q": q, "k": k, "threshold": threshold}
        if collections:
            payload["collections"] = collections
        resp = client.post("/recall", json=payload)
        if resp.status_code != 200:
            return {"found": False, "items": [], "error": f"HTTP {resp.status_code}"}
        return resp.json()


def store(document: dict[str, Any], collection: str = "sparta_qra") -> dict[str, Any]:
    """Call daemon /store to persist a document."""
    # Ensure _key exists
    if "_key" not in document:
        key_source = document.get("question", "") + "|" + document.get("source_control_id", "")
        document["_key"] = hashlib.sha256(key_source.encode()).hexdigest()[:16]

    with _get_client() as client:
        resp = client.post("/store", json={
            "document": document,
            "collection": collection,
        })
        if resp.status_code != 200:
            logger.error("store failed: HTTP {} - {}", resp.status_code, resp.text[:200])
            return {"ok": False, "error": f"HTTP {resp.status_code}"}
        return resp.json()


def upsert(documents: list[dict], collection: str) -> dict[str, Any]:
    """Call daemon /upsert for batch writes."""
    with _get_client() as client:
        resp = client.post("/upsert", json={
            "collection": collection,
            "documents": documents,
        })
        if resp.status_code != 200:
            return {"ok": False, "error": f"HTTP {resp.status_code}"}
        return resp.json()


def list_controls(
    collection: str = "sparta_controls",
    filters: dict | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Call daemon /list for paginated collection access."""
    with _get_client() as client:
        payload = {
            "collection": collection,
            "limit": limit,
            "offset": offset,
        }
        if filters:
            payload["filters"] = filters
        resp = client.post("/list", json=payload)
        if resp.status_code != 200:
            return {"documents": [], "total": 0, "error": f"HTTP {resp.status_code}"}
        return resp.json()


# ---------------------------------------------------------------------------
# v4.3 QRA Schema Builder
# ---------------------------------------------------------------------------

def enrich_v43(
    evidence: dict[str, Any],
    question: str,
    answer: str | None = None,
    source_framework: str | None = None,
    source_control_id: str | None = None,
    expertise: str = "expert",
    relationship_id: str | None = None,
) -> dict[str, Any]:
    """Build v4.3 QRA document from daemon evidence response.

    Args:
        evidence: Response from assemble_evidence()
        question: Original question text
        answer: Synthesized answer (if None, uses prior_qra_evidence)
        source_framework: Override framework detection
        source_control_id: Override control ID detection
        expertise: QRA expertise level
        relationship_id: Links persona variations

    Returns:
        v4.3 QRA document ready for /store
    """
    # Detect source framework/ID from evidence if not provided
    if not source_framework:
        if evidence.get("cwe_record"):
            source_framework = "CWE"
            source_control_id = source_control_id or evidence["cwe_record"].get("control_id")
        elif evidence.get("capec_record"):
            source_framework = "CAPEC"
            source_control_id = source_control_id or evidence["capec_record"].get("control_id")
        else:
            # Check glossary for first entity
            glossary = evidence.get("glossary", [])
            if glossary:
                source_framework = glossary[0].get("framework", "SPARTA")
                source_control_id = source_control_id or glossary[0].get("id")
            else:
                source_framework = "SPARTA"

    # Build crosswalk chains into evidence_case (self-contained structure)
    crosswalk_chains = evidence.get("crosswalk_chains", [])
    glossary = evidence.get("glossary", [])

    # Determine status based on assembly outcome
    # NOTE: "partial_chain" removed — chains don't have a partial flag
    if evidence.get("error"):
        status = "error"
    elif not glossary:
        status = "no_entity"
    elif not crosswalk_chains:
        status = "unmapped"
    else:
        status = "assembled"

    # Calculate scores (replacing monolithic 'confidence')
    retrieval_score = evidence.get("retrieval_score", 0.0)
    chain_density = min(1.0, len(crosswalk_chains) * 0.2) if crosswalk_chains else 0.0

    if crosswalk_chains:
        # Extract unique methods
        methods = sorted(set(
            c.get("relationship", c.get("method", "direct"))
            for c in crosswalk_chains
        ))
        evidence_case = {
            "status": status,
            "chains": crosswalk_chains,
            "methods": methods,
            # Formal proof (populated by enrich_with_proof)
            "formal_proof": None,
            # SACM reference (populated by enrich_with_sacm)
            "sacm_ref": None,
            # Provenance
            "graph_version": evidence.get("graph_version", "unknown"),
            "traversal_method": evidence.get("traversal_method", "bfs"),
            "assembled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    else:
        # Informational QRA: no crosswalk chains but still valid
        evidence_case = {
            "status": status,
            "chains": [],
            "methods": [],
            "formal_proof": None,
            "sacm_ref": None,
            "graph_version": evidence.get("graph_version", "unknown"),
            "traversal_method": evidence.get("traversal_method", "bfs"),
            "assembled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

    # Scores as separate top-level field (not inside evidence_case)
    scores = {
        "retrieval_score": retrieval_score,
        "chain_density": chain_density,
    }

    # Determine difficulty
    if not crosswalk_chains:
        difficulty = "single_hop"
    elif len(crosswalk_chains) == 1 and len(crosswalk_chains[0].get("hops", [])) <= 1:
        difficulty = "single_hop"
    elif any(len(c.get("hops", [])) > 2 for c in crosswalk_chains):
        difficulty = "synthesis"
    else:
        difficulty = "multi_hop"

    # Extract Mind tags from glossary entities
    mind_tags = set()
    for g in evidence.get("glossary", []):
        # SPARTA technique prefixes map to Mind tags
        gid = g.get("id", "")
        if gid.startswith("DE-"):
            mind_tags.add("Detect")
        elif gid.startswith("EX-") or gid.startswith("LM-"):
            mind_tags.add("Exploit")
        elif gid.startswith("PE-"):
            mind_tags.add("Persist")
        elif gid.startswith("EV-"):
            mind_tags.add("Evade")
        elif gid.startswith("RE-"):
            mind_tags.add("Restore")
        elif gid.startswith("CM") or gid.startswith("SV-"):
            mind_tags.add("Harden")

    # Synthesize answer from prior QRA evidence if not provided
    if not answer:
        prior = evidence.get("prior_qra_evidence", [])
        if prior:
            answer = prior[0].get("answer", "")[:1000]
        else:
            # Use glossary descriptions
            glossary = evidence.get("glossary", [])
            if glossary:
                answer = glossary[0].get("description", "")[:1000]
            else:
                answer = ""

    # Requirement text from source record
    requirement = ""
    if evidence.get("cwe_record"):
        requirement = evidence["cwe_record"].get("description", "")
    elif evidence.get("capec_record"):
        requirement = evidence["capec_record"].get("description", "")
    elif evidence.get("glossary"):
        requirement = evidence["glossary"][0].get("description", "")

    # Build v4.3 QRA document
    ts = int(time.time())

    # Generate unique run_id and qra_id for index compatibility
    # Existing sparta_qra has unique index on (run_id, qra_id)
    key_hash = hashlib.sha256(f"{question}|{source_control_id}".encode()).hexdigest()[:16]

    return {
        # Index compatibility (existing unique constraint on run_id, qra_id)
        "run_id": f"ec_v43_{ts // 86400}",  # date-based run_id
        "qra_id": f"v43_{source_control_id}_{key_hash}",  # unique per control+question

        # Core QRA fields
        "question": question[:500],
        "requirement": requirement[:1000],
        "answer": answer[:2000],
        "source_framework": source_framework,
        "source_control_id": source_control_id,
        "relationship_id": relationship_id or f"EC-{ts}",
        "expertise": expertise,
        "difficulty": difficulty,

        # Taxonomy
        "mind": sorted(mind_tags) if mind_tags else [],

        # Evidence case (self-contained with chains, formal_proof, sacm_ref)
        "evidence_case": evidence_case,

        # Assembly scores (NOT match confidence — retrieval metrics only)
        "scores": scores,

        # Metadata
        "created_at": ts,
        "source": "create-evidence-case-v43",
        "review_status": evidence.get("review_status", "pending"),

        # Lineage tracking (for staleness detection)
        "lineage": {
            # Graph state at assembly time
            "graph_version": evidence.get("graph_version", "unknown"),
            "graph_edge_count": evidence.get("graph_edge_count"),
            # Resolved entities (detect deprecation)
            "entity_ids": [g.get("id") for g in glossary if g.get("id")],
            "entity_frameworks": sorted(set(g.get("framework", "") for g in glossary if g.get("framework"))),
            # Prior QRAs used as evidence (detect upstream staleness)
            "upstream_qra_keys": [
                p.get("_key") for p in evidence.get("prior_qra_evidence", [])
                if p.get("_key")
            ],
            # Source document hashes (future: detect doc changes)
            "source_doc_hashes": [],  # Populated when fetching from external docs
            # Model versions (detect embedding/LLM drift)
            "embedding_model": evidence.get("embedding_model", "unknown"),
            "extractor_version": "v43",
            # Assembly timestamp (for time-based invalidation)
            "assembled_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },

        # Keep raw evidence for debugging
        "_evidence_glossary_count": len(glossary),
        "_evidence_chain_count": len(crosswalk_chains),
    }


def create_qra(
    question: str,
    source_id: str | None = None,
    answer: str | None = None,
    expertise: str = "expert",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Full pipeline: assemble evidence → enrich v4.3 → store.

    Args:
        question: Question or control ID to process
        source_id: Explicit source control ID (e.g., "CWE-287")
        answer: Pre-synthesized answer (if None, extracted from evidence)
        expertise: QRA expertise level
        dry_run: If True, return QRA without persisting

    Returns:
        v4.3 QRA document (persisted if not dry_run)
    """
    # Step 1: Assemble evidence via daemon
    evidence = assemble_evidence(question, source_id=source_id)

    if evidence.get("error"):
        return {"error": evidence["error"], "question": question}

    # Step 2: Enrich with v4.3 schema
    qra = enrich_v43(
        evidence=evidence,
        question=question,
        answer=answer,
        source_control_id=source_id,
        expertise=expertise,
    )

    # Step 3: Persist via daemon (unless dry_run)
    if not dry_run:
        result = store(qra, collection="sparta_qra")
        qra["_store_result"] = result

    return qra


# ---------------------------------------------------------------------------
# Evidence Enrichment: Lean4 Proofs and SACM References
# ---------------------------------------------------------------------------

LEAN4_SERVICE_URL = "http://127.0.0.1:8604"


def prove_requirement(
    requirement: str,
    tactics: list[str] | None = None,
    timeout: int = 60,
) -> dict[str, Any]:
    """Call lean4-prove-service to generate a formal proof.

    WHY FORMAL PROOFS ARE NEEDED:
    Matching (crosswalk chains, QRA evidence, semantic similarity) provides
    TRACEABILITY — "these things are related." But for certification (ISO 26262,
    DO-178C), we need VERIFICATION — proof that the control FUNCTIONALLY SATISFIES
    the requirement, not just that they share vocabulary.

    Example:
      Requirement: "shall implement multi-factor authentication"
      Control: SV-AC-2 "implement access control mechanisms"
      Matching confidence: 0.82 (crosswalk exists, QRAs mention both)
      Problem: Does SV-AC-2 actually cover MFA? Words overlap, function might not.

    The formal proof attempts to show: Control ⊢ Requirement (entailment).
    If the proof succeeds, the control is a valid implementation of the requirement.

    Args:
        requirement: The theorem/requirement to prove (natural language or formal)
        tactics: Optional list of preferred Lean4 tactics
        timeout: Compilation timeout in seconds

    Returns:
        {success, code, attempts, errors, proved_at}
    """
    try:
        resp = httpx.post(
            f"{LEAN4_SERVICE_URL}/prove",
            json={
                "requirement": requirement,
                "tactics": tactics or [],
                "model": "text",
                "max_retries": 3,
                "timeout": timeout,
            },
            timeout=httpx.Timeout(timeout + 30.0, connect=5.0),
        )
        if resp.status_code != 200:
            return {"success": False, "error": f"HTTP {resp.status_code}"}
        result = resp.json()
        result["proved_at"] = int(time.time()) if result.get("success") else None
        return result
    except httpx.TimeoutException:
        return {"success": False, "error": "timeout"}
    except Exception as exc:
        logger.error("prove_requirement failed: {}", exc)
        return {"success": False, "error": str(exc)}


def generate_sacm_ref(
    control_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Generate SACM reference for a control via create-gsn-diagram.

    Args:
        control_id: The control ID (e.g., "AC-1", "CWE-79")
        dry_run: If True, generate sample without ArangoDB query

    Returns:
        {gid, xml_snippet, generated_at} or {error}
    """
    import subprocess

    cmd = [
        "/home/graham/.claude/skills/create-gsn-diagram/run.sh",
        "export-sacm",
        "--control", control_id,
    ]
    if dry_run:
        cmd.append("--dry-run")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd="/home/graham/.claude/skills/create-gsn-diagram",
        )
        if result.returncode != 0:
            return {"error": result.stderr[:200] or "export-sacm failed"}

        # Parse the XML to extract GID
        xml_output = result.stdout
        gid = None
        if 'gid="G' in xml_output:
            # Extract first goal GID
            import re
            match = re.search(r'gid="(G\d+)"', xml_output)
            if match:
                gid = match.group(1)

        return {
            "gid": gid or f"G_{control_id}",
            "xml_snippet": xml_output[:500] if len(xml_output) > 500 else xml_output,
            "generated_at": int(time.time()),
        }
    except subprocess.TimeoutExpired:
        return {"error": "timeout"}
    except Exception as exc:
        logger.error("generate_sacm_ref failed: {}", exc)
        return {"error": str(exc)}


def enrich_evidence_case(
    qra: dict[str, Any],
    with_proof: bool = True,
    with_sacm: bool = True,
    proof_timeout: int = 60,
) -> dict[str, Any]:
    """Enrich a QRA's evidence_case with formal proof and SACM reference.

    Modifies qra in-place and returns it.

    Args:
        qra: The QRA document (must have evidence_case)
        with_proof: Generate formal proof via lean4-prove
        with_sacm: Generate SACM reference via create-gsn-diagram
        proof_timeout: Timeout for proof generation

    Returns:
        The enriched QRA document
    """
    evidence_case = qra.get("evidence_case")
    if evidence_case is None:
        evidence_case = {"chains": [], "confidence": 0.0, "methods": []}
        qra["evidence_case"] = evidence_case

    # Generate formal proof from requirement
    # GATE: Only attempt proof if deterministic checks pass (chains exist)
    # Per WALKTHROUGH.md: Informational status doesn't need proofs
    chains = evidence_case.get("chains") or []
    has_chains = len(chains) > 0
    if with_proof and evidence_case.get("formal_proof") is None and has_chains:
        requirement = qra.get("requirement") or qra.get("question", "")
        if requirement:
            proof_result = prove_requirement(requirement, timeout=proof_timeout)
            evidence_case["formal_proof"] = {
                "success": proof_result.get("success", False),
                "code": proof_result.get("code"),
                "attempts": proof_result.get("attempts", 0),
                "errors": proof_result.get("errors"),
                "proved_at": proof_result.get("proved_at"),
            }

    # Generate SACM reference from control ID
    if with_sacm and evidence_case.get("sacm_ref") is None:
        control_id = qra.get("source_control_id")
        if control_id:
            sacm_result = generate_sacm_ref(control_id)
            if not sacm_result.get("error"):
                evidence_case["sacm_ref"] = {
                    "gid": sacm_result.get("gid"),
                    "xml_snippet": sacm_result.get("xml_snippet"),
                    "generated_at": sacm_result.get("generated_at"),
                }

    return qra
